from datetime import datetime

from sqlalchemy.orm import Session

from src.models.project import Project
from src.models.task import Task, TaskKind, TaskState
from src.services import events, projects, refs, versioning
from src.services.errors import ConflictError, InvalidTransitionError, NotFoundError, ValidationError

# Fields update() is allowed to touch; state, kind, placement in the tree and
# timestamps only ever change through the dedicated functions.
_UPDATABLE_FIELDS = {"title", "body", "context", "size"}

# States in which a work item is closed; a feature can only close once all
# its children are in one of them.
_CLOSED_STATES = (TaskState.DONE, TaskState.CANCELLED)


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------

def _require_valid_title(title : str) -> None:
    """Refuse an empty task title.

    Args:
        title: The title to check.

    Raises:
        ValidationError: If the title is empty.
    """
    if not title.strip() :
        raise ValidationError("The title must be specified.")


def _require_closed_children(task : Task) -> None:
    """Refuse to close a feature that still has open children.

    Args:
        task: The feature (or task) about to be completed or cancelled.

    Raises:
        ConflictError: If one of its children is neither done nor cancelled.
    """
    open_children = [child.ref for child in task.children if child.state not in _CLOSED_STATES]
    if open_children:
        raise ConflictError(
            f"feature '{task.ref}' still has open children: {', '.join(open_children)}.")

def _descendants(task : Task) -> list:
    """Return every feature and task below a work item, depth first.

    Args:
        task: The work item to walk from.
    """
    found = []
    for child in task.children:
        found.append(child)
        found.extend(_descendants(child))
    return found

def _resolve_placement(session : Session, task : Task | None, project_key : str | None,
                       parent_ref : str | None) -> tuple[Project | None, Task | None]:
    """Work out and check where a work item goes in the tree.

    Args:
        session: Database session to use.
        task: The item being placed, or None when it is being created.
        project_key: Key of the project or subproject to place it in.
        parent_ref: Ref of the feature to place it under. Its project is
            used when project_key is None.

    Returns:
        The (project, parent feature) pair; either may be None.

    Raises:
        NotFoundError: If the project or the parent doesn't exist.
        ValidationError: If the parent isn't a feature, has no project, sits
            in another project than project_key, or is the item itself or one
            of its descendants.
    """
    project = projects.get(session, project_key) if project_key else None
    parent = get_by_ref(session, parent_ref) if parent_ref else None
    if parent is None:
        return project, None

    if parent.kind is not TaskKind.FEATURE:
        raise ValidationError(f"'{parent.ref}' is a task; only a feature can hold children.")
    if parent.project is None:
        raise ValidationError(f"feature '{parent.ref}' has no project yet.")
    if project is not None and parent.project_id != project.id:
        raise ValidationError(f"feature '{parent.ref}' isn't in project '{project.key}'.")
    if task is not None and (parent is task or parent in _descendants(task)):
        raise ValidationError(f"'{task.ref}' can't go under itself or one of its descendants.")
    return parent.project, parent

def _next_position(session : Session, project : Project | None, parent : Task | None) -> int:
    """Return the position after the last sibling at a place in the tree.

    Args:
        session: Database session to use.
        project: Project of the place, or None for raw captures.
        parent: Feature of the place, or None for the top of the project.
    """
    siblings = session.query(Task).filter_by(project_id=project.id if project else None,
                                             parent_id=parent.id if parent else None)
    positions = [sibling.position for sibling in siblings]
    return max(positions) + 1 if positions else 0

def _where(task : Task) -> dict:
    """Describe a work item's place in the tree for an event payload.

    Args:
        task: The work item.

    Returns:
        {"project": key or None, "parent": ref or None}.
    """
    return {"project": task.project.key if task.project else None,
            "parent": task.parent.ref if task.parent else None}

def _set_place(task : Task, project : Project | None, parent : Task | None) -> None:
    """Put a work item at a place in the tree, its whole subtree following.

    Args:
        task: The work item to place.
        project: Its new project, or None.
        parent: Its new parent feature, or None.
    """
    task.project = project
    task.parent = parent
    for descendant in _descendants(task):
        descendant.project = project

def _log_transition(session : Session, task : Task, action : str, previous : TaskState,
                    actor : str = events.ACTOR_WEB, **extra : object) -> None:
    """Log a task state change in the event log.

    Args:
        session: Database session to use.
        task: The task, already moved to its new state.
        action: Event action (e.g. "started").
        previous: The state the task was in before the change.
        actor: Who made the change, recorded in the event log.
        **extra: Additional payload entries (e.g. reason).
    """
    payload = {"from": previous.name, "to": task.state.name, **extra}
    events.log(session, actor, "task", task.id, action, payload)

