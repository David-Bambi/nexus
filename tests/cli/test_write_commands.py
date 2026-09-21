import io

import pytest

from src.cli.main import EXIT_ERROR, EXIT_OK, EXIT_USAGE, main
from src.models.task import TaskState
from src.services import events, projects, tasks, versions


@pytest.fixture
def run(session):
    """Run `nexus` on the test session; returns (exit code, stdout, stderr)."""
    def _run(*argv):
        out, err = io.StringIO(), io.StringIO()
        code = main(list(argv), session_factory=lambda: session, out=out, err=err)
        return code, out.getvalue(), err.getvalue()
    return _run


@pytest.fixture
def version(session):
    """A project with an open version."""
    projects.create(session, "nx", "Nexus", "")
    return versions.create(session, "nx", "0.1.0", "First", ["Ships"])


def _only_task(session):
    """The single task in the database."""
    (task,) = tasks.list(session)
    return task


def test_add_task_to_project_lands_in_inbox(run, session, version):
    """
    Given a project
    When running `nexus add task nx --title ...` with detail options
    Then an inbox task is created in the project, by the cli actor
    """
    code, out, _ = run("add", "task", "nx", "-t", "Write docs", "-c", "@ordi", "-s", "S", "-b", "More")
    task = _only_task(session)
    assert code == EXIT_OK and task.ref in out and "(inbox)" in out
    assert (task.title, task.state, task.project.key) == ("Write docs", TaskState.INBOX, "nx")
    assert (task.context, task.size, task.body) == ("@ordi", "S", "More")
    assert events.history(session, "task", task.id)[0].actor == events.ACTOR_CLI


@pytest.mark.parametrize("by_ref", [False, True])
def test_add_task_to_version_is_planned(run, session, version, by_ref):
    """
    Given a version
    When running `nexus add task nx <number or ref> --title ...`
    Then the task is created planned in that version
    """
    code, out, _ = run("add", "task", "nx", version.ref if by_ref else "0.1.0", "--title", "Ship")
    task = _only_task(session)
    assert code == EXIT_OK and "(planned)" in out
    assert (task.state, task.version_id) == (TaskState.PLANNED, version.id)


def test_add_task_prompts_for_missing_title_on_a_terminal(run, session, version, monkeypatch):
    """
    Given no --title and a terminal
    When running `nexus add task nx`
    Then the title is asked for
    """
    monkeypatch.setattr("sys.stdin", type("Tty", (), {"isatty": lambda self: True})())
    monkeypatch.setattr("builtins.input", lambda prompt: "Asked title")
    assert run("add", "task", "nx")[0] == EXIT_OK
    assert _only_task(session).title == "Asked title"


def test_add_task_without_title_and_terminal_is_a_usage_error(run, session, version, monkeypatch):
    """
    Given no --title and no terminal
    When running `nexus add task nx`
    Then it is a usage error and nothing is created
    """
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    code, _, err = run("add", "task", "nx")
    assert code == EXIT_USAGE and "--title" in err and tasks.list(session) == []


@pytest.mark.parametrize("argv", [["add"], ["add", "epic", "nx"], ["add", "task"],
                                  ["add", "task", "nx", "-t", "x", "-s", "XXL"]])
def test_add_with_a_malformed_command_line_is_a_usage_error(run, version, argv):
    """
    Given a malformed `add` command line
    When running nexus
    Then it is a usage error with exit code 2
    """
    assert run(*argv)[0] == EXIT_USAGE


def test_add_task_refused_by_the_services_is_a_domain_error(run, session, version):
    """
    Given a missing project, a released version and a blank title
    When adding tasks
    Then each is refused with exit code 1 and nothing is created
    """
    versions.start(session, version.id)
    versions.set_criterion_done(session, version.definition_of_done[0].id, True)
    versions.release(session, version.id)
    for argv in (["add", "task", "ghost", "-t", "x"],
                 ["add", "task", "nx", "0.1.0", "-t", "x"],
                 ["add", "task", "nx", "-t", "   "]):
        assert run(*argv)[0] == EXIT_ERROR
    assert tasks.list(session) == []


def test_sentence_is_captured_into_the_inbox(run, session):
    """
    Given a description with spaces
    When running `nexus "<description>"`
    Then an inbox task with that title is created, by the cli actor
    """
    code, out, _ = run("  Buy some milk ")
    task = _only_task(session)
    assert code == EXIT_OK and "(inbox)" in out
    assert (task.title, task.state, task.project_id) == ("Buy some milk", TaskState.INBOX, None)
    assert events.history(session, "task", task.id)[0].actor == events.ACTOR_CLI


def test_blank_description_is_refused(run, session):
    """
    Given an empty argument
    When running `nexus ""`
    Then it is refused with exit code 1 and nothing is created
    """
    assert run("")[0] == EXIT_ERROR and tasks.list(session) == []


def test_single_word_is_still_a_reference(run, session, version):
    """
    Given a project key
    When running `nexus nx`
    Then the project is shown, not captured as a task
    """
    assert "Nexus" in run("nx")[1] and tasks.list(session) == []
