"""Make authenticated trade creation idempotent under concurrent retries.

Revision ID: d0e1f2g3h4i5
Revises: c9d0e1f2g3h4
"""

import sqlalchemy as sa
from alembic import op

revision = "d0e1f2g3h4i5"
down_revision = "c9d0e1f2g3h4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("trades") as batch:
        batch.add_column(
            sa.Column("create_idempotency_key", sa.String(), nullable=True)
        )
        batch.create_unique_constraint(
            "uq_trades_user_create_idempotency",
            ["user_id", "create_idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("trades") as batch:
        batch.drop_constraint("uq_trades_user_create_idempotency", type_="unique")
        batch.drop_column("create_idempotency_key")
