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


def test_authenticate_login_does_not_crash_when_db_auth_raises(monkeypatch):
    """A DB/bcrypt error in the accounts-exist branch must degrade, not crash."""
    from src.tradelens.services import users

    monkeypatch.setattr(users, "users_exist", lambda: True)

    def _boom(*_a, **_k):
        raise RuntimeError("simulated DB / bcrypt failure")

    monkeypatch.setattr(users, "authenticate", _boom)

    # Must return a clean rejection tuple — never propagate the exception.
    assert auth.authenticate_login("ayoub", "whatever") == (False, None, None)


def test_login_form_renders_rejection_instead_of_crashing(monkeypatch):
    """Driving the login form with a raising auth path shows an error, not a crash."""
    from streamlit.testing.v1 import AppTest

    script = """
import sys
sys.path.insert(0, %r)
import src.tradelens.ui.components.auth as auth
auth.authenticate_login = lambda u, p: (_ for _ in ()).throw(RuntimeError("boom"))
auth.require_auth()
""" % str(
        __import__("pathlib").Path(__file__).resolve().parents[1]
    )

    at = AppTest.from_string(script, default_timeout=30).run()
    at.text_input(key="login_username").set_value("x")
    at.text_input(key="login_password").set_value("y")
    [b for b in at.button if b.label == "Sign In"][0].click()
    at.run()

    assert not at.exception, f"login click crashed: {list(at.exception)}"
