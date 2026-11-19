from sqlalchemy.orm import Session

from src.models.criterion import MajorCriterion
from src.models.project import Project
from src.models.task import Task, TaskKind
from src.services import events, projects
from src.services.errors import ConflictError, NotFoundError, ValidationError


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------

def _require_valid_text(text : str) -> None:
    """Refuse an empty criterion text.

    Args:
        text: The text to check.

    Raises:
        ValidationError: If the text is empty.
    """
    if not text.strip():
        raise ValidationError("The criterion text must be specified.")


def _criterion_payload(criterion : MajorCriterion, **extra) -> dict:
    """Build the event payload of a criterion change.

    Args:
        criterion: The criterion changed.
        **extra: Additional fields to record.

    Returns:
        The project key and criterion text, plus the extra fields.
    """
    return {"project": criterion.project.key, "text": criterion.text, **extra}


# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------

def label(project : Project) -> str:
    """Format a project's computed version.

    Args:
        project: Project or subproject.

    Returns:
        The version as "MAJOR.MINOR", e.g. "1.4".
    """
    return f"{project.version_major}.{project.version_minor}"


def bump_minor(session : Session, feature : Task, actor : str = events.ACTOR_WEB) -> None:
    """Raise MINOR on the feature's nearest project, once per feature.

    Called when a feature is completed. Does nothing for a task, for a
    feature without a project, or for a feature that already shipped (it was
    reopened and completed again). Doesn't commit: the caller commits it
    with the completion.

    Args:
        session: Database session to use.
        feature: The work item just completed.
        actor: Who made the change, recorded in the event log.
    """
    if feature.kind != TaskKind.FEATURE or feature.project is None or feature.released_in is not None:
        return

    project = feature.project
    previous = label(project)
    project.version_minor += 1
    feature.released_in = label(project)
    events.log(session, actor, "project", project.id, "minor_bumped",
               {"from": previous, "to": feature.released_in, "feature": feature.ref})


def set_version(session : Session, project_key : str, major : int, minor : int,
                actor : str = events.ACTOR_WEB) -> Project:
    """Set a project's version directly, e.g. when importing an existing project.

    Args:
        session: Database session to use.
        project_key: Key of the project or subproject.
        major: New MAJOR, zero or more.
        minor: New MINOR, zero or more.
        actor: Who made the change, recorded in the event log.

    Returns:
        The updated Project.

    Raises:
        NotFoundError: If no project has this key.
        ValidationError: If a part is negative.
    """
    if major < 0 or minor < 0:
        raise ValidationError("A version part can't be negative.")
    project = projects.get(session, project_key)
    previous = label(project)
    project.version_major = major
    project.version_minor = minor
    events.log(session, actor, "project", project.id, "version_set",
               {"from": previous, "to": label(project)})
    session.commit()
    return project


def parse_label(text : str) -> tuple[int, int] | None:
    """Read a "MAJOR.MINOR" version.

    Args:
        text: The version, e.g. "1.4".

    Returns:
        (major, minor), or None if the text isn't two non-negative integers.
    """
    parts = text.strip().split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]), int(parts[1])


def release_major(session : Session, project_key : str, actor : str = events.ACTOR_WEB) -> Project:
    """Move a project to its next major version.

    MAJOR goes up by 1, MINOR back to 0, and the criteria list is emptied.

    Args:
        session: Database session to use.
        project_key: Key of the project or subproject.
        actor: Who made the change, recorded in the event log.

    Returns:
        The updated Project.

    Raises:
        NotFoundError: If no project has this key.
        ConflictError: If the project has no criterion, or one isn't checked.
    """
    project = projects.get(session, project_key)
    if not project.criteria:
        raise ConflictError(f"project '{project_key}' has no criterion for its next major version.")
    unchecked = [criterion.text for criterion in project.criteria if not criterion.done]
    if unchecked:
        raise ConflictError(
            f"project '{project_key}' still has unchecked criteria: {'; '.join(unchecked)}.")

    previous = label(project)
    project.version_major += 1
    project.version_minor = 0
    events.log(session, actor, "project", project.id, "major_released",
               {"from": previous,
                "to": label(project),
                "criteria": [criterion.text for criterion in project.criteria]})
    project.criteria.clear()
    session.commit()
    return project


