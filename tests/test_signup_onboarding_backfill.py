"""Backfill for site accounts that already supplied personal details at signup.

The migration promotes ``onboarding_completed`` for opaque site-created
accounts whose personal details are already stored, so verified first-time
users stop being asked for the same fields a second time.

What the cases below exist to pin is everything the migration must *not* do.
It touches one column on a narrow predicate, and each of the ways that could
go wrong is a separate failure with a different blast radius: promoting an
incomplete account skips a form it genuinely needed, touching a legacy account
changes rows that predate the whole feature, and moving
``strategy_profile_completed`` or the verification fields would silently open
a gate that belongs to Streamlit or to email verification.
"""

from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import create_engine, text


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PREVIOUS_REVISION = "w3x4y5z6a7b8"


def _alembic(*args: str, url: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": url},
        cwd=_REPO_ROOT,
        check=False,
    )


def test_complete_site_signup_profiles_skip_redundant_personal_onboarding(tmp_path):
    url = f"sqlite:///{tmp_path / 'site-signup-backfill.db'}"
    before = _alembic("upgrade", _PREVIOUS_REVISION, url=url)
    assert before.returncode == 0, before.stderr

    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO users
                    (id, username, password_hash, email, is_active,
                     full_name, birthday, referral_source,
                     onboarding_completed, strategy_profile_completed,
                     email_verification_required)
                VALUES
                    (1, 'ayoub', 'legacy-hash', NULL, 1,
                     'Legacy Person', '1994-02-17', 'Reddit',
                     false, false, false),
                    (3, 'u_0123456789abcdef', 'smoke-hash', 'smoke@example.com', 1,
                     'Smoke Tester', '1994-02-17', 'Reddit',
                     false, false, true),
                    (4, 'u_fedcba9876543210', 'partial-hash', 'partial@example.com', 1,
                     'Partial Tester', '1994-02-17', NULL,
                     false, false, true)
                """
            )
        )

    upgraded = _alembic("upgrade", "head", url=url)
    assert upgraded.returncode == 0, upgraded.stderr

    with engine.begin() as connection:
        states = {
            username: (onboarding, strategy)
            for username, onboarding, strategy in connection.execute(
                text(
                    "SELECT username, onboarding_completed, strategy_profile_completed "
                    "FROM users ORDER BY id"
                )
            )
        }

    assert states["u_0123456789abcdef"] == (True, False)
    assert states["u_fedcba9876543210"] == (False, False)
    assert states["ayoub"] == (False, False), "legacy accounts must not be touched"


def _seed(engine) -> None:
    """One row per case in the approved matrix, plus the exact-case legacy pair."""
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO users
                    (id, username, password_hash, email, is_active,
                     full_name, birthday, referral_source,
                     onboarding_completed, strategy_profile_completed,
                     email_verification_required, email_verified_at)
                VALUES
                    -- C and D: the two legacy accounts, exact case preserved.
                    (1, 'ayoub', 'legacy-hash', NULL, 1,
                     'Legacy One', '1994-02-17', 'Reddit',
                     false, false, false, NULL),
                    (2, 'Ayoub', 'legacy-hash-2', NULL, 1,
                     'Legacy Two', '1994-02-17', 'Reddit',
                     false, false, false, NULL),
                    -- A: complete opaque site account.
                    (3, 'u_0123456789abcdef', 'h', 'a@example.invalid', 1,
                     'Complete Tester', '1994-02-17', 'Reddit',
                     false, false, true, NULL),
                    -- B: incomplete — no referral_source.
                    (4, 'u_fedcba9876543210', 'h', 'b@example.invalid', 1,
                     'No Referral', '1994-02-17', NULL,
                     false, false, true, NULL),
                    -- B: incomplete — no full_name.
                    (5, 'u_aaaabbbbccccdddd', 'h', 'c@example.invalid', 1,
                     NULL, '1994-02-17', 'Reddit',
                     false, false, true, NULL),
                    -- B: incomplete — blank full_name, which is not "present".
                    (6, 'u_1111222233334444', 'h', 'd@example.invalid', 1,
                     '   ', '1994-02-17', 'Reddit',
                     false, false, true, NULL),
                    -- B: incomplete — no birthday.
                    (7, 'u_5555666677778888', 'h', 'e@example.invalid', 1,
                     'No Birthday', NULL, 'Reddit',
                     false, false, true, NULL),
                    -- B: referral_source outside the accepted set.
                    (8, 'u_9999aaaabbbbcccc', 'h', 'f@example.invalid', 1,
                     'Bad Referral', '1994-02-17', 'Carrier pigeon',
                     false, false, true, NULL),
                    -- B: no email, so not a completed site signup.
                    (9, 'u_ddddeeeeffff0000', 'h', NULL, 1,
                     'No Email', '1994-02-17', 'Reddit',
                     false, false, true, NULL),
                    -- Already true: must stay true, and stay untouched.
                    (10, 'u_abcdabcdabcdabcd', 'h', 'g@example.invalid', 1,
                     'Already Done', '1994-02-17', 'Reddit',
                     true, false, false, '2026-08-01 00:00:00'),
                    -- A verified complete account: verification state must not move.
                    (11, 'u_beefbeefbeefbeef', 'h', 'h@example.invalid', 1,
                     'Verified Tester', '1994-02-17', 'Friend',
                     false, false, false, '2026-08-02 00:00:00')
                """
            )
        )


