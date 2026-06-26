"""
Password gate for TradeLens AI (Session A).

Single-user access control. Credentials come from Streamlit secrets / environment
(TRADELENS_USERNAME, TRADELENS_PASSWORD) — never hardcoded inline. A clearly
labeled demo fallback (demo / tradelens2025) keeps the public deploy usable when
no secrets are set; override it by setting the secrets.

Public surface:
    require_auth()          gate placed at the top of every page (after inject_css)
    render_logout_button()  sidebar logout control
    is_authenticated()      bool read of the session flag
    verify_credentials()    pure check, unit-tested

Credential reading is env-first so it is testable without Streamlit; st.secrets is
consulted as a fallback the same way config.py bridges ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import hmac
import os

# Labeled fallback for a demo-only deployment. Real deployments set the secrets
# below and these are never used. This is NOT a hardcoded production credential —
# it is overridden by TRADELENS_USERNAME / TRADELENS_PASSWORD whenever they exist.
_DEFAULT_USERNAME = "demo"
_DEFAULT_PASSWORD = "tradelens2025"

_AUTH_KEY = "authenticated"
_USER_KEY = "current_user"
_UID_KEY = "current_user_id"
_ERROR_KEY = "_login_error"
_MODE_KEY = "_auth_mode"  # "login" | "signup"
_SIGNUP_ERR = "_signup_error"
_SIGNUP_OK = "_signup_ok"


def _read_secret(name: str, default: str) -> str:
    """Read a secret: environment first, then st.secrets, then the default.

    Wrapped defensively — st.secrets raises if no secrets file exists, which is
    normal in tests, so any failure simply falls through to the default.
    """
    val = os.getenv(name)
    if val:
        return str(val)
    try:
        import streamlit as st

        secret = st.secrets.get(name, None)
        if secret:
            return str(secret)
    except Exception:  # noqa: BLE001 — missing secrets file is expected
        pass
    return default


def expected_credentials() -> tuple[str, str]:
    """The (username, password) the app will accept this run."""
    return (
        _read_secret("TRADELENS_USERNAME", _DEFAULT_USERNAME),
        _read_secret("TRADELENS_PASSWORD", _DEFAULT_PASSWORD),
    )


def verify_credentials(username: str | None, password: str | None) -> bool:
    """Constant-time check of submitted credentials against the configured pair."""
    exp_user, exp_pass = expected_credentials()
    user_ok = hmac.compare_digest(str(username or ""), exp_user)
    pass_ok = hmac.compare_digest(str(password or ""), exp_pass)
    return user_ok and pass_ok


# ---------------------------------------------------------------------------
# Multi-user (Session B): DB users with a secrets fallback + invite-code signup
# ---------------------------------------------------------------------------


def invite_code() -> str:
    """The configured signup invite code, or "" when signup is disabled."""
    return _read_secret("TRADELENS_INVITE_CODE", "")


def signup_enabled() -> bool:
    """Signup is offered only when an invite code is configured."""
    return bool(invite_code())


def authenticate_login(username, password):
    """Resolve a login attempt to ``(ok, username, user_id)``.

    DB users take precedence: once the users table has rows, only bcrypt DB users
    can sign in. While it is empty, fall back to the secrets credentials (whose
    user_id is None — legacy single-user trades).
    """
    from src.tradelens.services import users

    try:
        has_db_users = users.users_exist()
    except Exception:  # noqa: BLE001 — a DB hiccup must not lock everyone out
        has_db_users = False

    if has_db_users:
        user = users.authenticate(str(username or ""), str(password or ""))
        if user is not None:
            return True, user.username, user.id
        return False, None, None

    if verify_credentials(username, password):
        return True, str(username), None
    return False, None, None


def validate_signup(username, password, confirm, invite) -> str | None:
    """Return an error message for an invalid signup, or None when valid."""
    from src.tradelens.services import users

    if not users.is_valid_username(str(username or "")):
        return "Username must be 3–20 characters: letters, numbers, underscore."
    if users.username_taken(str(username)):
        return "Username already taken."
    if len(str(password or "")) < users.MIN_PASSWORD_LEN:
        return f"Password must be at least {users.MIN_PASSWORD_LEN} characters."
    if password != confirm:
        return "Passwords do not match."
    expected = invite_code()
    if not expected or not hmac.compare_digest(str(invite or ""), expected):
        return "Invalid invite code."
    return None


def process_signup(username, password, confirm, invite) -> str | None:
    """Validate + create a user. Returns an error message, or None on success."""
    from src.tradelens.services import users

    error = validate_signup(username, password, confirm, invite)
    if error:
        return error
    users.create_user(str(username), str(password))
    return None


# ---------------------------------------------------------------------------
# Streamlit-facing helpers (imported lazily so the module stays import-light)
# ---------------------------------------------------------------------------


def is_authenticated() -> bool:
    import streamlit as st

    return bool(st.session_state.get(_AUTH_KEY, False))


def _render_login_form(st) -> None:
    with st.form("tl_login", clear_on_submit=False):
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Sign In", use_container_width=True)

    if submitted:
        ok, uname, uid = authenticate_login(username, password)
        if ok:
            st.session_state[_AUTH_KEY] = True
            st.session_state[_USER_KEY] = uname
            st.session_state[_UID_KEY] = uid
            st.session_state.pop(_ERROR_KEY, None)
            st.rerun()
        else:
            st.session_state[_ERROR_KEY] = True

    if st.session_state.get(_ERROR_KEY):
        st.error("Incorrect username or password.")

    if signup_enabled():
        if st.button("Create Account", key="show_signup", use_container_width=True):
            st.session_state[_MODE_KEY] = "signup"
            st.session_state.pop(_ERROR_KEY, None)
            st.rerun()


def _render_signup_form(st) -> None:
    st.caption("Create your account — an invite code is required.")
    show = st.checkbox("Show password", key="signup_show")
    ptype = "default" if show else "password"
    with st.form("tl_signup", clear_on_submit=False):
        username = st.text_input("Username", key="signup_username")
        password = st.text_input("Password", type=ptype, key="signup_password")
        confirm = st.text_input("Confirm Password", type=ptype, key="signup_confirm")
        invite = st.text_input(
            "Invite Code — required to create an account", key="signup_invite"
        )
        submitted = st.form_submit_button("Create Account", use_container_width=True)

    if submitted:
        error = process_signup(username, password, confirm, invite)
        if error:
            st.session_state[_SIGNUP_ERR] = error
        else:
            st.session_state[_SIGNUP_OK] = True
            st.session_state[_MODE_KEY] = "login"
            st.session_state.pop(_SIGNUP_ERR, None)
            st.rerun()

    if st.session_state.get(_SIGNUP_ERR):
        st.error(st.session_state[_SIGNUP_ERR])

    if st.button("← Back to Sign In", key="back_to_login", use_container_width=True):
        st.session_state[_MODE_KEY] = "login"
        st.session_state.pop(_SIGNUP_ERR, None)
        st.rerun()


def _render_login() -> None:
    """Render the centered login card. Shown in place of any page content."""
    import streamlit as st

    from src.tradelens.ui.components.theme import (
        BORDER,
        SURFACE,
        TEXT_MUTED,
        TEXT_SECONDARY,
    )

    # Hide the sidebar entirely while logged out — no nav, no chrome.
    st.markdown(
        "<style>[data-testid='stSidebar']{display:none}</style>",
        unsafe_allow_html=True,
    )

    left, mid, right = st.columns([1, 1.4, 1])
    with mid:
        st.markdown(
            f"""<div style="background:{SURFACE};border:1px solid {BORDER};