# -----------------------------------------------------------------------------
# Major criteria
# -----------------------------------------------------------------------------

def get_criterion(session : Session, criterion_id : int) -> MajorCriterion:
    """Look up a major criterion by its id.

    Args:
        session: Database session to use.
        criterion_id: Id of the criterion.

    Returns:
        The matching MajorCriterion.

    Raises:
        NotFoundError: If no criterion has this id.
    """
    criterion = session.get(MajorCriterion, criterion_id)
    if criterion is None:
        raise NotFoundError(f"Criterion '{criterion_id}' doesn't exist.")
    return criterion


def add_criterion(session : Session, project_key : str, text : str,
                  actor : str = events.ACTOR_WEB) -> MajorCriterion:
    """Add a criterion for a project's next major version, at the end of its list.

    Args:
        session: Database session to use.
        project_key: Key of the project or subproject.
        text: What must be true before the next major version.
        actor: Who made the change, recorded in the event log.

    Returns:
        The new, unchecked MajorCriterion.

    Raises:
        NotFoundError: If no project has this key.
        ValidationError: If the text is empty.
    """
    _require_valid_text(text)
    project = projects.get(session, project_key)
    position = max((criterion.position for criterion in project.criteria), default=-1) + 1

    criterion = MajorCriterion(text=text.strip(), done=False, position=position)
    project.criteria.append(criterion)
    session.flush()

    events.log(session, actor, "criterion", criterion.id, "criterion_added",
               _criterion_payload(criterion))
    session.commit()
    return criterion


def update_criterion(session : Session, criterion_id : int, text : str,
                     actor : str = events.ACTOR_WEB) -> MajorCriterion:
    """Change the text of a major criterion.

    Args:
        session: Database session to use.
        criterion_id: Id of the criterion.
        text: New text.
        actor: Who made the change, recorded in the event log.

    Returns:
        The updated MajorCriterion.

    Raises:
        NotFoundError: If no criterion has this id.
        ValidationError: If the text is empty.
    """
    _require_valid_text(text)
    criterion = get_criterion(session, criterion_id)
    previous = criterion.text
    criterion.text = text.strip()
    events.log(session, actor, "criterion", criterion.id, "criterion_updated",
               _criterion_payload(criterion, previous=previous))
    session.commit()
    return criterion


def set_criterion_done(session : Session, criterion_id : int, done : bool,
                       actor : str = events.ACTOR_WEB) -> MajorCriterion:
    """Check or uncheck a major criterion.

    Args:
        session: Database session to use.
        criterion_id: Id of the criterion.
        done: True to check it, False to uncheck it.
        actor: Who made the change, recorded in the event log.

    Returns:
        The updated MajorCriterion.

    Raises:
        NotFoundError: If no criterion has this id.
    """
    criterion = get_criterion(session, criterion_id)
    previous = criterion.done
    criterion.done = done
    events.log(session, actor, "criterion", criterion.id, "criterion_checked",
               _criterion_payload(criterion, **{"from": previous, "to": done}))
    session.commit()
    return criterion


def delete_criterion(session : Session, criterion_id : int, actor : str = events.ACTOR_WEB) -> None:
    """Delete a major criterion.

    Args:
        session: Database session to use.
        criterion_id: Id of the criterion.
        actor: Who made the change, recorded in the event log.

    Raises:
        NotFoundError: If no criterion has this id.
    """
    criterion = get_criterion(session, criterion_id)
    events.log(session, actor, "criterion", criterion.id, "criterion_deleted",
               _criterion_payload(criterion, done=criterion.done))
    # Removing it from the list (delete-orphan) deletes the row and keeps the
    # project's loaded list in step.
    criterion.project.criteria.remove(criterion)
    session.commit()
