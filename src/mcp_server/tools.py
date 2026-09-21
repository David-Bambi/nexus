import json
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from src.mcp_server import serialize
from src.models.task import TaskState
from src.services import events, importer, projects, refs, tasks, versions, views
from src.services.errors import DomainError, ValidationError
from src.services.resolve import resolve_version

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
         read_only : bool = False, idempotent : bool = False) -> Callable:
    """Register a function as a tool.

    Args:
        name: Tool name.
        description: What the tool does, written for the assistant that reads it.
        properties: Schema of each argument, by name.
        required: Names of the required arguments.
        read_only: Whether the tool never changes anything.
        idempotent: Whether repeating the call changes nothing more.
    """
    def register(handler : Callable[[Session, dict], dict]) -> Callable:
        schema = {"type": "object", "properties": properties or {}, "additionalProperties": False}
        if required:
            schema["required"] = required
        TOOLS[name] = Tool(name, description, schema, handler, read_only, idempotent)
        return handler
    return register


# -----------------------------------------------------------------------------
# Shared argument handling
# -----------------------------------------------------------------------------

# Argument schemas reused by several tools.
_REF = _string("Task ref, e.g. t-4k2.")
_VERSION = _string("Version ref (v-9xa), or its number (e.g. 1.2.0) together with 'project'.")
_PROJECT = _string("Project key.")


def _limit(args : dict) -> int:
    """The row limit of a list tool, defaulted and capped."""
    return min(args.get("limit") or DEFAULT_LIMIT, MAX_LIMIT)


def _version_of(session : Session, args : dict):
    """The version named by the 'version' argument, by ref or by number within 'project'.

    Raises:
        ValidationError: If a number is given without a project.
        NotFoundError: If no such version exists.
    """
    reference, project = args["version"], args.get("project")
    if project:
        return resolve_version(session, project, reference)
    if not refs.is_ref(reference):
        raise ValidationError("'project' is required when the version is given by number")
    return versions.get_by_ref(session, reference)


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


@tool("list_versions", "List versions, of one project or of all projects.",
      {"project": _PROJECT}, read_only=True)
def list_versions(session : Session, args : dict) -> dict:
    """List versions."""
    items = versions.list(session, args["project"]) if args.get("project") else versions.list_all(session)
    return _listing("versions", [serialize.version_brief(v) for v in items])


@tool("list_tasks", "List tasks, oldest first, optionally filtered. With a limit, the most recent ones are kept.",
      {"state": _string("Only tasks in this state.", [s.name for s in TaskState]),
       "project": _string("Only tasks of this project (key). Also needed to name a version by number."),
       "version": _VERSION,
       "limit": _integer(f"Most tasks to return (default {DEFAULT_LIMIT}, max {MAX_LIMIT}).")},
      read_only=True)
def list_tasks(session : Session, args : dict) -> dict:
    """List tasks."""
    limit = _limit(args)
    states = [TaskState[args["state"]]] if args.get("state") else None
    version = _version_of(session, args) if args.get("version") else None
    items = views.list_tasks(session, states=states, project_key=args.get("project"),
                             version_id=version.id if version else None, limit=limit)
    return _listing("tasks", [serialize.task_brief(t) for t in items], limit)


@tool("get_project", "Show a project and its versions.", {"project": _PROJECT}, ["project"], read_only=True)
def get_project(session : Session, args : dict) -> dict:
    """Show a project."""
    project = projects.get(session, args["project"])
    return {**serialize.project(project),
            "versions": [serialize.version_brief(v) for v in versions.list(session, project.key)]}


@tool("get_version", "Show a version: its tasks and its definition-of-done checklist (criteria numbered from 1).",
      {"version": _VERSION, "project": _PROJECT}, ["version"], read_only=True)
def get_version(session : Session, args : dict) -> dict:
    """Show a version."""
    version = _version_of(session, args)
    return serialize.version(version, versions.list_tasks(session, version.id))


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


@tool("dashboard", "Overview: in-progress versions with progress, tasks being worked on or waiting, inbox and refine counts.",
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


@tool("add_task", "Create a task in a project: in the inbox, or planned straight into a version when 'version' is given.",
      {"project": _PROJECT, "title": _string("Task title."), "version": _VERSION,
       "body": _string("Free-text detail."), "context": _string("Context tag, e.g. @ordi."),
       "size": _string("Effort size.", SIZES)},
      ["project", "title"])
def add_task(session : Session, args : dict) -> dict:
    """Create a task."""
    detail = {name: args.get(name) for name in ("body", "context", "size")}
    if args.get("version"):
        version = _version_of(session, args)
        created = tasks.create_in_version(session, version.id, args["title"], actor=ACTOR, **detail)
    else:
        created = tasks.create(session, args["title"], project_key=args["project"], actor=ACTOR, **detail)
    return serialize.task(created)


@tool("import_data",
      "Import projects, versions and tasks. Give either 'document' (JSON: {\"projects\": [{\"key\", \"name\", "
      "\"versions\": [{\"number\", \"title\", \"dod\": [...], \"tasks\": [{\"title\", \"body\", \"context\", \"size\"}]}]}], "
      "\"tasks\": [{\"title\", \"project\", \"version\"}]}) or 'text' (one task title per line, into the inbox). "
      "Existing projects and versions are reused, never overwritten; tasks are always created. All or nothing. "
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
            "versions_created": result.versions_created, "versions_reused": result.versions_reused,
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


@tool("plan_task", "Plan a refined task into a version.", {"ref": _REF, "version": _VERSION, "project": _PROJECT},
      ["ref", "version"])
def plan_task(session : Session, args : dict) -> dict:
    """Plan a task into a version."""
    return serialize.task(tasks.plan(session, _task_of(session, args).id, _version_of(session, args).id, actor=ACTOR))


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


_transition("unplan_task", "Take a planned task out of its version, back to refined.", tasks.unplan)
_transition("start_task", "Start working on a planned task (planned to doing).", tasks.start)
_transition("complete_task", "Mark a task in progress as done.", tasks.complete)
_transition("block_task", "Mark a task in progress as waiting on something.", tasks.block,
            {"reason": _string("What the task is waiting for.")}, ["reason"])
_transition("unblock_task", "Resume a waiting task (waiting to doing).", tasks.unblock)


@tool("set_criterion_done", "Check or uncheck one definition-of-done criterion of a version.",
      {"version": _VERSION, "project": _PROJECT,
       "index": _integer("Criterion number, from 1, as listed by get_version."),
       "done": _boolean("True to check it, false to uncheck it.")},
      ["version", "index", "done"], idempotent=True)
def set_criterion_done(session : Session, args : dict) -> dict:
    """Check or uncheck a criterion."""
    version = _version_of(session, args)
    criteria = version.definition_of_done
    if not 1 <= args["index"] <= len(criteria):
        raise ValidationError(f"'index' must be between 1 and {len(criteria)}")
    versions.set_criterion_done(session, criteria[args["index"] - 1].id, args["done"], actor=ACTOR)
    return serialize.version(version, versions.list_tasks(session, version.id))


# -----------------------------------------------------------------------------
# Calling
# -----------------------------------------------------------------------------

def list_tools() -> list[dict]:
    """Describe every tool the way MCP's tools/list does."""
    return [{"name": t.name,
             "description": t.description,
             "inputSchema": t.schema,
             "annotations": {"readOnlyHint": t.read_only,
                             **({} if t.read_only else {"destructiveHint": False, "idempotentHint": t.idempotent}),
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
