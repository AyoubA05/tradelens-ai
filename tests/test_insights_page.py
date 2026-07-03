"""
Insights & Review page (Part 3) — Pattern Insights + Weekly Review merged, with
Claude running automatically on page load (no button to trigger it).

Runtime rendering is covered by tests/test_pages_boot.py (the page boots in demo
mode and auto-runs canned AI with zero spend). These gates lock the structural
contract: one merged page, auto-run (not button-gated), a loading indicator,
session-state caching, and specific inline errors instead of "AI unavailable".
"""

from pathlib import Path

PAGE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "tradelens"
    / "ui"
    / "pages"
    / "6_Insights.py"
)


def _src() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_page_exists():
    assert PAGE.exists(), "Insights & Review page must exist at pages/6_Insights.py"


def test_merges_patterns_and_weekly():
    src = _src()
    assert "Insights & Review" in src
    assert "Pattern Insights" in src and "Weekly Review" in src


def test_ai_runs_automatically_not_button_gated():
    """The deeper AI patterns and the weekly review must auto-run on load."""
    src = _src()
    # Auto-run helpers exist and are called at module scope (not behind a click).
    assert "_auto_run_pattern_cards()" in src
    assert "_auto_run_weekly(" in src
    # No "Detect deeper patterns with AI" button gate (the old click-to-run UX).
    assert "Detect deeper patterns with AI" not in src
    assert 'st.button("Generate weekly review"' not in src


def test_uses_spinner_loading_indicator():
    assert "st.spinner(" in _src()


def test_caches_ai_result_in_session_state():
    src = _src()
    assert "_ins_cards" in src  # cached pattern cards
    assert "_ins_sig" in src  # data-signature cache invalidation


def test_specific_inline_error_not_generic_unavailable():
    src = _src()
    # Errors surface the actual reason; never the generic "AI is unavailable".
    assert "AI is unavailable" not in src
    assert "couldn't run:" in src or "Could not" in src
