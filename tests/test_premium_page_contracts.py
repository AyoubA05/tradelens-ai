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


def _src_component(name: str) -> str:
    """Source of a `ui/components/` module.

    Task 9 moved the ledger's row-styling rule out of the page and into
    `components/ledger.py`, so contracts that used to read the page's text
    read the component's instead.
    """
    return (PAGES.parent / "components" / name).read_text(encoding="utf-8")


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
    """The rule moved to components/ledger.py in Task 9, so this follows it.

    It used to look for the token NAMES in the page's source, which worked
    only while the rule lived there. Reading the component's real behaviour is
    a stronger check than reading either file's text: it proves the money
    columns carry the semantic tokens rather than proving the words appear.
    """
    from src.tradelens.ui import design_system as ds
    from src.tradelens.ui.components.ledger import MONEY_COLUMNS, ledger_row_styles

    assert "_ledger_styles" in _src("2_Trades.py"), "the page still styles rows"
    assert MONEY_COLUMNS == ("P&L", "R")
    row = pd.Series({"Result": "Loss", "P&L": "-$314.00", "R": "-1.00R", "Asset": "NQ"})
    styles = dict(zip(row.index, ledger_row_styles(row)))
    assert ds.TL_DANGER in styles["P&L"]
    win = pd.Series({"Result": "Win", "P&L": "$755.00", "R": "3.00R", "Asset": "NQ"})
    assert ds.TL_SUCCESS in dict(zip(win.index, ledger_row_styles(win)))["P&L"]


def test_ledger_marks_result_without_relying_on_colour():
    """The semantic edge is a glyph, so the result survives greyscale and
    colour blindness."""
    from src.tradelens.ui.components.ledger import LEDGER_MARKS

    src = _src("2_Trades.py")
    assert set(LEDGER_MARKS) >= {"Win", "Loss", "Breakeven"}
    assert "LEDGER_MARKS.get" in src


def test_ledger_columns_are_the_scannable_set():
    src = _src("2_Trades.py")
    for column in ("Date", "Asset", "Session", "Setup", "Result", "P&L", "R", "Grade"):
        assert f'"{column}"' in src, column


def test_demo_ledger_uses_human_labels_and_financial_formats():
    from src.tradelens.services.demo import get_demo_df
    from src.tradelens.ui.components.ledger import demo_ledger_frame

    rendered = demo_ledger_frame(
        get_demo_df(as_of=__import__("datetime").date(2026, 8, 8))
    )

    assert list(rendered.columns) == [
        "Date",
        "Asset",
        "Direction",
        "Setup",
        "Session",
        "Result",
        "P&L",
        "R",
    ]
    assert rendered["Session"].str.contains("_").sum() == 0
    assert rendered["P&L"].map(lambda value: value.startswith(("$", "-$"))).all()
    assert rendered["R"].str.endswith("R").all()
    assert rendered["Result"].str.startswith(("▲", "▼", "■")).all()


def test_demo_ledger_humanizes_raw_sessions_and_formats_missing_values():
    from src.tradelens.ui.components.ledger import demo_ledger_frame

    rendered = demo_ledger_frame(
        pd.DataFrame(
            {
                "trade_date": ["2026-08-07", None],
                "asset": ["NQ", None],
                "direction": ["long", None],
                "setup_type": ["order_block", None],
                "session": ["ny_am", None],
                "result": ["win", None],
                "pnl": [1234.5, float("nan")],
                "rr_realized": [2, float("nan")],
            }
        )
    )

    assert rendered.iloc[0].to_dict() == {
        "Date": "2026-08-07",
        "Asset": "NQ",
        "Direction": "Long",
        "Setup": "Order Block",
        "Session": "New York AM",
        "Result": "▲ Win",
        "P&L": "$1,234.50",
        "R": "2.00R",
    }
    assert rendered.iloc[1].to_dict() == {
        "Date": "—",
        "Asset": "—",
        "Direction": "—",
        "Setup": "—",
        "Session": "—",
        "Result": "· —",
        "P&L": "—",
        "R": "—",
    }


def test_demo_ledger_uses_humanized_killzone_when_session_is_absent():
    """Older demo-shaped frames name the session column ``killzone``."""
    from src.tradelens.ui.components.ledger import demo_ledger_frame

    rendered = demo_ledger_frame(
        pd.DataFrame(
            {
                "trade_date": ["2026-08-07"],
                "asset": ["NQ"],
                "direction": ["long"],
                "setup_type": ["order_block"],
                "killzone": ["ny_pm"],
                "result": ["win"],
                "pnl": [125.0],
                "rr_realized": [1.5],
            }
        )
    )

    assert rendered.loc[0, "Session"] == "New York PM"


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


