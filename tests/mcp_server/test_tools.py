import json
from types import SimpleNamespace

import pytest

from src.mcp_server import tools
from src.models.event import Event
from src.models.task import Task, TaskKind
from src.services import events, projects, tasks


def call(session, name, /, **arguments):
    """Call a tool and return its raw MCP result (positional-only, so a tool may take a 'name' argument)."""
    return tools.call_tool(session, name, arguments)


def ok(session, name, /, **arguments):
    """Call a tool that must succeed; return its structured data."""
    result = call(session, name, **arguments)
    assert result["isError"] is False, result["content"][0]["text"]
    return result["structuredContent"]


def refused(session, name, /, **arguments):
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
    (only delete_criterion removes data)
    """
    listed = tools.list_tools()
    assert len(listed) == len(tools.TOOLS) == 30
    for item in listed:
        assert item["description"]
        assert item["inputSchema"]["type"] == "object" and item["inputSchema"]["additionalProperties"] is False
        assert set(item["inputSchema"].get("required", [])) <= set(item["inputSchema"]["properties"])
        hints = item["annotations"]
        assert hints["readOnlyHint"] == tools.TOOLS[item["name"]].read_only
        assert ("destructiveHint" in hints) == (not hints["readOnlyHint"])
        assert hints.get("destructiveHint", False) is (item["name"] == "delete_criterion")


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
                                     "description": None, "status": "ACTIVE", "version": "0.0",
                                     "directory": None, "effective_directory": None}]
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
    Then the first is refined at the top of the project and the second is refused
    """
    added = ok(session, "add_task", project="nx", title="A", context="@ordi", size="M", body="Detail")
    assert (added["state"], added["project"], added["parent"], added["kind"]) == ("REFINED", "nx", None, "TASK")
    assert (added["context"], added["size"], added["body"]) == ("@ordi", "M", "Detail")
    assert "doesn't exist" in refused(session, "add_task", project="ghost", title="C")
    assert "unknown argument(s): version" in refused(session, "add_task", project="nx", title="B", version="1.0")


def test_add_task_as_a_feature_or_under_a_parent(session, world):
    """A feature is added at the top; a task under it by parent alone takes its project."""
    feature = ok(session, "add_task", project="nx", title="Auth", kind="feature")
    child = ok(session, "add_task", parent=feature["ref"], title="Login")
    assert feature["kind"] == "FEATURE" and feature["ref"].startswith("f-")
    assert (child["parent"], child["project"], child["state"]) == (feature["ref"], "nx", "REFINED")
    assert "give a project" in refused(session, "add_task", title="Nowhere")


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
    ("clarify_task", lambda w: {"ref": w.inbox.ref, "project": "nx"}),
    ("move_task", lambda w: {"ref": w.refined.ref, "parent": w.planned.parent.ref}),
    ("change_kind", lambda w: {"ref": w.refined.ref, "kind": "feature"}),
    ("reorder_task", lambda w: {"ref": w.refined.ref, "direction": "up"}),
    ("reopen_task", lambda w: {"ref": w.done.ref}),
    ("cancel_task", lambda w: {"ref": w.refined.ref}),
    ("restore_task", lambda w: {"ref": w.cancelled.ref}),
    ("defer_task", lambda w: {"ref": w.refined.ref}),
    ("create_project", lambda w: {"key": "new", "name": "New"}),
    ("update_project", lambda w: {"project": "nx", "name": "Renamed"}),
    ("add_criterion", lambda w: {"project": "nx", "text": "Tests green"}),
    ("update_criterion", lambda w: {"project": "nx", "number": 1, "text": "Docs built"}),
    ("set_criterion_done", lambda w: {"project": "nx", "number": 1, "done": True}),
    ("delete_criterion", lambda w: {"project": "nx", "number": 1}),
    ("release_major", lambda w: {"project": "nx"}),
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
    _, planned, refined, inbox = world
    doing = tasks.create(session, "Doing", "nx")
    tasks.clarify(session, doing.id, "Doing", None, "nx", None, None)
    tasks.start(session, doing.id)
    waiting = tasks.create(session, "Waiting", "nx")
    tasks.clarify(session, waiting.id, "Waiting", None, "nx", None, None)
    tasks.start(session, waiting.id)
    tasks.block(session, waiting.id, "why")
    done = tasks.add_to_tree(session, "Done", project_key="nx")
    tasks.start(session, done.id)
    tasks.complete(session, done.id)
    cancelled = tasks.add_to_tree(session, "Cancelled", project_key="nx")
    tasks.cancel(session, cancelled.id)
    from src.services import versioning
    criterion = versioning.add_criterion(session, "nx", "Ready")
    versioning.set_criterion_done(session, criterion.id, True)
    known = SimpleNamespace(planned=planned, refined=refined, doing=doing, waiting=waiting,
                            inbox=inbox, done=done, cancelled=cancelled)
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


