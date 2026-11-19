from dataclasses import dataclass

from sqlalchemy.orm import Session, joinedload

from src.models.task import Task, TaskState
from src.services import projects
from src.services.errors import NotFoundError


@dataclass
class DashboardView:
    """Everything the overview page shows, gathered in one read."""

    # Tasks currently being worked on.
    doing: list
    # Tasks blocked on a third party or a prerequisite.
    waiting: list
    # Number of captured tasks still to triage.
    inbox_count: int
    # Number of refined items, ready to be started.
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
    """List refined items, ready to be started.

    Args:
        session: Database session to use.
        context: Optional context tag (e.g. "@ordi") to filter on.
        project_key: Optional project key to filter on. A key matching no
            project simply yields no results, rather than raising.
        limit: Optional maximum number of tasks to return.

    Returns:
        Refined items matching the given filters, oldest first
        (the oldest `limit` of them when a limit is given).
    """
    query = session.query(Task).options(joinedload(Task.project)).filter(
        Task.state == TaskState.REFINED
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


def list_tasks(session : Session, states : list[TaskState] | None = None, project_key : str | None = None,
               limit : int | None = None) -> list:
    """List tasks matching any combination of filters.

    Args:
        session: Database session to use.
        states: Optional states to keep; a task matches if it is in any of them.
        project_key: Optional project key to filter on.
        limit: Optional maximum number of tasks to return.

    Returns:
        Matching tasks in creation order, oldest first. With a limit, only
        the `limit` most recently created ones (still oldest first).

    Raises:
        NotFoundError: If project_key is given but no project has this key.
    """
    query = session.query(Task).options(joinedload(Task.project), joinedload(Task.parent))

    if states:
        query = query.filter(Task.state.in_(states))
    if project_key:
        query = query.filter(Task.project_id == projects.get(session, project_key).id)

    if limit is None:
        return query.order_by(Task.created_at, Task.id).all()

    recent = query.order_by(Task.created_at.desc(), Task.id.desc()).limit(limit).all()
    return recent[::-1]


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
        A DashboardView with the doing and waiting items (oldest first),
        and the inbox and refine counters (same definitions as inbox() and
        to_refine()).
    """
    def in_state(state : TaskState) -> list:
        """List the tasks in the given state, oldest first."""
        return (
            session.query(Task)
            .options(joinedload(Task.project), joinedload(Task.parent))
            .filter(Task.state == state)
            .order_by(Task.created_at)
            .all()
        )

    return DashboardView(
        doing=in_state(TaskState.DOING),
        waiting=in_state(TaskState.WAITING),
        inbox_count=session.query(Task).filter(Task.state == TaskState.INBOX).count(),
        refine_count=session.query(Task).filter(Task.state == TaskState.REFINED).count(),
    )
