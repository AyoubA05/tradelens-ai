"""Add users.app_surface for the Next.js migration cutover.

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
"""

import sqlalchemy as sa
from alembic import op

revision = "y5z6a7b8c9d0"
down_revision = "x4y5z6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default is mandatory, not stylistic: the column is NOT NULL and
    # existing rows have no value, so without it the ALTER fails on Postgres.
    op.add_column(
        "users",
        sa.Column(
            "app_surface",
            sa.String(),
            nullable=False,
            server_default=sa.text("'streamlit'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "app_surface")
