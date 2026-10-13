import pytest

from src.services import events, projects, tasks, versions
from src.models.version import VersionStatus
from src.models.task import Task, TaskState
from src.services.errors import ConflictError, NotFoundError, ValidationError

# Create ------------------------------------------------------------------------------------------

def test_create_returns_version(session):
    """Create a version returns a version
    Given a project 'nexus'
    When creating a version '0.1.0' with a definition of done
    Then the version is created with that number
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    assert version.id is not None
    assert version.number == "0.1.0"
    assert version.status is VersionStatus.PLANNED

def test_create_project_not_found(session):
    """Create a version under a non existing project raises a NotFoundError
    Given no project with 'nexus' key
    When creating a version under 'nexus'
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])

def test_create_rejects_empty_dod(session):
    """Create a version without a definition of done raises a ValidationError
    Given a project 'nexus'
    When creating a version with an empty definition of done
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    with pytest.raises(ValidationError):
        versions.create(session, "nexus", "0.1.0", "First version", [])

def test_create_rejects_duplicate_number(session):
    """Create a version with a duplicate number raises a ConflictError
    Given a project 'nexus' with version '0.1.0'
    When creating another version '0.1.0' under 'nexus'
    Then a conflict error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    with pytest.raises(ConflictError):
        versions.create(session, "nexus", "0.1.0", "First version again", ["Ships"])


# Get ---------------------------------------------------------------------------------------------

def test_get_version_found(session):
    """Get an existing version returns that version
    Given a project 'nexus' with version '0.1.0'
    When getting version '0.1.0' of 'nexus'
    Then the version is returned
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    version = versions.get(session, "nexus", "0.1.0")
    assert version.number == "0.1.0"

def test_get_version_not_found(session):
    """Get a non existing version raises a NotFoundError
    Given a project 'nexus' without version '0.1.0'
    When getting version '0.1.0' of 'nexus'
    Then a not found error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    with pytest.raises(NotFoundError):
        versions.get(session, "nexus", "0.1.0")

def test_get_version_project_not_found(session):
    """Get a version under a non existing project raises a NotFoundError
    Given no project with 'nexus' key
    When getting version '0.1.0' of 'nexus'
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        versions.get(session, "nexus", "0.1.0")


# List --------------------------------------------------------------------------------------------

def test_list_no_version(session):
    """List a project without versions returns an empty list
    Given a project 'nexus' without versions
    When listing the versions of 'nexus'
    Then the resulting list is empty
    """
    projects.create(session, "nexus", "Nexus", "")
    assert not versions.list(session, "nexus")

def test_list_with_version(session):
    """List a project's versions returns them
    Given a project 'nexus' with version '0.1.0'
    When listing the versions of 'nexus'
    Then the resulting list contains version '0.1.0'
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    version_list = versions.list(session, "nexus")
    assert len(version_list) == 1
    assert version_list[0].number == "0.1.0"


# Start ---------------------------------------------------------------------------------------------

def test_start_planned_version(session):
    """Start a planned version moves it to in progress
    Given a planned version '0.1.0'
    When starting that version
    Then its status is 'IN_PROGRESS'
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    started = versions.start(session, version.id)
    assert started.status is VersionStatus.IN_PROGRESS

def test_start_not_found(session):
    """Start a non existing version raises a NotFoundError
    Given no version with id 1
    When starting version 1
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        versions.start(session, 1)

def test_start_already_started(session):
    """Start an already started version raises a ValidationError
    Given a version already in progress
    When starting that version again
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    with pytest.raises(ValidationError):
        versions.start(session, version.id)


# Release -------------------------------------------------------------------------------------------

def test_release_in_progress_version(session):
    """Release an in progress version with no unfinished tasks releases it
    Given a version in progress with no tasks
    When releasing that version
    Then its status is 'RELEASED' and released_at is set
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    versions.set_criterion_done(session, version.definition_of_done[0].id, True)
    released = versions.release(session, version.id)
    assert released.status is VersionStatus.RELEASED
    assert released.released_at is not None

