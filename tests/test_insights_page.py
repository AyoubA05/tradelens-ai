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


def test_generation_shows_visible_progress():
    """A spinner collapses the panel, so the page jumps when the review
    lands and the reader loses their place. The skeleton stands in the
    note's own geometry instead, and announces itself."""
    src = _src()
    assert "render_note_skeleton()" in src
    assert src.count("placeholder.markdown(render_note_skeleton()") == 2
    # …and it is cleared once the call returns, whatever the outcome.
    assert src.count("placeholder.empty()") == 2


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
    (compute_candidates feeds the user message) and requires Observed Patterns."""
    from src.tradelens.services import weekly

    assert "### Observed Patterns" in weekly._REQUIRED_SECTIONS
    service_src = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "tradelens"
        / "services"
        / "weekly.py"
    ).read_text(encoding="utf-8")
    assert "compute_candidates(df)" in service_src
    assert 'load_prompt("weekly_recap_v1")' in service_src


# ---------------------------------------------------------------------------
# Customer-facing AI disclosure: evidence, not debug details
# ---------------------------------------------------------------------------

_UI_PAGES = Path(__file__).resolve().parents[1] / "src" / "tradelens" / "ui" / "pages"


def test_insights_does_not_render_model_reasoning_or_cost():
    """Internal generation details are operator data, not review content."""
    src = (_UI_PAGES / "6_Insights.py").read_text(encoding="utf-8")
    assert "thinking_summary" not in src
    assert "How the AI reasoned" not in src
    assert "Generation cost" not in src


def test_journal_does_not_render_generation_cost():
    src = (_UI_PAGES / "2_Trades.py").read_text(encoding="utf-8")
    assert "Generation cost" not in src


_SHELL = (
    Path(__file__).resolve().parents[1] / "src/tradelens/ui/components/review_reader.py"
)


def test_every_lens_uses_the_same_evidence_disclosure():
    """st.expander put the generated lenses' disclosure on the LIGHT
    workspace at 38px, while the composed note's sat on the dark sheet at
    44px — one component, two treatments, two surfaces. Measured at 375px.

    Task 12 moved the rendering into the shared shell, so the disclosure
    assertion follows it there. The page-level half — never reaching for
    st.expander again — still belongs to the page.
    """
    assert "render_evidence_disclosure(" in _SHELL.read_text(encoding="utf-8")
    assert "st.expander(" not in _src(), "the shared <details> builder, not st.expander"


def test_insights_shows_evidence_and_confidence():
    """What a review was based on travels with it.

    The rail is now built once per note by the shell rather than by the page,
    which is the point of §7.2 — so the rail assertion reads the shell and the
    page keeps the parts it still owns: what the note was based on, and the
    confidence band that describes the sample.
    """
    src = _src()
    assert "Trades reviewed" in src
    assert "_confidence_for(" in src
    shell = _SHELL.read_text(encoding="utf-8")
    assert "render_evidence_rail" in shell
    assert "render_evidence_disclosure(" in shell

    from src.tradelens.ui.components.workspace import render_evidence_disclosure

    assert "Evidence used" in render_evidence_disclosure(("Trades reviewed: 3",))


def test_confidence_bands_follow_sample_size():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_insights_probe", _UI_PAGES / "6_Insights.py"
    )
    # The page runs Streamlit at import time, so exercise the pure helper by
    # reading it out of the source rather than importing the module.
    src = (_UI_PAGES / "6_Insights.py").read_text(encoding="utf-8")
    assert spec is not None
    ns: dict = {}
    # The bands are unchanged; they now return the Evidence Rail's own
    # vocabulary (low/medium/high) instead of a second set of words for
    # the same three levels.
    start = src.index("_CONF_BY_SAMPLE = ")
    end = src.index("def _evidence_used")
    exec(src[start:end], ns)  # noqa: S102 — isolated pure function
    level = ns["_confidence_for"]
    assert level(0) == "low"
    assert level(9) == "low"
    assert level(10) == "medium"
    assert level(19) == "medium"
    assert level(20) == "high"
    assert level(200) == "high"


# ---------------------------------------------------------------------------
# Task 12 — one reading shell, and a regeneration that cannot lose a note.
# ---------------------------------------------------------------------------

import os  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

from tests.source_probe import function_source  # noqa: E402

_REGEN_CHECK = Path(__file__).resolve().parent / "insights_regen_check.py"
_ROOT = Path(__file__).resolve().parents[1]


def _regen(mode: str, db_path: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["DEMO_MODE"] = "true"  # never touch the network
    return subprocess.run(
        [sys.executable, str(_REGEN_CHECK), str(_ROOT), mode],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_a_failed_daily_regeneration_keeps_the_note_the_trader_had(tmp_path):
    """The defect this task exists for, proved by doing it.

    `_render_daily_lens` popped the cached note BEFORE calling the generator,
    and the generator writes its replacement only on success — so a
    `DebriefError` left the trader with no review at all. Weekly never did
    this and says so in a comment.

    The plan proposed comparing the source offsets of `.pop(` and
    `_run_daily_debrief(` inside the function. That would pass for a page
    that popped the key in a helper, or one line later, or under a different
    name, and it says nothing about what is on screen. This clicks the real
    control with the real generator raising and reads the rendered page.
    Mutation-checked: restoring the pop makes it fail with
    "FAILED REGENERATION DESTROYED THE PRIOR NOTE".
    """
    proc = _regen("fail", tmp_path / "fail.db")
    assert proc.returncode == 0, f"{proc.stderr[-2000:]}"


def test_a_successful_daily_regeneration_replaces_the_note(tmp_path):
    """The other half: keeping the old note must not mean never replacing it."""
    proc = _regen("succeed", tmp_path / "ok.db")
    assert proc.returncode == 0, f"{proc.stderr[-2000:]}"


def test_the_note_stays_and_the_control_locks_while_a_call_is_in_flight(tmp_path):
    """What the trader sees DURING regeneration, asserted rather than assumed.

    The busy pass is frozen at the moment of the blocking call, because a
    Streamlit button cannot become disabled inside its own handler and the
    two-pass flag is what makes the disabled state reachable at all. AppTest
    resolves `st.rerun()` inside the same `run()`, so clicking would skip
    straight past this pass — the check enters it directly and halts the
    script where the call would sit.

    Mutation-checked both ways: removing `disabled=busy` fails with "still
    live during the call", and removing the progress line fails with "no
    polite inline progress".
    """
    proc = _regen("inflight", tmp_path / "inflight.db")
    assert proc.returncode == 0, f"{proc.stderr[-2000:]}"


def test_no_lens_clears_its_cached_note_before_generating_a_replacement():
    """The structural half of the guard above, so a second lens cannot
    reintroduce the shape somewhere the behavioural check does not look."""
    src = _src()
    for lens in ("_render_daily_lens", "_render_weekly_lens"):
        body = function_source(src, lens)
        run_at = min(
            (
                body.index(marker)
                for marker in ("_run_daily_debrief(", "generate_weekly_review(")
                if marker in body
            ),
            default=len(body),
        )
        before = body[:run_at]
        assert "pop(cache_key)" not in before
        assert "pop(cache_key, None)" not in before


def test_all_three_lenses_render_the_same_period_stats_strip():
    """D7: Weekly and Daily opened with a five-cell strip; Patterns had none,
    so one page answered "how big is this sample" two different ways."""
    src = _src()
    for lens in ("_render_patterns_lens", "_render_weekly_lens", "_render_daily_lens"):
        assert "_note_stats(" in function_source(src, lens), lens


def test_the_patterns_strip_takes_its_figures_from_the_service():
    """Not recomputed on the page: `period_stats` assembles what the metrics
    service returns."""
    src = _src()
    assert "period_stats(df)" in function_source(src, "_render_patterns_lens")


def test_the_regenerate_control_is_disabled_while_a_call_is_in_flight():
    """D8. A Streamlit button cannot become disabled during its own handler —
    the script run is blocking, so `disabled=` alone is not a fix. Both lenses
    use the two-pass flag: the click records intent and reruns, and the next
    pass renders the control disabled, says the review is updating, and only
    then makes the call."""
    src = _src()
    for lens in ("_render_daily_lens", "_render_weekly_lens"):
        body = function_source(src, lens)
        assert "disabled=busy" in body, lens
        assert "busy_key" in body, lens
        # The disabled control and the progress line are rendered BEFORE the
        # blocking call, or the browser never shows them.
        assert body.index("_regenerating()") < max(
            body.rfind("_run_daily_debrief("), body.rfind("generate_weekly_review(")
        ), lens


def test_the_skeleton_stands_in_for_a_missing_note_never_for_a_present_one():
    """The skeleton replaces the note's geometry. Shown during a
    regeneration it would replace the review the trader is reading with grey
    bars — so regeneration gets an inline status line instead."""
    src = _src()
    for lens in ("_render_daily_lens", "_render_weekly_lens"):
        body = function_source(src, lens)
        assert "render_note_skeleton" not in body, lens
    # It still exists where there is genuinely nothing yet.
    assert "render_note_skeleton" in function_source(src, "_auto_run_weekly")
    assert "render_note_skeleton" in function_source(src, "_run_daily_debrief")


def test_every_lens_reads_through_the_one_shell():
    """D6: three lenses, one idea of what a review looks like."""
    src = _src()
    assert "render_research_note(" not in src, "the old per-finding rail path"
    for lens in ("_render_patterns_lens", "_render_weekly_lens", "_render_daily_lens"):
        body = function_source(src, lens)
        assert "render_review_reader(" in body or "_render_generated_note(" in body


def test_each_lens_remembers_its_own_section():
    """One shared key would move the reader's place in the Weekly note when
    they navigated the Daily one."""
    src = _src()
    keys = set(re.findall(r'state_key="(_ins_\w+)"', src)) | set(
        re.findall(r'key="(_ins_\w+_section)"', src)
    )
    assert len(keys) >= 3, keys
