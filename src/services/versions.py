from datetime import date, datetime

from sqlalchemy.orm import Session

from src.models.definition_of_done import DefinitionOfDoneCriterion
from src.models.version import Version, VersionStatus
from src.models.task import Task,TaskState
from src.services import events, projects, refs
from src.services.errors import ConflictError, NotFoundError, ValidationError

def create(session : Session,
           project_key : str,
           number : str,
           title : str,
           dod : list,
           goal : str | None = None,
           target_date : date | None = None,
           actor : str = events.ACTOR_WEB) -> Version:
    """Create a version under a project.

    Args:
        session: Database session to use.
        project_key: Key of the owning project.
        number: Version number (e.g. "0.2.0"), unique within the project.
        title: Short human-readable name for the version.
        dod: Definition-of-done criteria (one or more description strings).
        goal: Optional free-text goal for the version.
        target_date: Optional planning date.
        actor: Who made the change, recorded in the event log.

    Returns:
        The newly created Version.

    Raises:
        NotFoundError: If no project has this key.
        ValidationError: If dod is empty.
        ConflictError: If this project already has a version with this number.
    """
    project = projects.get(session, project_key)

    if not dod:
        raise ValidationError("Definition of done for the version must contain at least one entry.")

    if session.query(Version).filter_by(project_id=project.id, number=number).first() is not None:
        raise ConflictError(f"project '{project_key}' already has a version '{number}'")

    version = Version(ref=refs.generate(session, Version),
                      project_id=project.id,
                      number=number,
                      title=title,
                      goal=goal,
                      target_date=target_date)
    version.definition_of_done = [
        DefinitionOfDoneCriterion(description=text, position=i)
        for i, text in enumerate(dod)
    ]

    session.add(version)
    session.flush()
    events.log(session, actor, "version", version.id, "created",
               {"number": number, "title": title})
    session.commit()
    return version

def reorder(session : Session, project_key : str, ordered_ids : list, actor : str = events.ACTOR_WEB) -> None:
    """Reorder a project's versions.

    Args:
        session: Database session to use.
        project_key: Key of the owning project.
        ordered_ids: Version ids in the desired order; must match exactly
            the set of the project's version ids.
        actor: Who made the change, recorded in the event log.

    Raises:
        NotFoundError: If no project has this key.
        ValidationError: If ordered_ids does not match exactly the
            project's version ids.
    """
    project = projects.get(session, project_key)

    versions = session.query(Version).filter_by(project_id=project.id).all()
    if {v.id for v in versions} != set(ordered_ids):
        raise ValidationError("ordered_ids must match exactly the project's version ids.")

    versions_by_id = {v.id: v for v in versions}
    for position, version_id in enumerate(ordered_ids):
        versions_by_id[version_id].position = position

    events.log(session, actor, "project", project.id, "versions_reordered",
               {"ordered_ids": ordered_ids})
    session.commit()

def list(session : Session, project_key : str) -> list:
    """List a project's versions.

    Args:
        session: Database session to use.
        project_key: Key of the owning project.

    Returns:
        All matching versions, in the project's own order.

    Raises:
        NotFoundError: If no project has this key.
    """
    project = projects.get(session, project_key)

    return (session.query(Version).filter(Version.project_id == project.id)
            .order_by(Version.position, Version.id).all())


def list_all(session : Session) -> list:
    """List the versions of every project.

    Args:
        session: Database session to use.

    Returns:
        All versions, grouped by project (oldest project first) and in each
        project's own order.
    """
    return session.query(Version).order_by(Version.project_id, Version.position, Version.id).all()


def get(session : Session, project_key : str, number : str) -> Version:
    """Look up a version by its number within a project.

    Args:
        session: Database session to use.
        project_key: Key of the owning project.
        number: Version number (e.g. "0.2.0").

    Returns:
        The matching Version.

    Raises:
        NotFoundError: If no project has this key, or no version has this
            number within it.
    """
    project = projects.get(session, project_key)

    version = session.query(Version).filter_by(project_id=project.id, number=number).first()
    if not version:
        raise NotFoundError(f"Version number '{number}' doesn't exist.")
    else:
        return version


def get_by_ref(session : Session, ref : str) -> Version:
    """Look up a version by its short ref.

    Args:
        session: Database session to use.
        ref: Ref of the version (e.g. "v-9xa"), case-insensitive.

    Returns:
        The matching Version.

    Raises:
        NotFoundError: If no version has this ref.
    """
    version = session.query(Version).filter_by(ref=ref.strip().lower()).first()
    if not version:
        raise NotFoundError(f"Version '{ref}' doesn't exist.")
    else:
        return version

