"""
Structural contracts for the redesigned product destinations.

These assert the *composition* the specification asks for — how many views a
page has, what carries selection, what may not appear — rather than prose.
Behaviour lives in the pages' own suites; this file is the guard that stops
a page drifting back into the shape it was redesigned out of.

Task 5 covers Journal. Later tasks extend this file for Analytics, AI
Reviews, Strategy Profile and Settings.
"""

import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGES = ROOT / "src" / "tradelens" / "ui" / "pages"


def _src(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Journal — three views
# ---------------------------------------------------------------------------


def test_journal_exposes_exactly_three_views():
    src = _src("2_Trades.py")
    assert 'JOURNAL_VIEWS = ("Trades", "Calendar", "Trade Detail")' in src


def test_journal_renders_one_view_at_a_time():
    """Three views stacked down one page is the wall the redesign replaces."""
    src = _src("2_Trades.py")
    assert "_VIEW_KEY" in src
    assert "st.segmented_control(" in src or "st.radio(" in src


def test_journal_view_selector_carries_the_result_count():
    """Spec 11.3: the count sits next to the view selector, so a trader can
    see what the filters left them with before reading a single row."""
    src = _src("2_Trades.py")
    assert "_result_count_html" in src


def test_selecting_a_trade_opens_the_detail_view():
    src = _src("2_Trades.py")
    assert '_GOTO_KEY] = "Trade Detail"' in src


def test_view_changes_never_write_the_selectors_own_key_mid_run():
    """Streamlit raises StreamlitAPIException on any write to a widget's key
    after that widget is instantiated. "Open this trade" runs below the
    selector, so it records an intent that the next run applies before any
    widget exists. Caught in the browser, not by a boot test — boot tests
    set state before the first run, which is exactly the legal case.
    """
    src = _src("2_Trades.py")
    assert "_VIEW_WIDGET_KEY" in src and "_GOTO_KEY" in src
    # the selector's key and the intent store must not be the same key
    assert '_VIEW_KEY = "journal_view"' in src
    assert '_VIEW_WIDGET_KEY = "journal_view_pick"' in src
    # the intent is consumed before the selector is created
    assert src.index("pop(_GOTO_KEY") < src.index("st.radio(")


def test_pending_view_change_resets_the_selector_widget():
    """Setting only the default is not enough: once a widget has its own
    state, the default is ignored, so the widget state has to go."""
    src = _src("2_Trades.py")
    assert "st.session_state.pop(_VIEW_WIDGET_KEY, None)" in src


def test_trade_detail_has_a_back_path():
    """A detail view you cannot leave is a dead end."""
    src = _src("2_Trades.py")
    assert "Back to trades" in src


# ---------------------------------------------------------------------------
# Journal — the ledger is quiet
# ---------------------------------------------------------------------------


def test_ledger_has_no_full_row_result_tint():
    """Spec 11.3: win/loss use text and a small semantic mark, never a
    full-row fill. A tinted row makes every losing month look alarming
    before a single number has been read."""
    src = _src("2_Trades.py")
    assert "background-color" not in src, "row tints are gone"
    assert "TL_SUCCESS_DIM" not in src
    assert "TL_DANGER_DIM" not in src


def test_ledger_keeps_colour_on_monetary_text_only():
    src = _src("2_Trades.py")
    assert "_ledger_styles" in src
    # money keeps its sign colour; that is the one place red/green survives
    assert "TL_DANGER_INK" in src and "TL_SUCCESS_INK" in src


def test_ledger_marks_result_without_relying_on_colour():
    """The semantic edge is a glyph, so the result survives greyscale and
    colour blindness."""
    src = _src("2_Trades.py")
    assert "_LEDGER_MARKS" in src


def test_ledger_columns_are_the_scannable_set():
    src = _src("2_Trades.py")
    for column in ("Date", "Asset", "Session", "Setup", "Result", "P&L", "R", "Grade"):
        assert f'"{column}"' in src, column


def test_ledger_keeps_row_selection():
    """Clicking the row is how a trader opens a trade; a ledger you cannot
    click is a report."""
    src = _src("2_Trades.py")
    assert 'on_select="rerun"' in src
    assert 'selection_mode="single-row"' in src


# ---------------------------------------------------------------------------
# Journal — filters are compact
# ---------------------------------------------------------------------------


def test_active_filters_render_as_a_summary():
    src = _src("2_Trades.py")
    assert "render_filter_summary" in src
    assert "_active_filters(" in src


def test_secondary_filters_are_disclosed_not_stacked():
    """Six controls in a permanent well is a second page above the page."""
    src = _src("2_Trades.py")
    assert "More filters" in src


def test_filters_are_preserved():
    src = _src("2_Trades.py")
    for key in ("jf_from", "jf_to", "jf_assets", "jf_session", "jf_result", "jf_setup"):
        assert key in src, key
    assert "_clear_filters" in src


# ---------------------------------------------------------------------------
# Journal — the calendar and the research note
# ---------------------------------------------------------------------------


def test_calendar_view_uses_the_full_calendar_not_the_overview_preview():
    """Overview gets the compact preview; Journal is where a trader actually
    works a month, so it keeps the interactive grid."""
    src = _src("2_Trades.py")
    assert "render_trade_calendar(" in src
    assert "compact=True" not in src


def test_generated_summary_renders_as_a_research_note():
    """Spec 11.3: long generated prose leaves the table area and uses the
    shared evidence treatment."""
    src = _src("2_Trades.py")
    assert "render_editorial_readout" in src or "EvidenceItem" in src


def test_journal_preserves_its_ai_and_correction_workflows():
    src = _src("2_Trades.py")
    assert "generate_debrief(" in src
    assert 'log_ai_usage("Trade Summary"' in src
    assert "render_corrections_sidebar" in src
    assert "render_ai_review" in src
    assert "render_ask_ai" in src
    assert "render_screenshot_analyzer" in src


def test_journal_preserves_edit_and_delete_with_confirmation():
    src = _src("2_Trades.py")
    assert "update_trade(" in src
    assert "delete_trade(" in src
    assert "delete_confirm" in src


def test_trade_detail_uses_light_surface_tokens():
    """The detail card is white paper. The dark-instrument text tokens are
    near-white by design, so a P&L rendered with them was invisible on it —
    seen in the browser, not in any assertion."""
    src = _src("2_Trades.py")
    for dark in (
        "var(--tl-text)",
        "var(--tl-text-muted)",
        "var(--tl-text-faint)",
        "var(--tl-success)",
        "var(--tl-danger)",
    ):
        assert dark not in src, f"{dark} is a dark-surface token on a light card"
    assert "var(--tl-ink)" in src
    assert "var(--tl-muted)" in src


def test_journal_never_shows_generation_cost():
    """Operator accounting is not review content."""
    src = _src("2_Trades.py")
    assert "Generation cost" not in src
    assert "thinking_summary" not in src


# ---------------------------------------------------------------------------
# Ledger styling — pure, so it can be checked directly
# ---------------------------------------------------------------------------


def _ledger_module():
    """Load the ledger styling helpers without executing the page.

    The page is a Streamlit script: importing it runs auth, DB access and
    st.set_page_config. The styling rules are pure, so they are extracted
    and exec'd on their own.
    """
    import ast

    src = _src("2_Trades.py")
    tree = ast.parse(src)
    wanted = {"_LEDGER_MARKS", "_ledger_styles", "_fmt_money"}
    kept = [
        node
        for node in tree.body
        if (
            isinstance(node, ast.FunctionDef)
            and node.name in wanted
            or isinstance(node, ast.Assign)
            and any(getattr(t, "id", None) in wanted for t in node.targets)
        )
    ]
    module = ast.Module(body=kept, type_ignores=[])
    namespace = {
        "TL_SUCCESS_INK": "#167A47",
        "TL_DANGER_INK": "#B53A43",
        "TL_MUTED": "#5B6A70",
    }
    exec(compile(module, "<ledger>", "exec"), namespace)  # noqa: S102
    return namespace


def test_ledger_styles_never_set_a_row_background():
    ns = _ledger_module()
    row = pd.Series(
        {"Result": "Win", "P&L": "$755.00", "R": "3.00R", "Asset": "NQ"},
    )
    styles = ns["_ledger_styles"](row)
    assert len(styles) == len(row)
    assert not any("background" in s for s in styles)


def test_ledger_styles_colour_only_the_money_columns():
    ns = _ledger_module()
    row = pd.Series({"Result": "Loss", "P&L": "-$314.00", "R": "-1.00R", "Asset": "NQ"})
    styles = dict(zip(row.index, ns["_ledger_styles"](row)))
    assert "#B53A43" in styles["P&L"]
    assert "#B53A43" in styles["R"]
    assert styles["Asset"] == ""


def test_ledger_styles_leave_breakeven_neutral():
    """Zero is not a loss and not a win."""
    ns = _ledger_module()
    row = pd.Series({"Result": "Breakeven", "P&L": "$0.00", "R": "0.00R"})
    styles = dict(zip(row.index, ns["_ledger_styles"](row)))
    assert styles["P&L"] == ""
    assert styles["R"] == ""


def test_ledger_marks_cover_every_result():
    ns = _ledger_module()
    marks = ns["_LEDGER_MARKS"]
    assert set(marks) >= {"Win", "Loss", "Breakeven"}
    assert len(set(marks.values())) == len(marks), "each result needs its own glyph"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "—"), (0, "$0.00"), (755.0, "$755.00"), (-314.0, "-$314.00")],
)
def test_money_formatting_is_unchanged(value, expected):
    ns = _ledger_module()
    assert ns["_fmt_money"](value) == expected


