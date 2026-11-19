import io

import pytest

from src.cli.main import EXIT_ERROR, EXIT_OK, EXIT_USAGE, main
from src.models.task import TaskKind
from src.services import projects, tasks


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
    """A project with a subproject, a feature holding a task, and a loose task."""
    projects.create(session, "nx", "Nexus", "The manager")
    sub = projects.create(session, "v2", "Nexus 2", parent_key="nx")
    feature = tasks.create(session, "Tree", "nx", kind=TaskKind.FEATURE)
    planned = tasks.create(session, "Planned task", parent_ref=feature.ref, size="S", body="Details here")
    loose = tasks.capture(session, "Loose task")
    return sub, planned, loose


def test_version_command_prints_app_version(run):
    """
    Given the installed app
    When running `nexus version`
    Then "nexus <number>" is printed
    """
    code, out, _ = run("version")
    assert code == EXIT_OK and out.startswith("nexus ")


def test_tasks_lists_every_task_with_placement(run, data):
    """
    Given a task under a feature and a loose one
    When running `nexus tasks`
    Then both appear, with their ref, state, project and parent
    """
    _, planned, loose = data
    _, out, _ = run("tasks")
    assert out.splitlines()[0].split() == ["REF", "STATE", "PROJECT", "PARENT", "TITLE"]
    rows = [line.split(maxsplit=4) for line in out.splitlines()[1:]]
    assert [planned.ref, "INBOX", "nx", planned.parent.ref, "Planned task"] in rows
    assert [loose.ref, "INBOX", "-", "-", "Loose task"] in rows


def test_projects_lists_projects(run, data):
    """
    Given a project
    When running `nexus projects`
    Then its key, status and name are listed
    """
    _, out, _ = run("projects")
    assert "nx" in out and "ACTIVE" in out and "Nexus" in out


def test_empty_lists_say_none(run):
    """
    Given an empty database
    When listing tasks and projects
    Then each prints "(none)"
    """
    for word in ("tasks", "projects"):
        assert run(word)[1].strip() == "(none)"


def test_project_detail_lists_its_subprojects(run, data):
    """
    Given a project with a subproject
    When running `nexus nx`
    Then the project fields and its subprojects are shown
    """
    sub, _, _ = data
    code, out, _ = run("nx")
    assert code == EXIT_OK
    assert "The manager" in out and "Subprojects" in out and sub.ref in out


def test_subproject_ref_shows_the_subproject(run, data):
    """
    Given a subproject ref
    When running `nexus <ref>`
    Then the subproject detail is shown, with its parent
    """
    sub, _, _ = data
    code, out, _ = run(sub.ref)
    assert code == EXIT_OK and "Nexus 2" in out and "nx" in out


def test_task_detail(run, data):
    """
    Given a task under a feature, with a body
    When running `nexus <task ref>`
    Then its fields, parent and description are shown
    """
    _, planned, _ = data
    code, out, _ = run(planned.ref)
    assert code == EXIT_OK
    assert "INBOX" in out and planned.parent.ref in out and "Details here" in out


@pytest.mark.parametrize("argv", [["tasks", "x"], ["nx", "x"], ["TASK", "x"]])
def test_extra_arguments_are_usage_errors(run, data, argv):
    """
    Given a command line with a stray argument
    When running nexus
    Then it is a usage error with exit code 2
    """
    _, planned, _ = data
    argv = [planned.ref if a == "TASK" else a for a in argv]
    assert run(*argv)[0] == EXIT_USAGE
