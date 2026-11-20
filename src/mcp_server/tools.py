import json
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from src.mcp_server import serialize
from src.models.task import TaskKind, TaskState
from src.services import events, importer, projects, tasks, versioning, views
from src.services.errors import DomainError, ValidationError

# Who is recorded in the event log for changes made through a tool.
ACTOR = events.ACTOR_MCP

# Task sizes a tool accepts.
SIZES = ["XS", "S", "M", "L"]

# Rows a list tool returns when no limit is given, and the most it will return.
DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class UnknownTool(LookupError):
    """A tool was called that doesn't exist."""


@dataclass(frozen=True)
class Tool:
    """One callable tool."""

    name: str
    description: str
    # JSON Schema of the arguments (an object with no extra properties).
    schema: dict
    # (session, validated arguments) -> JSON-serialisable dict.
    handler: Callable[[Session, dict], dict]
    # True if the tool never changes anything.
    read_only: bool = False
    # True if calling it twice with the same arguments changes nothing more.
    idempotent: bool = False
    # True if it removes data rather than only adding or changing it.
    destructive: bool = False


# Every tool by name, filled by the @tool decorator below.
TOOLS: dict[str, Tool] = {}


# -----------------------------------------------------------------------------
# Argument schemas and validation
# -----------------------------------------------------------------------------

def _string(description : str, enum : list[str] | None = None) -> dict:
    """Schema of a string argument."""
    return {"type": "string", "description": description, **({"enum": enum} if enum else {})}


def _integer(description : str) -> dict:
    """Schema of an integer argument."""
    return {"type": "integer", "description": description}


def _boolean(description : str) -> dict:
    """Schema of a boolean argument."""
    return {"type": "boolean", "description": description}


def _object(description : str) -> dict:
    """Schema of a free-form object argument."""
    return {"type": "object", "description": description}


# Python types accepted for each schema type (bool is not an integer here).
_TYPES = {"string": str, "integer": int, "boolean": bool, "object": dict}


def validate(arguments : object, schema : dict) -> dict:
    """Check arguments against a tool's schema and normalise them.

    Args:
        arguments: The arguments as received.
        schema: The tool's input schema.

    Returns:
        The arguments with strings stripped; a blank optional string becomes
        None (so a field can be cleared).

    Raises:
        ValidationError: If arguments aren't an object, one is unknown,
            required or mistyped, a required string is blank, or a value is
            outside its enum.
    """
    if not isinstance(arguments, dict):
        raise ValidationError("arguments must be an object")
    properties = schema["properties"]

    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        raise ValidationError(f"unknown argument(s): {', '.join(unknown)}")

    cleaned = {}
    for name, spec in properties.items():
        required = name in schema.get("required", [])
        if arguments.get(name) is None:
            if required:
                raise ValidationError(f"'{name}' is required")
            continue
        value = arguments[name]
        expected = _TYPES[spec["type"]]
        if not isinstance(value, expected) or (expected is int and isinstance(value, bool)):
            raise ValidationError(f"'{name}' must be of type {spec['type']}")
        if isinstance(value, str):
            value = value.strip()
            if not value and required:
                raise ValidationError(f"'{name}' must not be blank")
            value = value or None
        if value is not None and "enum" in spec and value not in spec["enum"]:
            raise ValidationError(f"'{name}' must be one of {', '.join(spec['enum'])}")
        cleaned[name] = value
    return cleaned


def tool(name : str, description : str, properties : dict | None = None, required : list[str] | None = None,
         read_only : bool = False, idempotent : bool = False, destructive : bool = False) -> Callable:
    """Register a function as a tool.

    Args:
        name: Tool name.
        description: What the tool does, written for the assistant that reads it.
        properties: Schema of each argument, by name.
        required: Names of the required arguments.
        read_only: Whether the tool never changes anything.
        idempotent: Whether repeating the call changes nothing more.
        destructive: Whether the tool removes data.
    """
    def register(handler : Callable[[Session, dict], dict]) -> Callable:
        schema = {"type": "object", "properties": properties or {}, "additionalProperties": False}
        if required:
            schema["required"] = required
        TOOLS[name] = Tool(name, description, schema, handler, read_only, idempotent, destructive)
        return handler
    return register


