"""Task archive mark: when a done or cancelled item was put away.

Revision ID: e5f9b3c7a218
Revises: d4e8a2b6f107
Create Date: 2026-11-20 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f9b3c7a218'
down_revision: Union[str, Sequence[str], None] = 'd4e8a2b6f107'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add task.archived_at; nothing is archived yet."""
    with op.batch_alter_table('task') as batch_op:
        batch_op.add_column(sa.Column('archived_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove task.archived_at."""
    with op.batch_alter_table('task') as batch_op:
        batch_op.drop_column('archived_at')
