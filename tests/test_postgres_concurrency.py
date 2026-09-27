"""Live PostgreSQL concurrency — production gate 1.

Skipped unless TRADELENS_PG_TEST_URL and TRADELENS_PG_TEST_ALLOW_DROP=1 are
set. The target's identity is checked (tests/pg_guard.py) before the public
schema is dropped; point it only at the disposable database.

SQLite ignores `FOR UPDATE`, so none of these guarantees can be shown by the
hermetic suite. Each scenario runs in a child process (tests/pg_concurrency_check.py).
"""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
PG_URL = os.getenv("TRADELENS_PG_TEST_URL")
PG_ALLOW_DROP = os.getenv("TRADELENS_PG_TEST_ALLOW_DROP") == "1"
pytestmark = pytest.mark.skipif(
    not PG_URL or not PG_ALLOW_DROP,
    reason=(
        "set TRADELENS_PG_TEST_URL, TRADELENS_PG_TEST_ALLOW_DROP=1, "
        "TRADELENS_PG_EXPECT_HOST and TRADELENS_PG_EXPECT_DATABASE to run "
        "against the disposable database"
    ),
)


def _child_env() -> dict:
    env = os.environ.copy()
    env["DATABASE_URL"] = PG_URL
    env["DEMO_MODE"] = "true"
    return env


@pytest.fixture(scope="module")
def migrated_database():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from pg_guard import require_disposable_database
    from sqlalchemy import create_engine, text

    identity = require_disposable_database(PG_URL)
    print(f"\ngate-1 target: {json.dumps(identity)}")

    engine = create_engine(PG_URL)

    def reset():
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))

    reset()
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env=_child_env(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "alembic upgrade head failed"
    try:
        yield identity
    finally:
        reset()
        engine.dispose()


def _scenario(name: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "pg_concurrency_check.py"), name],
        cwd=ROOT,
        env=_child_env(),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    observed = json.loads(result.stdout.strip().splitlines()[-1])
    print(f"\n{name}: {json.dumps(observed)}")
    return observed


def test_concurrent_recap_saves_leave_exactly_one_row(migrated_database):
    """weekly_reviews has no unique (user_id, week_start). Twelve simultaneous
    saves across both paths must still leave one row, because both lock the
    week's trades first."""
    observed = _scenario("weekly_unique")
    assert observed == {"rows_per_round": [1] * 10, "errors": []}


def test_the_rolling_limit_holds_under_parallel_enqueues(migrated_database):
    observed = _scenario("enqueue_limit")
    assert observed["errors"] == [] and observed["same_errors"] == []
    assert (observed["created"], observed["refused"], observed["rows"]) == (5, 15, 5)
    assert (observed["same_created"], observed["same_ids"], observed["same_rows"]) == (
        1,
        1,
        1,
    )


def test_deleting_an_account_during_a_save_resurrects_nothing(migrated_database):
    observed = _scenario("delete_while_saving")
    assert observed["save_held_lock"] is True, observed
    assert observed["delete_seconds"] >= 2.0, observed
    assert observed["delete_error"] is None, observed
    assert observed["save_error"] is None, observed  # no deadlock either way
    assert observed["user_rows"] == 0 and observed["review_rows"] == 0, observed


def test_deleting_an_account_during_a_fast_save_neither_fails_nor_resurrects(
    migrated_database,
):
    """The realistic timing: the save inserts well inside the one-second
    deadlock check. Deletion locked the owner row then the trades while the
    save locked the trades then needed the owner row for its foreign key, so
    Postgres aborted the deletion. Both now take the owner row first."""
    observed = _scenario("delete_during_fast_save")
    # Real contention, not a lucky ordering: deletion started while the save
    # held its locks and had to wait out most of the 0.3s hold.
    assert observed["save_held_lock"] is True, observed
    assert observed["delete_seconds"] >= 0.2, observed
    assert observed["delete_error"] is None, observed
    assert observed["save_error"] is None, observed
    assert observed["user_rows"] == 0 and observed["review_rows"] == 0, observed


def test_deleting_an_account_during_a_trade_summary_save_neither_fails_nor_resurrects(
    migrated_database,
):
    observed = _scenario("delete_during_fast_trade_summary_save")
    assert observed["save_held_lock"] is True, observed
    assert observed["delete_seconds"] >= 0.2, observed
    assert observed["delete_error"] is None, observed
    assert observed["save_error"] is None, observed
    assert observed["user_rows"] == 0 and observed["summary_rows"] == 0, observed


def test_a_save_after_account_deletion_writes_nothing(migrated_database):
    observed = _scenario("save_after_delete")
    assert observed["user_rows"] == 0 and observed["review_rows"] == 0, observed
    assert observed["save_error"] == "ReviewSourceGone", observed


def test_locked_sources_make_a_trade_edit_wait(migrated_database):
    """Proves `FOR UPDATE` is real here: the holder sleeps 2s with the lock."""
    observed = _scenario("source_lock_blocks_writers")
    assert observed["writer_waited_seconds"] >= 1.5, observed


def test_the_database_itself_refuses_a_second_recap_for_one_week(migrated_database):
    """Defence in depth under the locks: migration i5j6k7l8m9n0."""
    observed = _scenario("weekly_constraint")
    assert observed["duplicate"] == "refused", observed
    assert observed["ownerless_rows"] >= 2, observed
