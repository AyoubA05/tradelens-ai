"""build_engine(url): per-dialect connect/pool settings (SP2).

SQLite needs check_same_thread=False (Streamlit threads); that arg is
SQLite-only and psycopg2 rejects it. Postgres (Neon) needs pool_pre_ping so
connections dropped by scale-to-zero are transparently replaced.
"""

from src.tradelens.db.session import build_engine


def test_sqlite_engine_connects(tmp_path):
    from sqlalchemy import text

    eng = build_engine(f"sqlite:///{tmp_path / 'x.db'}")
    assert eng.dialect.name == "sqlite"
    # Proves the SQLite-only check_same_thread connect-arg didn't break creation.
    with eng.connect() as c:
        assert c.execute(text("SELECT 1")).scalar() == 1


def test_postgres_url_builds_without_sqlite_args():
    # Must NOT raise: check_same_thread is SQLite-only and psycopg2 rejects it.
    # NullPool avoids opening a real connection at build time.
    from sqlalchemy.pool import NullPool

    eng = build_engine("postgresql://u:p@localhost:5432/db", poolclass=NullPool)
    assert eng.dialect.name == "postgresql"
    assert eng.pool.__class__.__name__ == "NullPool"


def test_postgres_enables_pre_ping():
    from sqlalchemy.pool import NullPool

    eng = build_engine("postgresql://u:p@localhost:5432/db", poolclass=NullPool)
    assert eng.pool._pre_ping is True