# ---------------------------------------------------------------------------
# Journal — real interactions, driven under AppTest in a subprocess.
#
# These click. Boot tests set session state before the first run, which is
# exactly the case Streamlit permits, so they can never reach the widget-key
# crash that opening a trade used to cause.
# ---------------------------------------------------------------------------

_FLOW_RUNNER = ROOT / "tests" / "journal_flow_check.py"


def _flow(scenario: str, tmp_path):
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / (scenario + '.db')}"
    env["DEMO_MODE"] = "true"  # never touch the network
    proc = subprocess.run(
        [sys.executable, str(_FLOW_RUNNER), str(ROOT), scenario],
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert proc.returncode == 0, (
        f"{scenario} failed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_ledger_row_opens_detail_and_back_returns(tmp_path):
    """The round trip, including that Back does not bounce and that the
    selected trade's identity survives the view change."""
    _flow("row_to_detail_and_back", tmp_path)


def test_calendar_day_opens_an_individual_trade(tmp_path):
    """Selecting a day offers a focusable opener per trade on that day, and
    it routes through the same intent mechanism as a ledger row."""
    _flow("calendar_day_to_detail", tmp_path)


def test_generated_summary_keeps_markdown_semantics(tmp_path):
    """content_md is a five-section Markdown document. Passed as a readout
    body it is escaped into literal ###, ** and list markers."""
    _flow("summary_markdown", tmp_path)


# ---------------------------------------------------------------------------
# Journal — the generated summary never reaches an HTML-allowing path
# ---------------------------------------------------------------------------


def test_model_output_is_never_rendered_with_unsafe_html():
    """Everything with unsafe_allow_html on this page is our own markup with
    escaped values. Model prose goes through Streamlit's Markdown renderer
    with unsafe HTML off."""
    src = _src("2_Trades.py")
    assert 'st.markdown(_cached["review"].get("content_md") or "")' in src
    assert "render_editorial_readout" not in src, "escapes Markdown into literals"
    assert "render_evidence_rail(" in src, "the evidence treatment is kept"


def test_calendar_data_carries_the_trade_id():
    """Without an id in the frame, a selected day cannot offer openers."""
    src = _src("2_Trades.py")
    assert '"id": t.id' in src
    assert "journal_calopen_" in src
    assert "on_click=_open_trade" in src


def test_only_trade_detail_animates_on_the_journal():
    """Emil: rows, sorting, filtering and hover stay instant — they happen
    dozens of times a session, where motion reads as lag."""
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    block = css[css.index(".st-key-tl_trade_detail {") :][:200]
    assert "animation: tl-detail-in 180ms" in block
    assert "tl-detail-in" in css and "translateY(4px)" in css
    # nothing animates the ledger itself
    for banned in ("stDataFrame", "tl-journal-row", "nth-child"):
        assert (
            f"{banned}" not in css or "animation" not in css[css.index(banned) :][:200]
        )


def test_trade_detail_reveal_respects_reduced_motion():
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    reduced = css[css.index("prefers-reduced-motion") :]
    assert ".st-key-tl_trade_detail" in reduced


def test_journal_calendar_stays_a_grid_on_a_phone():
    """Measured at 375px: st.columns wrap at that width, turning a month
    into a 31-row list. Scoped to the Journal so Overview and Analytics keep
    the calendar behaviour they already had."""
    from src.tradelens.ui import design_system as ds

    src = _src("2_Trades.py")
    assert 'st.container(key="tl_journal_calendar")' in src

    css = ds.build_css()
    # The GRID rule is the phone-only one; find it by its own declaration so
    # the 44px height rule (which is deliberately global) cannot be mistaken
    # for it.
    at = css.index('.st-key-tl_journal_calendar [data-testid="stHorizontalBlock"]')
    # it must sit inside a narrow-screen media query, whatever the project's
    # mobile breakpoint currently is
    enclosing = css.rindex("@media", 0, at)
    assert "max-width" in css[enclosing : enclosing + 60], css[
        enclosing : enclosing + 60
    ]
    assert "flex-wrap: nowrap" in css[at : at + 400]

    # Fitting seven columns across a phone must cost horizontal padding,
    # never the height of the target. A day cell is a button a thumb has to
    # hit, so it holds the same 44px floor as every other control — and at
    # every width, so the rule lives OUTSIDE the mobile media query.
    marker = '.st-key-tl_journal_calendar [data-testid="stColumn"] .stButton button'
    assert marker in css, "no rule sizes the calendar day cells"
    height_rule = css[css.index(marker) : css.index(marker) + 200]
    assert "min-height: 44px" in height_rule, height_rule
    assert css.index(marker) < enclosing, "the 44px floor must not be phone-only"

    # These buttons pass help=, which wraps them in a tooltip div, so the
    # child combinator used elsewhere silently matches nothing here.
    assert f"{marker} {{" in css
    assert (
        '.st-key-tl_journal_calendar [data-testid="stColumn"] .stButton > button'
        not in css
    ), "child combinator does not reach a button wrapped by help="

    # and nothing anywhere may shrink a day cell back below the floor
    for shrunk in ("min-height: 34px", "min-height: 36px", "min-height: 40px"):
        assert shrunk not in css, f"{shrunk} is below the 44px touch minimum"


# ---------------------------------------------------------------------------
# Analytics — one composed instrument panel per lens (Task 6)
# ---------------------------------------------------------------------------


def test_analytics_exposes_exactly_four_lenses():
    src = _src("4_Analytics.py")
    assert 'ANALYTICS_LENSES = ("Performance", "Risk", "Timing", "Setups")' in src


def test_analytics_renders_one_lens_at_a_time():
    """Six stacked sections is the wall this replaces: a trader scrolling
    past four charts to reach the one they wanted is not analysing."""
    src = _src("4_Analytics.py")
    assert "_LENS_BODIES[lens](df)" in src
    for fn in (
        "def _render_performance_lens(",
        "def _render_risk_lens(",
        "def _render_timing_lens(",
        "def _render_setups_lens(",
    ):
        assert fn in src, fn


def test_every_lens_follows_the_same_composition():
    """Spec 11.4: question/scope, ruled strip, dominant instrument, ranked
    evidence, editorial readout. Same order every time, so moving between
    lenses does not mean relearning the page."""
    src = _src("4_Analytics.py")
    assert src.count("render_kpi_strip(") >= 4
    # One readout builder, called once per lens — four copies of the same
    # composition is how they drift apart.
    assert "render_editorial_readout(" in src
    assert src.count("    _readout(") == 4


def test_analytics_uses_the_shared_chart_stage_everywhere():
    """A chart that skips the stage arrives with different margins, a
    different height, and light text on a dark ground."""
    src = _src("4_Analytics.py")
    assert "apply_chart_stage(" in src
    # no page-local restyling of figures survives
    assert "def _styled(" not in src
    assert "template=PLOTLY_TEMPLATE" not in src


def test_analytics_has_no_giant_one_off_metric_cards():
    """Best/Worst Session were full st.metric cards that truncated their own
    values. They belong in the ruled strip with the other measures."""
    src = _src("4_Analytics.py")
    assert "st.metric(" not in src
    assert "Best Session" not in src
    assert "Worst Session" not in src


def test_analytics_keeps_every_calculation():
    """This is a presentation change. Nothing here recomputes anything."""
    src = _src("4_Analytics.py")
    for fn in (
        "compute_basic_metrics",
        "compute_expectancy",
        "compute_profit_factor_raw",
        "compute_max_drawdown",
        "compute_equity_curve",
        "equity_curve_series",
        "drawdown_series",
        "by_session",
        "by_day_of_week",
        "compute_breakdown",
        "outcome_masks",
    ):
        assert fn in src, fn


def test_analytics_keeps_every_chart_it_had():
    src = _src("4_Analytics.py")
    for chart in (
        "equity_curve_chart",
        "drawdown_chart",
        "risk_over_time_chart",
        "pnl_by_session_chart",
        "pnl_by_dow_chart",
        "session_dow_heatmap",
        "win_rate_rules_chart",
        "pnl_by_emotion_chart",
    ):
        assert chart in src, chart


def test_analytics_keeps_the_calendar_under_timing():
    """Daily P&L across a month IS a timing question, so the calendar keeps
    a home rather than being dropped in the regrouping."""
    src = _src("4_Analytics.py")
    assert "render_calendar(" in src
    timing = src[src.index("def _render_timing_lens(") :]
    assert "render_calendar(" in timing[: timing.index("def _render_setups_lens(")]


def test_analytics_states_its_sample_on_the_panel_not_per_chart():
    """Spec 11.4: sample-size annotations at the panel level, not repeated
    inside every chart."""
    src = _src("4_Analytics.py")
    assert "add_sample_annotation(" in src
    assert src.count("add_sample_annotation(") <= 4, "one per lens, not per chart"


def test_analytics_filters_and_empty_states_are_preserved():
    src = _src("4_Analytics.py")
    for key in ("an_from", "an_to", "an_asset", "an_session", "an_strat"):
        assert key in src, key
    assert "No trades in this range yet" in src
    assert "No matching trades" in src


def test_analytics_lens_selector_never_writes_its_own_widget_key():
    """Same Streamlit rule the Journal hit: a write to a widget's key after
    the widget exists raises."""
    src = _src("4_Analytics.py")
    assert "_LENS_WIDGET_KEY" in src
    assert '_LENS_KEY = "analytics_lens"' in src


def test_risk_lens_withholds_a_chart_with_one_distinct_value():
    """A 'risk over time' line through one repeated value is a flat rule
    presented as a finding."""
    from src.tradelens.ui.components.data_state import has_variation

    assert not has_variation(pd.Series([100.0, 100.0, 100.0]))
    assert has_variation(pd.Series([100.0, 250.0]))
    assert not has_variation(pd.Series([], dtype=float))
    assert not has_variation(None)
    assert not has_variation(pd.Series([None, None], dtype=object))


# ---------------------------------------------------------------------------
# Analytics — correction pass
# ---------------------------------------------------------------------------


def test_timing_calendar_uses_the_filtered_frame():
    """Every other figure in the lens answers the filtered question. A
    calendar built from df_raw would quietly disagree with the strip and the
    heatmap directly above it."""
    src = _src("4_Analytics.py")
    assert "render_calendar(frame)" in src
    assert "render_calendar(df_raw)" not in src


def test_a_single_category_is_never_labelled_strongest():
    """'Strongest' implies a field to have been strongest of."""
    src = _src("4_Analytics.py")
    for ranked, only in (
        ("Strongest session", "Only session"),
        ("Strongest day", "Only day"),
        ("Strongest setup", "Only setup"),
    ):
        assert f'"{ranked}" if ' in src, ranked
        assert f'else "{only}"' in src, only


def test_setups_lens_computes_its_own_comparability():
    src = _src("4_Analytics.py")
    assert '_setups_comparable = enough_categories(setup_df, "setup_type")' in src


def test_single_category_readouts_do_not_claim_a_ranking():
    """The readout sentence must not say one thing beat another when there
    was nothing to beat."""
    src = _src("4_Analytics.py")
    assert "Every trade in range was in " in src
    assert "Only {best_setup['setup_type']} was traded in range" in src


def test_one_category_note_does_not_double_escape():
    """render_empty_state escapes its own inputs, so a caller that escapes
    first ships '&amp;' to the reader."""
    from src.tradelens.ui.design_system import render_empty_state

    html = render_empty_state("◆", "One setup so far: BOS & FVG", "body")
    assert "BOS &amp; FVG" in html
    assert "&amp;amp;" not in html

    src = _src("4_Analytics.py")
    assert 'f"One {noun} so far: {row[column]}"' in src
    assert "escape(str(row[column]))" not in src


# ---------------------------------------------------------------------------
# AI Reviews — research notes, not a feed of cards (Task 7)
# ---------------------------------------------------------------------------


def test_ai_reviews_exposes_exactly_three_lenses():
    src = _src("6_Insights.py")
    assert 'AI_REVIEW_LENSES = ("Patterns", "Weekly Recap", "Daily Debrief")' in src


def test_ai_reviews_renders_one_lens_at_a_time():
    src = _src("6_Insights.py")
    assert "_LENS_BODIES[lens]()" in src
    for fn in (
        "def _render_patterns_lens(",
        "def _render_weekly_lens(",
        "def _render_daily_lens(",
    ):
        assert fn in src, fn


def test_patterns_is_a_research_note_not_a_card_grid():
    """Spec 11.5: numbered findings in a real reading sequence, replacing
    the two-column grid of red and green insight cards."""
    src = _src("6_Insights.py")
    assert "render_research_note(" in src
    assert "ResearchNote(" in src
    assert "_insight_card_html" not in src, "the card grid is gone"
    assert "tl-insight-card" not in src
    assert "dcols = st.columns(2)" not in src


def test_patterns_leads_with_a_thesis():
    """One claim first, then the findings that support it. A page of equally
    weighted cards never said which one mattered most."""
    src = _src("6_Insights.py")
    assert "thesis=" in src
    assert "lead, rest = ordered[0], ordered[1:5]" in src


def test_findings_are_capped_at_five():
    src = _src("6_Insights.py")
    assert "ordered[1:5]" in src


def test_next_actions_are_review_actions_never_trade_actions():
    """The product reviews completed trades. An 'action' here is something
    to go and re-read, never something to take."""
    src = _src("6_Insights.py")
    assert "Re-read the trades behind" in src
    body = src[
        src.index("actions = [") : src.index(
            "st.markdown(\n        render_research_note"
        )
    ]
    lowered = body.lower()
    for banned in (
        "buy",
        "sell",
        "go long",
        "go short",
        "signal",
        "entry",
        "take this",
    ):
        assert banned not in lowered, banned


def test_generated_prose_never_reaches_an_html_allowing_path():
    """Same rule as the Journal summary: model markdown goes through
    Streamlit's renderer with unsafe HTML off."""
    src = _src("6_Insights.py")
    assert 'st.markdown(_md_safe(review["content_md"]))' in src


def test_the_note_body_gets_the_dark_reading_surface():
    """Spec 7: filters and controls stay on the light workspace; the thing
    being read gets its own plane."""
    from src.tradelens.ui import design_system as ds

    src = _src("6_Insights.py")
    assert 'st.container(key="tl_note_sheet")' in src
    css = ds.build_css()
    assert ".st-key-tl_note_sheet" in css
    block = css[css.index(".st-key-tl_note_sheet {") :][:220]
    assert "var(--tl-chart-stage)" in block


def test_confidence_is_stated_once_per_finding_not_as_a_footer():
    src = _src("6_Insights.py")
    assert "render_evidence_rail(" in src
    assert "_confidence_label" not in src, "the repeated footer label is gone"


def test_generation_keeps_the_previous_note_until_a_replacement_succeeds():
    """A failed regeneration must not cost the trader the review they had."""
    src = _src("6_Insights.py")
    regen = src[src.index("Regenerate this week") :]
    regen = regen[: regen.index("elif err:")]
    assert "save_weekly_review(review, overwrite=True" in regen
    assert "Could not regenerate" in regen
    # nothing clears the saved review before the new one is written
    assert "delete_weekly_review" not in regen


def test_every_failure_path_offers_retry():
    src = _src("6_Insights.py")
    assert "Retry weekly review" in src
    assert "Retry debrief" in src


def test_daily_debrief_links_back_to_the_journal():
    """Spec 11.5: contributing trades can be opened without losing the note."""
    src = _src("6_Insights.py")
    daily = src[src.index("def _render_daily_lens(") :]
    assert "Open these trades in the Journal" in daily


def test_ai_reviews_lens_selector_never_writes_its_own_widget_key():
    src = _src("6_Insights.py")
    assert '_LENS_KEY = "ai_review_lens"' in src
    assert '_LENS_WIDGET_KEY = "ai_review_lens_pick"' in src


def test_ai_reviews_keeps_its_generation_services():
    src = _src("6_Insights.py")
    for fn in (
        "generate_insights",
        "generate_weekly_review",
        "generate_debrief",
        "save_weekly_review",
        "get_weekly_review",
        "log_ai_usage",
    ):
        assert fn in src, fn


def _selectors(css: str) -> list[str]:
    """Every individual selector in the stylesheet, comments stripped."""
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out: list[str] = []
    for chunk in re.findall(r"(?m)^([^{}]+)\{", body):
        for sel in chunk.split(","):
            sel = " ".join(sel.split())
            if sel and not sel.startswith("@"):
                out.append(sel)
    return out


_APP = '[data-testid="stAppViewContainer"]'
_SHEET = ".st-key-tl_note_sheet"


def _unanchored(sels: list[str]) -> list[str]:
    """Selectors with the app-container anchor stripped off the front."""
    return [s[len(_APP) + 1 :] if s.startswith(_APP + " ") else s for s in sels]


def test_note_headings_outrank_the_global_heading_rule():
    """The workspace paints every h1-h3 in ink, anchored to the app
    container (specificity 0,1,1). A lone class loses to it, which rendered
    the note's own title near-black on the dark sheet — caught in the
    browser. Two classes, or the heading disappears."""
    from src.tradelens.ui import design_system as ds

    sels = _unanchored(_selectors(ds.build_css()))
    for selector in (".tl-note .tl-note-title", ".tl-note .tl-note-actions-title"):
        assert selector in sels, selector
    # the single-class forms must not be what carries the colour
    for weak in (".tl-note-title", ".tl-note-actions-title"):
        assert weak not in sels, weak


_TYPE_SCALE_SELECTORS = (
    ".tl-note-thesis",
    ".tl-note-sample",
    ".tl-note-limitation",
    ".tl-note-generated",
    ".tl-finding-title",
    ".tl-finding-number",
    ".tl-finding-text",
    ".tl-evidence-label",
    ".tl-evidence-claim",
)


def test_component_type_scale_outranks_streamlits_markdown_stylesheet():
    """Streamlit sizes markdown itself: `<container> p { font-size: inherit }`
    and its own h1-h4 sizes, both at specificity 0,1,1. A lone class loses.

    Unanchored, the Evidence Rail's 12px label, 14px claim and 16px body all
    rendered at 16px, and a 17px finding title rendered at 28px — larger than
    the note's own title. The rail had no hierarchy left and the note's was
    inverted. Measured at 375px; no assertion saw it.
    """
    from src.tradelens.ui import design_system as ds

    sels = _selectors(ds.build_css())
    for selector in _TYPE_SCALE_SELECTORS:
        assert selector not in sels, (
            f"{selector} declares type with one class — Streamlit's markdown "
            f"stylesheet outranks it; anchor it to {_APP}"
        )
        assert f"{_APP} {selector}" in sels, selector


def test_the_skeleton_pulse_is_opt_in_not_opt_out():
    """The only motion on this page. Declared inside
    `prefers-reduced-motion: no-preference` rather than switched off inside
    a `reduce` block, so a reader who has asked for less motion never gets
    it at all — not even for the first frame. Verified in the browser with
    the media feature emulated: animation-name computes to `none`.
    """
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    opt_in = css.index("@media (prefers-reduced-motion: no-preference)")
    end = css.index("@media", opt_in + 10)
    assert "tl-skeleton-pulse" in css[opt_in:end]
    # and it is not also declared unconditionally somewhere above
    assert "animation: tl-skeleton-pulse" not in css[:opt_in]


def test_dark_surface_overrides_name_both_reading_surfaces():
    """There are TWO dark reading surfaces: `.tl-note`, the note we compose
    ourselves, and `.st-key-tl_note_sheet`, the container a generated review
    is written into. The Evidence Rail and the numbered finding are built
    once and used on both, so they carry the light workspace's ink by
    default and every repaint has to name both.

    Naming only `.tl-note` left the rail's claim and values at 1.07:1 on the
    generated note — the signature component, invisible, in two of the three
    lenses. No assertion caught it; a contrast probe at 375px did.
    """
    from src.tradelens.ui import design_system as ds

    sels = _unanchored(_selectors(ds.build_css()))
    orphans = [
        s
        for s in sels
        if s.startswith(".tl-note ") and f"{_SHEET} {s[len('.tl-note '):]}" not in sels
    ]
    assert not orphans, f"dark-surface rules missing a sheet twin: {orphans}"


def test_streamlit_own_controls_reach_the_44px_floor():
    """Our components carry the floor themselves; Streamlit's defaults do
    not. Measured at 375px on 1.50.0: lens options 26px, date field 38px,
    sidebar handle 28px. Asserted by selector, not by counting occurrences
    of "44px", so the specific controls stay protected."""
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)
    for selector in (
        '[data-testid="stRadio"] label[data-baseweb="radio"]',
        '[data-testid="stDateInput"] input',
        '[data-testid="stSidebarCollapseButton"] button',
        '[data-testid="stExpandSidebarButton"]',
        '[data-testid="stExpander"] summary',
    ):
        block = re.search(
            re.escape(selector) + r"[^{}]*\{([^{}]*)\}",
            css,
        )
        assert block, f"no rule for {selector}"
        assert "44px" in block.group(1), selector

    # The widget's own label collapses to 0px under label_visibility=
    # "collapsed"; giving it a 44px floor would inject empty space above
    # every lens selector, so the rule must stay on the option labels.
    assert "stWidgetLabel" not in _selectors(css)


def test_the_44px_floor_is_not_hidden_behind_the_phone_breakpoint():
    """A target is a target at every width. A rule that only exists below
    767px regresses silently the moment anyone measures at 1440px."""
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)
    phone = css.index("@media (max-width: 767px)")
    for selector in (
        '[data-testid="stRadio"] label[data-baseweb="radio"]',
        '[data-testid="stDateInput"] input',
        '[data-testid="stExpandSidebarButton"]',
        '[data-testid="stPageLink-NavLink"]',
        '[data-testid="stExpander"] summary',
        '[data-testid="stTextInput"] input',
        ".stButton button",
    ):
        # the rule that DECLARES the floor, wherever it sits
        declaring = [
            m.start()
            for m in re.finditer(re.escape(selector) + r"[^{}]*\{([^{}]*)\}", css)
            if "min-height: 44px" in m.group(1)
        ]
        assert declaring, f"nothing declares a 44px floor for {selector}"
        assert min(declaring) < phone, f"{selector}'s 44px floor is phone-only"

    # …and the rule that declares the button floor must use the descendant
    # combinator: a button passing help= is wrapped in a tooltip div, so
    # `.stButton > button` never reaches it.
    floor = next(
        m
        for m in re.finditer(r"([^{}]*\.stButton[^{}]*)\{([^{}]*)\}", css)
        if "min-height: 44px" in m.group(2) and "stSidebar" not in m.group(1)
    )
    assert ">" not in floor.group(1), floor.group(1).strip()


