"""
Regression: the localhost login crash (Bug 1).

On a fresh Streamlit Community Cloud deploy the SQLite DB starts empty, so
`users_exist()` is False and login uses the secrets fallback — that path never
touches the DB-auth branch and "works fine". On localhost the dev DB already has
accounts, so `users_exist()` is True and `authenticate_login` calls
`users.authenticate()`. That call was unguarded, so any DB/bcrypt error there
escaped and crashed the whole login click. These tests lock the guard in place.
"""

from __future__ import annotations

import src.tradelens.ui.components.auth as auth


def test_authenticate_login_reports_a_db_failure_as_unavailable(monkeypatch):
    """A DB/bcrypt error in the accounts-exist branch must degrade, not crash.

    CONTRACT CHANGE, deliberate. This previously asserted a `(False, None,
    None)` rejection tuple. A rejection tuple is indistinguishable from "wrong
    password", and that conflation is what allowed a database outage to be
    reinterpreted as an authentication mode elsewhere in this function. The
    failure is now typed. The original intent — the exception must never reach
    the trader as a crash — is unchanged and is asserted by the AppTest below,
    which drives the real screen and requires no rendered exception.
    """
    import pytest

    from src.tradelens.services import users

    monkeypatch.setattr(users, "users_exist", lambda: True)

    def _boom(*_a, **_k):
        raise RuntimeError("simulated DB / bcrypt failure")

    monkeypatch.setattr(users, "authenticate", _boom)

    with pytest.raises(auth.AuthUnavailableError):
        auth.authenticate_login("ayoub", "whatever")


def test_login_form_renders_rejection_instead_of_crashing(monkeypatch):
    """Driving the login form with a raising auth path shows an error, not a crash.

    SP3: the form now lives in auth_screen (button label "Sign in"); the raising
    auth path is patched via monkeypatch (auto-restored) instead of mutating the
    module inside the script. signup toggle forced off — AppTest in streamlit
    1.50 cannot serialize st.segmented_control state on rerun.
    """
    from streamlit.testing.v1 import AppTest

    def _boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth, "authenticate_login", _boom)
    monkeypatch.setattr(auth, "signup_enabled", lambda: False)
    monkeypatch.setenv("ENABLE_LEGACY_STREAMLIT_AUTH", "true")

    script = """
import sys
sys.path.insert(0, %r)
import src.tradelens.ui.components.auth as auth
auth.require_auth()
""" % str(
        __import__("pathlib").Path(__file__).resolve().parents[1]
    )

    at = AppTest.from_string(script, default_timeout=30).run()
    at.text_input(key="login_username").set_value("x")
    at.text_input(key="login_password").set_value("y")
    [b for b in at.button if b.label == "Sign in"][0].click()
    at.run()

    assert not at.exception, f"login click crashed: {list(at.exception)}"
    rendered = " ".join(m.value for m in at.markdown)
    # The screen now separates "we could not check" from "those are wrong".
    # A raising auth path is the former, and saying "check your details" would
    # send a trader to reset a password that was never the problem.
    assert "Sign-in is temporarily unavailable" in rendered
    assert "Check your details and try again" not in rendered
    # And nothing about the failure itself reaches the page.
    for leak in ("boom", "RuntimeError", "Traceback"):
        assert leak not in rendered, f"{leak!r} leaked to the login screen"
