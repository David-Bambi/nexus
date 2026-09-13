"""definition of done as criteria table

Revision ID: 20f407853ff4
Revises: 0cd86ccf978f
Create Date: 2026-09-13 10:54:58.634843

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20f407853ff4'
down_revision: Union[str, Sequence[str], None] = '0cd86ccf978f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "definition_of_done_criterion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["version.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # SQLite has no ALTER TABLE DROP COLUMN; batch mode rebuilds the table.
    with op.batch_alter_table("version") as batch_op:
        batch_op.drop_column("definition_of_done")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("version") as batch_op:
        batch_op.add_column(sa.Column("definition_of_done", sa.Text(), nullable=True))
    op.drop_table("definition_of_done_criterion")
