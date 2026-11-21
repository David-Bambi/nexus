from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class MajorCriterion(Base):
    """One condition to meet before a project (or subproject) moves to its
    next major version. The list is emptied by each major release."""

    __tablename__ = "major_criterion"
    # AUTOINCREMENT: a deleted id is never handed out again, so the event log
    # never mixes the history of a deleted row with a new one.
    __table_args__ = {"sqlite_autoincrement": True}

    # Internal id, never shown to the user.
    id: Mapped[int] = mapped_column(primary_key=True)

    # Project or subproject the criterion belongs to.
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)

    # What must be true before the next major version.
    text: Mapped[str] = mapped_column(String, nullable=False)

    # Whether the criterion is met.
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Display order within the project's list.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Project or subproject the criterion belongs to.
    project: Mapped["Project"] = relationship(back_populates="criteria")
