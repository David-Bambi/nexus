import pytest

from src.models.task import TaskKind, TaskState
from src.services import projects, tasks, views
from src.services.errors import NotFoundError

# Inbox --------------------------------------------------------------------------------------------

def test_inbox_returns_only_inbox_tasks(session):
    """Inbox lists only inbox-state tasks
    Given a captured task and a refined task
    When listing the inbox
    Then only the captured task is returned
    """
    inbox_task = tasks.capture(session, "Write the docs")
    refined_task = tasks.capture(session, "Ship the release")
    tasks.clarify(session, refined_task.id, "Ship the release", None, None, None, None)

    result = views.inbox(session)
    assert [t.id for t in result] == [inbox_task.id]

def test_inbox_oldest_first(session):
    """Inbox lists tasks oldest first
    Given two captured tasks
    When listing the inbox
    Then they come back in capture order
    """
    first = tasks.capture(session, "First")
    second = tasks.capture(session, "Second")

    result = views.inbox(session)
    assert [t.id for t in result] == [first.id, second.id]

def test_inbox_empty(session):
    """Inbox with no captured tasks returns an empty list
    Given no tasks
    When listing the inbox
    Then the resulting list is empty
    """
    assert not views.inbox(session)


# To refine ------------------------------------------------------------------------------------------

def test_to_refine_returns_only_refined_tasks(session):
    """To-refine lists only refined items, ready to start
    Given an inbox task, a refined task and a started task
    When listing to-refine
    Then only the refined task is returned
    """
    tasks.capture(session, "Still in inbox")

    refined = tasks.capture(session, "Ready")
    tasks.clarify(session, refined.id, "Ready", None, None, None, None)

    started = tasks.capture(session, "Started")
    tasks.clarify(session, started.id, "Started", None, None, None, None)
    tasks.start(session, started.id)

    result = views.to_refine(session)
    assert [t.id for t in result] == [refined.id]

def test_to_refine_filters_by_context(session):
    """To-refine filters by context when given
    Given two refined tasks with different contexts
    When listing to-refine filtered by one context
    Then only the matching task is returned
    """
    matching = tasks.capture(session, "At the computer")
    tasks.clarify(session, matching.id, "At the computer", None, None, "@ordi", None)

    other = tasks.capture(session, "At the store")
    tasks.clarify(session, other.id, "At the store", None, None, "@achat", None)

    result = views.to_refine(session, context="@ordi")
    assert [t.id for t in result] == [matching.id]

def test_to_refine_filters_by_project_key(session):
    """To-refine filters by project key when given
    Given refined tasks under two different projects
    When listing to-refine filtered by one project key
    Then only that project's task is returned
    """
    projects.create(session, "nexus", "Nexus", "")
    projects.create(session, "other", "Other", "")

    matching = tasks.capture(session, "Nexus task")
    tasks.clarify(session, matching.id, "Nexus task", None, "nexus", None, None)

    other = tasks.capture(session, "Other task")
    tasks.clarify(session, other.id, "Other task", None, "other", None, None)

    result = views.to_refine(session, project_key="nexus")
    assert [t.id for t in result] == [matching.id]

def test_to_refine_unknown_project_key_returns_empty(session):
    """To-refine with an unknown project key returns no results
    Given a refined task with no project
    When listing to-refine filtered by a project key that doesn't exist
    Then the resulting list is empty
    """
    task = tasks.capture(session, "Needs planning")
    tasks.clarify(session, task.id, "Needs planning", None, None, None, None)

    assert not views.to_refine(session, project_key="does-not-exist")


# Search --------------------------------------------------------------------------------------------

def test_search_matches_title(session):
    """Search matches a substring of the title
    Given a captured task
    When searching for part of its title
    Then it is returned
    """
    task = tasks.capture(session, "Write the docs")
    result = views.search(session, "the docs")
    assert [t.id for t in result] == [task.id]

def test_search_matches_body(session):
    """Search matches a substring of the body
    Given a task with a body
    When searching for part of its body
    Then it is returned
    """
    projects.create(session, "nexus", "Nexus", "")
    task = tasks.create(session, "Ship it", "nexus", "Needs a changelog entry")
    result = views.search(session, "changelog")
    assert [t.id for t in result] == [task.id]

