from sqlalchemy.orm import Session, joinedload

from src.models.task import Task, TaskState
from src.services import projects
from src.services.errors import NotFoundError


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


def to_refine(session : Session, context : str | None = None, project_key : str | None = None) -> list:
    """List refined tasks that still need to be planned into a version.

    Args:
        session: Database session to use.
        context: Optional context tag (e.g. "@ordi") to filter on.
        project_key: Optional project key to filter on. A key matching no
            project simply yields no results, rather than raising.

    Returns:
        Refined, unplanned tasks matching the given filters, oldest first.
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

    return query.order_by(Task.created_at).all()


def search(session : Session, term : str) -> list:
    """Search tasks by a substring of their title or body.

    Args:
        session: Database session to use.
        term: Text to search for, matched case-insensitively. An empty or
            missing term yields no results, rather than the whole table.

    Returns:
        Matching tasks, oldest first.
    """
    if not term:
        return []

    pattern = f"%{term}%"
    return (
        session.query(Task)
        .filter((Task.title.ilike(pattern)) | (Task.body.ilike(pattern)))
        .order_by(Task.created_at)
        .all()
    )
