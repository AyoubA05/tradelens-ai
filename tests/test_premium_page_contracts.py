"""
Structural contracts for the redesigned product destinations.

These assert the *composition* the specification asks for — how many views a
page has, what carries selection, what may not appear — rather than prose.
Behaviour lives in the pages' own suites; this file is the guard that stops
a page drifting back into the shape it was redesigned out of.

Task 5 covers Journal. Later tasks extend this file for Analytics, AI
Reviews, Strategy Profile and Settings.
"""

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
