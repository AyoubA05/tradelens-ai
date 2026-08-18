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
REVIEW_OPTIONS_RUNNER = ROOT / "tests" / "insights_review_options_check.py"

# Session A: the sidebar now exposes exactly these five pages (plus app.py, the
# Dashboard, covered by test_dashboard). Home/TradeDetail/Calendar/Weekly/AI
# Partner moved to pages/_archive/ (Calendar + Weekly are now Analytics tabs).
ALL_PAGES = [
    "1_NewTrade.py",
    "2_Trades.py",
    "4_Analytics.py",
    "5_Strategy.py",
    "6_Insights.py",
    # Not bookkeeping: this list drives the parametrised boot test, so a page
    # absent from it is a page nothing proves boots.
    "7_Partner.py",
    "9_Settings.py",
]

# Read-only data pages worth booting with rows present.
SEED_PAGES = ["2_Trades.py", "4_Analytics.py", "6_Insights.py"]


def _boot(
    page: str,
    db_path: Path,
    seed: str,
    marker: str = "-",
    state: str = "{}",
    *,
    demo_mode: bool = True,
):
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["DEMO_MODE"] = "true" if demo_mode else "false"
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


# ---------------------------------------------------------------------------
# AI Reviews — each lens boots in each data state (Task 7).
# ---------------------------------------------------------------------------

_INSIGHTS = "6_Insights.py"


@pytest.mark.parametrize("lens", ["Patterns", "Weekly Recap", "Daily Debrief"])
def test_ai_review_lens_boots_with_rich_data(lens, tmp_path):
    _boot(
        _INSIGHTS,
        tmp_path / f"i-{lens}.db",
        "1",
        "-",
        json.dumps({"ai_review_lens": lens}),
    )


@pytest.mark.parametrize("lens", ["Patterns", "Weekly Recap", "Daily Debrief"])
def test_ai_review_lens_boots_with_one_trade(lens, tmp_path):
    _boot(
        _INSIGHTS,
        tmp_path / f"i1-{lens}.db",
        "one",
        "-",
        json.dumps({"ai_review_lens": lens}),
    )


