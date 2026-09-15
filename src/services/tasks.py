from datetime import datetime

from sqlalchemy.orm import Session

from src.models.task import Task, TaskState
from src.models.version import Version, VersionStatus
from src.services import projects
from src.services.errors import InvalidTransitionError, NotFoundError, ValidationError

# Fields update() is allowed to touch; state, project/version linkage and
# timestamps only ever change through the dedicated transition functions.
_UPDATABLE_FIELDS = {"title", "body", "context", "size"}

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

def list(session : Session) -> list:
    """List all tasks.

    Args:
        session: Database session to use.

    Returns:
        All tasks, ordered by creation.
    """
    return session.query(Task).order_by(Task.created_at).all()

def capture(session : Session, title : str) -> Task:
    """Quickly capture a task title, with no other detail yet.

    Args:
        session: Database session to use.
        title: Short title for the task.

    Returns:
        The newly created Task, in the inbox state.
    """
    task = Task(title=title, state=TaskState.INBOX)
    session.add(task)
    session.commit()
    return task

def create(session : Session,
           title : str,
           project_key : str | None = None,
           body : str | None = None,
           context : str | None = None,
           size : str | None = None) -> Task:
    """Create a task with its detail already known.

    Args:
        session: Database session to use.
        title: Short title for the task.
        project_key: Optional key of the owning project.
        body: Optional free-text detail.
        context: Optional context tag (e.g. "@ordi").
        size: Optional effort size ("XS", "S", "M", "L").

    Returns:
        The newly created Task, in the inbox state.

    Raises:
        NotFoundError: If project_key is given but no project has this key.
    """
    project = projects.get(session, project_key) if project_key else None

    task = Task(title=title,
                project_id=project.id if project else None,
                body=body,
                context=context,
                size=size,
                state=TaskState.INBOX)
    session.add(task)
    session.commit()
    return task

def update(session : Session, task_id : int, **fields : str | None) -> Task:
    """Update a task's descriptive fields.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        **fields: Values for any of "title", "body", "context", "size".

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

    for name, value in fields.items():
        setattr(task, name, value)

    session.commit()
    return task

def clarify(session : Session,
            task_id : int,
            title : str,
            body : str | None,
            project_key : str | None,
            context : str | None,
            size : str | None) -> Task:
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

    task.title = title
    task.body = body
    task.project_id = project.id if project else None
    task.context = context
    task.size = size
    task.state = TaskState.REFINED

    session.commit()
    return task

def plan(session : Session, task_id : int, version_id : int) -> Task:
    """Plan a refined task into a version.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        version_id: Id of the version to plan the task into.

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
    if version is None:
        raise NotFoundError(f"Version '{version_id}' doesn't exist.")

    if version.status == VersionStatus.RELEASED:
        raise ValidationError(f"version '{version_id}' is already released.")

    if task.project_id is not None and task.project_id != version.project_id:
        raise ValidationError(f"task '{task_id}' belongs to a different project than the version.")

    task.project_id = version.project_id
    task.version_id = version.id
    task.state = TaskState.PLANNED

    session.commit()
    return task

def unplan(session : Session, task_id : int) -> Task:
    """Unplan a planned task back to refined.

    Args:
        session: Database session to use.
        task_id: Id of the task.

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

    session.commit()
    return task

def start(session : Session, task_id : int) -> Task:
    """Start a planned task.

    Args:
        session: Database session to use.
        task_id: Id of the task.

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

    session.commit()
    return task

def block(session : Session, task_id : int, reason : str) -> Task:
    """Block a task that's being worked on.

    Args:
        session: Database session to use.
        task_id: Id of the task.
        reason: Why the task is blocked.

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

    session.commit()
    return task

def unblock(session : Session, task_id : int) -> Task:
    """Unblock a waiting task.

    Args:
        session: Database session to use.
        task_id: Id of the task.

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

    session.commit()
    return task

def complete(session : Session, task_id : int) -> Task:
    """Complete a task that's being worked on.

    Args:
        session: Database session to use.
        task_id: Id of the task.

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

    session.commit()
    return task

def reopen(session : Session, task_id : int) -> Task:
    """Reopen a completed task.

    Args:
        session: Database session to use.
        task_id: Id of the task.

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

    session.commit()
    return task

def defer(session : Session, task_id : int) -> Task:
    """Defer a task to someday, with no fixed schedule.

    Args:
        session: Database session to use.
        task_id: Id of the task.

    Returns:
        The deferred Task.

    Raises:
        NotFoundError: If no task has this id.
        InvalidTransitionError: If the task isn't inbox or refined.
    """
    task = get(session, task_id)

    if task.state not in (TaskState.INBOX, TaskState.REFINED):
        raise InvalidTransitionError(f"task '{task_id}' isn't inbox or refined.")

    task.state = TaskState.SOMEDAY

    session.commit()
    return task

def delete(session : Session, task_id : int) -> None:
    """Delete a task.

    Args:
        session: Database session to use.
        task_id: Id of the task.

    Raises:
        NotFoundError: If no task has this id.
    """
    task = get(session, task_id)
    session.delete(task)
    session.commit()
