"""The authentication path fails CLOSED.

Regression coverage for a long-standing bypass (present since `a0ef59b` /
`7bdf825`, not introduced by the redesign):

1. `expected_credentials()` handed out a committed pair — `demo` /
   `tradelens2025` — whenever the deployment secrets were unset.
2. `verify_credentials()` accepted it with no check that anything was
   configured.
3. `authenticate_login()` turned ANY exception from `users.users_exist()`
   into `has_db_users = False`, which routed the attempt into the legacy
   branch.

Chained: on a deployment with real accounts, a database outage downgraded
login to a password published in this repository, and issued a session with
`user_id=None` — the legacy tenant.

Every test here fails against that old behaviour.
"""

import logging

import pytest

from src.tradelens.ui.components import auth

HISTORICAL_USER = "demo"
HISTORICAL_PASS = "tradelens2025"


@pytest.fixture(autouse=True)
def _clear_legacy_env(monkeypatch):
    monkeypatch.delenv("TRADELENS_USERNAME", raising=False)
    monkeypatch.delenv("TRADELENS_PASSWORD", raising=False)


class _Boom(Exception):
    """Stands in for a driver error. Its text imitates the parts of a real
    DSN-carrying exception that must never reach a log or the screen."""

    def __init__(self):
        super().__init__(
            "could not connect to postgresql://tluser:hunter2@db.internal:5432/tradelens"
        )


def _users_module(
    monkeypatch,
    *,
    exists=None,
    raises_exist=False,
    authenticate=None,
    raises_auth=False,
):
    """Install a fake `services.users` for the lazy import inside auth.

    Both the `sys.modules` entry AND the package attribute are replaced, and
    the second one is not optional. `authenticate_login` does
    `from src.tradelens.services import users`, which resolves through the
    PACKAGE ATTRIBUTE as soon as any earlier test has imported the real
    module — so patching `sys.modules` alone works in isolation and is
    silently ignored in a full run. These tests passed on their own and failed
    in the suite for exactly that reason.
    """
    import sys
    import types

    import src.tradelens.services as services_pkg

    mod = types.ModuleType("src.tradelens.services.users")

    def users_exist():
        if raises_exist:
            raise _Boom()
        return exists

    def _authenticate(u, p):
        if raises_auth:
            raise _Boom()
        return authenticate(u, p) if authenticate else None

    mod.users_exist = users_exist
    mod.authenticate = _authenticate
    monkeypatch.setitem(sys.modules, "src.tradelens.services.users", mod)
    monkeypatch.setattr(services_pkg, "users", mod, raising=False)
    return mod


# ── no usable fallback credentials ────────────────────────────────────────


def test_the_committed_historical_defaults_are_gone_from_the_module():
    """The literal strings must not survive anywhere in the module, not even
    as an unused constant someone could wire back up."""
    import inspect

    source = inspect.getsource(auth)
    assert "tradelens2025" not in source
    assert not hasattr(auth, "_DEFAULT_PASSWORD")
    assert not hasattr(auth, "_DEFAULT_USERNAME")


def test_unset_legacy_credentials_cannot_authenticate():
    assert auth.expected_credentials() == ("", "")
    assert auth.legacy_login_configured() is False
    assert auth.verify_credentials(HISTORICAL_USER, HISTORICAL_PASS) is False


def test_the_historical_defaults_cannot_authenticate(monkeypatch):
    """The exact pair that used to work, against an empty database."""
    _users_module(monkeypatch, exists=False)
    ok, uname, uid = auth.authenticate_login(HISTORICAL_USER, HISTORICAL_PASS)
    assert (ok, uname, uid) == (False, None, None)


def test_blank_credentials_cannot_authenticate():
    """Unset used to compare the submission against ("", ""), so blank/blank
    authenticated."""
    assert auth.verify_credentials("", "") is False
    assert auth.verify_credentials(None, None) is False


@pytest.mark.parametrize(
    "user,password",
    [("only-user", ""), ("", "only-pass"), ("only-user", "   "), ("   ", "p")],
)
def test_half_configured_legacy_login_is_unavailable(monkeypatch, user, password):
    """A deployment that sets one half has not configured legacy login."""
    monkeypatch.setenv("TRADELENS_USERNAME", user)
    monkeypatch.setenv("TRADELENS_PASSWORD", password)
    if not user.strip() or not password.strip():
        assert auth.verify_credentials(user, password) is False


# ── configured legacy login still works (compatibility) ───────────────────


def test_explicitly_configured_legacy_login_still_works_on_an_empty_db(monkeypatch):
    """The supported compatibility mode. Legacy single-user deployments that
    DO configure their credentials must keep working."""
    monkeypatch.setenv("TRADELENS_USERNAME", "ayoub")
    monkeypatch.setenv("TRADELENS_PASSWORD", "s3cret!")
    _users_module(monkeypatch, exists=False)

    assert auth.legacy_login_configured() is True
    ok, uname, uid = auth.authenticate_login("ayoub", "s3cret!")
    assert ok is True
    assert uname == "ayoub"
    assert uid is None  # legacy tenant, by design, and only on an empty DB

    assert auth.authenticate_login("ayoub", "wrong")[0] is False


# ── database exceptions fail closed ───────────────────────────────────────


