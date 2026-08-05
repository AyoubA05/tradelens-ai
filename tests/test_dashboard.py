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
    # the ruled KPI strip replaces the six-card hero
    _run_boot(tmp_path / "seed.db", "tl-kpi-strip", "1")


def test_app_boots_sparse_data_withholds_the_dominant_chart(tmp_path):
    """One trade cannot carry a dominant equity instrument. The panel must
    degrade to the shared low-data explanation, not draw a dot on an axis."""
    _run_boot(tmp_path / "sparse.db", "tl-data-state", "one")


def test_app_boots_sparse_data_still_shows_the_strip(tmp_path):
    """Withholding the chart must not withhold the numbers — one trade still
    has a P&L worth reading."""
    _run_boot(tmp_path / "sparse2.db", "tl-kpi-strip", "one")


def test_app_boots_rich_data_shows_the_editorial_readout(tmp_path):
    _run_boot(tmp_path / "seed2.db", "tl-readout", "1")


# ---------------------------------------------------------------------------
# Task 3 — Overview composed as a command center.
# ---------------------------------------------------------------------------


def test_overview_uses_one_ruled_strip_not_six_cards():
    """Six separately boxed tiles say these numbers are six separate things.
    They are one measurement across a period."""
    src = APP_PATH.read_text(encoding="utf-8")
    assert "render_kpi_strip" in src
    assert "render_kpi_card" not in src, "the per-card hero is gone"
    assert "tl-hero-wrap" not in src, "the hero background wrapper is gone"
    assert "hero_bg.png" not in src, "no decoration behind the figures"


def test_overview_strip_carries_the_five_headline_measures():
    src = APP_PATH.read_text(encoding="utf-8")
    for label in ("Net P&L", "Win rate", "Expectancy", "Profit factor", "Trades"):
        assert label in src, label


def test_todays_and_weekly_pnl_survive_in_the_brief():
    """They left the strip but not the page — the Today Brief is where a
    trader looks for 'where am I right now'."""
    src = APP_PATH.read_text(encoding="utf-8")
    assert "today_pnl" in src and "current_week_pnl" in src
    assert "_render_today_brief" in src


def test_the_overview_reads_as_five_bands_in_the_spec_order():
    """Spec §5.1. The Overview is a fixed editorial composition, and the
    reading order IS the argument: where do I stand, can I trust it, how did I
    get here, what repeats, what do I do about it.

    This replaces a test that pinned the old two-column layout. That layout put
    the calendar beside the curve and had no place for discipline or recurring
    edge, so it could not express the argument.
    """
    src = APP_PATH.read_text(encoding="utf-8")
    bands = [
        "render_kpi_strip(_overview_metrics(df))",  # 1 current standing
        "render_discipline_panel(discipline_measures(df))",  # 2 risk/discipline
        "render_flanking_figures(trajectory_figures(df))",  # 3 trajectory
        "render_ranked_list(",  # 4 recurring edge
        "render_editorial_readout(",  # 5 next review action
    ]
    positions = []
    for marker in bands:
        assert marker in src, f"band marker missing: {marker}"
        positions.append(src.index(marker))
    assert positions == sorted(positions), "the five bands are out of reading order"


def test_each_band_uses_a_different_form():
    """The anti-grid rule is structural: five bands, five forms. If two bands
    shared a builder the Overview would become the wall of equal cards the
    direction forbids."""
    src = APP_PATH.read_text(encoding="utf-8")
    builders = (
        "render_kpi_strip",
        "render_discipline_panel",
        "render_flanking_figures",
        "render_ranked_list",
        "render_editorial_readout",
    )
    assert len(set(builders)) == 5
    for builder in builders:
        assert builder in src


def test_the_calendar_survived_the_recomposition():
    """Trading days moved into band 4 with the rest of what repeats — it must
    not have been dropped on the way."""
    src = APP_PATH.read_text(encoding="utf-8")
    assert "render_trade_calendar" in src


def test_overview_carries_one_editorial_observation():
    """One reading of the period, not a column of them."""
    src = APP_PATH.read_text(encoding="utf-8")
    assert src.count("render_editorial_readout(") == 1
    assert "EvidenceItem" in src
    assert "_overview_observation" in src


def _sessions(rows):
    return _df(
        [
            {"trade_date": f"2026-07-{d:02d}", "pnl": p, "killzone": k}
            for d, p, k in rows
        ]
    )