def test_trade_detail_uses_the_dark_surface_tokens():
    """The detail card is a dark panel now, not white paper.

    This test used to assert the opposite — that the near-white content
    tokens must NOT appear here, because a P&L rendered with them was
    invisible on a light card (found in the browser, not in an assertion).
    The card turned dark with the rest of the product, so the same reasoning
    now points the other way: the content tokens are exactly what belongs,
    and the deleted light-workspace tokens are what must not come back.
    """
    src = _src("2_Trades.py")
    for retired in (
        "TL_INK",
        "TL_MUTED",
        "TL_PAPER",
        "TL_SUCCESS_INK",
        "TL_DANGER_INK",
        "var(--tl-ink)",
        "var(--tl-paper)",
    ):
        assert retired not in src, f"{retired} was deleted with the light workspace"
    assert "TL_CONTENT_PRIMARY" in src or "var(--tl-content-primary)" in src
    # The semantic pair moved with the ledger rule into components/ledger.py
    # (Task 9). Asserting it there keeps the contract — the Journal still uses
    # the semantic tokens — without demanding they sit in a file that no
    # longer owns the decision.
    ledger_src = _src_component("ledger.py")
    assert "TL_SUCCESS" in ledger_src and "TL_DANGER" in ledger_src


def test_journal_never_shows_generation_cost():
    """Operator accounting is not review content."""
    src = _src("2_Trades.py")
    assert "Generation cost" not in src
    assert "thinking_summary" not in src


# ---------------------------------------------------------------------------
# Ledger styling — pure, so it can be checked directly
# ---------------------------------------------------------------------------


def _ledger_module():
    """Load the pure shared ledger helpers without booting the Streamlit page."""
    from src.tradelens.ui.components.ledger import (
        LEDGER_MARKS,
        format_money,
        ledger_row_styles,
    )

    return {
        "LEDGER_MARKS": LEDGER_MARKS,
        "format_money": format_money,
        "_ledger_styles": ledger_row_styles,
    }


def test_ledger_styles_never_set_a_row_background():
    ns = _ledger_module()
    row = pd.Series(
        {"Result": "Win", "P&L": "$755.00", "R": "3.00R", "Asset": "NQ"},
    )
    styles = ns["_ledger_styles"](row)
    assert len(styles) == len(row)
    assert not any("background" in s for s in styles)


def test_ledger_styles_colour_only_the_money_columns():
    """Asserts the token, not a literal.

    This read `#B53A43` — a light-workspace danger value deleted in Task 1.
    It passed only because the fixture injected that same string into the
    exec namespace, so it could never have noticed the product had moved to
    `TL_DANGER`. Naming the token is what makes it a real contract.
    """
    from src.tradelens.ui import design_system as ds

    ns = _ledger_module()
    row = pd.Series({"Result": "Loss", "P&L": "-$314.00", "R": "-1.00R", "Asset": "NQ"})
    styles = dict(zip(row.index, ns["_ledger_styles"](row)))
    assert ds.TL_DANGER in styles["P&L"]
    assert ds.TL_DANGER in styles["R"]
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
    marks = ns["LEDGER_MARKS"]
    assert set(marks) >= {"Win", "Loss", "Breakeven"}
    assert len(set(marks.values())) == len(marks), "each result needs its own glyph"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "—"), (0, "$0.00"), (755.0, "$755.00"), (-314.0, "-$314.00")],
)
def test_money_formatting_is_unchanged(value, expected):
    ns = _ledger_module()
    assert ns["format_money"](value) == expected


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


def test_the_full_calendar_stays_a_grid_on_a_phone():
    """Measured at 375px: st.columns wrap at that width, turning a month
    into a 31-row list. Keyed on the calendar form, not on the Journal, so
    every page that mounts the full calendar inherits the one rule."""
    from src.tradelens.ui import design_system as ds

    src = _src("2_Trades.py")
    assert 'st.container(key="tl_full_calendar")' in src

    css = ds.build_css()
    # The GRID rule is the phone-only one; find it by its own declaration so
    # the 44px height rule (which is deliberately global) cannot be mistaken
    # for it.
    at = css.index('.st-key-tl_full_calendar [data-testid="stHorizontalBlock"]')
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
    marker = '.st-key-tl_full_calendar [data-testid="stColumn"] .stButton button'
    assert marker in css, "no rule sizes the calendar day cells"
    height_rule = css[css.index(marker) : css.index(marker) + 200]
    assert "min-height: 44px" in height_rule, height_rule
    assert css.index(marker) < enclosing, "the 44px floor must not be phone-only"

    # These buttons pass help=, which wraps them in a tooltip div, so the
    # child combinator used elsewhere silently matches nothing here.
    assert f"{marker} {{" in css
    assert (
        '.st-key-tl_full_calendar [data-testid="stColumn"] .stButton > button'
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


def test_every_analytics_figure_carries_a_screen_reader_summary():
    """Spec §12: charts carry a text summary of the key insight.

    The plan's version of this task tested nothing of the sort, and Plotly
    gives a screen reader a canvas plus unlabelled SVG paths — the title and
    then silence. Hover tooltips need a pointer, so the numbers are not
    reachable that way either.

    Asserted through the AST rather than a substring count: `summary=` has to
    be present on each individual call, and a page with eight charts and
    eight of the word `summary` somewhere in it is not the same claim.
    """
    import ast

    tree = ast.parse(_src("4_Analytics.py"))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_chart"
    ]
    assert len(calls) >= 8, f"expected every lens's figures, found {len(calls)}"
    for call in calls:
        kwargs = {k.arg for k in call.keywords}
        assert "summary" in kwargs, (
            f"_chart call at line {call.lineno} renders a figure with no text "
            "alternative"
        )


