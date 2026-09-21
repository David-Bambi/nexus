import pytest

from src.services import events, projects, tasks, versions
from src.models.task import TaskState
from src.services.errors import InvalidTransitionError, NotFoundError, ValidationError

# Capture -----------------------------------------------------------------------------------------

def test_capture_returns_inbox_task(session):
    """Capture a title returns a task in the inbox state
    Given no prior state
    When capturing a task titled 'Write the docs'
    Then the task is created in the inbox state
    """
    task = tasks.capture(session, "Write the docs")
    assert task.id is not None
    assert task.title == "Write the docs"
    assert task.state is TaskState.INBOX


# Create --------------------------------------------------------------------------------------------

def test_create_returns_inbox_task(session):
    """Create a task with detail returns a task in the inbox state
    Given a project 'nexus'
    When creating a task under 'nexus' with a body, context and size
    Then the task is created in the inbox state with that detail
    """
    projects.create(session, "nexus", "Nexus", "")
    task = tasks.create(session, "Write the docs", "nexus", "Body", "@ordi", "S")
    assert task.state is TaskState.INBOX
    assert task.project_id is not None
    assert task.body == "Body"
    assert task.context == "@ordi"
    assert task.size == "S"

def test_create_project_not_found(session):
    """Create a task under a non existing project raises a NotFoundError
    Given no project with 'nexus' key
    When creating a task under 'nexus'
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        tasks.create(session, "Write the docs", "nexus")


# Create in version ------------------------------------------------------------------------------

def _released_version(session):
    """Create project 'nexus' with a released version 0.1.0 and return that version."""
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    versions.set_criterion_done(session, version.definition_of_done[0].id, True)
    versions.release(session, version.id)
    return version

def test_create_in_version_returns_planned_task(session):
    """Create a planned task returns a task planned in the version
    Given an open version
    When creating a planned task with a body, context and size
    Then the task is planned into that version's project with that detail
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.create_in_version(session, version.id, "Write the docs", "@ordi", "S", "Body")
    assert task.state is TaskState.PLANNED
    assert task.project_id == version.project_id
    assert task.version_id == version.id
    assert task.context == "@ordi"
    assert task.size == "S"
    assert task.body == "Body"
    assert [t.id for t in versions.list_tasks(session, version.id)] == [task.id]

def test_create_in_version_logs_created_event(session):
    """Create a planned task logs a created event
    Given an open version
    When creating a planned task
    Then its history holds a created event with the title, state and version
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.create_in_version(session, version.id, "Write the docs")
    assert _history(session, task.id) == [
        ("created", {"title": "Write the docs", "state": "PLANNED", "version_id": version.id})
    ]

def test_create_in_version_version_not_found(session):
    """Create a planned task in a non existing version raises a NotFoundError
    Given no version with id 1
    When creating a planned task in version 1
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        tasks.create_in_version(session, 1, "Write the docs")

def test_create_in_version_released_version(session):
    """Create a planned task in a released version raises a ValidationError
    Given a released version
    When creating a planned task in that version
    Then a validation error is raised and no task is created
    """
    version = _released_version(session)
    with pytest.raises(ValidationError):
        tasks.create_in_version(session, version.id, "Write the docs")
    assert tasks.list(session) == []

@pytest.mark.parametrize("title", ["", " "])
def test_create_in_version_empty_title(session, title):
    """Create a planned task with an empty title raises a ValidationError
    Given an open version
    When creating a planned task with an empty or blank title
    Then a validation error is raised and no task is created
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    with pytest.raises(ValidationError):
        tasks.create_in_version(session, version.id, title)
    assert tasks.list(session) == []


# Get ---------------------------------------------------------------------------------------------

def test_get_task_found(session):
    """Get an existing task returns that task
    Given a captured task
    When getting that task by id
    Then the task is returned
    """
    captured = tasks.capture(session, "Write the docs")
    task = tasks.get(session, captured.id)
    assert task.id == captured.id

def test_get_task_not_found(session):
    """Get a non existing task raises a NotFoundError
    Given no task with id 1
    When getting task 1
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        tasks.get(session, 1)


# List --------------------------------------------------------------------------------------------

def test_list_no_task(session):
    """List with no tasks returns an empty list
    Given no tasks
    When listing tasks
    Then the resulting list is empty
    """
    assert not tasks.list(session)

