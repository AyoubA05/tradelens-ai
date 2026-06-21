"""
Tests for the dashboard redesign (Phase 2, week6-d2).

Two layers:
  * Pure metrics helpers (trade_of_the_week, split_periods, period_deltas,
    current_week_pnl) — unit-tested directly, no DB, no Streamlit.
  * app.py boot smoke tests via AppTest, with the DB isolated to a tmp file by
    setting DATABASE_URL *before* the app is imported and purging the
    src.tradelens.* module cache so the engine rebuilds from the env (per the
    approved isolation strategy — no post-import monkeypatch of SessionLocal).
"""

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "src" / "tradelens" / "ui" / "app.py"


def _df(rows):
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# trade_of_the_week
# ---------------------------------------------------------------------------


def test_trade_of_week_picks_highest_ai_grade():
    from src.tradelens.services.metrics import trade_of_the_week

    df = _df(
        [
            {"asset": "NQ", "ai_grade": "B", "user_grade": "A", "pnl": 100.0},
            {"asset": "ES", "ai_grade": "A+", "user_grade": "C", "pnl": 50.0},
            {"asset": "BTC", "ai_grade": "C-", "user_grade": "A", "pnl": 999.0},
        ]
    )
    best = trade_of_the_week(df)
    assert best is not None
    assert best["asset"] == "ES"
    assert best["grade"] == "A+"
    assert best["grade_source"] == "ai"


def test_trade_of_week_falls_back_to_user_grade():
    from src.tradelens.services.metrics import trade_of_the_week

    df = _df(
        [
            {"asset": "NQ", "ai_grade": None, "user_grade": "B", "pnl": 100.0},
            {"asset": "ES", "ai_grade": None, "user_grade": "A-", "pnl": 50.0},
        ]
    )
    best = trade_of_the_week(df)
    assert best is not None
    assert best["asset"] == "ES"
    assert best["grade"] == "A-"
    assert best["grade_source"] == "user"


def test_trade_of_week_none_when_no_grades():
    from src.tradelens.services.metrics import trade_of_the_week

    df = _df(
        [
            {"asset": "NQ", "ai_grade": None, "user_grade": None, "pnl": 100.0},
            {"asset": "ES", "ai_grade": "", "user_grade": "", "pnl": 50.0},
        ]
    )
    assert trade_of_the_week(df) is None


def test_trade_of_week_tie_break_by_pnl():
    from src.tradelens.services.metrics import trade_of_the_week

    df = _df(
        [
            {"asset": "NQ", "ai_grade": "A", "user_grade": None, "pnl": 100.0},
            {"asset": "ES", "ai_grade": "A", "user_grade": None, "pnl": 400.0},
        ]
    )
    best = trade_of_the_week(df)
    assert best["asset"] == "ES"  # same grade, higher pnl wins


def test_trade_of_week_empty_df():
    from src.tradelens.services.metrics import trade_of_the_week

    assert trade_of_the_week(pd.DataFrame()) is None


# ---------------------------------------------------------------------------
# split_periods
# ---------------------------------------------------------------------------


def test_split_periods_windows():
    from src.tradelens.services.metrics import split_periods

    today = dt.date(2026, 6, 30)
    df = _df(
        [
            {"trade_date": "2026-06-25", "pnl": 1.0},  # current (within 30d)
            {"trade_date": "2026-06-10", "pnl": 2.0},  # current
            {"trade_date": "2026-05-20", "pnl": 3.0},  # prior (31-60d)
            {"trade_date": "2026-03-01", "pnl": 4.0},  # neither (too old)
        ]
    )
    current, prior = split_periods(df, days=30, today=today)
    assert set(current["trade_date"]) == {"2026-06-25", "2026-06-10"}
    assert set(prior["trade_date"]) == {"2026-05-20"}


def test_split_periods_empty_df():
    from src.tradelens.services.metrics import split_periods

    cur, pri = split_periods(pd.DataFrame(), days=30, today=dt.date(2026, 6, 30))
    assert cur.empty and pri.empty