def test_the_chart_helper_refuses_a_figure_with_no_summary():
    """Keyword-only and with no default, so the guard above cannot be
    satisfied by a helper that quietly accepts None."""
    import ast

    tree = ast.parse(_src("4_Analytics.py"))
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_chart"
    )
    assert "summary" in [a.arg for a in fn.args.kwonlyargs]
    idx = [a.arg for a in fn.args.kwonlyargs].index("summary")
    assert fn.args.kw_defaults[idx] is None, "summary must stay required"


def test_the_lens_selector_is_secondary_to_the_question_it_answers():
    """Spec §6.4: the selector is visually secondary to the current
    question's section header.

    The plan proposed `source.index("render_section_header") < source.index(
    "st.radio")`, which passes on this page for the wrong reason — the first
    `render_section_header` in the file is the `_section` helper's body at
    the top, hundreds of lines above the selector, and the header that
    actually states the question is rendered *after* the radio. The test
    would have reported success no matter which way round the page ran.

    What is asserted instead is what a reader gets: the radio carries no
    label of its own to compete with the heading, and the question header is
    the last thing rendered before the lens body. Measured at 1440: the
    question is 36px/700, a lens option 16px/400.
    """
    src = _src("4_Analytics.py")
    radio_at = src.index("st.radio(")
    question_at = src.index("render_section_header(lens,")
    assert radio_at < question_at, "the question must land after the selector"
    assert 'label_visibility="collapsed"' in src[radio_at:question_at]
    # The lens body follows the question, so nothing separates the two.
    assert src.index("_LENS_BODIES[lens](df)") > question_at


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


def test_no_raw_metric_card_reaches_analytics_through_a_component():
    """The contract above reads the page file, and for five raw metric cards
    that was not where they lived.

    The retired `calendar_view` rendered `st.columns(5)` of `st.metric` — a
    second, undesigned KPI system inside a lens that already opens with the
    ruled strip. Measured on the Timing lens at 1440: five `stMetric` nodes
    on screen while this file reported the page clean. A source scan that
    stops at the page cannot see what the page imports, so it follows them.
    """
    src = _src("4_Analytics.py")
    imported = re.findall(r"from src\.tradelens\.ui\.components\.(\w+) import", src)
    for module in imported:
        text = _src_component(f"{module}.py")
        assert "st.metric(" not in text, (
            f"components/{module}.py renders a raw metric card onto Analytics — "
            "the ruled strip is the page's one KPI system"
        )


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
    assert "render_trade_calendar(" in src
    timing = src[src.index("def _render_timing_lens(") :]
    body = timing[: timing.index("def _render_setups_lens(")]
    assert "render_trade_calendar(" in body


def test_there_is_one_full_calendar_implementation():
    """Analytics carried a second calendar of its own.

    `calendar_view.py` predated the dark retarget and never got it: a
    money-positive day was tinted with the brand teal — the colour §4.1
    reserves for actions and focus — while the KPI strip and the ledger use
    green for exactly that meaning, and its remaining colours were literal
    pre-redesign hexes rather than role tokens. It also shipped no textual
    legend, which §6.3 requires of a calendar. Measured on the Timing lens:
    `.tl-cal-legend` count 0 at 1440 and at coarse 375.

    Two implementations is why one of them could rot unnoticed, so the fix
    is one component, not a second retarget.
    """
    components = PAGES.parent / "components"
    assert not (components / "calendar_view.py").exists()
    # A month grid that RENDERS — charts.py also lays out a month, but it
    # returns a Plotly figure and never touches Streamlit, so it cannot be a
    # second mounted calendar.
    owners = set()
    for path in components.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "monthcalendar(" in text and "import streamlit" in text:
            owners.add(path.name)
    assert owners == {
        "trade_calendar.py"
    }, f"more than one component mounts a month grid: {sorted(owners)}"


