from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class DefinitionOfDoneCriterion(Base):
    """One checklist item defining what "done" means for a Version.

    A Version has many criteria (one-to-many); each criterion belongs to
    exactly one Version, so a plain `version_id` foreign key is enough —
    no junction table is needed.
    """

    __tablename__ = "definition_of_done_criterion"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("version.id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Manual ordering within a version's checklist.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    version: Mapped["Version"] = relationship(back_populates="definition_of_done")