# ---------------------------------------------------------------------------
# period_deltas
# ---------------------------------------------------------------------------


def test_period_deltas_basic():
    from src.tradelens.services.metrics import period_deltas

    current = _df([{"result": "Win", "pnl": 300.0} for _ in range(3)])
    prior = _df([{"result": "Loss", "pnl": -100.0} for _ in range(3)])
    deltas = period_deltas(current, prior)
    assert deltas["net_pnl"] == pytest.approx(900.0 - (-300.0))
    assert deltas["win_rate"] == pytest.approx(1.0 - 0.0)


def test_period_deltas_prior_empty_returns_none():
    """Guardrail: prior period with 0 trades -> None deltas, never ZeroDivisionError."""
    from src.tradelens.services.metrics import period_deltas

    current = _df([{"result": "Win", "pnl": 300.0}])
    deltas = period_deltas(current, pd.DataFrame())
    assert deltas["net_pnl"] is None
    assert deltas["win_rate"] is None
    assert deltas["profit_factor"] is None
    assert deltas["consistency"] is None


def test_period_deltas_consistency_none_under_5_trades():
    from src.tradelens.services.metrics import period_deltas

    current = _df([{"result": "Win", "pnl": 100.0} for _ in range(3)])
    prior = _df([{"result": "Win", "pnl": 50.0} for _ in range(3)])
    deltas = period_deltas(current, prior)
    assert deltas["consistency"] is None  # <5 trades each side
    assert deltas["net_pnl"] is not None  # other deltas still computed


# ---------------------------------------------------------------------------
# current_week_pnl
# ---------------------------------------------------------------------------


def test_current_week_pnl_sums_current_iso_week():
    from src.tradelens.services.metrics import current_week_pnl

    today = dt.date(2026, 6, 17)  # Wednesday; ISO week Mon 06-15 .. Sun 06-21
    df = _df(
        [
            {"trade_date": "2026-06-15", "pnl": 100.0},  # Mon — in week
            {"trade_date": "2026-06-21", "pnl": 50.0},  # Sun — in week
            {"trade_date": "2026-06-14", "pnl": 999.0},  # prev Sun — out
            {"trade_date": "2026-06-22", "pnl": 999.0},  # next Mon — out
        ]
    )
    assert current_week_pnl(df, today=today) == pytest.approx(150.0)


def test_current_week_pnl_empty_is_zero():
    from src.tradelens.services.metrics import current_week_pnl

    assert current_week_pnl(pd.DataFrame(), today=dt.date(2026, 6, 17)) == 0.0


# ---------------------------------------------------------------------------
# app.py boot smoke tests — run in a SUBPROCESS for true DB isolation.
#
# In-process reloading corrupts the rest of the suite (a second copy of
# ai_client breaks every isinstance(x, AIUnavailable) check). A child process
# has its own module state + DATABASE_URL engine, so the parent suite is
# untouched. DATABASE_URL is set in the child's env before import — exactly the
# "env var before import" strategy, with no SessionLocal monkeypatch.
# ---------------------------------------------------------------------------

_RUNNER = ROOT / "tests" / "app_boot_check.py"


def _run_boot(db_path: Path, marker: str, seed: str):
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["DEMO_MODE"] = "true"  # never touch the network on boot
    proc = subprocess.run(
        [sys.executable, str(_RUNNER), str(ROOT), str(APP_PATH), marker, seed],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, (
        f"boot failed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_app_boots_empty_db_shows_empty_state(tmp_path):
    # designed empty state (our component) must render, not a raw st.info
    _run_boot(tmp_path / "empty.db", "tl-empty-state", "0")


def test_app_boots_with_seed_data(tmp_path):
    # redesigned KPI glass cards must render
    _run_boot(tmp_path / "seed.db", "tl-kpi-card", "1")
