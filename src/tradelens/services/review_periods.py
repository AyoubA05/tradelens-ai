"""Review periods and period figures for the AI Review lenses.

Moved from `ui/components/review_dates.py` and `ui/components/review_reader.py`
(Phase 10A, Task A1) so the API can offer the same week/day options and strip
figures without importing the UI. The UI modules re-export these names.

`completed_*_options` never offer a period after the owner's today. Callers
compute `today` with `app_settings.today_for_owner` so every boundary follows
the owner's timezone, DST included (decisions R6, C6).

Streamlit-free.
"""

from __future__ import annotations

import datetime as dt
import math

import pandas as pd

from src.tradelens.services.ownership import require_user_id


def review_day_options(frame: pd.DataFrame) -> tuple[dt.date, ...]:
    trade_dates = frame.get("trade_date")
    if trade_dates is None:
        return ()
    parsed = pd.to_datetime(trade_dates, errors="coerce").dropna()
    return tuple(sorted(set(parsed.dt.date), reverse=True))


def review_week_options(frame: pd.DataFrame) -> tuple[dt.date, ...]:
    mondays = {
        day - dt.timedelta(days=day.weekday()) for day in review_day_options(frame)
    }
    return tuple(sorted(mondays, reverse=True))


def period_stats(trades) -> dict:
    """The five period figures every lens's strip reads, in one shape.

    §7.6 asks for one strip on all three lenses, same builder, same cells.
    Weekly and Daily already receive this dict from their own service; only
    Patterns had nothing, and it had nothing because there was nowhere to get
    it from that did not mean recomputing on the page.

    Nothing is calculated here. Each figure comes from the approved metrics
    service and is only assembled into the shape `render_kpi_strip` reads.
    """
    from src.tradelens.services.metrics import (
        compute_basic_metrics,
        compute_profit_factor_raw,
        total_edge_leak,
    )

    if trades is None or not isinstance(trades, pd.DataFrame) or trades.empty:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "profit_factor": None,
            "total_edge_leak": 0.0,
        }
    m = compute_basic_metrics(trades)
    pf = compute_profit_factor_raw(trades)
    return {
        "trades": int(m["total_trades"]),
        "win_rate": m["win_rate"],
        # None means "wins with no losses"; the strip renders that as ∞. An
        # inf float would not survive being stored or serialised, which is
        # why the weekly service uses the same convention.
        "profit_factor": None if math.isinf(pf) else pf,
        "total_pnl": m["total_pnl"],
        "total_edge_leak": total_edge_leak(trades),
    }


def _owner_trade_frame(owner: int) -> pd.DataFrame:
    from src.tradelens.services.trade_service import get_trades

    trades = get_trades(user_id=require_user_id(owner))
    return pd.DataFrame({"trade_date": [t.trade_date for t in trades]})


def completed_day_options(owner: int, *, today: dt.date) -> tuple:
    """Trade days on or before the owner's today, newest first (decision R6)."""
    return tuple(d for d in review_day_options(_owner_trade_frame(owner)) if d <= today)


def completed_week_options(owner: int, *, today: dt.date) -> tuple:
    """Mondays of weeks with a trade on or before the owner's today, newest first."""
    days = completed_day_options(owner, today=today)
    return tuple(
        sorted({d - dt.timedelta(days=d.weekday()) for d in days}, reverse=True)
    )
