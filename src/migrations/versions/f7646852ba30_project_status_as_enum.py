"""project status as enum

Revision ID: f7646852ba30
Revises: 1ee9c901eec2
Create Date: 2026-09-13 03:38:06.382510

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7646852ba30'
down_revision: Union[str, Sequence[str], None] = '1ee9c901eec2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite has no ALTER TABLE ADD CONSTRAINT; batch mode rebuilds the
    # table under the hood to add the CHECK constraint.
    with op.batch_alter_table("project") as batch_op:
        batch_op.create_check_constraint(
            "project_status", "status IN ('ACTIVE', 'ARCHIVED')"
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("project") as batch_op:
        batch_op.drop_constraint("project_status", type_="check")
