"""
Static-source polish checks for all 9 Streamlit pages (Phase 3, week6-d3).

These enforce the design-system rules by grepping each page's source — fast,
deterministic, and self-documenting so future sessions can extend them. They do
NOT import the pages (pages run Streamlit at import time); they read source text.
"""

import re
from pathlib import Path

import pytest

PAGES_DIR = Path(__file__).resolve().parents[1] / "src" / "tradelens" / "ui" / "pages"

# Session A: only the active (non-archived) pages are linted. Home/TradeDetail/
# Calendar/Weekly/AI Partner now live in pages/_archive/ (Calendar + Weekly are
# Analytics tabs); they re-enter the app in Session B/C.
ALL_PAGES = [
    "1_NewTrade.py",
    "2_Trades.py",
    "4_Analytics.py",
    "5_Strategy.py",
    "6_Insights.py",
    "9_Settings.py",
]

# Active pages that make AI calls. Pattern detection + the Weekly Review now live
# on the merged Insights & Review page (Analytics is pure analytics again).
AI_PAGES = [
    "6_Insights.py",
]

# Empty-state phrasing that must live in empty_state(), never a raw st.info().
# Extend this list as new empty-state copy appears.
EMPTY_STATE_PHRASES = [
    "no trades",
    "no data",
    "no results",
    "nothing here",
    "no entries",
]

# Emoji blocks (pictographs + dingbats/misc symbols + variation selectors).
# Typographic arrows are intentionally excluded — they are not icon emoji.
_EMOJI = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0000fe00-\U0000fe0f"
    "\U0001f000-\U0001f0ff"
    "]"
)

_HEADING_CALL = re.compile(r"st\.(?:title|header|subheader)\((.*?)\)", re.DOTALL)
_PAGE_ICON = re.compile(r"page_icon\s*=\s*[\"']([^\"']*)[\"']")
_ST_INFO = re.compile(r"st\.info\((.*?)\)", re.DOTALL)


def _src(page: str) -> str:
    return (PAGES_DIR / page).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Constraint 1 — exactly one inject_css() call per page
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page", ALL_PAGES)
def test_exactly_one_inject_css(page):
    assert (
        _src(page).count("inject_css()") == 1
    ), f"{page}: expected exactly one inject_css() call"


# ---------------------------------------------------------------------------
# Constraint 4 — no bare st.error / st.success in the UI layer (use toasts)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page", ALL_PAGES)
def test_no_bare_st_error(page):
    # icon='✕' (U+2715) looks right but fails Streamlit's validate_icon_or_emoji;
    # use '❌' (U+274C) — see test_toast_icons.py for the full story.
    assert "st.error(" not in _src(page), f"{page}: use st.toast(msg, icon='❌')"


@pytest.mark.parametrize("page", ALL_PAGES)
def test_no_bare_st_success(page):
    # icon='✓' (U+2713) looks right but fails Streamlit's validate_icon_or_emoji;
    # use '✅' (U+2705) — see test_toast_icons.py for the full story.
    assert "st.success(" not in _src(page), f"{page}: use st.toast(msg, icon='✅')"


# ---------------------------------------------------------------------------
# Bare-except guard — a bare `except:` swallows stack traces into blank widgets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page", ALL_PAGES)
def test_no_bare_st_exception(page):
    for i, line in enumerate(_src(page).splitlines(), 1):
        assert not re.match(
            r"\s*except\s*:", line
        ), f"{page}:{i}: bare 'except:' — catch a specific exception and toast it"


# ---------------------------------------------------------------------------
# Constraint 5 — empty states go through empty_state(), not st.info()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page", ALL_PAGES)
def test_no_emptystate_st_info(page):
    for call in _ST_INFO.findall(_src(page)):
        low = call.lower()
        for phrase in EMPTY_STATE_PHRASES:
            assert phrase not in low, (
                f"{page}: st.info() contains empty-state phrase {phrase!r} — "
                "use empty_state() instead"
            )


# ---------------------------------------------------------------------------
# No emoji in page headings or page_icon
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page", ALL_PAGES)
def test_no_emoji_in_headings(page):
    src = _src(page)
    for heading in _HEADING_CALL.findall(src):
        assert not _EMOJI.search(heading), f"{page}: emoji in heading: {heading!r}"
    for icon in _PAGE_ICON.findall(src):
        assert not _EMOJI.search(icon), f"{page}: emoji page_icon: {icon!r}"


# ---------------------------------------------------------------------------
# AI spinners must NOT leak a model brand name (Session A, Section 3).
# Copy stays generic ("AI reviews your chart"), never "Fable 5".
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("page", AI_PAGES)
def test_ai_spinner_has_no_model_brand(page):
    spinners = re.findall(r"st\.spinner\(\s*[\"'](.+?)[\"']", _src(page))
    assert spinners, f"{page}: expected at least one st.spinner"
    for text in spinners:
        low = text.lower()
        assert "fable" not in low, f"{page}: spinner leaks a model brand: {text!r}"
        assert "claude" not in low, f"{page}: spinner leaks a model brand: {text!r}"


