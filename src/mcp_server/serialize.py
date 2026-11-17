from datetime import date, datetime

from src.models.definition_of_done import DefinitionOfDoneCriterion
from src.models.event import Event
from src.models.project import Project
from src.models.task import Task
from src.models.version import Version
from src.services.views import DashboardView


def _iso(value : date | datetime | None) -> str | None:
    """Format a date or datetime as ISO 8601, keeping None."""
    return value.isoformat() if value else None


def project(item : Project) -> dict:
    """A project as a JSON-serialisable dict, identified by its key."""
    return {"key": item.key,
            "name": item.name,
            "description": item.description,
            "status": item.status.name}


def criterion(index : int, item : DefinitionOfDoneCriterion) -> dict:
    """A definition-of-done criterion; `index` is its 1-based place in the list."""
    return {"index": index, "description": item.description, "done": item.done}


def version_brief(item : Version) -> dict:
    """A version without its tasks or checklist, identified by its ref."""
    return {"ref": item.ref,
            "project": item.project.key,
            "number": item.number,
            "title": item.title,
            "status": item.status.name}


def version(item : Version, tasks : list[Task]) -> dict:
    """A version with its tasks and its definition of done."""
    return {**version_brief(item),
            "goal": item.goal,
            "target_date": _iso(item.target_date),
            "released_at": _iso(item.released_at),
            "tasks": [task_brief(t) for t in tasks],
            "definition_of_done": [criterion(i, c) for i, c in enumerate(item.definition_of_done, start=1)]}


def task_brief(item : Task) -> dict:
    """A task's identity and placement, identified by its ref."""
    return {"ref": item.ref,
            "title": item.title,
            "state": item.state.name,
            "project": item.project.key if item.project else None,
            "version": item.version.number if item.version else None,
            "version_ref": item.version.ref if item.version else None,
            "size": item.size,
            "context": item.context}


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
    """The dashboard: in-progress versions with progress, doing and waiting tasks, counters."""
    return {"in_progress": [{**version_brief(p.version),
                             "tasks_done": p.done, "tasks_total": p.total,
                             "criteria_done": p.dod_done, "criteria_total": p.dod_total}
                            for p in view.versions],
            "doing": [task_brief(t) for t in view.doing],
            "waiting": [task_brief(t) for t in view.waiting],
            "inbox_count": view.inbox_count,
            "refine_count": view.refine_count}
