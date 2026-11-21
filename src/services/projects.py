import os

from sqlalchemy.orm import Session

from src.models.project import Project, ProjectPriority, ProjectStatus
from src.services import events, refs
from src.services.errors import ConflictError, NotFoundError, ValidationError

# Keys a project may not take: the command line reads them as commands, not
# as project keys.
RESERVED_KEYS = frozenset({"add", "export", "help", "import", "projects", "state", "tasks", "version"})

# Default of update()'s directory argument: leave the directory as it is.
KEEP = object()

# Priorities from the most to the least pressing, the order projects are listed in.
PRIORITY_ORDER = (ProjectPriority.HIGH, ProjectPriority.NORMAL, ProjectPriority.LOW)

def normalize_directory(directory : str | None) -> str | None:
    """Turn a typed folder path into the stored form.

    Args:
        directory: Path as typed; "~" is expanded. None or blank means none.

    Returns:
        The absolute, normalised path without a trailing slash, or None.

    Raises:
        ValidationError: If the path is relative.
    """
    if directory is None or not directory.strip():
        return None
    path = os.path.expanduser(directory.strip())
    if not os.path.isabs(path):
        raise ValidationError(f"the directory must be an absolute path (or start with ~): '{directory.strip()}'.")
    return os.path.normpath(path)

def directory_of(project : Project | None) -> str | None:
    """The folder a project's work happens in: its own, else its parent's.

    Args:
        project: Project or subproject, or None.

    Returns:
        The nearest directory set, or None.
    """
    if project is None:
        return None
    if project.directory is None and project.parent is not None:
        return project.parent.directory
    return project.directory

def is_reserved_key(key : str) -> bool:
    """Tell whether a project key is refused as a command word or ref lookalike.

    Args:
        key: Candidate project key.
    """
    return key.strip().lower() in RESERVED_KEYS or refs.is_ref(key)

def create(session : Session, key : str, name : str, description : str | None = None,
           parent_key : str | None = None, directory : str | None = None,
           actor : str = events.ACTOR_WEB) -> Project:
    """Create a root project, or a subproject when a parent is given.

    Args:
        session: Database session to use.
        key: Unique slug identifying the project (used in URLs).
        name: Human-readable project name.
        description: Optional free-text description.
        parent_key: Key of the root project to create a subproject under;
            None for a root project.
        directory: Optional folder of the project on this machine (see
            normalize_directory).
        actor: Who made the change, recorded in the event log.

    Returns:
        The newly created Project. A subproject gets an "s-…" ref.

    Raises:
        ConflictError: If a project with this key already exists.
        NotFoundError: If the parent project doesn't exist.
        ValidationError: If the key is a reserved word or looks like a
            subproject, feature or task ref, if the parent is itself a
            subproject (only one level of subprojects), or if the directory
            is a relative path.
    """
    directory = normalize_directory(directory)
    if is_reserved_key(key):
        raise ValidationError(f"project key '{key}' is reserved.")

    if session.query(Project).filter_by(key=key).first() is not None:
        raise ConflictError(f"project key '{key}' already exists")

    parent = None
    if parent_key is not None:
        parent = get(session, parent_key)
        if parent.parent_id is not None:
            raise ValidationError(
                f"'{parent_key}' is a subproject; a subproject can't hold another one.")

    project = Project(key=key,
                      name=name,
                      description=description,
                      parent_id=parent.id if parent else None,
                      directory=directory,
                      ref=refs.generate(session, refs.SUBPROJECT) if parent else None)
    session.add(project)
    session.flush()

    payload = {"key": key, "name": name}
    if directory is not None:
        payload["directory"] = directory
    if parent is not None:
        payload.update(ref=project.ref, parent=parent.key)
    events.log(session, actor, "project", project.id, "created", payload)
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

def get_by_ref(session : Session, ref : str) -> Project:
    """Look up a subproject by its short ref.

    Args:
        session: Database session to use.
        ref: Ref of the subproject (e.g. "s-4k2"), case-insensitive.

    Returns:
        The matching subproject.

    Raises:
        NotFoundError: If no subproject has this ref.
    """
    project = session.query(Project).filter_by(ref=refs.normalize(ref)).first()
    if project is None:
        raise NotFoundError(f"Subproject '{ref}' doesn't exist.")
    return project

