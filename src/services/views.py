from dataclasses import dataclass

from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from src.models.task import Task, TaskState
from src.models.version import Version, VersionStatus
from src.services import projects
from src.services.errors import NotFoundError


@dataclass
class VersionProgress:
    """An in-progress version with how far its tasks have got."""

    # The version itself, with its project loaded.
    version: Version
    # Number of the version's tasks that are done.
    done: int
    # Number of tasks planned into the version, whatever their state.
    total: int


@dataclass
class DashboardView:
    """Everything the overview page shows, gathered in one read."""

    # In-progress versions with their progress.
    versions: list
    # Tasks currently being worked on.
    doing: list
    # Tasks blocked on a third party or a prerequisite.
    waiting: list
    # Number of captured tasks still to triage.
    inbox_count: int
    # Number of refined tasks still to plan into a version.
    refine_count: int


def inbox(session : Session) -> list:
    """List captured tasks still waiting to be triaged.

    Args:
        session: Database session to use.

    Returns:
        Inbox-state tasks, oldest first (the order they should be
        processed in, one at a time).
    """
    return (
        session.query(Task)
        .filter(Task.state == TaskState.INBOX)
        .order_by(Task.created_at)
        .all()
    )


def to_refine(session : Session, context : str | None = None, project_key : str | None = None,
              limit : int | None = None) -> list:
    """List refined tasks that still need to be planned into a version.

    Args:
        session: Database session to use.
        context: Optional context tag (e.g. "@ordi") to filter on.
        project_key: Optional project key to filter on. A key matching no
            project simply yields no results, rather than raising.
        limit: Optional maximum number of tasks to return.

    Returns:
        Refined, unplanned tasks matching the given filters, oldest first
        (the oldest `limit` of them when a limit is given).
    """
    query = session.query(Task).options(joinedload(Task.project)).filter(
        Task.state == TaskState.REFINED, Task.version_id.is_(None)
    )

    if context:
        query = query.filter(Task.context == context)

    if project_key:
        try:
            project = projects.get(session, project_key)
        except NotFoundError:
            return []
        query = query.filter(Task.project_id == project.id)

    query = query.order_by(Task.created_at)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def search(session : Session, term : str, limit : int | None = None) -> list:
    """Search tasks by a substring of their title or body.

    Args:
        session: Database session to use.
        term: Text to search for, matched case-insensitively. An empty or
            missing term yields no results, rather than the whole table.
        limit: Optional maximum number of tasks to return.

    Returns:
        Matching tasks, oldest first (the oldest `limit` of them when a
        limit is given).
    """
    if not term:
        return []

    pattern = f"%{term}%"
    query = (
        session.query(Task)
        .filter((Task.title.ilike(pattern)) | (Task.body.ilike(pattern)))
        .order_by(Task.created_at)
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def dashboard(session : Session) -> DashboardView:
    """Gather what the overview page shows.

    Args:
        session: Database session to use.

    Returns:
        A DashboardView with the in-progress versions and their progress,
        the doing and waiting tasks (oldest first), and the inbox and
        refine counters (same definitions as inbox() and to_refine()).
    """
    started = (
        session.query(Version)
        .options(joinedload(Version.project))
        .filter(Version.status == VersionStatus.IN_PROGRESS)
        .order_by(Version.project_id, Version.position, Version.id)
        .all()
    )

    counts = {
        version_id: (done, total)
        for version_id, done, total in session.query(
            Task.version_id,
            func.sum(case((Task.state == TaskState.DONE, 1), else_=0)),
            func.count(Task.id),
        )
        .filter(Task.version_id.in_([v.id for v in started]))
        .group_by(Task.version_id)
    }

    def in_state(state : TaskState) -> list:
        """List the tasks in the given state, oldest first."""
        return (
            session.query(Task)
            .options(joinedload(Task.project), joinedload(Task.version))
            .filter(Task.state == state)
            .order_by(Task.created_at)
            .all()
        )

    return DashboardView(
        versions=[VersionProgress(v, *counts.get(v.id, (0, 0))) for v in started],
        doing=in_state(TaskState.DOING),
        waiting=in_state(TaskState.WAITING),
        inbox_count=session.query(Task).filter(Task.state == TaskState.INBOX).count(),
        refine_count=session.query(Task).filter(
            Task.state == TaskState.REFINED, Task.version_id.is_(None)
        ).count(),
    )
