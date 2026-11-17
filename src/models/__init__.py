# Import every model here so a single `from src.models import Base` (or any
# import of this package) fully populates Base.metadata for Alembic.
from src.db import Base
from src.models.ai import AiMode, Nature, ProjectAiDomain, ProjectAiTarget
from src.models.project import Project
from src.models.tag import Tag, task_tag_table
from src.models.version import Version
from src.models.definition_of_done import DefinitionOfDoneCriterion
from src.models.task import Task
from src.models.event import Event

__all__ = [
    "Base",
    "AiMode",
    "Nature",
    "ProjectAiDomain",
    "ProjectAiTarget",
    "Project",
    "Tag",
    "task_tag_table",
    "Version",
    "DefinitionOfDoneCriterion",
    "Task",
    "Event",
]