def test_list_with_task(session):
    """List with a task returns it
    Given a captured task
    When listing tasks
    Then the resulting list contains that task
    """
    captured = tasks.capture(session, "Write the docs")
    task_list = tasks.list(session)
    assert len(task_list) == 1
    assert task_list[0].id == captured.id


# Update ------------------------------------------------------------------------------------------

def test_update_changes_fields(session):
    """Update a task's fields changes them
    Given a captured task
    When updating its title and size
    Then the task reflects the new values
    """
    task = tasks.capture(session, "Write the docs")
    updated = tasks.update(session, task.id, title="Write better docs", size="M")
    assert updated.title == "Write better docs"
    assert updated.size == "M"

def test_update_task_not_found(session):
    """Update a non existing task raises a NotFoundError
    Given no task with id 1
    When updating task 1
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        tasks.update(session, 1, title="Anything")

def test_update_rejects_unknown_field(session):
    """Update with a field outside the allowed set raises a ValidationError
    Given a captured task
    When updating its state directly through update()
    Then a validation error is raised
    """
    task = tasks.capture(session, "Write the docs")
    with pytest.raises(ValidationError):
        tasks.update(session, task.id, state=TaskState.DONE)


# Clarify -------------------------------------------------------------------------------------------

def test_clarify_inbox_task(session):
    """Clarify an inbox task moves it to refined
    Given a captured task
    When clarifying it with full detail
    Then the task is refined with that detail
    """
    projects.create(session, "nexus", "Nexus", "")
    task = tasks.capture(session, "Write the docs")
    clarified = tasks.clarify(session, task.id, "Write the docs", "Body", "nexus", "@ordi", "S")
    assert clarified.state is TaskState.REFINED
    assert clarified.project_id is not None
    assert clarified.context == "@ordi"

def test_clarify_someday_task(session):
    """Clarify a someday task reactivates it to refined
    Given a task deferred to someday
    When clarifying it
    Then the task is refined
    """
    task = tasks.capture(session, "Write the docs")
    tasks.defer(session, task.id)
    clarified = tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    assert clarified.state is TaskState.REFINED

def test_clarify_not_found(session):
    """Clarify a non existing task raises a NotFoundError
    Given no task with id 1
    When clarifying task 1
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        tasks.clarify(session, 1, "Title", None, None, None, None)

def test_clarify_wrong_state(session):
    """Clarify a task that isn't inbox or someday raises an InvalidTransitionError
    Given a refined task
    When clarifying it again
    Then an invalid transition error is raised
    """
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    with pytest.raises(InvalidTransitionError):
        tasks.clarify(session, task.id, "Write the docs", None, None, None, None)


# Plan ---------------------------------------------------------------------------------------------

def test_plan_refined_task(session):
    """Plan a refined task into a version moves it to planned
    Given a refined task and an open version
    When planning the task into the version
    Then the task is planned into that version's project
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    planned = tasks.plan(session, task.id, version.id)
    assert planned.state is TaskState.PLANNED
    assert planned.project_id == version.project_id
    assert planned.version_id == version.id

def test_plan_task_not_found(session):
    """Plan a non existing task raises a NotFoundError
    Given no task with id 1
    When planning task 1
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        tasks.plan(session, 1, 1)

def test_plan_version_not_found(session):
    """Plan into a non existing version raises a NotFoundError
    Given a refined task and no version with id 1
    When planning the task into version 1
    Then a not found error is raised
    """
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    with pytest.raises(NotFoundError):
        tasks.plan(session, task.id, 1)

def test_plan_not_refined(session):
    """Plan a task that isn't refined raises an InvalidTransitionError
    Given an inbox task and an open version
    When planning the task into the version
    Then an invalid transition error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    with pytest.raises(InvalidTransitionError):
        tasks.plan(session, task.id, version.id)

def test_plan_released_version(session):
    """Plan into an already released version raises a ValidationError
    Given a refined task and a released version
    When planning the task into that version
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    versions.set_criterion_done(session, version.definition_of_done[0].id, True)
    versions.release(session, version.id)
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    with pytest.raises(ValidationError):
        tasks.plan(session, task.id, version.id)