# ---------------------------------------------------------------------------
# Strategy Profile — a playbook, not a settings dump
# ---------------------------------------------------------------------------


def _strategy_src() -> str:
    return _src("5_Strategy.py")


def test_playbook_declares_its_six_sections():
    src = _strategy_src()
    assert (
        'PLAYBOOK_SECTIONS = (\n    "Identity",\n    "Entry Rules",\n'
        '    "Exit Rules",\n    "Risk Rules",\n    "Setups",\n'
        '    "Self-Awareness",\n)' in src
    )


def test_identity_is_open_and_the_rule_groups_are_accordions():
    """Spec 11.6: identity stays open; rule groups are accordions. A page that
    opens with nine expanded panels is the wall this replaces."""
    src = _strategy_src()
    # Identity is not behind a disclosure at all
    assert 'st.expander("Identity"' not in src
    # …and no section opens expanded
    assert "expanded=True" not in src


def test_expander_count_matches_the_five_collapsed_sections():
    """Eight disclosures for six sections is a settings dump. Stop/Take-profit
    become Exit Rules; setups traded, avoided and session filters become
    Setups."""
    src = _strategy_src()
    assert src.count("st.expander(") == 5


def test_profile_completion_is_reported():
    src = _strategy_src()
    assert "def _profile_completion(" in src
    assert "_render_profile_summary(" in src


