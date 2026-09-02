"""Add revision/tombstone state to trade drafts.

Revision ID: f2g3h4i5j6k7
Revises: e1f2g3h4i5j6
"""

import sqlalchemy as sa
from alembic import op

revision = "f2g3h4i5j6k7"
down_revision = "e1f2g3h4i5j6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trade_drafts",
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "trade_drafts",
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trade_drafts", "retired_at")
    op.drop_column("trade_drafts", "revision")
