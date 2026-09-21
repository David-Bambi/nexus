"""add cancelled task state

Revision ID: 3c1e5a7b9d20
Revises: 8d98a85a9c34
Create Date: 2026-09-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '3c1e5a7b9d20'
down_revision: Union[str, Sequence[str], None] = '8d98a85a9c34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Task states accepted before and after this revision.
OLD_STATES = "'INBOX', 'REFINED', 'PLANNED', 'DOING', 'WAITING', 'DONE', 'SOMEDAY'"
NEW_STATES = OLD_STATES + ", 'CANCELLED'"


def upgrade() -> None:
    """Upgrade schema."""
    # Batch mode rebuilds the table: SQLite can't alter a CHECK constraint.
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_constraint("task_state", type_="check")
        batch_op.create_check_constraint("task_state", f"state IN ({NEW_STATES})")


def downgrade() -> None:
    """Downgrade schema."""
    # Cancelled tasks have no equivalent before this revision: back to refined.
    op.execute("UPDATE task SET state = 'REFINED', version_id = NULL WHERE state = 'CANCELLED'")
    with op.batch_alter_table("task") as batch_op:
        batch_op.drop_constraint("task_state", type_="check")
        batch_op.create_check_constraint("task_state", f"state IN ({OLD_STATES})")
