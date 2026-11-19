import io

import pytest

from src.cli import commands, format as fmt
from src.cli.main import EXIT_ERROR, EXIT_OK, EXIT_USAGE, main
from src.models.task import TaskKind
from src.services.resolve import resolve
from src.services import projects, tasks
from src.services.errors import NotFoundError, ValidationError


@pytest.fixture
def run(session):
    """Run `nexus` on the test session; returns (exit code, stdout, stderr)."""
    def _run(*argv):
        out, err = io.StringIO(), io.StringIO()
        code = main(list(argv), session_factory=lambda: session, out=out, err=err)
        return code, out.getvalue(), err.getvalue()
    return _run


@pytest.fixture
def data(session):
    """A project with a subproject, a feature and a task under it, and a loose task."""
    projects.create(session, "nx", "Nexus", "")
    sub = projects.create(session, "v2", "Nexus 2", parent_key="nx")
    feature = tasks.create(session, "Tree", "nx", kind=TaskKind.FEATURE)
    planned = tasks.create(session, "Planned", parent_ref=feature.ref)
    loose = tasks.capture(session, "Loose")
    return sub, planned, loose


# Resolution ----------------------------------------------------------------------------------------

def test_resolve_project_key_subproject_ref_and_task_ref(session, data):
    """
    Given a project, a subproject and tasks
    When resolving their key and refs
    Then each resolves to its own kind
    """
    sub, planned, _ = data
    assert resolve(session, "nx").kind == "project"
    assert resolve(session, planned.ref).entity is planned
    assert resolve(session, sub.ref.upper()).entity is sub


def test_resolve_unknown_raises(session):
    """
    Given an empty database
    When resolving unknown project key and refs
    Then a not-found error is raised each time
    """
    for reference in ("nope", "t-zzz", "f-zzz", "s-zzz"):
        with pytest.raises(NotFoundError):
            resolve(session, reference)


# Reserved keys -------------------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["tasks", "Add", "import", "t-4k2", "f-abc", "s-abc"])
def test_reserved_project_keys_are_refused(session, key):
    """
    Given a word the CLI reads as a command, or a ref-shaped string
    When creating a project with it as key
    Then a validation error is raised
    """
    with pytest.raises(ValidationError):
        projects.create(session, key, "Name", "")


# Dispatch and exit codes ---------------------------------------------------------------------------

def test_no_arguments_prints_usage(run):
    """
    Given no arguments
    When running nexus
    Then the usage is printed and the exit code is 0
    """
    code, out, _ = run()
    assert code == EXIT_OK and out.startswith("usage: nexus")


def test_unknown_reference_is_a_domain_error(run):
    """
    Given an unknown reference
    When running nexus with it
    Then the message goes to stderr with exit code 1
    """
    code, out, err = run("nope")
    assert (code, out) == (EXIT_ERROR, "")
    assert err.strip() == "error: Project 'nope' doesn't exist."


def test_registered_command_receives_its_arguments(run, monkeypatch):
    """
    Given a registered command
    When running nexus with its word and arguments
    Then the command gets the arguments after the word
    """
    seen = []
    monkeypatch.setitem(commands.COMMANDS, "hello",
                        lambda session, args, out: (seen.append(args), out.write("hi\n")))
    code, out, _ = run("hello", "a", "b")
    assert (code, out, seen) == (EXIT_OK, "hi\n", [["a", "b"]])


def test_viewer_receives_the_resolved_target(run, data, monkeypatch):
    """
    Given a registered task viewer
    When running nexus with a task ref
    Then the viewer gets the resolved task
    """
    _, planned, _ = data
    monkeypatch.setitem(commands.VIEWERS, "task",
                        lambda session, target, args, out: out.write(target.entity.title + "\n"))
    assert run(planned.ref)[:2] == (EXIT_OK, "Planned\n")


def test_kind_without_viewer_is_a_usage_error(run, data, monkeypatch):
    """
    Given a reference whose kind has no viewer
    When running nexus
    Then it is a usage error with exit code 2
    """
    _, planned, _ = data
    monkeypatch.setattr(commands, "VIEWERS", {})
    code, _, err = run(planned.ref)
    assert code == EXIT_USAGE and "cannot show a task" in err


# Formatting ----------------------------------------------------------------------------------------

def test_table_aligns_columns():
    """
    Given headers and rows of different widths
    When formatting a table
    Then columns are padded to the widest cell, with no trailing spaces
    """
    text = fmt.table(["REF", "TITLE"], [["t-abc", "Short"], ["t-defgh", "A longer one"]])
    assert text.splitlines() == ["REF      TITLE", "t-abc    Short", "t-defgh  A longer one"]


def test_table_without_rows_says_none():
    """
    Given no rows
    When formatting a table
    Then "(none)" is returned
    """
    assert fmt.table(["REF"], []) == "(none)"


def test_detail_skips_empty_values_and_aligns():
    """
    Given fields, some empty
    When formatting a detail block
    Then empty fields are left out and values line up
    """
    text = fmt.detail([("Ref", "t-abc"), ("Context", None), ("State", "INBOX")])
    assert text.splitlines() == ["Ref    t-abc", "State  INBOX"]
