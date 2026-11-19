import json
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from src.mcp_server import serialize
from src.models.task import TaskState
from src.services import events, importer, projects, tasks, views
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

@tool("list_projects", "List projects.",
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


@tool("get_project", "Show a project or subproject and its subprojects.", {"project": _PROJECT}, ["project"], read_only=True)
def get_project(session : Session, args : dict) -> dict:
    """Show a project."""
    project = projects.get(session, args["project"])
    return {**serialize.project(project),
            "subprojects": [serialize.project(sub) for sub in project.subprojects]}


@tool("get_task", "Show a task with all its fields and its event history.", {"ref": _REF}, ["ref"], read_only=True)
def get_task(session : Session, args : dict) -> dict:
    """Show a task."""
    task = _task_of(session, args)
    return {**serialize.task(task),
            "history": [serialize.event(e) for e in events.history(session, "task", task.id)]}


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


@tool("add_task", "Create a task in a project's inbox.",
      {"project": _PROJECT, "title": _string("Task title."),
       "body": _string("Free-text detail."), "context": _string("Context tag, e.g. @ordi."),
       "size": _string("Effort size.", SIZES)},
      ["project", "title"])
def add_task(session : Session, args : dict) -> dict:
    """Create a task."""
    detail = {name: args.get(name) for name in ("body", "context", "size")}
    return serialize.task(tasks.create(session, args["title"], project_key=args["project"], actor=ACTOR, **detail))


@tool("import_data",
      "Import projects and tasks. Give either 'document' (JSON: {\"projects\": [{\"key\", \"name\", \"description\"}], "
      "\"tasks\": [{\"title\", \"body\", \"context\", \"size\", \"project\"}]}) or 'text' (one task title per line, "
      "into the inbox). Existing projects are reused, never overwritten; tasks are always created. All or nothing. "
      "Use dry_run first to check.",
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


@tool("update_task", "Change a task's title, body, context or size. A blank body, context or size clears it.",
      {"ref": _REF, "title": _string("New title."), "body": _string("New detail."),
       "context": _string("New context tag."), "size": _string("New size.", SIZES)},
      ["ref"], idempotent=True)
def update_task(session : Session, args : dict) -> dict:
    """Update a task's fields."""
    task = _task_of(session, args)
    fields = {name: args[name] for name in ("title", "body", "context", "size") if name in args}
    if not fields:
        raise ValidationError("give at least one field to change")
    if "title" in fields and fields["title"] is None:
        raise ValidationError("'title' must not be blank")
    return serialize.task(tasks.update(session, task.id, actor=ACTOR, **fields))


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