def test_the_playbook_says_what_it_is_for():
    """A page of rule fields with no stated purpose reads as configuration.
    This one grounds the AI reviews, and says so once."""
    src = _strategy_src()
    assert "grade" in src.lower() and "review" in src.lower()


def test_save_is_anchored_not_stretched():
    """A full-viewport primary button is a banner, not an action."""
    src = _strategy_src()
    assert 'width="stretch"' not in src
    assert "st.form_submit_button(" in src


def test_required_field_error_is_inline_and_persistent():
    """A toast auto-dismisses and never sits near the field it is about.
    Spec: error below the related field, and it must survive the rerun."""
    src = _strategy_src()
    assert 'st.toast("Strategy Name is required.' not in src
    assert "_NAME_ERROR_KEY" in src


def test_the_photographic_banner_is_gone():
    """PRODUCT.md anti-pattern: decoration behind information. The banner also
    hardcoded rgba(13,15,17,0.75), which is not a token."""
    src = _strategy_src()
    assert "strategy_banner.png" not in src
    assert "rgba(13,15,17" not in src
    assert "background-image" not in src


def test_saved_chips_do_not_sit_inside_the_edit_fields():
    """Chips previewed the SAVED profile directly under the input that edits
    it, so a changed field showed stale values beside itself. Read-only and
    editable states have to be visibly distinct (spec 11.6)."""
    src = _strategy_src()
    form = src[src.index('st.form("strategy_form")') :]
    assert "render_chip_row" not in form