# -----------------------------------------------------------------------------
# Reading
# -----------------------------------------------------------------------------

def get(session : Session, task_id : int) -> Task:
    """Look up a task by its id.

    Args:
        session: Database session to use.
        task_id: Id of the task.

    Returns:
        The matching Task.

    Raises:
        NotFoundError: If no task has this id.
    """
    task = session.query(Task).filter_by(id=task_id).first()
    if task is None:
        raise NotFoundError(f"Task '{task_id}' doesn't exist.")
    else:
        return task

def get_by_ref(session : Session, ref : str) -> Task:
    """Look up a task by its short ref.

    Args:
        session: Database session to use.
        ref: Ref of the feature or task (e.g. "t-4k2"), case-insensitive.
            Either prefix finds the item, so a ref written before a task
            became a feature still works.

    Returns:
        The matching Task.

    Raises:
        NotFoundError: If no feature or task has this ref.
    """
    task = None
    if refs.is_ref(ref) and refs.prefix_of(ref) != refs.SUBPROJECT:
        task = session.query(Task).filter(Task.ref.in_(refs.item_spellings(ref))).first()
    if task is None:
        raise NotFoundError(f"Task '{ref}' doesn't exist.")
    else:
        return task

def list(session : Session, limit : int | None = None) -> list:
    """List work items (features and tasks).

    Args:
        session: Database session to use.
        limit: Optional maximum number of tasks to return.

    Returns:
        All tasks, ordered by creation, oldest first. With a limit, only
        the `limit` most recently created ones (still oldest first).
    """
    if limit is None:
        return session.query(Task).order_by(Task.created_at, Task.id).all()


    recent = session.query(Task).order_by(Task.created_at.desc(), Task.id.desc()).limit(limit).all()
    return recent[::-1]

# -----------------------------------------------------------------------------
# Creation
# -----------------------------------------------------------------------------

def capture(session : Session, title : str, actor : str = events.ACTOR_WEB) -> Task:
    """Quickly capture a task title, with no other detail yet.

    Args:
        session: Database session to use.
        title: Short title for the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The newly created Task, in the inbox state.
    """
    task = Task(ref=refs.generate(session, refs.KIND_PREFIXES[TaskKind.TASK]), title=title, state=TaskState.INBOX)
    session.add(task)
    session.flush()
    events.log(session, actor, "task", task.id, "created", {"title": title})
    session.commit()
    return task

def create(session : Session,
           title : str,
           project_key : str | None = None,
           body : str | None = None,
           context : str | None = None,
           size : str | None = None,
           parent_ref : str | None = None,
           kind : TaskKind = TaskKind.TASK,
           actor : str = events.ACTOR_WEB) -> Task:
    """Create a feature or task with its detail already known.

    Args:
        session: Database session to use.
        title: Short title.
        project_key: Optional key of the project or subproject it goes in.
        body: Optional free-text detail.
        context: Optional context tag (e.g. "@ordi").
        size: Optional effort size ("XS", "S", "M", "L").
        parent_ref: Optional ref of the feature it goes under; its project is
            used when project_key is None.
        kind: TaskKind.TASK (default) or TaskKind.FEATURE.
        actor: Who made the change, recorded in the event log.

    Returns:
        The newly created item, in the inbox state, last among its siblings.

    Raises:
        NotFoundError: If the project or the parent doesn't exist.
        ValidationError: If the title is empty, or the parent can't hold it
            (see _resolve_placement).
    """
    _require_valid_title(title)
    project, parent = _resolve_placement(session, None, project_key, parent_ref)

    task = Task(ref=refs.generate(session, refs.KIND_PREFIXES[kind]),
                kind=kind,
                title=title,
                project=project,
                parent=parent,
                position=_next_position(session, project, parent),
                body=body,
                context=context,
                size=size,
                state=TaskState.INBOX)
    session.add(task)
    session.flush()
    events.log(session, actor, "task", task.id, "created",
               {"title": title, "kind": kind.name, **_where(task)})
    session.commit()
    return task

# -----------------------------------------------------------------------------
# Editing
# -----------------------------------------------------------------------------

