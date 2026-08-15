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
