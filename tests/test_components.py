"""
Tests for reusable UI component factories (Phase 1, week6-d1).

The factories are PURE string builders (no streamlit calls), so they unit-test
without a running app. One AppTest smoke test proves they render inside a real
Streamlit run without raising.
"""

from pathlib import Path

from src.tradelens.ui.components import theme
from src.tradelens.ui.components.ui import (
    empty_state,
    grade_chip,
    killzone_badge,
    kpi_card,
    section_header,
)

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# kpi_card
# ---------------------------------------------------------------------------


def test_kpi_card_contains_label_and_value():
    html = kpi_card("Win Rate", "62%")
    assert "Win Rate" in html
    assert "62%" in html


def test_kpi_card_value_uses_mono_font():
    html = kpi_card("Net P/L", "$1,240")
    assert theme.MONO_FONT in html


def test_kpi_card_positive_delta_is_teal():
    html = kpi_card("Net P/L", "$1,240", delta="+$320")
    assert theme.TEAL in html


def test_kpi_card_negative_delta_is_terra():
    html = kpi_card("Net P/L", "-$80", delta="-$120")
    assert theme.TERRA in html


def test_kpi_card_no_delta_renders():
    html = kpi_card("Trades", "60")
    assert "Trades" in html and "60" in html


# ---------------------------------------------------------------------------
# grade_chip
# ---------------------------------------------------------------------------


def test_grade_chip_a_plus_is_teal():
    assert theme.TEAL in grade_chip("A+")


def test_grade_chip_f_is_terra():
    assert theme.TERRA in grade_chip("F")


def test_grade_chip_unknown_grade_is_safe():
    html = grade_chip("Z")
    assert theme.TEXT_MUTED in html  # falls back to muted, no crash


def test_grade_chip_none_is_safe():
    assert isinstance(grade_chip(None), str)


# ---------------------------------------------------------------------------
# killzone_badge
# ---------------------------------------------------------------------------


def test_killzone_badge_known_label():
    assert "NY AM" in killzone_badge("ny_am")


def test_killzone_badge_unknown_titlecased():
    assert "Tokyo" in killzone_badge("tokyo")


def test_killzone_badge_empty_returns_empty():
    assert killzone_badge("") == ""


# ---------------------------------------------------------------------------
# section_header
# ---------------------------------------------------------------------------


def test_section_header_title_only():
    html = section_header("Performance")
    assert "Performance" in html


def test_section_header_with_subtitle():
    html = section_header("Performance", "Last 30 days")
    assert "Performance" in html and "Last 30 days" in html


# ---------------------------------------------------------------------------
# empty_state
# ---------------------------------------------------------------------------


def test_empty_state_message():
    html = empty_state("No trades yet")
    assert "No trades yet" in html


def test_empty_state_with_cta_renders_link():
    html = empty_state("No trades yet", cta_label="Log a trade", cta_href="/NewTrade")
    assert "Log a trade" in html and "/NewTrade" in html


def test_empty_state_without_cta_has_no_anchor():
    html = empty_state("Nothing here")
    assert "tl-empty-cta" not in html


# ---------------------------------------------------------------------------
# Architecture + render smoke test
# ---------------------------------------------------------------------------


def test_ui_module_is_streamlit_free():
    """Factories must be pure string builders — no direct streamlit dependency."""
    src = (ROOT / "src" / "tradelens" / "ui" / "components" / "ui.py").read_text()
    assert "import streamlit" not in src


def test_components_render_in_apptest():
    from streamlit.testing.v1 import AppTest

    script = (
        "import sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "import streamlit as st\n"
        "from src.tradelens.ui.components.theme import inject_css\n"
        "from src.tradelens.ui.components.ui import (\n"
        "    kpi_card, grade_chip, killzone_badge, section_header, empty_state,\n"
        ")\n"
        "inject_css()\n"
        "st.markdown(kpi_card('Net P/L', '$1,240', delta='+$320'), unsafe_allow_html=True)\n"
        "st.markdown(grade_chip('A+'), unsafe_allow_html=True)\n"
        "st.markdown(killzone_badge('ny_am'), unsafe_allow_html=True)\n"
        "st.markdown(section_header('Performance', 'Last 30 days'), unsafe_allow_html=True)\n"
        "st.markdown(empty_state('No trades', cta_label='Log', cta_href='/NewTrade'),"
        " unsafe_allow_html=True)\n"
    )
    at = AppTest.from_string(script).run()
    assert not at.exception
