"""
Tests for the login gate's pure credential logic (Session A, Section 1).

The Streamlit UI (require_auth / _render_login) is exercised by the page boot
tests; here we lock down verify_credentials() and the secrets/env precedence,
which are the security-critical, Streamlit-free parts.
"""

import importlib
import re
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
    monkeypatch.delenv("ENABLE_LEGACY_STREAMLIT_AUTH", raising=False)
    yield


def test_legacy_login_is_unavailable_when_unset():
    """CONTRACT CHANGE, deliberate. This test previously asserted the opposite —
    that unset secrets yielded a committed ``demo`` / ``tradelens2025`` pair
    which authenticated. That was the vulnerability, written down as a
    contract, so it is inverted rather than deleted: unset now means the
    legacy path does not exist. Full coverage in test_auth_fail_closed.py."""
    importlib.reload(auth)
    assert auth.expected_credentials() == ("", "")
    assert auth.legacy_login_configured() is False
    assert auth.verify_credentials("demo", "tradelens2025") is False


def test_wrong_credentials_rejected(monkeypatch):
    """Configured first, on purpose. With nothing configured every one of
    these would be False because the legacy path is closed, and the test would
    pass without ever exercising a credential comparison."""
    monkeypatch.setenv("TRADELENS_USERNAME", "ayoub")
    monkeypatch.setenv("TRADELENS_PASSWORD", "s3cret!")
    assert auth.verify_credentials("ayoub", "wrong") is False
    assert auth.verify_credentials("nobody", "s3cret!") is False
    assert auth.verify_credentials("", "") is False


def test_none_credentials_rejected(monkeypatch):
    monkeypatch.setenv("TRADELENS_USERNAME", "ayoub")
    monkeypatch.setenv("TRADELENS_PASSWORD", "s3cret!")
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


def test_bare_visit_hides_legacy_login_by_default():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_string(_GATE_SCRIPT).run()
    assert not at.exception
    assert "SECRET_DASHBOARD_BODY" not in _markdowns(at)
    assert not at.text_input
    links = at.get("link_button")
    assert [(link.label, link.url) for link in links] == [
        ("Sign in on TradeLens AI", "https://www.tradelensai.io/login")
    ]