# Project tree, version and children ----------------------------------------------------------------

def test_get_project_gives_version_criteria_and_tree(session, world):
    """
    Given the world project with a criterion and a cancelled top task
    When getting it, then with include_closed
    Then it shows its version, numbered criteria and nested tree, closed items only on request
    """
    from src.services import versioning

    sub, planned, refined, inbox = world
    versioning.add_criterion(session, "nx", "Tests green")
    tasks.cancel(session, refined.id)

    shown = ok(session, "get_project", project="nx")
    assert shown["version"] == "0.0"
    assert shown["criteria"] == [{"number": 1, "text": "Tests green", "done": False}]
    assert [s["key"] for s in shown["subprojects"]] == ["v2"]
    (feature,) = shown["tree"]
    assert feature["kind"] == "FEATURE" and [c["ref"] for c in feature["children"]] == [planned.ref]
    assert not _id_keys(shown)

    with_closed = ok(session, "get_project", project="nx", include_closed=True)
    assert [node["title"] for node in with_closed["tree"]] == ["Tree", "Refined task"]


def test_get_task_lists_a_feature_children_only_for_features(session, world):
    """A feature shows its direct children; a task has no children field."""
    sub, planned, refined, inbox = world
    feature = ok(session, "get_task", ref=planned.parent.ref)
    assert [c["ref"] for c in feature["children"]] == [planned.ref]
    assert "children" not in ok(session, "get_task", ref=planned.ref)


def test_list_projects_gives_versions(session, world):
    """Every listed project carries its version."""
    listed = ok(session, "list_projects")
    assert {p["key"]: p["version"] for p in listed["projects"]} == {"nx": "0.0", "v2": "0.0"}



# Tree and state write tools ------------------------------------------------------------------------

def test_clarify_task_turns_a_capture_into_a_feature_under_a_parent(session, world):
    """
    Given an inbox capture
    When it is clarified as a feature under the world's feature, with a size
    Then it is a refined feature there, its title kept
    """
    sub, planned, refined, inbox = world
    clarified = ok(session, "clarify_task", ref=inbox.ref, parent=planned.parent.ref, kind="feature", size="L")
    assert (clarified["kind"], clarified["state"], clarified["parent"]) == ("FEATURE", "REFINED", planned.parent.ref)
    assert (clarified["title"], clarified["size"], clarified["project"]) == ("Inbox task", "L", "nx")


def test_clarify_task_refuses_a_refined_item(session, world):
    """Only inbox and someday items can be clarified."""
    _, _, refined, _ = world
    assert "isn't inbox or someday" in refused(session, "clarify_task", ref=refined.ref, project="nx")


def test_move_and_change_kind_and_reorder(session, world):
    """An item moves under a feature, becomes a feature, and goes up among its siblings."""
    sub, planned, refined, inbox = world
    feature_ref = planned.parent.ref
    moved = ok(session, "move_task", ref=refined.ref, parent=feature_ref)
    assert moved["parent"] == feature_ref

    changed = ok(session, "change_kind", ref=moved["ref"], kind="feature")
    assert changed["kind"] == "FEATURE" and changed["ref"].startswith("f-")

    ok(session, "reorder_task", ref=changed["ref"], direction="up")
    shown = ok(session, "get_task", ref=feature_ref)
    assert [c["title"] for c in shown["children"]] == ["Refined task", "Planned task"]
    assert "already first" in refused(session, "reorder_task", ref=changed["ref"], direction="up")


