"""Schema bootstrap for local development and tests.

**Alembic is the authority on deployed schemas. This module is not.**

That division did not exist before 2026-08-10, and its absence is what put
production in the state this docstring now guards against. ``init_db()`` was
called unconditionally from ``ui/app.py`` on every boot, so each Streamlit Cloud
restart ran ``create_all`` + ``_reconcile_columns`` against the production Neon
database. Two consequences followed:

* Production got a full application schema and **no** ``alembic_version`` row,
  because neither function stamps one. Alembic never knew the database existed.
* ``_reconcile_columns`` adds missing *columns* and creates **no indexes**, so
  ``users.email`` arrived without the unique index its migration defines. Every
  index or constraint introduced after its table was first created is exposed to
  the same gap, and columns that are ``NOT NULL`` without a server default are
  skipped outright.

The policy now enforced in code:

* A database Alembic already tracks is refused outright — ``upgrade`` owns it.
* A non-SQLite database is refused unless a caller explicitly opts in, because
  that is how a second untracked production schema gets created by accident.
* Local SQLite bootstrap is unchanged, which is all this module was ever for.
* Application startup calls :func:`bootstrap_if_local`, which is a documented
  no-op against anything that is not a local SQLite file. Startup can no longer
  mutate a deployed schema behind Alembic's back.
"""

from sqlalchemy import inspect, text

from .session import engine as _default_engine, Base, DatabaseUnavailableError
from .models import Strategy, Trade, Screenshot  # noqa: F401


class SchemaManagedByAlembicError(RuntimeError):
    """The database is tracked by Alembic, so this module must not touch it."""


class UnmanagedRemoteSchemaError(RuntimeError):
    """Refusing to bootstrap a non-SQLite database that Alembic does not track.

    Creating one of these silently is precisely how production ended up with an
    application schema Alembic had never heard of.
    """


def _is_alembic_tracked(engine) -> bool:
    return "alembic_version" in set(inspect(engine).get_table_names())


def _is_local_sqlite(engine) -> bool:
    return engine.dialect.name == "sqlite"


def _reconcile_columns(engine) -> None:
    """Add model columns that are missing from already-existing tables.

    ``create_all()`` creates missing *tables* but never alters existing ones,
    so a persisted database (e.g. Streamlit Cloud's disk, which survives across
    deploys) drifts whenever a new column is added to a model. The app then
    SELECTs a column the physical table lacks and crashes on load.

    This is the automatic form of the historical ``catch_up_schema`` migration:
    for each mapped table that already exists, ``ALTER TABLE ADD COLUMN`` for any
    column the model declares but the table lacks. Only nullable / server-default
    columns are added — the only kind SQLite and PostgreSQL can add to a
    populated table — which covers every column added to date. Idempotent, and a
    no-op on a freshly created database.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    preparer = engine.dialect.identifier_preparer

    with engine.begin() as conn:
        for table in Base.metadata.tables.values():
            if table.name not in existing_tables:
                continue  # brand-new table — create_all already made it in full
            have = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                if not col.nullable and col.server_default is None:
                    # Cannot be safely added to a populated table; skip.
                    continue
                col_type = col.type.compile(dialect=engine.dialect)
                ddl = (
                    f"ALTER TABLE {preparer.quote(table.name)} "
                    f"ADD COLUMN {preparer.quote(col.name)} {col_type}"
                )
                conn.execute(text(ddl))


def init_db(engine=None, *, allow_unmanaged_remote: bool = False):
    """Create and reconcile the schema. Local development and tests only.

    Raises ``SchemaManagedByAlembicError`` when the database already carries an
    ``alembic_version`` row: from that point Alembic owns the schema, and a
    ``create_all`` alongside it produces exactly the kind of divergence that
    migrations exist to prevent.

    Raises ``UnmanagedRemoteSchemaError`` for a non-SQLite database that Alembic
    does not track, unless ``allow_unmanaged_remote=True`` is passed explicitly.
    The opt-in exists for the one legitimate case — deliberately bootstrapping a
    fresh remote database before stamping it — and being a keyword argument
    means no caller reaches it by accident.
    """
    engine = engine or _default_engine
    if engine is None:
        # Fail closed. `create_all(bind=None)` would raise on its own, but with
        # SQLAlchemy's own wording and traceback rather than a type the caller
        # can recognise and report without leaking the URL.
        raise DatabaseUnavailableError("database unavailable")

    if _is_alembic_tracked(engine):
        raise SchemaManagedByAlembicError(
            "This database is tracked by Alembic. Run `alembic upgrade head` "
            "instead; init_db must not alter a migrated schema."
        )

    if not _is_local_sqlite(engine) and not allow_unmanaged_remote:
        raise UnmanagedRemoteSchemaError(
            "Refusing to bootstrap a non-SQLite database that Alembic does not "
            "track. Migrate it with Alembic, or pass "
            "allow_unmanaged_remote=True if you are deliberately creating a "
            "fresh database that you will stamp immediately afterwards."
        )

    Base.metadata.create_all(bind=engine)
    _reconcile_columns(engine)


def bootstrap_if_local(engine=None) -> bool:
    """Bootstrap a local SQLite database; do nothing anywhere else.

    This is what application startup calls. It returns whether it did anything,
    and it never raises for the "not my job" cases — a deployed database simply
    is not this function's business.

    Startup used to call ``init_db()`` directly, which is why every Streamlit
    Cloud restart quietly ran DDL against production Neon.
    """
    engine = engine or _default_engine
    if engine is None:
        raise DatabaseUnavailableError("database unavailable")
    if not _is_local_sqlite(engine) or _is_alembic_tracked(engine):
        return False
    init_db(engine=engine)
    return True


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
