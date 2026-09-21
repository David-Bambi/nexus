from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.models.project import Project
from src.models.task import Task
from src.models.version import Version
from src.services import projects, refs, tasks, versions
from src.services.errors import NotFoundError


@dataclass(frozen=True)
class Target:
    """What a reference (from the CLI, an MCP call, …) points at."""

    # "project", "version" or "task".
    kind: str
    # The matching Project, Version or Task.
    entity: Project | Version | Task


def resolve(session : Session, reference : str) -> Target:
    """Resolve a reference to the row it designates.

    Args:
        session: Database session to use.
        reference: A task ref ("t-4k2"), a version ref ("v-9xa") or a
            project key.

    Returns:
        The Target found. A string shaped like a ref is never read as a
        project key: projects.create refuses such keys.

    Raises:
        NotFoundError: If nothing has this reference.
    """
    if refs.is_ref(reference):
        if reference.strip().lower().startswith("t"):
            return Target("task", tasks.get_by_ref(session, reference))
        return Target("version", versions.get_by_ref(session, reference))
    return Target("project", projects.get(session, reference))


def resolve_version(session : Session, project_key : str, version : str) -> Version:
    """Resolve a version named within a project.

    Args:
        session: Database session to use.
        project_key: Key of the owning project.
        version: The version's ref ("v-9xa") or its number ("0.2.0").

    Returns:
        The matching Version.

    Raises:
        NotFoundError: If the project or the version doesn't exist, or the
            ref belongs to another project.
    """
    project = projects.get(session, project_key)
    if not refs.is_ref(version):
        return versions.get(session, project_key, version)

    found = versions.get_by_ref(session, version)
    if found.project_id != project.id:
        raise NotFoundError(f"Version '{version}' doesn't belong to project '{project_key}'.")
    return found
