from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class Version(Base):
    """A milestone that ships one complete feature; the unit of planning
    that a Task attaches to."""

    __tablename__ = "version"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    # e.g. "0.2.0" — free string, not parsed/validated as SemVer at the DB level.
    number: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    goal: Mapped[Optional[str]] = mapped_column(Text)
    # Meant to be mandatory, but that rule is enforced in services/, not as
    # a DB constraint.
    definition_of_done: Mapped[Optional[str]] = mapped_column(Text)
    # "planned" -> "in_progress" -> "released".
    status: Mapped[str] = mapped_column(String, nullable=False, default="planned")
    # Manual ordering among a project's versions (drag-to-reorder in the UI).
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    # Set when the version is released; null while planned/in_progress.
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    project: Mapped["Project"] = relationship(back_populates="versions")
    tasks: Mapped[list["Task"]] = relationship(back_populates="version")
