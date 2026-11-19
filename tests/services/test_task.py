import pytest

from src.models.task import TaskKind, TaskState
from src.services import events, projects, tasks
from src.services.errors import ConflictError, InvalidTransitionError, NotFoundError, ValidationError

FEATURE = TaskKind.FEATURE


# Helpers -----------------------------------------------------------------------------------------

def _history(session, task_id):
    """Return a task's logged (action, payload) pairs, oldest first."""
    return [(e.action, e.payload) for e in events.history(session, "task", task_id)]

def _refined_task(session, title="Write the docs"):
    """Capture a task and clarify it, ready to be started."""
    task = tasks.capture(session, title)
    return tasks.clarify(session, task.id, title, None, None, None, None)

def _doing(session, task):
    """Clarify (if needed) and start a work item; return it."""
    if task.state is TaskState.INBOX:
        tasks.clarify(session, task.id, task.title, task.body,
                      task.project.key if task.project else None, None, None,
                      parent_ref=task.parent.ref if task.parent else None)
    return tasks.start(session, task.id)

@pytest.fixture
def nexus(session):
    """A root project 'nexus'."""
    return projects.create(session, "nexus", "Nexus")


# Capture and create ------------------------------------------------------------------------------

def test_capture_returns_inbox_task(session):
    """Capture a title returns a task in the inbox state
    Given no prior state
    When capturing a task titled 'Write the docs'
    Then the task is created in the inbox state, as a task with no project
    """
    task = tasks.capture(session, "Write the docs")
    assert task.state is TaskState.INBOX
    assert task.kind is TaskKind.TASK
    assert task.project is None and task.parent is None
    assert task.ref.startswith("t-")

def test_create_returns_inbox_task(session, nexus):
    """Create a task with detail returns a task in the inbox state
    Given a project 'nexus'
    When creating a task under 'nexus' with a body, context and size
    Then the task is created in the inbox state with that detail
    """
    task = tasks.create(session, "Write the docs", "nexus", "Body", "@ordi", "S")
    assert task.state is TaskState.INBOX
    assert task.project is nexus
    assert (task.body, task.context, task.size) == ("Body", "@ordi", "S")

def test_create_feature(session, nexus):
    """A feature is created with an f- ref
    Given a project 'nexus'
    When creating a feature in it
    Then it has the feature kind and an f- ref
    """
    feature = tasks.create(session, "Tree", "nexus", kind=FEATURE)
    assert feature.kind is FEATURE
    assert feature.ref.startswith("f-")

def test_create_under_a_feature_takes_its_project(session, nexus):
    """An item created under a feature lands in the feature's project
    Given a feature in 'nexus'
    When creating a task under it without naming a project
    Then the task is a child of the feature, in 'nexus'
    """
    feature = tasks.create(session, "Tree", "nexus", kind=FEATURE)
    task = tasks.create(session, "Model", parent_ref=feature.ref)
    assert task.parent is feature
    assert task.project is nexus
    assert feature.children == [task]

def test_create_appends_after_the_last_sibling(session, nexus):
    """New siblings are ordered last
    Given a feature with one child
    When creating a second child
    Then its position comes after the first one
    """
    feature = tasks.create(session, "Tree", "nexus", kind=FEATURE)
    first = tasks.create(session, "One", parent_ref=feature.ref)
    second = tasks.create(session, "Two", parent_ref=feature.ref)
    assert second.position > first.position
    assert feature.children == [first, second]

def test_create_under_a_task_is_refused(session, nexus):
    """Only a feature can hold children
    Given a task in 'nexus'
    When creating an item under it
    Then a validation error is raised
    """
    parent = tasks.create(session, "Leaf", "nexus")
    with pytest.raises(ValidationError):
        tasks.create(session, "Child", parent_ref=parent.ref)

def test_create_under_a_feature_of_another_project_is_refused(session, nexus):
    """The parent must sit in the named project
    Given a feature in 'nexus' and a project 'other'
    When creating an item in 'other' under that feature
    Then a validation error is raised
    """
    projects.create(session, "other", "Other")
    feature = tasks.create(session, "Tree", "nexus", kind=FEATURE)
    with pytest.raises(ValidationError):
        tasks.create(session, "Child", "other", parent_ref=feature.ref)

def test_create_in_a_subproject(session, nexus):
    """A subproject holds its own items
    Given a subproject 'v2' of 'nexus'
    When creating a feature in 'v2'
    Then the feature belongs to 'v2'
    """
    sub = projects.create(session, "v2", "Nexus 2", parent_key="nexus")
    feature = tasks.create(session, "Tree", "v2", kind=FEATURE)
    assert feature.project is sub

