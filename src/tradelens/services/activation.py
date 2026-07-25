"""Where a new trader is on the path to their first useful weekly review.

Milestones are derived from records the product already needs — a Strategy
profile, complete Trade rows, a saved WeeklyReview — rather than from a
behavioural event table. A beta that instruments its users more closely
than it reviews their trades has its priorities backwards, and derived
state cannot drift out of sync with what the user can actually see.

Pure and Streamlit-free: callers pass the already-scoped records in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

# A weekly review needs a sample worth reviewing; below this the AI is
# mostly describing noise back to the trader.
TRADES_FOR_REVIEW = 5

# What makes a trade "journalled" rather than merely saved: the fields every
# downstream metric and review depends on.
_REQUIRED_TRADE_FIELDS = (
    "trade_date",
    "result",
    "pnl",
    "setup_type",
    "followed_rules",
)


@dataclass(frozen=True)
class ActivationStatus:
    completed: int
    total: int
    next_key: Optional[str]
    is_activated: bool
    complete_trades: int
    trades_until_review: int


def _is_complete_trade(trade: Any) -> bool:
    return all(
        getattr(trade, field, None) is not None for field in _REQUIRED_TRADE_FIELDS
    )


def activation_status(
    *,
    strategy: Optional[Mapping[str, Any]],
    trades: Iterable[Any],
    weekly_review: Optional[Mapping[str, Any]],
) -> ActivationStatus:
    """Return the trader's position on the three-step activation path."""
    complete_trades = sum(1 for trade in trades if _is_complete_trade(trade))

    checks = (
        ("strategy", bool(strategy and strategy.get("name"))),
        ("first_trade", complete_trades >= 1),
        (
            "weekly_review",
            complete_trades >= TRADES_FOR_REVIEW and weekly_review is not None,
        ),
    )

    completed = sum(1 for _, done in checks if done)
    next_key = next((key for key, done in checks if not done), None)

    return ActivationStatus(
        completed=completed,
        total=len(checks),
        next_key=next_key,
        is_activated=next_key is None,
        complete_trades=complete_trades,
        trades_until_review=max(0, TRADES_FOR_REVIEW - complete_trades),
    )


# Per unfinished step: card heading, slug fallback, and the link label.
NEXT_STEP_COPY = {
    "strategy": ("Define your trading process", "/Strategy", "Open Strategy Profile"),
    "first_trade": ("Journal your first completed trade", "/NewTrade", "Log a trade"),
    "weekly_review": ("Review your first useful sample", "/Insights", "Open Insights"),
}