def list(session : Session, include_archived : bool = False) -> list:
    """List projects.

    Args:
        session: Database session to use.
        include_archived: If False (default), archived projects are excluded.

    Returns:
        All matching projects, by priority (high first), then in creation
        order; a subproject sorts with its root.
    """
    query = session.query(Project)
    if not include_archived:
        query = query.filter(Project.status != ProjectStatus.ARCHIVED)
    return sorted(query.all(), key=lambda p: (PRIORITY_ORDER.index(p.effective_priority),
                                              p.parent_id or p.id, p.parent_id is not None, p.id))

def archive(session : Session, key : str, actor : str = events.ACTOR_WEB) -> Project:
    """Archive a project.

    Args:
        session: Database session to use.
        key: Unique slug identifying the project.
        actor: Who made the change, recorded in the event log.

    Returns:
        The archived Project.

    Raises:
        NotFoundError: If no project has this key.
    """
    project = get(session, key)
    previous = project.status
    project.status = ProjectStatus.ARCHIVED
    events.log(session, actor, "project", project.id, "archived",
               {"from": previous.name, "to": ProjectStatus.ARCHIVED.name})
    session.commit()
    return project

def update(session : Session, key : str, name : str, description : str | None,
           directory : str | None | object = KEEP, priority : ProjectPriority | None = None,
           actor : str = events.ACTOR_WEB) -> Project:
    """Change a project's name, description, directory and priority; its key never changes.

    Args:
        session: Database session to use.
        key: Unique slug identifying the project.
        name: New display name.
        description: New description; None or blank clears it.
        directory: New folder (see normalize_directory); None or blank
            clears it; KEEP (the default) leaves it unchanged.
        priority: New priority, root projects only; None leaves it unchanged.
        actor: Who made the change, recorded in the event log.

    Returns:
        The updated Project. Only the fields that changed are logged, and
        nothing is logged if none did.

    Raises:
        NotFoundError: If no project has this key.
        ValidationError: If the name is empty, the directory relative, or a
            priority is given for a subproject (it follows its root's).
    """
    if not name.strip():
        raise ValidationError("The project name must be specified.")
    project = get(session, key)
    if priority is not None and project.parent is not None and priority is not project.priority:
        raise ValidationError(f"subproject '{key}' follows its root project's priority.")

    new_values = {"name": name.strip(), "description": (description or "").strip() or None}
    if directory is not KEEP:
        new_values["directory"] = normalize_directory(directory)
    if priority is not None:
        new_values["priority"] = priority
    changes = {}
    for field, value in new_values.items():
        previous = getattr(project, field)
        if previous != value:
            # An enum is logged by its name, to stay readable JSON.
            changes[field] = {"from": getattr(previous, "name", previous), "to": getattr(value, "name", value)}
            setattr(project, field, value)

    if changes:
        events.log(session, actor, "project", project.id, "updated", changes)
    session.commit()
    return project

def restore(session : Session, key : str, actor : str = events.ACTOR_WEB) -> Project:
    """Bring an archived project back to active.

    Args:
        session: Database session to use.
        key: Unique slug identifying the project.
        actor: Who made the change, recorded in the event log.

    Returns:
        The active Project.

    Raises:
        NotFoundError: If no project has this key.
        ConflictError: If the project isn't archived.
    """
    project = get(session, key)
    if project.status != ProjectStatus.ARCHIVED:
        raise ConflictError(f"project '{key}' isn't archived.")
    project.status = ProjectStatus.ACTIVE
    events.log(session, actor, "project", project.id, "restored",
               {"from": ProjectStatus.ARCHIVED.name, "to": ProjectStatus.ACTIVE.name})
    session.commit()
    return project

def delete(session : Session, key : str, actor : str = events.ACTOR_WEB) -> None:
    """Delete an empty project or subproject.

    Args:
        session: Database session to use.
        key: Unique slug identifying the project.
        actor: Who made the change, recorded in the event log.

    Raises:
        NotFoundError: If no project has this key.
        ConflictError: If the project still holds subprojects, features or
            tasks: they must be deleted or moved first.
    """
    project = get(session, key)
    if project.subprojects or project.tasks:
        raise ConflictError(
            f"project '{key}' isn't empty: delete or move its subprojects, features and tasks first.")

    payload = {"key": key, "name": project.name}
    if project.ref is not None:
        payload["ref"] = project.ref
    events.log(session, actor, "project", project.id, "deleted", payload)
    session.delete(project)
    session.commit()
