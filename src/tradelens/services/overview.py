# src/tradelens/services/overview.py
"""Compose the Overview payload from the existing metric functions.

This module adds no arithmetic. Every figure comes from `services/metrics`,
which the parity harness already pins — the job here is to select, name, and
shape, so that the API and the Streamlit Dashboard cannot drift into two
different answers to the same question.

Two rules govern the shaping:

* **Undefined is not zero.** Profit factor with no losses, expectancy with no
  trades, a drawdown over an empty period — each crosses the boundary as a
  value plus a state, never as a plausible-looking number.
* **A sample decides what it has earned.** The flags come from
  `services/sample_policy`, so the client renders a low-data state rather than
  inventing one per component.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

import pandas as pd

from src.tradelens.api.serialization import finite_or_state
from src.tradelens.services import metrics
from src.tradelens.services.activation import activation_status
from src.tradelens.services.ownership import require_user_id
from src.tradelens.services.sample_policy import sample_state
from src.tradelens.services.strategy import get_active_strategy
from src.tradelens.services.trade_service import get_trades
from src.tradelens.services.weekly import get_weekly_reviews

RECENT_TRADE_LIMIT = 5

_TRADE_COLUMNS = (
    "id",
    "trade_date",
    "entry_time",
    "asset",
    "session",
    "setup_type",
    "timeframe",
    "result",
    "pnl",
    "rr_realized",
    "risk_amount",
    "followed_rules",
    "mistake_tags",
    "strategy_used",
    "htf_bias",
    "ltf_bias",
    "killzone",
    "day_of_week",
)


def _frame(trades: List[Any]) -> pd.DataFrame:
    """The metric functions take a DataFrame with these exact columns.

    Built explicitly rather than from `__dict__` so a schema change surfaces
    here as a missing column instead of silently changing a metric.
    """
    if not trades:
        return pd.DataFrame(columns=list(_TRADE_COLUMNS))
    return pd.DataFrame(
        [{c: getattr(t, c, None) for c in _TRADE_COLUMNS} for t in trades]
    )


def _pair(value: Any) -> Dict[str, Any]:
    """A possibly-undefined number as {value, state}."""
    number, state = finite_or_state(value)
    return {"value": number, "state": state}


def _need(mapping: Any, key: str) -> Any:
    """Read a required key, loudly.

    Deliberately not `.get(key, 0.0)`. Every figure here comes from
    `services/metrics`, and if one of those functions is renamed or its output
    reshaped, a defaulting read turns the mistake into a plausible $0.00 on a
    trader's dashboard instead of a failure. The pre-flight scan for this phase
    found six such wrong column names at once, five of which would have rendered
    as confident zeroes. Fail here instead.
    """
    if isinstance(mapping, dict):
        if key not in mapping:
            raise KeyError(f"metrics output is missing {key!r}; got {sorted(mapping)}")
        return mapping[key]
    if key not in mapping:
        raise KeyError(f"metrics frame is missing column {key!r}")
    return mapping[key]


def build_overview(
    *,
    user_id: int,
    start: str,
    end: str,
    today: Optional[dt.date] = None,
) -> dict:
    """Everything the Overview screen shows, for one owner over one period."""
    owner = require_user_id(user_id)
    now = today or dt.date.today()

    trades = get_trades(user_id=owner, start_date=start, end_date=end)
    df = _frame(trades)
    sample = sample_state(df)

    basic = metrics.compute_basic_metrics(df)
    equity = metrics.compute_equity_curve(df)
    streaks = metrics.compute_streaks(df)
    adherence = metrics.rule_adherence_rate(df)
    leak = metrics.edge_leak_summary(df)

    pf_value, pf_state = finite_or_state(metrics.compute_profit_factor_raw(df))
    expectancy_value, expectancy_state = finite_or_state(
        metrics.compute_expectancy(basic)
        if _need(basic, "total_trades")
        else float("nan")
    )

    end_date = dt.date.fromisoformat(end)

    # `compute_equity_curve` above stays as the max-drawdown input (one point
    # per trade, matching how drawdown is computed elsewhere); the chart the
    # Overview draws needs one point per day, which is what daily_equity_curve
    # gives — collapsed and column-named `cumulative_pnl`, not `equity`.
    equity_curve = (
        []
        if not sample.show_series
        else [
            {"date": str(r["trade_date"]), "equity": float(r["cumulative_pnl"])}
            for _, r in metrics.daily_equity_curve(df).iterrows()
        ]
    )

    return {
        "period": {"from": start, "to": end},
        "sample": {
            "trades": sample.trades,
            "dated_points": sample.dated_points,
            "show_summary": sample.show_summary,
            "show_series": sample.show_series,
            "show_dominant_series": sample.show_dominant_series,
            "show_comparisons": sample.show_comparisons,
            "show_patterns": sample.show_patterns,
        },
        "kpi": {
            "net_pnl": float(_need(basic, "total_pnl") or 0.0),
            "win_rate": _need(basic, "win_rate"),
            "expectancy": expectancy_value,
            "expectancy_state": expectancy_state,
            "profit_factor": pf_value,
            "profit_factor_state": pf_state,
            "trades": int(_need(basic, "total_trades") or 0),
            "wins": int(_need(basic, "wins") or 0),
            "losses": int(_need(basic, "losses") or 0),
            "today_pnl": metrics.today_pnl(df, today=now),
            "week_pnl": metrics.current_week_pnl(df, today=now),
        },
        "risk": {
            "max_drawdown": _pair(metrics.compute_max_drawdown(equity)),
            "rule_adherence": {
                "rate": adherence.rate,
                "followed": adherence.followed,
                "recorded": adherence.recorded,
            },
            # EdgeLeakSummary names these net_pnl / qualifying_trades /
            # recorded_trades; the API uses plainer words for the same figures.
            "edge_leak": {
                "amount": leak.net_pnl or 0.0,
                "trades": leak.qualifying_trades,
                "recorded": leak.recorded_trades,
            },
            "consistency": _pair(metrics.consistency_score(df)),
        },
        "equity_curve": equity_curve,
        "trajectory": {
            # compute_streaks names these current_streak / max_win_streak /
            # max_loss_streak.
            "current_streak": _need(streaks, "current_streak"),
            "streak_type": _need(streaks, "streak_type"),
            "best_streak": _need(streaks, "max_win_streak"),
            "worst_streak": _need(streaks, "max_loss_streak"),
            "average_win": _pair(_need(basic, "avg_win")),
            "average_loss": _pair(_need(basic, "avg_loss")),
        },
        "recurring_edge": {
            "killzones": _breakdown(metrics.killzone_performance(df), "killzone"),
            "setups": _breakdown(metrics.setup_performance(df), "setup_type"),
        },
        "calendar": _calendar(df, end_date.year, end_date.month),
        "next_review_action": _next_action(owner, trades),
        "recent_trades": [
            {
                "id": t.id,
                "trade_date": t.trade_date,
                "asset": t.asset,
                "session": t.session,
                "setup_type": t.setup_type,
                "result": t.result,
                "pnl": t.pnl,
                "rr_realized": t.rr_realized,
            }
            for t in trades[:RECENT_TRADE_LIMIT]
        ],
    }


def _breakdown(frame: pd.DataFrame, label_column: str) -> List[dict]:
    """A grouped metric frame as rows the client can render directly.

    Both groupers expose the P&L column as `total_pnl`; the API calls it
    `net_pnl` because that is what it means to a reader.
    """
    if frame is None or frame.empty or label_column not in frame.columns:
        return []
    for required in (label_column, "total_pnl", "trades"):
        if required not in frame.columns:
            raise KeyError(f"breakdown frame is missing column {required!r}")
    rows = []
    for _, r in frame.iterrows():
        rows.append(
            {
                "label": str(r[label_column]),
                "net_pnl": float(r["total_pnl"] or 0.0),
                "trades": int(r["trades"] or 0),
            }
        )
    return rows


def _calendar(df: pd.DataFrame, year: int, month: int) -> dict:
    """One month of trading days.

    An empty day means no trade was taken, which is information rather than
    missing data — so days without trades are simply absent from `days`.
    """
    frame = metrics.calendar_daily_pnl(df, year, month)
    days = []
    if frame is not None and not frame.empty:
        for _, r in frame.iterrows():
            pnl = float(_need(r, "net_pnl") or 0.0)
            days.append(
                {
                    "date": str(_need(r, "trade_date")),
                    "pnl": pnl,
                    "outcome": (
                        "positive" if pnl > 0 else "negative" if pnl < 0 else "flat"
                    ),
                }
            )
    return {"year": year, "month": month, "days": days}


def _next_action(owner: int, trades: List[Any]) -> dict:
    """Where the trader stands on the activation path."""
    status = activation_status(
        strategy=get_active_strategy(owner),
        trades=trades,
        weekly_review=(get_weekly_reviews(owner, limit=1) or [None])[0],
    )
    return {
        "completed": status.completed,
        "total": status.total,
        "next_key": status.next_key,
        "is_activated": status.is_activated,
        "trades_until_review": status.trades_until_review,
    }