def test_leading_category_identifies_the_carrying_session():
    """The observation's factual basis is a pure function, so it can be
    tested without booting the page it appears on."""
    from src.tradelens.ui.components.data_state import leading_category

    leader = leading_category(
        _sessions(
            [
                (1, 300.0, "london_open"),
                (2, 250.0, "london_open"),
                (3, -80.0, "ny_am"),
                (6, 120.0, "london_open"),
                (7, -40.0, "ny_am"),
                (8, 90.0, "london_open"),
            ]
        ),
        "killzone",
    )
    assert leader.key == "london_open"
    assert leader.count == 4
    assert leader.total == pytest.approx(760.0)
    assert leader.categories == 2
    assert not leader.is_only_category
    assert leader.share > 0.5


def test_leading_category_is_withheld_on_a_small_sample():
    """Naming a leading session out of three trades describes noise."""
    from src.tradelens.ui.components.data_state import leading_category

    assert leading_category(None, "killzone") is None
    assert leading_category(pd.DataFrame(), "killzone") is None
    assert (
        leading_category(
            _sessions([(1, 10.0, "ny_am"), (2, 20.0, "ny_am")]), "killzone"
        )
        is None
    )


def test_leading_category_reports_a_single_category_honestly():
    from src.tradelens.ui.components.data_state import leading_category

    leader = leading_category(
        _sessions([(d, 50.0, "ny_am") for d in range(1, 7)]), "killzone"
    )
    assert leader.is_only_category
    assert leader.categories == 1


def test_leading_category_handles_a_zero_net_period():
    """A share of nothing is not a majority — this must not divide by zero."""
    from src.tradelens.ui.components.data_state import leading_category

    leader = leading_category(
        _sessions(
            [
                (1, 100.0, "london_open"),
                (2, -100.0, "ny_am"),
                (3, 50.0, "london_open"),
                (6, -50.0, "ny_am"),
                (7, 0.0, "ny_pm"),
            ]
        ),
        "killzone",
    )
    assert leader.overall_total == pytest.approx(0.0)
    assert leader.share == 0.0


def test_leading_category_ignores_rows_with_no_category_or_value():
    from src.tradelens.ui.components.data_state import leading_category

    df = _df(
        [
            {"trade_date": "2026-07-01", "pnl": 100.0, "killzone": "ny_am"},
            {"trade_date": "2026-07-02", "pnl": 50.0, "killzone": ""},
            {"trade_date": "2026-07-03", "pnl": None, "killzone": "london_open"},
            {"trade_date": "2026-07-06", "pnl": 40.0, "killzone": None},
            {"trade_date": "2026-07-07", "pnl": 30.0, "killzone": "ny_am"},
            {"trade_date": "2026-07-08", "pnl": 20.0, "killzone": "ny_am"},
        ]
    )
    leader = leading_category(df, "killzone")
    assert leader.key == "ny_am"
    assert leader.count == 3
    assert leader.categories == 1


def test_observation_copy_stays_reflective():
    """Source-level guard on the wording: the Overview describes what was
    recorded and never suggests what to take next."""
    src = APP_PATH.read_text(encoding="utf-8")
    body = src[
        src.index("def _overview_observation") : src.index("def _render_today_brief")
    ]
    lowered = body.lower()
    for banned in (
        "signal",
        "buy now",
        "go long",
        "go short",
        "you should",
        "next trade",
    ):
        assert banned not in lowered
    assert "recorded" in lowered


def test_active_filter_reads_as_a_summary_not_a_second_control_group():
    src = APP_PATH.read_text(encoding="utf-8")
    assert "render_filter_summary" in src
    # the control itself stays — filtering is preserved
    assert '"All assets"' in src
    assert 'df["asset"].astype(str) == asset_choice' in src


def test_recent_trades_ledger_has_no_full_row_tint():
    """Spec 11.3: win/loss use text and a small semantic mark, never a
    full-row fill."""
    src = APP_PATH.read_text(encoding="utf-8")
    assert "<tr>" in src
    for tinted in ('<tr class="win"', '<tr class="loss"', 'tr class="pnl'):
        assert tinted not in src
    # money stays right-aligned and monospaced
    assert "num" in src and "mono" in src


def test_activation_demo_and_empty_states_are_preserved():
    src = APP_PATH.read_text(encoding="utf-8")
    assert "activation_status" in src and "NEXT_STEP_COPY" in src
    assert "render_demo_banner" in src
    assert "count_sample_trades" in src
    assert "Load sample trades" in src
    assert "daily_equity_curve" in src and "compute_basic_metrics" in src


