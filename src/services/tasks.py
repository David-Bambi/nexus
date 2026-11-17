from datetime import datetime

from sqlalchemy.orm import Session

from src.models.task import Task, TaskState
from src.models.version import Version, VersionStatus
from src.services import events, projects, refs
from src.services.errors import InvalidTransitionError, NotFoundError, ValidationError

# Fields update() is allowed to touch; state, project/version linkage and
# timestamps only ever change through the dedicated transition functions.
_UPDATABLE_FIELDS = {"title", "body", "context", "size"}


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------

def _require_unreleased(version : Version) -> None:
    """Refuse changes to a released version.

    Args:
        version: The version to check.

    Raises:
        ValidationError: If the version is already released.
    """
    if version.status == VersionStatus.RELEASED:
        raise ValidationError(f"version '{version.id}' is already released.")

def _require_existing_version(version : Version, version_id : int) -> None:
    """Refuse a version lookup that found nothing.

    Args:
        version: The version returned by the lookup, or None.
        version_id: Id that was looked up, used in the error message.

    Raises:
        NotFoundError: If version is None.
    """
    if version is None:
        raise NotFoundError(f"Version '{version_id}' doesn't exist.")

def _require_valid_title(title : str) -> None:
    """Refuse an empty task title.

    Args:
        title: The title to check.

    Raises:
        ValidationError: If the title is empty.
    """
    if not title.strip() :
        raise ValidationError("The title must be specified.")


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
        ref: Ref of the task (e.g. "t-4k2"), case-insensitive.

    Returns:
        The matching Task.

    Raises:
        NotFoundError: If no task has this ref.
    """
    task = session.query(Task).filter_by(ref=ref.strip().lower()).first()
    if task is None:
        raise NotFoundError(f"Task '{ref}' doesn't exist.")
    else:
        return task

def list(session : Session, limit : int | None = None) -> list:
    """List tasks.

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
    task = Task(ref=refs.generate(session, Task), title=title, state=TaskState.INBOX)
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
           actor : str = events.ACTOR_WEB) -> Task:
    """Create a task with its detail already known.

    Args:
        session: Database session to use.
        title: Short title for the task.
        project_key: Optional key of the owning project.
        body: Optional free-text detail.
        context: Optional context tag (e.g. "@ordi").
        size: Optional effort size ("XS", "S", "M", "L").
        actor: Who made the change, recorded in the event log.

    Returns:
        The newly created Task, in the inbox state.

    Raises:
        NotFoundError: If project_key is given but no project has this key.
    """
    project = projects.get(session, project_key) if project_key else None

    task = Task(ref=refs.generate(session, Task),
                title=title,
                project_id=project.id if project else None,
                body=body,
                context=context,
                size=size,
                state=TaskState.INBOX)
    session.add(task)
    session.flush()
    events.log(session, actor, "task", task.id, "created", {"title": title})
    session.commit()
    return task

