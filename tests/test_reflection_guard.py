import pytest

from src.tradelens.services import reflection_guard, trade_summary


class Boom(Exception):
    pass


@pytest.mark.parametrize(
    "text",
    [
        "### Focus for Next Week\nKeep logging HTF bias before every entry.",
        "Long entries were late last week.",
        "Next time I will size smaller after a loss.",
    ],
)
def test_process_reflection_passes(text):
    reflection_guard.reject_forward_looking(text, Boom)


@pytest.mark.parametrize(
    "text",
    [
        "Next week, short the open.",
        "You should buy above 20150.",
        "Consider longs tomorrow.",
    ],
)
def test_trade_guidance_is_rejected_with_the_callers_error(text):
    with pytest.raises(Boom):
        reflection_guard.reject_forward_looking(text, Boom)


def test_trade_summary_still_raises_its_own_error():
    with pytest.raises(trade_summary.TradeSummaryError) as caught:
        trade_summary._reject_forward_looking("You should buy above 20150.")
    assert str(caught.value) == (
        "The AI summary contained forward-looking trade guidance."
    )


def test_the_guard_says_it_is_not_a_semantic_guarantee():
    doc = reflection_guard.reject_forward_looking.__doc__ or ""
    assert "defense-in-depth" in doc
    assert "not a semantic guarantee" in doc.lower()


# ── Fix round 1: false positives on past-tense and process-rule phrasing ──

PASSES = [
    "You entered long near 4500 twice.",
    "Aim to enter only after a confirmed displacement.",
    "You exited short above 20150 before the target.",
    "Took a long near 4500 after the London sweep.",
    "Went long at 4500 into the open.",
    "Held the short from 4520 through the news.",
    "Closed the long near 20150 early.",
    "Sold at 4510 on the first push.",
    "Bought near 4490 after the sweep.",
    "Shorted near 4530 against the bias.",
    "Longed at 4480 without confirmation.",
    "Stopped out of the long at 4500.",
    "Scaled out of the short near 4470.",
    "Added to the long above 4500 late.",
    "Cut the short at 4515.",
    "Plan to enter only after the 15m displacement closes.",
    "Wait for confirmation before you enter.",
    "Next week, only enter after confirmation.",
]

FAILS = [
    "Next week, short the open.",
    "You should buy above 20150.",
    "Consider longs tomorrow.",
    "Aim to buy above 4500.",
    "Short below 4500 tomorrow.",
    "Look to long near 20150.",
    "Consider shorts only after a sweep above 4520.",
    "You should enter long only after confirmation.",
    "Buy above 4500.",
]


@pytest.mark.parametrize("text", PASSES)
def test_sentence_table_passes(text):
    reflection_guard.reject_forward_looking(text, Boom)


@pytest.mark.parametrize("text", FAILS)
def test_sentence_table_fails(text):
    with pytest.raises(Boom):
        reflection_guard.reject_forward_looking(text, Boom)


def _usage():
    from src.tradelens.services.ai_client import Usage

    return Usage("claude-opus-5", 1, 1, 0, 0.0, 0.0)


def test_streamlit_daily_and_summary_calls_log_usage_once_on_guard_rejection(
    monkeypatch,
):
    """The Streamlit pages pass `on_usage`; a rejected answer still logs once."""
    from types import SimpleNamespace

    from src.tradelens.services import debrief

    bad = "\n\n".join(
        "%s\nYou should buy above 20150." % h for h in debrief._REQUIRED_SECTIONS
    )
    monkeypatch.setattr(debrief, "chat", lambda **k: (bad, _usage()))
    logged = []
    trade = SimpleNamespace(trade_date="2026-09-08", result="Win", pnl=5.0)
    with pytest.raises(debrief.DebriefError):
        debrief.generate_debrief([trade], on_usage=lambda usage: logged.append(usage))
    assert len(logged) == 1


def test_streamlit_weekly_call_logs_usage_once_on_validation_failure(
    two_users, monkeypatch
):
    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal
    from src.tradelens.services import weekly

    a, _ = two_users
    db = SessionLocal()
    try:
        db.add(Trade(user_id=a, asset="NQ", result="Win", trade_date="2026-09-08"))
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(weekly, "chat", lambda **k: ("### What Worked\nx", _usage()))
    logged = []
    with pytest.raises(weekly.WeeklyReviewError):
        weekly.generate_weekly_review(
            "2026-09-07", user_id=a, on_usage=lambda usage: logged.append(usage)
        )
    assert len(logged) == 1


def _page(name):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src" / "tradelens" / "ui" / "pages"
    return (root / name).read_text(encoding="utf-8")


def _flat(src):
    import re

    return re.sub(r"\(\s+", "(", re.sub(r"\s+", " ", src))


def test_insights_page_logs_review_usage_through_on_usage_exactly_once():
    src = _flat(_page("6_Insights.py"))
    assert src.count("generate_weekly_review(monday,") == 2
    assert src.count('on_usage=lambda usage: log_ai_usage("Weekly Review"') == 2
    assert src.count('log_ai_usage("Weekly Review"') == 2
    assert src.count("generate_debrief(day_trades,") == 1
    assert src.count('on_usage=lambda usage: log_ai_usage("Daily Debrief"') == 1
    # No second, post-success record for either feature.
    assert src.count('log_ai_usage("Daily Debrief"') == 1


def test_trades_page_logs_summary_usage_through_on_usage_exactly_once():
    src = _flat(_page("2_Trades.py"))
    assert src.count("generate_debrief(trades,") == 1
    assert src.count('on_usage=lambda usage: log_ai_usage("Trade Summary"') == 1
    assert src.count('log_ai_usage("Trade Summary"') == 1
