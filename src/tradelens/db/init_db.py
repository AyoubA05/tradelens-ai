from sqlalchemy import inspect, text

from .session import engine as _default_engine, Base, DatabaseUnavailableError
from .models import Strategy, Trade, Screenshot  # noqa: F401


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


def init_db(engine=None):
    engine = engine or _default_engine
    if engine is None:
        # Fail closed. `create_all(bind=None)` would raise on its own, but with
        # SQLAlchemy's own wording and traceback rather than a type the caller
        # can recognise and report without leaking the URL.
        raise DatabaseUnavailableError("database unavailable")
    Base.metadata.create_all(bind=engine)
    _reconcile_columns(engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
