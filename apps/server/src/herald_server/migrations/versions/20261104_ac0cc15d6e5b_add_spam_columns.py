"""add spam columns: email.in_spam and mailbox.read_spam (PR #52 added them to the models).

Revision ID: ac0cc15d6e5b
Revises: 92710862999b
Create Date: 2026-11-04 10:02:30.616539
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "ac0cc15d6e5b"
down_revision: str | Sequence[str] | None = "92710862999b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = (("email", "in_spam"), ("mailbox", "read_spam"))


def _has_column(table: str, column: str) -> bool:
    # Dev databases stamped at the baseline got these columns by hand while PR #52 was built,
    # before this migration existed. Adding them again would fail with "column already
    # exists", so skip a column that is there. Offline (--sql) has no database to look at.
    if context.is_offline_mode():
        return False
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # The server default fills existing rows, so the column can be NOT NULL from the start.
    for table, column in COLUMNS:
        if not _has_column(table, column):
            op.add_column(
                table,
                sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()),
            )


def downgrade() -> None:
    # Batch mode: SQLite cannot drop a column with a plain ALTER.
    for table, column in COLUMNS:
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_column(column)
