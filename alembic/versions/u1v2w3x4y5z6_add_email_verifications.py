"""Add email_verifications: durable, opaque, single-use verification tokens.

Nothing in s9 fits. `auth_attempts` is a rate-limit counter with no user
foreign key, no token hash and no expiry. `auth_handoffs` lives 120 seconds and
has nowhere to record which address a token belongs to — the field that stops a
token surviving an email change. Sharing either would also mean one bug in one
consume path could burn the other kind of credential.

This supersedes the design in spec section 8, which avoided a table by reusing
the password-reset pattern: a code signed with a key derived from account state,
so completing verification invalidated outstanding codes for free. That pattern
puts the user id and expiry *inside* the token payload, making it a signed claim
rather than an opaque handle, and it records nothing when a token is used — so a
replay attempt cannot be told apart from a forgery.

Additive only: one new table. No existing table is altered, no data is migrated,
and no row count anywhere can change.

Revision ID: u1v2w3x4y5z6
Revises: s9t0u1v2w3x4
Create Date: 2026-08-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, Sequence[str], None] = "s9t0u1v2w3x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        # SHA-256 hex, the same representation auth_handoffs and auth_sessions
        # already use. The raw token is never stored.
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The NORMALISED address being verified, under the same contract as
        # users.email. Compared against the account's current address at consume
        # time, so a token issued for a previous address cannot verify a new one.
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        # Successfully used.
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        # Replaced by a newer token, or invalidated by an email change. Kept
        # separate from consumed_at because "clicked" and "asked for another"
        # are different events, and telling them apart is the difference
        # between an attack signal and an ordinary support case.
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        # Cheap guard against a clock or arithmetic bug producing a token that
        # is expired the moment it is issued.
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_email_verifications_expiry_after_creation",
        ),
    )

    # Two indexes, each earning its place:
    #
    #   token_hash  — the whole consume path is WHERE token_hash = :h, and the
    #                 uniqueness is also the collision guarantee.
    #   user_id     — supersession runs UPDATE ... WHERE user_id = :u on every
    #                 issue, and resend looks up by account.
    #
    # No index on expires_at. The proposal listed one "for cleanup", but the
    # sweep deletes on created_at and nothing would ever use it; at one row per
    # signup or resend a full-table sweep is free, while the index would cost
    # write amplification on every insert.
    op.create_index(
        "ix_email_verifications_token_hash",
        "email_verifications",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_email_verifications_user_id", "email_verifications", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_email_verifications_user_id", table_name="email_verifications")
    op.drop_index("ix_email_verifications_token_hash", table_name="email_verifications")
    op.drop_table("email_verifications")
