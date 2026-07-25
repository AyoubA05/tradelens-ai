"""Activation milestones derived from records the product already keeps.

No behavioural event table: a beta that tracks its users more closely than
it reviews their trades has its priorities backwards. Every milestone here
is read from a Strategy, Trade, or WeeklyReview row the user created on
purpose.
"""

from types import SimpleNamespace

from src.tradelens.services.activation import ActivationStatus, activation_status


def _trade(day: str, complete: bool = True):
    return SimpleNamespace(
        trade_date=day,
        result="Win" if complete else None,
        pnl=100.0 if complete else None,
        setup_type="FVG" if complete else None,
        followed_rules=1 if complete else None,
    )


def test_new_user_is_directed_to_strategy_profile():
    status = activation_status(strategy=None, trades=[], weekly_review=None)
    assert status.next_key == "strategy"
    assert status.completed == 0
    assert status.is_activated is False


def test_strategy_owner_is_directed_to_first_complete_trade():
    status = activation_status(
        strategy={"name": "My Process"}, trades=[], weekly_review=None
    )
    assert status.next_key == "first_trade"
    assert status.completed == 1


def test_five_complete_trades_unlock_weekly_review_step():
    trades = [_trade(f"2026-07-{day:02d}") for day in range(1, 6)]
    status = activation_status(
        strategy={"name": "My Process"}, trades=trades, weekly_review=None
    )
    assert status.next_key == "weekly_review"
    assert status.completed == 2


def test_reviewed_user_is_activated():
    trades = [_trade(f"2026-07-{day:02d}") for day in range(1, 6)]
    status = activation_status(
        strategy={"name": "My Process"},
        trades=trades,
        weekly_review={"week_start": "2026-06-29"},
    )
    assert status.next_key is None
    assert status.is_activated is True
    assert status.completed == status.total


def test_incomplete_trades_do_not_count_toward_the_first_trade_milestone():
    """A row with no result or setup isn't a journalled trade yet."""
    status = activation_status(
        strategy={"name": "My Process"},
        trades=[_trade("2026-07-01", complete=False)],
        weekly_review=None,
    )
    assert status.next_key == "first_trade"


def test_a_review_without_five_trades_does_not_activate():
    """Reviewing two trades is not the habit the milestone is measuring."""
    status = activation_status(
        strategy={"name": "My Process"},
        trades=[_trade("2026-07-01"), _trade("2026-07-02")],
        weekly_review={"week_start": "2026-06-29"},
    )
    assert status.next_key == "weekly_review"
    assert status.is_activated is False


def test_a_nameless_strategy_does_not_count():
    status = activation_status(strategy={"name": ""}, trades=[], weekly_review=None)
    assert status.next_key == "strategy"


def test_status_is_immutable():
    status = activation_status(strategy=None, trades=[], weekly_review=None)
    assert isinstance(status, ActivationStatus)
    try:
        status.completed = 3  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("ActivationStatus should be frozen")


def test_remaining_trades_tells_the_user_how_far_they_are():
    status = activation_status(
        strategy={"name": "My Process"},
        trades=[_trade("2026-07-01"), _trade("2026-07-02")],
        weekly_review=None,
    )
    assert status.trades_until_review == 3


def test_generators_are_accepted_for_trades():
    """The caller may pass a lazy query result, not just a list."""
    trades = (_trade(f"2026-07-{d:02d}") for d in range(1, 6))
    status = activation_status(
        strategy={"name": "My Process"}, trades=trades, weekly_review=None
    )
    assert status.next_key == "weekly_review"


# ---------------------------------------------------------------------------
# Every record feeding activation must be user-scoped
# ---------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

_UI = Path(__file__).resolve().parents[1] / "src" / "tradelens" / "ui"


def test_dashboard_scopes_every_activation_input_to_the_current_user():
    """An activation card built from another user's rows would be a leak."""
    src = (_UI / "app.py").read_text(encoding="utf-8")
    block = src[
        src.index("_activation = activation_status(") : src.index("if not _activation")
    ]
    assert "get_trades(user_id=uid)" in block
    assert "uid)" in block  # get_weekly_review(..., uid)
    assert "strategy=_strategy" in block
    # _strategy itself is loaded scoped.
    assert "get_active_strategy(uid) if uid is not None else None" in src


def test_dashboard_card_is_hidden_once_activated():
    src = (_UI / "app.py").read_text(encoding="utf-8")
    assert "if not _activation.is_activated and _activation.next_key:" in src


def test_insights_does_not_auto_generate_below_the_threshold():
    src = (_UI / "pages" / "6_Insights.py").read_text(encoding="utf-8")
    assert "_complete_trades < TRADES_FOR_REVIEW" in src
