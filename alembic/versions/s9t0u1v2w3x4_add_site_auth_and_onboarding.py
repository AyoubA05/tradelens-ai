"""Add onboarding/profile columns and the site-hosted auth tables.

Additive only. Every new users column is nullable or carries a server default,
so the ALTER cannot fail against a populated table and no row count changes
anywhere. Production is Neon/Postgres and already holds real accounts, so this
runs as an ALTER on live data rather than a rebuild.

The backfill encodes one deliberate asymmetry, and it is the reason this
revision needed a design discussion at all:

    legacy accounts get email_verification_required = False,
    NOT a fabricated email_verified_at.

Setting a timestamp would have been one line shorter and would have let legacy
users sign in identically. It is rejected because it writes a claim into the
data that is false — nobody ever confirmed those addresses — and it would make
"which addresses are actually confirmed?" permanently unanswerable. Exempting
them by flag keeps the record honest, and leaves "require verification of old
accounts too" as a single boolean flip per user.

Revision ID: s9t0u1v2w3x4
Revises: t0u1v2w3x4y5
Create Date: 2026-08-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s9t0u1v2w3x4"
down_revision: Union[str, Sequence[str], None] = "t0u1v2w3x4y5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Declared in the order added, so downgrade() can drop them in reverse.
_USER_COLUMNS = (
    "full_name",
    "birthday",
    "referral_source",
    "referral_source_other",
    "onboarding_completed",
    "strategy_profile_completed",
    "email_verified_at",
    "email_verification_required",
)


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(), nullable=True))
    op.add_column("users", sa.Column("birthday", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("referral_source", sa.String(), nullable=True))
    op.add_column(
        "users", sa.Column("referral_source_other", sa.String(), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "onboarding_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "strategy_profile_completed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verification_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    # --- backfill -----------------------------------------------------------
    # Every row that exists at this instant is, by definition, a legacy account.

    # They never saw the personal-info form, so do not trap them behind it.
    op.execute("UPDATE users SET onboarding_completed = true")

    # The explicit legacy compatibility rule. email_verified_at stays NULL.
    op.execute("UPDATE users SET email_verification_required = false")

    # A user with an active profile has already done the first-run step; a user
    # without one gets it exactly once. Correlated EXISTS rather than a JOIN so
    # the statement is valid on both SQLite (tests) and Postgres (production).
    op.execute(
        """
        UPDATE users SET strategy_profile_completed = true
        WHERE EXISTS (
            SELECT 1 FROM strategies
            WHERE strategies.user_id = users.id AND strategies.is_active = 1
        )
        """
    )

    # --- new tables ---------------------------------------------------------

    op.create_table(
        "auth_handoffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_auth_handoffs_token_hash", "auth_handoffs", ["token_hash"], unique=True
    )
    op.create_index("ix_auth_handoffs_user_id", "auth_handoffs", ["user_id"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_auth_sessions_token_hash", "auth_sessions", ["token_hash"], unique=True
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bucket", sa.String(200), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_attempts_bucket", "auth_attempts", ["bucket"])
    op.create_index("ix_auth_attempts_created_at", "auth_attempts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_attempts_created_at", table_name="auth_attempts")
    op.drop_index("ix_auth_attempts_bucket", table_name="auth_attempts")
    op.drop_table("auth_attempts")

    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_token_hash", table_name="auth_sessions")
    op.drop_table("auth_sessions")

    op.drop_index("ix_auth_handoffs_user_id", table_name="auth_handoffs")
    op.drop_index("ix_auth_handoffs_token_hash", table_name="auth_handoffs")
    op.drop_table("auth_handoffs")

    # batch_alter_table so this also works on SQLite, which cannot DROP COLUMN
    # directly on older versions and needs a table rebuild instead.
    with op.batch_alter_table("users") as batch:
        for column in reversed(_USER_COLUMNS):
            batch.drop_column(column)
