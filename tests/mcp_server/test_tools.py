import json
from types import SimpleNamespace

import pytest

from src.mcp_server import tools
from src.models.event import Event
from src.models.task import Task, TaskKind
from src.services import events, projects, tasks


def call(session, name, **arguments):
    """Call a tool and return its raw MCP result."""
    return tools.call_tool(session, name, arguments)


def ok(session, name, **arguments):
    """Call a tool that must succeed; return its structured data."""
    result = call(session, name, **arguments)
    assert result["isError"] is False, result["content"][0]["text"]
    return result["structuredContent"]


def refused(session, name, **arguments):
    """Call a tool that must be refused; return the message."""
    result = call(session, name, **arguments)
    assert result["isError"] is True and "structuredContent" not in result
    return result["content"][0]["text"]


@pytest.fixture
def world(session):
    """A project with a subproject, a feature holding a refined task, a refined task and an inbox task."""
    projects.create(session, "nx", "Nexus", "The manager")
    sub = projects.create(session, "v2", "Nexus 2", parent_key="nx")
    feature = tasks.create(session, "Tree", "nx", kind=TaskKind.FEATURE)
    planned = tasks.create(session, "Planned task", parent_ref=feature.ref, size="S")
    tasks.clarify(session, planned.id, "Planned task", None, None, None, "S", parent_ref=feature.ref)
    refined = tasks.capture(session, "Refined task")
    tasks.clarify(session, refined.id, "Refined task", None, "nx", None, None)
    inbox = tasks.capture(session, "Inbox task")
    return sub, planned, refined, inbox


def _id_keys(data):
    """Every key named id or ending in _id, at any depth (a raw database id leaking out)."""
    found = []
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "id" or key.endswith("_id"):
                found.append(key)
            found += _id_keys(value)
    elif isinstance(data, list):
        for item in data:
            found += _id_keys(item)
    return found


def _last_event(session):
    return session.query(Event).order_by(Event.id.desc()).first()


# Catalogue -----------------------------------------------------------------------------------------

def test_every_tool_is_described_with_a_strict_schema_and_annotations():
    """
    Given the tool registry
    When listing the tools
    Then each has a description, an object schema with no extra properties, and hints matching its kind
    (none removes data)
    """
    listed = tools.list_tools()
    assert len(listed) == len(tools.TOOLS) == 15
    for item in listed:
        assert item["description"]
        assert item["inputSchema"]["type"] == "object" and item["inputSchema"]["additionalProperties"] is False
        assert set(item["inputSchema"].get("required", [])) <= set(item["inputSchema"]["properties"])
        hints = item["annotations"]
        assert hints["readOnlyHint"] == tools.TOOLS[item["name"]].read_only
        assert ("destructiveHint" in hints) == (not hints["readOnlyHint"])
        assert hints.get("destructiveHint", False) is False


def test_read_only_tools_are_exactly_the_read_ones():
    """
    Given the registry
    When collecting read-only tools
    Then they are the listing and showing tools, and no writer among them
    """
    assert {n for n, t in tools.TOOLS.items() if t.read_only} == {
        "list_projects", "list_tasks", "get_project", "get_task", "inbox", "search", "dashboard"}


READ_CALLS = [("list_projects", {}), ("list_tasks", {}), ("list_tasks", {"project": "nx"}),
              ("get_project", {"project": "nx"}), ("inbox", {}), ("search", {"term": "task"}), ("dashboard", {})]


@pytest.mark.parametrize("name,arguments", READ_CALLS)
def test_read_tools_change_nothing(session, world, name, arguments):
    """
    Given a database with data
    When calling a read-only tool
    Then no row and no event is added, and the session holds no pending change
    """
    before = session.query(Event).count()
    ok(session, name, **arguments)
    assert session.query(Event).count() == before
    assert not session.new and not session.dirty


def test_result_carries_json_text_and_the_same_structured_data(session, world):
    """
    Given a successful call
    When reading the result
    Then the text content is the JSON of the structured content
    """
    result = call(session, "list_projects")
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]


# Validation ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,arguments,message", [
    ("capture_task", {}, "'title' is required"),
    ("capture_task", {"title": "   "}, "must not be blank"),
    ("capture_task", {"title": 5}, "must be of type string"),
    ("capture_task", {"title": "x", "bogus": 1}, "unknown argument(s): bogus"),
    ("search", {"term": "x", "limit": True}, "must be of type integer"),
    ("list_tasks", {"state": "NOPE"}, "must be one of"),
    ("add_task", {"project": "nx", "title": "x", "size": "XXL"}, "must be one of"),
])
def test_invalid_arguments_are_reported_not_raised(session, world, name, arguments, message):
    """
    Given malformed arguments
    When calling a tool
    Then the call returns an error result naming the problem, and writes nothing
    """
    before = session.query(Event).count()
    assert message in refused(session, name, **arguments)
    assert session.query(Event).count() == before


