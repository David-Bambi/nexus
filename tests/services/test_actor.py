import pytest

from src.models.task import TaskState
from src.services import events, projects, tasks, versions

MCP = events.ACTOR_MCP


@pytest.fixture
def world(session):
    """A project with two versions, and a factory of tasks in a chosen state."""
    projects.create(session, "nx", "Nexus", "")
    v1 = versions.create(session, "nx", "1.0", "First", ["Ships", "Documented"])
    v2 = versions.create(session, "nx", "2.0", "Second", ["Ships"])

    def make(state=TaskState.INBOX):
        """Create a task and walk it to the given state (planned in v1 when past refined)."""
        task = tasks.capture(session, "A task")
        if state == TaskState.INBOX:
            return task
        tasks.clarify(session, task.id, "A task", None, None, None, None)
        if state == TaskState.REFINED:
            return task
        tasks.plan(session, task.id, v1.id)
        if state == TaskState.PLANNED:
            return task
        tasks.start(session, task.id)
        if state == TaskState.WAITING:
            tasks.block(session, task.id, "why")
        if state == TaskState.DONE:
            tasks.complete(session, task.id)
        return task

    return session, v1, v2, make


def _last_event(session):
    """The most recently logged event."""
    return session.query(events.Event).order_by(events.Event.id.desc()).first()


# Each case: (entity kind of its event, function running the mutation with the mcp actor).
CASES = {
    "update": ("task", lambda s, v1, v2, make: tasks.update(s, make().id, actor=MCP, title="New")),
    "clarify": ("task", lambda s, v1, v2, make: tasks.clarify(s, make().id, "T", None, None, None, None, actor=MCP)),
    "plan": ("task", lambda s, v1, v2, make: tasks.plan(s, make(TaskState.REFINED).id, v1.id, actor=MCP)),
    "unplan": ("task", lambda s, v1, v2, make: tasks.unplan(s, make(TaskState.PLANNED).id, actor=MCP)),
    "start": ("task", lambda s, v1, v2, make: tasks.start(s, make(TaskState.PLANNED).id, actor=MCP)),
    "block": ("task", lambda s, v1, v2, make: tasks.block(s, make(TaskState.DOING).id, "why", actor=MCP)),
    "unblock": ("task", lambda s, v1, v2, make: tasks.unblock(s, make(TaskState.WAITING).id, actor=MCP)),
    "complete": ("task", lambda s, v1, v2, make: tasks.complete(s, make(TaskState.DOING).id, actor=MCP)),
    "reopen": ("task", lambda s, v1, v2, make: tasks.reopen(s, make(TaskState.DONE).id, actor=MCP)),
    "defer": ("task", lambda s, v1, v2, make: tasks.defer(s, make().id, actor=MCP)),
    "move": ("task", lambda s, v1, v2, make: tasks.move_to_version(s, make(TaskState.PLANNED).id, v2.id, actor=MCP)),
    "cancel": ("task", lambda s, v1, v2, make: tasks.cancel(s, make().id, actor=MCP)),
    "restore": ("task", lambda s, v1, v2, make: tasks.restore(s, tasks.cancel(s, make().id).id, actor=MCP)),
    "change_state": ("task", lambda s, v1, v2, make: tasks.change_state(s, make(TaskState.PLANNED).id, TaskState.DOING, actor=MCP)),
    "version_start": ("version", lambda s, v1, v2, make: versions.start(s, v2.id, actor=MCP)),
    "add_criterion": ("version", lambda s, v1, v2, make: versions.add_criterion(s, v1.id, "New", actor=MCP)),
    "set_criterion_done": ("version", lambda s, v1, v2, make: versions.set_criterion_done(s, v1.definition_of_done[0].id, True, actor=MCP)),
    "update_criterion": ("version", lambda s, v1, v2, make: versions.update_criterion(s, v1.definition_of_done[0].id, "Edited", actor=MCP)),
    "delete_criterion": ("version", lambda s, v1, v2, make: versions.delete_criterion(s, v1.definition_of_done[1].id, actor=MCP)),
    "reorder": ("project", lambda s, v1, v2, make: versions.reorder(s, "nx", [v2.id, v1.id], actor=MCP)),
    "archive": ("project", lambda s, v1, v2, make: projects.archive(s, "nx", actor=MCP)),
}


@pytest.mark.parametrize("name", list(CASES))
def test_every_mutation_records_the_given_actor(world, name):
    """
    Given any mutating service
    When it runs with the mcp actor
    Then the last event it logged carries that actor
    """
    kind, run = CASES[name]
    run(*world)
    event = _last_event(world[0])
    assert (event.entity_type, event.actor) == (kind, MCP), f"{name}: {event.action} by {event.actor}"


def test_delete_task_and_project_record_the_given_actor(world):
    """
    Given a task and a project
    When deleting them with the mcp actor
    Then both "deleted" events carry that actor
    """
    session, v1, v2, make = world
    t = make()
    tasks.delete(session, t.id, actor=events.ACTOR_MCP)
    projects.create(session, "gone", "Gone", "")
    projects.delete(session, "gone", actor=events.ACTOR_MCP)
    deleted = [e for e in session.query(events.Event).all() if e.action == "deleted"]
    assert {e.entity_type: e.actor for e in deleted} == {"task": "mcp", "project": "mcp"}


def test_release_records_the_given_actor(world):
    """
    Given a started version whose checklist is done
    When releasing it with the mcp actor
    Then the "released" event carries that actor
    """
    session, v1, v2, make = world
    versions.start(session, v2.id)
    versions.set_criterion_done(session, v2.definition_of_done[0].id, True)
    versions.release(session, v2.id, actor=events.ACTOR_MCP)
    released = [e for e in session.query(events.Event).all() if e.action == "released"]
    assert [e.actor for e in released] == ["mcp"]


def test_defaults_stay_web(world):
    """
    Given a mutation called without an actor
    When it runs
    Then its event is attributed to the web
    """
    session, v1, v2, make = world
    t = make()
    tasks.update(session, t.id, title="Renamed")
    assert _last_event(session).actor == events.ACTOR_WEB
