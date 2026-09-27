"""Identity guard for destructive live-PostgreSQL tests (production gate 1).

Every live-Postgres test drops the public schema. Before it may do so, the
target must be proven to be the disposable database the owner named: the URL's
host has to equal ``TRADELENS_PG_EXPECT_HOST`` exactly, and, when
``TRADELENS_PG_EXPECT_DATABASE`` is set, the server's ``current_database()``
has to match it. Anything else aborts before a single statement is sent that
could change data.

Not collected by pytest (no ``test_`` prefix). Never prints the URL.
"""

import os
from urllib.parse import urlsplit


class NotTheDisposableDatabase(RuntimeError):
    pass


def require_disposable_database(url: str) -> dict:
    expected_host = os.getenv("TRADELENS_PG_EXPECT_HOST", "").strip()
    if not expected_host:
        raise NotTheDisposableDatabase(
            "set TRADELENS_PG_EXPECT_HOST to the disposable database's host"
        )
    host = urlsplit(url).hostname or ""
    if host != expected_host:
        raise NotTheDisposableDatabase(
            "TRADELENS_PG_TEST_URL does not point at TRADELENS_PG_EXPECT_HOST"
        )

    from sqlalchemy import create_engine, text

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            database, user, version = connection.execute(
                text("SELECT current_database(), current_user, version()")
            ).one()
    finally:
        engine.dispose()

    expected_database = os.getenv("TRADELENS_PG_EXPECT_DATABASE", "").strip()
    if expected_database and database != expected_database:
        raise NotTheDisposableDatabase(
            "current_database() does not match TRADELENS_PG_EXPECT_DATABASE"
        )
    return {
        "host": host,
        "database": database,
        "user": user,
        "server": version.split(",")[0],
    }
