#!/usr/bin/env python3
"""
Pre-compute KPI summary for a user and write to the performance_metrics table.

Usage:
    python scripts/recompute_metrics.py
    python scripts/recompute_metrics.py --user-id 1
"""
import argparse
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

# parents[1] of scripts/recompute_metrics.py  →  project root
_root = str(Path(__file__).resolve().parents[1])
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd  # noqa: E402

from src.tradelens.db.models import PerformanceMetrics  # noqa: E402
from src.tradelens.db.session import SessionLocal  # noqa: E402
from src.tradelens.services.metrics import (  # noqa: E402
    by_day_of_week,
    by_strategy,
    by_timeframe,
    compute_basic_metrics,
    compute_profit_factor_raw,
)
from src.tradelens.services.trade_service import get_trades  # noqa: E402


def _build_df(trades) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": t.trade_date,
                "day_of_week": t.day_of_week,
                "strategy_used": t.strategy_used,
                "timeframe": t.timeframe,
                "rr_realized": t.rr_realized,
                "pnl": t.pnl,
                "result": t.result,
            }
            for t in trades
        ]
    )


def recompute(user_id: int) -> None:
    print(f"Loading trades for user_id={user_id}…")
    trades = get_trades(user_id=user_id)
    df = _build_df(trades)

    if df.empty:
        print("No trades found. Nothing to compute.")
        return

    m = compute_basic_metrics(df)
    pf = compute_profit_factor_raw(df)

    # best/worst day — by_day_of_week sorts chronologically; re-sort by pnl here
    dow_df = by_day_of_week(df)
    best_day = worst_day = None
    if not dow_df.empty:
        dow_sorted = dow_df.sort_values("total_pnl", ascending=False).reset_index(
            drop=True
        )
        best_day = str(dow_sorted.iloc[0]["day_of_week"])
        worst_day = str(dow_sorted.iloc[-1]["day_of_week"])

    # best/worst strategy — by_strategy already sorts total_pnl descending
    strat_df = by_strategy(df)
    best_strategy = strat_df.iloc[0]["strategy_used"] if not strat_df.empty else None
    worst_strategy = strat_df.iloc[-1]["strategy_used"] if len(strat_df) > 1 else None

    # best/worst timeframe — by_timeframe already sorts total_pnl descending
    tf_df = by_timeframe(df)
    best_timeframe = tf_df.iloc[0]["timeframe"] if not tf_df.empty else None
    worst_timeframe = tf_df.iloc[-1]["timeframe"] if len(tf_df) > 1 else None

    period_start = (
        df["trade_date"].dropna().min() if "trade_date" in df.columns else None
    )
    period_end = df["trade_date"].dropna().max() if "trade_date" in df.columns else None
    now = datetime.now(timezone.utc).isoformat()

    # float("inf") cannot be stored in SQLite REAL; store None (column is not displayed)
    pf_stored = None if math.isinf(pf) else round(pf, 4)

    db = SessionLocal()
    try:
        row = (
            db.query(PerformanceMetrics)
            .filter(PerformanceMetrics.user_id == user_id)
            .first()
        )
        if row is None:
            row = PerformanceMetrics(user_id=user_id)
            db.add(row)

        row.period_start = period_start
        row.period_end = period_end
        row.trades_count = m["total_trades"]
        row.win_rate = round(m["win_rate"], 4)
        row.profit_factor = pf_stored
        row.avg_rr = round(m["avg_rr_realized"], 4)
        row.avg_win = round(m["avg_win"], 4)
        row.avg_loss = round(m["avg_loss"], 4)
        row.total_pnl = round(m["total_pnl"], 2)
        row.best_day = best_day
        row.worst_day = worst_day
        row.best_strategy = best_strategy
        row.worst_strategy = worst_strategy
        row.best_timeframe = best_timeframe
        row.worst_timeframe = worst_timeframe
        row.computed_at = now

        db.commit()
        db.refresh(row)
    finally:
        db.close()

    pf_display = "∞" if math.isinf(pf) else f"{pf:.2f}"
    print()
    print(f"user_id:       {user_id}")
    print(f"period:        {period_start} → {period_end}")
    print(f"trades:        {m['total_trades']}")
    print(f"total_pnl:     ${m['total_pnl']:,.2f}")
    print(f"win_rate:      {m['win_rate']:.1%}")
    print(f"profit_factor: {pf_display}")
    print(f"avg_rr:        {m['avg_rr_realized']:.2f}R")
    print(f"best_day:      {best_day}")
    print(f"worst_day:     {worst_day}")
    print(f"best_strategy: {best_strategy}")
    print(f"computed_at:   {now}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-compute KPI metrics for a user.")
    parser.add_argument(
        "--user-id",
        type=int,
        default=1,
        dest="user_id",
        help="User ID to compute metrics for (default: 1)",
    )
    args = parser.parse_args()
    recompute(args.user_id)


if __name__ == "__main__":
    main()