def test_every_stored_field_survives_the_regrouping():
    src = _strategy_src()
    for field in (
        "name",
        "trading_style",
        "markets",
        "timeframes",
        "entry_rules",
        "stop_rules",
        "take_profit_rules",
        "risk_rules",
        "setups_traded",
        "setups_avoided",
        "news_session_rules",
        "common_mistakes",
    ):
        assert f"{field}=" in src, field


def test_starter_template_and_service_calls_are_preserved():
    src = _strategy_src()
    assert "STARTER_TEMPLATE" in src
    assert "upsert_strategy_profile(" in src
    assert "get_active_strategy(" in src


def test_starter_template_leads_only_while_the_playbook_is_empty():
    """One primary action per screen. With a profile saved, Save is the
    primary and the template drops to secondary."""
    src = _strategy_src()
    assert 'type="secondary" if profile else "primary"' in src


def test_completion_is_read_from_the_saved_profile_not_the_form():
    """A figure driven by unsaved keystrokes would claim the AI has context
    it has not been given."""
    src = _strategy_src()
    assert "_render_profile_summary(profile or {})" in src
    body = src[src.index("def _profile_completion(") : src.index("def _facet(")]
    assert "profile.get(" in body
    assert "st.session_state" not in body


def test_the_playbook_animates_the_disclosure_and_nothing_else():
    """Emil pass. Opening a rule section is the one state change worth
    conveying — the panel's contents otherwise appear out of nothing. Save
    is a submit a trader repeats all session, and validation text has to be
    readable the instant it exists; animating either makes the interface
    feel slower at the two moments the user is watching most closely.
    """
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)
    reveal = re.search(
        r'\.st-key-tl_playbook_form \[data-testid="stExpander"\] '
        r"details\[open\] > summary \+ div \{([^{}]*)\}",
        css,
    )
    assert reveal, "no accordion reveal"
    body = reveal.group(1)
    # opacity and transform only, inside the UI window, on the shared curve
    assert "tl-section-in" in body
    assert "180ms" in body
    assert "var(--tl-ease-out)" in body
    frames = re.search(r"@keyframes tl-section-in \{(.*?)\n\}", css, re.S).group(1)
    for banned in ("height", "width", "margin", "padding"):
        assert banned not in frames, banned

    # the two things that must never move
    for still in (".tl-field-error", ".tl-playbook-progress"):
        block = re.search(re.escape(still) + r"[^{}]*\{([^{}]*)\}", css)
        assert block and "animation" not in block.group(1), still


