"""Project directory: the project's folder on this machine.

Revision ID: c7d2f4a1e835
Revises: b3c1e7a2d904
Create Date: 2026-11-19 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d2f4a1e835'
down_revision: Union[str, Sequence[str], None] = 'b3c1e7a2d904'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add project.directory."""
    with op.batch_alter_table('project') as batch_op:
        batch_op.add_column(sa.Column('directory', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove project.directory."""
    with op.batch_alter_table('project') as batch_op:
        batch_op.drop_column('directory')