def test_plan_different_project(session):
    """Plan into a version of a different project raises a ValidationError
    Given a refined task attached to project 'nexus' and a version under 'other'
    When planning the task into that version
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    projects.create(session, "other", "Other", "")
    version = versions.create(session, "other", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, "nexus", None, None)
    with pytest.raises(ValidationError):
        tasks.plan(session, task.id, version.id)


# Unplan --------------------------------------------------------------------------------------------

def test_unplan_planned_task(session):
    """Unplan a planned task moves it back to refined
    Given a planned task
    When unplanning it
    Then the task is refined and no longer linked to a version
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    tasks.plan(session, task.id, version.id)
    unplanned = tasks.unplan(session, task.id)
    assert unplanned.state is TaskState.REFINED
    assert unplanned.version_id is None

def test_unplan_not_planned(session):
    """Unplan a task that isn't planned raises an InvalidTransitionError
    Given an inbox task
    When unplanning it
    Then an invalid transition error is raised
    """
    task = tasks.capture(session, "Write the docs")
    with pytest.raises(InvalidTransitionError):
        tasks.unplan(session, task.id)


# Start ---------------------------------------------------------------------------------------------

def test_start_planned_task(session):
    """Start a planned task moves it to doing
    Given a planned task
    When starting it
    Then the task is doing
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    tasks.plan(session, task.id, version.id)
    started = tasks.start(session, task.id)
    assert started.state is TaskState.DOING

def test_start_not_planned(session):
    """Start a task that isn't planned raises an InvalidTransitionError
    Given an inbox task
    When starting it
    Then an invalid transition error is raised
    """
    task = tasks.capture(session, "Write the docs")
    with pytest.raises(InvalidTransitionError):
        tasks.start(session, task.id)


# Block / unblock -------------------------------------------------------------------------------------

def test_block_doing_task(session):
    """Block a doing task moves it to waiting with a reason
    Given a doing task
    When blocking it with a reason
    Then the task is waiting with that reason recorded
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    tasks.plan(session, task.id, version.id)
    tasks.start(session, task.id)
    blocked = tasks.block(session, task.id, "Waiting on review")
    assert blocked.state is TaskState.WAITING
    assert blocked.blocked_reason == "Waiting on review"

def test_block_not_doing(session):
    """Block a task that isn't doing raises an InvalidTransitionError
    Given an inbox task
    When blocking it
    Then an invalid transition error is raised
    """
    task = tasks.capture(session, "Write the docs")
    with pytest.raises(InvalidTransitionError):
        tasks.block(session, task.id, "Some reason")

def test_block_empty_reason(session):
    """Block with an empty reason raises a ValidationError
    Given a doing task
    When blocking it with an empty reason
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    tasks.plan(session, task.id, version.id)
    tasks.start(session, task.id)
    with pytest.raises(ValidationError):
        tasks.block(session, task.id, "")

def test_unblock_waiting_task(session):
    """Unblock a waiting task moves it back to doing
    Given a waiting task
    When unblocking it
    Then the task is doing and its blocked reason is cleared
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    tasks.plan(session, task.id, version.id)
    tasks.start(session, task.id)
    tasks.block(session, task.id, "Waiting on review")
    unblocked = tasks.unblock(session, task.id)
    assert unblocked.state is TaskState.DOING
    assert unblocked.blocked_reason is None

def test_unblock_not_waiting(session):
    """Unblock a task that isn't waiting raises an InvalidTransitionError
    Given an inbox task
    When unblocking it
    Then an invalid transition error is raised
    """
    task = tasks.capture(session, "Write the docs")
    with pytest.raises(InvalidTransitionError):
        tasks.unblock(session, task.id)


# Complete / reopen -----------------------------------------------------------------------------------

def test_complete_doing_task(session):
    """Complete a doing task moves it to done
    Given a doing task
    When completing it
    Then the task is done with closed_at set
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    tasks.plan(session, task.id, version.id)
    tasks.start(session, task.id)
    completed = tasks.complete(session, task.id)
    assert completed.state is TaskState.DONE
    assert completed.closed_at is not None

def test_complete_not_doing(session):
    """Complete a task that isn't doing raises an InvalidTransitionError
    Given an inbox task
    When completing it
    Then an invalid transition error is raised
    """
    task = tasks.capture(session, "Write the docs")
    with pytest.raises(InvalidTransitionError):
        tasks.complete(session, task.id)

def test_reopen_done_task(session):
    """Reopen a done task moves it back to doing
    Given a done task
    When reopening it
    Then the task is doing and closed_at is cleared
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    tasks.plan(session, task.id, version.id)
    tasks.start(session, task.id)
    tasks.complete(session, task.id)
    reopened = tasks.reopen(session, task.id)
    assert reopened.state is TaskState.DOING
    assert reopened.closed_at is None