def test_demo_review_periods_use_demo_rows_and_offer_empty_recovery(tmp_path):
    """Only populated demo periods may reach generation, with a safe exit otherwise."""
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'review-options.db'}"
    env["DEMO_MODE"] = "true"
    proc = subprocess.run(
        [sys.executable, str(REVIEW_OPTIONS_RUNNER), str(ROOT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr


def test_patterns_lens_renders_a_research_note(tmp_path):
    """The note's own thesis heading, not a grid of insight cards."""
    _boot(
        _INSIGHTS,
        tmp_path / "i-note.db",
        "1",
        "tl-note-thesis",
        json.dumps({"ai_review_lens": "Patterns"}),
    )


def test_patterns_lens_numbers_its_findings(tmp_path):
    _boot(
        _INSIGHTS,
        tmp_path / "i-findings.db",
        "1",
        "tl-finding-number",
        json.dumps({"ai_review_lens": "Patterns"}),
    )


def test_patterns_lens_carries_an_evidence_rail(tmp_path):
    _boot(
        _INSIGHTS,
        tmp_path / "i-rail.db",
        "1",
        "tl-evidence-rail",
        json.dumps({"ai_review_lens": "Patterns"}),
    )


def test_patterns_lens_collapses_its_evidence_used(tmp_path):
    _boot(
        _INSIGHTS,
        tmp_path / "i-details.db",
        "1",
        "<details",
        json.dumps({"ai_review_lens": "Patterns"}),
    )


# ---------------------------------------------------------------------------
# Strategy Profile — playbook states
# ---------------------------------------------------------------------------

_STRATEGY = "5_Strategy.py"
_SIGNED_IN = json.dumps({"current_user_id": 1})


def test_strategy_empty_profile_says_what_is_lost_until_it_is_filled(tmp_path):
    """No profile: the page has to say what filling this in buys, not just
    present twelve empty fields. (The starter-template button is the other
    half of the invitation; buttons are not markdown, so it is asserted in
    the page contracts instead.)"""
    _boot(
        _STRATEGY,
        tmp_path / "s-empty.db",
        "0",
        "fall back to generic",
        _SIGNED_IN,
        demo_mode=False,
    )


def test_strategy_empty_profile_reports_zero_completion(tmp_path):
    _boot(
        _STRATEGY,
        tmp_path / "s-zero.db",
        "0",
        "0 of 6 sections",
        _SIGNED_IN,
        demo_mode=False,
    )


def test_strategy_summarizes_a_saved_profile(tmp_path):
    _boot(_STRATEGY, tmp_path / "s-name.db", "profile", "ICT Continuation", _SIGNED_IN)


def test_strategy_reports_partial_completion(tmp_path):
    """The seeded profile fills Identity and Entry Rules only. A completion
    figure that cannot go down is not feedback."""
    _boot(_STRATEGY, tmp_path / "s-part.db", "profile", "2 of 6 sections", _SIGNED_IN)


def test_strategy_shows_saved_values_as_read_only_chips(tmp_path):
    """Chips describe the SAVED profile, so they belong with the summary and
    not under the input that edits them."""
    _boot(_STRATEGY, tmp_path / "s-chips.db", "profile", "tl-chip-row", _SIGNED_IN)


def test_strategy_states_what_the_playbook_grounds(tmp_path):
    _boot(_STRATEGY, tmp_path / "s-why.db", "profile", "grading", _SIGNED_IN)


def test_strategy_name_error_survives_the_rerun(tmp_path):
    """A toast would be gone before the trader looked up. The error is state,
    so a page booted with it set must render it."""
    _boot(
        _STRATEGY,
        tmp_path / "s-err.db",
        "0",
        "Strategy name is required",
        json.dumps({"current_user_id": 1, "_strategy_name_error": True}),
        demo_mode=False,
    )


def test_strategy_boots_signed_out_without_a_profile(tmp_path):
    """uid is None for the secrets-fallback legacy user. The page never sees
    it: an ownerless session is refused at the shared auth gate before any
    page body — including this one — runs."""
    _boot(
        _STRATEGY,
        tmp_path / "s-anon.db",
        "0",
        "-",
        json.dumps({"current_user_id": None}),
    )


# ---------------------------------------------------------------------------
# Settings — quiet sections
# ---------------------------------------------------------------------------

_SETTINGS = "9_Settings.py"


@pytest.mark.parametrize("section", ["Profile", "Preferences", "Data", "Danger Zone"])
def test_settings_renders_each_section(section, tmp_path):
    _boot(_SETTINGS, tmp_path / f"set-{section[:4]}.db", "0", section)


def test_settings_encloses_its_destructive_actions(tmp_path):
    """The only bordered object on the page."""
    _boot(_SETTINGS, tmp_path / "set-danger.db", "0", "tl-danger-zone")


def test_settings_states_the_ai_integration_without_calling_it_an_error(tmp_path):
    _boot(_SETTINGS, tmp_path / "set-ai.db", "0", "tl-settings-state")


def test_the_partner_conversation_survives_arriving_on_the_page(tmp_path):
    """Navigating away is not closing the conversation, so arriving on the
    phone destination must render the history that is already in session
    state rather than starting a fresh one.

    Driven through the same subprocess harness as every other boot, with the
    history preset before the first run — which is exactly the state a
    multipage navigation leaves behind.
    """
    import json

    _boot(
        "7_Partner.py",
        tmp_path / "partner.db",
        "0",
        "PERSISTED QUESTION",
        json.dumps(
            {
                "partner_history_1": [
                    {"role": "user", "content": "PERSISTED QUESTION"}
                ]
            }
        ),
    )


def test_the_partner_page_refuses_an_ownerless_session(tmp_path):
    """The harness boots authenticated with no user id — a legacy login.
    Every user-facing service now requires a concrete owner, so this session
    is refused at the shared auth gate before the Partner page body — the
    composer it would otherwise render — ever runs.

    This assertion changed with the Ruling 10 gate: it previously expected
    the Partner's own OWNERLESS_PREVIEW copy, which the page rendered itself;
    an ownerless session no longer reaches page code at all.
    """
    from src.tradelens.ui.components.auth import OWNERLESS_SESSION_MESSAGE

    _boot(
        "7_Partner.py",
        tmp_path / "empty.db",
        "0",
        OWNERLESS_SESSION_MESSAGE,
        json.dumps({"current_user_id": None}),
    )


def test_the_partner_page_states_its_scope_to_a_signed_in_trader(tmp_path):
    """With an owner and no trades yet, the page states what would unlock it
    rather than showing a composer that cannot answer."""
    _boot(
        "7_Partner.py",
        tmp_path / "owned.db",
        "profile",
        "Log at least one completed trade",
        json.dumps({"current_user_id": 1}),
    )
