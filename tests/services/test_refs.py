import re

import pytest

from src.models.task import Task
from src.models.version import Version
from src.services import events, projects, refs, tasks, versions
from src.services.errors import NotFoundError


def test_generate_formats_ref_with_model_prefix(session):
    """
    Given an empty database
    When refs are generated for a task and a version
    Then they are prefixed "t-" / "v-" followed by a base36 code
    """
    assert re.fullmatch(r"t-[0-9a-z]{3}", refs.generate(session, Task))
    assert re.fullmatch(r"v-[0-9a-z]{3}", refs.generate(session, Version))


def test_generate_retries_on_collision(session, monkeypatch):
    """
    Given a task already holding the first candidate ref
    When a ref is generated
    Then the taken candidate is skipped
    """
    candidates = iter("aaabbb")
    monkeypatch.setattr(refs.secrets, "choice", lambda _alphabet: next(candidates))
    session.add(Task(ref="t-aaa", title="Existing"))
    session.commit()
    assert refs.generate(session, Task) == "t-bbb"


def test_generate_widens_code_when_crowded(session, monkeypatch):
    """
    Given a namespace where every short candidate collides
    When a ref is generated
    Then the code grows by one character after repeated collisions
    """
    monkeypatch.setattr(refs, "_is_taken", lambda _s, _m, ref: len(ref) == len("t-abc"))
    assert len(refs.generate(session, Task)) == len("t-abcd")


def test_services_assign_unique_refs(session):
    """
    Given a project
    When tasks and a version are created through the services
    Then each gets its own ref, unique within its table
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First", ["Ships"])
    captured = tasks.capture(session, "Captured")
    planned = tasks.create_in_version(session, version.id, "Planned")
    assert version.ref.startswith("v-")
    assert captured.ref.startswith("t-") and planned.ref.startswith("t-")
    assert captured.ref != planned.ref


def test_get_by_ref_finds_task_and_version(session):
    """
    Given a version and a task with refs
    When looked up by ref, in any letter case
    Then the matching rows are returned
    """
    projects.create(session, "nexus", "Nexus", "")
    version = versions.create(session, "nexus", "0.1.0", "First", ["Ships"])
    task = tasks.capture(session, "Captured")
    assert tasks.get_by_ref(session, task.ref.upper()) is task
    assert versions.get_by_ref(session, f" {version.ref} ") is version


def test_get_by_ref_unknown_raises(session):
    """
    Given an empty database
    When looking up an unknown ref
    Then a not-found error is raised
    """
    with pytest.raises(NotFoundError):
        tasks.get_by_ref(session, "t-zzz")
    with pytest.raises(NotFoundError):
        versions.get_by_ref(session, "v-zzz")


def test_creations_record_the_given_actor(session):
    """
    Given the CLI actor
    When a project, version and tasks are created with it
    Then their "created" events carry that actor, and default to web otherwise
    """
    project = projects.create(session, "nexus", "Nexus", "", actor=events.ACTOR_CLI)
    version = versions.create(session, "nexus", "0.1.0", "First", ["Ships"], actor=events.ACTOR_CLI)
    captured = tasks.capture(session, "Captured", actor=events.ACTOR_CLI)
    created = tasks.create(session, "Created", project_key="nexus", actor=events.ACTOR_CLI)
    planned = tasks.create_in_version(session, version.id, "Planned", actor=events.ACTOR_CLI)
    default = tasks.capture(session, "Default")
    for kind, entity in (("project", project), ("version", version), ("task", captured),
                         ("task", created), ("task", planned)):
        assert events.history(session, kind, entity.id)[0].actor == events.ACTOR_CLI
    assert events.history(session, "task", default.id)[0].actor == events.ACTOR_WEB
