from datetime import date, datetime

from sqlalchemy.orm import Session

from src.models.definition_of_done import DefinitionOfDoneCriterion
from src.models.version import Version, VersionStatus
from src.models.task import Task,TaskState
from src.services import projects
from src.services.errors import ConflictError, NotFoundError, ValidationError

def create(session : Session,
           project_key : str,
           number : str,
           title : str,
           dod : list,
           goal : str | None = None,
           target_date : date | None = None) -> Version:
    """Create a version under a project.

    Args:
        session: Database session to use.
        project_key: Key of the owning project.
        number: Version number (e.g. "0.2.0"), unique within the project.
        title: Short human-readable name for the version.
        dod: Definition-of-done criteria (one or more description strings).
        goal: Optional free-text goal for the version.
        target_date: Optional planning date.

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

    version = Version(project_id=project.id,
                      number=number,
                      title=title,
                      goal=goal,
                      target_date=target_date)
    version.definition_of_done = [
        DefinitionOfDoneCriterion(description=text, position=i)
        for i, text in enumerate(dod)
    ]

    session.add(version)
    session.commit()
    return version

def reorder(session : Session, project_key : str, ordered_ids : list) -> None:
    """Reorder a project's versions.

    Args:
        session: Database session to use.
        project_key: Key of the owning project.
        ordered_ids: Version ids in the desired order; must match exactly
            the set of the project's version ids.

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

    session.commit()

def list(session : Session, project_key : str) -> list:
    """List a project's versions.

    Args:
        session: Database session to use.
        project_key: Key of the owning project.

    Returns:
        All matching versions.

    Raises:
        NotFoundError: If no project has this key.
    """
    project = projects.get(session, project_key)

    return session.query(Version).filter(Version.project_id == project.id).all()


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


def start(session : Session, version_id : int) -> Version:
    """Start a version.

    Args:
        session: Database session to use.
        version_id: Id of the version.

    Returns:
        The started Version.

    Raises:
        NotFoundError: If no version has this id.
        ValidationError: If the version is not currently planned.
    """
    version = _get_by_id(session, version_id)

    if version.status == VersionStatus.PLANNED:
        version.status = VersionStatus.IN_PROGRESS
        session.commit()
        return version
    else:
        raise ValidationError("The version is already started")


def release(session : Session, version_id : int) -> Version:
    """Release a version.

    Args:
        session: Database session to use.
        version_id: Id of the version.

    Returns:
        The released Version.

    Raises:
        NotFoundError: If no version has this id.
        ValidationError: If the version has unfinished tasks, or is not
            currently in progress.
    """
    version = _get_by_id(session, version_id)

    unfinished_tasks = session.query(Task).filter(Task.version_id == version_id,
                                                  Task.state != TaskState.DONE).first()

    if unfinished_tasks:
        raise ValidationError(f"Version '{version.number}' has unfinished tasks")

    if version.status == VersionStatus.IN_PROGRESS:
        version.status = VersionStatus.RELEASED
        version.released_at = datetime.utcnow()
        session.commit()
        return version
    else:
        raise ValidationError("Cannot release this version.")