def test_cancel_restore_defer_reopen(session, world):
    """The state tools move an item through cancelled, refined, someday, and done back to doing."""
    _, planned, refined, _ = world
    assert ok(session, "cancel_task", ref=refined.ref)["state"] == "CANCELLED"
    assert ok(session, "restore_task", ref=refined.ref)["state"] == "REFINED"
    assert ok(session, "defer_task", ref=refined.ref)["state"] == "SOMEDAY"

    ok(session, "start_task", ref=planned.ref)
    ok(session, "complete_task", ref=planned.ref)
    assert ok(session, "reopen_task", ref=planned.ref)["state"] == "DOING"
    assert "isn't done" in refused(session, "reopen_task", ref=planned.ref)



# Project and version tools -------------------------------------------------------------------------

def test_create_project_and_subproject_then_update(session):
    """A root project and its subproject are created; the root's name and description change."""
    root = ok(session, "create_project", key="nx", name="Nexus", description="Manager")
    sub = ok(session, "create_project", key="web", name="Web", parent="nx")
    assert (root["version"], root["parent"]) == ("0.0", None)
    assert (sub["parent"], sub["ref"][:2]) == ("nx", "s-")
    assert "already exists" in refused(session, "create_project", key="nx", name="Again")

    renamed = ok(session, "update_project", project="nx", name="Nexus 2")
    assert (renamed["name"], renamed["description"]) == ("Nexus 2", "Manager")
    cleared = ok(session, "update_project", project="nx", description="")
    assert (cleared["name"], cleared["description"]) == ("Nexus 2", None)
    assert "at least one field" in refused(session, "update_project", project="nx")


def test_criteria_by_number_then_major_release(session):
    """
    Given a project at 0.1 with two criteria
    When the second is checked, the first deleted, and the major released
    Then numbers shift, the release is refused until all are checked, and the project ends at 1.0
    """
    ok(session, "create_project", key="nx", name="Nexus")
    feature = ok(session, "add_task", project="nx", title="Auth", kind="feature")
    ok(session, "start_task", ref=feature["ref"])
    ok(session, "complete_task", ref=feature["ref"])

    ok(session, "add_criterion", project="nx", text="Tests green")
    result = ok(session, "add_criterion", project="nx", text="Docs built")
    assert result == {"project": "nx", "version": "0.1", "criteria": [
        {"number": 1, "text": "Tests green", "done": False},
        {"number": 2, "text": "Docs built", "done": False}]}

    ok(session, "set_criterion_done", project="nx", number=2, done=True)
    assert "unchecked criteria" in refused(session, "release_major", project="nx")
    result = ok(session, "delete_criterion", project="nx", number=1)
    assert result["criteria"] == [{"number": 1, "text": "Docs built", "done": True}]
    assert "no criterion 3" in refused(session, "update_criterion", project="nx", number=3, text="X")

    released = ok(session, "release_major", project="nx")
    assert (released["version"], released["criteria"]) == ("1.0", [])


def test_project_directory_through_create_and_update(session):
    """A directory is set on creation, inherited by a subproject, kept, then cleared."""
    root = ok(session, "create_project", key="nx", name="Nexus", directory="/srv/nexus/")
    sub = ok(session, "create_project", key="web", name="Web", parent="nx")
    assert (root["directory"], sub["directory"], sub["effective_directory"]) == ("/srv/nexus", None, "/srv/nexus")
    assert "absolute" in refused(session, "update_project", project="nx", directory="relative/path")

    assert ok(session, "update_project", project="nx", name="Nexus 2")["directory"] == "/srv/nexus"
    assert ok(session, "update_project", project="nx", directory="")["directory"] is None


def test_update_task_as_a_correction(session, world):
    """With correction, the change is logged as corrected."""
    _, planned, _, _ = world
    ok(session, "update_task", ref=planned.ref, title="Planned task!", correction=True)
    assert _last_event(session).action == "corrected"
    ok(session, "update_task", ref=planned.ref, size="M")
    assert _last_event(session).action == "updated"
