import pytest

from src.models.task import TaskKind, TaskState
from src.services import events, projects, tasks

MCP = events.ACTOR_MCP


@pytest.fixture
def world(session):
    """A project with a feature, and a factory of tasks in a chosen state."""
    projects.create(session, "nx", "Nexus", "")
    feature = tasks.create(session, "Tree", "nx", kind=TaskKind.FEATURE)

    def make(state=TaskState.INBOX):
        """Create a task in 'nx' and walk it to the given state."""
        task = tasks.create(session, "A task", "nx")
        if state == TaskState.INBOX:
            return task
        tasks.clarify(session, task.id, "A task", None, "nx", None, None)
        if state == TaskState.REFINED:
            return task
        tasks.start(session, task.id)
        if state == TaskState.WAITING:
            tasks.block(session, task.id, "why")
        if state == TaskState.DONE:
            tasks.complete(session, task.id)
        return task

    return session, feature, make


def _last_event(session):
    """The most recently logged event."""
    return session.query(events.Event).order_by(events.Event.id.desc()).first()


# Each case: (entity kind of its event, function running the mutation with the mcp actor).
CASES = {
    "update": ("task", lambda s, f, make: tasks.update(s, make().id, actor=MCP, title="New")),
    "clarify": ("task", lambda s, f, make: tasks.clarify(s, make().id, "T", None, None, None, None, actor=MCP)),
    "start": ("task", lambda s, f, make: tasks.start(s, make(TaskState.REFINED).id, actor=MCP)),
    "block": ("task", lambda s, f, make: tasks.block(s, make(TaskState.DOING).id, "why", actor=MCP)),
    "unblock": ("task", lambda s, f, make: tasks.unblock(s, make(TaskState.WAITING).id, actor=MCP)),
    "complete": ("task", lambda s, f, make: tasks.complete(s, make(TaskState.DOING).id, actor=MCP)),
    "reopen": ("task", lambda s, f, make: tasks.reopen(s, make(TaskState.DONE).id, actor=MCP)),
    "defer": ("task", lambda s, f, make: tasks.defer(s, make().id, actor=MCP)),
    "move": ("task", lambda s, f, make: tasks.move(s, make().id, parent_ref=f.ref, actor=MCP)),
    "change_kind": ("task", lambda s, f, make: tasks.change_kind(s, make().id, TaskKind.FEATURE, actor=MCP)),
    "cancel": ("task", lambda s, f, make: tasks.cancel(s, make().id, actor=MCP)),
    "restore": ("task", lambda s, f, make: tasks.restore(s, tasks.cancel(s, make().id).id, actor=MCP)),
    "change_state": ("task", lambda s, f, make: tasks.change_state(s, make(TaskState.REFINED).id, TaskState.DOING, actor=MCP)),
    "create_subproject": ("project", lambda s, f, make: projects.create(s, "sub", "Sub", parent_key="nx", actor=MCP)),
    "archive": ("project", lambda s, f, make: projects.archive(s, "nx", actor=MCP)),
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
    session, _, make = world
    tasks.delete(session, make().id, actor=MCP)
    projects.create(session, "gone", "Gone", "")
    projects.delete(session, "gone", actor=MCP)
    deleted = [e for e in session.query(events.Event).all() if e.action == "deleted"]
    assert {e.entity_type: e.actor for e in deleted} == {"task": "mcp", "project": "mcp"}


def test_defaults_stay_web(world):
    """
    Given a mutation called without an actor
    When it runs
    Then its event is attributed to the web
    """
    session, _, make = world
    tasks.update(session, make().id, title="Renamed")
    assert _last_event(session).actor == events.ACTOR_WEB
