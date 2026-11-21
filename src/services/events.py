from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from src.models.event import Event
from src.models.task import Task

# Actor recorded on every event written from the web interface.
ACTOR_WEB = "web"

# Actor recorded on every event written from the command line.
ACTOR_CLI = "cli"

# Actor recorded on every event written through the MCP endpoint.
ACTOR_MCP = "mcp"


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
        entity_type: Kind of entity changed ("task", "project").
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
        entity_type: Kind of entity ("task", "project").
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
