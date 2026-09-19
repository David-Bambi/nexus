from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base


class Event(Base):
    """Append-only audit trail: one row per domain mutation, never updated
    or deleted. Powers task history, changelogs, and future traceability."""

    __tablename__ = "event"
    # Keeps history lookups (one entity's events) fast as the log grows.
    __table_args__ = (Index("ix_event_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    
    # "web" in v1; will later distinguish "cli" / "agent".
    actor: Mapped[str] = mapped_column(String, nullable=False)
    # No FK on purpose: an append-only log that references any entity type
    # by name + id, so an entry survives even if the entity is later deleted.
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # e.g. "created", "planned", "completed" — free string, one per mutation.
    action: Mapped[str] = mapped_column(String, nullable=False)
    # Arbitrary JSON snapshot of what changed, e.g. {"from": "doing", "to": "done"}.
    payload: Mapped[Optional[dict]] = mapped_column(JSON)
