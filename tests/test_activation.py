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
    """An activation card built from another user's rows would be a leak.

    The anchor moved when band 5 took over rendering — the decision now lives
    in overview_bands.next_review_action — but the inputs are still assembled
    here, so this still guards the same thing: every one of them is scoped.
    """
    src = (_UI / "app.py").read_text(encoding="utf-8")
    start = src.index("_activation = activation_status(")
    block = src[start : src.index(")", src.index("weekly_review=", start))]
    assert "get_trades(user_id=uid)" in block
    assert "uid)" in block  # get_weekly_review(..., uid)
    assert "strategy=_strategy" in block
    # _strategy itself is loaded scoped.
    assert "get_active_strategy(uid) if uid is not None else None" in src
    # And the whole computation only happens for an authenticated user.
    assert "if uid is not None:" in src[: start + 200]


def test_dashboard_card_is_hidden_once_activated():
    """Tested through the decision function rather than a source string.

    The literal `if not _activation.is_activated` moved out of app.py into
    overview_bands.next_review_action when band 5 absorbed the card, so
    grepping the page for it was checking where the code lives, not what it
    does. This checks the behaviour: an activated account gets no next step.
    """
    import pandas as pd

    from src.tradelens.services.activation import ActivationStatus
    from src.tradelens.ui.components.overview_bands import next_review_action

    activated = ActivationStatus(
        completed=3,
        total=3,
        next_key=None,
        is_activated=True,
        complete_trades=9,
        trades_until_review=0,
    )
    band = next_review_action(pd.DataFrame(), activated)
    assert band is None or band.kind != "next_step"

    unactivated = ActivationStatus(
        completed=1,
        total=3,
        next_key="first_trade",
        is_activated=False,
        complete_trades=0,
        trades_until_review=5,
    )
    assert next_review_action(pd.DataFrame(), unactivated).kind == "next_step"


def test_insights_does_not_auto_generate_below_the_threshold():
    """Below the threshold the page must show what would unlock a recap and
    return, rather than spending an API call on a sample that cannot say
    anything true. (The counter moved inside the Weekly lens; the gate and
    its early return are what matter.)"""
    src = (_UI / "pages" / "6_Insights.py").read_text(encoding="utf-8")
    assert "complete < TRADES_FOR_REVIEW" in src
    gate = src[src.index("complete < TRADES_FOR_REVIEW") :]
    gate = gate[: gate.index("_auto_run_weekly(monday, uid)")]
    assert "render_empty_state(" in gate
    assert "return" in gate, "the gate must stop before the AI call"


def test_the_api_contract_pins_the_same_step_keys_the_service_emits():
    """One spelling of each step, everywhere.

    The Overview card keyed its copy off three invented names; two of them no
    service ever emits, so those states fell through to "the activation path is
    complete" while the card showed "1 of 3 done". The contract now declares a
    closed union, and this pins that union to the keys `activation_status`
    actually produces — including the copy table this module ships for them.
    """
    from typing import get_args

    from src.tradelens.api.schemas.overview import NextReviewAction
    from src.tradelens.services.activation import NEXT_STEP_COPY, STEP_KEYS

    # Optional[Literal[...]] → (Literal[...], NoneType)
    literal = get_args(NextReviewAction.model_fields["next_key"].annotation)[0]
    assert get_args(literal) == STEP_KEYS
    assert tuple(NEXT_STEP_COPY) == STEP_KEYS
