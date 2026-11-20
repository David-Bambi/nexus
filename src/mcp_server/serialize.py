from datetime import date, datetime

from src.models.criterion import MajorCriterion
from src.models.event import Event
from src.models.project import Project
from src.models.task import Task
from src.services import projects, versioning
from src.services.views import DashboardView, TreeNode


def _iso(value : date | datetime | None) -> str | None:
    """Format a date or datetime as ISO 8601, keeping None."""
    return value.isoformat() if value else None


def project(item : Project) -> dict:
    """A project or subproject as a JSON-serialisable dict, identified by its key."""
    return {"key": item.key,
            "ref": item.ref,
            "parent": item.parent.key if item.parent else None,
            "name": item.name,
            "description": item.description,
            "status": item.status.name,
            "priority": item.effective_priority.name,
            "version": versioning.label(item),
            "directory": item.directory,
            "effective_directory": projects.directory_of(item)}


def criteria(items : list[MajorCriterion]) -> list[dict]:
    """A project's criteria for the next major version, in list order.

    Each is identified by its "number", counted from 1, never by a raw id.
    """
    return [{"number": number, "text": item.text, "done": item.done}
            for number, item in enumerate(items, start=1)]


def tree(nodes : list[TreeNode]) -> list[dict]:
    """A work tree as nested dicts: each item's brief plus its "children"."""
    return [{**task_brief(node.item), "children": tree(node.children)} for node in nodes]


def task_brief(item : Task) -> dict:
    """A feature's or task's identity and placement, identified by its ref."""
    return {"ref": item.ref,
            "kind": item.kind.name,
            "title": item.title,
            "state": item.state.name,
            "project": item.project.key if item.project else None,
            "parent": item.parent.ref if item.parent else None,
            "size": item.size,
            "context": item.context,
            "released_in": item.released_in}


def task(item : Task) -> dict:
    """A task with all its fields."""
    return {**task_brief(item),
            "body": item.body,
            "blocked_reason": item.blocked_reason,
            "created_at": _iso(item.created_at),
            "updated_at": _iso(item.updated_at),
            "closed_at": _iso(item.closed_at)}


def event(item : Event) -> dict:
    """An event-log entry."""
    return {"at": _iso(item.at),
            "actor": item.actor,
            "action": item.action,
            "payload": item.payload}


def dashboard(view : DashboardView) -> dict:
    """The dashboard: active root projects by priority with their progress, doing and waiting items, counters."""
    return {"projects": [{"key": row.project.key, "name": row.project.name, "priority": row.project.priority.name,
                          "version": versioning.label(row.project), "features_done": row.features_done,
                          "features_total": row.features_total} for row in view.projects],
            "doing": [task_brief(t) for t in view.doing],
            "waiting": [task_brief(t) for t in view.waiting],
            "inbox_count": view.inbox_count,
            "refine_count": view.refine_count}