def test_non_object_arguments_are_refused(session):
    """
    Given arguments that are not an object
    When calling a tool
    Then an error result is returned
    """
    assert "must be an object" in tools.call_tool(session, "inbox", [1])["content"][0]["text"]


def test_missing_arguments_default_to_empty(session):
    """
    Given a tool with no required argument
    When calling it with None arguments
    Then it runs
    """
    assert tools.call_tool(session, "inbox", None)["isError"] is False


def test_unknown_tool_raises(session):
    """
    Given a name that is no tool
    When calling it
    Then UnknownTool is raised, for the transport to report
    """
    with pytest.raises(tools.UnknownTool):
        tools.call_tool(session, "nope", {})


def test_domain_errors_become_error_results(session, world):
    """
    Given a reference to nothing
    When calling tools with it
    Then the service's message comes back as an error result
    """
    assert "doesn't exist" in refused(session, "get_task", ref="t-zzz")
    assert "doesn't exist" in refused(session, "get_project", project="ghost")


# Reading -------------------------------------------------------------------------------------------

def test_list_and_show_tools_return_refs_and_no_integer_ids(session, world):
    """
    Given a project, a subproject, a feature and tasks
    When reading them through the tools
    Then results identify things by key or ref, with kind and parent, and never expose a raw id
    """
    sub, planned, _, _ = world
    listed = ok(session, "list_tasks")
    assert listed["count"] == 4 and listed["truncated"] is False
    by_ref = {t["ref"]: t for t in listed["tasks"]}
    assert by_ref[planned.ref]["kind"] == "TASK" and by_ref[planned.ref]["parent"] == planned.parent.ref
    assert by_ref[planned.parent.ref]["kind"] == "FEATURE"
    shown = ok(session, "get_project", project="nx")
    assert shown["subprojects"] == [{"key": "v2", "ref": sub.ref, "parent": "nx", "name": "Nexus 2",
                                     "description": None, "status": "ACTIVE"}]
    assert not _id_keys(shown) and not _id_keys(listed)


def test_list_tasks_filters(session, world):
    """
    Given items in several states and projects
    When filtering by state, project and limit
    Then only matching items are returned
    """
    _, planned, refined, inbox = world
    assert [t["ref"] for t in ok(session, "list_tasks", state="INBOX")["tasks"]] == [planned.parent.ref, inbox.ref]
    assert {t["ref"] for t in ok(session, "list_tasks", project="nx")["tasks"]} == {
        planned.parent.ref, planned.ref, refined.ref}
    limited = ok(session, "list_tasks", limit=1)
    assert [t["ref"] for t in limited["tasks"]] == [inbox.ref] and limited["truncated"] is True


def test_get_task_includes_its_history(session, world):
    """
    Given a task that changed
    When showing it
    Then its event history is included
    """
    _, planned, _, _ = world
    tasks.start(session, planned.id)
    task = ok(session, "get_task", ref=planned.ref)
    assert task["state"] == "DOING" and [e["action"] for e in task["history"]] == ["created", "clarified", "started"]


def test_search_inbox_and_dashboard(session, world):
    """
    Given tasks
    When searching, listing the inbox and reading the dashboard
    Then each answers from the data
    """
    _, planned, _, inbox = world
    assert [t["ref"] for t in ok(session, "search", term="INBOX")["tasks"]] == [inbox.ref]
    assert [t["ref"] for t in ok(session, "inbox")["tasks"]] == [planned.parent.ref, inbox.ref]
    dashboard = ok(session, "dashboard")
    assert dashboard["inbox_count"] == 2 and dashboard["refine_count"] == 2 and "in_progress" not in dashboard


# Writing -------------------------------------------------------------------------------------------

def test_capture_task_records_the_mcp_actor(session):
    """
    Given a title
    When capturing through the tool
    Then an inbox task exists and its event is attributed to mcp
    """
    task = ok(session, "capture_task", title="  Buy milk ")
    assert (task["title"], task["state"]) == ("Buy milk", "INBOX")
    assert _last_event(session).actor == events.ACTOR_MCP


