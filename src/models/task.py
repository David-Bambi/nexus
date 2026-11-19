from datetime import datetime
from enum import Enum, auto
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base
from src.models.tag import task_tag_table


class TaskState(Enum):
    """A work item's position in the GTD workflow. See the state diagram in
    docs/architecture/overview.md for the allowed transitions."""

    INBOX = auto()
    REFINED = auto()
    DOING = auto()
    WAITING = auto()
    DONE = auto()
    SOMEDAY = auto()
    CANCELLED = auto()


class TaskKind(Enum):
    """What a work item is: a feature (can hold children) or a task (a leaf)."""

    FEATURE = auto()
    TASK = auto()


class Task(Base):
    """A work item of the project tree, feature or task, driven through the
    GTD state machine."""

    __tablename__ = "task"
    # AUTOINCREMENT: a deleted id is never handed out again, so the event log
    # never mixes the history of a deleted row with a new one.
    __table_args__ = {"sqlite_autoincrement": True}

    # Internal id, never shown to the user.
    id: Mapped[int] = mapped_column(primary_key=True)

    # Short unique reference ("f-4k2" for a feature, "t-4k2" for a task),
    # immutable; set by services/refs.
    ref: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    # Feature or task.
    kind: Mapped[TaskKind] = mapped_column(
        SAEnum(TaskKind, name="task_kind", create_constraint=True),
        nullable=False,
        default=TaskKind.TASK,
    )

    # Nearest project or subproject above the item. Null on a raw capture,
    # which is the GTD inbox, not an edge case.
    project_id: Mapped[Optional[int]] = mapped_column(ForeignKey("project.id"))

    # Feature directly above the item; null when it sits right under its
    # project (or has no project yet).
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("task.id"))

    # One-line title.
    title: Mapped[str] = mapped_column(String, nullable=False)

    # Free-text detail.
    body: Mapped[Optional[str]] = mapped_column(Text)

    # Position in the GTD workflow.
    state: Mapped[TaskState] = mapped_column(
        SAEnum(TaskState, name="task_state", create_constraint=True),
        nullable=False,
        default=TaskState.INBOX,
    )

    # Free string, e.g. "@ordi", "@achat" — suggested set only.
    context: Mapped[Optional[str]] = mapped_column(String)

    # XS / S / M / L — ordinal effort estimate, never converted to hours.
    size: Mapped[Optional[str]] = mapped_column(String)

    # Manual ordering among the item's siblings.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Required by services/ whenever state == "waiting".
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Creation time (UTC).
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Last change time (UTC).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Set on completion, cleared on reopen.
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Version of the nearest project the feature first shipped in (e.g.
    # "1.4"); set on its first completion and kept on reopen. Always null
    # on a task.
    released_in: Mapped[Optional[str]] = mapped_column(String)

    # Nearest project or subproject; None on a raw capture.
    project: Mapped[Optional["Project"]] = relationship(back_populates="tasks")

    # Feature directly above; None at the top of a project.
    parent: Mapped[Optional["Task"]] = relationship(
        back_populates="children", remote_side=[id]
    )

    # Features and tasks directly below a feature, in sibling order. Not
    # cascaded: services/ only delete an empty feature.
    children: Mapped[list["Task"]] = relationship(
        back_populates="parent", order_by="Task.position"
    )

    # Free-form labels.
    tags: Mapped[list["Tag"]] = relationship(
        secondary=task_tag_table, back_populates="tasks"
    )
