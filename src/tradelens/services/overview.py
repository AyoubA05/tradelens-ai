# src/tradelens/services/overview.py
"""Compose the Overview payload from the existing metric functions.

Every computed figure comes from `services/metrics`, which the parity harness
already pins. This module selects, names, shapes, and gates those figures so
that missing evidence cannot become a plausible number at the API boundary.

Two rules govern the shaping:

* **Undefined is not zero.** Profit factor with no losses, expectancy with no
  trades, a drawdown over an empty period — each crosses the boundary as a
  value plus a state, never as a plausible-looking number. This includes
  figures `metrics` itself has already flattened to a finite 0.0 for lack of
  sample (max_drawdown below two points, consistency below five trades, an
  average with no members, a win rate over zero trades) — `finite_or_state`
  cannot recover those from NaN/inf because they were never non-finite, so
  this module gates them on the sample directly and reports
  `state: "undefined_no_sample"`.
* **A sample decides what it has earned.** The flags come from
  `services/sample_policy`, so the client renders a low-data state rather than
  inventing one per component.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Mapping, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from src.tradelens.api.serialization import finite_or_state
from src.tradelens.services import metrics
from src.tradelens.services.activation import activation_status
from src.tradelens.services.app_settings import DEFAULT_TIMEZONE, get_timezone
from src.tradelens.services.ownership import require_user_id
from src.tradelens.services.sample_policy import sample_state
from src.tradelens.services.sessions import KILLZONE_LABELS
from src.tradelens.services.strategy import get_active_strategy
from src.tradelens.services.trade_service import get_trades
from src.tradelens.services.weekly import get_weekly_reviews

RECENT_TRADE_LIMIT = 5

_TRADE_COLUMNS = (
    "id",
    "trade_date",
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
    "killzone",
    "day_of_week",
    # The grade columns are not displayed by the Overview, but
    # `consistency_score` weights a grade-trend term at 25% and looks for
    # exactly these two names. pandas reports a missing column as absent
    # rather than raising, so omitting them silently returned the neutral 0.5
    # trend and put the API up to 12.5 points away from the Streamlit
    # Dashboard, whose frame carries both. Divergence between the two surfaces
    # is the failure this module exists to prevent.
    "user_grade",
    "ai_grade",
)


def _frame(trades: List[Any]) -> pd.DataFrame:
    """The metric functions take a DataFrame with these exact columns.

    Built explicitly, and read with a bare `getattr` (no default), so a
    renamed or removed ORM attribute raises `AttributeError` here instead of
    silently producing an all-`None` column that every downstream metric then
    degrades against quietly — a renamed `pnl` rendering $0.00 across the
    dashboard is exactly the failure this module exists to prevent.
    """
    if not trades:
        return pd.DataFrame(columns=list(_TRADE_COLUMNS))
    return pd.DataFrame([{c: getattr(t, c) for c in _TRADE_COLUMNS} for t in trades])


def _pair(value: Any) -> Dict[str, Any]:
    """A possibly-undefined number as {value, state}."""
    number, state = finite_or_state(value)
    if number is None and state is None:
        state = "undefined_no_sample"
    return {"value": number, "state": state}


_UNDEFINED_NO_SAMPLE = {"value": None, "state": "undefined_no_sample"}


def _undefined(state: str) -> Dict[str, Any]:
    return {"value": None, "state": state}


def _money_pair(value: Any, *, complete: bool) -> Dict[str, Any]:
    """A monetary value that is only meaningful when its rows record P&L."""
    if not complete:
        return _undefined("undefined_incomplete_sample")
    return _pair(value)


def _sample_pair(value: Any, insufficient: bool) -> Dict[str, Any]:
    """A number gated by sample size, not merely by non-finiteness.

    `finite_or_state` only recovers a state from NaN/±inf. Several metrics
    flatten "not enough data" to an ordinary finite 0.0 instead of a
    non-finite sentinel — max_drawdown below two points, consistency_score
    below five trades, an average over zero members, a win rate over zero
    trades — so `_pair` alone is a no-op on all of them and 0.0 would read as
    a real answer. `insufficient` is computed by the caller from the sample
    counts already in hand (`basic`), not from the metric's return value.
    """
    if insufficient:
        return dict(_UNDEFINED_NO_SAMPLE)
    return _pair(value)


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


def _today_for_owner(owner: int, *, now_utc: Optional[dt.datetime] = None) -> dt.date:
    """Return the current calendar date in one owner's configured timezone."""
    zone_name = get_timezone(owner)
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, KeyError, ValueError, OSError):
        try:
            zone = ZoneInfo(DEFAULT_TIMEZONE)
        except (ZoneInfoNotFoundError, KeyError, ValueError, OSError):
            zone = dt.timezone.utc

    instant = now_utc or dt.datetime.now(dt.timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=dt.timezone.utc)
    return instant.astimezone(zone).date()