def test_release_not_found(session):
    """Release a non existing version raises a NotFoundError
    Given no version with id 1
    When releasing version 1
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        versions.release(session, 1)

def test_release_not_in_progress(session):
    """Release a planned version raises a ValidationError
    Given a planned version '0.1.0'
    When releasing that version
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    with pytest.raises(ValidationError):
        versions.release(session, version.id)

def test_release_with_unfinished_tasks(session):
    """Release a version with unfinished tasks raises a ValidationError
    Given a version in progress with an unfinished task
    When releasing that version
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    task = Task(ref="t-tst", title="Write the docs", project_id=version.project_id,
                version_id=version.id, state=TaskState.PLANNED)
    session.add(task)
    session.commit()
    with pytest.raises(ValidationError):
        versions.release(session, version.id)


# Reorder -------------------------------------------------------------------------------------------

def test_reorder_versions(session):
    """Reorder a project's versions updates their position
    Given a project 'nexus' with versions '0.1.0' and '0.2.0'
    When reordering with '0.2.0' before '0.1.0'
    Then '0.2.0' has position 0 and '0.1.0' has position 1, and listing follows that order
    """
    projects.create(session, "nexus", "Nexus", "")
    v1 = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    v2 = versions.create(session, "nexus", "0.2.0", "Second version", ["Ships"])
    versions.reorder(session, "nexus", [v2.id, v1.id])
    assert v2.position == 0
    assert v1.position == 1
    assert versions.list(session, "nexus") == [v2, v1]

def test_reorder_project_not_found(session):
    """Reorder versions of a non existing project raises a NotFoundError
    Given no project with 'nexus' key
    When reordering versions of 'nexus'
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        versions.reorder(session, "nexus", [])

def test_reorder_mismatched_ids(session):
    """Reorder with ids not matching the project's versions raises a ValidationError
    Given a project 'nexus' with version '0.1.0'
    When reordering with an id that doesn't belong to 'nexus'
    Then a validation error is raised
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    with pytest.raises(ValidationError):
        versions.reorder(session, "nexus", [999])


# Events ------------------------------------------------------------------------------------------

def _history(session, version_id):
    """Return a version's logged (action, payload) pairs, oldest first."""
    return [(e.action, e.payload) for e in events.history(session, "version", version_id)]

def test_create_logs_created(session):
    """Create logs a created event
    Given a project 'nexus'
    When creating version '0.1.0'
    Then its history holds a created event carrying number and title
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])

    assert _history(session, version.id) == [
        ("created", {"number": "0.1.0", "title": "First version"})]

def test_create_conflict_logs_nothing(session):
    """A refused create logs no event
    Given a project with version '0.1.0'
    When creating '0.1.0' again
    Then a conflict error is raised and only one created event exists for versions
    """
    projects.create(session, "nexus", "Nexus", "")
    versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    with pytest.raises(ConflictError):
        versions.create(session, "nexus", "0.1.0", "Duplicate", ["Ships"])

    assert session.query(events.Event).filter_by(entity_type="version").count() == 1

def test_start_and_release_log_events(session):
    """Start and release log their status change
    Given a version with no tasks
    When starting then releasing it
    Then its history shows both status changes, in order
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    versions.set_criterion_done(session, version.definition_of_done[0].id, True)
    versions.release(session, version.id)

    assert _history(session, version.id)[1:] == [
        ("started", {"from": "PLANNED", "to": "IN_PROGRESS"}),
        ("dod_checked", {"criterion_id": version.definition_of_done[0].id, "description": "Ships"}),
        ("released", {"from": "IN_PROGRESS", "to": "RELEASED"}),
    ]