def test_the_accordion_reveal_is_withdrawn_under_reduced_motion():
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    start = css.index("@media (prefers-reduced-motion: reduce)")
    depth, i = 0, css.index("{", start)
    while i < len(css):
        depth += (css[i] == "{") - (css[i] == "}")
        if depth == 0:
            break
        i += 1
    reduce_block = css[start : i + 1]
    assert "st-key-tl_playbook_form" in reduce_block
    assert "details[open] > summary + div" in reduce_block
    assert "animation: none" in reduce_block


def test_the_reveal_is_scoped_to_the_playbook_not_every_expander():
    """Every st.expander in the app carries the same testid. An unscoped
    rule animates the Journal's filters, the wizard's screenshot panel,
    Settings and the auth screen — a page-load flicker on five pages that
    asked for none. The keyed container is what confines it."""
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)
    for match in re.finditer(r"([^{}]*)\{([^{}]*)\}", css):
        if "tl-section-in" not in match.group(2):
            continue
        assert "st-key-tl_playbook_form" in match.group(1), match.group(1).strip()
    # …and the page actually renders that container around the form
    src = _strategy_src()
    assert 'st.container(key="tl_playbook_form")' in src


def test_the_44px_expander_floor_stays_global():
    """The reveal is Strategy-only; the touch target is not. An accordion
    header is a control on every page that has one."""
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)
    floor = re.search(
        r'(?<![\w-])\[data-testid="stExpander"\] summary \{([^{}]*)\}', css
    )
    assert floor, "the expander touch target must stay unscoped"
    assert "min-height: 44px" in floor.group(1)