# -----------------------------------------------------------------------------
# Shared argument handling
# -----------------------------------------------------------------------------

# Argument schemas reused by several tools.
_REF = _string("Feature or task ref, e.g. f-4k2 or t-4k2.")
_PROJECT = _string("Project key.")


def _limit(args : dict) -> int:
    """The row limit of a list tool, defaulted and capped."""
    return min(args.get("limit") or DEFAULT_LIMIT, MAX_LIMIT)


def _task_of(session : Session, args : dict):
    """The task named by the 'ref' argument."""
    return tasks.get_by_ref(session, args["ref"])


def _listing(name : str, items : list, limit : int | None = None) -> dict:
    """A list result: the items, how many, and whether a limit cut it short."""
    return {name: items, "count": len(items), "truncated": limit is not None and len(items) == limit}


# -----------------------------------------------------------------------------
# Read tools
# -----------------------------------------------------------------------------

@tool("list_projects", "List projects and subprojects, each with its version.",
      {"include_archived": _boolean("Also list archived projects (default false).")}, read_only=True)
def list_projects(session : Session, args : dict) -> dict:
    """List projects."""
    items = projects.list(session, include_archived=bool(args.get("include_archived")))
    return _listing("projects", [serialize.project(p) for p in items])


@tool("list_tasks", "List features and tasks, oldest first, optionally filtered. With a limit, the most recent ones are kept.",
      {"state": _string("Only items in this state.", [s.name for s in TaskState]),
       "project": _string("Only items of this project or subproject (key)."),
       "limit": _integer(f"Most items to return (default {DEFAULT_LIMIT}, max {MAX_LIMIT}).")},
      read_only=True)
def list_tasks(session : Session, args : dict) -> dict:
    """List tasks."""
    limit = _limit(args)
    states = [TaskState[args["state"]]] if args.get("state") else None
    items = views.list_tasks(session, states=states, project_key=args.get("project"), limit=limit)
    return _listing("tasks", [serialize.task_brief(t) for t in items], limit)


@tool("get_project",
      "Show a project or subproject: its version, its criteria for the next major version, its subprojects and its "
      "work tree (features with nested 'children', and tasks). Done and cancelled items are left out unless "
      "include_closed is true.",
      {"project": _PROJECT,
       "include_closed": _boolean("Also show done and cancelled items (default false).")},
      ["project"], read_only=True)
def get_project(session : Session, args : dict) -> dict:
    """Show a project with its version, criteria, subprojects and tree."""
    project = projects.get(session, args["project"])
    nodes = views.project_tree(project, include_closed=bool(args.get("include_closed")))
    return {**serialize.project(project),
            "criteria": serialize.criteria(project.criteria),
            "subprojects": [serialize.project(sub) for sub in project.subprojects],
            "tree": serialize.tree(nodes)}


@tool("get_task",
      "Show a feature or task with all its fields and its event history; a feature also lists its direct children "
      "(done and cancelled included).",
      {"ref": _REF}, ["ref"], read_only=True)
def get_task(session : Session, args : dict) -> dict:
    """Show a task, and a feature's direct children."""
    task = _task_of(session, args)
    result = {**serialize.task(task),
              "history": [serialize.event(e) for e in events.history(session, "task", task.id)]}
    if task.kind is TaskKind.FEATURE:
        result["children"] = [serialize.task_brief(child) for child in task.children]
    return result


@tool("inbox", "List captured tasks still to triage, oldest first.", read_only=True)
def inbox(session : Session, args : dict) -> dict:
    """List the inbox."""
    return _listing("tasks", [serialize.task_brief(t) for t in views.inbox(session)])


@tool("search", "Search tasks by a substring of their title or body.",
      {"term": _string("Text to look for, case-insensitive."),
       "limit": _integer(f"Most tasks to return (default {DEFAULT_LIMIT}, max {MAX_LIMIT}).")},
      ["term"], read_only=True)
