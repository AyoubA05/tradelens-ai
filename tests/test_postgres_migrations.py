"""Guarded live PostgreSQL migration verification for a disposable database."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, inspect, text


ROOT = Path(__file__).resolve().parents[1]
PG_URL = os.getenv("TRADELENS_PG_TEST_URL")
PG_ALLOW_DROP = os.getenv("TRADELENS_PG_TEST_ALLOW_DROP") == "1"
pytestmark = pytest.mark.skipif(
    not PG_URL or not PG_ALLOW_DROP,
    reason=(
        "set TRADELENS_PG_TEST_URL and TRADELENS_PG_TEST_ALLOW_DROP=1 "
        "to run against a disposable database whose public schema is dropped"
    ),
)


def _run_alembic(args: list[str], database_url: str) -> None:
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env["DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Alembic {' '.join(args)} failed"


@pytest.fixture
def disposable_public_schema():
    engine = create_engine(PG_URL)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        yield PG_URL
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        engine.dispose()


def test_postgres_chain_round_trips_task_one(disposable_public_schema):
    for args in (
        ["upgrade", "head"],
        ["downgrade", "p6q7r8s9t0u1"],
        ["upgrade", "head"],
    ):
        _run_alembic(args, disposable_public_schema)

    engine = create_engine(disposable_public_schema)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            strategy_columns = {
                column["name"] for column in inspector.get_columns("strategies")
            }
            assert "user_id" in strategy_columns
            assert "user_settings" in inspector.get_table_names()
            unique_names = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("user_settings")
            }
            assert "uq_user_settings_user_key" in unique_names
    finally:
        engine.dispose()