def test_reopen_not_done(session):
    """Reopen a task that isn't done raises an InvalidTransitionError
    Given an inbox task
    When reopening it
    Then an invalid transition error is raised
    """
    task = tasks.capture(session, "Write the docs")
    with pytest.raises(InvalidTransitionError):
        tasks.reopen(session, task.id)


# Defer ---------------------------------------------------------------------------------------------

def test_defer_inbox_task(session):
    """Defer an inbox task moves it to someday
    Given an inbox task
    When deferring it
    Then the task is someday
    """
    task = tasks.capture(session, "Write the docs")
    deferred = tasks.defer(session, task.id)
    assert deferred.state is TaskState.SOMEDAY

def test_defer_planned_task(session):
    """Defer a planned task raises an InvalidTransitionError
    Given a planned task
    When deferring it
    Then an invalid transition error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    tasks.plan(session, task.id, version.id)
    with pytest.raises(InvalidTransitionError):
        tasks.defer(session, task.id)


# Delete --------------------------------------------------------------------------------------------

def test_delete_task(session):
    """Delete a task removes it
    Given a captured task
    When deleting it
    Then getting it afterward raises a NotFoundError
    """
    task = tasks.capture(session, "Write the docs")
    tasks.delete(session, task.id)
    with pytest.raises(NotFoundError):
        tasks.get(session, task.id)

def test_delete_task_not_found(session):
    """Delete a non existing task raises a NotFoundError
    Given no task with id 1
    When deleting task 1
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        tasks.delete(session, 1)


# Events ------------------------------------------------------------------------------------------

def _history(session, task_id):
    """Return a task's logged (action, payload) pairs, oldest first."""
    return [(e.action, e.payload) for e in events.history(session, "task", task_id)]

def _refined_task(session, title="Write the docs"):
    """Capture a task and clarify it, ready to be planned."""
    task = tasks.capture(session, title)
    return tasks.clarify(session, task.id, title, None, None, None, None)

def _doing_task(session):
    """Return a task in the doing state, inside a fresh project and version."""
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = _refined_task(session)
    tasks.plan(session, task.id, version.id)
    return tasks.start(session, task.id), version

def test_capture_logs_created(session):
    """Capture logs a created event
    Given no prior state
    When capturing a task titled 'Write the docs'
    Then its history holds a created event carrying the title
    """
    task = tasks.capture(session, "Write the docs")
    assert _history(session, task.id) == [("created", {"title": "Write the docs"})]

def test_create_logs_created(session):
    """Create logs a created event
    Given no prior state
    When creating a task titled 'Write the docs'
    Then its history holds a created event carrying the title
    """
    task = tasks.create(session, "Write the docs")
    assert _history(session, task.id) == [("created", {"title": "Write the docs"})]

def test_update_logs_changed_fields_only(session):
    """Update logs an updated event holding only the changed fields
    Given a captured task with no body
    When updating its title and passing the same empty body
    Then the updated event lists the title change and not the body
    """
    task = tasks.capture(session, "Write the docs")
    tasks.update(session, task.id, title="Write the manual", body=None)

    assert _history(session, task.id)[1] == (
        "updated", {"title": {"from": "Write the docs", "to": "Write the manual"}})

def test_update_without_change_logs_nothing(session):
    """Update that changes nothing logs no event
    Given a captured task
    When updating its title to the same value
    Then only the created event is in its history
    """
    task = tasks.capture(session, "Write the docs")
    tasks.update(session, task.id, title="Write the docs")

    assert [action for action, _ in _history(session, task.id)] == ["created"]

