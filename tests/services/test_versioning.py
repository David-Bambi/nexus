import pytest

from src.models.task import TaskKind
from src.services import events, projects, tasks, versioning
from src.services.errors import ConflictError, NotFoundError, ValidationError


# Helpers -----------------------------------------------------------------------------------------

def _project_actions(session, project):
    """Return a project's logged (action, payload) pairs, oldest first."""
    return [(e.action, e.payload) for e in events.history(session, "project", project.id)]


def _doing(session, title, project_key, kind=TaskKind.TASK, parent_ref=None):
    """Create a work item, clarify it and start it; return it."""
    item = tasks.create(session, title, project_key=None if parent_ref else project_key,
                        parent_ref=parent_ref, kind=kind)
    tasks.clarify(session, item.id, title, None, project_key, None, None, parent_ref=parent_ref)
    return tasks.start(session, item.id)


@pytest.fixture
def nexus(session):
    """A root project 'nexus'."""
    return projects.create(session, "nexus", "Nexus")


# Minor bump --------------------------------------------------------------------------------------

def test_new_project_starts_at_zero(session, nexus):
    """A new project is at version 0.0."""
    assert versioning.label(nexus) == "0.0"


def test_completed_feature_bumps_minor(session, nexus):
    """
    Given a feature being worked on
    When it is completed
    Then MINOR goes up, the feature records its version, and the bump is logged
    """
    feature = _doing(session, "Login", "nexus", kind=TaskKind.FEATURE)
    tasks.complete(session, feature.id)

    assert versioning.label(nexus) == "0.1"
    assert feature.released_in == "0.1"
    assert _project_actions(session, nexus)[-1] == (
        "minor_bumped", {"from": "0.0", "to": "0.1", "feature": feature.ref})


def test_completed_task_leaves_the_version(session, nexus):
    """A completed task doesn't change the version."""
    task = _doing(session, "Fix typo", "nexus")
    tasks.complete(session, task.id)

    assert versioning.label(nexus) == "0.0"
    assert task.released_in is None


def test_cancelled_feature_leaves_the_version(session, nexus):
    """A cancelled feature doesn't change the version."""
    feature = _doing(session, "Login", "nexus", kind=TaskKind.FEATURE)
    tasks.cancel(session, feature.id)

    assert versioning.label(nexus) == "0.0"


def test_reopened_feature_bumps_only_once(session, nexus):
    """
    Given a completed feature
    When it is reopened, then completed again
    Then the version doesn't go down nor up again, and it keeps its version
    """
    feature = _doing(session, "Login", "nexus", kind=TaskKind.FEATURE)
    tasks.complete(session, feature.id)
    tasks.reopen(session, feature.id)
    assert versioning.label(nexus) == "0.1"

    tasks.complete(session, feature.id)
    assert versioning.label(nexus) == "0.1"
    assert feature.released_in == "0.1"


def test_nested_feature_bumps_its_nearest_project(session, nexus):
    """A feature inside another feature bumps the project they belong to."""
    outer = _doing(session, "Auth", "nexus", kind=TaskKind.FEATURE)
    inner = _doing(session, "Login", "nexus", kind=TaskKind.FEATURE, parent_ref=outer.ref)
    tasks.complete(session, inner.id)
    tasks.complete(session, outer.id)

    assert versioning.label(nexus) == "0.2"
    assert (inner.released_in, outer.released_in) == ("0.1", "0.2")


def test_subproject_feature_bumps_only_the_subproject(session, nexus):
    """A feature of a subproject bumps the subproject, not its parent."""
    sub = projects.create(session, "bilan", "Bilan", parent_key="nexus")
    feature = _doing(session, "Collect", "bilan", kind=TaskKind.FEATURE)
    tasks.complete(session, feature.id)

    assert versioning.label(sub) == "0.1"
    assert versioning.label(nexus) == "0.0"


def test_moving_a_done_feature_leaves_both_versions(session, nexus):
    """Moving a completed feature changes neither project's version."""
    other = projects.create(session, "other", "Other")
    feature = _doing(session, "Login", "nexus", kind=TaskKind.FEATURE)
    tasks.complete(session, feature.id)
    tasks.move(session, feature.id, project_key="other")

    assert (versioning.label(nexus), versioning.label(other)) == ("0.1", "0.0")
    assert feature.released_in == "0.1"


