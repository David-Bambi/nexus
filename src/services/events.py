from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from src.models.event import Event
from src.models.task import Task

# Actor recorded on every event written from the web interface.
ACTOR_WEB = "web"


def log(session : Session,
        actor : str,
        entity_type : str,
        entity_id : int,
        action : str,
        payload : dict | None = None) -> Event:
    """Record a domain mutation in the event log.

    The event is added to the session but not committed: the caller commits
    it together with the mutation it describes, so both are stored or neither.

    Args:
        session: Database session to use.
        actor: Who made the change (e.g. ACTOR_WEB).
        entity_type: Kind of entity changed ("task", "version", "project").
        entity_id: Id of the entity changed.
        action: What happened (e.g. "created", "completed").
        payload: Optional JSON-serialisable detail of the change.

    Returns:
        The newly added Event.
    """
    event = Event(actor=actor,
                  entity_type=entity_type,
                  entity_id=entity_id,
                  action=action,
                  payload=payload)
    session.add(event)
    return event


def history(session : Session, entity_type : str, entity_id : int) -> list:
    """List the events recorded for one entity.

    Args:
        session: Database session to use.
        entity_type: Kind of entity ("task", "version", "project").
        entity_id: Id of the entity.

    Returns:
        The entity's events, oldest first. Empty if none were recorded.
    """
    return (
        session.query(Event)
        .filter(Event.entity_type == entity_type, Event.entity_id == entity_id)
        .order_by(Event.at, Event.id)
        .all()
    )


def changelog(session : Session, version_id : int) -> list:
    """List what happened in a version.

    Args:
        session: Database session to use.
        version_id: Id of the version.

    Returns:
        The version's own events plus the events of the tasks currently
        planned in it, oldest first. Tasks deleted or unplanned since are
        not included.
    """
    task_ids = session.query(Task.id).filter(Task.version_id == version_id)

    return (
        session.query(Event)
        .filter(or_(
            and_(Event.entity_type == "version", Event.entity_id == version_id),
            and_(Event.entity_type == "task", Event.entity_id.in_(task_ids)),
        ))
        .order_by(Event.at, Event.id)
        .all()
    )
