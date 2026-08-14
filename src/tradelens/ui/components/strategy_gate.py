"""First-run Strategy Profile routing for site-authenticated users.

Where a user lands after authenticating is decided by one database field:

    strategy_profile_completed = false  -> first-run Strategy Profile
    strategy_profile_completed = true   -> the normal dashboard

Two properties are load-bearing.

**The value is read from the account, never from the URL.** A user arrives with
a credential and nothing else; letting the URL assert onboarding state would let
anyone skip the first-run step by editing a query parameter.

**Authenticating does not complete the profile.** The flag becomes true only
when the Strategy Profile flow actually saves one — or when the user explicitly
says they do not have a strategy yet. A brand-new site-auth user is *expected*
to arrive with it false; that false is the entire routing signal, which is also
why handoff eligibility deliberately does not require it.
"""

from __future__ import annotations


def needs_strategy_profile(user_id) -> bool:
    """Whether this account should be routed to the first-run profile.

    Reads the current value from the database on each call. A legacy session
    with no concrete user id is never routed here — those accounts own no
    Strategy rows, and ``strategy._require_concrete_user_id`` raises on a null
    id.
    """
    if user_id is None:
        return False

    from src.tradelens.services.users import get_onboarding_state

    return not get_onboarding_state(user_id)["strategy_profile_completed"]


def route_after_authentication(user_id) -> str:
    """``"strategy_profile"`` or ``"dashboard"``. One place, so callers agree."""
    return "strategy_profile" if needs_strategy_profile(user_id) else "dashboard"


# The existing Strategy Profile page. There is one Strategy Profile in this app
# and this is it — the first-run step reuses the real page rather than a second
# implementation that could drift from it.
STRATEGY_PAGE = "pages/5_Strategy.py"

FIRST_RUN_KEY = "_strategy_first_run"


def enforce_first_run(st, user_id) -> bool:
    """Send a site-authenticated first-timer to the Strategy Profile page.

    Returns True when it redirected.

    **Deliberately scoped to the site path.** A legacy username/password session
    is left exactly as it was: those accounts were backfilled from whether a
    Strategy row already existed, so an old account that never wrote one would
    otherwise start being bounced off its own dashboard by a rollout it did not
    opt into. Legacy behaviour must not change while both paths are live.

    ``st.switch_page`` needs the page registry, which a registry-less boot
    (AppTest) does not have. A failure there must not take down the dashboard,
    so it degrades to rendering normally — the flag is still false and the next
    real navigation routes correctly.
    """
    from src.tradelens.ui.components import site_auth

    if not site_auth.is_site_authenticated(st):
        return False
    if not needs_strategy_profile(user_id):
        return False

    st.session_state[FIRST_RUN_KEY] = True
    try:
        st.switch_page(STRATEGY_PAGE)
    except Exception:  # noqa: BLE001 — never break the dashboard over routing
        return False
    return True


def is_first_run(st) -> bool:
    """Whether the Strategy Profile page is being shown as the first-run step."""
    return bool(st.session_state.get(FIRST_RUN_KEY))
