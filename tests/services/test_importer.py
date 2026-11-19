import copy

import pytest

from src.models.task import TaskState
from src.services import events, importer, projects, tasks
from src.services.errors import ValidationError

DOCUMENT = {
    "projects": [{"key": "nx", "name": "Nexus", "description": "The manager"}],
    "tasks": [
        {"title": "Loose"},
        {"title": "In project", "project": "nx", "size": "S", "context": "@ordi", "body": "Detail"},
    ],
}


def _apply(session, data, **kwargs):
    """Apply a document as the cli actor."""
    return importer.apply(session, copy.deepcopy(data), events.ACTOR_CLI, **kwargs)


def _titles(session):
    """Titles of every task, oldest first."""
    return [t.title for t in tasks.list(session)]


def test_import_creates_everything(session):
    """
    Given a document with a project and tasks
    When importing it
    Then all of them are created in the inbox, in their project if they name one
    """
    result = _apply(session, DOCUMENT)
    assert (result.projects_created, result.tasks_created) == (1, 2)
    assert projects.get(session, "nx").description == "The manager"
    by_title = {t.title: t for t in tasks.list(session)}
    assert by_title["Loose"].project_id is None and by_title["Loose"].state == TaskState.INBOX
    in_project = by_title["In project"]
    assert in_project.project.key == "nx" and in_project.state == TaskState.INBOX
    assert (in_project.size, in_project.context, in_project.body) == ("S", "@ordi", "Detail")


def test_import_reports_created_refs_and_actor(session):
    """
    Given a document
    When importing it
    Then the result lists refs of created tasks, and events carry the actor
    """
    result = _apply(session, DOCUMENT)
    assert [kind for kind, _, _ in result.created] == ["task", "task"]
    task = tasks.get_by_ref(session, result.created[0][1])
    assert events.history(session, "task", task.id)[0].actor == events.ACTOR_CLI


def test_import_reuses_existing_project_without_overwriting(session):
    """
    Given an existing project
    When importing a document naming it with other values
    Then it is reused unchanged, and the tasks are added
    """
    projects.create(session, "nx", "Original", "Keep me")
    result = _apply(session, DOCUMENT)
    assert (result.projects_created, result.projects_reused) == (0, 1)
    assert projects.get(session, "nx").name == "Original"
    assert "In project" in _titles(session)


def test_import_twice_duplicates_tasks_only(session):
    """
    Given a document imported once
    When importing it again
    Then the project is reused and the tasks are created again
    """
    _apply(session, DOCUMENT)
    result = _apply(session, DOCUMENT)
    assert (result.projects_created, result.tasks_created) == (0, 2)
    assert len(tasks.list(session)) == 4


def test_dry_run_writes_nothing_and_hides_refs(session):
    """
    Given a document
    When importing with dry_run
    Then the counts are reported, nothing is stored and refs are None
    """
    result = _apply(session, DOCUMENT, dry_run=True)
    assert result.dry_run and result.tasks_created == 2
    assert all(ref is None for _, ref, _ in result.created)
    assert tasks.list(session) == [] and projects.list(session) == []


def test_invalid_document_reports_every_problem_and_writes_nothing(session):
    """
    Given a document with several problems
    When importing it
    Then all of them are reported and nothing is stored
    """
    data = {
        "projects": [{"key": "tasks", "name": "Reserved"},
                     {"key": "ok", "name": "Ok", "versions": []},
                     {"key": "ok", "name": "Twice"}],
        "tasks": [{"title": " "}, {"title": "x", "size": "XXL"},
                  {"title": "z", "project": "ghost"}, {"title": "w", "project": "ok", "version": "9"},
                  {"title": "v", "bogus": 1}],
        "extra": 1,
    }
    with pytest.raises(importer.ImportInvalid) as raised:
        _apply(session, data)
    text = "\n".join(raised.value.errors)
    for expected in ("key is reserved", "unknown field 'versions'", "project declared twice",
                     "'title' is required", "'size' must be one of", "project 'ghost' doesn't exist",
                     "unknown field 'version'", "unknown field 'bogus'", "unknown field 'extra'"):
        assert expected in text
    assert projects.list(session) == [] and tasks.list(session) == []


@pytest.mark.parametrize("data", [[], "text", None, {"projects": "x"}, {"projects": ["x"]},
                                  {"projects": [{"key": 1}]}, {"tasks": [{"title": 3}]}])
def test_wrong_shapes_are_reported_not_raised(session, data):
    """
    Given a document of the wrong shape or types
    When validating it
    Then problems are returned instead of an unexpected exception
    """
    assert importer.validate(session, data)


def test_failure_midway_rolls_everything_back(session, monkeypatch):
    """
    Given a service failing on the third task
    When importing
    Then the error propagates and nothing at all is stored
    """
    real = tasks.create
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            raise ValidationError("boom")
        return real(*args, **kwargs)

    monkeypatch.setattr(tasks, "create", flaky)
    with pytest.raises(ValidationError, match="boom"):
        _apply(session, {"projects": [{"key": "nx", "name": "Nexus"}],
                         "tasks": [{"title": "a"}, {"title": "b"}, {"title": "c"}]})
    assert tasks.list(session) == [] and projects.list(session) == []


def test_parse_text_makes_one_inbox_task_per_line():
    """
    Given text with blank lines and padding
    When parsing it
    Then each non-blank line becomes a loose task
    """
    assert importer.parse_text("  a \n\n b\n") == {"tasks": [{"title": "a"}, {"title": "b"}]}


def test_values_are_stripped(session):
    """
    Given padded titles and keys
    When importing
    Then the stored values are stripped
    """
    _apply(session, {"projects": [{"key": " nx ", "name": " Nexus "}], "tasks": [{"title": " t ", "project": " nx "}]})
    assert projects.get(session, "nx").name == "Nexus" and _titles(session) == ["t"]
