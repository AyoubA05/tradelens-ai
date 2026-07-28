"""
Boot smoke tests for all 9 pages (Phase 3, week6-d3).

Each page is booted under AppTest in a SUBPROCESS with an isolated tmp DB (see
app_boot_check.py for why a subprocess and not an in-process module reload). The
empty-DB boots exercise the designed empty-state paths; the seed-DB boots cover
the read-only data pages with rows present. Marker "-" means boot-only: assert
the page raises no exception.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES_DIR = ROOT / "src" / "tradelens" / "ui" / "pages"
RUNNER = ROOT / "tests" / "app_boot_check.py"

# Session A: the sidebar now exposes exactly these five pages (plus app.py, the
# Dashboard, covered by test_dashboard). Home/TradeDetail/Calendar/Weekly/AI
# Partner moved to pages/_archive/ (Calendar + Weekly are now Analytics tabs).
ALL_PAGES = [
    "1_NewTrade.py",
    "2_Trades.py",
    "4_Analytics.py",
    "5_Strategy.py",
    "6_Insights.py",
    "9_Settings.py",
]

# Read-only data pages worth booting with rows present.
SEED_PAGES = ["2_Trades.py", "4_Analytics.py", "6_Insights.py"]


def _boot(page: str, db_path: Path, seed: str, marker: str = "-", state: str = "{}"):
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["DEMO_MODE"] = "true"  # never touch the network on boot
    proc = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            str(ROOT),
            str(PAGES_DIR / page),
            marker,
            seed,
            state,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, (
        f"{page} boot failed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


@pytest.mark.parametrize("page", ALL_PAGES)
def test_page_boots_empty_db(page, tmp_path):
    _boot(page, tmp_path / "empty.db", "0")


@pytest.mark.parametrize("page", SEED_PAGES)
def test_page_boots_seed_db(page, tmp_path):
    _boot(page, tmp_path / "seed.db", "1")


# ---------------------------------------------------------------------------
# Shell contract — the custom navigation is the ONLY navigation
# ---------------------------------------------------------------------------


def test_streamlits_own_page_navigation_stays_disabled():
    """TradeLens renders its own labelled rail. With Streamlit's automatic
    nav also on, a trader sees two menus listing the same pages under
    different names — the file names, which say `6_Insights`."""
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert "showSidebarNavigation = false" in config


@pytest.mark.parametrize("page", ALL_PAGES)
def test_every_page_renders_the_custom_shell(page):
    """A page that forgets the shell loses navigation entirely — there is no
    fallback menu to fall back to."""
    src = (PAGES_DIR / page).read_text(encoding="utf-8")
    assert "render_sidebar" in src, f"{page} renders no navigation"


def test_the_entrypoint_renders_the_custom_shell():
    src = (ROOT / "src" / "tradelens" / "ui" / "app.py").read_text(encoding="utf-8")
    assert "render_sidebar" in src


def test_no_page_hardcodes_its_own_navigation_list():
    """Navigation lives in components/sidebar.py. A page building its own
    list is how the rail and the page disagree about what exists."""
    pages = [PAGES_DIR / p for p in ALL_PAGES]
    pages.append(ROOT / "src" / "tradelens" / "ui" / "app.py")
    for path in pages:
        src = path.read_text(encoding="utf-8")
        assert "PRIMARY_NAV = " not in src, f"{path.name} redefines the nav"
        assert "MOBILE_NAV = " not in src, f"{path.name} redefines the mobile nav"


# ---------------------------------------------------------------------------
# Journal — the three views boot in every data state (Task 5).
#
# State is injected through the runner's optional session-state argument, so
# each view is exercised on a real seeded DB rather than trusted from source.
# ---------------------------------------------------------------------------

_JOURNAL = "2_Trades.py"


def test_journal_trades_view_lists_the_ledger(tmp_path):
    _boot(_JOURNAL, tmp_path / "j1.db", "1", "Journal", '{"journal_view": "Trades"}')


def test_journal_calendar_view_renders_the_full_calendar(tmp_path):
    """The Journal calendar keeps its month control — that is what makes it
    the full view rather than the Overview preview."""
    _boot(
        _JOURNAL,
        tmp_path / "j2.db",
        "1",
        "net positive day",
        '{"journal_view": "Calendar"}',
    )


def test_journal_detail_view_without_a_selection_explains_itself(tmp_path):
    """Landing on Trade Detail with nothing chosen must say what to do, not
    render a blank page."""
    _boot(
        _JOURNAL,
        tmp_path / "j3.db",
        "1",
        "No trade selected",
        '{"journal_view": "Trade Detail"}',
    )


def test_journal_detail_view_opens_a_selected_trade(tmp_path):
    """The marker is a section of the detail body, not the Back button: the
    runner inspects markdown, and a button label is not markdown."""
    _boot(
        _JOURNAL,
        tmp_path / "j4.db",
        "1",
        "Risk & Outcome",
        '{"journal_view": "Trade Detail", "selected_trade_id": 1}',
    )


def test_journal_no_results_state_survives_a_narrow_filter(tmp_path):
    """A filter that matches nothing is not an empty journal, and must not
    read like one."""
    _boot(
        _JOURNAL,
        tmp_path / "j5.db",
        "1",
        "No trades match your filters",
        '{"jf_result": "Breakeven", "jf_setup": "All", "jf_session": "All"}',
    )


def test_journal_empty_db_under_demo_mode_shows_demo_data(tmp_path):
    """Pre-existing behaviour, pinned so the redesign cannot lose it: with
    DEMO_MODE on and nothing logged, the Journal shows demo trades rather
    than an empty state, and says so."""
    _boot(_JOURNAL, tmp_path / "j6.db", "0", "Showing demo data")


# ---------------------------------------------------------------------------
# Analytics — every lens boots in every data state (Task 6).
# ---------------------------------------------------------------------------

_ANALYTICS = "4_Analytics.py"


@pytest.mark.parametrize("lens", ["Performance", "Risk", "Timing", "Setups"])
def test_analytics_lens_boots_with_rich_data(lens, tmp_path):
    _boot(
        _ANALYTICS,
        tmp_path / f"a-{lens}.db",
        "1",
        "-",
        json.dumps({"analytics_lens": lens}),
    )


@pytest.mark.parametrize("lens", ["Performance", "Risk", "Timing", "Setups"])
def test_analytics_lens_boots_with_one_trade(lens, tmp_path):
    """A single trade must degrade to explanations, never a chart drawn
    through one point."""
    _boot(
        _ANALYTICS,
        tmp_path / f"a1-{lens}.db",
        "one",
        "-",
        json.dumps({"analytics_lens": lens}),
    )


def test_analytics_performance_lens_shows_its_readout(tmp_path):
    _boot(
        _ANALYTICS,
        tmp_path / "a-readout.db",
        "1",
        "tl-readout",
        json.dumps({"analytics_lens": "Performance"}),
    )


def test_analytics_risk_lens_states_fixed_risk_instead_of_charting_it(tmp_path):
    """Every seeded trade risks the same amount, so a 'risk over time' line
    would be a flat rule presented as a finding."""
    _boot(
        _ANALYTICS,
        tmp_path / "a-fixedrisk.db",
        "fixedrisk",
        "Risk is fixed at",
        json.dumps({"analytics_lens": "Risk"}),
    )


def test_analytics_renders_only_the_selected_lens(tmp_path):
    """The Setups leaderboard must not appear while Performance is open."""
    _boot(
        _ANALYTICS,
        tmp_path / "a-onelens.db",
        "1",
        "How did this period actually go?",
        json.dumps({"analytics_lens": "Performance"}),
    )


def test_analytics_timing_never_ranks_a_single_day(tmp_path):
    """One weekday in range has nothing to be strongest of."""
    _boot(
        _ANALYTICS,
        tmp_path / "a-oneday.db",
        "onecategory",
        "Only day",
        json.dumps({"analytics_lens": "Timing"}),
    )


def test_analytics_setups_never_ranks_a_single_setup(tmp_path):
    _boot(
        _ANALYTICS,
        tmp_path / "a-onesetup.db",
        "onecategory",
        "Only setup",
        json.dumps({"analytics_lens": "Setups"}),
    )


def test_analytics_single_setup_readout_does_not_claim_a_ranking(tmp_path):
    _boot(
        _ANALYTICS,
        tmp_path / "a-onesetup-readout.db",
        "onecategory",
        "was traded in range",
        json.dumps({"analytics_lens": "Setups"}),
    )


def test_analytics_category_names_are_escaped_exactly_once(tmp_path):
    """'BOS & FVG' must reach the reader as an ampersand, not '&amp;'."""
    _boot(
        _ANALYTICS,
        tmp_path / "a-escape.db",
        "onecategory",
        "BOS &amp; FVG",
        json.dumps({"analytics_lens": "Setups"}),
    )


def test_analytics_timing_calendar_follows_the_asset_filter(tmp_path):
    """The calendar answers the same filtered question as the strip and the
    heatmap above it. Filtering to an asset that is not in range empties the
    lens rather than leaving a full-month calendar behind."""
    _boot(
        _ANALYTICS,
        tmp_path / "a-calfilter.db",
        "1",
        "No matching trades",
        json.dumps({"analytics_lens": "Timing", "an_asset": ["NOT_A_REAL_ASSET"]}),
    )