def create_in_version(session : Session,
                      version_id : int,
                      title : str,
                      context : str | None = None,
                      size : str | None = None,
                      body : str | None = None,
                      actor : str = events.ACTOR_WEB) -> Task:
    """Create a task directly in a version, already planned.

    Skips the inbox and refine steps: the task belongs to the version and to
    the version's project from the start.

    Args:
        session: Database session to use.
        version_id: Id of the version to create the task in.
        title: Short title for the task.
        context: Optional context tag (e.g. "@ordi").
        size: Optional effort size ("XS", "S", "M", "L").
        body: Optional free-text detail.
        actor: Who made the change, recorded in the event log.

    Returns:
        The newly created Task, in the planned state.

    Raises:
        NotFoundError: If no version has this id.
        ValidationError: If the version is already released, or the title is empty.
    """
    version = session.query(Version).filter_by(id=version_id).first()
    _require_existing_version(version, version_id)
    _require_unreleased(version)
    _require_valid_title(title)


    task = Task(ref=refs.generate(session, Task),
                project_id=version.project_id,
                version_id=version_id,
                title=title,
                state=TaskState.PLANNED,
                context=context,
                size=size,
                body=body)
    
    session.add(task)
    session.flush()
    events.log(session, 
               actor,
               "task",
                task.id, 
                "created",  
                {"title": title, "state": "PLANNED", "version_id": version.id})
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
            actor : str = events.ACTOR_WEB) -> Task:
    """Clarify a captured task into a refined one, ready to be planned.

    Also reactivates a task deferred to someday, back into refined.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        title: Short title for the task.
        body: Optional free-text detail.
        project_key: Optional key of the owning project.
        context: Optional context tag (e.g. "@ordi").
        size: Optional effort size ("XS", "S", "M", "L").
        actor: Who made the change, recorded in the event log.

    Returns:
        The clarified Task, in the refined state.

    Raises:
        NotFoundError: If no task has this id, or project_key is given but
            no project has this key.
        InvalidTransitionError: If the task isn't inbox or someday.
    """
    task = get(session, task_id)

    if task.state not in (TaskState.INBOX, TaskState.SOMEDAY):
        raise InvalidTransitionError(f"task '{task_id}' isn't inbox or someday.")

    project = projects.get(session, project_key) if project_key else None

    previous = task.state
    task.title = title
    task.body = body
    task.project_id = project.id if project else None
    task.context = context
    task.size = size
    task.state = TaskState.REFINED

    _log_transition(session, task, "clarified", previous, actor=actor)
    session.commit()
    return task

# -----------------------------------------------------------------------------
# Lifecycle transitions
# -----------------------------------------------------------------------------

