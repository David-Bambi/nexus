import copy

import pytest

from src.models.task import TaskKind, TaskState
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


# Tree --------------------------------------------------------------------------------------------

TREE = {"projects": [{
    "key": "metrique", "name": "Métriques",
    "items": [{"title": "Top task", "size": "S"}],
    "subprojects": [{
        "key": "bilan", "name": "Bilan de version",
        "items": [{"kind": "feature", "title": "Collect", "children": [
            {"title": "Read Nexus", "context": "@ordi"},
            {"kind": "feature", "title": "Sessions", "children": [{"title": "Parse JSONL"}]},
        ]}],
    }],
}]}


def test_import_tree_builds_subprojects_features_and_tasks(session):
    """
    Given a document with a project, a subproject and nested features
    When importing it
    Then the whole tree exists, each item refined, in the right place
    """
    result = _apply(session, TREE)
    assert (result.projects_created, result.tasks_created) == (2, 5)
    bilan = projects.get(session, "bilan")
    assert bilan.parent.key == "metrique" and bilan.ref.startswith("s-")
    by_title = {t.title: t for t in tasks.list(session)}
    assert by_title["Top task"].project.key == "metrique" and by_title["Top task"].parent is None
    collect, sessions = by_title["Collect"], by_title["Sessions"]
    assert collect.kind is TaskKind.FEATURE and collect.project is bilan and collect.parent is None
    assert by_title["Read Nexus"].parent is collect and by_title["Read Nexus"].context == "@ordi"
    assert sessions.parent is collect and by_title["Parse JSONL"].parent is sessions
    assert by_title["Parse JSONL"].project is bilan
    assert {t.state for t in by_title.values()} == {TaskState.REFINED}
    assert [kind for kind, _, _ in result.created].count("feature") == 2


def test_import_tree_into_existing_projects(session):
    """
    Given the project and subproject already exist
    When importing the tree
    Then both are reused and only the items are created
    """
    projects.create(session, "metrique", "Original")
    projects.create(session, "bilan", "Original sub", parent_key="metrique")
    result = _apply(session, TREE)
    assert (result.projects_created, result.projects_reused, result.tasks_created) == (0, 2, 5)
    assert projects.get(session, "bilan").name == "Original sub"


def test_import_tree_dry_run_writes_nothing(session):
    """
    Given the tree document
    When importing with dry_run
    Then counts are reported and nothing is stored
    """
    result = _apply(session, TREE, dry_run=True)
    assert result.tasks_created == 5 and tasks.list(session) == [] and projects.list(session) == []


def test_invalid_tree_reports_every_problem(session):
    """
    Given a tree with misplaced children, bad kinds and nested subprojects
    When importing it
    Then each problem is reported and nothing is stored
    """
    projects.create(session, "taken", "Taken")
    data = {"projects": [{
        "key": "p", "name": "P",
        "items": [{"title": "Leaf", "children": [{"title": "x"}]},
                  {"kind": "epic", "title": "Odd"},
                  {"kind": "feature", "title": "F", "children": [{"title": ""}]}],
        "subprojects": [{"key": "s", "name": "S", "subprojects": []},
                        {"key": "taken"}],
    }]}
    with pytest.raises(importer.ImportInvalid) as raised:
        _apply(session, data)
    text = "\n".join(raised.value.errors)
    for expected in ("only a feature can have 'children'", "'kind' must be one of",
                     "children[0]: 'title' is required", "unknown field 'subprojects'",
                     "already exists as a root project"):
        assert expected in text
    assert tasks.list(session) == []


def test_existing_subproject_cant_be_imported_as_a_root_project(session):
    """
    Given a subproject 'bilan' of 'metrique'
    When importing 'bilan' at the top of the document
    Then the document is refused
    """
    projects.create(session, "metrique", "Métriques")
    projects.create(session, "bilan", "Bilan", parent_key="metrique")
    errors = importer.validate(session, {"projects": [{"key": "bilan"}]})
    assert errors == ["projects[0] ('bilan'): already exists as a subproject of 'metrique'"]


# Version and criteria ----------------------------------------------------------------------------

VERSIONED = {"projects": [{
    "key": "metrique", "name": "Metrique", "version": "1.4",
    "criteria": ["Bilan done", {"text": "Docs built", "done": True}],
    "subprojects": [{"key": "bilan", "name": "Bilan", "version": "0.2"}],
}]}


def test_import_sets_version_and_criteria(session):
    """
    Given a document giving projects a version and criteria
    When importing it
    Then each new project has them, in order
    """
    _apply(session, VERSIONED)

    metrique = projects.get(session, "metrique")
    assert (metrique.version_major, metrique.version_minor) == (1, 4)
    assert [(c.text, c.done) for c in metrique.criteria] == [("Bilan done", False), ("Docs built", True)]
    assert (projects.get(session, "bilan").version_minor) == 2


def test_import_version_dry_run_writes_nothing(session):
    """A dry run with versions and criteria writes nothing."""
    _apply(session, VERSIONED, dry_run=True)
    assert projects.list(session) == []


def test_import_version_on_existing_project_is_refused(session):
    """An existing project's version and criteria are never overwritten."""
    projects.create(session, "metrique", "Metrique")
    with pytest.raises(importer.ImportInvalid) as error:
        _apply(session, {"projects": [{"key": "metrique", "version": "2.0", "criteria": ["X"]}]})
    assert error.value.errors == [
        "projects[0] ('metrique'): 'version' can't be set on an existing project",
        "projects[0] ('metrique'): 'criteria' can't be set on an existing project",
    ]


def test_import_invalid_version_and_criteria(session):
    """Every malformed version or criterion is reported."""
    errors = importer.validate(session, {"projects": [{
        "key": "x", "name": "X", "version": "1",
        "criteria": [3, " ", {"text": "", "done": "y", "extra": 1}],
    }]})
    assert errors == [
        "projects[0] ('x'): 'version' must look like '1.4'",
        "projects[0] ('x') criteria[0]: must be a string or an object",
        "projects[0] ('x') criteria[1]: text is required",
        "projects[0] ('x') criteria[2]: unknown field 'extra'",
        "projects[0] ('x') criteria[2]: 'text' is required",
        "projects[0] ('x') criteria[2]: 'done' must be true or false",
    ]
