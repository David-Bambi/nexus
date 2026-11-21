"""Project priority: HIGH, NORMAL or LOW, set on root projects.

Revision ID: d4e8a2b6f107
Revises: c7d2f4a1e835
Create Date: 2026-11-20 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e8a2b6f107'
down_revision: Union[str, Sequence[str], None] = 'c7d2f4a1e835'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add project.priority, NORMAL for every existing project."""
    with op.batch_alter_table('project') as batch_op:
        batch_op.add_column(sa.Column(
            'priority',
            sa.Enum('HIGH', 'NORMAL', 'LOW', name='project_priority', create_constraint=True),
            nullable=False,
            server_default='NORMAL',
        ))


def downgrade() -> None:
    """Remove project.priority."""
    with op.batch_alter_table('project') as batch_op:
        batch_op.drop_column('priority')
