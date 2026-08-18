"""Numeric drift detector.

Phase 0 pins the SERVICE outputs. From Phase 2 onward each API response is
asserted equal to the service output for the same input, so the snapshot chain
runs from the database to the screen.

Refresh deliberately, never reflexively:  TL_UPDATE_SNAPSHOTS=1 pytest tests/parity
A diff here is either a bug you just introduced or a change you can explain.
"""

import json
import os
import pathlib

import pandas as pd

from src.tradelens.api.serialization import to_jsonable
from src.tradelens.services import metrics, trade_service
from tests.parity.dataset import seed_golden_dataset

SNAPSHOT = pathlib.Path(__file__).parent / "snapshots" / "metrics.json"


def _frame(user_id: int) -> pd.DataFrame:
    trades = trade_service.get_trades(user_id=user_id)
    return pd.DataFrame(
        [
            {
                "trade_date": t.trade_date,
                "day_of_week": t.day_of_week,
                "asset": t.asset,
                "session": t.session,
                "setup_type": t.setup_type,
                "timeframe": t.timeframe,
                "result": t.result,
                "pnl": t.pnl,
                "rr_realized": t.rr_realized,
                "risk_amount": t.risk_amount,
                "followed_rules": t.followed_rules,
                "mistake_tags": t.mistake_tags,
                "strategy_used": t.strategy_used,
                "htf_bias": t.htf_bias,
                "killzone": t.killzone,
            }
            for t in trades
        ]
    )


def golden_metrics(user_id: int) -> dict:
    df = _frame(user_id)
    return {
        "basic": metrics.compute_basic_metrics(df),
        "expectancy": metrics.compute_expectancy(metrics.compute_basic_metrics(df)),
        "profit_factor_raw": metrics.compute_profit_factor_raw(df),
        "max_drawdown": metrics.compute_max_drawdown(metrics.compute_equity_curve(df)),
        "streaks": metrics.compute_streaks(df),
        "consistency_score": metrics.consistency_score(df),
        "total_edge_leak": metrics.total_edge_leak(df),
        "by_session": metrics.by_session(df),
        "by_asset": metrics.by_asset(df),
        "by_setup_type": metrics.by_setup_type(df),
        "by_day_of_week": metrics.by_day_of_week(df),
        "killzone_performance": metrics.killzone_performance(df),
        "mistake_frequency": metrics.mistake_frequency(df),
        "equity_curve": metrics.compute_equity_curve(df),
        "daily_pnl": metrics.daily_pnl(df),
    }


def test_metrics_match_the_golden_snapshot(two_users):
    user_id, _ = two_users
    seed_golden_dataset(user_id)

    actual = to_jsonable(golden_metrics(user_id))

    if os.getenv("TL_UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")

    expected = json.loads(SNAPSHOT.read_text())
    assert actual == expected


def test_the_golden_dataset_is_scoped_to_its_owner(two_users):
    """A parity snapshot computed from two tenants' trades would be green and
    meaningless."""
    a, b = two_users
    seed_golden_dataset(a)
    assert trade_service.get_trades(user_id=b) == []


def test_every_snapshotted_value_survives_strict_json(two_users):
    a, _ = two_users
    seed_golden_dataset(a)
    json.dumps(to_jsonable(golden_metrics(a)), allow_nan=False)
