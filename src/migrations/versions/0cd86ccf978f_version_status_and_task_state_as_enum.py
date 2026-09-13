"""version status and task state as enum

Revision ID: 0cd86ccf978f
Revises: f7646852ba30
Create Date: 2026-09-13 03:47:16.292472

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0cd86ccf978f'
down_revision: Union[str, Sequence[str], None] = 'f7646852ba30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite has no ALTER TABLE ADD CONSTRAINT; batch mode rebuilds the
    # table under the hood to add each CHECK constraint.
    with op.batch_alter_table("version") as batch_op:
        batch_op.create_check_constraint(
            "version_status", "status IN ('PLANNED', 'IN_PROGRESS', 'RELEASED')"
        )
    with op.batch_alter_table("task") as batch_op:
        batch_op.create_check_constraint(
            "task_state",
            "state IN ('INBOX', 'REFINED', 'PLANNED', 'DOING', 'WAITING', 'DONE', 'SOMEDAY')",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_constraint("task_state", type_="check")
    with op.batch_alter_table("version") as batch_op:
        batch_op.drop_constraint("version_status", type_="check")
