# Import every model here so a single `from src.models import Base` (or any
# import of this package) fully populates Base.metadata for Alembic.
from src.db import Base
from src.models.project import Project
from src.models.criterion import MajorCriterion
from src.models.tag import Tag, task_tag_table
from src.models.task import Task, TaskKind, TaskState
from src.models.event import Event

__all__ = [
    "Base",
    "Project",
    "MajorCriterion",
    "Tag",
    "task_tag_table",
    "Task",
    "TaskKind",
    "TaskState",
    "Event",
]