def test_overview_keeps_one_primary_action_and_no_quick_action_wall():
    """The rail already carries 'Log completed trade'. A row of three
    equally weighted action cards repeated it and diluted it."""
    src = APP_PATH.read_text(encoding="utf-8")
    assert "Quick Actions" not in src
    assert "tl-action-card" not in src


# ---------------------------------------------------------------------------
# Compact calendar mode (Overview) — the Analytics calendar is untouched.
# ---------------------------------------------------------------------------


def test_calendar_supports_a_compact_overview_mode():
    import inspect

    from src.tradelens.ui.components.trade_calendar import render_trade_calendar

    params = inspect.signature(render_trade_calendar).parameters
    assert "compact" in params
    assert params["compact"].default is False, "full mode stays the default"
    assert "selected_date" in params


def test_compact_calendar_hides_the_legend_and_day_panel():
    """In the Overview column the calendar is a preview: the legend and the
    inline day table belong to the full view, which Journal owns."""
    from src.tradelens.ui.components import trade_calendar

    src = Path(trade_calendar.__file__).read_text(encoding="utf-8")
    assert "if not compact" in src or "not compact" in src


def test_compact_calendar_is_one_grid_not_stacked_columns():
    """Measured at 375px: st.columns(7) stacks below Streamlit's mobile
    breakpoint, turning the calendar into a 31-row list that buried the
    chart under 2,000px of dates."""
    from src.tradelens.ui.components.trade_calendar import compact_month_html

    daily = {
        "2026-07-01": {"pnl": 120.0, "trades": 1, "outcome": "positive"},
        "2026-07-02": {"pnl": -40.0, "trades": 2, "outcome": "negative"},
        "2026-07-03": {"pnl": 0.0, "trades": 1, "outcome": "breakeven"},
    }
    html = compact_month_html(2026, 7, daily)
    assert "grid-template-columns:repeat(7,1fr)" in html
    # every day of July is present exactly once
    assert html.count('class="tl-cal-dot') == 3
    assert "tl-cal-dot positive" in html and "tl-cal-dot negative" in html
    # no raw hex: colour comes from design-system classes and tokens
    assert "#" not in html


def test_compact_calendar_renders_every_day_of_the_month():
    from src.tradelens.ui.components.trade_calendar import compact_month_html

    html = compact_month_html(2026, 2, {})  # 28 days, starts Sunday
    for day in range(1, 29):
        assert f">{day}</div>" in html or f">{day}<br/>" in html, day


# ---------------------------------------------------------------------------
# Dominant-instrument threshold.
# ---------------------------------------------------------------------------


def test_dominant_series_needs_four_points_but_series_still_needs_two():
    """Spec 11.1: fewer than four usable time points gets a compact trend
    summary instead of an oversized chart. The two-point rule that governs
    the Analytics page is unchanged."""
    import pandas as pd

    from src.tradelens.ui.components.data_state import sample_state

    two = pd.DataFrame({"trade_date": ["2026-07-01", "2026-07-02"], "pnl": [1.0, 2.0]})
    state = sample_state(two)
    assert state.show_series, "Analytics threshold must not move"
    assert not state.show_dominant_series

    four = pd.DataFrame(
        {
            "trade_date": ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06"],
            "pnl": [1.0, 2.0, 3.0, 4.0],
        }
    )
    assert sample_state(four).show_dominant_series


def test_dominant_series_is_false_for_empty_and_none():
    from src.tradelens.ui.components.data_state import sample_state

    assert not sample_state(None).show_dominant_series
    assert not sample_state(pd.DataFrame()).show_dominant_series


# ---------------------------------------------------------------------------
# Item 12 — trade calendar + asset filter.
# ---------------------------------------------------------------------------


def test_calendar_month_helpers():
    from src.tradelens.ui.components.trade_calendar import (
        day_key,
        month_label,
        month_options,
    )

    daily = {
        "2026-07-01": {"pnl": 1.0, "trades": 1, "outcome": "positive"},
        "2026-07-15": {"pnl": -1.0, "trades": 1, "outcome": "negative"},
        "2026-06-30": {"pnl": 0.0, "trades": 1, "outcome": "breakeven"},
    }
    assert month_options(daily) == ["2026-07", "2026-06"]  # newest first
    assert month_label("2026-07") == "July 2026"
    assert day_key(2026, 7, 3) == "2026-07-03"