def test_the_analytics_calendar_states_which_month_it_is_describing():
    """The page's date filter says one thing and the calendar's month says
    another. The old month figures were five bare `st.metric` cards headed
    'Month Net P&L', sitting under a page filtered to 90 days — two windows
    labelled alike. The summary now names the month it belongs to."""
    src = _src("4_Analytics.py")
    assert "show_month_summary=True" in src
    comp = _src_component("trade_calendar.py")
    assert "def month_summary(" in comp
    # Named in days, because the map it reads has no per-trade outcome.
    assert "winning_days" in comp
    assert "win_rate" not in comp


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
    assert "render_trade_calendar(frame" in src
    assert "render_trade_calendar(df_raw" not in src


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
    # The note is still composed here; it is now READ through the shared
    # shell, which is what gives Patterns the same anatomy as the two
    # generated lenses instead of its own.
    assert "view_from_note(" in src
    assert "render_review_reader(" in src
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
    body = src[src.index("actions = [") : src.index('state_key="_ins_patterns')]
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
    Streamlit's renderer with unsafe HTML off.

    This used to assert one exact source line on the page. Task 12 moved
    rendering into the shared reading shell, and an exact-string contract
    would have failed for the move rather than for a safety regression — so
    it now asserts the property where the rendering actually happens: the
    page hands `content_md` to the shell, and every `unsafe_allow_html=True`
    call in the shell is checked (through the AST, in
    `tests/test_review_reader.py`) to carry no generated text.
    """
    import ast

    src = _src("6_Insights.py")
    assert 'content_md=review.get("content_md")' in src
    assert "render_review_reader(" in src
    # The page itself must not paint generated prose into markup.
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and any(
            k.arg == "unsafe_allow_html"
            and isinstance(k.value, ast.Constant)
            and k.value.value is True
            for k in node.keywords
        ):
            dumped = ast.dump(
                ast.Module(body=[ast.Expr(a) for a in node.args], type_ignores=[])
            )
            assert "content_md" not in dumped, f"line {node.lineno}"


def test_the_note_body_gets_the_dark_reading_surface():
    """Spec 7: the thing being read gets its own plane, distinct from the
    filters and controls around it.

    The plane is opened by the shell now, not by each lens — which is what
    stops one lens drifting onto a different surface.
    """
    from src.tradelens.ui import design_system as ds

    assert 'st.container(key="tl_note_sheet")' in _src_component("review_reader.py")
    css = ds.build_css()
    assert ".st-key-tl_note_sheet" in css
    block = css[css.index(".st-key-tl_note_sheet {") :][:220]
    assert "var(--tl-surface-chart)" in block


def test_the_evidence_rail_is_stated_once_per_note_not_under_every_finding():
    """§7.2 is explicit: the rail appears once per note, "not under every
    paragraph".

    This test used to require the opposite, because the page rendered
    `render_research_note`, which embeds a rail inside every numbered
    finding — four findings put four stacked rails on a Patterns note. The
    shell shows one section at a time and one rail, and the rail's confidence
    is the floor across the findings so nothing is overstated.
    """
    src = _src("6_Insights.py")
    assert "render_evidence_rail(" not in src, "the rail belongs to the shell"
    assert "render_research_note(" not in src, "the per-finding rail path"
    assert "_confidence_label" not in src, "the repeated footer label is gone"

    from src.tradelens.ui.components.review_reader import (
        build_note_regions,
        view_from_note,
    )
    from src.tradelens.ui.components.workspace import (
        EvidenceItem,
        ResearchFinding,
        ResearchNote,
    )

    ev = EvidenceItem("e", "n=9", "medium", None)
    note = ResearchNote(
        title="t",
        thesis="th",
        findings=tuple(ResearchFinding(n, f"F{n}", "b", ev) for n in range(1, 5)),
        actions=(),
        evidence_used=(),
        sample="n=9",
        limitation="",
    )
    assert build_note_regions(view_from_note(note)).count("tl-evidence-rail") == 1


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
    # Every opt-in block, not just the first: there is now more than one,
    # and taking css.index() made this test depend on their order.
    # A brace-depth walk, not a regex: these blocks contain @keyframes, so
    # any fixed-nesting pattern strips only part of them and the "outside"
    # half then still contains what it was meant to exclude.
    inside, outside, cursor = "", "", 0
    for match in re.finditer(
        r"@media \(prefers-reduced-motion: no-preference\)[^{]*\{", css
    ):
        if match.start() < cursor:
            continue
        depth, i = 1, match.end()
        while i < len(css) and depth:
            depth += (css[i] == "{") - (css[i] == "}")
            i += 1
        outside += css[cursor : match.start()]
        inside += css[match.end() : i - 1]
        cursor = i
    outside += css[cursor:]

    assert "tl-skeleton-pulse" in inside
    # …and it is not ALSO declared outside one, where it would run for a
    # reader who asked for less motion.
    assert "animation: tl-skeleton-pulse" not in outside


def test_dark_surface_overrides_name_both_reading_surfaces():
    """There are TWO dark reading surfaces: `.tl-note`, the note we compose
    ourselves, and `.st-key-tl_note_sheet`, the container a generated review
    is written into. The Evidence Rail and the numbered finding are built
    once and used on both, so a rule naming only one leaves the other
    unstyled and every repaint has to name both.

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
        # search every block for this selector, not the first: a selector
        # legitimately appears in more than one rule (size here, colour
        # elsewhere), and the floor is only in one of them.
        blocks = [
            m.group(1)
            for m in re.finditer(re.escape(selector) + r"[^{}]*\{([^{}]*)\}", css)
        ]
        assert blocks, f"no rule for {selector}"
        assert any("44px" in b for b in blocks), selector

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
        '[data-testid="stDownloadButton"] button',
        '[data-testid="stFileUploader"] button',
        '[data-testid="stSelectbox"] [data-baseweb="select"] > div',
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


