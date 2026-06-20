from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

_DB_DIR = Path(__file__).resolve().parents[3] / "data"
_DB_DIR.mkdir(exist_ok=True)
DATABASE_URL = f"sqlite:///{_DB_DIR / 'tradelens.db'}"

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