def test_search_is_case_insensitive(session):
    """Search matches regardless of case
    Given a captured task
    When searching using different casing than the title
    Then it is still returned
    """
    task = tasks.capture(session, "Write the docs")
    result = views.search(session, "WRITE")
    assert [t.id for t in result] == [task.id]

def test_search_no_match(session):
    """Search with no matching text returns an empty list
    Given a captured task
    When searching for text it doesn't contain
    Then the resulting list is empty
    """
    tasks.capture(session, "Write the docs")
    assert not views.search(session, "nonexistent")

def test_search_empty_term_returns_empty(session):
    """Search with an empty term returns no results, not the whole table
    Given a captured task
    When searching with an empty term
    Then the resulting list is empty
    """
    tasks.capture(session, "Write the docs")
    assert not views.search(session, "")


# Dashboard ----------------------------------------------------------------------------------------

def _refined_task(session, title):
    """Capture and clarify a task."""
    task = tasks.capture(session, title)
    return tasks.clarify(session, task.id, title, None, None, None, None)

def test_dashboard_empty(session):
    """Dashboard on an empty database shows nothing
    Given no data
    When building the dashboard
    Then there are no tasks and both counters are zero
    """
    result = views.dashboard(session)

    assert not result.doing
    assert not result.waiting
    assert result.inbox_count == 0
    assert result.refine_count == 0

def test_dashboard_splits_doing_and_waiting(session):
    """Dashboard separates items in progress from blocked ones
    Given a doing task, a waiting task and a merely refined task
    When building the dashboard
    Then doing and waiting hold one task each, and the refined task appears in neither
    """
    doing = _refined_task(session, "Doing")
    waiting = _refined_task(session, "Waiting")
    _refined_task(session, "Refined")
    tasks.start(session, doing.id)
    tasks.start(session, waiting.id)
    tasks.block(session, waiting.id, "Waiting for review")

    result = views.dashboard(session)
    assert [t.id for t in result.doing] == [doing.id]
    assert [t.id for t in result.waiting] == [waiting.id]

def test_dashboard_counters_match_inbox_and_refine(session):
    """Dashboard counters match the inbox and refine queues
    Given two inbox tasks, one refined task and one started task
    When building the dashboard
    Then the counters equal the lengths of inbox() and to_refine()
    """
    tasks.capture(session, "First")
    tasks.capture(session, "Second")
    _refined_task(session, "Ready")
    tasks.start(session, _refined_task(session, "Started").id)

    result = views.dashboard(session)
    assert result.inbox_count == len(views.inbox(session)) == 2
    assert result.refine_count == len(views.to_refine(session)) == 1


# Limits -------------------------------------------------------------------------------------------

def test_to_refine_limit_keeps_the_oldest(session):
    """To refine with a limit returns only the oldest tasks
    Given three refined tasks
    When listing the queue with a limit of 2
    Then the two oldest are returned, oldest first
    """
    ids = [_refined_task(session, name).id for name in ("First", "Second", "Third")]

    result = views.to_refine(session, limit=2)
    assert [t.id for t in result] == ids[:2]

def test_to_refine_without_limit_returns_everything(session):
    """To refine without a limit returns the whole queue
    Given three refined tasks
    When listing the queue
    Then all three are returned
    """
    for name in ("First", "Second", "Third"):
        _refined_task(session, name)

    assert len(views.to_refine(session)) == 3

def test_search_limit_keeps_the_oldest_matches(session):
    """Search with a limit returns only the oldest matches
    Given three tasks containing 'docs'
    When searching with a limit of 2
    Then the two oldest matches are returned
    """
    ids = [tasks.capture(session, f"Docs {n}").id for n in range(3)]

    result = views.search(session, "docs", limit=2)
    assert [t.id for t in result] == ids[:2]

# List tasks ---------------------------------------------------------------------------------------

@pytest.fixture
def board(session):
    """Two projects, a feature in the first, and items in several states and places."""
    projects.create(session, "nx", "Nexus", "")
    projects.create(session, "other", "Other", "")
    loose = tasks.capture(session, "Loose")
    in_project = tasks.create(session, "In project", project_key="nx")
    feature = tasks.create(session, "Feature", project_key="nx", kind=TaskKind.FEATURE)
    doing = tasks.create(session, "Doing", parent_ref=feature.ref)
    tasks.clarify(session, doing.id, "Doing", None, None, None, None, parent_ref=feature.ref)
    tasks.start(session, doing.id)
    elsewhere = tasks.create(session, "Elsewhere", project_key="other")
    return loose, in_project, feature, doing, elsewhere


