"""
Tests for the login gate's pure credential logic (Session A, Section 1).

The Streamlit UI (require_auth / _render_login) is exercised by the page boot
tests; here we lock down verify_credentials() and the secrets/env precedence,
which are the security-critical, Streamlit-free parts.
"""

import importlib
from pathlib import Path

import pytest

import src.tradelens.ui.components.auth as auth

ROOT = Path(__file__).resolve().parents[1]

_GATE_SCRIPT = f"""
import sys
sys.path.insert(0, r"{ROOT}")
import streamlit as st
from src.tradelens.ui.components.auth import require_auth
require_auth()
st.markdown("SECRET_DASHBOARD_BODY")
"""


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("TRADELENS_USERNAME", raising=False)
    monkeypatch.delenv("TRADELENS_PASSWORD", raising=False)
    yield


def test_default_credentials_used_when_unset():
    importlib.reload(auth)
    assert auth.expected_credentials() == ("demo", "tradelens2025")
    assert auth.verify_credentials("demo", "tradelens2025") is True


def test_wrong_credentials_rejected():
    assert auth.verify_credentials("demo", "wrong") is False
    assert auth.verify_credentials("nobody", "tradelens2025") is False
    assert auth.verify_credentials("", "") is False


def test_none_credentials_rejected():
    assert auth.verify_credentials(None, None) is False


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("TRADELENS_USERNAME", "ayoub")
    monkeypatch.setenv("TRADELENS_PASSWORD", "s3cret!")
    assert auth.expected_credentials() == ("ayoub", "s3cret!")
    assert auth.verify_credentials("ayoub", "s3cret!") is True
    # The old demo default must no longer be accepted once secrets are set.
    assert auth.verify_credentials("demo", "tradelens2025") is False


def _markdowns(at):
    return " ".join(str(getattr(m, "value", "")) for m in at.markdown)


def test_require_auth_blocks_when_unauthenticated():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_string(_GATE_SCRIPT).run()
    assert not at.exception
    # Login form is shown; the gated body must NOT render.
    assert "SECRET_DASHBOARD_BODY" not in _markdowns(at)
    assert len(at.text_input) >= 2  # username + password fields


def test_require_auth_passes_when_authenticated():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_string(_GATE_SCRIPT)
    at.session_state["authenticated"] = True
    at.run()
    assert not at.exception
    assert "SECRET_DASHBOARD_BODY" in _markdowns(at)
