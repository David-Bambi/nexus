"""add ref to task and version

Revision ID: a4f19c2e7b31
Revises: 3c1e5a7b9d20
Create Date: 2026-09-21 10:00:00.000000

"""
import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4f19c2e7b31'
down_revision: Union[str, Sequence[str], None] = '3c1e5a7b9d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Base36 alphabet and per-table prefix, mirroring src/services/refs.py.
_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
_TABLES = {"task": "t", "version": "v"}


def _backfill(table : str, prefix : str) -> None:
    """Give every existing row of a table a unique ref.

    Args:
        table: Table name.
        prefix: Ref prefix for the table's rows.
    """
    bind = op.get_bind()
    ids = [row[0] for row in bind.execute(sa.text(f"SELECT id FROM {table} ORDER BY id"))]
    used = set()
    length = 3
    for row_id in ids:
        # Widen the code when the 3-character space runs low.
        if len(used) > 20000:
            length = 4
        while True:
            ref = f"{prefix}-" + "".join(secrets.choice(_ALPHABET) for _ in range(length))
            if ref not in used:
                break
        used.add(ref)
        bind.execute(sa.text(f"UPDATE {table} SET ref = :ref WHERE id = :id"),
                     {"ref": ref, "id": row_id})


def upgrade() -> None:
    """Upgrade schema."""
    for table, prefix in _TABLES.items():
        # Added nullable so existing rows can be backfilled, then tightened.
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("ref", sa.String(), nullable=True))
        _backfill(table, prefix)
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column("ref", existing_type=sa.String(), nullable=False)
            batch_op.create_unique_constraint(f"uq_{table}_ref", ["ref"])


def downgrade() -> None:
    """Downgrade schema."""
    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(f"uq_{table}_ref", type_="unique")
            batch_op.drop_column("ref")