def test_the_starter_button_says_that_it_saves():
    """It calls upsert_strategy_profile immediately. Copy promising a review
    step before anything is stored describes a different button."""
    src = _strategy_src()
    assert "Apply the ICT/SMC starter playbook" in src
    assert "Saves a complete starter playbook as your active profile" in src
    # the retired promises
    for lie in ("edit before saving", "review and save", "Starter template loaded"):
        assert lie not in src, lie


def test_both_writes_go_through_the_one_protected_path():
    """The starter button wrote outside the guarded path, so a driver error
    there propagated to the page with whatever the exception carried. There
    is now a single _write(); nothing may call the service directly."""
    src = _strategy_src()
    body = src[src.index("def _write(") :]
    calls = [
        line
        for line in body.splitlines()
        if "upsert_strategy_profile(" in line and "def " not in line
    ]
    assert len(calls) == 1, f"writes outside _write(): {calls}"
    assert "_write(_STARTER_ERROR_KEY, **STARTER_TEMPLATE)" in src
    assert "_write(\n            _SAVE_ERROR_KEY," in src


def test_a_failed_starter_write_reports_beside_its_own_button():
    """The save slot is at the foot of a form the trader never opened."""
    src = _strategy_src()
    assert "starter_error_slot" in src
    assert src.index("starter_error_slot = st.empty()") < src.index(
        'st.form("strategy_form")'
    )


