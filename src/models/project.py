from datetime import datetime
from enum import Enum, auto
from typing import Optional

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class ProjectStatus(Enum):
    """Lifecycle state of a project."""

    ACTIVE = auto()
    ARCHIVED = auto()


class Project(Base):
    """Top of the work tree: a root project, or a subproject of one.

    A root project has no parent. A subproject has a root project as parent
    (one level only, enforced by services/) and owns its own work tree.
    """

    __tablename__ = "project"
    # AUTOINCREMENT: a deleted id is never handed out again, so the event log
    # never mixes the history of a deleted row with a new one.
    __table_args__ = {"sqlite_autoincrement": True}

    # Internal id, never shown to the user.
    id: Mapped[int] = mapped_column(primary_key=True)

    # Short unique key typed by the user, e.g. "nexus".
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    # Short unique reference of a subproject (e.g. "s-4k2"), immutable; set
    # by services/refs. Null on a root project, which is named by its key.
    ref: Mapped[Optional[str]] = mapped_column(String, unique=True)

    # Root project this subproject belongs to; null on a root project.
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("project.id"))

    # Display name.
    name: Mapped[str] = mapped_column(String, nullable=False)

    # Free-text description.
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Active or archived.
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus, name="project_status", create_constraint=True),
        nullable=False,
        default=ProjectStatus.ACTIVE,
    )

    # Absolute path of the project's folder on this machine (e.g.
    # "/home/me/projets/nexus"), normalised by services/projects; null when
    # not set. Ties Claude Code sessions to the project.
    directory: Mapped[Optional[str]] = mapped_column(String)

    # MAJOR part of the computed version; raised by hand once every major
    # criterion is checked (services/versioning).
    version_major: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # MINOR part of the computed version; raised by each feature completed
    # under this project, reset to 0 by a major release.
    version_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Creation time (UTC).
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Root project above this subproject; None on a root project.
    parent: Mapped[Optional["Project"]] = relationship(
        back_populates="subprojects", remote_side=[id]
    )

    # Subprojects of this root project. Not cascaded: services/ only delete
    # an empty project.
    subprojects: Mapped[list["Project"]] = relationship(back_populates="parent")

    # Every feature and task whose nearest project is this one.
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")

    # Criteria for the next major version, in display order. Cascaded: the
    # list belongs to the project and is emptied by each major release.
    criteria: Mapped[list["MajorCriterion"]] = relationship(
        back_populates="project",
        order_by="MajorCriterion.position",
        cascade="all, delete-orphan",
    )