def test_dashboard_has_asset_filter_and_calendar():
    """Item 12 contract, carried into the command-center composition.

    The filter is still dynamic and still scopes every figure; the calendar
    and the equity curve are still present. What changed is presentation:
    the calendar renders in compact mode inside the brief column, and the
    six KPI card labels became the five-measure ruled strip — both covered
    by the Task 3 tests below.
    """
    src = APP_PATH.read_text(encoding="utf-8")
    assert '"All assets"' in src  # default option
    assert "_traded_assets" in src and 'df["asset"].dropna()' in src  # dynamic
    assert "render_trade_calendar(df, compact=True)" in src
    # Filter is applied to the frame every stat below derives from.
    assert 'df["asset"].astype(str) == asset_choice' in src
    # The underlying calculations are untouched.
    for fn in (
        "compute_basic_metrics",
        "compute_expectancy",
        "compute_profit_factor_raw",
        "today_pnl",
        "current_week_pnl",
        "daily_equity_curve",
        "get_last_n_trades",
    ):
        assert fn in src, fn
    assert "equity_curve_chart(eq)" in src


# ---------------------------------------------------------------------------
# Task 5 — Overview band 2, the discipline panel
# ---------------------------------------------------------------------------
def _discipline(df):
    """From the pure module, not the page. app.py runs its whole Streamlit
    script at module scope, so importing it to reach one helper boots a page
    and needs a database — which is why this logic lives in overview_bands."""
    from src.tradelens.ui.components.overview_bands import (  # noqa: PLC0415
        discipline_measures,
    )

    return {m.label: m for m in discipline_measures(df)}


def test_band_two_carries_the_four_discipline_measures():
    measures = _discipline(
        pd.DataFrame(
            {
                "trade_date": [f"2026-08-{d:02d}" for d in range(1, 7)],
                "pnl": [10.0, -4.0, 2.0, 8.0, -1.0, 5.0],
                "followed_rules": [True, False, True, True, False, True],
            }
        )
    )
    assert set(measures) == {
        "Max drawdown",
        "Rule adherence",
        "Edge leak",
        "Consistency",
    }


def test_unknown_adherence_reads_not_recorded_never_zero_percent():
    """A rate over an unknown sample is not 0% — it is unknown. Reporting 0%
    would accuse a trader who simply never filled the field."""
    adherence = _discipline(pd.DataFrame({"pnl": [1.0, 2.0]}))["Rule adherence"]
    assert adherence.value == "Not recorded"
    assert "0%" not in adherence.value


def test_a_known_zero_adherence_is_shown_as_zero_with_its_sample():
    df = pd.DataFrame({"followed_rules": [False, False], "pnl": [-1.0, -2.0]})
    adherence = _discipline(df)["Rule adherence"]
    assert adherence.value == "0%"
    assert adherence.sample == "0 of 2"


def test_a_positive_edge_leak_is_never_presented_as_a_good_outcome():
    """Rule-breaking that happened to net a profit is lucky, not repeatable,
    and must never read as a win."""
    df = pd.DataFrame({"followed_rules": [False, True], "pnl": [40.0, 10.0]})
    leak = _discipline(df)["Edge leak"]
    assert leak.note and "not repeatable" in leak.note.lower()


def test_an_unknown_edge_leak_is_distinguished_from_a_clean_sample():
    """Spec D10: 0.0 meant three different things. They must read
    differently."""
    unknown = _discipline(pd.DataFrame({"pnl": [1.0]}))["Edge leak"]
    clean = _discipline(
        pd.DataFrame({"followed_rules": [True, True], "pnl": [5.0, 6.0]})
    )["Edge leak"]
    assert unknown.value == "Not recorded"
    assert clean.value != "Not recorded"
    assert unknown.value != clean.value


def test_consistency_is_withheld_below_five_trades_and_says_what_unlocks_it():
    df = pd.DataFrame({"pnl": [1.0, 2.0, 3.0]})
    score = _discipline(df)["Consistency"]
    assert "2 more" in score.sample


def test_no_discipline_measure_is_toned():
    """Process measures may not borrow the money palette."""
    from src.tradelens.ui.components.overview_bands import (  # noqa: PLC0415
        discipline_measures,
    )

    df = pd.DataFrame({"followed_rules": [True, False], "pnl": [5.0, -5.0]})
    for measure in discipline_measures(df):
        assert not hasattr(measure, "tone")