def test_transitions_log_events(session):
    """Every transition logs an event with its from and to states
    Given a captured task
    When it goes through clarify, plan, start, block, unblock, complete and reopen
    Then each step appears in its history, in order, with the states it moved between
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = _refined_task(session)
    tasks.plan(session, task.id, version.id)
    tasks.start(session, task.id)
    tasks.block(session, task.id, "Waiting for review")
    tasks.unblock(session, task.id)
    tasks.complete(session, task.id)
    tasks.reopen(session, task.id)

    assert _history(session, task.id)[1:] == [
        ("clarified", {"from": "INBOX", "to": "REFINED"}),
        ("planned", {"from": "REFINED", "to": "PLANNED", "version_id": version.id}),
        ("started", {"from": "PLANNED", "to": "DOING"}),
        ("blocked", {"from": "DOING", "to": "WAITING", "reason": "Waiting for review"}),
        ("unblocked", {"from": "WAITING", "to": "DOING"}),
        ("completed", {"from": "DOING", "to": "DONE"}),
        ("reopened", {"from": "DONE", "to": "DOING"}),
    ]

def test_unplan_logs_unplanned(session):
    """Unplan logs an unplanned event
    Given a planned task
    When unplanning it
    Then its history ends with an unplanned event
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = _refined_task(session)
    tasks.plan(session, task.id, version.id)
    tasks.unplan(session, task.id)

    assert _history(session, task.id)[-1] == ("unplanned", {"from": "PLANNED", "to": "REFINED"})

def test_defer_logs_deferred(session):
    """Defer logs a deferred event with the state it left
    Given a refined task
    When deferring it
    Then its history ends with a deferred event from refined to someday
    """
    task = _refined_task(session)
    tasks.defer(session, task.id)

    assert _history(session, task.id)[-1] == ("deferred", {"from": "REFINED", "to": "SOMEDAY"})

def test_refused_transition_logs_nothing(session):
    """A refused transition logs no event
    Given a captured task
    When completing it, which is not allowed from inbox
    Then an invalid transition error is raised and only the created event exists
    """
    task = tasks.capture(session, "Write the docs")
    with pytest.raises(InvalidTransitionError):
        tasks.complete(session, task.id)

    assert [action for action, _ in _history(session, task.id)] == ["created"]

def test_refused_block_logs_nothing(session):
    """A block refused for its empty reason logs no event
    Given a task in progress
    When blocking it with an empty reason
    Then a validation error is raised and no blocked event exists
    """
    task, _ = _doing_task(session)
    with pytest.raises(ValidationError):
        tasks.block(session, task.id, "")

    assert "blocked" not in [action for action, _ in _history(session, task.id)]

def test_delete_logs_deleted_and_keeps_history(session):
    """Delete logs a deleted event and leaves the task's history readable
    Given a captured task
    When deleting it
    Then its history holds the created and deleted events, the latter carrying the title
    """
    task = tasks.capture(session, "Write the docs")
    task_id = task.id
    tasks.delete(session, task_id)

    assert _history(session, task_id) == [
        ("created", {"title": "Write the docs"}),
        ("deleted", {"title": "Write the docs"}),
    ]


# List ---------------------------------------------------------------------------------------------

def test_list_with_limit_returns_the_most_recent_oldest_first(session):
    """List with a limit returns the newest tasks, in creation order
    Given four captured tasks
    When listing with a limit of 3
    Then the three most recent are returned, oldest first
    """
    ids = [tasks.capture(session, f"Task {n}").id for n in range(4)]

    result = tasks.list(session, limit=3)
    assert [t.id for t in result] == ids[1:]

def test_list_limit_larger_than_the_data_returns_everything(session):
    """List with a limit above the number of tasks returns them all
    Given two captured tasks
    When listing with a limit of 10
    Then both are returned
    """
    tasks.capture(session, "First")
    tasks.capture(session, "Second")

    assert len(tasks.list(session, limit=10)) == 2


# Change state --------------------------------------------------------------------------------------

def _planned_task(session):
    """Create project 'nexus', version 0.1.0 and a task planned in it; return the task."""
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    return tasks.plan(session, task.id, version.id)

def test_change_state_walks_the_working_states(session):
    """Change state follows the lifecycle from planned to done and back
    Given a planned task
    When moving it to doing, waiting, doing, done, then doing
    Then each move lands in the requested state
    """
    task = _planned_task(session)
    assert tasks.change_state(session, task.id, TaskState.DOING).state is TaskState.DOING
    waiting = tasks.change_state(session, task.id, TaskState.WAITING, "Waiting for review")
    assert waiting.state is TaskState.WAITING
    assert waiting.blocked_reason == "Waiting for review"
    assert tasks.change_state(session, task.id, TaskState.DOING).state is TaskState.DOING
    assert tasks.change_state(session, task.id, TaskState.DONE).state is TaskState.DONE
    assert tasks.change_state(session, task.id, TaskState.DOING).state is TaskState.DOING

