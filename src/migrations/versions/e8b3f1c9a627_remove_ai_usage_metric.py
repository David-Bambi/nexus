"""remove ai usage metric

Revision ID: e8b3f1c9a627
Revises: c5e2d8a1f034
Create Date: 2026-11-17 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8b3f1c9a627'
down_revision: Union[str, Sequence[str], None] = 'c5e2d8a1f034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Values the removed AI mode column accepted.
AI_MODES = ("AUTONOMOUS", "LEARNED", "DELEGATED", "GUIDED", "DEPENDENT")
# Values the removed domain nature columns accepted.
NATURES = ("FOUNDING", "REPETITIVE", "PERIPHERAL")


def upgrade() -> None:
    """Upgrade schema: drop the AI usage metric (recorded modes and project settings are lost)."""
    op.drop_table("project_ai_target")
    op.drop_table("project_ai_domain")
    # Batch mode rebuilds the table: SQLite can't drop a CHECK constraint in place.
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_constraint("task_ai_mode", type_="check")
        batch_op.drop_column("ai_mode")


def downgrade() -> None:
    """Downgrade schema: recreate the AI usage metric, empty."""
    with op.batch_alter_table("task") as batch_op:
        batch_op.add_column(sa.Column(
            "ai_mode",
            sa.Enum(*AI_MODES, name="task_ai_mode", create_constraint=True),
            nullable=True,
        ))
    op.create_table(
        "project_ai_domain",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("nature", sa.Enum(*NATURES, name="ai_nature", create_constraint=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "domain", name="uq_project_ai_domain"),
    )
    op.create_table(
        "project_ai_target",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nature", sa.Enum(*NATURES, name="ai_target_nature", create_constraint=True), nullable=False),
        sa.Column("min_own_pct", sa.Integer(), nullable=True),
        sa.Column("max_dependent_pct", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "nature", name="uq_project_ai_target"),
    )
