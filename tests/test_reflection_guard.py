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
