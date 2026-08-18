"""
Sample/demo trade management (Session A + Session B).

Loads a batch of clearly-flagged demo trades (is_sample = 1) and clears ONLY
those rows — real trades are never touched. Sessions B scopes everything to a
user_id so one account's demo data never clears another's. Streamlit-free.
"""

from __future__ import annotations

import datetime as dt
import json

from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ownership import require_user_id

_ASSETS = [
    ("NQ", "Futures"),
    ("ES", "Futures"),
    ("EURUSD", "Forex"),
    ("GBP/USD", "Forex"),
]
_SETUPS = ["Liquidity Sweep", "FVG + OB", "BOS + FVG", "CHoCH Entry"]
_KILLZONES = ["ny_am", "london_open", "ny_pm"]
_SESSIONS = ["New York", "London", "New York", "Asian"]
_MISTAKES = ["FOMO Entry", "Moved SL", "Overtraded", "Ignored HTF Bias"]
_GRADES = ["A", "B", "C", "B+", "A-"]
SAMPLE_COUNT = 20


def _sample_filter(query, user_id: int):
    """Scope a query to one user's sample trades.

    The owner is required. It used to fall back to the NULL-owner (legacy)
    tenant when `user_id` was None instead of raising — a missing owner
    silently widened the query rather than being caught as a programming
    error.
    """
    owner = require_user_id(user_id)
    return query.filter(Trade.is_sample == 1, Trade.user_id == owner)


def count_sample_trades(user_id) -> int:
    """How many sample trades exist for this user."""
    db = SessionLocal()
    try:
        return _sample_filter(db.query(Trade), user_id).count()
    finally:
        db.close()


def clear_sample_trades(user_id) -> int:
    """Delete only this user's sample-flagged trades. Returns the number removed."""
    db = SessionLocal()
    try:
        removed = _sample_filter(db.query(Trade), user_id).delete(
            synchronize_session=False
        )
        db.commit()
        return removed
    finally:
        db.close()


def _recent_weekdays(n: int) -> list:
    """The last `n` weekdays ending today, oldest first.

    Anchoring sample trades to the recent past (instead of a fixed calendar date)
    keeps them inside the app's default date ranges — dashboard, "this week", and
    the Analytics last-90-days filter all show them no matter when the demo runs.
    """
    days, day = [], dt.date.today()
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day -= dt.timedelta(days=1)
    return list(reversed(days))


def _build_sample_trades(user_id) -> list:
    """A deterministic, varied 20-trade demo set (~60% win / 30% loss / 10% BE),
    dated over the most recent weekdays so it always appears on the dashboard."""
    rows = []
    weekdays = _recent_weekdays(SAMPLE_COUNT)
    for i in range(SAMPLE_COUNT):
        bucket = i % 10
        result = "Win" if bucket < 6 else ("Loss" if bucket < 9 else "Breakeven")
        if result == "Win":
            pnl = float(200 + (i * 37) % 600)  # $200–$800
            rr = round(1.5 + (i % 4) * 0.5, 2)
        elif result == "Loss":
            pnl = float(-(150 + (i * 23) % 250))  # -$150 to -$400
            rr = -1.0
        else:
            pnl, rr = 0.0, 0.0

        day = weekdays[i]

        asset, asset_class = _ASSETS[i % len(_ASSETS)]
        mistakes = [_MISTAKES[i % len(_MISTAKES)]] if result == "Loss" else []
        rows.append(
            Trade(
                trade_date=day.isoformat(),
                day_of_week=day.strftime("%A"),
                asset=asset,
                asset_class=asset_class,
                direction="Long" if i % 2 == 0 else "Short",
                session=_SESSIONS[i % len(_SESSIONS)],
                timeframe=["5m", "15m", "1H"][i % 3],
                setup_type=_SETUPS[i % len(_SETUPS)],
                killzone=_KILLZONES[i % len(_KILLZONES)],
                htf_bias=["bullish", "bearish", "neutral"][i % 3],
                result=result,
                pnl=pnl,
                rr_realized=rr,
                ai_grade=_GRADES[i % len(_GRADES)],
                mistake_tags=json.dumps(mistakes),
                followed_rules=0 if mistakes else 1,
                notes="Sample trade for the demo." if i % 3 == 0 else None,
                is_sample=1,
                user_id=user_id,
            )
        )
    return rows


def load_sample_trades(user_id) -> int:
    """Insert SAMPLE_COUNT demo trades flagged is_sample=1 for `user_id`.

    The owner is required, for the same reason as `_sample_filter`. Clears
    this user's existing sample rows first so repeated loads don't pile up
    duplicates. Returns the number of rows inserted.

    Each row is stamped with the user's active strategy, exactly as
    New Trade stamps a real one. Without it the sample set produces trades
    no logging flow could actually create, and Analytics' Strategy filter
    sits permanently empty for anyone exploring the product with sample
    data — a control that offers nothing is worse than no control.
    """
    owner = require_user_id(user_id)
    clear_sample_trades(owner)
    rows = _build_sample_trades(owner)

    strategy_name = None
    try:
        from src.tradelens.services.strategy import get_active_strategy

        active = get_active_strategy(owner)
        strategy_name = (active or {}).get("name") or None
    except Exception:  # noqa: BLE001 — sample data must load regardless
        strategy_name = None
    if strategy_name:
        for row in rows:
            row.strategy_used = strategy_name

    db = SessionLocal()
    try:
        db.add_all(rows)
        db.commit()
        return len(rows)
    finally:
        db.close()
