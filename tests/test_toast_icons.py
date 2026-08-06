"""
Every st.toast(..., icon="...") call must use an icon Streamlit actually accepts.

Root cause of a Streamlit Cloud crash (StreamlitAPIException on Strategy page's
"Use ICT/SMC Starter Template" button): icon="✓" (U+2713 CHECK MARK) looks like
an emoji but Streamlit's validate_icon_or_emoji() rejects it — only "✅" (U+2705
WHITE HEAVY CHECK MARK) validates. Same defect for icon="✕" (U+2715) vs the
valid "❌" (U+274C). Five call sites across two pages used the invalid glyphs;
test_page_polish.py's own guidance text ("use st.toast(msg, icon='✓')") was
telling contributors to reproduce the bug.

This scans every active page's source (no Streamlit import — pages run
Streamlit at import time) and validates each icon literal for real, so any
future non-validating icon fails the suite instead of only surfacing on
Streamlit Cloud when the button is clicked.
"""

import re
from pathlib import Path

import pytest
from streamlit.errors import StreamlitAPIException
from streamlit.string_util import validate_icon_or_emoji

PAGES_DIR = Path(__file__).resolve().parents[1] / "src" / "tradelens" / "ui" / "pages"

ALL_PAGES = [
    "1_NewTrade.py",
    "2_Trades.py",
    "4_Analytics.py",
    "5_Strategy.py",
    "6_Insights.py",
    "9_Settings.py",
]

_TOAST_ICON_RE = re.compile(r'st\.toast\([^)]*icon="([^"]+)"')


def _icons_in(page: str) -> list[str]:
    src = (PAGES_DIR / page).read_text(encoding="utf-8")
    return _TOAST_ICON_RE.findall(src)


@pytest.mark.parametrize("page", ALL_PAGES)
def test_all_toast_icons_are_valid(page):
    icons = _icons_in(page)
    for icon in icons:
        try:
            validate_icon_or_emoji(icon)
        except StreamlitAPIException as exc:
            pytest.fail(f"{page}: icon={icon!r} is invalid — {exc}")


def test_at_least_one_page_uses_toast_icons():
    # Guards against the regex silently matching nothing if st.toast's call
    # style changes (a passing-by-vacuous-truth false negative).
    assert any(_icons_in(page) for page in ALL_PAGES)


_TOAST_CALL_RE = re.compile(r"st\.toast\(([^)]*)\)")


@pytest.mark.parametrize("page", ALL_PAGES)
def test_every_toast_icon_is_a_literal_the_validator_can_see(page):
    """An icon behind a constant is an icon this file cannot validate.

    Found in Task 9. Routing the Journal's three toasts through a module
    constant left `_TOAST_ICON_RE` matching nothing on that page, so all three
    silently dropped out of `test_all_toast_icons_are_valid` while it kept
    reporting green — the same shape of false pass the invalid `✓` icon caused
    on Streamlit Cloud, which is why this file exists. Icons stay inline so the
    validator above actually runs on them.
    """
    src = (PAGES_DIR / page).read_text(encoding="utf-8")
    for call in _TOAST_CALL_RE.findall(src):
        if "icon=" not in call:
            continue
        argument = call.split("icon=", 1)[1].strip()
        assert argument.startswith(('"', "'")), (
            f"{page}: st.toast icon must be an inline literal so it is "
            f"validated, got icon={argument!r}"
        )
