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
    "9_Settings.py",
]

# Active pages that make AI calls (Analytics hosts pattern detection + the
# Weekly Review tab).
AI_PAGES = [
    "4_Analytics.py",
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
    assert "st.error(" not in _src(page), f"{page}: use st.toast(msg, icon='✕')"


@pytest.mark.parametrize("page", ALL_PAGES)
def test_no_bare_st_success(page):
    assert "st.success(" not in _src(page), f"{page}: use st.toast(msg, icon='✓')"


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