border-radius:16px;padding:32px 28px;margin-top:8vh;text-align:center">
<div style="font-family:'Space Grotesk',sans-serif;font-size:1.9rem;
font-weight:700;letter-spacing:-0.02em">TradeLens AI</div>
<div style="color:{TEXT_MUTED};font-size:0.95rem;margin-top:4px">Post-Trade Journal</div>
<div style="color:{TEXT_SECONDARY};font-size:0.85rem;margin-top:14px">
Sign in to review your trades.</div></div>""",
            unsafe_allow_html=True,
        )

        if st.session_state.pop(_SIGNUP_OK, False):
            st.success("Account created. Sign in below.")

        if st.session_state.get(_MODE_KEY) == "signup":
            _render_signup_form(st)
        else:
            _render_login_form(st)


def require_auth() -> None:
    """Gate: if not signed in, render the login page and halt the script.

    Call once near the top of every page, right after inject_css(). When the user
    is authenticated this is a fast no-op.
    """
    import streamlit as st

    if is_authenticated():
        return
    _render_login()
    st.stop()


def render_logout_button() -> None:
    """Render a logout control (intended for the sidebar)."""
    import streamlit as st

    if st.button("Sign out", key="tl_logout", use_container_width=True):
        st.session_state[_AUTH_KEY] = False
        for key in (_USER_KEY, _UID_KEY, _ERROR_KEY, _MODE_KEY):
            st.session_state.pop(key, None)
        st.rerun()


def current_user() -> str | None:
    """The signed-in username, or None."""
    import streamlit as st

    return st.session_state.get(_USER_KEY)


def current_user_id() -> int | None:
    """The signed-in user's DB id (None for the secrets-fallback legacy user)."""
    import streamlit as st

    return st.session_state.get(_UID_KEY)