def search(session : Session, args : dict) -> dict:
    """Search tasks."""
    limit = _limit(args)
    return _listing("tasks", [serialize.task_brief(t) for t in views.search(session, args["term"], limit)], limit)


@tool("dashboard", "Overview: items being worked on or waiting, inbox and refine counts.",
      read_only=True)
def dashboard(session : Session, args : dict) -> dict:
    """Show the dashboard."""
    return serialize.dashboard(views.dashboard(session))


# -----------------------------------------------------------------------------
# Write tools
# -----------------------------------------------------------------------------

@tool("capture_task", "Capture a task into the inbox, with just a title.", {"title": _string("Task title.")}, ["title"])
def capture_task(session : Session, args : dict) -> dict:
    """Capture a task."""
    return serialize.task(tasks.capture(session, args["title"], actor=ACTOR))


# Item kinds as the tools take them, mapped to the model's.
_KINDS = {"task": TaskKind.TASK, "feature": TaskKind.FEATURE}
_KIND = _string("Item kind.", list(_KINDS))
_PARENT = _string("Ref of the feature it goes under, e.g. f-4k2.")


@tool("add_task",
      "Add a feature or task to a project's tree, in the inbox state: placed, still to refine (clarify_task "
      "refines it). For a bare capture with no project, use capture_task. "
      "Give the project, the parent feature, or both; with only a parent, its project is used.",
      {"project": _PROJECT, "parent": _PARENT, "title": _string("Item title."),
       "kind": _string("Item kind (default task).", list(_KINDS)),
       "body": _string("Free-text detail."), "context": _string("Context tag, e.g. @ordi."),
       "size": _string("Effort size.", SIZES)},
      ["title"])
def add_task(session : Session, args : dict) -> dict:
    """Add an item to a project's tree."""
    detail = {name: args.get(name) for name in ("body", "context", "size")}
    return serialize.task(tasks.add_to_tree(
        session, args["title"], project_key=args.get("project"), parent_ref=args.get("parent"),
        kind=_KINDS[args.get("kind") or "task"], actor=ACTOR, **detail))


@tool("clarify_task",
      "Triage a captured (inbox) or someday item into a refined one, placed in a project's tree. Fields left out keep "
      "their current value; give project and/or parent to place it, kind to turn it into a feature.",
      {"ref": _REF, "title": _string("New title."), "project": _PROJECT, "parent": _PARENT, "kind": _KIND,
       "body": _string("Free-text detail."), "context": _string("Context tag, e.g. @ordi."),
       "size": _string("Effort size.", SIZES)},
      ["ref"])
def clarify_task(session : Session, args : dict) -> dict:
    """Clarify an inbox or someday item."""
    task = _task_of(session, args)
    project = args.get("project")
    parent = args.get("parent")
    if project is None and parent is None:
        # Neither given: the item keeps its current place.
        project = task.project.key if task.project else None
        parent = task.parent.ref if task.parent else None
    return serialize.task(tasks.clarify(
        session, task.id,
        args.get("title") or task.title,
        args["body"] if "body" in args else task.body,
        project,
        args["context"] if "context" in args else task.context,
        args["size"] if "size" in args else task.size,
        parent_ref=parent,
        kind=_KINDS[args["kind"]] if args.get("kind") else None,
        actor=ACTOR))


@tool("move_task",
      "Move a feature (with its whole subtree) or a task: to the top of a project, or under a feature. It keeps its "
      "state.",
      {"ref": _REF, "project": _PROJECT, "parent": _PARENT}, ["ref"])
def move_task(session : Session, args : dict) -> dict:
    """Move an item in the tree."""
    task = _task_of(session, args)
    return serialize.task(tasks.move(session, task.id, project_key=args.get("project"),
                                     parent_ref=args.get("parent"), actor=ACTOR))


@tool("change_kind",
      "Turn a task into a feature, or an empty feature into a task. The ref's letter follows (t-4k2 <-> f-4k2).",
      {"ref": _REF, "kind": _KIND}, ["ref", "kind"])
