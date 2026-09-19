from datetime import date, datetime
from enum import Enum

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from src.models.event import Event
from src.models.project import Project
from src.models.tag import Tag
from src.models.task import Task
from src.models.version import Version


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


def _all(session : Session, model : type) -> list:
    """Query every row of a model, in id order."""
    return session.query(model).order_by(model.id).all()


def dump_json(session : Session) -> dict:
    """Dump the whole database as a JSON-serialisable dict.

    Args:
        session: Database session to use.

    Returns:
        A dict with the export time and every table: "projects",
        "versions" (each with its ordered "definition_of_done" descriptions),
        "tasks" (each with its "tags" names), "tags" and "events". Enums are
        given by name and dates in ISO 8601. Archived projects and done tasks
        are included.
    """
    versions = []
    for version in _all(session, Version):
        criteria = sorted(version.definition_of_done, key=lambda c: c.position)
        versions.append({**_row(version), "definition_of_done": [c.description for c in criteria]})

    tasks = [
        {**_row(task), "tags": sorted(tag.name for tag in task.tags)}
        for task in _all(session, Task)
    ]

    return {
        "exported_at": _json_value(datetime.utcnow()),
        "projects": [_row(p) for p in _all(session, Project)],
        "versions": versions,
        "tasks": tasks,
        "tags": [_row(t) for t in _all(session, Tag)],
        "events": [_row(e) for e in _all(session, Event)],
    }