def update(session : Session, task_id : int, actor : str = events.ACTOR_WEB, **fields : str | None) -> Task:
    """Update a task's descriptive fields.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        **fields: Values for any of "title", "body", "context", "size".
        actor: Who made the change, recorded in the event log.

    Returns:
        The updated Task.

    Raises:
        NotFoundError: If no task has this id.
        ValidationError: If a field name isn't updatable this way.
    """
    task = get(session, task_id)

    for name in fields:
        if name not in _UPDATABLE_FIELDS:
            raise ValidationError(f"field '{name}' cannot be updated this way.")

    changes = {}
    for name, value in fields.items():
        old_value = getattr(task, name)
        if old_value != value:
            changes[name] = {"from": old_value, "to": value}
        setattr(task, name, value)

    if changes:
        events.log(session, actor, "task", task.id, "updated", changes)

    session.commit()
    return task

def clarify(session : Session,
            task_id : int,
            title : str,
            body : str | None,
            project_key : str | None,
            context : str | None,
            size : str | None,
            parent_ref : str | None = None,
            kind : TaskKind | None = None,
            actor : str = events.ACTOR_WEB) -> Task:
    """Clarify a captured item into a refined one, ready to be started.

    Also reactivates a task deferred to someday, back into refined.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        title: Short title for the task.
        body: Optional free-text detail.
        project_key: Optional key of the owning project.
        context: Optional context tag (e.g. "@ordi").
        size: Optional effort size ("XS", "S", "M", "L").
        parent_ref: Optional ref of the feature it goes under.
        kind: New kind, e.g. TaskKind.FEATURE to turn a captured task into a
            feature; None keeps the current kind.
        actor: Who made the change, recorded in the event log.

    Returns:
        The clarified Task, in the refined state.

    Raises:
        NotFoundError: If no task has this id, or the project or the parent
            doesn't exist.
        InvalidTransitionError: If the task isn't inbox or someday.
        ValidationError: If the parent can't hold it, or a feature with
            children would become a task.
    """
    task = get(session, task_id)

    if task.state not in (TaskState.INBOX, TaskState.SOMEDAY):
        raise InvalidTransitionError(f"task '{task_id}' isn't inbox or someday.")

    project, parent = _resolve_placement(session, task, project_key, parent_ref)
    if kind is not None and kind is not task.kind:
        _change_kind(session, task, kind, actor)

    previous = task.state
    if (project, parent) != (task.project, task.parent):
        _set_place(task, project, parent)
        task.position = _next_position(session, project, parent)
    task.title = title
    task.body = body
    task.context = context
    task.size = size
    task.state = TaskState.REFINED

    _log_transition(session, task, "clarified", previous, actor=actor, **_where(task))
    session.commit()
    return task

# -----------------------------------------------------------------------------
# Lifecycle transitions
# -----------------------------------------------------------------------------