def test_add_task_to_a_project(session, world):
    """
    Given a project
    When adding a task to it, then to a missing one
    Then the first lands in the project's inbox and the second is refused
    """
    inbox = ok(session, "add_task", project="nx", title="A", context="@ordi", size="M", body="Detail")
    assert (inbox["state"], inbox["project"], inbox["parent"]) == ("INBOX", "nx", None)
    assert (inbox["context"], inbox["size"], inbox["body"]) == ("@ordi", "M", "Detail")
    assert "doesn't exist" in refused(session, "add_task", project="ghost", title="C")
    assert "unknown argument(s): version" in refused(session, "add_task", project="nx", title="B", version="1.0")


def test_import_data_dry_run_then_real(session):
    """
    Given a document
    When importing with dry_run then for real
    Then the dry run writes nothing and reports refs as null, the real one stores everything
    """
    document = {"projects": [{"key": "demo", "name": "Demo"}], "tasks": [{"title": "Loose"}, {"title": "In", "project": "demo"}]}
    dry = ok(session, "import_data", document=document, dry_run=True)
    assert dry["dry_run"] and dry["tasks_created"] == 2 and all(c["ref"] is None for c in dry["created"])
    assert tasks.list(session) == []
    real = ok(session, "import_data", document=document)
    assert real["projects_created"] == 1 and len(tasks.list(session)) == 2
    assert all(c["ref"].startswith("t-") for c in real["created"])
    assert {e.actor for e in session.query(Event).all()} == {"mcp"}


def test_import_data_text_and_argument_rules(session):
    """
    Given a text list, both inputs, or none
    When importing
    Then text becomes inbox tasks, and anything but exactly one input is refused
    """
    assert ok(session, "import_data", text="A\nB\n")["tasks_created"] == 2
    assert "exactly one" in refused(session, "import_data")
    assert "exactly one" in refused(session, "import_data", text="x", document={})


def test_import_data_invalid_document_lists_problems_and_writes_nothing(session):
    """
    Given an invalid document
    When importing
    Then the error lists the problems and nothing is stored
    """
    message = refused(session, "import_data", document={"tasks": [{"title": ""}, {"title": "x", "size": "XXL"}]})
    assert "2 problem(s)" in message and tasks.list(session) == []


def test_update_task_changes_and_clears_fields(session, world):
    """
    Given a task with a size
    When updating its title and clearing its size, then updating nothing
    Then the fields change, and an empty update is refused
    """
    _, planned, _, _ = world
    updated = ok(session, "update_task", ref=planned.ref, title="Renamed", size=" ")
    assert (updated["title"], updated["size"]) == ("Renamed", None)
    assert _last_event(session).actor == events.ACTOR_MCP
    assert "at least one field" in refused(session, "update_task", ref=planned.ref)


def test_task_lifecycle_through_tools(session, world):
    """
    Given a refined task
    When starting, blocking, unblocking and completing it through the tools
    Then it follows the state machine, each step logged by mcp
    """
    _, _, refined, _ = world
    states = [ok(session, name, **args)["state"] for name, args in [
        ("start_task", {"ref": refined.ref}),
        ("block_task", {"ref": refined.ref, "reason": "waiting on X"}),
        ("unblock_task", {"ref": refined.ref}),
        ("complete_task", {"ref": refined.ref}),
    ]]
    assert states == ["DOING", "WAITING", "DOING", "DONE"]
    assert {e.actor for e in events.history(session, "task", refined.id)[2:]} == {"mcp"}


def test_transition_errors(session, world):
    """
    Given an inbox task, a refined one, and a feature whose child is open
    When starting the inbox task, blocking without a reason, and completing the feature
    Then each is refused with a message
    """
    _, planned, _, inbox = world
    assert "isn't refined" in refused(session, "start_task", ref=inbox.ref)
    assert "'reason' is required" in refused(session, "block_task", ref=planned.ref)
    feature = planned.parent
    tasks.clarify(session, feature.id, feature.title, None, "nx", None, None)
    tasks.start(session, feature.id)
    assert "open children" in refused(session, "complete_task", ref=feature.ref)


def test_a_refused_write_leaves_no_partial_change(session, world):
    """
    Given a write refused by a service
    When it fails
    Then the session has no pending change left
    """
    _, _, _, inbox = world
    refused(session, "complete_task", ref=inbox.ref)
    assert not session.new and not session.dirty


# Gaps found by measuring coverage ------------------------------------------------------------------

