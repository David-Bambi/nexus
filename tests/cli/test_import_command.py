import io
import json

import pytest

from src.cli.main import EXIT_ERROR, EXIT_OK, EXIT_USAGE, main
from src.services import events, projects, tasks


@pytest.fixture
def run(session):
    """Run `nexus` on the test session; returns (exit code, stdout, stderr)."""
    def _run(*argv):
        out, err = io.StringIO(), io.StringIO()
        code = main(list(argv), session_factory=lambda: session, out=out, err=err)
        return code, out.getvalue(), err.getvalue()
    return _run


@pytest.fixture
def document(tmp_path):
    """A small import file; returns its path."""
    path = tmp_path / "import.json"
    path.write_text(json.dumps({"projects": [{"key": "nx", "name": "Nexus"}],
                                "tasks": [{"title": "From file", "project": "nx"}]}))
    return str(path)


def test_import_file_creates_and_lists_refs(run, session, document):
    """
    Given an import file
    When running `nexus import <file>`
    Then the data is created by the cli actor and the created refs are listed
    """
    code, out, _ = run("import", document)
    (task,) = tasks.list(session)
    assert code == EXIT_OK and "Created 1 project(s), 1 feature(s) and task(s)" in out and task.ref in out
    assert events.history(session, "task", task.id)[0].actor == events.ACTOR_CLI


def test_import_dry_run_writes_nothing(run, session, document):
    """
    Given an import file
    When running with --dry-run
    Then the summary says what would be created and nothing is stored
    """
    code, out, _ = run("import", document, "--dry-run")
    assert code == EXIT_OK and out.startswith("Would create 1 project(s)")
    assert tasks.list(session) == [] and projects.list(session) == []


def test_import_from_stdin_and_text_mode(run, session, monkeypatch):
    """
    Given a plain list on stdin
    When running `nexus import - --text`
    Then each line becomes an inbox task
    """
    monkeypatch.setattr("sys.stdin", io.StringIO("Buy milk\n\nCall bank\n"))
    assert run("import", "-", "--text")[0] == EXIT_OK
    assert [t.title for t in tasks.list(session)] == ["Buy milk", "Call bank"]


def test_import_json_from_stdin(run, session, monkeypatch):
    """
    Given a JSON document on stdin
    When running `nexus import -`
    Then it is imported
    """
    monkeypatch.setattr("sys.stdin", io.StringIO('{"tasks": [{"title": "Piped"}]}'))
    assert run("import", "-")[0] == EXIT_OK and _titles(session) == ["Piped"]


def _titles(session):
    return [t.title for t in tasks.list(session)]


def test_invalid_document_lists_problems_and_exits_1(run, session, tmp_path):
    """
    Given a document with problems
    When importing it
    Then every problem goes to stderr, exit code 1, nothing stored
    """
    path = tmp_path / "bad.json"
    path.write_text('{"tasks": [{"title": ""}, {"title": "x", "size": "XXL"}]}')
    code, out, err = run("import", str(path))
    assert (code, out) == (EXIT_ERROR, "") and "2 problem(s)" in err and "tasks[1]" in err
    assert tasks.list(session) == []


def test_broken_json_exits_1(run, tmp_path):
    """
    Given a file that is not JSON
    When importing it
    Then the error says so, with exit code 1
    """
    path = tmp_path / "bad.json"
    path.write_text("{nope")
    code, _, err = run("import", str(path))
    assert code == EXIT_ERROR and "invalid JSON" in err


@pytest.mark.parametrize("argv", [["import"], ["import", "/no/such/file.json"], ["import", "a", "b"]])
def test_usage_errors(run, argv):
    """
    Given a missing argument, an unreadable file or a stray argument
    When running `nexus import`
    Then it is a usage error with exit code 2
    """
    assert run(*argv)[0] == EXIT_USAGE


# Export -------------------------------------------------------------------------------------------

def test_export_features_to_stdout_and_to_a_file(session, tmp_path):
    """
    Given a feature
    When running `nexus export features`, then with -o
    Then the JSON export goes to stdout, then to the file with a short confirmation
    """
    import io
    import json

    from src.cli.main import EXIT_OK, main
    from src.models.task import TaskKind
    from src.services import projects, tasks

    projects.create(session, "nx", "Nexus")
    tasks.add_to_tree(session, "Auth", project_key="nx", kind=TaskKind.FEATURE, refined=True)

    def run(*argv):
        out, err = io.StringIO(), io.StringIO()
        code = main(list(argv), session_factory=lambda: session, out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    code, out, _ = run("export", "features")
    data = json.loads(out)
    assert code == EXIT_OK and data["schema"] == "nexus.features/1"
    assert [f["title"] for f in data["features"]] == ["Auth"]

    target = tmp_path / "features.json"
    code, out, _ = run("export", "features", "-o", str(target))
    assert code == EXIT_OK and "Exported 1 feature(s)" in out
    assert json.loads(target.read_text())["features"][0]["title"] == "Auth"


def test_export_with_a_wrong_command_line_is_a_usage_error(session, tmp_path):
    """An unknown export, or an unwritable file, is a usage error."""
    import io

    from src.cli.main import EXIT_USAGE, main

    def code(*argv):
        return main(list(argv), session_factory=lambda: session, out=io.StringIO(), err=io.StringIO())

    assert code("export") == EXIT_USAGE
    assert code("export", "tasks") == EXIT_USAGE
    assert code("export", "features", "-o", str(tmp_path / "missing" / "f.json")) == EXIT_USAGE