@pytest.mark.parametrize("title", ["", "   "])
def test_create_empty_title(session, title):
    """An empty title is refused
    Given no prior state
    When creating an item with a blank title
    Then a validation error is raised
    """
    with pytest.raises(ValidationError):
        tasks.create(session, title)

def test_create_project_or_parent_not_found(session):
    """Unknown project or parent raises a NotFoundError
    Given an empty database
    When creating an item in an unknown project, or under an unknown feature
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        tasks.create(session, "Write the docs", "nexus")
    with pytest.raises(NotFoundError):
        tasks.create(session, "Write the docs", parent_ref="f-zzz")


# Read and update ---------------------------------------------------------------------------------

def test_get_task_found_and_not_found(session):
    """Get returns the task, or raises for an unknown id
    Given one captured task
    When getting it, then an unknown id
    Then the task is returned, then a not found error is raised
    """
    task = tasks.capture(session, "Write the docs")
    assert tasks.get(session, task.id) is task
    with pytest.raises(NotFoundError):
        tasks.get(session, task.id + 1)

def test_list_with_limit_returns_the_most_recent_oldest_first(session):
    """A limit keeps the most recent items, still oldest first
    Given three captured tasks
    When listing with a limit of 2
    Then the last two are returned, oldest first
    """
    for title in ("First", "Second", "Third"):
        tasks.capture(session, title)
    assert [t.title for t in tasks.list(session, limit=2)] == ["Second", "Third"]

def test_update_changes_fields_and_logs_only_changes(session):
    """Update changes descriptive fields and logs only what changed
    Given a captured task
    When updating its title and setting the same body
    Then the title changes and the updated event names only the title
    """
    task = tasks.capture(session, "Old")
    tasks.update(session, task.id, title="New", body=None)
    assert task.title == "New"
    assert _history(session, task.id)[-1] == ("updated", {"title": {"from": "Old", "to": "New"}})

def test_update_rejects_unknown_field(session):
    """Kind, state and placement can't be updated this way
    Given a captured task
    When updating its state or kind
    Then a validation error is raised
    """
    task = tasks.capture(session, "Write the docs")
    for field in ("state", "kind", "parent_id"):
        with pytest.raises(ValidationError):
            tasks.update(session, task.id, **{field: "x"})


# Clarify -----------------------------------------------------------------------------------------

def test_clarify_inbox_task(session, nexus):
    """Clarify an inbox task makes it refined, in its project
    Given a captured task
    When clarifying it into 'nexus'
    Then it is refined and belongs to 'nexus'
    """
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", "Body", "nexus", "@ordi", "S")
    assert task.state is TaskState.REFINED
    assert task.project is nexus

def test_clarify_into_a_feature(session, nexus):
    """Triage can turn a capture into a feature
    Given a captured task
    When clarifying it with the feature kind
    Then it becomes a refined feature with an f- ref, and the kind change is logged
    """
    task = tasks.capture(session, "Tree")
    code = task.ref[2:]
    tasks.clarify(session, task.id, "Tree", None, "nexus", None, None, kind=FEATURE)
    assert task.kind is FEATURE
    assert task.ref == f"f-{code}"
    assert [a for a, _ in _history(session, task.id)] == ["created", "kind_changed", "clarified"]

def test_clarify_under_a_feature(session, nexus):
    """Triage can place a capture under a feature
    Given a feature in 'nexus' and a captured task
    When clarifying the task under the feature
    Then it is a child of the feature, in 'nexus'
    """
    feature = tasks.create(session, "Tree", "nexus", kind=FEATURE)
    task = tasks.capture(session, "Model")
    tasks.clarify(session, task.id, "Model", None, None, None, None, parent_ref=feature.ref)
    assert task.parent is feature and task.project is nexus

def test_clarify_someday_task(session):
    """Clarify reactivates a someday task
    Given a task deferred to someday
    When clarifying it
    Then it is refined
    """
    task = tasks.capture(session, "Maybe")
    tasks.defer(session, task.id)
    tasks.clarify(session, task.id, "Maybe", None, None, None, None)
    assert task.state is TaskState.REFINED

def test_clarify_wrong_state(session):
    """Only inbox or someday items can be clarified
    Given a refined task
    When clarifying it again
    Then an invalid transition error is raised
    """
    task = _refined_task(session)
    with pytest.raises(InvalidTransitionError):
        tasks.clarify(session, task.id, "Again", None, None, None, None)


# Lifecycle ---------------------------------------------------------------------------------------

def test_transitions_log_events(session):
    """Every transition logs an event with its from and to states
    Given a captured task
    When it goes through clarify, start, block, unblock, complete and reopen
    Then each step appears in its history, in order
    """
    task = _refined_task(session)
    tasks.start(session, task.id)
    tasks.block(session, task.id, "Waiting for review")
    tasks.unblock(session, task.id)
    tasks.complete(session, task.id)
    tasks.reopen(session, task.id)

    assert _history(session, task.id)[1:] == [
        ("clarified", {"from": "INBOX", "to": "REFINED", "project": None, "parent": None}),
        ("started", {"from": "REFINED", "to": "DOING"}),
        ("blocked", {"from": "DOING", "to": "WAITING", "reason": "Waiting for review"}),
        ("unblocked", {"from": "WAITING", "to": "DOING"}),
        ("completed", {"from": "DOING", "to": "DONE"}),
        ("reopened", {"from": "DONE", "to": "DOING"}),
    ]

def test_start_needs_a_refined_task(session):
    """An inbox task can't be started
    Given a captured task
    When starting it
    Then an invalid transition error is raised
    """
    task = tasks.capture(session, "Write the docs")
    with pytest.raises(InvalidTransitionError):
        tasks.start(session, task.id)

def test_block_needs_a_reason(session):
    """Blocking needs a reason, and a refused block logs nothing
    Given a task in progress
    When blocking it with an empty reason
    Then a validation error is raised and no blocked event exists
    """
    task = tasks.start(session, _refined_task(session).id)
    with pytest.raises(ValidationError):
        tasks.block(session, task.id, "")
    assert "blocked" not in [a for a, _ in _history(session, task.id)]

@pytest.mark.parametrize("prepare", [
    lambda session, task: None,
    lambda session, task: tasks.start(session, task.id),
    lambda session, task: (tasks.start(session, task.id), tasks.block(session, task.id, "Review")),
])
def test_cancel_open_task(session, prepare):
    """Cancelling an open task closes it and clears its block
    Given a refined task, possibly started or blocked
    When cancelling it
    Then it is cancelled, closed and unblocked
    """
    task = _refined_task(session)
    prepare(session, task)
    tasks.cancel(session, task.id)
    assert task.state is TaskState.CANCELLED
    assert task.closed_at is not None and task.blocked_reason is None

def test_restore_cancelled_task(session):
    """Restore brings a cancelled task back to refined
    Given a cancelled task
    When restoring it
    Then it is refined and no longer closed
    """
    task = _refined_task(session)
    tasks.cancel(session, task.id)
    tasks.restore(session, task.id)
    assert task.state is TaskState.REFINED and task.closed_at is None

def test_change_state_walks_the_working_states(session):
    """Change state follows the lifecycle from refined to done and back
    Given a refined task
    When moving it to doing, waiting, doing, done, then doing
    Then each move lands in the requested state
    """
    task = _refined_task(session)
    for target, reason in ((TaskState.DOING, ""), (TaskState.WAITING, "Review"),
                           (TaskState.DOING, ""), (TaskState.DONE, ""), (TaskState.DOING, "")):
        assert tasks.change_state(session, task.id, target, reason).state is target

@pytest.mark.parametrize("target", [TaskState.INBOX, TaskState.DONE, TaskState.WAITING])
def test_change_state_not_allowed(session, target):
    """Change state refuses a move the lifecycle doesn't allow
    Given a refined task
    When moving it to inbox, done or waiting
    Then an invalid transition error is raised
    """
    task = _refined_task(session)
    with pytest.raises(InvalidTransitionError):
        tasks.change_state(session, task.id, target, "Reason")
    assert task.state is TaskState.REFINED

def test_planned_state_is_gone():
    """Without versions, nothing is planned any more
    Given the task states
    When listing them
    Then PLANNED isn't one of them
    """
    assert "PLANNED" not in TaskState.__members__


# Closing a feature -------------------------------------------------------------------------------

@pytest.fixture
def feature_with_child(session, nexus):
    """A feature in progress with one task in progress below it."""
    feature = tasks.create(session, "Tree", "nexus", kind=FEATURE)
    child = tasks.create(session, "Model", parent_ref=feature.ref)
    _doing(session, feature)
    _doing(session, child)
    return feature, child

@pytest.mark.parametrize("close", [tasks.complete, tasks.cancel])
def test_feature_with_open_children_cant_close(session, feature_with_child, close):
    """A feature can't be completed or cancelled while a child is open
    Given a feature with a child in progress
    When completing or cancelling the feature
    Then a conflict error is raised and the feature stays in progress
    """
    feature, _ = feature_with_child
    with pytest.raises(ConflictError):
        close(session, feature.id)
    assert feature.state is TaskState.DOING

@pytest.mark.parametrize("close_child", [tasks.complete, tasks.cancel])
def test_feature_closes_once_children_are_closed(session, feature_with_child, close_child):
    """A feature closes once every child is done or cancelled
    Given a feature whose only child is done or cancelled
    When completing the feature
    Then it is done
    """
    feature, child = feature_with_child
    close_child(session, child.id)
    tasks.complete(session, feature.id)
    assert feature.state is TaskState.DONE


# Move --------------------------------------------------------------------------------------------

def test_move_under_a_feature_keeps_the_state(session, nexus):
    """Moving keeps the state and logs where from and where to
    Given a task in progress at the top of 'nexus' and a feature
    When moving the task under the feature
    Then it is the feature's child, still in progress, and a moved event names both places
    """
    feature = tasks.create(session, "Tree", "nexus", kind=FEATURE)
    task = _doing(session, tasks.create(session, "Model", "nexus"))
    tasks.move(session, task.id, parent_ref=feature.ref)
    assert task.parent is feature and task.state is TaskState.DOING
    assert _history(session, task.id)[-1] == ("moved", {
        "from": {"project": "nexus", "parent": None},
        "to": {"project": "nexus", "parent": feature.ref}})

def test_move_a_feature_takes_its_subtree(session, nexus):
    """A moved feature takes its descendants to the new project
    Given a feature with a sub-feature and a task in 'nexus', and a subproject 'v2'
    When moving the feature to 'v2'
    Then the feature and every descendant belong to 'v2'
    """
    sub = projects.create(session, "v2", "Nexus 2", parent_key="nexus")
    feature = tasks.create(session, "Tree", "nexus", kind=FEATURE)
    inner = tasks.create(session, "Inner", parent_ref=feature.ref, kind=FEATURE)
    leaf = tasks.create(session, "Leaf", parent_ref=inner.ref)
    tasks.move(session, feature.id, project_key="v2")
    assert feature.parent is None
    assert {feature.project, inner.project, leaf.project} == {sub}

def test_move_under_itself_or_a_descendant_is_refused(session, nexus):
    """No cycle in the tree
    Given a feature with a sub-feature
    When moving the feature under itself or under its sub-feature
    Then a validation error is raised each time
    """
    feature = tasks.create(session, "Tree", "nexus", kind=FEATURE)
    inner = tasks.create(session, "Inner", parent_ref=feature.ref, kind=FEATURE)
    for target in (feature, inner):
        with pytest.raises(ValidationError):
            tasks.move(session, feature.id, parent_ref=target.ref)

def test_move_needs_a_new_place(session, nexus):
    """Moving needs a destination different from the current one
    Given a task at the top of 'nexus'
    When moving it with no destination, or to 'nexus' again
    Then a validation error is raised each time and nothing is logged
    """
    task = tasks.create(session, "Model", "nexus")
    with pytest.raises(ValidationError):
        tasks.move(session, task.id)
    with pytest.raises(ValidationError):
        tasks.move(session, task.id, project_key="nexus")
    assert [a for a, _ in _history(session, task.id)] == ["created"]


# Change kind -------------------------------------------------------------------------------------

def test_change_kind_respells_the_ref(session, nexus):
    """A task becomes a feature and back, keeping its code
    Given a task 't-<code>'
    When turning it into a feature, then back into a task
    Then its ref is 'f-<code>', then 't-<code>', and both changes are logged
    """
    task = tasks.create(session, "Tree", "nexus")
    code = task.ref[2:]
    tasks.change_kind(session, task.id, FEATURE)
    assert task.ref == f"f-{code}"
    assert tasks.get_by_ref(session, f"t-{code}") is task
    tasks.change_kind(session, task.id, TaskKind.TASK)
    assert task.ref == f"t-{code}"
    assert _history(session, task.id)[1] == (
        "kind_changed", {"from": "TASK", "to": "FEATURE", "ref": {"from": f"t-{code}", "to": f"f-{code}"}})

def test_change_kind_of_a_feature_with_children_is_refused(session, nexus):
    """A feature with children can't become a task
    Given a feature with a child
    When turning it into a task
    Then a validation error is raised
    """
    feature = tasks.create(session, "Tree", "nexus", kind=FEATURE)
    tasks.create(session, "Model", parent_ref=feature.ref)
    with pytest.raises(ValidationError):
        tasks.change_kind(session, feature.id, TaskKind.TASK)

def test_change_kind_to_the_same_kind_is_refused(session):
    """Changing to the current kind is refused
    Given a task
    When turning it into a task
    Then a validation error is raised
    """
    task = tasks.capture(session, "Write the docs")
    with pytest.raises(ValidationError):
        tasks.change_kind(session, task.id, TaskKind.TASK)


# Delete ------------------------------------------------------------------------------------------

def test_delete_logs_deleted_and_keeps_history(session):
    """Delete logs a deleted event and leaves the history readable
    Given a captured task
    When deleting it
    Then it is gone, and its history holds created and deleted
    """
    task = tasks.capture(session, "Write the docs")
    task_id, ref = task.id, task.ref
    tasks.delete(session, task_id)
    with pytest.raises(NotFoundError):
        tasks.get(session, task_id)
    assert _history(session, task_id)[-1] == (
        "deleted", {"title": "Write the docs", "kind": "TASK", "ref": ref})

def test_delete_a_feature_with_children_is_refused(session, nexus):
    """A feature is deleted only once empty
    Given a feature with a child
    When deleting the feature, then the child, then the feature
    Then the first delete raises a conflict error; the next two succeed
    """
    feature = tasks.create(session, "Tree", "nexus", kind=FEATURE)
    child = tasks.create(session, "Model", parent_ref=feature.ref)
    with pytest.raises(ConflictError):
        tasks.delete(session, feature.id)
    tasks.delete(session, child.id)
    session.refresh(feature)
    tasks.delete(session, feature.id)
    assert tasks.list(session) == []


# Reorder -----------------------------------------------------------------------------------------

def _siblings(session, project_key="nexus"):
    """Titles of a project's top items, in sibling order."""
    from src.services import views
    return [node.item.title for node in views.project_tree(projects.get(session, project_key), include_closed=True)]


