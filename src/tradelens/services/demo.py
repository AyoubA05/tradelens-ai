"""
DEMO_MODE support for TradeLens AI (Week 6 — Ship Week).

Three pieces:
  * is_demo()          — thin read of settings.demo_mode.
  * get_demo_df()      — a deterministic, synthetic 60-trade DataFrame with the
                         full Week 5 SMC/ICT column set, so the public demo
                         renders rich analytics on a cold/empty cloud DB with
                         ZERO database access and zero API spend.
  * load_demo_fixture()— returns a cached AI response (as a string) for a feature,
                         keyed by trade_id with a "default" fallback. Never raises.

Streamlit-free (safe to import from services/pages). No database access.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Optional

from src.tradelens.config import settings

# NOTE (intentional coupling): demo AI fixtures live under tests/fixtures/demo_ai/
# per the Week 6 spec. The whole repo deploys to Streamlit Cloud, so this path is
# valid at runtime. Resolved repo-relative: services/ -> tradelens -> src -> root.
_FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "demo_ai"

_ASSETS = ["NQ", "ES", "BTCUSD", "EURUSD"]
_KILLZONES = ["ny_am", "london", "ny_pm", "asia"]
_CONFIRMATIONS = ["BOS", "CHoCH", "Liquidity Sweep", "FVG Fill", "OB Reaction"]
_SETUPS = ["FVG", "Order Block", "Liquidity Sweep", "BOS", "OB + FVG"]
_ENTRY_TYPES = ["limit", "market", "stop_limit"]
_EMOTIONS = ["Calm", "Confident", "Anxious", "FOMO", "Neutral"]
_MISTAKES = ["Early Entry", "Late Entry", "Moved Stop", "FOMO", "Overtrading"]
_GRADES = ["A+", "A", "A-", "B+", "B", "C+", "C", "D", "F"]
_DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
DEMO_TRADE_COUNT = 60


def is_demo() -> bool:
    """True when DEMO_MODE is on (cached/mock AI output, zero API spend)."""
    return bool(settings.demo_mode)


def _demo_dates(
    *, as_of: dt.date, count: int = DEMO_TRADE_COUNT
) -> tuple[dt.date, ...]:
    dates = []
    cursor = as_of
    while len(dates) < count:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= dt.timedelta(days=1)
    return tuple(reversed(dates))


def _demo_row(
    *,
    i: int,
    day: dt.date,
    a: int,
    pnl: float,
    rr: float,
    result: str,
    followed: int,
    mistakes: list[str],
    grade: str,
) -> dict[str, object]:
    return {
        "id": i + 1,
        "trade_date": day.isoformat(),
        "day_of_week": _DOW[day.weekday()],
        "asset": _ASSETS[i % len(_ASSETS)],
        "asset_class": "Futures",
        "session": ["London", "NY AM", "NY PM", "Asia"][i % 4],
        "timeframe": ["5m", "15m", "1H"][i % 3],
        "strategy_used": "ICT OB Strategy",
        "setup_type": _SETUPS[i % len(_SETUPS)],
        "direction": "Long" if i % 2 == 0 else "Short",
        "entry_price": round(100 + a * 0.5, 2),
        "exit_price": round(100 + a * 0.5 + (pnl / 10.0), 2),
        "pnl": pnl,
        "result": result,
        "rr_realized": rr,
        "ai_grade": grade,
        "user_grade": grade if i % 3 else None,
        "killzone": _KILLZONES[i % len(_KILLZONES)],
        "htf_bias": ["bullish", "bearish", "neutral"][i % 3],
        "liquidity_sweep": i % 2,
        "fvg_used": (i + 1) % 2,
        "order_block_used": i % 2,
        "bos": (i + 1) % 2,
        "choch": i % 3 == 0,
        "confirmation_model": _CONFIRMATIONS[i % len(_CONFIRMATIONS)],
        "entry_type": _ENTRY_TYPES[i % len(_ENTRY_TYPES)],
        "mistake_tags": json.dumps(mistakes),
        "followed_rules": followed,
        "emotions_before": _EMOTIONS[i % len(_EMOTIONS)],
        "emotions_during": _EMOTIONS[(i + 1) % len(_EMOTIONS)],
        "emotions_after": _EMOTIONS[(i + 2) % len(_EMOTIONS)],
        "updated_at": f"{day.isoformat()}T12:00:00",
    }


def get_demo_df(*, as_of: Optional[dt.date] = None):
    """Return 60 deterministic completed trades ending no later than ``as_of``."""
    import pandas as pd  # local import keeps module import light

    anchor = as_of or dt.date.today()
    dates = _demo_dates(as_of=anchor)
    rows = []
    for i, day in enumerate(dates):
        # Deterministic pseudo-randomness from the index — no RNG state.
        a = (i * 37) % 100
        b = (i * 53) % 100
        result = "Win" if a < 55 else ("Loss" if a < 90 else "Breakeven")
        if result == "Win":
            pnl = round(120 + (b % 9) * 45, 2)
            rr = round(1.5 + (b % 5) * 0.5, 2)
        elif result == "Loss":
            pnl = round(-(80 + (b % 6) * 30), 2)
            rr = round(-1.0, 2)
        else:
            pnl, rr = 0.0, 0.0

        followed = 0 if (i % 5 == 0) else 1
        mistakes = [] if followed else [_MISTAKES[i % len(_MISTAKES)]]
        grade = _GRADES[i % len(_GRADES)]

        rows.append(
            _demo_row(
                i=i,
                day=day,
                a=a,
                pnl=pnl,
                rr=rr,
                result=result,
                followed=followed,
                mistakes=mistakes,
                grade=grade,
            )
        )
    return pd.DataFrame(rows)


def load_demo_fixture(feature: str, trade_id: Optional[int] = None) -> Optional[str]:
    """Return the cached demo AI response for a feature as a string.

    Looks up tests/fixtures/demo_ai/<feature>.json (a dict keyed by str trade_id
    plus a "default"). Returns the trade-specific entry, else the default, else
    None. Object/list entries are JSON-encoded so callers can pass the result
    straight through as an ai_client demo_response. Never raises.
    """
    try:
        path = _FIXTURES_DIR / f"{feature}.json"
        if not feature or not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        entry = None
        if trade_id is not None:
            entry = data.get(str(trade_id))
        if entry is None:
            entry = data.get("default")
        if entry is None:
            return None
        return entry if isinstance(entry, str) else json.dumps(entry)
    except Exception:
        return None
