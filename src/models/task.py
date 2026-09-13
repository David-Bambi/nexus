from datetime import datetime
from enum import Enum, auto
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base
from src.models.tag import task_tag_table


class TaskState(Enum):
    """A task's position in the GTD workflow. See the state diagram in
    docs/architecture/overview.md for the allowed transitions."""

    INBOX = auto()
    REFINED = auto()
    PLANNED = auto()
    DOING = auto()
    WAITING = auto()
    DONE = auto()
    SOMEDAY = auto()


class Task(Base):
    """The base unit of work, driven through the GTD state machine."""

    __tablename__ = "task"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable project/version is the GTD mechanism, not an edge case: no
    # project = raw capture, no version = not yet planned.
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("project.id"))
    version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("version.id"))
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    state: Mapped[TaskState] = mapped_column(
        SAEnum(TaskState, name="task_state", create_constraint=True),
        nullable=False,
        default=TaskState.INBOX,
    )
    # Free string, e.g. "@ordi", "@achat" — suggested set only.
    context: Mapped[Optional[str]] = mapped_column(String)
    # XS / S / M / L — ordinal effort estimate, never converted to hours.
    size: Mapped[Optional[str]] = mapped_column(String)
    # Manual ordering within a version board.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Required by services/ whenever state == "waiting".
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    # Set on completion, cleared on reopen.
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    project: Mapped[Optional["Project"]] = relationship(back_populates="tasks")
    version: Mapped[Optional["Version"]] = relationship(back_populates="tasks")
    tags: Mapped[list["Tag"]] = relationship(
        secondary=task_tag_table, back_populates="tasks"
    )