def test_change_state_waiting_without_reason(session):
    """Change state to waiting without a reason raises a ValidationError
    Given a task in doing
    When moving it to waiting with an empty reason
    Then a validation error is raised and the task stays in doing
    """
    task = _planned_task(session)
    tasks.start(session, task.id)
    with pytest.raises(ValidationError):
        tasks.change_state(session, task.id, TaskState.WAITING)
    assert tasks.get(session, task.id).state is TaskState.DOING

@pytest.mark.parametrize("target", [TaskState.INBOX, TaskState.PLANNED, TaskState.DONE, TaskState.WAITING])
def test_change_state_not_allowed(session, target):
    """Change state to a state the lifecycle doesn't allow raises an InvalidTransitionError
    Given a planned task
    When moving it to inbox, planned, done or waiting
    Then an invalid transition error is raised
    """
    task = _planned_task(session)
    with pytest.raises(InvalidTransitionError):
        tasks.change_state(session, task.id, target, "Reason")
    assert tasks.get(session, task.id).state is TaskState.PLANNED

def test_change_state_not_found(session):
    """Change state of a non existing task raises a NotFoundError
    Given no task with id 1
    When moving task 1 to doing
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        tasks.change_state(session, 1, TaskState.DOING)

def test_change_state_released_version(session):
    """Change state of a task in a released version raises a ValidationError
    Given a done task in a released version
    When reopening it through a state change
    Then a validation error is raised and the task stays done
    """
    task = _planned_task(session)
    version = versions.list(session, "nexus")[0]
    versions.start(session, version.id)
    tasks.start(session, task.id)
    tasks.complete(session, task.id)
    versions.set_criterion_done(session, version.definition_of_done[0].id, True)
    versions.release(session, version.id)
    with pytest.raises(ValidationError):
        tasks.change_state(session, task.id, TaskState.DOING)
    assert tasks.get(session, task.id).state is TaskState.DONE


# Cancel and restore ----------------------------------------------------------------------------

@pytest.mark.parametrize("prepare", [
    lambda session, task: None,
    lambda session, task: tasks.start(session, task.id),
    lambda session, task: (tasks.start(session, task.id), tasks.block(session, task.id, "Review")),
])
def test_cancel_open_task_in_a_version(session, prepare):
    """Cancel a planned, doing or waiting task cancels it and keeps its version
    Given a task planned in a version, possibly started or blocked
    When cancelling it
    Then the task is cancelled, closed, unblocked, and still in the version
    """
    task = _planned_task(session)
    prepare(session, task)
    cancelled = tasks.cancel(session, task.id)
    assert cancelled.state is TaskState.CANCELLED
    assert cancelled.closed_at is not None
    assert cancelled.blocked_reason is None
    assert cancelled.version_id == task.version_id

def test_cancel_inbox_task(session):
    """Cancel a captured task cancels it
    Given a task in the inbox
    When cancelling it
    Then the task is cancelled and the event log records the previous state
    """
    task = tasks.capture(session, "Write the docs")
    tasks.cancel(session, task.id)
    assert _history(session, task.id)[-1] == ("cancelled", {"from": "INBOX", "to": "CANCELLED"})

def test_cancel_done_or_cancelled_task(session):
    """Cancel a done or an already cancelled task raises an InvalidTransitionError
    Given a done task and a cancelled task
    When cancelling each
    Then an invalid transition error is raised
    """
    done = _planned_task(session)
    tasks.start(session, done.id)
    tasks.complete(session, done.id)
    cancelled = tasks.capture(session, "Other")
    tasks.cancel(session, cancelled.id)
    for task in (done, cancelled):
        with pytest.raises(InvalidTransitionError):
            tasks.cancel(session, task.id)

def test_cancel_not_found(session):
    """Cancel a non existing task raises a NotFoundError
    Given no task with id 1
    When cancelling task 1
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        tasks.cancel(session, 1)

def test_change_state_to_cancelled(session):
    """Change state to cancelled cancels the task
    Given a planned task
    When moving it to cancelled
    Then the task is cancelled
    """
    task = _planned_task(session)
    assert tasks.change_state(session, task.id, TaskState.CANCELLED).state is TaskState.CANCELLED