# ---------------------------------------------------------------------------
# Constraint 2 — emotion picker writes the existing 3 columns, no new ones
# ---------------------------------------------------------------------------


def test_emotion_picker_uses_existing_columns():
    src = _src("1_NewTrade.py")
    for col in ("emotions_before", "emotions_during", "emotions_after"):
        assert col in src, f"emotion column {col} missing from New Trade form"


def test_psychology_step_has_process_notes_field():
    """Item 8: dedicated 'What happened during this trade?' process-notes field."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "tradelens"
        / "ui"
        / "pages"
        / "1_NewTrade.py"
    ).read_text(encoding="utf-8")
    assert "What happened during this trade?" in src
    assert "nt_process_notes" in src
    assert '"trade_process_notes": process_notes' in src  # saved as its own field
    # Emotional field remains separate and untouched.
    assert "How were you feeling during this trade?" in src


# ---------------------------------------------------------------------------
# SP4 Phase B — loading feedback on AI paths
# ---------------------------------------------------------------------------

_COMPONENTS_DIR = PAGES_DIR.parent / "components"

# The modules that OWN an AI call each show a spinner at the call site.
# 1_NewTrade.py itself makes no direct AI call (its AI runs through
# ai_autofill_review, which is asserted here), so it is deliberately absent.
_AI_CALL_OWNERS = [
    PAGES_DIR / "6_Insights.py",
    _COMPONENTS_DIR / "ai_autofill_review.py",
    _COMPONENTS_DIR / "screenshot_analyzer.py",
]


@pytest.mark.parametrize("path", _AI_CALL_OWNERS, ids=lambda p: p.name)
def test_ai_call_owners_show_loading_feedback(path):
    """SP4 Phase B: AI calls take seconds — every module that makes one must
    show a spinner rather than freezing the pane with no feedback."""
    src = path.read_text(encoding="utf-8")
    assert "st.spinner" in src, f"{path.name}: AI call path needs st.spinner feedback"


# ---------------------------------------------------------------------------
# Constraint — New Trade shows exactly one progress system
# ---------------------------------------------------------------------------


def test_new_trade_has_one_progress_component():
    """The wizard used numbered tabs AND a numbered rail on every step.

    Two indicators for one position is noise, and they had to be kept in
    sync by hand. st.tabs is the surviving system: it is also the page's
    navigation, and unlike a rail it renders every step's body each run —
    which is what keeps the save payload's values defined.
    """
    src = _src("1_NewTrade.py")
    assert src.count("render_step_indicator(") == 0
    assert src.count("st.tabs(") == 1


def test_new_trade_steps_are_numbered_once():
    """Step numbers live on the tabs and nowhere else."""
    src = _src("1_NewTrade.py")
    for n, label in enumerate(
        ["Screenshot & AI", "Market Context", "Trade Details", "Psychology"], start=1
    ):
        assert f'"{n} · {label}"' in src


def test_review_hides_blank_rows_instead_of_listing_them():
    """Review & Save must not repeat 'Not entered yet' down the page.

    Blank optional rows collapse to one per-section count; a section with
    nothing filled in is dropped entirely.
    """
    src = _src("1_NewTrade.py")
    assert "value != _NOT_ENTERED" in src
    assert "optional field" in src


# ---------------------------------------------------------------------------
# Constraint — solid teal is reserved for primary actions
# ---------------------------------------------------------------------------

# (page, key fragment) pairs for controls that must NOT read as the primary
# action: resets, regenerates, retries, and destructive controls.
SECONDARY_CONTROLS = [
    ("2_Trades.py", "secondary_jf_clear"),
    ("2_Trades.py", "secondary_delete_btn"),
    ("6_Insights.py", "secondary_ins_wk_regen"),
    ("6_Insights.py", "secondary_ins_wk_retry"),
    ("6_Insights.py", "secondary_ins_dbf_regen"),
    ("6_Insights.py", "secondary_ins_dbf_retry"),
]


@pytest.mark.parametrize(("page", "key"), SECONDARY_CONTROLS)
def test_secondary_controls_use_the_secondary_key_prefix(page, key):
    """The CSS is scoped by widget key, so the key IS the styling contract."""
    assert f'key="{key}"' in _src(page)


def test_design_system_styles_the_secondary_key_prefix():
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    assert "st-key-secondary_" in css
    assert "background: transparent" in css


def test_save_trade_remains_primary():
    """Reserving teal must not demote the action that completes the task."""
    assert 'type="primary", key="edit_save"' in _src("2_Trades.py")
    assert "secondary_edit_save" not in _src("2_Trades.py")
