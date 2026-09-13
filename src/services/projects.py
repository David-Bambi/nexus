from sqlalchemy.orm import Session

from src.models.project import Project, ProjectStatus
from src.services.errors import ConflictError, NotFoundError

def create(session : Session, key : str, name : str, description : str | None = None) -> Project:
    """Create a project. Raises ConflictError if the key is already taken."""
    if session.query(Project).filter_by(key=key).first() is not None:
        raise ConflictError(f"project key '{key}' already exists")

    project = Project(key=key, 
                      name=name, 
                      description=description)
    session.add(project)
    session.commit()
    return project

def get(session : Session, key : str) -> Project:
    project = session.query(Project).filter_by(key=key).first()
    if project is None:
        raise NotFoundError
    else:
        return project

def list(session : Session, include_archived : bool = False) -> list:
    """List projects. Archived projects are excluded unless include_archived is True."""
    query = session.query(Project)
    if not include_archived:
        query = query.filter(Project.status != ProjectStatus.ARCHIVED)
    return query.all()

def archive(session : Session, key : str) -> Project:
    """Archive a project. Raises NotFoundError if the key doesn't exist."""
    project = get(session, key)
    project.status = ProjectStatus.ARCHIVED
    session.commit()
    return project
