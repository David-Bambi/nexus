from sqlalchemy import Column, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base

# Many-to-many link between tasks and tags — free-form labels, no extra
# columns needed on the association itself.
task_tag_table = Table(
    "task_tag",
    Base.metadata,
    Column("task_id", ForeignKey("task.id"), primary_key=True),
    Column("tag_id", ForeignKey("tag.id"), primary_key=True),
)


class Tag(Base):
    """A free-form label a user can attach to any number of tasks."""

    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    tasks: Mapped[list["Task"]] = relationship(
        secondary=task_tag_table, back_populates="tags"
    )
