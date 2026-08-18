import sys
from pathlib import Path

import pytest

# Ensure `src.tradelens` is importable from all test files
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def _isolate_streamlit_secrets(monkeypatch):
    """Keep a developer's real ``.streamlit/secrets.toml`` out of the test run.

    ``st.secrets`` lazily loads from ``./.streamlit/secrets.toml`` relative to the
    CWD. When a developer has real credentials there (e.g. TRADELENS_USERNAME),
    those leak into tests that assume an empty secrets store and assert the demo
    fallback. Pinning the parsed mapping to ``{}`` makes the suite deterministic
    on every machine without touching the real file. Tests that need specific
    secrets set ``st.secrets`` themselves (e.g. AppTest.secrets).
    """
    # Most UI tests predate site-hosted auth and intentionally enter pages by
    # setting the legacy ``authenticated`` session-state marker. Keep that
    # test harness explicit now that production defaults to website login.
    # The auth-fallback tests remove this variable themselves so they still
    # exercise the real default-off behavior.
    monkeypatch.setenv("ENABLE_LEGACY_STREAMLIT_AUTH", "true")

    try:
        import streamlit as st

        saved = st.secrets._secrets
        st.secrets._secrets = {}
        try:
            yield
        finally:
            st.secrets._secrets = saved
    except Exception:  # noqa: BLE001 — Streamlit not importable shouldn't break tests
        yield


@pytest.fixture
def two_users(tmp_path, monkeypatch):
    """Two real user rows in an isolated database.

    Isolation tests are worthless against a shared database: a leak and a clean
    run look identical if the other tenant's rows happen not to exist. This
    guarantees both tenants exist and are distinguishable.
    """
    import importlib

    db_path = tmp_path / "isolation.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    from src.tradelens import config as tl_config

    importlib.reload(tl_config)
    from src.tradelens.db import session as db_session

    importlib.reload(db_session)
    from src.tradelens.db import models as db_models

    importlib.reload(db_models)
    db_models.Base.metadata.create_all(db_session.engine)

    from src.tradelens.services import users

    importlib.reload(users)
    a = users.create_user("trader_a", "correct-horse-battery-1")
    b = users.create_user("trader_b", "correct-horse-battery-2")
    yield a.id, b.id
