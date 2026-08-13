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
