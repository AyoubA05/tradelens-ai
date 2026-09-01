"""`services/drafts.py`: owner-scoped read/write of the one live draft.

Mirrors the isolation discipline of `test_api_trades.py`: two real users in
one database, and every assertion about "only mine" is checked as an
observable (a row, a return value) rather than trusted from the code path
that is supposed to enforce it.
"""

from __future__ import annotations

import pytest

from src.tradelens.services import drafts


def test_owner_reads_their_own_draft(two_users):
    user_a, _ = two_users
    drafts.save_draft(user_a, {"asset": "NQ", "notes": "scalp"})
    assert drafts.get_draft(user_a) == {"asset": "NQ", "notes": "scalp"}


def test_a_second_owner_s_draft_is_invisible(two_users):
    user_a, user_b = two_users
    drafts.save_draft(user_a, {"asset": "NQ"})
    assert drafts.get_draft(user_b) is None


def test_owner_with_no_draft_gets_none(two_users):
    user_a, _ = two_users
    assert drafts.get_draft(user_a) is None


def test_saving_twice_supersedes_rather_than_accumulates(two_users):
    from src.tradelens.db.models import TradeDraft
    from src.tradelens.db.session import SessionLocal

    user_a, _ = two_users
    drafts.save_draft(user_a, {"asset": "NQ"})
    drafts.save_draft(user_a, {"asset": "MNQ", "notes": "updated"})

    assert drafts.get_draft(user_a) == {"asset": "MNQ", "notes": "updated"}

    db = SessionLocal()
    try:
        rows = db.query(TradeDraft).filter(TradeDraft.user_id == user_a).all()
    finally:
        db.close()
    assert len(rows) == 1


def test_delete_draft_removes_it(two_users):
    user_a, _ = two_users
    drafts.save_draft(user_a, {"asset": "NQ"})
    drafts.delete_draft(user_a)
    assert drafts.get_draft(user_a) is None


def test_delete_draft_is_a_no_op_when_none_exists(two_users):
    user_a, _ = two_users
    drafts.delete_draft(user_a)  # must not raise
    assert drafts.get_draft(user_a) is None


@pytest.mark.parametrize("bad", [None, 0, -1, True, "1"])
def test_get_draft_requires_a_valid_owner(bad):
    with pytest.raises(ValueError):
        drafts.get_draft(bad)


@pytest.mark.parametrize("bad", [None, 0, -1, True, "1"])
def test_save_draft_requires_a_valid_owner(bad):
    with pytest.raises(ValueError):
        drafts.save_draft(bad, {"asset": "NQ"})
