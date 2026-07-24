"""Canonical outcome rules shared by the create, edit, and import paths.

A trade's money result is the fact; the Win/Loss/Breakeven label is a
description of it. When both are supplied they must agree, otherwise the
record would corrupt every downstream metric that classifies by outcome.
Streamlit-free by design so services and importers can share it.
"""

from __future__ import annotations

from typing import Optional

VALID_OUTCOMES = {"win": "Win", "loss": "Loss", "breakeven": "Breakeven"}


class OutcomeMismatch(ValueError):
    """Raised when a supplied outcome contradicts the supplied P&L."""


def is_blank(value: object) -> bool:
    """True for None and whitespace-only values (Streamlit sends both)."""
    return value is None or str(value).strip() == ""


def _normalise_result(result: object) -> Optional[str]:
    if is_blank(result):
        return None
    value = str(result).strip().lower()
    if value not in VALID_OUTCOMES:
        raise ValueError(f"Unknown outcome: {result!r}")
    return VALID_OUTCOMES[value]


def canonical_outcome(result: object, pnl: object) -> Optional[str]:
    """Return the outcome label that a row is allowed to store.

    P&L wins when it is present. A manual outcome is kept only when no P&L
    was entered. Disagreement raises rather than silently picking a side.
    """
    normalised = _normalise_result(result)
    if is_blank(pnl):
        return normalised

    value = float(pnl)
    expected = "Win" if value > 0 else "Loss" if value < 0 else "Breakeven"
    if normalised is not None and normalised != expected:
        raise OutcomeMismatch(
            f"Outcome {normalised!r} does not match P&L {value:,.2f}; "
            f"expected {expected!r}."
        )
    return expected
