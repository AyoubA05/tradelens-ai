from sqlalchemy import inspect, text

from src.tradelens.db.session import SessionLocal, engine


def test_users_has_app_surface_defaulting_to_streamlit(two_users):
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "app_surface" in cols

    db = SessionLocal()
    try:
        surfaces = [r[0] for r in db.execute(text("SELECT app_surface FROM users"))]
    finally:
        db.close()
    assert surfaces and all(s == "streamlit" for s in surfaces)


def test_app_surface_accepts_the_nextjs_value(two_users):
    a, _ = two_users
    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE users SET app_surface = 'nextjs' WHERE id = :u"), {"u": a}
        )
        db.commit()
        value = db.execute(
            text("SELECT app_surface FROM users WHERE id = :u"), {"u": a}
        ).scalar()
    finally:
        db.close()
    assert value == "nextjs"
