from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class Project(Base):
    """Top-level container in the Project -> Version -> Task hierarchy."""

    __tablename__ = "project"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Short unique slug used in URLs (e.g. /projects/<key>), not the id.
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # e.g. "active" / "archived" — plain string for now, no enum yet.
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Deleting a project deletes its versions with it.
    versions: Mapped[list["Version"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    # Not cascaded: a task can outlive its project (e.g. unassigned later).
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")
