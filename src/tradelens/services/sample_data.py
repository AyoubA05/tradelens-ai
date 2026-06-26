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


def _sample_filter(query, user_id):
    """Scope a query to a user's sample trades (NULL owner when user_id is None)."""
    query = query.filter(Trade.is_sample == 1)
    if user_id is None:
        return query.filter(Trade.user_id.is_(None))
    return query.filter(Trade.user_id == user_id)


def count_sample_trades(user_id=None) -> int:
    """How many sample trades exist for this user."""
    db = SessionLocal()
    try:
        return _sample_filter(db.query(Trade), user_id).count()
    finally:
        db.close()


def clear_sample_trades(user_id=None) -> int:
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


def load_sample_trades(user_id=None) -> int:
    """Insert SAMPLE_COUNT demo trades flagged is_sample=1 for `user_id`.

    Clears this user's existing sample rows first so repeated loads don't pile up
    duplicates. Returns the number of rows inserted.
    """
    clear_sample_trades(user_id)
    rows = _build_sample_trades(user_id)
    db = SessionLocal()
    try:
        db.add_all(rows)
        db.commit()
        return len(rows)
    finally:
        db.close()
