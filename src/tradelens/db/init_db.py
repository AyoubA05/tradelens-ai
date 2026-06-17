from .session import engine, Base
from .models import Strategy, Trade, Screenshot


def init_db():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
