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
    assert "Pattern Insights" in src and "Weekly Recap" in src


def test_ai_runs_automatically_not_button_gated():
    """The deeper AI patterns and the weekly review must auto-run on load."""
    src = _src()
    # The recap auto-run helper exists and is called at module scope.
    assert "_auto_run_weekly(" in src
    # No "Detect deeper patterns with AI" button gate (the old click-to-run UX).
    assert "Detect deeper patterns with AI" not in src
    assert 'st.button("Generate weekly review"' not in src


def test_uses_spinner_loading_indicator():
    assert "st.spinner(" in _src()


def test_caches_ai_result_in_session_state():
    src = _src()
    assert "_wk_err_" in src  # per-week error cache (no retry loop)
    assert "get_weekly_review(monday, uid)" in src  # saved recap reused, no re-spend


def test_specific_inline_error_not_generic_unavailable():
    src = _src()
    # Errors surface the actual reason; never the generic "AI is unavailable".
    assert "AI is unavailable" not in src
    assert "couldn't run:" in src or "Could not" in src


# ---------------------------------------------------------------------------
# Item 10 — one unified Weekly Recap (single AI call), separate sections retired.
# ---------------------------------------------------------------------------


def test_weekly_recap_replaces_patterns_and_review_sections():
    src = _src()
    assert "Weekly Recap" in src
    assert "Deeper AI patterns" not in src  # retired UI section
    assert "detect_patterns" not in src  # no second AI call from this page
    assert 'section_header("Weekly Review")' not in src  # retired UI section
    # Kept as their own sections, per spec:
    assert "Pattern Insights" in src
    assert "Daily Debrief" in src


def test_recap_is_one_call_with_pattern_data():
    """The recap service call receives the pattern statistics in the SAME call
    (compute_candidates feeds the user message) and requires Pattern Signals."""
    from src.tradelens.services import weekly

    assert "### Pattern Signals" in weekly._REQUIRED_SECTIONS
    service_src = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "tradelens"
        / "services"
        / "weekly.py"
    ).read_text(encoding="utf-8")
    assert "compute_candidates(df)" in service_src
    assert 'load_prompt("weekly_recap_v1")' in service_src
