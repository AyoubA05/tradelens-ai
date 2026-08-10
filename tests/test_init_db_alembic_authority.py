"""Alembic owns deployed schemas; init_db owns local bootstrap. Nothing else.

Production reached 2026-08-10 with a complete application schema and no
alembic_version row, and with users.email present but missing the unique index
its migration defines. Both came from one cause: ui/app.py called init_db() on
every boot, so each Streamlit Cloud restart ran create_all + _reconcile_columns
against the real Neon database. create_all never stamps, and
_reconcile_columns adds columns without ever creating indexes.

These tests make that combination impossible to recreate.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from src.tradelens.db.init_db import (
    SchemaManagedByAlembicError,
    UnmanagedRemoteSchemaError,
    bootstrap_if_local,
    init_db,
)


def _sqlite(tmp_path, name="local.db"):
    return create_engine(f"sqlite:///{tmp_path / name}")


def _mark_tracked(engine, revision="r8s9t0u1v2w3") -> None:
    """Give a database the alembic_version table Alembic would have created."""
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:r)"),
            {"r": revision},
        )


def test_local_sqlite_bootstrap_still_works(tmp_path):
    """The one job this module legitimately has."""
    engine = _sqlite(tmp_path)

    init_db(engine=engine)

    assert "users" in set(inspect(engine).get_table_names())


def test_an_alembic_tracked_database_is_refused(tmp_path):
    """Once migrations own a schema, create_all alongside them causes drift."""
    engine = _sqlite(tmp_path)
    init_db(engine=engine)
    _mark_tracked(engine)

    with pytest.raises(SchemaManagedByAlembicError):
        init_db(engine=engine)


def test_bootstrap_if_local_is_a_no_op_on_a_tracked_database(tmp_path):
    """Startup must not raise on a migrated database — it must not act at all."""
    engine = _sqlite(tmp_path)
    init_db(engine=engine)
    _mark_tracked(engine)

    assert bootstrap_if_local(engine=engine) is False


def test_bootstrap_if_local_reports_when_it_acted(tmp_path):
    engine = _sqlite(tmp_path)

    assert bootstrap_if_local(engine=engine) is True
    assert "users" in set(inspect(engine).get_table_names())


def test_a_non_sqlite_database_is_refused_without_an_explicit_opt_in(monkeypatch):
    """The guard that would have prevented the production drift entirely.

    Simulated rather than run against a real Postgres: the decision is made
    from engine.dialect.name, so faking that exercises the actual branch.
    """
    from src.tradelens.db import init_db as init_db_module

    engine = create_engine("sqlite://")
    # Patch the predicate rather than engine.dialect: SQLAlchemy's Engine does
    # not accept a substituted dialect, and the branch under test is decided by
    # this function anyway.
    monkeypatch.setattr(init_db_module, "_is_local_sqlite", lambda _engine: False)

    with pytest.raises(UnmanagedRemoteSchemaError):
        init_db(engine=engine)


def test_bootstrap_if_local_never_touches_a_non_sqlite_database(monkeypatch):
    """Application startup is the caller that caused this. It must be inert."""
    from src.tradelens.db import init_db as init_db_module

    engine = create_engine("sqlite://")
    # Patch the predicate rather than engine.dialect: SQLAlchemy's Engine does
    # not accept a substituted dialect, and the branch under test is decided by
    # this function anyway.
    monkeypatch.setattr(init_db_module, "_is_local_sqlite", lambda _engine: False)

    assert bootstrap_if_local(engine=engine) is False
    assert set(inspect(engine).get_table_names()) == set()


def test_app_startup_does_not_call_init_db_directly():
    """A source-level guard, because the risky call is one word away.

    Re-introducing `init_db()` in app.py would restore the exact behaviour that
    mutated production on every restart, and nothing else in the suite would
    notice.
    """
    from pathlib import Path

    raw = (
        Path(__file__).parent.parent / "src" / "tradelens" / "ui" / "app.py"
    ).read_text()
    # Comments explaining the old behaviour necessarily mention it by name, so
    # only executable lines are inspected.
    source = "\n".join(
        line for line in raw.splitlines() if not line.lstrip().startswith("#")
    )

    assert "bootstrap_if_local()" in source
    assert "init_db()" not in source, (
        "app.py must not call init_db() at startup — that is what ran DDL "
        "against production Neon on every boot"
    )
