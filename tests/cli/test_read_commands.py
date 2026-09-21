import io

import pytest

from src.cli.main import EXIT_ERROR, EXIT_OK, EXIT_USAGE, main
from src.services import projects, tasks, versions


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
    """A project with a version (one checked criterion), a planned task and a loose task."""
    projects.create(session, "nx", "Nexus", "The manager")
    version = versions.create(session, "nx", "0.1.0", "First", ["Ships", "Documented"], goal="Ship it")
    versions.set_criterion_done(session, version.definition_of_done[0].id, True)
    planned = tasks.create_in_version(session, version.id, "Planned task", size="S", body="Details here")
    loose = tasks.capture(session, "Loose task")
    return version, planned, loose


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
    Given a planned task and a loose one
    When running `nexus tasks`
    Then both appear, with their ref, state, project and version
    """
    _, planned, loose = data
    _, out, _ = run("tasks")
    assert out.splitlines()[0].split() == ["REF", "STATE", "PROJECT", "VERSION", "TITLE"]
    assert f"{planned.ref}  PLANNED  nx       0.1.0    Planned task" in out
    assert f"{loose.ref}  INBOX    -        -        Loose task" in out


def test_versions_lists_versions_of_all_projects(run, data):
    """
    Given a version
    When running `nexus versions`
    Then it is listed with its ref, project, number and status
    """
    version, _, _ = data
    _, out, _ = run("versions")
    assert version.ref in out and "nx" in out and "0.1.0" in out and "PLANNED" in out


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
    When listing tasks, versions and projects
    Then each prints "(none)"
    """
    for word in ("tasks", "versions", "projects"):
        assert run(word)[1].strip() == "(none)"


def test_project_detail_lists_its_versions(run, data):
    """
    Given a project with a version
    When running `nexus nx`
    Then the project fields and its versions are shown
    """
    version, _, _ = data
    code, out, _ = run("nx")
    assert code == EXIT_OK
    assert "The manager" in out and "Versions" in out and version.ref in out


@pytest.mark.parametrize("token", ["0.1.0", "REF"])
def test_version_detail_by_number_or_ref(run, data, token):
    """
    Given a version with tasks and a definition of done
    When running `nexus nx <number or ref>`
    Then its tasks and checklist are shown, with checked criteria marked
    """
    version, planned, _ = data
    token = version.ref if token == "REF" else token
    code, out, _ = run("nx", token)
    assert code == EXIT_OK
    assert "Ship it" in out and planned.ref in out
    assert "Definition of done (1/2)" in out
    assert "[x] Ships" in out and "[ ] Documented" in out


def test_version_ref_alone_shows_the_version(run, data):
    """
    Given a version ref
    When running `nexus <ref>`
    Then the version detail is shown
    """
    version, _, _ = data
    assert "Definition of done" in run(version.ref)[1]


def test_task_detail(run, data):
    """
    Given a planned task with a body
    When running `nexus <task ref>`
    Then its fields and description are shown
    """
    _, planned, _ = data
    code, out, _ = run(planned.ref)
    assert code == EXIT_OK
    assert "PLANNED" in out and "0.1.0" in out and "Details here" in out


def test_unknown_version_is_a_domain_error(run, data):
    """
    Given a project without version 9.9
    When running `nexus nx 9.9`
    Then the error goes to stderr with exit code 1
    """
    code, out, err = run("nx", "9.9")
    assert (code, out) == (EXIT_ERROR, "") and "9.9" in err


@pytest.mark.parametrize("argv", [["tasks", "x"], ["nx", "0.1.0", "x"], ["TASK", "x"]])
def test_extra_arguments_are_usage_errors(run, data, argv):
    """
    Given a command line with a stray argument
    When running nexus
    Then it is a usage error with exit code 2
    """
    _, planned, _ = data
    argv = [planned.ref if a == "TASK" else a for a in argv]
    assert run(*argv)[0] == EXIT_USAGE
