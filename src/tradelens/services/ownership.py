"""The single definition of a valid request owner.

Every user-facing service validates its `user_id` through this function. It
exists because the alternative — each service inventing its own check — is how
one of them ends up accepting None and reading the legacy tenant, or accepting
True and reading user 1. There is one rule and one place to change it.

No Streamlit imports here.
"""

from __future__ import annotations


def require_user_id(value: object) -> int:
    """Return `value` as a concrete owner id, or raise.

    `bool` is rejected explicitly: it is a subclass of `int`, so `True` would
    otherwise pass both the type check and the positivity check and silently
    scope a query to user 1.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("user_id must be a positive integer")
    return value