def test_opt_in_flag_restores_legacy_login(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("ENABLE_LEGACY_STREAMLIT_AUTH", "true")
    at = AppTest.from_string(_GATE_SCRIPT).run()
    assert not at.exception
    assert "SECRET_DASHBOARD_BODY" not in _markdowns(at)
    assert len(at.text_input) >= 2  # username + password fields


def test_require_auth_passes_when_legacy_authenticated(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("ENABLE_LEGACY_STREAMLIT_AUTH", "true")
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


def test_full_reload_survives_auth_gate_apptest(tmp_path, monkeypatch):
    """End-to-end: a fresh Streamlit session (reload) with a valid URL token
    passes require_auth and reaches page content — no login page, no st.stop."""
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from src.tradelens.ui.components import auth

    monkeypatch.setenv("ENABLE_LEGACY_STREAMLIT_AUTH", "true")

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


def test_sign_out_cleanup_removes_all_partner_session_state():
    """Conversation copy promises that signing out ends the session."""
    state = {
        "authenticated": True,
        "current_user": "ayoub",
        "current_user_id": 7,
        "partner_open": True,
        "partner_history_7": [{"role": "user", "content": "private"}],
        "partner_error_7": "failure",
        "partner_in_drawer": "draft",
        "_partner_pending_drawer": "suggestion",
        "secondary_partner_drawer_chip_0": True,
        "unrelated_preference": "keep",
    }

    auth._clear_session_state_for_sign_out(state)

    assert state == {"unrelated_preference": "keep"}


# ---------------------------------------------------------------------------
# Round 4 — a queued question must not survive its author's session
# ---------------------------------------------------------------------------


def test_sign_out_removes_the_partner_queue_and_run_counter():
    """`_partner_queue` and `_partner_run` are not matched by the
    `_partner_pending_` prefix, so they survived sign-out — carrying the
    previous trader's unsent question in plain text."""
    from src.tradelens.ui.components.partner_turn import (
        QUEUE_KEY,
        RUN_KEY,
        queue_question,
    )

    state = {"authenticated": True, "current_user_id": 7, "keep": "me"}
    queue_question(state, surface="page", text="alice private question", run_id=3)
    state[RUN_KEY] = 3

    auth._clear_session_state_for_sign_out(state)

    assert QUEUE_KEY not in state
    assert RUN_KEY not in state
    # The text itself, not just the key: a queue nested inside another
    # surviving value would still be a leak.
    assert "alice private question" not in repr(state)
    assert state == {"keep": "me"}


def test_one_traders_queued_question_cannot_be_claimed_by_the_next():
    """The reproduction, end to end and in order.

    Alice queues a question and signs out without it being sent. Bob signs in
    to the same browser session, and the Partner advances a run. Bob's run
    must not be able to claim Alice's question, and it must not be anywhere on
    Bob's screen.
    """
    from src.tradelens.ui.components.partner_turn import (
        QUEUE_KEY,
        RUN_KEY,
        begin_partner_run,
        claim_question,
        current_run,
        history_key,
        queue_question,
    )

    private = "alice private question"
    state = {"authenticated": True, "current_user": "alice", "current_user_id": 7}

    # Alice's session: a run is stamped, a question is queued, nothing sends.
    begin_partner_run(state)
    queue_question(state, surface="page", text=private, run_id=current_run(state))
    state[history_key(7)] = [{"role": "user", "content": private}]

    # Alice signs out.
    auth._clear_session_state_for_sign_out(state)
    assert QUEUE_KEY not in state, "Alice's queue outlived her session"
    assert RUN_KEY not in state, "the run counter outlived her session"
    assert private not in repr(state)

    # Bob signs in to the same browser session.
    state.update({"authenticated": True, "current_user": "bob", "current_user_id": 8})

    # Bob's first Partner run.
    run_id = begin_partner_run(state)
    assert claim_question(state, surface="page", run_id=run_id) is None
    assert claim_question(state, surface="drawer", run_id=run_id) is None

    # …and a second, in case adjacency were to line up by coincidence.
    run_id = begin_partner_run(state)
    assert claim_question(state, surface="page", run_id=run_id) is None
    assert private not in repr(state)
    assert state.get(history_key(8)) is None


def test_every_partner_session_key_is_covered_by_the_cleanup():
    """The structural guard, so the next key cannot be forgotten the way
    `_partner_queue` was.

    Each name the Partner writes into session state is checked against the
    prefixes the cleanup actually sweeps, rather than against a list somebody
    has to remember to update.
    """
    import inspect

    from src.tradelens.ui.components import partner_turn as pt

    source = inspect.getsource(auth._clear_session_state_for_sign_out)
    prefixes = tuple(
        re.findall(r'"((?:_)?(?:partner|secondary_partner)[a-z_]*)"', source)
    )
    assert prefixes, "no partner prefixes found in the cleanup"

    written = [
        pt.QUEUE_KEY,
        pt.RUN_KEY,
        pt.HISTORY_PREFIX + "7",
        pt.ERROR_PREFIX + "7",
        "partner_open",
        "partner_in_drawer",
        "partner_in_page",
        "secondary_partner_drawer_chip_0",
    ]
    uncovered = [k for k in written if not k.startswith(prefixes)]
    assert not uncovered, f"sign-out does not clear: {uncovered}"


def test_every_way_out_of_a_session_runs_the_same_cleanup():
    """There is one cleanup, and both exits reach it.

    Deleting an account ends the session too, and a second cleanup path would
    be a second place for a key to be forgotten — which is how this defect
    happened in the first place.
    """
    import ast
    import inspect
    from pathlib import Path

    # `sign_out` is the only caller of the cleanup, and it is what the
    # account-deletion flow uses.
    assert "_clear_session_state_for_sign_out" in inspect.getsource(auth.sign_out)

    settings = (
        Path(__file__).resolve().parents[1] / "src/tradelens/ui/pages/9_Settings.py"
    ).read_text(encoding="utf-8")
    assert "sign_out()" in settings

    # …and nothing else in the UI clears session state its own way.
    ui = Path(__file__).resolve().parents[1] / "src/tradelens/ui"
    for path in ui.rglob("*.py"):
        if "_archive" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert "session_state.clear()" not in text, path.name
        if path.name == "auth.py":
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.FunctionDef)
                and "clear_session" in node.name
                and node.name != "_clear_session_state_for_sign_out"
            ):
                raise AssertionError(f"a second cleanup in {path.name}: {node.name}")
