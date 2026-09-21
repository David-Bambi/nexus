import json

import pytest

from src.mcp_server import tools
from src.models.event import Event
from src.services import events, projects, tasks, versions


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
    """A project with a version (two criteria), a planned task, a refined task and an inbox task."""
    projects.create(session, "nx", "Nexus", "The manager")
    version = versions.create(session, "nx", "1.0", "First", ["Ships", "Documented"], goal="Ship it")
    planned = tasks.create_in_version(session, version.id, "Planned task", size="S")
    refined = tasks.capture(session, "Refined task")
    tasks.clarify(session, refined.id, "Refined task", None, "nx", None, None)
    inbox = tasks.capture(session, "Inbox task")
    return version, planned, refined, inbox


def _last_event(session):
    return session.query(Event).order_by(Event.id.desc()).first()


# Catalogue -----------------------------------------------------------------------------------------

def test_every_tool_is_described_with_a_strict_schema_and_annotations():
    """
    Given the tool registry
    When listing the tools
    Then each has a description, an object schema with no extra properties, and hints matching its kind
    """
    listed = tools.list_tools()
    assert len(listed) == len(tools.TOOLS) == 20
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
        "list_projects", "list_versions", "list_tasks", "get_project", "get_version", "get_task",
        "inbox", "search", "dashboard"}


READ_CALLS = [("list_projects", {}), ("list_versions", {}), ("list_versions", {"project": "nx"}),
              ("list_tasks", {}), ("get_project", {"project": "nx"}), ("get_version", {"version": "1.0", "project": "nx"}),
              ("inbox", {}), ("search", {"term": "task"}), ("dashboard", {})]


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
    assert "'project' is required" in refused(session, "get_version", version="1.0")


# Reading -------------------------------------------------------------------------------------------

def test_list_and_show_tools_return_refs_and_no_integer_ids(session, world):
    """
    Given a project, a version and tasks
    When reading them through the tools
    Then results identify things by key or ref, and never expose a raw id
    """
    version, planned, _, _ = world
    listed = ok(session, "list_tasks")
    assert listed["count"] == 3 and listed["truncated"] is False
    shown = ok(session, "get_version", version=version.ref)
    assert shown["ref"] == version.ref and shown["project"] == "nx"
    assert [t["ref"] for t in shown["tasks"]] == [planned.ref]
    assert shown["definition_of_done"] == [{"index": 1, "description": "Ships", "done": False},
                                           {"index": 2, "description": "Documented", "done": False}]
    assert "id" not in json.dumps(ok(session, "get_project", project="nx")).replace("ident", "")


def test_list_tasks_filters(session, world):
    """
    Given tasks in several states
    When filtering by state, project, version and limit
    Then only matching tasks are returned
    """
    version, planned, refined, inbox = world
    assert [t["ref"] for t in ok(session, "list_tasks", state="INBOX")["tasks"]] == [inbox.ref]
    assert [t["ref"] for t in ok(session, "list_tasks", version="1.0", project="nx")["tasks"]] == [planned.ref]
    assert [t["ref"] for t in ok(session, "list_tasks", version=version.ref)["tasks"]] == [planned.ref]
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
    assert task["state"] == "DOING" and [e["action"] for e in task["history"]] == ["created", "started"]


def test_search_inbox_and_dashboard(session, world):
    """
    Given tasks
    When searching, listing the inbox and reading the dashboard
    Then each answers from the data
    """
    _, planned, _, inbox = world
    assert [t["ref"] for t in ok(session, "search", term="INBOX")["tasks"]] == [inbox.ref]
    assert [t["ref"] for t in ok(session, "inbox")["tasks"]] == [inbox.ref]
    dashboard = ok(session, "dashboard")
    assert dashboard["inbox_count"] == 1 and dashboard["refine_count"] == 1 and dashboard["in_progress"] == []


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


def test_add_task_to_project_or_version(session, world):
    """
    Given a project and a version
    When adding tasks with and without a version
    Then one lands in the inbox and one is planned in the version
    """
    inbox = ok(session, "add_task", project="nx", title="A", context="@ordi", size="M", body="Detail")
    assert (inbox["state"], inbox["project"], inbox["version"]) == ("INBOX", "nx", None)
    assert (inbox["context"], inbox["size"], inbox["body"]) == ("@ordi", "M", "Detail")
    planned = ok(session, "add_task", project="nx", version="1.0", title="B")
    assert (planned["state"], planned["version"]) == ("PLANNED", "1.0")
    assert "doesn't exist" in refused(session, "add_task", project="ghost", title="C")


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
    Given a refined task and a version
    When planning, starting, blocking, unblocking and completing it through the tools
    Then it follows the state machine, each step logged by mcp
    """
    version, _, refined, _ = world
    states = [ok(session, name, **args)["state"] for name, args in [
        ("plan_task", {"ref": refined.ref, "version": version.ref}),
        ("start_task", {"ref": refined.ref}),
        ("block_task", {"ref": refined.ref, "reason": "waiting on X"}),
        ("unblock_task", {"ref": refined.ref}),
        ("complete_task", {"ref": refined.ref}),
    ]]
    assert states == ["PLANNED", "DOING", "WAITING", "DOING", "DONE"]
    assert {e.actor for e in events.history(session, "task", refined.id)[2:]} == {"mcp"}


def test_unplan_task_and_transition_errors(session, world):
    """
    Given a planned task and an inbox task
    When unplanning the first and starting the second
    Then the first goes back to refined and the second is refused with a message
    """
    _, planned, _, inbox = world
    assert ok(session, "unplan_task", ref=planned.ref)["state"] == "REFINED"
    assert "isn't planned" in refused(session, "start_task", ref=inbox.ref)
    assert "'reason' is required" in refused(session, "block_task", ref=planned.ref)


def test_set_criterion_done_by_index(session, world):
    """
    Given a version with two criteria
    When checking the second one, then using an out-of-range index
    Then it is checked, and the bad index is refused
    """
    version, _, _, _ = world
    shown = ok(session, "set_criterion_done", version=version.ref, index=2, done=True)
    assert [c["done"] for c in shown["definition_of_done"]] == [False, True]
    assert "between 1 and 2" in refused(session, "set_criterion_done", version=version.ref, index=3, done=True)
    assert _last_event(session).actor == events.ACTOR_MCP


def test_a_refused_write_leaves_no_partial_change(session, world):
    """
    Given a write refused by a service
    When it fails
    Then the session has no pending change left
    """
    _, _, _, inbox = world
    refused(session, "complete_task", ref=inbox.ref)
    assert not session.new and not session.dirty