def test_restore_cancelled_task(session):
    """Restore a cancelled task brings it back to refined, out of its version
    Given a task cancelled while planned in a version
    When restoring it
    Then the task is refined, has no version and is no longer closed
    """
    task = _planned_task(session)
    tasks.cancel(session, task.id)
    restored = tasks.restore(session, task.id)
    assert restored.state is TaskState.REFINED
    assert restored.version_id is None
    assert restored.closed_at is None
    assert _history(session, task.id)[-1] == ("restored", {"from": "CANCELLED", "to": "REFINED"})

def test_restore_not_cancelled(session):
    """Restore a task that isn't cancelled raises an InvalidTransitionError
    Given an inbox task
    When restoring it
    Then an invalid transition error is raised
    """
    task = tasks.capture(session, "Write the docs")
    with pytest.raises(InvalidTransitionError):
        tasks.restore(session, task.id)


# Move to version ------------------------------------------------------------------------------

def test_move_to_version_changes_only_the_version(session):
    """Move a planned task to another version keeps its state
    Given a task planned in 0.1.0 and a second version 0.2.0
    When moving the task to 0.2.0
    Then the task is in 0.2.0, still planned, and the event log records both versions
    """
    task = _planned_task(session)
    first_version_id = task.version_id
    other = versions.create(session, "nexus", "0.2.0", "Second version", ["Ships"])
    moved = tasks.move_to_version(session, task.id, other.id)
    assert moved.version_id == other.id
    assert moved.state is TaskState.PLANNED
    assert _history(session, task.id)[-1] == (
        "moved",
        {"from": "PLANNED", "to": "PLANNED", "from_version_id": first_version_id, "version_id": other.id},
    )

@pytest.mark.parametrize("state", [TaskState.DOING, TaskState.WAITING])
def test_move_to_version_started_task(session, state):
    """Move a doing or waiting task keeps its state
    Given a doing or waiting task and a second version
    When moving the task to the second version
    Then the task is in the second version with the same state
    """
    task = _planned_task(session)
    tasks.start(session, task.id)
    if state is TaskState.WAITING:
        tasks.block(session, task.id, "Review")
    other = versions.create(session, "nexus", "0.2.0", "Second version", ["Ships"])
    assert tasks.move_to_version(session, task.id, other.id).state is state

def test_move_to_version_not_movable_state(session):
    """Move a done or refined task raises an InvalidTransitionError
    Given a refined task
    When moving it to a version
    Then an invalid transition error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    task = _refined_task(session)
    with pytest.raises(InvalidTransitionError):
        tasks.move_to_version(session, task.id, version.id)

def test_move_to_version_same_version(session):
    """Move a task to the version it is already in raises a ValidationError
    Given a task planned in 0.1.0
    When moving it to 0.1.0
    Then a validation error is raised
    """
    task = _planned_task(session)
    with pytest.raises(ValidationError):
        tasks.move_to_version(session, task.id, task.version_id)

def test_move_to_version_other_project(session):
    """Move a task to a version of another project raises a ValidationError
    Given a task planned in project 'nexus' and a version of project 'other'
    When moving the task to that version
    Then a validation error is raised and the task stays put
    """
    task = _planned_task(session)
    projects.create(session, "other", "Other", "")
    foreign = versions.create(session, "other", "0.1.0", "Foreign version", ["Ships"])
    with pytest.raises(ValidationError):
        tasks.move_to_version(session, task.id, foreign.id)
    assert tasks.get(session, task.id).version_id == task.version_id

def test_move_to_version_released_target(session):
    """Move a task to a released version raises a ValidationError
    Given a task planned in 0.2.0 and a released version 0.1.0
    When moving the task to 0.1.0
    Then a validation error is raised
    """
    released = _released_version(session)
    open_version = versions.create(session, "nexus", "0.2.0", "Second version", ["Ships"])
    task = tasks.create_in_version(session, open_version.id, "Write the docs")
    with pytest.raises(ValidationError):
        tasks.move_to_version(session, task.id, released.id)

def test_move_to_version_not_found(session):
    """Move a non existing task, or to a non existing version, raises a NotFoundError
    Given no task and a planned task
    When moving task 1, then moving the planned task to version 99
    Then a not found error is raised each time
    """
    with pytest.raises(NotFoundError):
        tasks.move_to_version(session, 1, 1)
    task = _planned_task(session)
    with pytest.raises(NotFoundError):
        tasks.move_to_version(session, task.id, 99)