def _get_by_id(session : Session, version_id : int) -> Version:
    """Look up a version by its id.

    Args:
        session: Database session to use.
        version_id: Id of the version.

    Returns:
        The matching Version.

    Raises:
        NotFoundError: If no version has this id.
    """
    version = session.query(Version).filter_by(id=version_id).first()
    if not version:
        raise NotFoundError(f"Version '{version_id}' doesn't exist.")
    else:
        return version


def start(session : Session, version_id : int, actor : str = events.ACTOR_WEB) -> Version:
    """Start a version.

    Args:
        session: Database session to use.
        version_id: Id of the version.
        actor: Who made the change, recorded in the event log.

    Returns:
        The started Version.

    Raises:
        NotFoundError: If no version has this id.
        ValidationError: If the version is not currently planned.
    """
    version = _get_by_id(session, version_id)

    if version.status == VersionStatus.PLANNED:
        version.status = VersionStatus.IN_PROGRESS
        events.log(session, actor, "version", version.id, "started",
                   {"from": VersionStatus.PLANNED.name, "to": VersionStatus.IN_PROGRESS.name})
        session.commit()
        return version
    else:
        raise ValidationError("The version is already started")


def release(session : Session, version_id : int, actor : str = events.ACTOR_WEB) -> Version:
    """Release a version.

    Args:
        session: Database session to use.
        version_id: Id of the version.
        actor: Who made the change, recorded in the event log.

    Returns:
        The released Version.

    Raises:
        NotFoundError: If no version has this id.
        ValidationError: If the version has unfinished tasks (cancelled ones don't count), has unchecked
            definition of done criteria, or is not currently in progress.
    """
    version = _get_by_id(session, version_id)

    unfinished_tasks = session.query(Task).filter(Task.version_id == version_id,
                                                  Task.state.notin_([TaskState.DONE, TaskState.CANCELLED])).first()

    if unfinished_tasks:
        raise ValidationError(f"Version '{version.number}' has unfinished tasks")

    if any(not criterion.done for criterion in version.definition_of_done):
        raise ValidationError(f"Version '{version.number}' has unchecked definition of done criteria")

    if version.status == VersionStatus.IN_PROGRESS:
        version.status = VersionStatus.RELEASED
        version.released_at = datetime.utcnow()
        events.log(session, actor, "version", version.id, "released",
                   {"from": VersionStatus.IN_PROGRESS.name, "to": VersionStatus.RELEASED.name})
        session.commit()
        return version
    else:
        raise ValidationError("Cannot release this version.")

# Task states that still count as work to do; deleting their version sends them back to refined.
_UNFINISHED_STATES = (TaskState.PLANNED, TaskState.DOING, TaskState.WAITING)


def delete(session : Session, version_id : int, actor : str = events.ACTOR_WEB) -> None:
    """Delete a version and its definition of done.

    Its unfinished tasks (planned, doing or waiting) go back to refined,
    without a version, so they can be planned again. Its other tasks (done,
    cancelled, someday) are kept but no longer belong to a version.

    Args:
        session: Database session to use.
        version_id: Id of the version.
        actor: Who made the change, recorded in the event log.

    Raises:
        NotFoundError: If no version has this id.
    """
    version = _get_by_id(session, version_id)

    for task in version.tasks[:]:
        if task.state in _UNFINISHED_STATES:
            previous = task.state
            task.state = TaskState.REFINED
            task.blocked_reason = None
            events.log(session, actor, "task", task.id, "unplanned",
                       {"from": previous.name, "to": TaskState.REFINED.name, "version": version.ref})
        task.version_id = None
        version.tasks.remove(task)

    events.log(session, actor, "version", version.id, "deleted",
               {"project": version.project.key, "number": version.number, "title": version.title})
    session.delete(version)
    session.commit()


def _get_editable_criterion(session : Session, criterion_id : int) -> DefinitionOfDoneCriterion:
    """Look up a criterion whose version still accepts changes.

    Args:
        session: Database session to use.
        criterion_id: Id of the criterion.

    Returns:
        The matching DefinitionOfDoneCriterion.

    Raises:
        NotFoundError: If no criterion has this id.
        ConflictError: If the criterion's version is released.
    """
    criterion = session.query(DefinitionOfDoneCriterion).filter_by(id=criterion_id).first()
    if not criterion:
        raise NotFoundError(f"Criterion '{criterion_id}' doesn't exist.")
    if criterion.version.status == VersionStatus.RELEASED:
        raise ConflictError("The definition of done of a released version cannot change.")
    return criterion


