import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from src.tradelens.config import settings

_log = logging.getLogger(__name__)


class DatabaseUnavailableError(RuntimeError):
    """The configured database could not be built or reached.

    Deliberately carries no detail. Every caller that reports this to a human
    must be able to do so without inspecting it, because the information this
    exception would otherwise carry — the URL, the host, the driver, the
    credentials embedded in a DSN — is exactly what must not be shown.
    """


def _safe_reason(exc: BaseException) -> str:
    """The most that may be said about a database failure.

    The exception TYPE NAME and nothing else. SQLAlchemy raises
    ``ArgumentError``/``NoSuchModuleError`` with the offending URL inlined in
    ``str(exc)``, and a DSN carries the password, so neither the message nor
    the traceback may reach a log line, let alone a page. A class name cannot
    contain a credential.
    """
    return type(exc).__name__


# Single source of truth: the URL comes from config (env DATABASE_URL / .env),
# defaulting to the local SQLite file. This keeps session.py consistent with
# config and lets tests point at an isolated DB via the DATABASE_URL env var.
DATABASE_URL = settings.database_url


def build_engine(url: str, **overrides):
    """Create an Engine with per-dialect connect/pool settings.

    SQLite needs check_same_thread=False for Streamlit's threads; that arg is
    SQLite-only and psycopg2 rejects it. Postgres (Neon) gets pool_pre_ping so a
    connection dropped by scale-to-zero is transparently replaced. `overrides`
    lets tests inject e.g. poolclass=NullPool to avoid real connections.
    """
    kwargs = dict(overrides)
    if url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {"check_same_thread": False})
        if ":memory:" not in url and url.startswith("sqlite:///"):
            Path(url[len("sqlite:///") :]).parent.mkdir(parents=True, exist_ok=True)
    else:
        kwargs.setdefault("pool_pre_ping", True)
    return create_engine(url, **kwargs)


# Engine construction is CONTAINED, not allowed to escape as an import-time
# exception. It used to escape, and the consequence was measured rather than
# imagined: with an unusable DATABASE_URL the failure surfaced before any page
# rendered, so Streamlit painted its own error view — a full traceback, with
# the connection string in it, in the browser.
#
# Containment is not a fallback. `engine` becomes None and STAYS None; nothing
# here quietly substitutes SQLite, an empty database, or any other target. A
# deployment configured to talk to Postgres must never silently start writing
# to a local file where a different tenant's data would appear to be missing
# and new data would be written somewhere nobody is looking.
try:
    engine = build_engine(DATABASE_URL)
except Exception as exc:  # noqa: BLE001 — contained and reported without detail
    _log.error(
        "Database engine unavailable (%s). Check the DATABASE_URL setting; "
        "its value is deliberately not logged.",
        _safe_reason(exc),
    )
    engine = None

_sessionmaker = (
    sessionmaker(bind=engine, autoflush=False, autocommit=False)
    if engine is not None
    else None
)


def SessionLocal(*args, **kwargs):
    """A session, or a refusal. Never a session bound to nothing.

    A callable rather than the `sessionmaker` instance it replaces: every one
    of the 80-odd call sites uses it as ``SessionLocal()``, so the shape is
    unchanged, and `sessionmaker(bind=None)` would otherwise hand back a
    session that fails later, further from the cause, with a message that is
    not ours to control.
    """
    if _sessionmaker is None:
        raise DatabaseUnavailableError("database unavailable")
    return _sessionmaker(*args, **kwargs)


def database_ready() -> bool:
    """Whether the engine exists. Does not connect."""
    return engine is not None


class Base(DeclarativeBase):
    pass


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