def test_refused_release_logs_nothing(session):
    """A refused release logs no event
    Given a started version with an unfinished task
    When releasing it
    Then a validation error is raised and no released event exists
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    task = tasks.capture(session, "Write the docs")
    tasks.clarify(session, task.id, "Write the docs", None, None, None, None)
    tasks.plan(session, task.id, version.id)
    with pytest.raises(ValidationError):
        versions.release(session, version.id)

    assert "released" not in [action for action, _ in _history(session, version.id)]

def test_reorder_logs_on_project(session):
    """Reorder logs a versions_reordered event on the project
    Given a project with two versions
    When reordering them
    Then the project's history holds the new order
    """
    project = projects.create(session, "nexus", "Nexus", "")
    first = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    second = versions.create(session, "nexus", "0.2.0", "Second version", ["Ships"])
    versions.reorder(session, "nexus", [second.id, first.id])

    history = events.history(session, "project", project.id)
    assert (history[-1].action, history[-1].payload) == (
        "versions_reordered", {"ordered_ids": [second.id, first.id]})


# Definition of done ------------------------------------------------------------------------------

def _version_with_dod(session, *dod):
    """Create project 'nexus' with a version '0.1.0' holding the given criteria."""
    projects.create(session, "nexus", "Nexus", "")
    return versions.create(session, "nexus", "0.1.0", "First version", list(dod))

def _released_version(session):
    """Create a released version '0.1.0' with one checked criterion."""
    version = _version_with_dod(session, "Ships")
    versions.start(session, version.id)
    versions.set_criterion_done(session, version.definition_of_done[0].id, True)
    versions.release(session, version.id)
    return version

def test_add_criterion_appends_unchecked(session):
    """Add a criterion appends it, unchecked, after the existing ones
    Given a version with criteria 'Ships' and 'Docs'
    When adding the criterion 'Tests'
    Then it is last, unchecked, and the description is stripped
    """
    version = _version_with_dod(session, "Ships", "Docs")
    criterion = versions.add_criterion(session, version.id, "  Tests ")
    assert [c.description for c in version.definition_of_done] == ["Ships", "Docs", "Tests"]
    assert criterion.position == 2
    assert criterion.done is False

def test_add_criterion_rejects_empty_description(session):
    """Add a blank criterion raises a ValidationError
    Given a version
    When adding a criterion with a blank description
    Then a validation error is raised
    """
    version = _version_with_dod(session, "Ships")
    with pytest.raises(ValidationError):
        versions.add_criterion(session, version.id, "   ")

def test_add_criterion_version_not_found(session):
    """Add a criterion to a non existing version raises a NotFoundError
    Given no version
    When adding a criterion to version 1
    Then a not found error is raised
    """
    with pytest.raises(NotFoundError):
        versions.add_criterion(session, 1, "Tests")

def test_update_criterion_changes_description(session):
    """Update a criterion changes its description
    Given a version with criterion 'Ships'
    When updating it to 'Ships to prod'
    Then the criterion has the new description
    """
    version = _version_with_dod(session, "Ships")
    criterion = versions.update_criterion(session, version.definition_of_done[0].id, "Ships to prod")
    assert criterion.description == "Ships to prod"

def test_update_criterion_rejects_empty_description(session):
    """Update a criterion to a blank description raises a ValidationError
    Given a version with criterion 'Ships'
    When updating it to a blank description
    Then a validation error is raised
    """
    version = _version_with_dod(session, "Ships")
    with pytest.raises(ValidationError):
        versions.update_criterion(session, version.definition_of_done[0].id, " ")

def test_delete_criterion_removes_it(session):
    """Delete a criterion removes it from the version
    Given a version with criteria 'Ships' and 'Docs'
    When deleting 'Ships'
    Then only 'Docs' remains
    """
    version = _version_with_dod(session, "Ships", "Docs")
    versions.delete_criterion(session, version.definition_of_done[0].id)
    assert [c.description for c in version.definition_of_done] == ["Docs"]

def test_delete_last_criterion_rejected(session):
    """Delete the last criterion raises a ValidationError
    Given a version with a single criterion
    When deleting it
    Then a validation error is raised and the criterion remains
    """
    version = _version_with_dod(session, "Ships")
    with pytest.raises(ValidationError):
        versions.delete_criterion(session, version.definition_of_done[0].id)
    assert len(version.definition_of_done) == 1

def test_set_criterion_done_checks_and_unchecks(session):
    """Set a criterion done toggles its state
    Given a version with an unchecked criterion
    When checking it, then unchecking it
    Then its done flag follows
    """
    version = _version_with_dod(session, "Ships")
    criterion_id = version.definition_of_done[0].id
    assert versions.set_criterion_done(session, criterion_id, True).done is True
    assert versions.set_criterion_done(session, criterion_id, False).done is False

def test_criterion_not_found(session):
    """Mutating a non existing criterion raises a NotFoundError
    Given no criterion
    When updating, deleting or checking criterion 1
    Then a not found error is raised each time
    """
    with pytest.raises(NotFoundError):
        versions.update_criterion(session, 1, "x")
    with pytest.raises(NotFoundError):
        versions.delete_criterion(session, 1)
    with pytest.raises(NotFoundError):
        versions.set_criterion_done(session, 1, True)

def test_released_version_dod_is_frozen(session):
    """Every DOD mutation on a released version raises a ConflictError
    Given a released version
    When adding, updating, deleting or unchecking a criterion
    Then a conflict error is raised each time
    """
    version = _released_version(session)
    criterion_id = version.definition_of_done[0].id
    with pytest.raises(ConflictError):
        versions.add_criterion(session, version.id, "Tests")
    with pytest.raises(ConflictError):
        versions.update_criterion(session, criterion_id, "Other")
    with pytest.raises(ConflictError):
        versions.delete_criterion(session, criterion_id)
    with pytest.raises(ConflictError):
        versions.set_criterion_done(session, criterion_id, False)

def test_release_with_unchecked_criterion(session):
    """Release a version with an unchecked criterion raises a ValidationError
    Given a version in progress with one checked and one unchecked criterion
    When releasing it
    Then a validation error is raised and the version stays in progress
    """
    version = _version_with_dod(session, "Ships", "Docs")
    versions.start(session, version.id)
    versions.set_criterion_done(session, version.definition_of_done[0].id, True)
    with pytest.raises(ValidationError):
        versions.release(session, version.id)
    assert version.status is VersionStatus.IN_PROGRESS

def test_dod_mutations_log_events(session):
    """DOD mutations log events on the version
    Given a version with criterion 'Ships'
    When adding 'Docs', renaming it, checking it, unchecking it, then deleting it
    Then the history shows each mutation in order
    """
    version = _version_with_dod(session, "Ships")
    docs = versions.add_criterion(session, version.id, "Docs")
    versions.update_criterion(session, docs.id, "Docs v2")
    versions.set_criterion_done(session, docs.id, True)
    versions.set_criterion_done(session, docs.id, False)
    versions.delete_criterion(session, docs.id)

    assert [action for action, _ in _history(session, version.id)[1:]] == [
        "dod_added", "dod_updated", "dod_checked", "dod_unchecked", "dod_deleted",
    ]

def test_set_criterion_done_unchanged_logs_nothing(session):
    """Setting a criterion to its current state logs no event
    Given a version with an unchecked criterion
    When setting it to not done
    Then no dod event exists
    """
    version = _version_with_dod(session, "Ships")
    versions.set_criterion_done(session, version.definition_of_done[0].id, False)
    assert [action for action, _ in _history(session, version.id)] == ["created"]


def test_release_ignores_cancelled_tasks(session):
    """Release a version whose only open task was cancelled releases it
    Given a version in progress with a cancelled task and a done task
    When releasing that version
    Then the version is released
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First version", ["Ships"])
    versions.start(session, version.id)
    versions.set_criterion_done(session, version.definition_of_done[0].id, True)
    dropped = tasks.create_in_version(session, version.id, "Dropped")
    tasks.cancel(session, dropped.id)
    assert versions.release(session, version.id).status is VersionStatus.RELEASED


