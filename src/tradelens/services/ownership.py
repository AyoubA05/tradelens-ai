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


def lock_owner_first(db, owner: int) -> None:
    """Take the owner's row `FOR KEY SHARE` before locking any of their rows.

    Account deletion locks the owner row `FOR UPDATE`, then the trades. A save
    that locked the trades first and then inserted a row referencing the owner
    — whose foreign-key check needs `KEY SHARE` on that same row — took the
    opposite order, and PostgreSQL broke the cycle by aborting one side: the
    deletion, whenever the save was quick (production gate 1). Every writer
    that locks trades and then inserts an owner-referencing row calls this
    first, so all of them take one order. `KEY SHARE` blocks only a deletion
    or key change of that row, never another save. SQLite ignores it.
    """
    from src.tradelens.db.models import User

    db.query(User.id).filter(User.id == owner).with_for_update(
        read=True, key_share=True
    ).first()
