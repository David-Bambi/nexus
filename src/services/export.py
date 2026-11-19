from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import inspect
from sqlalchemy.orm import Session, selectinload

from src.models.criterion import MajorCriterion
from src.models.event import Event
from src.models.project import Project
from src.models.tag import Tag
from src.models.task import Task, TaskKind
from src.services import projects


def _json_value(value : object) -> object:
    """Convert a column value into a JSON-serialisable one.

    Args:
        value: Raw column value.

    Returns:
        The enum's name, the ISO 8601 form of a date or datetime, or the
        value itself for anything already serialisable.
    """
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row(entity : object) -> dict:
    """Turn a model instance into a dict of its column values.

    Args:
        entity: Any mapped model instance.

    Returns:
        Column name mapped to its JSON-serialisable value.
    """
    return {
        attr.key: _json_value(getattr(entity, attr.key))
        for attr in inspect(entity).mapper.column_attrs
    }


def _all(session : Session, model : type, *options : object) -> list:
    """Query every row of a model, in id order.

    Args:
        session: Database session to use.
        model: The model to query.
        *options: Loader options, to fetch related rows in bulk rather than
            one query per row.
    """
    return session.query(model).options(*options).order_by(model.id).all()


def dump_json(session : Session) -> dict:
    """Dump the whole database as a JSON-serialisable dict.

    Args:
        session: Database session to use.

    Returns:
        A dict with the export time and every table: "projects" (root
        projects and subprojects, a subproject with its "parent_id", each
        with its "version_major" and "version_minor"), "criteria" (major
        criteria, by "project_id"), "tasks" (features and tasks, each with
        its "kind", "parent_id", "released_in" and "tags" names), "tags"
        and "events". Enums are given by name and
        dates in ISO 8601. Archived projects and done tasks are included.
    """
    tasks = [
        {**_row(task), "tags": sorted(tag.name for tag in task.tags)}
        for task in _all(session, Task, selectinload(Task.tags))
    ]

    return {
        "exported_at": _json_value(datetime.utcnow()),
        "projects": [_row(p) for p in _all(session, Project)],
        "criteria": [_row(c) for c in _all(session, MajorCriterion)],
        "tasks": tasks,
        "tags": [_row(t) for t in _all(session, Tag)],
        "events": [_row(e) for e in _all(session, Event)],
    }


# -----------------------------------------------------------------------------
# Feature export for metrique
# -----------------------------------------------------------------------------

# Name and version of the feature export's format. Bumped whenever a field
# is removed or changes meaning; adding a field keeps the version.
FEATURES_SCHEMA = "nexus.features/1"


def _utc(value : datetime | None) -> str | None:
    """Format a stored (naive, UTC) datetime as ISO 8601 with its offset.

    Args:
        value: A datetime as stored by Nexus, or None.

    Returns:
        e.g. "2026-11-19T21:17:55.646794+00:00", or None.
    """
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def _concerns(event : Event, feature : Task) -> bool:
    """Tell whether a task event belongs to a feature's record.

    It does when it is the feature's own event, when the item was under the
    feature at that moment, or when the item was moved out of it.

    Args:
        event: An event of entity type "task".
        feature: The feature.
    """
    if event.entity_id == feature.id:
        return True
    payload = event.payload or {}
    if payload.get("parent") == feature.ref:
        return True
    moved_from = payload.get("from")
    return event.action == "moved" and isinstance(moved_from, dict) and moved_from.get("parent") == feature.ref


def features(session : Session) -> dict:
    """Export every feature with the facts needed to measure it.

    The format is a stable contract for the metrique project, named by
    FEATURES_SCHEMA. Dates are UTC with an explicit offset.

    Args:
        session: Database session to use.

    Returns:
        {"schema", "exported_at", "features": [...]}, one entry per feature
        in creation order, each with: "ref", "title", "state", "project"
        (key of the nearest project), "directory" (folder of the nearest
        project, else of its parent project), "started_at" (first start),
        "closed_at", "released_in", "plan" (refs of its children at its
        first start, or None if never started), "children" (direct
        children: "ref", "kind", "title", "state", "size") and "events"
        (its own and its children's, oldest first: "at", "actor", "ref",
        "action", "payload"). A child's event belongs to the feature it was
        under at that moment; moving a child out is the feature's event too.
    """
    items = _all(session, Task, selectinload(Task.children))
    refs = {item.id: item.ref for item in items}
    task_events = (session.query(Event).filter(Event.entity_type == "task")
                   .order_by(Event.at, Event.id).all())

    exported = []
    for feature in (item for item in items if item.kind is TaskKind.FEATURE):
        own = [e for e in task_events if _concerns(e, feature)]
        first_start = next((e for e in own if e.entity_id == feature.id and e.action == "started"), None)
        exported.append({
            "ref": feature.ref,
            "title": feature.title,
            "state": feature.state.name,
            "project": feature.project.key if feature.project else None,
            "directory": projects.directory_of(feature.project),
            "started_at": _utc(first_start.at) if first_start else None,
            "closed_at": _utc(feature.closed_at),
            "released_in": feature.released_in,
            "plan": (first_start.payload or {}).get("plan") if first_start else None,
            "children": [{"ref": child.ref, "kind": child.kind.name, "title": child.title,
                          "state": child.state.name, "size": child.size}
                         for child in feature.children],
            "events": [{"at": _utc(e.at),
                        "actor": e.actor,
                        "ref": refs.get(e.entity_id) or (e.payload or {}).get("ref"),
                        "action": e.action,
                        "payload": e.payload}
                       for e in own],
        })

    return {"schema": FEATURES_SCHEMA,
            "exported_at": _utc(datetime.utcnow()),
            "features": exported}
