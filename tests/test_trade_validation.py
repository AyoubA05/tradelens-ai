import pytest

from src.tradelens.services.trade_validation import OutcomeMismatch, canonical_outcome


@pytest.mark.parametrize(
    ("pnl", "expected"),
    [(250, "Win"), (-50, "Loss"), (0, "Breakeven"), ("125.25", "Win")],
)
def test_pnl_determines_outcome(pnl, expected):
    assert canonical_outcome(None, pnl) == expected


def test_manual_outcome_is_kept_when_pnl_is_missing():
    assert canonical_outcome("loss", None) == "Loss"


def test_conflicting_values_are_rejected():
    with pytest.raises(OutcomeMismatch, match="does not match"):
        canonical_outcome("Win", -500)


def test_unknown_manual_outcome_is_rejected():
    with pytest.raises(ValueError, match="Unknown outcome"):
        canonical_outcome("Great", None)


def test_blank_values_are_left_alone():
    assert canonical_outcome(None, None) is None
    assert canonical_outcome("", "") is None


def test_matching_values_are_accepted():
    assert canonical_outcome("Win", 250) == "Win"
    assert canonical_outcome("Breakeven", 0) == "Breakeven"
