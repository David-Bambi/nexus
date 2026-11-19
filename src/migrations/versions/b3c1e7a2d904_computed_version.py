"""Computed version: MAJOR.MINOR on projects, major criteria, released_in.

Revision ID: b3c1e7a2d904
Revises: 87dc79bc1cbb
Create Date: 2026-11-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3c1e7a2d904'
down_revision: Union[str, Sequence[str], None] = '87dc79bc1cbb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the version columns, released_in and the major_criterion table."""
    # server_default lets SQLite add a NOT NULL column to existing rows.
    with op.batch_alter_table('project') as batch_op:
        batch_op.add_column(sa.Column('version_major', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('version_minor', sa.Integer(), nullable=False, server_default='0'))
    with op.batch_alter_table('task') as batch_op:
        batch_op.add_column(sa.Column('released_in', sa.String(), nullable=True))
    op.create_table('major_criterion',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('text', sa.String(), nullable=False),
    sa.Column('done', sa.Boolean(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['project.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sqlite_autoincrement=True
    )


def downgrade() -> None:
    """Remove the computed-version schema."""
    op.drop_table('major_criterion')
    with op.batch_alter_table('task') as batch_op:
        batch_op.drop_column('released_in')
    with op.batch_alter_table('project') as batch_op:
        batch_op.drop_column('version_minor')
        batch_op.drop_column('version_major')
