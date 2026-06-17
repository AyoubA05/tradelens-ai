from .session import engine, Base
from .models import Strategy, Trade, Screenshot  # noqa: F401 — imported for SQLAlchemy metadata side-effects

def init_db():
    """Create all tables. Safe to call multiple times — no-op if tables already exist."""
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
