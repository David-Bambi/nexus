from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from src.models.project import Project
from src.models.task import Task, TaskKind, TaskState
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


@dataclass
class TreeNode:
    """One feature or task of a project tree, with the nodes below it."""

    # The feature or task.
    item: Task
    # Nodes of its children, in sibling order; always empty for a task.
    children: list


# States hidden from a project tree unless closed items are asked for.
_CLOSED_STATES = (TaskState.DONE, TaskState.CANCELLED)


def _nodes(items : list, include_closed : bool) -> list:
    """Build the tree nodes of sibling items, recursively.

    Args:
        items: Sibling features and tasks.
        include_closed: Whether done and cancelled items are kept; a
            hidden feature hides its whole subtree.

    Returns:
        A TreeNode per kept item, in sibling order.
    """
    kept = [item for item in items if include_closed or item.state not in _CLOSED_STATES]
    return [TreeNode(item, _nodes(item.children, include_closed))
            for item in sorted(kept, key=lambda item: (item.position, item.id))]


def project_tree(project : Project, include_closed : bool = False) -> list:
    """Give a project's work tree, ready to render.

    Args:
        project: Project or subproject; its subprojects' trees aren't
            included.
        include_closed: Whether done and cancelled items are shown.

    Returns:
        A TreeNode per item at the top of the project, in sibling order.
    """
    top = [item for item in project.tasks if item.parent_id is None]
    return _nodes(top, include_closed)


# Kanban columns, left to right: one per state of work still to do. Done,
# someday and cancelled tasks stay off the board.
BOARD_COLUMNS = (
    TaskState.INBOX,
    TaskState.REFINED,
    TaskState.DOING,
    TaskState.WAITING,
)


@dataclass
class KanbanLane:
    """One swimlane of a kanban board: a top-level feature's tasks, or the
    tasks sitting right under a project."""

    # Top-level feature of the lane; None for the project's loose tasks.
    feature: Optional[Task]
    # Subproject the lane belongs to; None for the board's own project.
    subproject: Optional[Project]
    # Tasks per state, in BOARD_COLUMNS order, every state present.
    columns: dict


def _sorted(items : list) -> list:
    """Sort sibling items in tree order.

    Args:
        items: Sibling features and tasks.

    Returns:
        The items by position, then creation order.
    """
    return sorted(items, key=lambda item: (item.position, item.id))


def _board_tasks(items : list):
    """Walk sibling items depth first and yield the tasks shown on a board.

    Args:
        items: Sibling features and tasks.

    Yields:
        Each task whose state has a column, in tree order; features are
        walked through, never shown.
    """
    for item in _sorted(items):
        if item.kind == TaskKind.FEATURE:
            yield from _board_tasks(item.children)
        elif item.state in BOARD_COLUMNS:
            yield item


def _lane(feature : Optional[Task], subproject : Optional[Project], items : list) -> KanbanLane:
    """Build one swimlane from the items it holds.

    Args:
        feature: Top-level feature of the lane, or None for loose tasks.
        subproject: Subproject the lane belongs to, or None.
        items: Items right under the lane's feature (or loose tasks).

    Returns:
        The lane, with its tasks sorted into state columns.
    """
    columns = {state: [] for state in BOARD_COLUMNS}
    for task in _board_tasks(items):
        columns[task.state].append(task)
    return KanbanLane(feature, subproject, columns)


def _project_lanes(project : Project, subproject : Optional[Project]) -> list:
    """Build the swimlanes of a single project, without its subprojects.

    Args:
        project: Project or subproject whose items are laid out.
        subproject: The same project when it is a subproject of the board,
            None for the board's own project.

    Returns:
        A lane per top-level feature in tree order, then the lane of loose
        tasks; lanes without a task are left out.
    """
    top = _sorted([item for item in project.tasks if item.parent_id is None])
    lanes = [_lane(item, subproject, item.children)
             for item in top if item.kind == TaskKind.FEATURE]
    loose = [item for item in top if item.kind == TaskKind.TASK]
    lanes.append(_lane(None, subproject, loose))
    return [lane for lane in lanes if any(lane.columns.values())]


def project_board(project : Project) -> list:
    """Give a project's kanban board, ready to render.

    Args:
        project: Project or subproject; a root project's subprojects are
            laid out after its own lanes.

    Returns:
        A KanbanLane per non-empty swimlane: the project's own lanes, then
        each subproject's.
    """
    lanes = _project_lanes(project, None)
    for subproject in project.subprojects:
        lanes.extend(_project_lanes(subproject, subproject))
    return lanes


def item_tree(item : Task, include_closed : bool = False) -> list:
    """Give the tree below a feature, ready to render.

    Args:
        item: Feature (or task, whose tree is empty).
        include_closed: Whether done and cancelled items are shown.

    Returns:
        A TreeNode per child, in sibling order.
    """
    return _nodes(item.children, include_closed)


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