def _top_items(session, *titles):
    """Create refined top items of project 'nexus'; return them."""
    items = []
    for title in titles:
        item = tasks.create(session, title, project_key="nexus")
        items.append(tasks.clarify(session, item.id, title, None, "nexus", None, None))
    return items


def test_reorder_up_and_down_logs_the_move(session, nexus):
    """
    Given three sibling items A, B, C
    When C goes up, then A goes down
    Then the order is B, A, C… step by step, and each move is logged
    """
    a, b, c = _top_items(session, "A", "B", "C")
    tasks.reorder(session, c.id, "up")
    assert _siblings(session) == ["A", "C", "B"]

    tasks.reorder(session, a.id, "down")
    assert _siblings(session) == ["C", "A", "B"]
    assert _history(session, a.id)[-1] == ("reordered", {"from": 0, "to": 1, "direction": "down"})


def test_reorder_first_up_or_last_down_is_refused(session, nexus):
    """The first item can't go up, the last can't go down."""
    a, b = _top_items(session, "A", "B")
    with pytest.raises(ValidationError, match="already first"):
        tasks.reorder(session, a.id, "up")
    with pytest.raises(ValidationError, match="already last"):
        tasks.reorder(session, b.id, "down")


def test_reorder_open_item_skips_closed_siblings(session, nexus):
    """An open item moves past a cancelled sibling hidden from the tree."""
    a, b, c = _top_items(session, "A", "B", "C")
    tasks.cancel(session, b.id)
    tasks.reorder(session, c.id, "up")
    assert _siblings(session) == ["C", "A", "B"]


def test_reorder_stays_among_siblings_under_a_feature(session, nexus):
    """Reordering under a feature leaves the top level as it was."""
    feature, top = _top_items(session, "Auth", "Readme")
    tasks.change_kind(session, feature.id, TaskKind.FEATURE)
    children = []
    for title in ("Login", "Logout"):
        child = tasks.create(session, title, project_key="nexus", parent_ref=feature.ref)
        children.append(tasks.clarify(session, child.id, title, None, "nexus", None, None, parent_ref=feature.ref))
    tasks.reorder(session, children[1].id, "up")

    assert [child.title for child in feature.children] == ["Logout", "Login"]
    assert _siblings(session) == ["Auth", "Readme"]


def test_reorder_refuses_a_capture_or_a_bad_direction(session, nexus):
    """An inbox capture has no tree order; a direction must be up or down."""
    capture = tasks.capture(session, "Loose")
    with pytest.raises(ValidationError, match="no project"):
        tasks.reorder(session, capture.id, "up")
    (item,) = _top_items(session, "A")
    with pytest.raises(ValidationError, match="unknown direction"):
        tasks.reorder(session, item.id, "sideways")
