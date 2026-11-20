import io

import pytest

from src.cli.main import EXIT_ERROR, EXIT_OK, EXIT_USAGE, main
from src.models.task import TaskState
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
def project(session):
    """A project 'nx'."""
    return projects.create(session, "nx", "Nexus", "")


def _only_task(session):
    """The single task in the database."""
    (task,) = tasks.list(session)
    return task


def test_add_task_to_project_is_inbox_in_its_tree(run, session, project):
    """
    Given a project
    When running `nexus add task nx --title ...` with detail options
    Then an inbox task is created at the top of the project, by the cli actor
    """
    code, out, _ = run("add", "task", "nx", "-t", "Write docs", "-c", "@ordi", "-s", "S", "-b", "More")
    task = _only_task(session)
    assert code == EXIT_OK and f"Created task {task.ref} (inbox, nx): Write docs" in out
    assert (task.title, task.state, task.project.key, task.parent) == ("Write docs", TaskState.INBOX, "nx", None)
    assert (task.context, task.size, task.body) == ("@ordi", "S", "More")
    assert {e.actor for e in events.history(session, "task", task.id)} == {events.ACTOR_CLI}


def test_add_feature_then_task_under_it(run, session, project):
    """A feature is added, then a task under it with --parent."""
    run("add", "feature", "nx", "-t", "Auth")
    feature_ref = tasks.list(session)[0].ref
    code, out, _ = run("add", "task", "nx", "--parent", feature_ref, "-t", "Login")
    assert code == EXIT_OK and f"(inbox, nx > {feature_ref}): Login" in out
    # The cli closes its session after each run: read the feature afresh.
    feature = tasks.get_by_ref(session, feature_ref)
    assert feature.kind.name == "FEATURE" and [c.title for c in feature.children] == ["Login"]


def test_add_under_a_feature_of_another_project_is_refused(run, session, project):
    """A parent from another project is refused, and nothing is created."""
    projects.create(session, "other", "Other")
    run("add", "feature", "nx", "-t", "Auth")
    feature_ref = tasks.list(session)[0].ref
    code, _, err = run("add", "task", "other", "--parent", feature_ref, "-t", "Stray")
    assert code == EXIT_ERROR and "isn't in project" in err
    assert [t.title for t in tasks.list(session)] == ["Auth"]


def test_add_task_prompts_for_missing_title_on_a_terminal(run, session, project, monkeypatch):
    """
    Given no --title and a terminal
    When running `nexus add task nx`
    Then the title is asked for
    """
    monkeypatch.setattr("sys.stdin", type("Tty", (), {"isatty": lambda self: True})())
    monkeypatch.setattr("builtins.input", lambda prompt: "Asked title")
    assert run("add", "task", "nx")[0] == EXIT_OK
    assert _only_task(session).title == "Asked title"


def test_add_task_without_title_and_terminal_is_a_usage_error(run, session, project, monkeypatch):
    """
    Given no --title and no terminal
    When running `nexus add task nx`
    Then it is a usage error and nothing is created
    """
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    code, _, err = run("add", "task", "nx")
    assert code == EXIT_USAGE and "--title" in err and tasks.list(session) == []


@pytest.mark.parametrize("argv", [["add"], ["add", "epic", "nx"], ["add", "task"],
                                  ["add", "task", "nx", "-t", "x", "-s", "XXL"],
                                  ["add", "task", "nx", "0.1.0", "-t", "x"]])
def test_add_with_a_malformed_command_line_is_a_usage_error(run, project, argv):
    """
    Given a malformed `add` command line
    When running nexus
    Then it is a usage error with exit code 2
    """
    assert run(*argv)[0] == EXIT_USAGE


def test_add_task_refused_by_the_services_is_a_domain_error(run, session, project):
    """
    Given a missing project and a blank title
    When adding tasks
    Then each is refused with exit code 1 and nothing is created
    """
    for argv in (["add", "task", "ghost", "-t", "x"],
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
    assert code == EXIT_OK and "(inbox):" in out
    assert (task.title, task.state, task.project_id) == ("Buy some milk", TaskState.INBOX, None)
    assert events.history(session, "task", task.id)[0].actor == events.ACTOR_CLI


def test_blank_description_is_refused(run, session):
    """
    Given an empty argument
    When running `nexus ""`
    Then it is refused with exit code 1 and nothing is created
    """
    assert run("")[0] == EXIT_ERROR and tasks.list(session) == []


def test_single_word_is_still_a_reference(run, session, project):
    """
    Given a project key
    When running `nexus nx`
    Then the project is shown, not captured as a task
    """
    assert "Nexus" in run("nx")[1] and tasks.list(session) == []


@pytest.mark.parametrize("argv", [("check", "1"), ("start",), ("0.1.0",)])
def test_words_after_a_project_are_usage_errors(run, project, argv):
    """
    Given a project
    When running a former version action, or a version number, after its key
    Then it is a usage error: versions are gone
    """
    assert run("nx", *argv)[0] == EXIT_USAGE