def test_the_button_label_colour_reaches_tooltip_wrapped_buttons():
    """The floor above learned the `>` lesson; the colour rule had not.

    A button passing ``help=`` is wrapped in a tooltip div, so
    ``.stButton > button`` never matches it — and config.toml's
    ``primaryColor`` then paints a primary button teal with Streamlit's own
    WHITE label. Measured on Strategy's "Apply the ICT/SMC starter playbook"
    at 1.61:1 against the teal, at all four audited widths, while every other
    primary button in the product was correctly dark-on-teal.

    Guarding the rule that declares the colour, not one page's markup: the
    next control to pass ``help=`` must inherit the fix rather than rediscover
    the bug.
    """
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)

    declaring = [
        m
        for m in re.finditer(r"([^{}]*\.stButton[^{}]*)\{([^{}]*)\}", css)
        if "color:" in m.group(2) and "stSidebar" not in m.group(1)
    ]
    assert declaring, "nothing declares a label colour for .stButton"
    for m in declaring:
        assert ">" not in m.group(1), (
            "a tooltip-wrapped button escapes this colour rule: " + m.group(1).strip()
        )


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
    assert src.count("st.expander(PLAYBOOK_SECTIONS[") == 5
    assert src.count('st.expander("Build a playbook manually"') == 1


def test_profile_completion_is_reported():
    src = _strategy_src()
    component = _src_component("strategy_profile.py")
    assert "def profile_completion(" in component
    assert "profile_completion(profile)" in src
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
    body = _src_component("strategy_profile.py")
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
    assert "Saves this complete starter playbook as your active profile" in src
    assert "You can edit every rule afterward." in src
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
    assert "_write(_STARTER_ERROR_KEY, **dict(STARTER_TEMPLATE))" in src
    assert "_write(\n                _SAVE_ERROR_KEY," in src


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


def test_ownerless_demo_is_complete_read_only_and_sidebar_coherent(tmp_path):
    """The page and rail consume one complete demo fixture, with no write UI
    and no ownerless persistence call available behind that presentation."""
    _strategy_flow("ownerless_demo_is_one_read_only_profile", tmp_path)


def test_real_empty_account_has_one_primary_and_collapsed_manual_route(tmp_path):
    """Starter save leads; manual construction remains reachable but quiet."""
    _strategy_flow("real_empty_account_has_collapsed_onboarding", tmp_path)


def test_stored_profile_maintenance_stays_direct_and_persistent(tmp_path):
    """Onboarding disclosure must not wrap a profile after it exists."""
    _strategy_flow("stored_profile_is_directly_editable", tmp_path)


# ---------------------------------------------------------------------------
# Settings — quiet, safe, and clearly secondary
# ---------------------------------------------------------------------------


def _settings_src() -> str:
    return _src("9_Settings.py")


def test_settings_declares_its_four_sections():
    src = _settings_src()
    assert (
        'SETTINGS_SECTIONS = (\n    "Profile",\n    "Preferences",\n'
        '    "Data",\n    "Danger Zone",\n)' in src
    )


def test_settings_stops_being_seven_stacked_subheaders():
    """Seven st.subheaders behind six dividers is a list of everything the
    app can do, not a settings page."""
    src = _settings_src()
    assert "st.subheader(" not in src
    assert src.count("st.divider()") == 0


def test_settings_uses_the_shared_masthead_like_every_other_page():
    src = _settings_src()
    assert "render_workspace_header(" in src
    assert "section_header(" not in src.replace("render_section_header(", "")


