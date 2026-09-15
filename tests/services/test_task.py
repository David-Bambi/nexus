import pytest

from src.services import projects, tasks, versions
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
