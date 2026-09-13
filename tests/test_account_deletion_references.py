"""Account deletion leaves no row that still references the user.

`auth_sessions.user_id` and `auth_handoffs.user_id` are NOT NULL foreign keys
to `users.id` with no `ondelete`. On PostgreSQL a single remaining row makes
the user delete fail outright, and `revoke_all_for_user` only sets
`revoked_at` — it does not remove the row. SQLite in tests does not enforce
foreign keys, so these tests assert the property directly: after deletion,
no table holds a row for the account (except anonymised cost records).
"""

from __future__ import annotations

import datetime as dt
import hashlib

import pytest
from sqlalchemy import text

from src.tradelens.db.models import Base
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import account
from src.tradelens.services.auth_sessions import SURFACE_WEBSITE

# Every table that is deleted by owner rather than through a trade. Kept
# literal so a table dropped from `account._OWNED_BY_USER` fails here by name.
OWNER_TABLES = (
    "auth_sessions",
    "auth_handoffs",
    "user_settings",
    "email_verifications",
    "password_resets",
    "ai_jobs",
    "trade_summary_results",
    "trade_drafts",
    "strategies",
    "trades",
    "corrections",
    "weekly_reviews",
)


def _session_row(user_id, token="t"):
    now = dt.datetime.now(dt.timezone.utc)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, "
                "expires_at, last_seen_at, surface) VALUES (:h,:u,:c,:e,:l,:s)"
            ),
            {
                "h": hashlib.sha256(("%s:%s" % (user_id, token)).encode()).hexdigest(),
                "u": user_id,
                "c": now,
                "e": now + dt.timedelta(hours=1),
                "l": now,
                "s": SURFACE_WEBSITE,
            },
        )
        db.commit()
    finally:
        db.close()


def _job_row(user_id):
    now = dt.datetime.now(dt.timezone.utc)
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO ai_jobs (user_id, kind, idempotency_key, status, "
                "payload, attempts, created_at) "
                "VALUES (:u, 'partner_turn', :k, 'succeeded', '{}', 0, :c)"
            ),
            {"u": user_id, "k": "key-%s" % user_id, "c": now},
        )
        db.commit()
    finally:
        db.close()


def _rows(user_id, table):
    db = SessionLocal()
    try:
        return db.execute(
            text("SELECT COUNT(*) FROM {} WHERE user_id = :u".format(table)),
            {"u": user_id},
        ).scalar()
    finally:
        db.close()


def test_session_rows_are_deleted_not_just_revoked(two_users):
    owner = two_users[1]
    _session_row(owner, "a")
    _session_row(owner, "b")
    assert _rows(owner, "auth_sessions") == 2
    assert account.delete_account(owner) is True
    assert _rows(owner, "auth_sessions") == 0


def test_job_rows_are_deleted_with_the_account(two_users):
    owner = two_users[1]
    _job_row(owner)
    assert account.delete_account(owner) is True
    assert _rows(owner, "ai_jobs") == 0


@pytest.mark.parametrize("table", OWNER_TABLES)
def test_no_owner_table_keeps_a_row_for_the_deleted_account(two_users, table):
    owner = two_users[1]
    _session_row(owner)
    _job_row(owner)
    assert account.delete_account(owner) is True
    assert _rows(owner, table) == 0, table


def test_another_accounts_sessions_and_jobs_are_untouched(two_users):
    first, owner = two_users
    _session_row(first, "theirs")
    _job_row(first)
    _session_row(owner)
    assert account.delete_account(owner) is True
    assert _rows(first, "auth_sessions") == 1
    assert _rows(first, "ai_jobs") == 1


def test_every_table_with_a_user_id_has_a_deletion_decision():
    """A table added later with a `user_id` must be deleted or anonymised.

    Without this, a new owner-scoped table would silently outlive the account
    it belongs to — or, if it has a non-cascading foreign key, make account
    deletion fail on PostgreSQL.
    """
    decided = {model.__tablename__ for model in account._OWNED_BY_USER}
    decided |= set(account.ANONYMISED)
    # Deleted in `delete_account` through the owner's trade ids, or as the
    # account row itself.
    decided |= {"trades", "screenshots", "aianalysis", "users"}
    with_user_id = {
        table.name for table in Base.metadata.sorted_tables if "user_id" in table.c
    }
    assert with_user_id - decided == set()
