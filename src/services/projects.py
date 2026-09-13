from sqlalchemy.orm import Session

from src.models.project import Project, ProjectStatus
from src.services.errors import ConflictError, NotFoundError

def create(session : Session, key : str, name : str, description : str | None = None) -> Project:
    """Create a project.

    Args:
        session: Database session to use.
        key: Unique slug identifying the project (used in URLs).
        name: Human-readable project name.
        description: Optional free-text description.

    Returns:
        The newly created Project.

    Raises:
        ConflictError: If a project with this key already exists.
    """
    if session.query(Project).filter_by(key=key).first() is not None:
        raise ConflictError(f"project key '{key}' already exists")

    project = Project(key=key,
                      name=name,
                      description=description)
    session.add(project)
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
        raise NotFoundError
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
    project.status = ProjectStatus.ARCHIVED
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
    session.delete(project)
    session.commit()