def plan(session : Session, task_id : int, version_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Plan a refined task into a version.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        version_id: Id of the version to plan the task into.
        actor: Who made the change, recorded in the event log.

    Returns:
        The planned Task.

    Raises:
        NotFoundError: If no task or version has this id.
        InvalidTransitionError: If the task isn't refined.
        ValidationError: If the version is already released, or the task
            already belongs to a different project than the version.
    """
    task = get(session, task_id)

    if task.state != TaskState.REFINED:
        raise InvalidTransitionError(f"task '{task_id}' isn't refined.")

    version = session.query(Version).filter_by(id=version_id).first()
    
    _require_existing_version(version, version_id)
    _require_unreleased(version)

    if task.project_id is not None and task.project_id != version.project_id:
        raise ValidationError(f"task '{task_id}' belongs to a different project than the version.")

    task.project_id = version.project_id
    task.version_id = version.id
    task.state = TaskState.PLANNED

    _log_transition(session, task, "planned", TaskState.REFINED, version_id=version.id, actor=actor)
    session.commit()
    return task

def unplan(session : Session, task_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Unplan a planned task back to refined.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The unplanned Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task isn't planned.
    """
    task = get(session, task_id)

    if task.state != TaskState.PLANNED:
        raise InvalidTransitionError(f"task '{task_id}' isn't planned.")

    task.version_id = None
    task.state = TaskState.REFINED

    _log_transition(session, task, "unplanned", TaskState.PLANNED, actor=actor)
    session.commit()
    return task

def start(session : Session, task_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Start a planned task.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The started Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task isn't planned.
    """
    task = get(session, task_id)

    if task.state != TaskState.PLANNED:
        raise InvalidTransitionError(f"task '{task_id}' isn't planned.")

    task.state = TaskState.DOING

    _log_transition(session, task, "started", TaskState.PLANNED, actor=actor)
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
    """Complete a task that's being worked on.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The completed Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task isn't doing.
    """
    task = get(session, task_id)

    if task.state != TaskState.DOING:
        raise InvalidTransitionError(f"task '{task_id}' isn't doing.")

    task.state = TaskState.DONE
    task.closed_at = datetime.utcnow()

    _log_transition(session, task, "completed", TaskState.DOING, actor=actor)
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

def move_to_version(session : Session, task_id : int, version_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Move a planned, doing or waiting task to another version of its project.

    The task keeps its state; only its version changes.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        version_id: Id of the version to move the task to.
        actor: Who made the change, recorded in the event log.

    Returns:
        The moved Task.

    Raises:
        NotFoundError: If no task or version has this id.
        InvalidTransitionError: If the task isn't planned, doing or waiting.
        ValidationError: If the task's current version or the target version
            is already released, the target is the task's current version, or
            the target belongs to a different project than the task.
    """
    task = get(session, task_id)

    if task.state not in (TaskState.PLANNED, TaskState.DOING, TaskState.WAITING):
        raise InvalidTransitionError(f"task '{task_id}' isn't planned, doing or waiting.")

    version = session.query(Version).filter_by(id=version_id).first()

    _require_existing_version(version, version_id)
    if task.version is not None:
        _require_unreleased(task.version)
    _require_unreleased(version)

    if task.version_id == version.id:
        raise ValidationError(f"task '{task_id}' is already in version '{version.number}'.")
    if task.project_id != version.project_id:
        raise ValidationError(f"task '{task_id}' belongs to a different project than the version.")

    previous_version_id = task.version_id
    task.version = version

    _log_transition(session, task, "moved", task.state,
                    from_version_id=previous_version_id, version_id=version.id, actor=actor)
    session.commit()
    return task

def cancel(session : Session, task_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Cancel a task that won't be done.

    The task keeps its version, so the version's history still shows it.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The cancelled Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task is already done or cancelled.
        ValidationError: If the task's version is already released.
    """
    task = get(session, task_id)

    if task.state in (TaskState.DONE, TaskState.CANCELLED):
        raise InvalidTransitionError(f"task '{task_id}' is already done or cancelled.")
    if task.version is not None:
        _require_unreleased(task.version)

    previous = task.state
    task.state = TaskState.CANCELLED
    task.blocked_reason = None
    task.closed_at = datetime.utcnow()

    _log_transition(session, task, "cancelled", previous, actor=actor)
    session.commit()
    return task

def restore(session : Session, task_id : int, actor : str = events.ACTOR_WEB) -> Task:
    """Bring a cancelled task back to refined, out of any version.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Returns:
        The restored Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task isn't cancelled.
        ValidationError: If the task's version is already released.
    """
    task = get(session, task_id)

    if task.state != TaskState.CANCELLED:
        raise InvalidTransitionError(f"task '{task_id}' isn't cancelled.")
    if task.version is not None:
        _require_unreleased(task.version)

    task.state = TaskState.REFINED
    task.version_id = None
    task.closed_at = None

    _log_transition(session, task, "restored", TaskState.CANCELLED, actor=actor)
    session.commit()
    return task

def change_state(session : Session, task_id : int, target : TaskState, reason : str = "", actor : str = events.ACTOR_WEB) -> Task:
    """Move a task to a target state through the matching lifecycle transition.

    Covers the working states and cancelling: planned to doing, doing to
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
        ValidationError: If the task's version is already released, or the
            target is waiting and the reason is empty.
    """
    task = get(session, task_id)

    if task.version is not None:
        _require_unreleased(task.version)
    if target == TaskState.CANCELLED:
        return cancel(session, task_id, actor=actor)
    if target == TaskState.WAITING:
        return block(session, task_id, reason, actor=actor)
    if target == TaskState.DONE:
        return complete(session, task_id, actor=actor)
    if target == TaskState.DOING:
        if task.state == TaskState.PLANNED:
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
    """Delete a task.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        actor: Who made the change, recorded in the event log.

    Raises:
        NotFoundError: If no task has this id.
    """
    task = get(session, task_id)
    events.log(session, actor, "task", task.id, "deleted", {"title": task.title})
    session.delete(task)
    session.commit()