def test_no_status_paints_semantic_text_on_its_own_tint():
    """Measured in Task 1: any semantic hue on a 10% tint of the same hue
    fails AA at every tint strength. Three of these were inline-styled here,
    which also retyped tokens the page is not allowed to override."""
    src = _settings_src()
    for banned in (
        "var(--tl-success-dim)",
        "var(--tl-danger-dim)",
        "var(--tl-primary-dim)",
    ):
        assert banned not in src, banned
    assert "style=" not in src, "no inline style overrides on this page"


def test_a_missing_api_key_is_not_painted_as_an_error():
    """Red means an error or a loss. Not having configured an optional
    integration is neither — it is a state with an action attached."""
    src = _settings_src()
    assert "AI Disabled" not in src
    assert "❌" not in src and "✅" not in src and "🔬" not in src


def test_saving_a_preference_reports_in_place():
    """A toast auto-dismisses and sits nowhere near the control. Settings
    are saved one at a time, so the confirmation belongs beside the one that
    changed."""
    src = _settings_src()
    assert "def _render_setting_status(" in src
    assert "_render_setting_status(" in src
    assert 'st.toast("Trading timezone saved' not in src


def test_settings_has_no_oversized_or_promotional_button():
    """Nothing on this page is the primary action of the product."""
    src = _settings_src()
    assert 'width="stretch"' not in src
    assert 'type="primary"' not in src
    assert "Open Dashboard" not in src


def test_destructive_actions_sit_in_their_own_bordered_section():
    src = _settings_src()
    assert "tl-danger-zone" in src
    # …and it is the last thing on the page
    assert src.index("tl-danger-zone") > src.index('"Data"')


def test_destructive_actions_keep_typed_confirmation_and_consequences():
    src = _settings_src()
    assert "DELETE MY ACCOUNT" in src
    assert 'typed != "DELETE"' in src
    assert "cannot be undone" in src
    assert "Export your trades first" in src


def test_settings_never_shows_the_exception_to_the_trader():
    """Same rule as the playbook: driver text can carry a DSN."""
    src = _settings_src()
    assert "{exc}" not in src
    assert "str(exc)" not in src
    assert "_log.exception(" in src


def test_the_csv_service_does_not_hand_the_page_an_exception_to_render():
    """Settings renders import errors verbatim, so the leak was transitive:
    the page was clean and the service was not."""
    import inspect

    from src.tradelens.services import csvio

    source = inspect.getsource(csvio)
    assert "{exc}" not in source
    assert "except Exception as exc" not in source
    assert "_log.exception(" in source
    # the row number is the actionable part and must survive
    assert "Row {row}" in source


def test_the_danger_zone_border_encloses_the_whole_container():
    """A border on the heading markup alone would draw a box around a title
    and leave both destructive actions outside it. Streamlit renders the
    expanders as siblings of that markup, so the border belongs on the
    keyed container.

    The colour changed in Task 13: the perimeter is the neutral strong line,
    not the danger hue. Spec §6.7 names TL_LINE_STRONG for it, and red stays
    on the heading and the two destructive buttons, where it is the only
    thing carrying the warning. This assertion previously required
    `var(--tl-danger)` here, which is the state Task 13 supersedes — the
    containment property it was written to protect is unchanged.
    """
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)
    keyed = re.search(r"\.st-key-tl_danger_zone \{([^{}]*)\}", css)
    assert keyed, "the keyed container carries no rule"
    assert "border: 1px solid var(--tl-line-strong)" in keyed.group(1)
    # …and the heading markup does not draw its own box
    heading = re.search(r"(?<![\w-])\.tl-danger-zone \{([^{}]*)\}", css)
    if heading:
        assert "border:" not in heading.group(1), heading.group(1)


def test_settings_keeps_every_action_it_had():
    src = _settings_src()
    for call in (
        "export_trades_csv(",
        "import_trades_csv(",
        "load_sample_trades(",
        "clear_sample_trades(",
        "set_timezone(",
        "set_email(",
        "delete_all_trades(",
        "delete_account(",
        "monthly_cost_by_feature(",
    ):
        assert call in src, call


def test_settings_stays_out_of_primary_navigation():
    from src.tradelens.ui.components import sidebar

    assert all("Settings" not in label for label, *_ in sidebar.PRIMARY_NAV)
    assert any("Settings" in label for label, *_ in sidebar.UTILITY_NAV)


# ---------------------------------------------------------------------------
# Settings — real interactions, driven under AppTest in a subprocess.
# ---------------------------------------------------------------------------

_SETTINGS_RUNNER = ROOT / "tests" / "settings_flow_check.py"


