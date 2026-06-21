# Keep all analytics calculations reusable and Streamlit-free so future dashboards
# can build new charts without rewriting metric logic.
#
# Expected DataFrame schema (matches Trade ORM attribute names):
#   trade_date   str  "YYYY-MM-DD"           (ISO string sorts correctly)
#   result       str  "Win" / "Loss" / "Breakeven"   (title case; functions normalize)
#   pnl          float  nullable
#   rr_realized  float  nullable
#   asset        str    NOT NULL
#   session      str    nullable
#   day_of_week  str    nullable
#   bias         str    nullable  (user-confirmed via Save Labels)

import datetime as dt
import json
import math
from typing import Optional, Tuple

import pandas as pd


def _safe_float(value) -> float:
    """Return float(value), or 0.0 for NaN / inf / None / type errors."""
    try:
        f = float(value)
        return 0.0 if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return 0.0


def _outcome_masks(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Return (win_mask, loss_mask, be_mask) boolean Series.

    Primary source: result column (case-insensitive "win" / "loss" / "breakeven").
    Fallback: pnl column (>0 / <0 / ==0) when result column is absent.

    This is the single canonical rule for outcome classification across all metrics.
    PnL is used only for money metrics (avg_win, avg_loss, total_pnl, etc.).
    """
    if "result" in df.columns:
        r = df["result"].fillna("").str.lower()
        return (r == "win"), (r == "loss"), (r == "breakeven")

    if "pnl" in df.columns:
        pnl = pd.to_numeric(df["pnl"], errors="coerce")
        return (pnl > 0), (pnl < 0), (pnl == 0)

    false_s = pd.Series([False] * len(df), index=df.index)
    return false_s, false_s, false_s


_EMPTY_METRICS: dict = {
    "total_trades": 0,
    "wins": 0,
    "losses": 0,
    "breakevens": 0,
    "win_rate": 0.0,
    "loss_rate": 0.0,
    "total_pnl": 0.0,
    "avg_win": 0.0,
    "avg_loss": 0.0,
    "avg_rr_realized": 0.0,
    "profit_factor": 0.0,
    "best_trade": 0.0,
    "worst_trade": 0.0,
}


def compute_basic_metrics(df: pd.DataFrame) -> dict:
    """
    Compute performance metrics from a DataFrame of trades.

    Outcome classification (wins/losses/breakevens/rates) uses _outcome_masks():
    result string primary, pnl fallback. Money metrics always use pnl column.
    All returned floats are guaranteed non-NaN.
    """
    if df is None or df.empty or "pnl" not in df.columns:
        return dict(_EMPTY_METRICS)

    total = len(df)
    pnl = pd.to_numeric(df["pnl"], errors="coerce")

    win_mask, loss_mask, be_mask = _outcome_masks(df)

    wins = int(win_mask.sum())
    losses = int(loss_mask.sum())
    breakevens = int(be_mask.sum())

    win_pnls = pnl[win_mask]
    loss_pnls = pnl[loss_mask]

    sum_wins = win_pnls.sum()
    sum_losses = loss_pnls.sum()

    profit_factor = (
        _safe_float(sum_wins / abs(sum_losses)) if abs(sum_losses) > 0 else 0.0
    )

    avg_win = _safe_float(win_pnls.mean()) if wins > 0 else 0.0
    avg_loss = _safe_float(loss_pnls.mean()) if losses > 0 else 0.0

    avg_rr = 0.0
    if "rr_realized" in df.columns:
        rr = pd.to_numeric(df["rr_realized"], errors="coerce").dropna()
        avg_rr = _safe_float(rr.mean()) if not rr.empty else 0.0

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "breakevens": breakevens,
        "win_rate": _safe_float(wins / total) if total > 0 else 0.0,
        "loss_rate": _safe_float(losses / total) if total > 0 else 0.0,
        "total_pnl": _safe_float(pnl.sum()),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "avg_rr_realized": avg_rr,
        "profit_factor": profit_factor,
        "best_trade": _safe_float(pnl.max()),
        "worst_trade": _safe_float(pnl.min()),
    }


def compute_equity_curve(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a cumulative P/L curve from a trades DataFrame.

    Returns columns: trade_date, pnl, cumulative_pnl — sorted ascending by date.
    NaN pnl values are treated as 0 so they don't break the running sum.
    """
    empty = pd.DataFrame(columns=["trade_date", "pnl", "cumulative_pnl"])

    if df is None or df.empty:
        return empty
    if "pnl" not in df.columns or "trade_date" not in df.columns:
        return empty

    curve = df[["trade_date", "pnl"]].copy()
    curve["pnl"] = pd.to_numeric(curve["pnl"], errors="coerce").fillna(0.0)
    curve = curve.sort_values("trade_date", ascending=True).reset_index(drop=True)
    curve["cumulative_pnl"] = curve["pnl"].cumsum()

    return curve[["trade_date", "pnl", "cumulative_pnl"]]


def get_last_n_trades(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Return the n most recent trades sorted by trade_date descending."""
    if df is None or df.empty:
        return pd.DataFrame()
    if "trade_date" not in df.columns:
        return df.head(n)

    return df.sort_values("trade_date", ascending=False).head(n).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Week 4 additions
# ---------------------------------------------------------------------------


def compute_expectancy(metrics: dict) -> float:
    """
    Average expected $ per trade for the strategy.

    Formula: expectancy = win_rate × avg_win + loss_rate × avg_loss

    avg_loss is already a negative float (mean of losing PnL values), so the
    loss side naturally subtracts from the win side.

    Input: dict from compute_basic_metrics() — needs win_rate, loss_rate,
           avg_win, avg_loss, total_trades.
    Returns 0.0 when total_trades == 0 or any required key is missing.
    Never returns NaN.
    """
    required = {"win_rate", "loss_rate", "avg_win", "avg_loss", "total_trades"}
    if not required.issubset(metrics):
        return 0.0
    if metrics.get("total_trades", 0) == 0:
        return 0.0

    win_rate = _safe_float(metrics["win_rate"])
    loss_rate = _safe_float(metrics["loss_rate"])
    avg_win = _safe_float(metrics["avg_win"])
    avg_loss = _safe_float(metrics["avg_loss"])

    return _safe_float(win_rate * avg_win + loss_rate * avg_loss)


def compute_max_drawdown(equity_curve: pd.DataFrame) -> float:
    """
    Maximum peak-to-trough drawdown on the running equity curve.

    Input: DataFrame from compute_equity_curve() with a cumulative_pnl column.
    Returns the drawdown as a positive float (0.0 for flat or monotonically
    rising curves). Never returns NaN.

    Formula: max(rolling_peak - cumulative_pnl)
    where rolling_peak = cumulative_pnl.cummax()
    """
    if equity_curve is None or equity_curve.empty:
        return 0.0
    if "cumulative_pnl" not in equity_curve.columns:
        return 0.0
    if len(equity_curve) < 2:
        return 0.0

    curve = pd.to_numeric(equity_curve["cumulative_pnl"], errors="coerce").dropna()
    if curve.empty:
        return 0.0

    rolling_peak = curve.cummax()
    drawdown = rolling_peak - curve
    return _safe_float(drawdown.max())


def compute_profit_factor_raw(df: pd.DataFrame) -> float:
    """
    Profit factor from a trades DataFrame, preserving inf for all-wins periods.

    Unlike compute_basic_metrics(), returns float("inf") when wins > 0 but no
    losses exist — useful for KPI cards and gauges that can display "∞".

    Returns:
      float("inf")  — wins > 0 and no losses
      numeric ratio — wins and losses both present
      0.0           — no trades, no wins, or pnl column absent
    """
    if df is None or df.empty or "pnl" not in df.columns:
        return 0.0

    pnl = pd.to_numeric(df["pnl"], errors="coerce")
    sum_wins = _safe_float(pnl[pnl > 0].sum())
    sum_losses = abs(_safe_float(pnl[pnl < 0].sum()))

    if sum_losses > 0:
        return sum_wins / sum_losses
    if sum_wins > 0:
        return float("inf")
    return 0.0


def compute_streaks(df: pd.DataFrame) -> dict:
    """
    Compute win/loss streaks from the trades DataFrame.

    Requires columns: trade_date, result.
    result values are normalized to lowercase; "win" and "loss" extend streaks;
    any other value (including "breakeven") resets the streak to 0.

    Returns:
        current_streak: int  — positive = active win streak, negative = active loss streak
        max_win_streak:  int  — longest win streak observed
        max_loss_streak: int  — longest loss streak observed (positive magnitude)
        streak_type:     str  — "win" | "loss" | "none"
    """
    empty = {
        "current_streak": 0,
        "max_win_streak": 0,
        "max_loss_streak": 0,
        "streak_type": "none",
    }

    if df is None or df.empty:
        return empty
    if "result" not in df.columns or "trade_date" not in df.columns:
        return empty

    valid = df.dropna(subset=["trade_date", "result"]).copy()
    valid = valid.sort_values("trade_date", ascending=True).reset_index(drop=True)

    if valid.empty:
        return empty

    current = 0
    max_win = 0
    max_loss = 0

    for r in valid["result"].str.lower():
        if r == "win":
            current = current + 1 if current > 0 else 1
        elif r == "loss":
            current = current - 1 if current < 0 else -1
        else:
            current = 0

        if current > max_win:
            max_win = current
        if -current > max_loss:
            max_loss = -current

    if current > 0:
        streak_type = "win"
    elif current < 0:
        streak_type = "loss"
    else:
        streak_type = "none"

    return {
        "current_streak": current,
        "max_win_streak": max_win,
        "max_loss_streak": max_loss,
        "streak_type": streak_type,
    }


equity_curve_series = compute_equity_curve  # public alias — same behavior, cleaner name for analytics callers

_BREAKDOWN_COLS = [
    "trades",
    "wins",
    "losses",
    "breakevens",
    "win_rate",
    "avg_pnl",
    "total_pnl",
]


def compute_breakdown(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """
    Group trades by a column and compute per-group performance metrics.

    Useful group-by values: "session", "asset", "day_of_week", "bias".
    Any column present in the DataFrame is valid.

    Win/loss classification uses _outcome_masks() (result string primary, pnl fallback).
    Money metrics (avg_pnl, total_pnl) use the pnl column.
    NaN pnl rows count toward trade totals but are excluded from pnl averages.

    Returns DataFrame sorted by total_pnl descending with columns:
        [by], trades, wins, losses, breakevens, win_rate, avg_pnl, total_pnl

    Returns an empty DataFrame with correct columns if `by` is not in df or df is empty.
    """
    empty = pd.DataFrame(columns=[by] + _BREAKDOWN_COLS)

    if df is None or df.empty or by not in df.columns:
        return empty

    work = df.copy()
    work["_count"] = 1
    work["_pnl"] = (
        pd.to_numeric(df["pnl"], errors="coerce")
        if "pnl" in df.columns
        else pd.Series([float("nan")] * len(df), index=df.index)
    )

    win_mask, loss_mask, be_mask = _outcome_masks(df)
    work["_win"] = win_mask.astype(int)
    work["_loss"] = loss_mask.astype(int)
    work["_be"] = be_mask.astype(int)

    grouped = (
        work.groupby(by, dropna=True)
        .agg(
            trades=("_count", "sum"),
            wins=("_win", "sum"),
            losses=("_loss", "sum"),
            breakevens=("_be", "sum"),
            total_pnl=("_pnl", "sum"),
            avg_pnl=("_pnl", "mean"),
        )
        .reset_index()
    )

    grouped["win_rate"] = grouped.apply(
        lambda row: (
            _safe_float(row["wins"] / row["trades"]) if row["trades"] > 0 else 0.0
        ),
        axis=1,
    )
    grouped["total_pnl"] = grouped["total_pnl"].apply(_safe_float)
    grouped["avg_pnl"] = grouped["avg_pnl"].apply(_safe_float)

    return (
        grouped[[by] + _BREAKDOWN_COLS]
        .sort_values("total_pnl", ascending=False)
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Week 4 Day 2 — time-series and distribution helpers
# ---------------------------------------------------------------------------


def daily_pnl(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate P&L per calendar day.

    Rows with a null trade_date are dropped before grouping so they don't
    create a spurious NaT bucket. No date reindexing — gaps between trading
    days remain gaps.

    Returns columns: trade_date, daily_pnl — sorted ascending.
    Returns an empty DataFrame with those columns on empty input.
    """
    empty = pd.DataFrame(columns=["trade_date", "daily_pnl"])

    if trades is None or trades.empty:
        return empty
    if "trade_date" not in trades.columns or "pnl" not in trades.columns:
        return empty

    work = trades[["trade_date", "pnl"]].copy()
    work = work.dropna(subset=["trade_date"])
    if work.empty:
        return empty

    work["pnl"] = pd.to_numeric(work["pnl"], errors="coerce").fillna(0.0)
    grouped = (
        work.groupby("trade_date", sort=True)["pnl"]
        .sum()
        .reset_index()
        .rename(columns={"pnl": "daily_pnl"})
    )
    grouped["daily_pnl"] = grouped["daily_pnl"].apply(_safe_float)
    return grouped[["trade_date", "daily_pnl"]]


def drawdown_series(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Per-trade drawdown series relative to the running equity peak.

    Calls equity_curve_series() to get cumulative_pnl, then computes:
        running_peak = cumulative_pnl.cummax()
        drawdown     = cumulative_pnl - running_peak   (always ≤ 0)

    drawdown is negative-or-zero: a value of -50 means the equity is 50 below
    its previous high. abs(drawdown.min()) gives the maximum drawdown magnitude,
    consistent with compute_max_drawdown().

    Returns columns: trade_date, cumulative_pnl, running_peak, drawdown.
    Returns an empty DataFrame with those columns on empty input.
    """
    _cols = ["trade_date", "cumulative_pnl", "running_peak", "drawdown"]
    empty = pd.DataFrame(columns=_cols)

    curve = equity_curve_series(trades)
    if curve.empty:
        return empty

    result = curve[["trade_date", "cumulative_pnl"]].copy()
    result["running_peak"] = result["cumulative_pnl"].cummax()
    result["drawdown"] = result["cumulative_pnl"] - result["running_peak"]
    return result[_cols].reset_index(drop=True)


def r_multiple_distribution(trades: pd.DataFrame, bins: int = 20) -> pd.DataFrame:
    """
    Histogram of realized R-multiples (rr_realized column).

    NaN values are dropped before binning. Returns a DataFrame suitable for a
    Plotly bar/histogram chart with columns: bin_left, bin_right, count.

    Edge cases:
    - Empty or all-NaN input → empty DataFrame with those columns.
    - All identical values → single bin (avoids pd.cut ValueError).
    - bins is capped at len(rr) to prevent empty bins.
    """
    empty = pd.DataFrame(columns=["bin_left", "bin_right", "count"])

    if trades is None or trades.empty or "rr_realized" not in trades.columns:
        return empty

    rr = pd.to_numeric(trades["rr_realized"], errors="coerce").dropna()
    if rr.empty:
        return empty

    # All values identical — pd.cut would error; return single bin
    if rr.min() == rr.max():
        return pd.DataFrame(
            {
                "bin_left": [rr.min()],
                "bin_right": [rr.max()],
                "count": [len(rr)],
            }
        )

    n_bins = min(bins, len(rr))
    binned = pd.cut(rr, bins=n_bins, include_lowest=True)
    counts = binned.value_counts().sort_index()

    return pd.DataFrame(
        {
            "bin_left": [iv.left for iv in counts.index],
            "bin_right": [iv.right for iv in counts.index],
            "count": counts.values,
        }
    )


# ---------------------------------------------------------------------------
# Week 4 Day 3 — group-by breakdown helpers
# ---------------------------------------------------------------------------

DOW_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

_GROUP_RR_COLS = [
    "trades",
    "wins",
    "losses",
    "breakevens",
    "win_rate",
    "avg_rr_realized",
    "total_pnl",
]


def _group_with_rr(
    df: pd.DataFrame,
    by: str,
    sort_by: Optional[str] = "total_pnl",
    sort_ascending: bool = False,
) -> pd.DataFrame:
    """
    Core groupby engine shared by the by_* functions.

    Excludes rows where the group-by column is null. Outcome classification
    uses _outcome_masks() (result string primary, pnl fallback). avg_rr_realized
    uses pandas skipna mean.

    Returns: [by, trades, wins, losses, breakevens, win_rate, avg_rr_realized, total_pnl]
    Sorted by sort_by (skipped when None). Empty DataFrame with correct columns on
    empty/missing input.
    """
    _cols = [by] + _GROUP_RR_COLS
    empty = pd.DataFrame(columns=_cols)

    if df is None or df.empty or by not in df.columns:
        return empty

    work = df.dropna(subset=[by]).copy()
    if work.empty:
        return empty

    work["_count"] = 1
    work["_pnl"] = (
        pd.to_numeric(work["pnl"], errors="coerce")
        if "pnl" in work.columns
        else pd.Series([float("nan")] * len(work), index=work.index)
    )
    work["_rr"] = (
        pd.to_numeric(work["rr_realized"], errors="coerce")
        if "rr_realized" in work.columns
        else pd.Series([float("nan")] * len(work), index=work.index)
    )

    win_mask, loss_mask, be_mask = _outcome_masks(work)
    work["_win"] = win_mask.astype(int)
    work["_loss"] = loss_mask.astype(int)
    work["_be"] = be_mask.astype(int)

    grouped = (
        work.groupby(by, dropna=True)
        .agg(
            trades=("_count", "sum"),
            wins=("_win", "sum"),
            losses=("_loss", "sum"),
            breakevens=("_be", "sum"),
            total_pnl=("_pnl", "sum"),
            avg_rr_realized=("_rr", "mean"),
        )
        .reset_index()
    )

    grouped["win_rate"] = grouped.apply(
        lambda row: (
            _safe_float(row["wins"] / row["trades"]) if row["trades"] > 0 else 0.0
        ),
        axis=1,
    )
    grouped["total_pnl"] = grouped["total_pnl"].apply(_safe_float)
    grouped["avg_rr_realized"] = grouped["avg_rr_realized"].apply(_safe_float)

    if sort_by and sort_by in grouped.columns:
        grouped = grouped.sort_values(sort_by, ascending=sort_ascending).reset_index(
            drop=True
        )

    return grouped[_cols]


def _group_with_profit_factor(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """
    Groupby engine for by_strategy / by_timeframe / by_asset.

    Calls _group_with_rr, then appends profit_factor per group.

    profit_factor may be float("inf") when a group has wins but no losses.
    _safe_float() is intentionally NOT applied here. Callers must handle inf.

    Returns: [by, trades, wins, losses, breakevens, win_rate, total_pnl, profit_factor]
    sorted by total_pnl descending.
    """
    _cols = [
        by,
        "trades",
        "wins",
        "losses",
        "breakevens",
        "win_rate",
        "total_pnl",
        "profit_factor",
    ]
    empty = pd.DataFrame(columns=_cols)

    base = _group_with_rr(df, by=by)
    if base.empty:
        return empty

    if df is not None and not df.empty and "pnl" in df.columns and by in df.columns:
        work = df.dropna(subset=[by]).copy()
        pnl = pd.to_numeric(work["pnl"], errors="coerce").fillna(0.0)
        work["_win_pnl"] = pnl.clip(lower=0)
        work["_loss_pnl"] = pnl.clip(upper=0)

        pf_groups = (
            work.groupby(by, dropna=True)
            .agg(sum_wins=("_win_pnl", "sum"), sum_losses=("_loss_pnl", "sum"))
            .reset_index()
        )

        def _pf(row: pd.Series) -> float:
            sw = _safe_float(row["sum_wins"])
            sl = abs(_safe_float(row["sum_losses"]))
            if sl > 0:
                return sw / sl
            if sw > 0:
                return float("inf")
            return 0.0

        pf_groups["profit_factor"] = pf_groups.apply(_pf, axis=1)
        base = base.merge(pf_groups[[by, "profit_factor"]], on=by, how="left")
        base["profit_factor"] = base["profit_factor"].fillna(0.0)
    else:
        base["profit_factor"] = 0.0

    return base[_cols].sort_values("total_pnl", ascending=False).reset_index(drop=True)


def by_day_of_week(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Performance breakdown by day of week (Monday → Sunday).

    day_of_week values must be full English names from strftime("%A") —
    "Monday", "Tuesday", etc. Rows with null day_of_week are excluded.

    Returns columns: day_of_week, trades, wins, losses, breakevens, win_rate,
    avg_rr_realized, total_pnl — sorted chronologically Mon → Sun.
    Returns an empty DataFrame with those columns on empty input.
    """
    result = _group_with_rr(trades, by="day_of_week", sort_by=None)
    if result.empty:
        return result

    result["day_of_week"] = pd.Categorical(
        result["day_of_week"], categories=DOW_ORDER, ordered=True
    )
    return result.sort_values("day_of_week").reset_index(drop=True)


def by_session(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Performance breakdown by trading session (e.g., "London", "NY AM").

    Rows with null session are excluded.

    Returns columns: session, trades, wins, losses, breakevens, win_rate,
    avg_rr_realized, total_pnl — sorted by total_pnl descending.
    Returns an empty DataFrame with those columns on empty input.
    """
    return _group_with_rr(trades, by="session")


def by_strategy(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Performance breakdown by strategy name (strategy_used column).

    Rows with null strategy_used are excluded — unlabeled trades have no strategy
    assignment and would pollute per-strategy metrics.

    profit_factor may be float("inf") when a group has wins but no losses.
    _safe_float() is intentionally NOT applied here. Callers must handle inf.

    Returns columns: strategy_used, trades, wins, losses, breakevens, win_rate,
    total_pnl, profit_factor — sorted by total_pnl descending.
    Returns an empty DataFrame with those columns on empty input.
    """
    return _group_with_profit_factor(trades, "strategy_used")


def by_timeframe(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Performance breakdown by chart timeframe (e.g., "5m", "15m", "1H").

    Rows with null timeframe are excluded.

    profit_factor may be float("inf") when a group has wins but no losses.
    _safe_float() is intentionally NOT applied here. Callers must handle inf.

    Returns columns: timeframe, trades, wins, losses, breakevens, win_rate,
    total_pnl, profit_factor — sorted by total_pnl descending.
    Returns an empty DataFrame with those columns on empty input.
    """
    return _group_with_profit_factor(trades, "timeframe")


def by_asset(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Performance breakdown by traded asset (e.g., "NQ", "ES", "BTC").

    Rows with null asset are excluded.

    profit_factor may be float("inf") when a group has wins but no losses.
    _safe_float() is intentionally NOT applied here. Callers must handle inf.

    Returns columns: asset, trades, wins, losses, breakevens, win_rate,
    total_pnl, profit_factor — sorted by total_pnl descending.
    Returns an empty DataFrame with those columns on empty input.
    """
    return _group_with_profit_factor(trades, "asset")


def by_setup_type(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Win/Loss/Breakeven composition by setup type.

    No PnL or R-multiple metrics — this function powers a stacked bar chart
    showing outcome distribution for each setup. Rows with null setup_type
    are excluded.

    Returns columns: setup_type, trades, wins, losses, breakevens — sorted by
    trades descending. Returns an empty DataFrame with those columns on empty input.
    """
    _cols = ["setup_type", "trades", "wins", "losses", "breakevens"]
    empty = pd.DataFrame(columns=_cols)

    if trades is None or trades.empty or "setup_type" not in trades.columns:
        return empty

    work = trades.dropna(subset=["setup_type"]).copy()
    if work.empty:
        return empty

    work["_count"] = 1
    win_mask, loss_mask, be_mask = _outcome_masks(work)
    work["_win"] = win_mask.astype(int)
    work["_loss"] = loss_mask.astype(int)
    work["_be"] = be_mask.astype(int)

    grouped = (
        work.groupby("setup_type", dropna=True)
        .agg(
            trades=("_count", "sum"),
            wins=("_win", "sum"),
            losses=("_loss", "sum"),
            breakevens=("_be", "sum"),
        )
        .reset_index()
    )

    return grouped[_cols].sort_values("trades", ascending=False).reset_index(drop=True)


def emotion_vs_rr(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Average realized R-multiple grouped by pre-trade emotional state.

    PnL is excluded — this chart highlights how emotional state correlates with
    trade quality in R terms, not dollar terms. Rows with null emotions_before
    are excluded from grouping. NaN rr_realized values are excluded from the
    per-group mean (pandas skipna default) but still count toward trades.

    Returns columns: emotions_before, trades, avg_rr_realized — sorted by
    avg_rr_realized descending. Returns an empty DataFrame with those columns
    on empty input.
    """
    _cols = ["emotions_before", "trades", "avg_rr_realized"]
    empty = pd.DataFrame(columns=_cols)

    if trades is None or trades.empty or "emotions_before" not in trades.columns:
        return empty

    work = trades.dropna(subset=["emotions_before"]).copy()
    if work.empty:
        return empty

    work["_count"] = 1
    work["_rr"] = (
        pd.to_numeric(work["rr_realized"], errors="coerce")
        if "rr_realized" in work.columns
        else pd.Series([float("nan")] * len(work), index=work.index)
    )

    grouped = (
        work.groupby("emotions_before", dropna=True)
        .agg(
            trades=("_count", "sum"),
            avg_rr_realized=("_rr", "mean"),
        )
        .reset_index()
    )

    grouped["avg_rr_realized"] = grouped["avg_rr_realized"].apply(_safe_float)

    return (
        grouped[_cols]
        .sort_values("avg_rr_realized", ascending=False)
        .reset_index(drop=True)
    )


def by_hour_of_day(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Performance by hour of day (integer 0–23).

    Requires an 'hour_of_day' integer column in the DataFrame. The Trade ORM
    currently has no time field (only trade_date as an ISO date string with no
    clock component). Callers must derive hour_of_day from a future time column
    before calling this function.

    If 'hour_of_day' is absent, returns an empty DataFrame with the correct
    columns. This is forward-compatible: add a time column, derive hour_of_day,
    and this function will work without changes here.

    Returns columns: hour_of_day, trades, total_pnl, avg_rr_realized — sorted
    by hour_of_day ascending.
    """
    _cols = ["hour_of_day", "trades", "total_pnl", "avg_rr_realized"]
    empty = pd.DataFrame(columns=_cols)

    if trades is None or trades.empty or "hour_of_day" not in trades.columns:
        return empty

    work = trades.dropna(subset=["hour_of_day"]).copy()
    if work.empty:
        return empty

    work["_count"] = 1
    work["_pnl"] = (
        pd.to_numeric(work["pnl"], errors="coerce")
        if "pnl" in work.columns
        else pd.Series([float("nan")] * len(work), index=work.index)
    )
    work["_rr"] = (
        pd.to_numeric(work["rr_realized"], errors="coerce")
        if "rr_realized" in work.columns
        else pd.Series([float("nan")] * len(work), index=work.index)
    )

    grouped = (
        work.groupby("hour_of_day", dropna=True)
        .agg(
            trades=("_count", "sum"),
            total_pnl=("_pnl", "sum"),
            avg_rr_realized=("_rr", "mean"),
        )
        .reset_index()
    )

    grouped["total_pnl"] = grouped["total_pnl"].apply(_safe_float)
    grouped["avg_rr_realized"] = grouped["avg_rr_realized"].apply(_safe_float)

    return (
        grouped[_cols].sort_values("hour_of_day", ascending=True).reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Week 5 Phase 2 — SMC/ICT killzone analytics + calendar
# ---------------------------------------------------------------------------

# Chronological display order for killzones (matches services/sessions.py).
KILLZONE_ORDER = ["asia", "london_open", "ny_am", "ny_lunch", "ny_pm", "off_session"]

_KILLZONE_COLS = [
    "killzone",
    "trades",
    "wins",
    "losses",
    "breakevens",
    "win_rate",
    "avg_rr_realized",
    "profit_factor",
    "total_pnl",
]


def killzone_performance(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Per-killzone performance: trades, win_rate, avg_rr_realized, profit_factor, total_pnl.

    Combines the avg-R engine (_group_with_rr) with per-group profit_factor
    (_group_with_profit_factor) so a single row carries both. profit_factor may
    be float("inf") for a killzone with wins but no losses — callers must handle it.

    Rows with null killzone are excluded. Sorted in chronological killzone order
    (asia → london_open → ny_am → ny_lunch → ny_pm → off_session); any unknown
    killzone sorts last by total_pnl descending. Empty input → empty frame with
    the correct columns.
    """
    empty = pd.DataFrame(columns=_KILLZONE_COLS)

    rr = _group_with_rr(trades, by="killzone", sort_by=None)
    if rr.empty:
        return empty

    pf = _group_with_profit_factor(trades, "killzone")[["killzone", "profit_factor"]]
    merged = rr.merge(pf, on="killzone", how="left")
    merged["profit_factor"] = merged["profit_factor"].fillna(0.0)

    order_map = {kz: i for i, kz in enumerate(KILLZONE_ORDER)}
    merged["_ord"] = merged["killzone"].map(
        lambda kz: order_map.get(kz, len(KILLZONE_ORDER))
    )
    merged = (
        merged.sort_values(["_ord", "total_pnl"], ascending=[True, False])
        .drop(columns="_ord")
        .reset_index(drop=True)
    )
    return merged[_KILLZONE_COLS]


def confirmation_model_performance(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Performance breakdown by confirmation_model (e.g., "BOS", "FVG Fill").

    Rows with null confirmation_model are excluded. profit_factor may be
    float("inf"); callers must handle it. Sorted by total_pnl descending.

    Returns columns: confirmation_model, trades, wins, losses, breakevens,
    win_rate, total_pnl, profit_factor. Empty input → empty frame.
    """
    return _group_with_profit_factor(trades, "confirmation_model")


def _parse_mistake_tags(raw) -> list:
    """Parse a mistake_tags cell (JSON list string, list, or null) into a list of strings."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw if t]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            val = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            return []
        if isinstance(val, list):
            return [str(t) for t in val if t]
    return []


_MISTAKE_COLS = ["mistake_tag", "count", "total_pnl", "avg_pnl"]


def mistake_frequency(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Frequency and P&L impact of each mistake tag.

    mistake_tags is a JSON list column (e.g. '["FOMO", "Late Entry"]'). Each tag
    on a trade is attributed that trade's full pnl, so total_pnl per tag is the
    summed pnl of every trade carrying it (tags on the same trade share its pnl).

    Returns columns: mistake_tag, count, total_pnl, avg_pnl — sorted by count
    descending. Empty / all-empty / malformed input → empty frame.
    """
    empty = pd.DataFrame(columns=_MISTAKE_COLS)

    if trades is None or trades.empty or "mistake_tags" not in trades.columns:
        return empty

    pnl_series = (
        pd.to_numeric(trades["pnl"], errors="coerce")
        if "pnl" in trades.columns
        else None
    )

    rows = []
    for idx, raw in trades["mistake_tags"].items():
        tags = _parse_mistake_tags(raw)
        if not tags:
            continue
        pnl = _safe_float(pnl_series[idx]) if pnl_series is not None else 0.0
        for tag in tags:
            rows.append((tag, pnl))

    if not rows:
        return empty

    exploded = pd.DataFrame(rows, columns=["mistake_tag", "_pnl"])
    grouped = (
        exploded.groupby("mistake_tag")
        .agg(
            count=("_pnl", "size"), total_pnl=("_pnl", "sum"), avg_pnl=("_pnl", "mean")
        )
        .reset_index()
    )
    grouped["total_pnl"] = grouped["total_pnl"].apply(_safe_float)
    grouped["avg_pnl"] = grouped["avg_pnl"].apply(_safe_float)

    return (
        grouped[_MISTAKE_COLS]
        .sort_values(["count", "total_pnl"], ascending=[False, True])
        .reset_index(drop=True)
    )


def total_edge_leak(trades: pd.DataFrame) -> float:
    """
    Net P&L of trades where the trader broke their own process.

    A trade leaks edge when followed_rules is explicitly False (0) OR it carries
    one or more mistake_tags. Each qualifying trade is counted exactly once, even
    when both signals are present.

    The sign is preserved: a negative result is the usual "leak" (rule-breaking
    cost money); a positive result means rule-breaking trades happened to net a
    profit (lucky, not repeatable). A None/NaN followed_rules with no mistake tags
    is treated as "not recorded" and excluded.

    Returns 0.0 on empty input or when neither signal column is present.
    """
    if trades is None or trades.empty or "pnl" not in trades.columns:
        return 0.0

    has_followed = "followed_rules" in trades.columns
    has_mistakes = "mistake_tags" in trades.columns
    if not has_followed and not has_mistakes:
        return 0.0

    pnl = pd.to_numeric(trades["pnl"], errors="coerce").fillna(0.0)
    leak_mask = pd.Series([False] * len(trades), index=trades.index)

    if has_followed:
        fr = pd.to_numeric(trades["followed_rules"], errors="coerce")
        leak_mask = leak_mask | (fr == 0)

    if has_mistakes:
        has_tag = trades["mistake_tags"].apply(
            lambda raw: len(_parse_mistake_tags(raw)) > 0
        )
        leak_mask = leak_mask | has_tag

    return _safe_float(pnl[leak_mask].sum())


# Letter grade → numeric (F..A spans a 0..4 range used for the trend component).
_GRADE_TO_NUM = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
_GRADE_RANGE = 4

# consistency_score component weights — must sum to 1.0.
_CONSISTENCY_WEIGHTS = {
    "rule_adherence": 0.40,
    "mistake_cleanliness": 0.35,
    "grade_trend": 0.25,
}
_MIN_TRADES_FOR_CONSISTENCY = 5
_GRADE_TREND_WINDOW = 20


def _is_followed(value) -> bool:
    """True only when followed_rules is explicitly truthy (1 / True)."""
    if value is True:
        return True
    try:
        return int(value) == 1
    except (TypeError, ValueError):
        return False


def _grade_trend_component(trades: pd.DataFrame) -> float:
    """
    Normalised grade trend (0..1) over the last _GRADE_TREND_WINDOW graded trades.

    Prefers user_grade, falling back to ai_grade. Letters map A..F → 4..0. The
    least-squares slope is projected across the window (slope × (n-1)) and scaled
    by the full grade range into 0..1, where 0.5 is "no trend". With fewer than two
    graded trades there is no trend signal, so it returns the neutral 0.5.
    """
    col = None
    for candidate in ("user_grade", "ai_grade"):
        if candidate in trades.columns:
            col = candidate
            break
    if col is None:
        return 0.5

    work = trades.copy()
    if "trade_date" in work.columns:
        work = work.sort_values("trade_date")

    nums = [
        _GRADE_TO_NUM[g]
        for g in work[col].tolist()
        if isinstance(g, str) and g in _GRADE_TO_NUM
    ]
    nums = nums[-_GRADE_TREND_WINDOW:]
    n = len(nums)
    if n < 2:
        return 0.5

    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(nums) / n
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        return 0.5
    slope = sum((xs[i] - x_mean) * (nums[i] - y_mean) for i in range(n)) / denom

    projected = slope * (n - 1)  # total grade change predicted across the window
    normalised = 0.5 + projected / (2 * _GRADE_RANGE)
    return max(0.0, min(1.0, normalised))


def consistency_score(trades: pd.DataFrame) -> float:
    """
    A 0–100 process-consistency score blending three components.

    Weights (documented contract):
      • Rule adherence       40%  — share of trades with followed_rules truthy.
      • Mistake cleanliness  35%  — 1 − (trades with any mistake_tags / total).
      • Grade trend          25%  — slope of numeric grade over the last 20 trades,
                                    normalised to 0..1 (0.5 = flat / no signal).

    Returns 0.0 when there are fewer than 5 trades (too little signal to score).
    Result is rounded to one decimal place.
    """
    if trades is None or len(trades) < _MIN_TRADES_FOR_CONSISTENCY:
        return 0.0

    total = len(trades)

    if "followed_rules" in trades.columns:
        followed = trades["followed_rules"].apply(_is_followed).sum()
        rule_adherence = followed / total
    else:
        rule_adherence = 0.0

    if "mistake_tags" in trades.columns:
        dirty = (
            trades["mistake_tags"]
            .apply(lambda raw: len(_parse_mistake_tags(raw)) > 0)
            .sum()
        )
        mistake_cleanliness = 1.0 - (dirty / total)
    else:
        mistake_cleanliness = 1.0  # no recorded mistakes → treated as clean

    grade_trend = _grade_trend_component(trades)

    score = 100.0 * (
        _CONSISTENCY_WEIGHTS["rule_adherence"] * rule_adherence
        + _CONSISTENCY_WEIGHTS["mistake_cleanliness"] * mistake_cleanliness
        + _CONSISTENCY_WEIGHTS["grade_trend"] * grade_trend
    )
    return round(_safe_float(score), 1)


_CALENDAR_COLS = ["trade_date", "day", "net_pnl", "trades", "wins", "losses"]


def calendar_daily_pnl(trades: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    """
    Per-day net P&L for a single calendar month — powers the calendar heatmap.

    Filters to trades whose ISO trade_date falls in the given year/month, then
    aggregates per day. Days with no trades are simply absent (the page maps the
    present days onto a month grid).

    Returns columns: trade_date, day (int 1–31), net_pnl, trades, wins, losses —
    sorted by day ascending. Empty / no-trades-this-month input → empty frame.
    """
    empty = pd.DataFrame(columns=_CALENDAR_COLS)

    if (
        trades is None
        or trades.empty
        or "trade_date" not in trades.columns
        or "pnl" not in trades.columns
    ):
        return empty

    prefix = f"{year:04d}-{month:02d}"
    work = trades.dropna(subset=["trade_date"]).copy()
    work = work[work["trade_date"].astype(str).str.startswith(prefix)]
    if work.empty:
        return empty

    work["_pnl"] = pd.to_numeric(work["pnl"], errors="coerce").fillna(0.0)
    win_mask, loss_mask, _ = _outcome_masks(work)
    work["_win"] = win_mask.astype(int)
    work["_loss"] = loss_mask.astype(int)
    work["_count"] = 1

    grouped = (
        work.groupby("trade_date")
        .agg(
            net_pnl=("_pnl", "sum"),
            trades=("_count", "sum"),
            wins=("_win", "sum"),
            losses=("_loss", "sum"),
        )
        .reset_index()
    )
    grouped["net_pnl"] = grouped["net_pnl"].apply(_safe_float)
    grouped["day"] = grouped["trade_date"].astype(str).str.slice(8, 10).astype(int)

    return grouped[_CALENDAR_COLS].sort_values("day").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Dashboard helpers (Week 6 — Ship Week)
# ---------------------------------------------------------------------------

# Full grade ranking incl. +/- modifiers for Trade-of-the-Week selection.
_GRADE_RANK = {
    "A+": 12,
    "A": 11,
    "A-": 10,
    "B+": 9,
    "B": 8,
    "B-": 7,
    "C+": 6,
    "C": 5,
    "C-": 4,
    "D+": 3,
    "D": 2,
    "D-": 1,
    "F": 0,
}


def _coerce_date(value) -> Optional[dt.date]:
    """Best-effort convert str/date/datetime to a date; None on failure."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _best_by_grade(df: pd.DataFrame, grade_col: str):
    """Return the row with the highest grade in grade_col, tie-broken by pnl.
    None when no row has a recognised grade."""
    if grade_col not in df.columns:
        return None
    sub = df[df[grade_col].notna() & (df[grade_col].astype(str).str.strip() != "")]
    if sub.empty:
        return None
    sub = sub.copy()
    sub["_rank"] = sub[grade_col].map(lambda g: _GRADE_RANK.get(str(g).strip(), -1))
    sub = sub[sub["_rank"] >= 0]
    if sub.empty:
        return None
    if "pnl" in sub.columns:
        sub["_pnl_sort"] = pd.to_numeric(sub["pnl"], errors="coerce").fillna(
            float("-inf")
        )
    else:
        sub["_pnl_sort"] = 0.0
    sub = sub.sort_values(["_rank", "_pnl_sort"], ascending=[False, False])
    return sub.iloc[0]


def trade_of_the_week(df: pd.DataFrame) -> Optional[dict]:
    """Highest-graded trade for the 'Trade of the Week' card.

    Prefers ai_grade; falls back to user_grade when no trade has an ai_grade;
    returns None when neither grade is set on any trade (caller renders an empty
    state). Ties on grade are broken by higher pnl. Returns a plain dict with the
    chosen 'grade' and 'grade_source' ('ai' | 'user') added.
    """
    if df is None or df.empty:
        return None

    source = "ai"
    row = _best_by_grade(df, "ai_grade")
    if row is None:
        source = "user"
        row = _best_by_grade(df, "user_grade")
    if row is None:
        return None

    result = row.drop(
        labels=[c for c in ("_rank", "_pnl_sort") if c in row.index]
    ).to_dict()
    result["grade"] = (
        result.get("ai_grade") if source == "ai" else result.get("user_grade")
    )
    result["grade_source"] = source
    return result


def split_periods(
    df: pd.DataFrame, days: int = 30, today=None
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split trades into (current, prior) windows of `days` each, ending today.

    current = (today-days, today];  prior = (today-2*days, today-days].
    `today` accepts a date/datetime/ISO-string; defaults to today.
    """
    empty = pd.DataFrame()
    if df is None or df.empty or "trade_date" not in df.columns:
        return empty, empty

    anchor = _coerce_date(today) or dt.date.today()
    work = df.copy()
    work["_dt"] = pd.to_datetime(work["trade_date"], errors="coerce").dt.date
    work = work[work["_dt"].notna()]

    cur_start = anchor - dt.timedelta(days=days)
    prior_start = anchor - dt.timedelta(days=2 * days)
    current = work[(work["_dt"] > cur_start) & (work["_dt"] <= anchor)]
    prior = work[(work["_dt"] > prior_start) & (work["_dt"] <= cur_start)]
    return (
        current.drop(columns=["_dt"]).reset_index(drop=True),
        prior.drop(columns=["_dt"]).reset_index(drop=True),
    )


def _safe_delta(current, prior) -> Optional[float]:
    """current - prior, or None if either side is non-finite (inf/NaN)."""
    try:
        c, p = float(current), float(prior)
    except (TypeError, ValueError):
        return None
    if math.isnan(c) or math.isinf(c) or math.isnan(p) or math.isinf(p):
        return None
    return c - p


def period_deltas(current_df: pd.DataFrame, prior_df: pd.DataFrame) -> dict:
    """Deltas (current − prior) for the hero KPIs.

    Returns keys: net_pnl, win_rate, profit_factor, consistency. Any value is
    None when it cannot be computed — notably when the prior period has no trades
    (no ZeroDivisionError), or for consistency when either side has <5 trades.
    """
    keys = ("net_pnl", "win_rate", "profit_factor", "consistency")
    none = {k: None for k in keys}
    if prior_df is None or prior_df.empty or current_df is None or current_df.empty:
        return dict(none)

    cur = compute_basic_metrics(current_df)
    pri = compute_basic_metrics(prior_df)
    out = {
        "net_pnl": _safe_delta(cur["total_pnl"], pri["total_pnl"]),
        "win_rate": _safe_delta(cur["win_rate"], pri["win_rate"]),
        "profit_factor": _safe_delta(cur["profit_factor"], pri["profit_factor"]),
    }
    if (
        len(current_df) >= _MIN_TRADES_FOR_CONSISTENCY
        and len(prior_df) >= _MIN_TRADES_FOR_CONSISTENCY
    ):
        out["consistency"] = _safe_delta(
            consistency_score(current_df), consistency_score(prior_df)
        )
    else:
        out["consistency"] = None
    return out


def current_week_pnl(df: pd.DataFrame, today=None) -> float:
    """Net P&L for the ISO week (Mon–Sun) containing `today`. 0.0 when empty."""
    if df is None or df.empty or "trade_date" not in df.columns:
        return 0.0

    anchor = _coerce_date(today) or dt.date.today()
    monday = anchor - dt.timedelta(days=anchor.weekday())
    sunday = monday + dt.timedelta(days=6)

    work = df.copy()
    work["_dt"] = pd.to_datetime(work["trade_date"], errors="coerce").dt.date
    mask = work["_dt"].notna() & (work["_dt"] >= monday) & (work["_dt"] <= sunday)
    pnl = pd.to_numeric(work.loc[mask, "pnl"], errors="coerce").fillna(0.0)
    return _safe_float(pnl.sum())
