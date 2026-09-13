from datetime import date, datetime
from enum import Enum, auto
from typing import Optional

from sqlalchemy import Date, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class VersionStatus(Enum):
    """A version's lifecycle: PLANNED -> IN_PROGRESS -> RELEASED."""

    PLANNED = auto()
    IN_PROGRESS = auto()
    RELEASED = auto()


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

    status: Mapped[VersionStatus] = mapped_column(
        SAEnum(VersionStatus, name="version_status", create_constraint=True),
        nullable=False,
        default=VersionStatus.PLANNED,
    )
    
    # Manual ordering among a project's versions (drag-to-reorder in the UI).
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    
    # Set when the version is released; null while planned/in_progress.
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relations
    project: Mapped["Project"] = relationship(back_populates="versions")
    tasks: Mapped[list["Task"]] = relationship(back_populates="version")
    definition_of_done: Mapped[list["DefinitionOfDoneCriterion"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