def _settings_flow(scenario: str, tmp_path):
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / (scenario + '.db')}"
    env["DEMO_MODE"] = "true"
    proc = subprocess.run(
        [sys.executable, str(_SETTINGS_RUNNER), str(ROOT), scenario],
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
    )
    assert proc.returncode == 0, (
        f"{scenario} failed (rc={proc.returncode})\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )


def test_changing_a_preference_saves_and_reports_beside_it(tmp_path):
    _settings_flow("timezone_saves_and_reports_in_place", tmp_path)


def test_sample_data_loads_clears_and_leaves_real_trades_alone(tmp_path):
    _settings_flow("sample_data_loads_and_clears", tmp_path)


def test_export_supplies_only_the_signed_in_users_rows(tmp_path):
    """The bytes the PAGE hands to the download control are captured and
    inspected. Recreating the same CSV in the test would prove the service
    works, not the page — an export wired to an unscoped query would pass."""
    _settings_flow("export_supplies_only_the_signed_in_users_rows", tmp_path)


def test_account_deletion_completes_and_clears_the_session(tmp_path):
    """Locked for a wrong phrase and two near misses, unlocked by the exact
    one, then: no UI exception, the row gone, the session cleared, and a
    second account and its trades untouched."""
    _settings_flow("account_deletion_completes", tmp_path)


def test_a_failed_csv_import_leaks_nothing(tmp_path):
    """The page renders whatever import_trades_csv puts in `errors`, so the
    service is the boundary. A driver error there used to arrive verbatim,
    DSN and SQL included."""
    _settings_flow("csv_import_failure_leaks_nothing", tmp_path)


def test_destructive_actions_are_actually_gated(tmp_path):
    """A confirmation that renders but does not gate is worse than none —
    it reads as protection. Checked with wrong text, near-miss text, and
    the exact phrase, for both actions."""
    _settings_flow("destructive_actions_are_gated", tmp_path)


# ---------------------------------------------------------------------------
# Task 10 — cross-page hardening
# ---------------------------------------------------------------------------

_UI_PAGES_ALL = [
    "1_NewTrade.py",
    "2_Trades.py",
    "4_Analytics.py",
    "5_Strategy.py",
    "6_Insights.py",
    "9_Settings.py",
]


def test_no_live_page_renders_a_bare_exception():
    """A domain error carries a message written for the trader and may be
    shown. Anything caught by a bare `except Exception` is a driver, network
    or parser message that can carry a DSN, an API key or a fragment of the
    row — it goes to the log, never to the page.
    """
    import re as _re

    offenders = []
    roots = [PAGES] + [
        ROOT / "src" / "tradelens" / "ui" / "components",
        ROOT / "src" / "tradelens" / "services",
    ]
    for root in roots:
        for path in root.glob("*.py"):
            src = path.read_text(encoding="utf-8")
            for match in _re.finditer(
                r"except\s+Exception(?:\s*\)?)?\s+as\s+(\w+)\s*:(.*?)(?=\n    (?:except|else|finally)|\n\S|\Z)",
                src,
                _re.S,
            ):
                name, body = match.group(1), match.group(2)
                rendered = [
                    line
                    for line in body.splitlines()
                    if f"{{{name}}}" in line or f"str({name})" in line
                ]
                if rendered:
                    offenders.append(f"{path.name}: {rendered[0].strip()[:70]}")
    assert not offenders, "bare exception text reaching the UI:\n" + "\n".join(
        offenders
    )


def test_the_csv_boundary_keeps_the_row_number_and_nothing_else():
    from src.tradelens.services import csvio

    assert "Row {row}" in csvio._ROW_FAILED
    assert "{exc}" not in csvio._ROW_FAILED
    assert "{exc}" not in csvio._PARSE_FAILED


def test_every_live_page_scopes_its_reads_to_the_signed_in_user():
    """One account must never read another's rows. Checked at the call site
    because that is where the scope is either passed or forgotten."""
    import re as _re

    scoped = (
        "get_trades",
        "get_active_strategy",
        "get_weekly_review",
        "get_timezone",
        "count_sample_trades",
        "delete_all_trades",
        "monthly_cost_by_feature",
    )
    offenders = []
    for name in _UI_PAGES_ALL + ["../app.py"]:
        path = (PAGES / name).resolve()
        src = path.read_text(encoding="utf-8")
        for fn in scoped:
            for match in _re.finditer(rf"\b{fn}\(", src):
                depth, i = 0, match.end() - 1
                while i < len(src):
                    depth += (src[i] == "(") - (src[i] == ")")
                    if depth == 0:
                        break
                    i += 1
                call = src[match.end() : i]
                if "user_id" not in call and "uid" not in call:
                    offenders.append(f"{path.name}: {fn}({call.strip()[:40]})")
    assert not offenders, "unscoped reads:\n" + "\n".join(offenders)


def test_the_primary_action_label_inherits_its_link_colour():
    """The link paints dark-on-teal, but Streamlit renders the label as a
    <p> inside a markdown container and the rail's text rule repainted it
    near-white — 1.33:1 on the product's most prominent action."""
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)
    rule = re.search(
        r'\.st-key-tl_nav_action \[data-testid="stPageLink-NavLink"\] \*[^{}]*\{([^{}]*)\}',
        css,
    )
    assert rule, "the label is not tied to the link's colour"
    assert "color: inherit" in rule.group(1)