def add_criterion(session : Session, version_id : int, description : str, actor : str = events.ACTOR_WEB) -> DefinitionOfDoneCriterion:
    """Append a criterion to a version's definition of done.

    Args:
        session: Database session to use.
        version_id: Id of the version.
        description: Text of the new criterion.
        actor: Who made the change, recorded in the event log.

    Returns:
        The newly created DefinitionOfDoneCriterion, unchecked, in last position.

    Raises:
        NotFoundError: If no version has this id.
        ValidationError: If the description is empty.
        ConflictError: If the version is released.
    """
    version = _get_by_id(session, version_id)

    if version.status == VersionStatus.RELEASED:
        raise ConflictError("The definition of done of a released version cannot change.")

    description = description.strip()
    if not description:
        raise ValidationError("A criterion description cannot be empty.")

    position = max((c.position for c in version.definition_of_done), default=-1) + 1
    criterion = DefinitionOfDoneCriterion(description=description, position=position)
    version.definition_of_done.append(criterion)
    session.flush()
    events.log(session, actor, "version", version.id, "dod_added",
               {"criterion_id": criterion.id, "description": description})
    session.commit()
    return criterion


def update_criterion(session : Session, criterion_id : int, description : str, actor : str = events.ACTOR_WEB) -> DefinitionOfDoneCriterion:
    """Change the description of a criterion.

    Args:
        session: Database session to use.
        criterion_id: Id of the criterion.
        description: New text of the criterion.
        actor: Who made the change, recorded in the event log.

    Returns:
        The updated DefinitionOfDoneCriterion.

    Raises:
        NotFoundError: If no criterion has this id.
        ValidationError: If the description is empty.
        ConflictError: If the criterion's version is released.
    """
    criterion = _get_editable_criterion(session, criterion_id)

    description = description.strip()
    if not description:
        raise ValidationError("A criterion description cannot be empty.")

    previous = criterion.description
    criterion.description = description
    events.log(session, actor, "version", criterion.version_id, "dod_updated",
               {"criterion_id": criterion.id, "from": previous, "to": description})
    session.commit()
    return criterion


def delete_criterion(session : Session, criterion_id : int, actor : str = events.ACTOR_WEB) -> None:
    """Delete a criterion from a version's definition of done.

    Args:
        session: Database session to use.
        criterion_id: Id of the criterion.
        actor: Who made the change, recorded in the event log.

    Raises:
        NotFoundError: If no criterion has this id.
        ValidationError: If it is the last criterion of its version.
        ConflictError: If the criterion's version is released.
    """
    criterion = _get_editable_criterion(session, criterion_id)
    version = criterion.version

    if len(version.definition_of_done) <= 1:
        raise ValidationError("Definition of done for the version must contain at least one entry.")

    version.definition_of_done.remove(criterion)
    events.log(session, actor, "version", version.id, "dod_deleted",
               {"criterion_id": criterion_id, "description": criterion.description})
    session.commit()


def set_criterion_done(session : Session, criterion_id : int, done : bool, actor : str = events.ACTOR_WEB) -> DefinitionOfDoneCriterion:
    """Check or uncheck a criterion.

    Args:
        session: Database session to use.
        criterion_id: Id of the criterion.
        done: True to check the criterion, False to uncheck it.
        actor: Who made the change, recorded in the event log.

    Returns:
        The updated DefinitionOfDoneCriterion.

    Raises:
        NotFoundError: If no criterion has this id.
        ConflictError: If the criterion's version is released.
    """
    criterion = _get_editable_criterion(session, criterion_id)

    if criterion.done != done:
        criterion.done = done
        events.log(session, actor, "version", criterion.version_id,
                   "dod_checked" if done else "dod_unchecked",
                   {"criterion_id": criterion.id, "description": criterion.description})
    session.commit()
    return criterion


def list_tasks(session : Session, version_id : int) -> list:
    """List the tasks planned in a version.

    Args:
        session: Database session to use.
        version_id: Id of the version.

    Returns:
        The version's tasks, ordered by position.

    Raises:
        NotFoundError: If no version has this id.
    """
    _get_by_id(session, version_id)
    return session.query(Task).filter(Task.version_id == version_id).order_by(Task.position).all()
