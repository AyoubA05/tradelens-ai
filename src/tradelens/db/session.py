from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from src.tradelens.config import settings

# Single source of truth: the URL comes from config (env DATABASE_URL / .env),
# defaulting to the local SQLite file. This keeps session.py consistent with
# config and lets tests point at an isolated DB via the DATABASE_URL env var.
DATABASE_URL = settings.database_url

# Ensure the parent directory exists for file-based SQLite URLs.
if DATABASE_URL.startswith("sqlite:///") and ":memory:" not in DATABASE_URL:
    _db_file = Path(DATABASE_URL[len("sqlite:///") :])
    _db_file.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