# Delete ------------------------------------------------------------------------------------------

def _task_in(session, version, title, state):
    """Create a task in a version and move it to the given state."""
    task = tasks.create_in_version(session, version.id, title)
    if state in (TaskState.DOING, TaskState.WAITING, TaskState.DONE):
        tasks.start(session, task.id)
    if state == TaskState.WAITING:
        tasks.block(session, task.id, "why")
    if state == TaskState.DONE:
        tasks.complete(session, task.id)
    if state == TaskState.CANCELLED:
        tasks.cancel(session, task.id)
    return task


def test_delete_version_sends_unfinished_tasks_back_to_refined(session):
    """Deleting a version keeps its tasks, sending the unfinished ones back to refined
    Given a version with a planned, a doing, a waiting, a done and a cancelled task
    When deleting the version
    Then it and its criteria are gone, the first three are refined without a version or block reason,
    and the done and cancelled ones keep their state without a version
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First", ["Ships", "Docs"])
    versions.start(session, version.id)
    states = [TaskState.PLANNED, TaskState.DOING, TaskState.WAITING, TaskState.DONE, TaskState.CANCELLED]
    created = [_task_in(session, version, s.name, s) for s in states]
    version_id = version.id

    versions.delete(session, version_id)

    with pytest.raises(NotFoundError):
        versions.get(session, "nexus", "0.1.0")
    assert versions.list(session, "nexus") == []
    assert [(t.state, t.version_id, t.blocked_reason) for t in created] == [
        (TaskState.REFINED, None, None), (TaskState.REFINED, None, None), (TaskState.REFINED, None, None),
        (TaskState.DONE, None, None), (TaskState.CANCELLED, None, None)]
    assert session.query(Task).count() == 5


def test_delete_version_logs_the_deletion_and_each_unplanned_task(session):
    """Deleting a version logs it, plus an unplanned event per task sent back to refined
    Given a version with a doing and a done task
    When deleting it as the cli
    Then the version has a deleted event, the doing task an unplanned one, the done task none, all by the cli
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First", ["Ships"])
    doing = _task_in(session, version, "Doing", TaskState.DOING)
    done = _task_in(session, version, "Done", TaskState.DONE)
    version_id, ref = version.id, version.ref
    done_events = len(events.history(session, "task", done.id))

    versions.delete(session, version_id, actor=events.ACTOR_CLI)

    deleted = events.history(session, "version", version_id)[-1]
    assert (deleted.action, deleted.actor) == ("deleted", events.ACTOR_CLI)
    assert deleted.payload == {"project": "nexus", "number": "0.1.0", "title": "First"}
    unplanned = events.history(session, "task", doing.id)[-1]
    assert (unplanned.action, unplanned.actor) == ("unplanned", events.ACTOR_CLI)
    assert unplanned.payload == {"from": "DOING", "to": "REFINED", "version": ref}
    assert len(events.history(session, "task", done.id)) == done_events


def test_delete_released_version_is_allowed(session):
    """A released version can be deleted too
    Given a released version with a done task
    When deleting it
    Then it is gone and the task stays done
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First", ["Ships"])
    versions.start(session, version.id)
    done = _task_in(session, version, "Done", TaskState.DONE)
    versions.set_criterion_done(session, version.definition_of_done[0].id, True)
    versions.release(session, version.id)

    versions.delete(session, version.id)

    assert versions.list(session, "nexus") == [] and done.state == TaskState.DONE and done.version_id is None


def test_delete_missing_version_raises(session):
    """Deleting an unknown version is refused
    Given no version
    When deleting id 999
    Then NotFoundError is raised
    """
    with pytest.raises(NotFoundError):
        versions.delete(session, 999)
