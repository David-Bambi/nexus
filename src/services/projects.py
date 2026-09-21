from sqlalchemy.orm import Session

from src.models.project import Project, ProjectStatus
from src.services import events, refs
from src.services.errors import ConflictError, NotFoundError, ValidationError

# Keys a project may not take: the command line reads them as commands, not
# as project keys.
RESERVED_KEYS = frozenset({"add", "help", "import", "projects", "tasks", "version", "versions"})

def is_reserved_key(key : str) -> bool:
    """Tell whether a project key is refused as a command word or ref lookalike.

    Args:
        key: Candidate project key.
    """
    return key.strip().lower() in RESERVED_KEYS or refs.is_ref(key)

def create(session : Session, key : str, name : str, description : str | None = None,
           actor : str = events.ACTOR_WEB) -> Project:
    """Create a project.

    Args:
        session: Database session to use.
        key: Unique slug identifying the project (used in URLs).
        name: Human-readable project name.
        description: Optional free-text description.
        actor: Who made the change, recorded in the event log.

    Returns:
        The newly created Project.

    Raises:
        ConflictError: If a project with this key already exists.
        ValidationError: If the key is a reserved word or looks like a
            task or version ref.
    """
    if is_reserved_key(key):
        raise ValidationError(f"project key '{key}' is reserved.")

    if session.query(Project).filter_by(key=key).first() is not None:
        raise ConflictError(f"project key '{key}' already exists")

    project = Project(key=key,
                      name=name,
                      description=description)
    session.add(project)
    session.flush()
    events.log(session, actor, "project", project.id, "created",
               {"key": key, "name": name})
    session.commit()
    return project

def get(session : Session, key : str) -> Project:
    """Look up a project by its key.

    Args:
        session: Database session to use.
        key: Unique slug identifying the project.

    Returns:
        The matching Project.

    Raises:
        NotFoundError: If no project has this key.
    """
    project = session.query(Project).filter_by(key=key).first()
    if project is None:
        raise NotFoundError(f"Project '{key}' doesn't exist.")
    else:
        return project

def list(session : Session, include_archived : bool = False) -> list:
    """List projects.

    Args:
        session: Database session to use.
        include_archived: If False (default), archived projects are excluded.

    Returns:
        All matching projects.
    """
    query = session.query(Project)
    if not include_archived:
        query = query.filter(Project.status != ProjectStatus.ARCHIVED)
    return query.all()

def archive(session : Session, key : str) -> Project:
    """Archive a project.

    Args:
        session: Database session to use.
        key: Unique slug identifying the project.

    Returns:
        The archived Project.

    Raises:
        NotFoundError: If no project has this key.
    """
    project = get(session, key)
    previous = project.status
    project.status = ProjectStatus.ARCHIVED
    events.log(session, events.ACTOR_WEB, "project", project.id, "archived",
               {"from": previous.name, "to": ProjectStatus.ARCHIVED.name})
    session.commit()
    return project

def delete(session : Session, key : str) -> None:
    """Delete a project.

    Args:
        session: Database session to use.
        key: Unique slug identifying the project.

    Raises:
        NotFoundError: If no project has this key.
    """
    project = get(session, key)
    events.log(session, events.ACTOR_WEB, "project", project.id, "deleted",
               {"key": key, "name": project.name})
    session.delete(project)
    session.commit()