def test_page_chrome_type_is_anchored_so_the_system_controls_it():
    """A lone class loses to Streamlit's markdown stylesheet: the masthead
    declared 30px and rendered 44, the section title declared 22 and
    rendered 36. (24px was the phone override, which never applied.)"""
    from src.tradelens.ui import design_system as ds

    sels = _selectors(ds.build_css())
    for selector in (
        ".tl-masthead-title",
        ".tl-masthead-subtitle",
        ".tl-section-title",
        ".tl-section-subtitle",
    ):
        assert selector not in sels, f"{selector} declares type unanchored"
        assert f"{_APP} {selector}" in sels, selector


def test_a_data_table_scrolls_inside_its_own_frame():
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)
    rule = re.search(r'\[data-testid="stDataFrame"\] \{([^{}]*)\}', css)
    assert rule and "overflow-x: auto" in rule.group(1)


def test_anchored_headings_keep_a_line_box_taller_than_their_type():
    """Anchoring the font-size made the declaration authoritative — and the
    old line-heights, previously overridden by Streamlit, suddenly applied.
    44px text on a 36px line collides on any title that wraps."""
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)
    for selector in (".tl-masthead-title", ".tl-section-title"):
        for block in re.finditer(re.escape(selector) + r"[^{}]*\{([^{}]*)\}", css):
            body = block.group(1)
            size = re.search(r"font-size:\s*(\d+)px", body)
            lead = re.search(r"line-height:\s*(\d+)px", body)
            if size and lead:
                assert int(lead.group(1)) > int(size.group(1)), (
                    f"{selector}: {size.group(1)}px type on a "
                    f"{lead.group(1)}px line"
                )


def test_disabled_controls_keep_streamlits_dimming():
    """WCAG 1.4.3 exempts text in an inactive control, and the dimming IS
    the disabled affordance — a disabled multiselect's label measured
    2.42:1 on Analytics and must stay that way. Raising it would make an
    unavailable control look available, which is the worse defect."""
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)
    for match in re.finditer(r"([^{}]*)\{([^{}]*)\}", css):
        selector, body = match.group(1), match.group(2)
        # A :not(:disabled) selector targets the OPPOSITE of a disabled
        # control — the read-only field whose value the trader is meant to
        # read — so the negation is removed before asking whether this rule
        # is about disabled controls at all. Without this the guard fired on
        # the rule that exists to keep read-only text legible.
        targets = re.sub(r":not\(:?\[?disabled\]?\)", "", selector)
        if "disabled" not in targets:
            continue
        if "color:" not in body:
            continue
        # the only permitted disabled recolour is the danger zone stepping
        # its own buttons DOWN to the muted token, never up to ink
        assert "var(--tl-content-primary)" not in body, selector.strip()


def test_baseline_legibility_never_sits_inside_a_hover_query():
    """Legibility is not a hover state.

    The primary action's label inherits the link's dark colour so it is not
    repainted near-white on teal. That rule was written INSIDE
    `@media (hover: hover) and (pointer: fine)`, which meant every touch
    device kept the 1.33:1 label — and a desktop browser merely resized to
    375px would never reveal it, because `hover: hover` still matches when
    only the viewport changes. Colour rules stay out; :hover stays in.
    """
    from src.tradelens.ui import design_system as ds

    css = re.sub(r"/\*.*?\*/", "", ds.build_css(), flags=re.S)
    for match in re.finditer(r"@media\s*\(hover:\s*hover\)[^{]*\{", css):
        depth, i = 1, match.end()
        while i < len(css) and depth:
            depth += (css[i] == "{") - (css[i] == "}")
            i += 1
        block = css[match.end() : i - 1]
        for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", block):
            selector, body = rule.group(1).strip(), rule.group(2)
            if "color:" not in body:
                continue
            assert (
                ":hover" in selector or ":active" in selector
            ), f"non-hover colour rule inside a hover query: {selector}"

    # …and the inheritance rule itself sits at nesting depth 0, i.e. inside
    # no at-rule at all. Splitting the stylesheet on the first "@media"
    # would be wrong: the rail has hover queries above this one.
    needle = '.st-key-tl_nav_action [data-testid="stPageLink-NavLink"] p'
    depth = 0
    for token in re.finditer(r"[{}]", css[: css.index(needle)]):
        depth += 1 if token.group(0) == "{" else -1
    assert depth == 0, (
        f"the label inheritance rule is nested {depth} level(s) deep, "
        "so it is conditional"
    )
