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
_ERROR_KEY = "_login_error"


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
# Streamlit-facing helpers (imported lazily so the module stays import-light)
# ---------------------------------------------------------------------------


def is_authenticated() -> bool:
    import streamlit as st

    return bool(st.session_state.get(_AUTH_KEY, False))


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

        with st.form("tl_login", clear_on_submit=False):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)

        if submitted:
            if verify_credentials(username, password):
                st.session_state[_AUTH_KEY] = True
                st.session_state.pop(_ERROR_KEY, None)
                st.rerun()
            else:
                st.session_state[_ERROR_KEY] = True

        if st.session_state.get(_ERROR_KEY):
            st.error("Incorrect username or password.")


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
        st.session_state.pop(_ERROR_KEY, None)
        st.rerun()
