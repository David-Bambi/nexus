from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.models.project import Project
from src.models.task import Task, TaskKind
from src.services import projects, refs, tasks


@dataclass(frozen=True)
class Target:
    """What a reference (from the CLI, an MCP call, …) points at."""

    # "project", "subproject", "feature" or "task".
    kind: str
    # The matching Project or Task.
    entity: Project | Task


def resolve(session : Session, reference : str) -> Target:
    """Resolve a reference to the row it designates.

    Args:
        session: Database session to use.
        reference: A subproject ref ("s-4k2"), a feature or task ref
            ("f-4k2", "t-4k2") or a project key.

    Returns:
        The Target found. Its kind follows the row, not the prefix typed: a
        task that became a feature is a "feature" even when named "t-…". A
        string shaped like a ref is never read as a project key:
        projects.create refuses such keys.

    Raises:
        NotFoundError: If nothing has this reference.
    """
    if not refs.is_ref(reference):
        return Target("project", projects.get(session, reference))
    if refs.prefix_of(reference) == refs.SUBPROJECT:
        return Target("subproject", projects.get_by_ref(session, reference))

    item = tasks.get_by_ref(session, reference)
    return Target("feature" if item.kind is TaskKind.FEATURE else "task", item)
