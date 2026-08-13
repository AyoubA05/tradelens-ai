"""Site-hosted authentication inside Streamlit: the ``ht`` → ``s`` entry path.

Kept separate from ``auth.py`` on purpose. That module owns the legacy
username/password path, which must keep working untouched during rollout, and
mixing the two would make it easy for a bug in one to authenticate through the
other. The precedence between them lives in ``auth.require_auth`` and is the
only place they meet.

Entry precedence:

    1. a valid ``s`` credential   -> durable Streamlit session
    2. otherwise a ``ht``         -> one-time atomic exchange, then ``s``
    3. otherwise                  -> legacy login (auth.py, unchanged)

**An invalid ``s`` must not inherit stale authenticated state.** Streamlit
reruns constantly and ``st.session_state`` survives between runs, so a session
that authenticated a minute ago still has ``authenticated = True`` sitting in
memory after its credential is revoked. Every run therefore re-validates against
the database and clears the runtime flags on failure, rather than trusting what
a previous rerun left behind.

**Beta limitation, stated plainly and not softened.** ``s`` is a bearer
credential carried in the URL, because Streamlit Community Cloud offers no
server-side cookie write outside its own OIDC flow. Anyone holding a copied
Streamlit URL can authenticate as that session until it is revoked or expires.
Replacing the query parameter cleans up the URL Streamlit currently controls; it
does **not** erase entries already written to browser history, and nothing here
should be read as claiming otherwise. This is not equivalent to an HttpOnly
cookie.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

# Canonical parameters, fixed by the approved design (spec §7.4).
HANDOFF_PARAM = "ht"
SESSION_PARAM = "s"

# Runtime keys. Prefixed so the sign-out sweep can find them, and deliberately
# few: session_state is UI scaffolding here, never the authority.
_SITE_AUTH_KEY = "_site_auth_user_id"
_SITE_TOKEN_KEY = "_site_auth_token"
_SITE_ERROR_KEY = "_site_auth_error"
_HT_SEEN_KEY = "_site_auth_ht_attempted"

INVALID_LINK_MESSAGE = (
    "This sign-in link is no longer valid. Return to TradeLens AI and try again."
)


def _site_origin() -> str:
    """Where an invalid link sends the user back to. Server configuration only.

    Never a value from the URL: reflecting a client-supplied destination on an
    error page is an open redirect, and an auth error page is exactly where a
    user is most willing to click through.
    """
    from src.tradelens.settings_source import read_setting

    return read_setting("SITE_ORIGIN", "https://www.tradelensai.io")


def _clear_runtime_auth(state) -> None:
    """Drop cached authentication so a failed check cannot fall through.

    Without this, a revoked credential leaves ``authenticated = True`` in
    session_state from an earlier rerun and the app would keep rendering as
    though nothing happened.
    """
    for key in (_SITE_AUTH_KEY, _SITE_TOKEN_KEY):
        state.pop(key, None)


def _replace_query_params(st, *, session_token: str | None) -> None:
    """Leave exactly one credential in the visible URL, or none.

    Uses Streamlit 1.50's stable ``st.query_params``; the deprecated
    ``experimental_*`` API is not used. ``ht`` is always removed — leaving both
    parameters would keep a spent one-time credential visible for no reason.
    """
    st.query_params.pop(HANDOFF_PARAM, None)
    if session_token is None:
        st.query_params.pop(SESSION_PARAM, None)
    else:
        st.query_params[SESSION_PARAM] = session_token


def try_site_session(st) -> int | None:
    """Resolve an existing ``s`` credential to a user id, or None.

    Validated server-side on every run. ``st.session_state`` caches nothing that
    could substitute for this check.
    """
    from src.tradelens.services.auth_sessions import restore_streamlit_session

    token = st.query_params.get(SESSION_PARAM) or st.session_state.get(_SITE_TOKEN_KEY)
    if not token:
        return None

    user_id = restore_streamlit_session(token)
    if user_id is None:
        # Revoked, expired, idle out, or never real. Clear both the runtime
        # flags and the dead parameter so reruns stop presenting it.
        _clear_runtime_auth(st.session_state)
        _replace_query_params(st, session_token=None)
        return None

    st.session_state[_SITE_AUTH_KEY] = user_id
    st.session_state[_SITE_TOKEN_KEY] = token
    # Re-assert the parameter: Streamlit does not reliably preserve query params
    # across page navigation, and losing it mid-session would sign the user out.
    if st.query_params.get(SESSION_PARAM) != token:
        st.query_params[SESSION_PARAM] = token
    return user_id


def try_handoff_exchange(st) -> int | None:
    """Exchange a ``ht`` for a session, once.

    Returns the user id on success. On failure it records a generic error,
    strips the dead parameter, and marks the attempt so reruns do not keep
    presenting the same spent credential to the database.
    """
    from src.tradelens.services.auth_exchange import (
        exchange_handoff_for_streamlit_session,
    )

    raw_ht = st.query_params.get(HANDOFF_PARAM)
    if not raw_ht:
        return None

    # One attempt per runtime session. A one-time token cannot succeed twice, so
    # retrying on every rerun would only generate database load and log noise.
    if st.session_state.get(_HT_SEEN_KEY):
        _replace_query_params(st, session_token=None)
        return None
    st.session_state[_HT_SEEN_KEY] = True

    session_token = exchange_handoff_for_streamlit_session(raw_ht)

    if session_token is None:
        # Malformed, unknown, expired, consumed, or ineligible — one message for
        # all of them. The raw handoff is not stored anywhere, including here.
        st.session_state[_SITE_ERROR_KEY] = INVALID_LINK_MESSAGE
        _clear_runtime_auth(st.session_state)
        _replace_query_params(st, session_token=None)
        _log.info("site auth: handoff exchange rejected")
        return None

    from src.tradelens.services.auth_sessions import restore_streamlit_session

    user_id = restore_streamlit_session(session_token)
    if user_id is None:  # pragma: no cover - a session we just created
        st.session_state[_SITE_ERROR_KEY] = INVALID_LINK_MESSAGE
        _replace_query_params(st, session_token=None)
        return None

    st.session_state[_SITE_AUTH_KEY] = user_id
    st.session_state[_SITE_TOKEN_KEY] = session_token
    st.session_state.pop(_SITE_ERROR_KEY, None)
    # ht out, s in — one write, so both are never visible together.
    _replace_query_params(st, session_token=session_token)
    _log.info("site auth: handoff exchanged")
    return user_id


def authenticate(st) -> int | None:
    """The site-auth entry point. Returns a user id, or None to fall through.

    Order matters: an established session is checked before a handoff, so a
    refresh on a URL that still carries a spent ``ht`` does not report a failure
    for a session that is perfectly valid.
    """
    user_id = try_site_session(st)
    if user_id is not None:
        return user_id
    return try_handoff_exchange(st)


def site_error(st) -> str | None:
    """The generic failure message, if the last attempt failed."""
    return st.session_state.get(_SITE_ERROR_KEY)


def return_to_site_url() -> str:
    """Server-configured destination for the "back to TradeLens AI" link."""
    return _site_origin().rstrip("/") + "/login"


def sign_out_streamlit_session(st) -> bool:
    """End *this* Streamlit session and nothing else.

    Revokes only the current row, so the user's website session and any other
    Streamlit session stay live. "Sign out everywhere" is a separate, explicit
    action and must not be what an ordinary sign-out quietly does.
    """
    from src.tradelens.services.auth_sessions import revoke_streamlit_session

    token = st.session_state.get(_SITE_TOKEN_KEY) or st.query_params.get(SESSION_PARAM)
    revoked = revoke_streamlit_session(token) if token else False

    _clear_runtime_auth(st.session_state)
    st.session_state.pop(_HT_SEEN_KEY, None)
    _replace_query_params(st, session_token=None)
    _log.info("site auth: streamlit session signed out")
    return revoked


def is_site_authenticated(st) -> bool:
    """Whether this run authenticated through the site path.

    Reads a runtime flag that ``authenticate`` sets only after a successful
    server-side validation in the same run — it is a marker of what already
    happened, not an authority of its own.
    """
    return st.session_state.get(_SITE_AUTH_KEY) is not None
