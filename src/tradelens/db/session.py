from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from src.tradelens.config import settings

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


engine = build_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