# Set version -------------------------------------------------------------------------------------

def test_set_version_logs_the_change(session, nexus):
    """Setting a version directly records it in the event log."""
    versioning.set_version(session, "nexus", 2, 3)

    assert versioning.label(nexus) == "2.3"
    assert _project_actions(session, nexus)[-1] == ("version_set", {"from": "0.0", "to": "2.3"})


def test_set_version_refuses_a_negative_part(session, nexus):
    """A negative version part is refused."""
    with pytest.raises(ValidationError):
        versioning.set_version(session, "nexus", -1, 0)


@pytest.mark.parametrize("text, expected", [
    ("1.4", (1, 4)), (" 0.0 ", (0, 0)), ("12.30", (12, 30)),
    ("1", None), ("1.4.2", None), ("a.b", None), ("-1.0", None), ("", None),
])
def test_parse_label(text, expected):
    """Only two non-negative integers joined by a dot are a version."""
    assert versioning.parse_label(text) == expected


# Criteria ----------------------------------------------------------------------------------------

def _criterion_actions(session, criterion_id):
    """Return a criterion's logged actions, oldest first."""
    return [e.action for e in events.history(session, "criterion", criterion_id)]


def test_criteria_crud_is_ordered_and_logged(session, nexus):
    """
    Given a project
    When criteria are added, edited, checked and deleted
    Then the list keeps its order and every change is logged
    """
    first = versioning.add_criterion(session, "nexus", " Tests green ")
    second = versioning.add_criterion(session, "nexus", "Docs built")
    assert [(c.text, c.position, c.done) for c in nexus.criteria] == [
        ("Tests green", 0, False), ("Docs built", 1, False)]

    versioning.update_criterion(session, first.id, "All tests green")
    versioning.set_criterion_done(session, first.id, True)
    versioning.set_criterion_done(session, first.id, False)
    versioning.delete_criterion(session, second.id)

    assert [(c.text, c.done) for c in nexus.criteria] == [("All tests green", False)]
    assert _criterion_actions(session, first.id) == [
        "criterion_added", "criterion_updated", "criterion_checked", "criterion_checked"]
    assert _criterion_actions(session, second.id) == ["criterion_added", "criterion_deleted"]


def test_criterion_empty_text_is_refused(session, nexus):
    """A criterion needs a text, on creation and on edit."""
    with pytest.raises(ValidationError):
        versioning.add_criterion(session, "nexus", "  ")
    criterion = versioning.add_criterion(session, "nexus", "Tests green")
    with pytest.raises(ValidationError):
        versioning.update_criterion(session, criterion.id, "")


def test_criterion_not_found(session, nexus):
    """An unknown criterion or project is reported."""
    with pytest.raises(NotFoundError):
        versioning.set_criterion_done(session, 999, True)
    with pytest.raises(NotFoundError):
        versioning.add_criterion(session, "missing", "Tests green")


# Major release -----------------------------------------------------------------------------------

def test_major_refused_without_criteria(session, nexus):
    """A major release needs at least one criterion."""
    with pytest.raises(ConflictError):
        versioning.release_major(session, "nexus")


def test_major_refused_with_an_unchecked_criterion(session, nexus):
    """A major release needs every criterion checked."""
    done = versioning.add_criterion(session, "nexus", "Tests green")
    versioning.add_criterion(session, "nexus", "Docs built")
    versioning.set_criterion_done(session, done.id, True)

    with pytest.raises(ConflictError, match="Docs built"):
        versioning.release_major(session, "nexus")
    assert versioning.label(nexus) == "0.0"


def test_major_release(session, nexus):
    """
    Given a project at 0.2 with every criterion checked
    When it moves to its next major version
    Then it is at 1.0, its list is empty and the criteria are kept in the log
    """
    versioning.set_version(session, "nexus", 0, 2)
    criterion = versioning.add_criterion(session, "nexus", "Tests green")
    versioning.set_criterion_done(session, criterion.id, True)

    versioning.release_major(session, "nexus")

    assert versioning.label(nexus) == "1.0"
    assert nexus.criteria == []
    assert _project_actions(session, nexus)[-1] == (
        "major_released", {"from": "0.2", "to": "1.0", "criteria": ["Tests green"]})