def _titles(result):
    return [t.title for t in result]


def test_list_tasks_without_filters_returns_everything_oldest_first(session, board):
    """
    Given tasks in several states and projects
    When listing without filters
    Then all come back in creation order
    """
    assert _titles(views.list_tasks(session)) == ["Loose", "In project", "Feature", "Doing", "Elsewhere"]


def test_list_tasks_filters_by_states(session, board):
    """
    Given tasks in several states
    When filtering on one state, then on two
    Then a task matches if it is in any of the given states
    """
    assert _titles(views.list_tasks(session, states=[TaskState.DOING])) == ["Doing"]
    assert _titles(views.list_tasks(session, states=[TaskState.DOING, TaskState.CANCELLED])) == ["Doing"]
    assert len(views.list_tasks(session, states=[TaskState.DOING, TaskState.INBOX])) == 5


def test_list_tasks_filters_by_project(session, board):
    """
    Given items spread over projects, some under a feature
    When filtering by project, alone and with a state
    Then only matching items are returned, those under a feature included
    """
    assert _titles(views.list_tasks(session, project_key="nx")) == ["In project", "Feature", "Doing"]
    assert _titles(views.list_tasks(session, project_key="nx", states=[TaskState.INBOX])) == ["In project", "Feature"]


def test_list_tasks_limit_keeps_the_most_recent_oldest_first(session, board):
    """
    Given five items
    When listing with a limit of two
    Then the two most recently created come back, oldest first
    """
    assert _titles(views.list_tasks(session, limit=2)) == ["Doing", "Elsewhere"]


def test_list_tasks_unknown_project_raises(session, board):
    """
    Given no project with the key
    When filtering on it
    Then a not-found error is raised
    """
    with pytest.raises(NotFoundError):
        views.list_tasks(session, project_key="ghost")


# Project tree ------------------------------------------------------------------------------------

def _refined(session, title, project_key=None, parent_ref=None, kind=TaskKind.TASK):
    """Create a refined item in a project's tree; return it."""
    item = tasks.create(session, title, project_key=None if parent_ref else project_key,
                        parent_ref=parent_ref, kind=kind)
    return tasks.clarify(session, item.id, title, None, project_key, None, None, parent_ref=parent_ref)


def _shape(nodes):
    """Turn tree nodes into nested (title, children) pairs."""
    return [(node.item.title, _shape(node.children)) for node in nodes]


@pytest.fixture
def tree(session):
    """A project 'nx' with a feature holding a sub-feature and a task, and a top task."""
    project = projects.create(session, "nx", "Nexus")
    auth = _refined(session, "Auth", "nx", kind=TaskKind.FEATURE)
    login = _refined(session, "Login", "nx", parent_ref=auth.ref, kind=TaskKind.FEATURE)
    _refined(session, "Form", "nx", parent_ref=login.ref)
    _refined(session, "Hash", "nx", parent_ref=auth.ref)
    _refined(session, "Readme", "nx")
    return project


def test_project_tree_nests_items_in_sibling_order(session, tree):
    """The tree gives the top items, then each feature's children, in order."""
    assert _shape(views.project_tree(tree)) == [
        ("Auth", [("Login", [("Form", [])]), ("Hash", [])]),
        ("Readme", []),
    ]


def test_project_tree_hides_closed_items_unless_asked(session, tree):
    """
    Given a cancelled task and a cancelled feature
    When building the tree
    Then both are hidden, with the feature's subtree, unless closed items are asked for
    """
    by_title = {t.title: t for t in tasks.list(session)}
    tasks.cancel(session, by_title["Hash"].id)
    tasks.cancel(session, by_title["Form"].id)
    tasks.cancel(session, by_title["Login"].id)

    assert _shape(views.project_tree(tree)) == [("Auth", []), ("Readme", [])]
    assert _shape(views.project_tree(tree, include_closed=True))[0] == (
        "Auth", [("Login", [("Form", [])]), ("Hash", [])])


def test_project_tree_leaves_out_subprojects(session, tree):
    """A subproject's items aren't part of its parent's tree."""
    projects.create(session, "sub", "Sub", parent_key="nx")
    _refined(session, "Sub task", "sub")
    assert [title for title, _ in _shape(views.project_tree(tree))] == ["Auth", "Readme"]