def change_kind(session : Session, args : dict) -> dict:
    """Change an item's kind."""
    task = _task_of(session, args)
    return serialize.task(tasks.change_kind(session, task.id, _KINDS[args["kind"]], actor=ACTOR))


@tool("reorder_task",
      "Move an item one place up or down among its siblings. An open item skips done and cancelled siblings.",
      {"ref": _REF, "direction": _string("Where to move it.", ["up", "down"])}, ["ref", "direction"])
def reorder_task(session : Session, args : dict) -> dict:
    """Move an item among its siblings."""
    task = _task_of(session, args)
    return serialize.task(tasks.reorder(session, task.id, args["direction"], actor=ACTOR))


@tool("import_data",
      "Import projects, subprojects, features and tasks. Give either 'document' (JSON: {\"projects\": [{\"key\", "
      "\"name\", \"description\", \"items\": [ITEM], \"subprojects\": [{\"key\", \"name\", \"items\": [ITEM]}]}], "
      "\"tasks\": [{\"title\", \"body\", \"context\", \"size\", \"project\"}]}, where ITEM is {\"kind\": \"feature\" or "
      "\"task\" (default), \"title\", \"body\", \"context\", \"size\", \"children\": [ITEM] (features only)}) or 'text' "
      "(one task title per line, into the inbox). Existing projects are reused, never overwritten; items are always "
      "created, refined in their tree; loose tasks land in the inbox. All or nothing. Use dry_run first to check.",
      {"document": _object("The import document."), "text": _string("Plain list, one task title per line."),
       "dry_run": _boolean("Validate and report without writing anything.")})
def import_data(session : Session, args : dict) -> dict:
    """Import a document or a text list."""
    if (args.get("document") is None) == (args.get("text") is None):
        raise ValidationError("give exactly one of 'document' or 'text'")
    data = args["document"] if args.get("document") is not None else importer.parse_text(args["text"])
    result = importer.apply(session, data, ACTOR, dry_run=bool(args.get("dry_run")))
    return {"dry_run": result.dry_run,
            "projects_created": result.projects_created, "projects_reused": result.projects_reused,
            "tasks_created": result.tasks_created,
            "created": [{"kind": kind, "ref": ref, "title": title} for kind, ref, title in result.created]}


@tool("update_task",
      "Change a task's title, body, context or size. A blank body, context or size clears it. Set correction to "
      "true when the change only fixes a mistake (typo, wrong size), not the work itself.",
      {"ref": _REF, "title": _string("New title."), "body": _string("New detail."),
       "context": _string("New context tag."), "size": _string("New size.", SIZES),
       "correction": _boolean("The change fixes a mistake; logged as 'corrected' (default false).")},
      ["ref"], idempotent=True)
def update_task(session : Session, args : dict) -> dict:
    """Update a task's fields, as a change or a correction."""
    task = _task_of(session, args)
    fields = {name: args[name] for name in ("title", "body", "context", "size") if name in args}
    if not fields:
        raise ValidationError("give at least one field to change")
    if "title" in fields and fields["title"] is None:
        raise ValidationError("'title' must not be blank")
    return serialize.task(tasks.update(session, task.id, actor=ACTOR,
                                       correction=bool(args.get("correction")), **fields))


def _transition(name : str, description : str, action : Callable, extra : dict | None = None,
                required : list[str] | None = None) -> None:
    """Register a tool that moves a task with one lifecycle function.

    Args:
        name: Tool name.
        description: Tool description.
        action: The tasks.* function, called as action(session, id, actor=..., **extra arguments).
        extra: Schema of the arguments besides 'ref'.
        required: Required arguments besides 'ref'.
    """
    def handler(session : Session, args : dict) -> dict:
        others = {key: value for key, value in args.items() if key != "ref"}
        return serialize.task(action(session, _task_of(session, args).id, actor=ACTOR, **others))
    tool(name, description, {"ref": _REF, **(extra or {})}, ["ref", *(required or [])])(handler)


