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
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    from src.tradelens import config as tl_config

    # Patch the FIELD on the existing `settings` singleton rather than
    # reloading the config module. `importlib.reload(tl_config)` would build
    # a brand new `Settings()` instance in tl_config's namespace, but every
    # service that captured `settings` by reference at its own import time
    # (e.g. ai_client.py: `from src.tradelens.config import settings`) would
    # keep pointing at the OLD object — permanently diverged from
    # `tl_config.settings` for the rest of the process, well past this
    # fixture's teardown. That divergence is silent until something reads a
    # field through the stale reference (e.g. a test's
    # `monkeypatch.setattr(ai_client.settings, "anthropic_api_key", ...)`
    # landing on an object `resolve_anthropic_key()` no longer looks at) and
    # then every AI call in every later test sees "API key not configured".
    # Mutating the one object everyone already holds a reference to avoids
    # creating a second one.
    monkeypatch.setattr(tl_config.settings, "database_url", db_url)

    from src.tradelens.db import session as db_session

    importlib.reload(db_session)
    from src.tradelens.db import models as db_models

    # `db.models` and the services are NOT reloaded, and that is load-bearing.
    # Neither holds an engine: `db.models` owns only Base/metadata, which is
    # engine-agnostic, and `users` reaches the database through `SessionLocal`.
    #
    # Reloading `db.models` re-registers its tables against whatever `Base` it
    # re-imports, which raises "Table 'users' is already defined for this
    # MetaData instance" depending on which modules a given test file happened
    # to import first — green in one run order and red in another, which is the
    # worst failure mode a fixture can have.
    #
    # Reloading `db.session` alone is sufficient: reload replaces that module's
    # globals IN PLACE, so the `SessionLocal` function object every service
    # already captured by reference reads the new `_sessionmaker` through its
    # own __globals__.
    db_models.Base.metadata.create_all(db_session.engine)

    from src.tradelens.services import users
    a = users.create_user("trader_a", "correct-horse-battery-1")
    b = users.create_user("trader_b", "correct-horse-battery-2")
    try:
        yield a.id, b.id
    finally:
        # Undo the env/attribute patches FIRST. pytest tears fixtures down in
        # reverse setup order, and `monkeypatch` was set up before this
        # fixture body ran, so its own finalizer would otherwise fire AFTER
        # this code — meaning `tl_config.settings.database_url` would still
        # read the tmp path here and the reload below would just rebuild the
        # same throwaway engine again.
        monkeypatch.undo()
        importlib.reload(db_session)


@pytest.fixture
def website_session(two_users):
    """A live website session for the first test user: ``(user_id, raw_token)``.

    Inserted directly rather than through a login flow: this is the credential
    the API's Lock 2 resolves, and the point is to exercise that resolution, not
    the website's sign-in form.
    """
    import datetime as dt
    import hashlib
    import secrets

    from sqlalchemy import text as sa_text

    from src.tradelens.db.session import SessionLocal
    from src.tradelens.services import auth_sessions

    user_id = two_users[0]
    token = secrets.token_urlsafe(32)
    now = dt.datetime.now(dt.timezone.utc)
    digest = hashlib.sha256(
        (auth_sessions.WEBSITE_DOMAIN + token).encode("utf-8")
    ).hexdigest()
    db = SessionLocal()
    try:
        db.execute(
            sa_text(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, "
                "expires_at, last_seen_at, surface) VALUES (:h,:u,:c,:e,:l,:s)"
            ),
            {
                "h": digest,
                "u": user_id,
                "c": now,
                "e": now + dt.timedelta(hours=12),
                "l": now,
                "s": auth_sessions.SURFACE_WEBSITE,
            },
        )
        db.commit()
    finally:
        db.close()
    return user_id, token
