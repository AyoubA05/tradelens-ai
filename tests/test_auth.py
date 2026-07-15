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


# ---------------------------------------------------------------------------
# Item 1 — reload-persistent sessions. Root cause of "dashboard logs me out":
# auth lived only in st.session_state, which Streamlit wipes on a full browser
# reload. A signed, expiring URL token now restores the session in require_auth.
# ---------------------------------------------------------------------------


def test_issue_and_verify_token_roundtrip():
    from src.tradelens.ui.components import auth

    token = auth._issue_token("ayoub", 7)
    assert auth._verify_token(token) == ("ayoub", 7)


def test_verify_token_keeps_legacy_none_user_id():
    from src.tradelens.ui.components import auth

    assert auth._verify_token(auth._issue_token("demo", None)) == ("demo", None)


def test_verify_token_rejects_tampering_and_garbage():
    from src.tradelens.ui.components import auth

    token = auth._issue_token("ayoub", 7)
    assert auth._verify_token(token[:-2] + "zz") is None
    assert auth._verify_token("not-a-token") is None
    assert auth._verify_token("") is None
    assert auth._verify_token(None) is None


def test_verify_token_rejects_expired():
    import time

    from src.tradelens.ui.components import auth

    old = auth._issue_token("ayoub", 7, now=time.time() - 8 * 24 * 3600)
    assert auth._verify_token(old) is None


def test_reload_restores_session_from_url_token():
    """Simulates a full page reload: empty session_state, token still in URL."""
    from types import SimpleNamespace

    from src.tradelens.ui.components import auth

    fake_st = SimpleNamespace(
        session_state={},
        query_params={"auth": auth._issue_token("ayoub", 3)},
    )
    auth._try_restore(fake_st)
    assert fake_st.session_state["authenticated"] is True
    assert fake_st.session_state["current_user"] == "ayoub"
    assert fake_st.session_state["current_user_id"] == 3


def test_restore_ignores_forged_token():
    from types import SimpleNamespace

    from src.tradelens.ui.components import auth

    fake_st = SimpleNamespace(session_state={}, query_params={"auth": "forged.abc"})
    auth._try_restore(fake_st)
    assert "authenticated" not in fake_st.session_state


def test_full_reload_survives_auth_gate_apptest(tmp_path):
    """End-to-end: a fresh Streamlit session (reload) with a valid URL token
    passes require_auth and reaches page content — no login page, no st.stop."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from src.tradelens.ui.components import auth

    root = Path(__file__).resolve().parents[1]
    script = (
        "import sys\n"
        f'sys.path.insert(0, r"{root}")\n'
        "import streamlit as st\n"
        "from src.tradelens.ui.components.auth import require_auth\n"
        "require_auth()\n"
        'st.write("DASHBOARD_OK")\n'
    )
    at = AppTest.from_string(script)
    at.query_params["auth"] = auth._issue_token("demo", None)
    at.run()
    assert not at.exception
    assert at.session_state["authenticated"] is True
    assert any("DASHBOARD_OK" in str(el.value) for el in at.markdown) or any(
        "DASHBOARD_OK" in str(getattr(el, "value", "")) for el in at.get("text")
    )


def test_persist_token_rotates_before_expiry():
    """Sliding rotation: a token in its last half-TTL is replaced, so a leaked
    URL dies within 24h while an active trader never expires mid-session."""
    import time
    from types import SimpleNamespace

    from src.tradelens.ui.components import auth

    aging = auth._issue_token("ayoub", 3, now=time.time() - (auth._TOKEN_TTL_S * 0.6))
    fake_st = SimpleNamespace(
        session_state={
            "authenticated": True,
            "current_user": "ayoub",
            "current_user_id": 3,
            "_auth_token": aging,
        },
        query_params={"auth": aging},
    )
    auth._persist_token(fake_st)
    fresh = fake_st.session_state["_auth_token"]
    assert fresh != aging  # rotated
    assert auth._verify_token(fresh) == ("ayoub", 3)
    assert fake_st.query_params["auth"] == fresh  # URL updated too