def _states(engine) -> dict:
    with engine.begin() as connection:
        return {
            row[0]: {
                "onboarding": bool(row[1]),
                "strategy": bool(row[2]),
                "verification_required": bool(row[3]),
                "verified_at": row[4],
            }
            for row in connection.execute(
                text(
                    "SELECT username, onboarding_completed,"
                    " strategy_profile_completed, email_verification_required,"
                    " email_verified_at FROM users ORDER BY id"
                )
            )
        }


def _migrated(tmp_path, name: str):
    """Seed at the previous revision, upgrade to head, return the engine."""
    url = f"sqlite:///{tmp_path / name}.db"
    before = _alembic("upgrade", _PREVIOUS_REVISION, url=url)
    assert before.returncode == 0, before.stderr
    engine = create_engine(url)
    _seed(engine)
    upgraded = _alembic("upgrade", "head", url=url)
    assert upgraded.returncode == 0, upgraded.stderr
    return engine, url


def test_case_a_complete_site_account_is_promoted(tmp_path):
    engine, _ = _migrated(tmp_path, "case-a")
    assert _states(engine)["u_0123456789abcdef"]["onboarding"] is True


def test_case_b_incomplete_site_accounts_are_left_alone(tmp_path):
    """Every way an account can fall short of "personal details already given"."""
    engine, _ = _migrated(tmp_path, "case-b")
    states = _states(engine)
    for username in (
        "u_fedcba9876543210",  # no referral_source
        "u_aaaabbbbccccdddd",  # no full_name
        "u_1111222233334444",  # blank full_name
        "u_5555666677778888",  # no birthday
        "u_9999aaaabbbbcccc",  # referral_source not in the accepted set
        "u_ddddeeeeffff0000",  # no email
    ):
        assert states[username]["onboarding"] is False, username


def test_cases_c_and_d_legacy_accounts_are_untouched(tmp_path):
    """Both legacy rows, including the exact-case second one."""
    engine, _ = _migrated(tmp_path, "case-cd")
    states = _states(engine)
    assert states["ayoub"]["onboarding"] is False
    assert states["Ayoub"]["onboarding"] is False


def test_case_e_strategy_profile_flag_is_never_changed(tmp_path):
    """Streamlit owns this gate; the migration must not open it for anyone."""
    engine, _ = _migrated(tmp_path, "case-e")
    assert all(state["strategy"] is False for state in _states(engine).values())


def test_case_f_email_verification_state_is_never_changed(tmp_path):
    """Promoting onboarding must not let anyone past the verification gate."""
    engine, _ = _migrated(tmp_path, "case-f")
    states = _states(engine)
    assert states["u_0123456789abcdef"]["verification_required"] is True
    assert states["u_0123456789abcdef"]["verified_at"] is None
    assert states["u_beefbeefbeefbeef"]["verification_required"] is False
    assert states["u_beefbeefbeefbeef"]["verified_at"] is not None
    assert states["ayoub"]["verification_required"] is False


def test_an_already_complete_account_is_not_disturbed(tmp_path):
    engine, _ = _migrated(tmp_path, "already")
    assert _states(engine)["u_abcdabcdabcdabcd"]["onboarding"] is True


def test_the_migration_creates_no_users_and_no_strategies(tmp_path):
    engine, _ = _migrated(tmp_path, "creates-nothing")
    with engine.begin() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar() == 11
        assert connection.execute(text("SELECT count(*) FROM strategies")).scalar() == 0


def test_downgrade_runs_and_leaves_recognised_state_intact(tmp_path):
    """The downgrade is a deliberate no-op, and that is the honest choice.

    Once an account's stored details have been recognised as complete, setting
    the flag back would recreate the duplicate form — and the migration cannot
    tell an account it promoted from one that was already true, so a faithful
    reversal is not available. What must hold is that downgrading still runs
    cleanly and destroys nothing.
    """
    engine, url = _migrated(tmp_path, "downgrade")
    promoted = _states(engine)

    down = _alembic("downgrade", _PREVIOUS_REVISION, url=url)
    assert down.returncode == 0, down.stderr

    after = _states(engine)
    assert after == promoted, "downgrade must not alter user state"

    with engine.begin() as connection:
        version = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
    assert version == _PREVIOUS_REVISION

    # And upgrading again is idempotent.
    again = _alembic("upgrade", "head", url=url)
    assert again.returncode == 0, again.stderr
    assert _states(engine) == promoted