_transition("start_task", "Start working on a refined task (refined to doing).", tasks.start)
_transition("complete_task", "Mark a task in progress as done. A feature closes only once its children are done or cancelled.",
            tasks.complete)
_transition("block_task", "Mark a task in progress as waiting on something.", tasks.block,
            {"reason": _string("What the task is waiting for.")}, ["reason"])
_transition("unblock_task", "Resume a waiting task (waiting to doing).", tasks.unblock)
_transition("reopen_task", "Reopen a done item (done to doing). A reopened feature keeps the version it shipped in.",
            tasks.reopen)
_transition("cancel_task", "Cancel an open item that won't be done. A feature only once its children are closed.",
            tasks.cancel)
_transition("restore_task", "Bring a cancelled item back to refined.", tasks.restore)
_transition("defer_task", "Defer an inbox or refined item to someday.", tasks.defer)
_transition("unstart_task", "Put a doing or waiting item back to refined; a waiting one loses its reason.",
            tasks.unstart)
_transition("unrefine_task", "Put a refined item back to inbox, to refine again; it keeps its place.",
            tasks.unrefine)

# States set_state can reach.
_SETTABLE_STATES = ["INBOX", "REFINED", "DOING", "WAITING", "DONE", "CANCELLED"]


@tool("set_state",
      "Move an item to any of these states, chaining the lifecycle steps on the way (e.g. inbox to done is "
      "refined, started, then completed; each step is logged). WAITING needs a reason.",
      {"ref": _REF, "state": _string("Target state.", _SETTABLE_STATES),
       "reason": _string("What the item waits for; only for WAITING.")},
      ["ref", "state"])
def set_state(session : Session, args : dict) -> dict:
    """Move an item to a target state, through as many steps as needed."""
    task = _task_of(session, args)
    return serialize.task(tasks.change_state(session, task.id, TaskState[args["state"]],
                                             args.get("reason") or "", actor=ACTOR))


# -----------------------------------------------------------------------------
# Project and version tools
# -----------------------------------------------------------------------------

@tool("create_project",
      "Create a root project, or a subproject when 'parent' (a root project's key) is given. The key is short, "
      "unique and can't change later.",
      {"key": _string("Unique short key, e.g. nexus."), "name": _string("Display name."),
       "description": _string("Free-text description."),
       "parent": _string("Key of the root project to create a subproject under."),
       "directory": _string("Absolute path of the project's folder on this machine (~ is expanded).")},
      ["key", "name"])
def create_project(session : Session, args : dict) -> dict:
    """Create a project or subproject."""
    return serialize.project(projects.create(session, args["key"], args["name"], args.get("description"),
                                             parent_key=args.get("parent"), directory=args.get("directory"),
                                             actor=ACTOR))


@tool("update_project",
      "Change a project's name, description and/or directory. A blank description or directory clears it.",
      {"project": _PROJECT, "name": _string("New display name."), "description": _string("New description."),
       "directory": _string("New absolute folder path (~ is expanded).")},
      ["project"], idempotent=True)
def update_project(session : Session, args : dict) -> dict:
    """Change a project's name, description or directory."""
    project = projects.get(session, args["project"])
    if not {"name", "description", "directory"} & set(args):
        raise ValidationError("give at least one field to change")
    if "name" in args and args["name"] is None:
        raise ValidationError("'name' must not be blank")
    name = args.get("name") or project.name
    description = args["description"] if "description" in args else project.description
    directory = args["directory"] if "directory" in args else projects.KEEP
    return serialize.project(projects.update(session, project.key, name, description, directory=directory,
                                             actor=ACTOR))


# Schema of the argument numbering a criterion.
_NUMBER = _integer("Criterion number, from 1, as listed by get_project.")


def _criterion_at(session : Session, args : dict):
    """The criterion of the 'project' argument at position 'number', counted from 1."""
    project = projects.get(session, args["project"])
    number = args["number"]
    if not 1 <= number <= len(project.criteria):
        raise ValidationError(
            f"project '{project.key}' has no criterion {number} (it has {len(project.criteria)}).")
    return project.criteria[number - 1]