def build_overview(
    *,
    user_id: int,
    start: str,
    end: str,
    today: Optional[dt.date] = None,
) -> dict:
    """Everything the Overview screen shows, for one owner over one period."""
    owner = require_user_id(user_id)
    now = today or _today_for_owner(owner)

    trades = get_trades(user_id=owner, start_date=start, end_date=end)
    df = _frame(trades)
    sample = sample_state(df)

    # Activation and "today"/"this week" are lifetime concepts, not a function
    # of whatever analysis period the trader happens to have selected. A
    # trader with 40 lifetime trades who picks a quiet month must not be told
    # to log their first trade, and today's P&L must not vanish because
    # `start`/`end` don't happen to include today. One extra unfiltered read
    # covers both.
    lifetime_trades = get_trades(user_id=owner)
    lifetime_df = _frame(lifetime_trades)

    basic = metrics.compute_basic_metrics(df)
    equity = metrics.compute_equity_curve(df)
    streaks = metrics.compute_streaks(df)
    adherence = metrics.rule_adherence_rate(df)
    leak = metrics.edge_leak_summary(df)

    total_trades = int(_need(basic, "total_trades") or 0)
    wins = int(_need(basic, "wins") or 0)
    losses = int(_need(basic, "losses") or 0)
    pnl = pd.to_numeric(df["pnl"], errors="coerce")
    pnl_recorded = int(pnl.notna().sum())
    pnl_complete = bool(pnl.notna().all())
    win_mask, loss_mask, _ = metrics.outcome_masks(df)
    win_pnl_complete = wins > 0 and bool(pnl[win_mask].notna().all())
    loss_pnl_complete = losses > 0 and bool(pnl[loss_mask].notna().all())

    # A period with neither a win nor a loss has no ratio to report: no
    # numerator and no denominator. `compute_profit_factor_raw` flattens that
    # to a finite 0.0, which `finite_or_state` cannot tell apart from a genuine
    # zero (all-losing period), so an all-breakeven month rendered "0.00x" —
    # the worst possible profit factor — where the truth is "not applicable".
    # Gated on the sample here, like the other pre-flattened figures.
    if total_trades == 0 or (wins == 0 and losses == 0):
        pf_value, pf_state = None, "undefined_no_sample"
    elif not pnl_complete:
        pf_value, pf_state = None, "undefined_incomplete_sample"
    else:
        pf_value, pf_state = finite_or_state(metrics.compute_profit_factor_raw(df))
    if total_trades == 0:
        expectancy_value, expectancy_state = None, "undefined_no_sample"
    elif not pnl_complete:
        expectancy_value, expectancy_state = None, "undefined_incomplete_sample"
    else:
        expectancy_value, expectancy_state = finite_or_state(
            metrics.compute_expectancy(basic)
        )

    end_date = dt.date.fromisoformat(end)

    # `compute_equity_curve` above stays as the max-drawdown input (one point
    # per trade, matching how drawdown is computed elsewhere); the chart the
    # Overview draws needs one point per day, which is what daily_equity_curve
    # gives — collapsed and column-named `cumulative_pnl`, not `equity`.
    #
    # Missing P&L is not zero movement, so an incomplete period has no curve.
    # Small complete samples still cross the boundary; sample_policy tells the
    # client whether they have earned the right to be drawn.
    equity_curve = (
        [
            {"date": str(r["trade_date"]), "equity": float(r["cumulative_pnl"])}
            for _, r in metrics.daily_equity_curve(df).iterrows()
        ]
        if pnl_complete
        else []
    )

    lifetime_dates = pd.to_datetime(lifetime_df["trade_date"], errors="coerce").dt.date
    week_start = now - dt.timedelta(days=now.weekday())
    week_end = week_start + dt.timedelta(days=6)
    today_rows = lifetime_dates == now
    week_rows = (
        lifetime_dates.notna()
        & (lifetime_dates >= week_start)
        & (lifetime_dates <= week_end)
    )
    lifetime_pnl = pd.to_numeric(lifetime_df["pnl"], errors="coerce")
    today_complete = bool(lifetime_pnl[today_rows].notna().all())
    week_complete = bool(lifetime_pnl[week_rows].notna().all())

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
            "pnl_recorded": pnl_recorded,
            "pnl_complete": pnl_complete,
        },
        "kpi": {
            "net_pnl": _money_pair(
                float(_need(basic, "total_pnl") or 0.0), complete=pnl_complete
            ),
            "win_rate": _sample_pair(_need(basic, "win_rate"), total_trades == 0),
            "expectancy": expectancy_value,
            "expectancy_state": expectancy_state,
            "profit_factor": pf_value,
            "profit_factor_state": pf_state,
            "trades": total_trades,
            "wins": wins,
            "losses": losses,
            "today_pnl": _money_pair(
                metrics.today_pnl(lifetime_df, today=now), complete=today_complete
            ),
            "week_pnl": _money_pair(
                metrics.current_week_pnl(lifetime_df, today=now),
                complete=week_complete,
            ),
        },
        "risk": {
            "max_drawdown": (
                _undefined("undefined_incomplete_sample")
                if not pnl_complete
                else _sample_pair(metrics.compute_max_drawdown(equity), len(equity) < 2)
            ),
            "rule_adherence": {
                "rate": adherence.rate,
                "followed": adherence.followed,
                "recorded": adherence.recorded,
            },
            # EdgeLeakSummary names these net_pnl / qualifying_trades /
            # recorded_trades; the API uses plainer words for the same
            # figures. `net_pnl` is None when there is no followed_rules or
            # mistake_tags evidence to interpret — that is a different fact
            # from "zero leaked", so it goes through `_pair`, not `or 0.0`.
            "edge_leak": {
                "amount": (
                    _undefined("undefined_incomplete_sample")
                    if leak.recorded_trades > 0 and not pnl_complete
                    else _pair(leak.net_pnl)
                ),
                "trades": leak.qualifying_trades,
                "recorded": leak.recorded_trades,
            },
            "consistency": _sample_pair(
                metrics.consistency_score(df),
                total_trades < metrics.MIN_TRADES_FOR_CONSISTENCY,
            ),
        },
        "trajectory": {
            "equity_curve": equity_curve,
            # compute_streaks names these current_streak / max_win_streak /
            # max_loss_streak.
            "current_streak": _need(streaks, "current_streak"),
            "streak_type": _need(streaks, "streak_type"),
            "best_streak": _need(streaks, "max_win_streak"),
            "worst_streak": _need(streaks, "max_loss_streak"),
            "average_win": (
                _undefined("undefined_no_sample")
                if wins == 0
                else (
                    _undefined("undefined_incomplete_sample")
                    if not win_pnl_complete
                    else _pair(_need(basic, "avg_win"))
                )
            ),
            "average_loss": (
                _undefined("undefined_no_sample")
                if losses == 0
                else (
                    _undefined("undefined_incomplete_sample")
                    if not loss_pnl_complete
                    else _pair(_need(basic, "avg_loss"))
                )
            ),
        },
        "recurring_edge": {
            "killzones": (
                _breakdown(
                    metrics.killzone_performance(df),
                    "killzone",
                    labels=KILLZONE_LABELS,
                )
                if pnl_complete
                else []
            ),
            "setups": (
                _breakdown(metrics.setup_performance(df), "setup_type")
                if pnl_complete
                else []
            ),
        },
        "calendar": _calendar(df, end_date.year, end_date.month),
        "next_review_action": _next_action(owner, lifetime_trades),
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


