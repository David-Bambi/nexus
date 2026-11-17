from enum import Enum, auto
from typing import Optional

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db import Base


class AiMode(Enum):
    """How the AI took part in a finished task: who defined it, who executed it."""

    # Defined by David, executed by David.
    AUTONOMOUS = auto()
    # Defined by David, executed by David with explanations from the AI.
    LEARNED = auto()
    # Defined by David, executed by the AI.
    DELEGATED = auto()
    # Defined by the AI, executed by David.
    GUIDED = auto()
    # Defined by the AI, executed by the AI.
    DEPENDENT = auto()


class Nature(Enum):
    """Nature of a work domain in a project, which sets the target for that domain."""

    # The first time, the core logic, the architecture: David defines and executes.
    FOUNDING = auto()
    # A new case of work David already understood and defined: the AI may execute.
    REPETITIVE = auto()
    # Outside what David wants to learn or do: the AI may define and execute.
    PERIPHERAL = auto()


class ProjectAiDomain(Base):
    """A project's own nature for one domain, overriding the default nature."""

    __tablename__ = "project_ai_domain"
    __table_args__ = (UniqueConstraint("project_id", "domain", name="uq_project_ai_domain"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    # Domain slug, one of the fixed list in services/ai.
    domain: Mapped[str] = mapped_column(String, nullable=False)
    nature: Mapped[Nature] = mapped_column(
        SAEnum(Nature, name="ai_nature", create_constraint=True), nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="ai_domains")


class ProjectAiTarget(Base):
    """A project's target on its AI usage profile, for one nature."""

    __tablename__ = "project_ai_target"
    __table_args__ = (UniqueConstraint("project_id", "nature", name="uq_project_ai_target"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    nature: Mapped[Nature] = mapped_column(
        SAEnum(Nature, name="ai_target_nature", create_constraint=True), nullable=False
    )
    # Minimum weighted share (0-100) of autonomous + learned tasks; None = no minimum.
    min_own_pct: Mapped[Optional[int]] = mapped_column(Integer)
    # Maximum weighted share (0-100) of dependent tasks; None = no maximum.
    max_dependent_pct: Mapped[Optional[int]] = mapped_column(Integer)

    project: Mapped["Project"] = relationship(back_populates="ai_targets")
