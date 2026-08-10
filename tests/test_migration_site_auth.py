"""Schema contract for the site-hosted auth migration (s9t0u1v2w3x4).

Three things are locked down here, in order of how expensive they are to get
wrong:

1. The legacy backfill. Existing production accounts must survive a migration
   that introduces steps they never took, and must do so without the data
   claiming they took them.
2. Row counts. This revision adds columns and tables; it must move no rows.
3. The column types, because Postgres is production and a DATE stored as TEXT
   is the kind of thing that only hurts a year later.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime

from sqlalchemy import create_engine, text

from src.tradelens.db.models import AuthAttempt, AuthHandoff, AuthSession, User

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PREVIOUS_REVISION = "r8s9t0u1v2w3"


def _alembic(*args: str, url: str) -> subprocess.CompletedProcess:
    """Run alembic against an isolated database."""
    # `python -m alembic`, not a bare `alembic`: the console script is only on
    # PATH when the venv is activated, which it is not under a bare pytest run.
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=_REPO_ROOT,
        check=False,
    )


# ---------------------------------------------------------------------------
# Model shape
# ---------------------------------------------------------------------------


def test_user_carries_the_onboarding_and_profile_columns():
    user = User(username="ayoub", password_hash="x")
    for column in (
        "full_name",
        "birthday",
        "referral_source",
        "referral_source_other",
        "onboarding_completed",
        "strategy_profile_completed",
        "email_verified_at",
        "email_verification_required",
    ):
        assert hasattr(user, column), f"User is missing {column}"


def test_profile_columns_use_real_database_types():
    """Postgres is production, so a birthday is a DATE, not a string.

    The older columns on this table store ISO strings, which is why this is
    worth asserting rather than assuming: following that convention would have
    been the path of least resistance and the wrong choice.
    """
    columns = User.__table__.columns
    assert columns["birthday"].type.python_type is date
    assert columns["email_verified_at"].type.python_type is datetime
    assert columns["email_verified_at"].type.timezone is True
    assert columns["onboarding_completed"].type.python_type is bool
    assert columns["strategy_profile_completed"].type.python_type is bool
    assert columns["email_verification_required"].type.python_type is bool


def test_new_profile_columns_are_nullable_so_the_migration_cannot_break_rows():
    columns = User.__table__.columns
    for name in ("full_name", "birthday", "referral_source", "referral_source_other"):
        assert columns[name].nullable, f"{name} must stay nullable for legacy rows"
    # The flags are NOT NULL, which is safe only because they carry a server
    # default; without one the ALTER would fail against a populated table.
    for name in (
        "onboarding_completed",
        "strategy_profile_completed",
        "email_verification_required",
    ):
        assert not columns[name].nullable
        assert columns[name].server_default is not None, (
            f"{name} is NOT NULL, so it needs a server default or the ALTER "
            f"fails on every existing row"
        )


def test_auth_tables_store_only_hashed_credentials():
    """A database read must not yield anything replayable."""
    for model in (AuthHandoff, AuthSession):
        columns = model.__table__.columns
        assert "token_hash" in columns
        assert "token" not in columns, f"{model.__name__} must not store a raw token"
        assert columns["token_hash"].unique is True
        assert columns["token_hash"].index is True


def test_auth_attempts_can_distinguish_a_failure_from_a_success():
    """Per-identifier limits count failures only.

    Without this column the limit counts every attempt, and an attacker locks a
    known user out by deliberately burning their quota.
    """
    columns = AuthAttempt.__table__.columns
    assert "succeeded" in columns
    assert columns["succeeded"].type.python_type is bool
    assert columns["bucket"].index is True


# ---------------------------------------------------------------------------
# Migration round trip
# ---------------------------------------------------------------------------


def test_migration_upgrades_and_downgrades_cleanly(tmp_path):
    """A downgrade that has never been executed is not a rollback plan."""
    url = f"sqlite:///{tmp_path / 'roundtrip.db'}"

    up = _alembic("upgrade", "head", url=url)
    assert up.returncode == 0, up.stderr

    down = _alembic("downgrade", "-1", url=url)
    assert down.returncode == 0, down.stderr

    again = _alembic("upgrade", "head", url=url)
    assert again.returncode == 0, again.stderr


# ---------------------------------------------------------------------------
# Backfill — the part that touches real production rows
# ---------------------------------------------------------------------------


def _seed_pre_migration(url: str) -> None:
    """Build the schema one revision back and put legacy-shaped rows in it."""
    result = _alembic("upgrade", _PREVIOUS_REVISION, url=url)
    assert result.returncode == 0, result.stderr

    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, username, password_hash, email, is_active) "
                "VALUES (1, 'withprofile', 'h', 'a@example.com', 1), "
                "       (2, 'noprofile',   'h', NULL,            1)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO strategies (user_id, name, is_active) "
                "VALUES (1, 'SMC', 1)"
            )
        )


def test_legacy_users_are_exempted_not_falsely_marked_verified(tmp_path):
    """The heart of the legacy rule.

    Backfilling `email_verified_at = now()` would have been one line shorter and
    would have let legacy users log in just the same. It is rejected because it
    writes a claim into the data that is not true: nobody ever confirmed those
    addresses. Exempting them with a flag keeps the record honest and leaves
    "require verification of old accounts too" as one boolean per user.
    """
    url = f"sqlite:///{tmp_path / 'backfill.db'}"
    _seed_pre_migration(url)
    assert _alembic("upgrade", "head", url=url).returncode == 0

    engine = create_engine(url)
    with engine.begin() as conn:
        verified, required = conn.execute(
            text(
                "SELECT email_verified_at, email_verification_required "
                "FROM users WHERE username = 'withprofile'"
            )
        ).one()

    assert verified is None, "must not fabricate a verification timestamp"
    assert not required, "legacy accounts must be exempt from verification"


def test_legacy_users_skip_the_personal_info_onboarding(tmp_path):
    url = f"sqlite:///{tmp_path / 'onboarding.db'}"
    _seed_pre_migration(url)
    assert _alembic("upgrade", "head", url=url).returncode == 0

    engine = create_engine(url)
    with engine.begin() as conn:
        rows = dict(
            conn.execute(text("SELECT username, onboarding_completed FROM users")).all()
        )

    assert all(rows.values()), "legacy users never saw the form; do not trap them"


def test_strategy_completion_is_backfilled_from_the_existing_profile(tmp_path):
    """Users with a profile skip the first-run step; users without get it once."""
    url = f"sqlite:///{tmp_path / 'strategy.db'}"
    _seed_pre_migration(url)
    assert _alembic("upgrade", "head", url=url).returncode == 0

    engine = create_engine(url)
    with engine.begin() as conn:
        rows = dict(
            conn.execute(
                text("SELECT username, strategy_profile_completed FROM users")
            ).all()
        )

    assert rows["withprofile"], "an active profile means the step is already done"
    assert not rows["noprofile"], "no profile means exactly one first-run pass"


def test_migration_changes_no_row_counts(tmp_path):
    """This revision adds columns and tables. It must move no rows anywhere."""
    url = f"sqlite:///{tmp_path / 'counts.db'}"
    _seed_pre_migration(url)
    engine = create_engine(url)

    tables = ("users", "strategies")
    with engine.begin() as conn:
        before = {
            t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in tables
        }

    assert _alembic("upgrade", "head", url=url).returncode == 0

    with engine.begin() as conn:
        after = {
            t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in tables
        }

    assert before == after