def test_save_failure_never_shows_the_exception_to_the_trader():
    """Driver text can carry a database URL, a dialect message or a fragment
    of the row. It belongs in the log."""
    src = _strategy_src()
    assert "Could not save the playbook. Try again." in src
    assert "_log.exception(" in src
    # The exception is never even bound to a name, so there is nothing to
    # interpolate. Checked as code, not as text: the docstring explaining
    # why says "str(exc)" out loud.
    assert "except Exception as" not in src
    assert "{exc}" not in src
    # and the box it lands in still escapes
    from src.tradelens.ui.components.ui import error_box

    assert "<script>" not in error_box("<script>x</script>")


# ---------------------------------------------------------------------------
# Strategy Profile — real interactions, driven under AppTest in a subprocess.
#
# These click, type and then read the DATABASE back. A marker test can only
# prove the page rendered a string; it cannot prove the starter template
# persisted, that a blank name was refused before any write, or that saving
# an edit left the untouched sections alone.
# ---------------------------------------------------------------------------

_STRATEGY_RUNNER = ROOT / "tests" / "strategy_flow_check.py"


def _strategy_flow(scenario: str, tmp_path):
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / (scenario + '.db')}"
    env["DEMO_MODE"] = "true"  # never touch the network
    proc = subprocess.run(
        [sys.executable, str(_STRATEGY_RUNNER), str(ROOT), scenario],
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert proc.returncode == 0, (
        f"{scenario} failed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_starter_playbook_actually_persists(tmp_path):
    """The button says it saves a complete playbook as the active profile.
    This reads the row back and checks every section is written, then that
    the summary reports 6 of 6."""
    _strategy_flow("starter_template_persists", tmp_path)


def test_blank_name_is_refused_before_anything_is_written(tmp_path):
    """No row, plus a field-level message carrying role="alert"."""
    _strategy_flow("blank_name_is_refused", tmp_path)


def test_correcting_the_name_saves_and_clears_the_error(tmp_path):
    """The draft survives the refusal, the corrected form writes, and the
    completion figure follows the saved profile rather than the form."""
    _strategy_flow("correcting_the_name_saves", tmp_path)


def test_a_failed_starter_write_is_contained(tmp_path):
    """The starter write raises with a credential-bearing driver message.
    The page must survive it, render the generic recovery message, leak none
    of the DSN, create no row, and leave an existing playbook untouched."""
    _strategy_flow("starter_write_failure_is_contained", tmp_path)


def test_editing_one_section_preserves_the_untouched_ones(tmp_path):
    """A full profile, one field changed, eleven left alone. The failure
    this catches is a collapsed section's widget defaulting to "" instead
    of the stored value, which silently blanks it on the next save."""
    _strategy_flow("editing_preserves_untouched_fields", tmp_path)
