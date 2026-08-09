"""
AI Review component — journal entry + process grade for a saved trade.

Surfaces the existing journal (services/journal.py) and grading
(services/grading.py) pipelines on the live Journal page. Both are post-trade
reflection only: the journal is an 8-section retrospective and the grade scores
PROCESS quality against the Strategy Profile — never signals or predictions.

Requires a saved AIAnalysis row (created by the screenshot analyzer on the same
page) because the generated journal/grade persist to that row and build on its
user-confirmed labels. Grade overrides are recorded to correction memory.
"""

from __future__ import annotations

import json

from src.tradelens.services.ai_analysis_service import (
    get_analysis_for_trade,
    save_grade,
    save_journal,
    save_user_grade,
)
from src.tradelens.services.ai_client import AIParseError
from src.tradelens.services.corrections import record_correction
from src.tradelens.services.cost import log_ai_usage
from src.tradelens.services.grading import (
    GradingError,
    build_grading_context,
    grade_trade,
)
from src.tradelens.services.journal import (
    JournalStructureError,
    build_journal_context,
    generate_journal,
)
from src.tradelens.ui.components.ui import error_box, grade_chip
from src.tradelens.utils.ai_utils import ai_available

_GRADE_OPTS = ["(none)", "A", "B", "C", "D", "F"]


def _render_journal(st, trade, analysis, strategy_profile, user_id) -> None:
    st.markdown("**Journal Entry**")
    has_journal = bool(analysis.journal_entry_md)
    if has_journal:
        with st.expander("View journal entry", expanded=False):
            st.markdown(analysis.journal_entry_md)
        run = st.button("Regenerate journal", key=f"ai_journal_{trade.id}")
    else:
        st.caption("No journal yet — generate a written review of this trade.")
        run = st.button(
            "Generate journal entry", type="primary", key=f"ai_journal_{trade.id}"
        )
    if not run:
        return
    with st.spinner("Writing journal entry with AI…"):
        try:
            trade_dict, ai_dict = build_journal_context(trade, analysis)
            markdown, usage = generate_journal(
                trade_dict, ai_dict, strategy_profile=strategy_profile
            )
            save_journal(analysis.id, markdown)
            log_ai_usage("AI Journal", usage, user_id=user_id)
            st.toast("Journal saved", icon=":material/check_circle:")
            st.rerun()
        except (JournalStructureError, ValueError) as exc:
            st.markdown(
                error_box(f"Journal generation failed: {exc}"), unsafe_allow_html=True
            )
        except Exception:  # noqa: BLE001 — never crash the page, no raw traces
            st.markdown(
                error_box("Journal generation couldn't run. Please try again."),
                unsafe_allow_html=True,
            )


def _render_grade(st, trade, analysis, strategy_profile, user_id) -> None:
    st.markdown("**Process Grade**")
    st.caption("Grades your process against your rules — not the outcome.")
    try:
        saved = json.loads(analysis.grading_json) if analysis.grading_json else None
    except (json.JSONDecodeError, TypeError):
        saved = None

    if saved is None:
        run = st.button("Grade this trade", type="primary", key=f"ai_grade_{trade.id}")
    else:
        st.markdown(
            f"**AI Grade:** {grade_chip(trade.ai_grade)} &nbsp; "
            f"Score: **{saved.get('score', '—')}/10**",
            unsafe_allow_html=True,
        )
        if saved.get("one_line_verdict"):
            st.markdown(f"*{saved['one_line_verdict']}*")
        rubric = saved.get("rubric", {})
        if rubric:
            with st.expander("Rubric details", expanded=False):
                for dim, rdata in rubric.items():
                    label = dim.replace("_", " ").title()
                    st.markdown(
                        f"**{label}** — {rdata.get('score', '—')}/10: "
                        f"{rdata.get('note', '')}"
                    )

        # Your call, always: override the AI grade (recorded as a correction).
        current = trade.user_grade if trade.user_grade in _GRADE_OPTS else "(none)"
        oc, bc = st.columns([2, 1])
        override = oc.selectbox(
            "Your grade override",
            _GRADE_OPTS,
            index=_GRADE_OPTS.index(current),
            key=f"ai_grade_override_{trade.id}",
        )
        if bc.button("Save override", key=f"ai_grade_override_btn_{trade.id}"):
            resolved = None if override == "(none)" else override
            record_correction(trade.id, analysis.id, "grade", trade.ai_grade, resolved)
            save_user_grade(trade.id, resolved)
            st.toast("Grade override saved", icon=":material/check_circle:")
            st.rerun()
        run = st.button("Re-grade trade", key=f"ai_grade_{trade.id}")

    if not run:
        return
    with st.spinner("Grading your process with AI…"):
        try:
            trade_dict, vision_dict = build_grading_context(trade, analysis)
            result, usage = grade_trade(trade_dict, strategy_profile, vision_dict)
            save_grade(analysis.id, result)
            log_ai_usage("Trade Grading", usage, user_id=user_id)
            st.toast("Grade saved", icon=":material/check_circle:")
            st.rerun()
        except (GradingError, AIParseError, ValueError) as exc:
            st.markdown(error_box(f"Grading failed: {exc}"), unsafe_allow_html=True)
        except Exception:  # noqa: BLE001 — never crash the page, no raw traces
            st.markdown(
                error_box("Grading couldn't run. Please try again."),
                unsafe_allow_html=True,
            )


def render_ai_review(trade, strategy_profile=None, user_id=None) -> None:
    """Render the journal + grade section for a selected trade (post-trade only)."""
    import streamlit as st

    st.divider()
    st.subheader("AI Review")
    st.caption("Post-trade reflection — a written journal and a process grade.")

    if not ai_available():
        st.info(
            "AI features are off. Add your Anthropic API key in Settings to "
            "enable them."
        )
        return
    if trade is None:
        return

    analysis = get_analysis_for_trade(trade.id)
    if analysis is None:
        st.caption(
            "Run the screenshot analysis above first — the journal and grade "
            "build on the AI labels you confirm there."
        )
        return

    j, g = st.columns(2, gap="large")
    with j:
        _render_journal(st, trade, analysis, strategy_profile, user_id)
    with g:
        _render_grade(st, trade, analysis, strategy_profile, user_id)