def _breakdown(
    frame: pd.DataFrame,
    label_column: str,
    *,
    labels: Optional[Mapping[str, str]] = None,
) -> List[dict]:
    """A grouped metric frame as rows the client can render directly.

    Both groupers expose the P&L column as `total_pnl`; the API calls it
    `net_pnl` because that is what it means to a reader. An empty/None frame
    is a legitimate "nothing to show"; a frame that lacks `label_column`,
    `total_pnl`, or `trades` is not — that means the grouper's shape changed,
    and the previous silent `return []` for a missing label column would have
    hidden that behind an empty panel instead.
    """
    if frame is None or frame.empty:
        return []
    for required in (label_column, "total_pnl", "trades"):
        if required not in frame.columns:
            raise KeyError(f"breakdown frame is missing column {required!r}")
    rows = []
    for _, r in frame.iterrows():
        key = str(r[label_column])
        rows.append(
            {
                "label": labels.get(key, key) if labels is not None else key,
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
    incomplete_dates = set()
    if df is not None and not df.empty:
        dates = pd.to_datetime(df["trade_date"], errors="coerce")
        pnl = pd.to_numeric(df["pnl"], errors="coerce")
        incomplete_dates = {
            value.date().isoformat()
            for value in dates[pnl.isna() & dates.notna()].tolist()
            if value.year == year and value.month == month
        }
    days = []
    if frame is not None and not frame.empty:
        for _, r in frame.iterrows():
            trade_date = str(_need(r, "trade_date"))
            if trade_date in incomplete_dates:
                days.append({"date": trade_date, "pnl": None, "outcome": "unknown"})
                continue
            pnl = float(_need(r, "net_pnl") or 0.0)
            days.append(
                {
                    "date": trade_date,
                    "pnl": pnl,
                    "outcome": (
                        "positive" if pnl > 0 else "negative" if pnl < 0 else "flat"
                    ),
                }
            )
    return {"year": year, "month": month, "days": days}


def _next_action(owner: int, trades: List[Any]) -> dict:
    """Where the trader stands on the activation path.

    `trades` here must be the trader's lifetime trades, not a period-filtered
    slice — activation is a lifetime concept, and a narrow analysis window
    must not reset it.
    """
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