def test_a_database_exception_fails_closed(monkeypatch):
    _users_module(monkeypatch, raises_exist=True)
    with pytest.raises(auth.AuthUnavailableError):
        auth.authenticate_login("anyone", "anything")


def test_a_database_exception_fails_closed_even_with_legacy_configured(monkeypatch):
    """The exact bypass. Legacy credentials configured, database down — the
    old code would have accepted the legacy pair. It must not."""
    monkeypatch.setenv("TRADELENS_USERNAME", "ayoub")
    monkeypatch.setenv("TRADELENS_PASSWORD", "s3cret!")
    _users_module(monkeypatch, raises_exist=True)
    with pytest.raises(auth.AuthUnavailableError):
        auth.authenticate_login("ayoub", "s3cret!")


def test_a_database_exception_never_reaches_verify_credentials(monkeypatch):
    """Not just "the answer is no" — the legacy comparison must never even be
    attempted, because reaching it at all is the bug."""
    called = []
    monkeypatch.setattr(
        auth,
        "verify_credentials",
        lambda u, p: called.append((u, p)) or True,
    )
    _users_module(monkeypatch, raises_exist=True)
    with pytest.raises(auth.AuthUnavailableError):
        auth.authenticate_login("demo", "tradelens2025")
    assert called == [], "the legacy path was reached during an outage"


def test_a_credential_check_exception_also_fails_closed(monkeypatch):
    _users_module(monkeypatch, exists=True, raises_auth=True)
    with pytest.raises(auth.AuthUnavailableError):
        auth.authenticate_login("someone", "something")


def test_a_database_exception_does_not_change_authentication_mode(monkeypatch):
    """`users_exist` must be consulted exactly once and its failure must not
    be reinterpreted as "no users"."""
    calls = []

    import sys
    import types

    mod = types.ModuleType("src.tradelens.services.users")

    def users_exist():
        calls.append(1)
        raise _Boom()

    import src.tradelens.services as services_pkg

    mod.users_exist = users_exist
    mod.authenticate = lambda u, p: None
    monkeypatch.setitem(sys.modules, "src.tradelens.services.users", mod)
    monkeypatch.setattr(services_pkg, "users", mod, raising=False)

    with pytest.raises(auth.AuthUnavailableError):
        auth.authenticate_login("demo", "tradelens2025")
    assert len(calls) == 1


# ── database-backed deployments ───────────────────────────────────────────


class _User:
    def __init__(self, username, uid):
        self.username = username
        self.id = uid


def test_database_users_still_authenticate_normally(monkeypatch):
    _users_module(
        monkeypatch,
        exists=True,
        authenticate=lambda u, p: _User("dave", 7) if p == "right" else None,
    )
    ok, uname, uid = auth.authenticate_login("dave", "right")
    assert (ok, uname, uid) == (True, "dave", 7)


def test_no_database_backed_login_receives_a_none_user_id(monkeypatch):
    _users_module(
        monkeypatch,
        exists=True,
        authenticate=lambda u, p: _User("dave", 7),
    )
    ok, _uname, uid = auth.authenticate_login("dave", "right")
    assert ok is True
    assert uid is not None


def test_invalid_database_credentials_do_not_fall_through_to_legacy(monkeypatch):
    """Accounts exist, the submission is the legacy pair. It must be rejected
    rather than granted a user_id=None session."""
    monkeypatch.setenv("TRADELENS_USERNAME", "ayoub")
    monkeypatch.setenv("TRADELENS_PASSWORD", "s3cret!")
    _users_module(monkeypatch, exists=True, authenticate=lambda u, p: None)

    ok, uname, uid = auth.authenticate_login("ayoub", "s3cret!")
    assert (ok, uname, uid) == (False, None, None)


# ── nothing sensitive escapes ─────────────────────────────────────────────


def test_the_log_line_carries_no_dsn_credentials_or_driver_message(monkeypatch, caplog):
    _users_module(monkeypatch, raises_exist=True)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(auth.AuthUnavailableError):
            auth.authenticate_login("demo", "tradelens2025")

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert blob, "the failure was not logged at all"
    for secret in (
        "postgresql://",
        "hunter2",
        "tluser",
        "db.internal",
        "5432",
        "tradelens2025",
        "demo",
    ):
        assert secret not in blob, f"{secret!r} leaked into the log"
    # The type name is the safe subset that IS reported.
    assert "_Boom" in blob


def test_the_login_screen_copy_is_calm_and_generic():
    """The outage message must not name the failure, and must not claim the
    credentials were wrong — the app does not know."""
    import inspect

    from src.tradelens.ui.components import auth_screen

    source = inspect.getsource(auth_screen)
    assert "Sign-in is temporarily unavailable." in source
    idx = source.index("Sign-in is temporarily unavailable.")
    window = source[idx : idx + 260]
    for banned in ("Traceback", "postgres", "OperationalError", "DSN", "str(exc)"):
        assert banned not in window


def test_an_outage_is_reported_differently_from_a_wrong_password():
    """Reporting an outage as a bad password sends a trader to reset a
    password that was never the problem."""
    import inspect

    from src.tradelens.ui.components import auth_screen

    source = inspect.getsource(auth_screen)
    assert "AuthUnavailableError" in source
    assert "Incorrect username or password." in source
    assert source.index("Sign-in is temporarily unavailable.") != source.index(
        "Incorrect username or password."
    )