def test_item_tree_gives_a_feature_children(session, tree):
    """The tree below a feature holds its children only."""
    auth = next(t for t in tasks.list(session) if t.title == "Auth")
    assert _shape(views.item_tree(auth)) == [("Login", [("Form", [])]), ("Hash", [])]


# Project board -----------------------------------------------------------------------------------

def _board(lanes):
    """Turn board lanes into (feature, subproject, {state: [task titles]}) triples,
    keeping only non-empty columns."""
    return [
        (lane.feature.title if lane.feature else None,
         lane.subproject.key if lane.subproject else None,
         {state.name: [task.title for task in tasks_] for state, tasks_ in lane.columns.items() if tasks_})
        for lane in lanes
    ]


def _by_title(session):
    """Map every task and feature title to its item."""
    return {t.title: t for t in tasks.list(session)}


def test_project_board_lays_tasks_out_by_feature(session, tree):
    """
    Given a feature holding a sub-feature and a task, and a loose task
    When building the board
    Then the feature has a lane with its tasks, sub-features included, and the loose task has
    its own lane last; features are never cards
    """
    assert _board(views.project_board(tree)) == [
        ("Auth", None, {"REFINED": ["Form", "Hash"]}),
        (None, None, {"REFINED": ["Readme"]}),
    ]


def test_project_board_has_a_column_per_open_state_in_order(session, tree):
    """Each lane holds a column per state of work still to do, in board order."""
    lane = views.project_board(tree)[0]
    assert list(lane.columns) == list(views.BOARD_COLUMNS)
    assert [state.name for state in views.BOARD_COLUMNS] == ["INBOX", "REFINED", "DOING", "WAITING"]


def test_project_board_sorts_tasks_by_state(session, tree):
    """
    Given a started task and a blocked task
    When building the board
    Then each task sits in its state's column
    """
    by_title = _by_title(session)
    tasks.start(session, by_title["Hash"].id)
    tasks.start(session, by_title["Form"].id)
    tasks.block(session, by_title["Form"].id, "Waiting on review")

    assert _board(views.project_board(tree))[0] == (
        "Auth", None, {"DOING": ["Hash"], "WAITING": ["Form"]})


def test_project_board_follows_tree_order(session, tree):
    """
    Given a task moved above the sub-feature
    When building the board
    Then it comes first in the column
    """
    tasks.reorder(session, _by_title(session)["Hash"].id, "up")

    assert _board(views.project_board(tree))[0][2]["REFINED"] == ["Hash", "Form"]


def test_project_board_leaves_out_closed_and_someday_tasks_and_empty_lanes(session, tree):
    """
    Given a done task, a deferred task and the only loose task cancelled
    When building the board
    Then none of them is on the board, and the emptied loose lane is left out
    """
    by_title = _by_title(session)
    tasks.start(session, by_title["Form"].id)
    tasks.complete(session, by_title["Form"].id)
    tasks.defer(session, by_title["Hash"].id)
    tasks.cancel(session, by_title["Readme"].id)

    assert views.project_board(tree) == []


def test_project_board_leaves_out_features_without_tasks(session, tree):
    """A feature with no task below it gets no lane."""
    _refined(session, "Empty", "nx", kind=TaskKind.FEATURE)
    assert [lane[0] for lane in _board(views.project_board(tree))] == ["Auth", None]


def test_project_board_adds_subproject_lanes_after(session, tree):
    """
    Given a subproject with a feature and a loose task
    When building the parent's board
    Then the subproject's lanes come after the parent's, tagged with the subproject
    """
    projects.create(session, "sub", "Sub", parent_key="nx")
    api = _refined(session, "Api", "sub", kind=TaskKind.FEATURE)
    _refined(session, "Endpoint", "sub", parent_ref=api.ref)
    _refined(session, "Loose", "sub")

    assert _board(views.project_board(tree))[2:] == [
        ("Api", "sub", {"REFINED": ["Endpoint"]}),
        (None, "sub", {"REFINED": ["Loose"]}),
    ]


def test_project_board_empty_project(session):
    """A project without tasks has an empty board."""
    project = projects.create(session, "void", "Void")
    assert views.project_board(project) == []
