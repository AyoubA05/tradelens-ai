"""Add password_resets: durable, opaque, single-use reset tokens.

Replaces the signed claim-bearing codes in services/password_reset.py, which
carry the user id and expiry inside the token and store nothing — so a replay
cannot be distinguished from a forgery, and outstanding tokens cannot be
explicitly invalidated.

None of the existing auth tables fit, and none may be reused: email_verifications
proves a different thing under different eligibility rules, auth_handoffs lives
120 seconds, auth_sessions is a session store, auth_attempts is a rate-limit
counter with no user foreign key.

Deliberately the same shape as email_verifications plus one column. Two token
tables with identical columns and identical consume semantics are far easier to
reason about than two that each invented their own.

`password_hash_fingerprint` recovers a property the signed-claim design had for
free: because its key derived from the current password hash, any password
change invalidated every outstanding code. Here it is compared at consume, so a
hash changed by any route makes the token stale — a condition nobody can forget,
rather than a supersede-write every future password-change path must remember.
It stores SHA-256 of the hash; never the hash, never the password.

Additive only: one new table. No existing table is altered, no data migrated,
and no row count anywhere can change.

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-08-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v2w3x4y5z6a7"
down_revision: Union[str, Sequence[str], None] = "u1v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), primary_key=True),
        # SHA-256 hex, the representation every other token table uses.
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Normalised verified address the reset was issued for. Compared at
        # consume, so a link mailed to a previous address cannot reset a
        # changed one.
        sa.Column("email", sa.String(), nullable=False),
        # SHA-256 hex of the exact users.password_hash string, UTF-8 encoded.
        sa.Column("password_hash_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_password_resets_expiry_after_creation",
        ),
    )

    # Two indexes, each earning its place:
    #   token_hash — the consume path is WHERE token_hash = :h, and the
    #                uniqueness is also the collision guarantee.
    #   user_id    — supersession runs UPDATE ... WHERE user_id = :u on every
    #                request, and the reset transaction looks up by account.
    # No expires_at index: the sweep deletes on created_at, so nothing uses it.
    op.create_index(
        "ix_password_resets_token_hash", "password_resets", ["token_hash"], unique=True
    )
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_password_resets_user_id", table_name="password_resets")
    op.drop_index("ix_password_resets_token_hash", table_name="password_resets")
    op.drop_table("password_resets")