def start(session : Session, task_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Start a refined feature or task.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The started Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task isn't refined.
    """
    task = get(session, task_id)

    if task.state != TaskState.REFINED:
        raise InvalidTransitionError(f"task '{task_id}' isn't refined.")

    task.state = TaskState.DOING

    _log_transition(session, task, "started", TaskState.REFINED, actor=actor)
    session.commit()
    return task

def block(session : Session, task_id : int, reason : str, actor : str = events.ACTOR_WEB) -> Task:
    """Block a task that's being worked on.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        reason: Why the task is blocked.
        actor: Who made the change, recorded in the event log.

    Returns:
        The blocked Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task isn't doing.
        ValidationError: If reason is empty.
    """
    task = get(session, task_id)

    if task.state != TaskState.DOING:
        raise InvalidTransitionError(f"task '{task_id}' isn't doing.")

    if not reason:
        raise ValidationError("a blocked task requires a non-empty reason.")

    task.state = TaskState.WAITING
    task.blocked_reason = reason

    _log_transition(session, task, "blocked", TaskState.DOING, reason=reason, actor=actor)
    session.commit()
    return task

def unblock(session : Session, task_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Unblock a waiting task.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The unblocked Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task isn't waiting.
    """
    task = get(session, task_id)

    if task.state != TaskState.WAITING:
        raise InvalidTransitionError(f"task '{task_id}' isn't waiting.")

    task.state = TaskState.DOING
    task.blocked_reason = None

    _log_transition(session, task, "unblocked", TaskState.WAITING, actor=actor)
    session.commit()
    return task

def complete(session : Session, task_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Complete a feature or task that's being worked on.

    A feature completed for the first time raises MINOR on its nearest
    project and records the version it shipped in.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The completed Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task isn't doing.
        ConflictError: If it is a feature with a child neither done nor
            cancelled.
    """
    task = get(session, task_id)

    if task.state != TaskState.DOING:
        raise InvalidTransitionError(f"task '{task_id}' isn't doing.")
    _require_closed_children(task)

    task.state = TaskState.DONE
    task.closed_at = datetime.utcnow()

    _log_transition(session, task, "completed", TaskState.DOING, actor=actor)
    # A feature shipping raises MINOR on its nearest project, once.
    versioning.bump_minor(session, task, actor=actor)
    session.commit()
    return task

def reopen(session : Session, task_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Reopen a completed task.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The reopened Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task isn't done.
    """
    task = get(session, task_id)

    if task.state != TaskState.DONE:
        raise InvalidTransitionError(f"task '{task_id}' isn't done.")

    task.state = TaskState.DOING
    task.closed_at = None

    _log_transition(session, task, "reopened", TaskState.DONE, actor=actor)
    session.commit()
    return task

def defer(session : Session, task_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Defer a task to someday, with no fixed schedule.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The deferred Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task isn't inbox or refined.
    """
    task = get(session, task_id)

    if task.state not in (TaskState.INBOX, TaskState.REFINED):
        raise InvalidTransitionError(f"task '{task_id}' isn't inbox or refined.")

    previous = task.state
    task.state = TaskState.SOMEDAY

    _log_transition(session, task, "deferred", previous, actor=actor)
    session.commit()
    return task

def move(session : Session, task_id : int, project_key : str | None = None,
         parent_ref : str | None = None, actor : str = events.ACTOR_WEB) -> Task:
    """Move a feature or task elsewhere in the tree; a feature takes its
    whole subtree along.

    The item keeps its state. Given only a project, it goes to the top of
    that project; given a parent feature, under it.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        project_key: Key of the project or subproject to move it to.
        parent_ref: Ref of the feature to move it under.
        actor: Who made the change, recorded in the event log.

    Returns:
        The moved Task, last among its new siblings.

    Raises:
        NotFoundError: If no task has this id, or the project or the parent
            doesn't exist.
        ValidationError: If neither a project nor a parent is given, the
            item is already there, or the parent can't hold it (no cycle).
    """
    task = get(session, task_id)
    if project_key is None and parent_ref is None:
        raise ValidationError("give a project or a parent feature to move to.")

    project, parent = _resolve_placement(session, task, project_key, parent_ref)
    if (project, parent) == (task.project, task.parent):
        raise ValidationError(f"'{task.ref}' is already there.")

    previous = _where(task)
    _set_place(task, project, parent)
    task.position = _next_position(session, project, parent)

    events.log(session, actor, "task", task.id, "moved", {"from": previous, "to": _where(task)})
    session.commit()
    return task

# Directions reorder() accepts, mapped to the step taken among the siblings.
_REORDER_STEPS = {"up": -1, "down": 1}

def reorder(session : Session, task_id : int, direction : str, actor : str = events.ACTOR_WEB) -> Task:
    """Move a work item one place up or down among its siblings.

    An open item swaps with its nearest open sibling, so it never seems to
    stay still behind a done or cancelled one hidden from the tree; a closed
    item swaps with its nearest sibling. Sibling positions are renumbered
    0, 1, 2… in the new order.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        direction: "up" or "down".
        actor: Who made the change, recorded in the event log.

    Returns:
        The moved Task.

    Raises:
        NotFoundError: If no task has this id.
        ValidationError: If the direction is unknown, the item has no
            project (inbox order is capture order), or it is already first
            (up) or last (down).
    """
    if direction not in _REORDER_STEPS:
        raise ValidationError(f"unknown direction '{direction}': use up or down.")
    task = get(session, task_id)
    if task.project is None:
        raise ValidationError(f"'{task.ref}' has no project yet; only items in a tree can be reordered.")

    siblings = sorted(
        session.query(Task).filter_by(project_id=task.project_id, parent_id=task.parent_id),
        key=lambda sibling: (sibling.position, sibling.id))
    index = siblings.index(task)
    step = _REORDER_STEPS[direction]
    neighbour = index + step
    if task.state not in _CLOSED_STATES:
        while 0 <= neighbour < len(siblings) and siblings[neighbour].state in _CLOSED_STATES:
            neighbour += step
    if not 0 <= neighbour < len(siblings):
        raise ValidationError(f"'{task.ref}' is already {'first' if step < 0 else 'last'}.")

    previous = task.position
    siblings.insert(neighbour, siblings.pop(index))
    for position, sibling in enumerate(siblings):
        sibling.position = position

    events.log(session, actor, "task", task.id, "reordered",
               {"from": previous, "to": task.position, "direction": direction})
    session.commit()
    return task

def _change_kind(session : Session, task : Task, kind : TaskKind, actor : str) -> None:
    """Turn a task into a feature or back, respelling its ref; no commit.

    Args:
        session: Database session to use.
        task: The work item.
        kind: Its new kind, different from the current one.
        actor: Who made the change, recorded in the event log.

    Raises:
        ValidationError: If a feature with children would become a task.
    """
    if kind is TaskKind.TASK and task.children:
        raise ValidationError(f"feature '{task.ref}' has children; a task can't hold any.")

    previous_kind, previous_ref = task.kind, task.ref
    task.kind = kind
    task.ref = refs.with_kind(task.ref, kind)
    events.log(session, actor, "task", task.id, "kind_changed",
               {"from": previous_kind.name, "to": kind.name,
                "ref": {"from": previous_ref, "to": task.ref}})

def change_kind(session : Session, task_id : int, kind : TaskKind, actor : str = events.ACTOR_WEB) -> Task:
    """Turn a task into a feature, or an empty feature into a task.

    The ref keeps its code and takes the new kind's prefix ("t-4k2" becomes
    "f-4k2"); either spelling still finds the item.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        kind: The new kind.
        actor: Who made the change, recorded in the event log.

    Returns:
        The changed Task.

    Raises:
        NotFoundError: If no task has this id.
        ValidationError: If the item already has this kind, or a feature with
            children would become a task.
    """
    task = get(session, task_id)
    if task.kind is kind:
        raise ValidationError(f"'{task.ref}' is already a {kind.name.lower()}.")

    _change_kind(session, task, kind, actor)
    session.commit()
    return task

def cancel(session : Session, task_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Cancel a feature or task that won't be done.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The cancelled Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task is already done or cancelled.
        ConflictError: If it is a feature with a child neither done nor
            cancelled.
    """
    task = get(session, task_id)

    if task.state in _CLOSED_STATES:
        raise InvalidTransitionError(f"task '{task_id}' is already done or cancelled.")
    _require_closed_children(task)

    previous = task.state
    task.state = TaskState.CANCELLED
    task.blocked_reason = None
    task.closed_at = datetime.utcnow()

    _log_transition(session, task, "cancelled", previous, actor=actor)
    session.commit()
    return task

def restore(session : Session, task_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Bring a cancelled feature or task back to refined.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The restored Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task isn't cancelled.
    """
    task = get(session, task_id)

    if task.state != TaskState.CANCELLED:
        raise InvalidTransitionError(f"task '{task_id}' isn't cancelled.")

    task.state = TaskState.REFINED
    task.closed_at = None

    _log_transition(session, task, "restored", TaskState.CANCELLED, actor=actor)
    session.commit()
    return task

def change_state(session : Session, task_id : int, target : TaskState, reason : str = "", actor : str = events.ACTOR_WEB) -> Task:
    """Move a task to a target state through the matching lifecycle transition.

    Covers the working states and cancelling: refined to doing, doing to
    waiting or done, waiting or done back to doing, any open task to cancelled.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        target: State to move the task to.
        reason: Why the task is blocked; only used when the target is waiting.
        actor: Who made the change, recorded in the event log.

    Returns:
        The updated Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task can't go from its state to the target.
        ValidationError: If the target is waiting and the reason is empty.
        ConflictError: If a feature with open children would be closed.
    """
    task = get(session, task_id)

    if target == TaskState.CANCELLED:
        return cancel(session, task_id, actor=actor)
    if target == TaskState.WAITING:
        return block(session, task_id, reason, actor=actor)
    if target == TaskState.DONE:
        return complete(session, task_id, actor=actor)
    if target == TaskState.DOING:
        if task.state == TaskState.REFINED:
            return start(session, task_id, actor=actor)
        if task.state == TaskState.WAITING:
            return unblock(session, task_id, actor=actor)
        if task.state == TaskState.DONE:
            return reopen(session, task_id, actor=actor)
    raise InvalidTransitionError(
        f"task '{task_id}' can't go from {task.state.name} to {target.name}.")

# -----------------------------------------------------------------------------
# Deletion
# -----------------------------------------------------------------------------

def delete(session : Session, task_id : int, actor : str = events.ACTOR_WEB) -> None:
    """Delete a task, or a feature with no children.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Raises:
        NotFoundError: If no task has this id.
        ConflictError: If it is a feature that still has children.
    """
    task = get(session, task_id)
    if task.children:
        raise ConflictError(
            f"feature '{task.ref}' isn't empty: delete or move its children first.")
    events.log(session, actor, "task", task.id, "deleted",
               {"title": task.title, "kind": task.kind.name, "ref": task.ref})
    session.delete(task)
    session.commit()