def test_unexpected_errors_roll_back_and_propagate(session, world, monkeypatch):
    """
    Given a handler failing with something that isn't a domain error
    When calling the tool
    Then the session is rolled back and the exception reaches the caller
    """
    def boom(session, args):
        session.add(Task(ref="t-boo", title="half done"))
        raise RuntimeError("boom")

    monkeypatch.setitem(tools.TOOLS, "capture_task", tools.Tool("capture_task", "", tools.TOOLS["capture_task"].schema, boom))
    with pytest.raises(RuntimeError):
        call(session, "capture_task", title="x")
    assert not session.new and tasks.get_by_ref(session, world[1].ref)


def test_update_task_refuses_a_blank_title_and_bad_size(session, world):
    """
    Given a task
    When updating its title to blank or its size to an unknown one
    Then both are refused and nothing changes
    """
    _, planned, _, _ = world
    assert "'title' must not be blank" in refused(session, "update_task", ref=planned.ref, title="  ")
    assert "must be one of" in refused(session, "update_task", ref=planned.ref, size="XXL")
    assert tasks.get_by_ref(session, planned.ref).title == "Planned task"


def test_list_filters_refuse_unknown_references(session, world):
    """
    Given a project that doesn't exist
    When filtering tasks by it
    Then a readable error is returned
    """
    assert "doesn't exist" in refused(session, "list_tasks", project="ghost")


def test_search_reports_truncation_and_archived_projects_are_opt_in(session, world):
    """
    Given several matches and an archived project
    When searching with a small limit and listing projects with and without archived
    Then truncation is flagged, and archived projects only appear on request
    """
    assert ok(session, "search", term="task", limit=2)["truncated"] is True
    projects.create(session, "old", "Old", "")
    projects.archive(session, "old")
    assert [p["key"] for p in ok(session, "list_projects")["projects"]] == ["nx", "v2"]
    assert {p["key"] for p in ok(session, "list_projects", include_archived=True)["projects"]} == {"nx", "v2", "old"}


def test_dashboard_lists_working_tasks(session, world):
    """
    Given a doing task and a waiting one
    When reading the dashboard
    Then doing and waiting are reported
    """
    _, planned, refined, _ = world
    tasks.start(session, planned.id)
    tasks.start(session, refined.id)
    tasks.block(session, refined.id, "why")
    board = ok(session, "dashboard")
    assert [t["ref"] for t in board["doing"]] == [planned.ref] and [t["ref"] for t in board["waiting"]] == [refined.ref]


WRITE_CALLS = [
    ("capture_task", lambda w: {"title": "T"}),
    ("add_task", lambda w: {"project": "nx", "title": "T"}),
    ("import_data", lambda w: {"text": "T"}),
    ("update_task", lambda w: {"ref": w.planned.ref, "title": "New"}),
    ("start_task", lambda w: {"ref": w.planned.ref}),
    ("complete_task", lambda w: {"ref": w.doing.ref}),
    ("block_task", lambda w: {"ref": w.doing.ref, "reason": "why"}),
    ("unblock_task", lambda w: {"ref": w.waiting.ref}),
]


@pytest.mark.parametrize("name,arguments", WRITE_CALLS, ids=[n for n, _ in WRITE_CALLS])
def test_every_write_tool_logs_the_mcp_actor(session, world, name, arguments):
    """
    Given each write tool
    When it runs
    Then every event it logged is attributed to mcp
    """
    _, planned, refined, _ = world
    doing = tasks.create(session, "Doing", "nx")
    tasks.clarify(session, doing.id, "Doing", None, "nx", None, None)
    tasks.start(session, doing.id)
    waiting = tasks.create(session, "Waiting", "nx")
    tasks.clarify(session, waiting.id, "Waiting", None, "nx", None, None)
    tasks.start(session, waiting.id)
    tasks.block(session, waiting.id, "why")
    known = SimpleNamespace(planned=planned, refined=refined, doing=doing, waiting=waiting)
    before = session.query(Event).count()
    ok(session, name, **arguments(known))
    fresh = session.query(Event).order_by(Event.id).offset(before).all()
    assert fresh and {e.actor for e in fresh} == {events.ACTOR_MCP}


def test_the_write_calls_above_cover_every_write_tool():
    """
    Given the registry
    When comparing its write tools with the ones exercised above
    Then none is left out, so a new write tool can't skip the actor check
    """
    assert {t.name for t in tools.TOOLS.values() if not t.read_only} == {name for name, _ in WRITE_CALLS}