def _criteria_result(session : Session, key : str) -> dict:
    """A project's version and criteria, the result of every criterion tool."""
    project = projects.get(session, key)
    return {"project": project.key, "version": versioning.label(project),
            "criteria": serialize.criteria(project.criteria)}


@tool("add_criterion", "Append a criterion for a project's next major version.",
      {"project": _PROJECT, "text": _string("What must be true before the next major version.")},
      ["project", "text"])
def add_criterion(session : Session, args : dict) -> dict:
    """Append a criterion."""
    versioning.add_criterion(session, args["project"], args["text"], actor=ACTOR)
    return _criteria_result(session, args["project"])


@tool("update_criterion", "Change the text of one criterion for a project's next major version.",
      {"project": _PROJECT, "number": _NUMBER, "text": _string("New text.")},
      ["project", "number", "text"], idempotent=True)
def update_criterion(session : Session, args : dict) -> dict:
    """Change a criterion's text."""
    versioning.update_criterion(session, _criterion_at(session, args).id, args["text"], actor=ACTOR)
    return _criteria_result(session, args["project"])


@tool("set_criterion_done", "Check or uncheck one criterion for a project's next major version.",
      {"project": _PROJECT, "number": _NUMBER, "done": _boolean("True to check it, false to uncheck it.")},
      ["project", "number", "done"], idempotent=True)
def set_criterion_done(session : Session, args : dict) -> dict:
    """Check or uncheck a criterion."""
    versioning.set_criterion_done(session, _criterion_at(session, args).id, args["done"], actor=ACTOR)
    return _criteria_result(session, args["project"])


@tool("delete_criterion",
      "Remove one criterion for a project's next major version. The numbers of the following criteria shift down "
      "by one.",
      {"project": _PROJECT, "number": _NUMBER}, ["project", "number"], destructive=True)
def delete_criterion(session : Session, args : dict) -> dict:
    """Remove a criterion."""
    versioning.delete_criterion(session, _criterion_at(session, args).id, actor=ACTOR)
    return _criteria_result(session, args["project"])


@tool("release_major",
      "Move a project to its next major version: MAJOR + 1, MINOR back to 0, criteria list emptied. Refused unless "
      "it has criteria and every one is checked. MINOR goes up by itself each time a feature is completed.",
      {"project": _PROJECT}, ["project"])
def release_major(session : Session, args : dict) -> dict:
    """Release the next major version."""
    versioning.release_major(session, args["project"], actor=ACTOR)
    return _criteria_result(session, args["project"])


def list_tools() -> list[dict]:
    """Describe every tool the way MCP's tools/list does."""
    return [{"name": t.name,
             "description": t.description,
             "inputSchema": t.schema,
             "annotations": {"readOnlyHint": t.read_only,
                             **({} if t.read_only else {"destructiveHint": t.destructive, "idempotentHint": t.idempotent}),
                             "openWorldHint": False}}
            for t in TOOLS.values()]


def failure(message : str) -> dict:
    """A tool result reporting a failure the assistant can read and react to."""
    return {"content": [{"type": "text", "text": message}], "isError": True}


def call_tool(session : Session, name : str, arguments : object) -> dict:
    """Run a tool and shape its outcome as an MCP tool result.

    Args:
        session: Database session to use.
        name: Tool name.
        arguments: The arguments as received (validated here).

    Returns:
        {"content", "structuredContent", "isError": False} on success. A
        refusal by the arguments check or by a service comes back as
        {"content", "isError": True} with its message, after rolling back.

    Raises:
        UnknownTool: If no tool has this name.
    """
    if name not in TOOLS:
        raise UnknownTool(name)
    found = TOOLS[name]
    try:
        data = found.handler(session, validate({} if arguments is None else arguments, found.schema))
    except DomainError as error:
        session.rollback()
        return failure(str(error))
    except Exception:
        session.rollback()
        raise
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
            "structuredContent": data,
            "isError": False}
