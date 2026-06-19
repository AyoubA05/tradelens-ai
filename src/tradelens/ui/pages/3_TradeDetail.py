import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[4])
if _root not in sys.path:
    sys.path.insert(0, _root)

import json  # noqa: E402

import streamlit as st  # noqa: E402

from src.tradelens.services.ai_analysis_service import (  # noqa: E402
    create_or_update_analysis,
    get_analysis_for_trade,
    save_grade,
    save_journal,
    save_user_grade,
    update_analysis_fields,
)
from src.tradelens.services.corrections import record_correction  # noqa: E402
from src.tradelens.services.grading import GradingError, build_grading_context, grade_trade  # noqa: E402
from src.tradelens.services.journal import JournalStructureError, build_journal_context, generate_journal  # noqa: E402
from src.tradelens.services.strategy import get_active_strategy  # noqa: E402
from src.tradelens.services.trade_service import get_trades  # noqa: E402
from src.tradelens.services.vision import ScreenshotAnalysisError, analyze_screenshot  # noqa: E402

st.set_page_config(page_title="Trade Detail", page_icon="🔍")
st.title("🔍 Trade Detail")

# ── Trade selector ────────────────────────────────────────────────
trades = get_trades()
if not trades:
    st.info("No trades found. Log your first trade on the New Trade page.")
    st.stop()

# Build label map: "id — date  asset  result"
trade_labels = {
    t.id: f"#{t.id}  {t.trade_date or '—'}  {t.asset}  {t.result or '?'}"
    for t in trades
}

# Pre-select if another page set this in session state
default_id = st.session_state.get("selected_trade_id", trades[0].id)
if default_id not in trade_labels:
    default_id = trades[0].id

selected_id = st.selectbox(
    "Select Trade",
    options=list(trade_labels.keys()),
    format_func=lambda tid: trade_labels[tid],
    index=list(trade_labels.keys()).index(default_id),
)
st.session_state["selected_trade_id"] = selected_id

trade = next(t for t in trades if t.id == selected_id)

st.markdown("---")

# ── Trade info ────────────────────────────────────────────────────
st.subheader("Trade Info")
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"**Date:** {trade.trade_date or '—'}")
    st.markdown(f"**Asset:** {trade.asset}")
    st.markdown(f"**Direction:** {trade.direction or '—'}")
    st.markdown(f"**Session:** {trade.session or '—'}")
    st.markdown(f"**Setup Type:** {trade.setup_type or '—'}")
with c2:
    st.markdown(f"**Result:** {trade.result or '—'}")
    pnl_str = f"${trade.pnl:,.2f}" if trade.pnl is not None else "—"
    st.markdown(f"**P&L:** {pnl_str}")
    rr_str = f"{trade.rr_realized:.2f}R" if trade.rr_realized else "—"
    st.markdown(f"**RR Realized:** {rr_str}")
    st.markdown(f"**Bias:** {trade.bias or '—'}")
    st.markdown(f"**Strategy Used:** {trade.strategy_used or '—'}")

if trade.notes:
    st.markdown(f"**Notes:** {trade.notes}")

st.markdown("---")

# ── Screenshot panel ──────────────────────────────────────────────
st.subheader("Chart Screenshot")

screenshots = sorted(trade.screenshots or [], key=lambda s: s.uploaded_at or "", reverse=True)
latest_screenshot = screenshots[0] if screenshots else None

has_screenshot = latest_screenshot is not None and Path(latest_screenshot.file_path).exists()

if has_screenshot:
    st.image(latest_screenshot.file_path, use_column_width=True)
else:
    st.info("No screenshot uploaded for this trade. Upload one via the New Trade page.")

st.markdown("---")

# ── AI Analysis section ───────────────────────────────────────────
st.subheader("AI Screenshot Analysis")

# Check API key
try:
    from src.tradelens.config import settings
    api_key_ok = bool(settings.anthropic_api_key) or settings.demo_mode
except Exception:
    api_key_ok = False

if not api_key_ok:
    st.warning("ANTHROPIC_API_KEY is not set. Add it to your secrets/.env to enable AI analysis.")

# Load existing analysis (if any)
analysis = get_analysis_for_trade(selected_id)

# Fetch active strategy profile once; used by all three AI calls on this page
active_strategy = get_active_strategy()
if active_strategy:
    st.caption(f"Active strategy: **{active_strategy.get('name', '—')}**")
else:
    st.caption("No strategy profile set — using generic ICT/price-action framework.")

if analysis is None:
    # No analysis yet
    analyze_btn = st.button(
        "Analyze Screenshot",
        type="primary",
        disabled=not has_screenshot or not api_key_ok,
        help="Upload a screenshot first, then click to run AI analysis." if not has_screenshot else "",
    )
    if analyze_btn:
        trade_ctx = {
            "asset": trade.asset,
            "direction": trade.direction,
            "result": trade.result,
            "pnl": trade.pnl,
            "session": trade.session,
            "setup_type": trade.setup_type,
            "bias": trade.bias,
            "notes": trade.notes,
        }
        with st.spinner("Analyzing chart… this may take 10–20 seconds."):
            try:
                vision_result, usage = analyze_screenshot(
                    latest_screenshot.file_path,
                    trade_ctx,
                    strategy_profile=active_strategy,
                )
                analysis = create_or_update_analysis(selected_id, vision_result, usage)
                st.caption(f"AI: {usage}")
                st.success("Analysis complete! Labels loaded below.")
                st.rerun()
            except ScreenshotAnalysisError as exc:
                st.error(f"Screenshot analysis failed: {exc}")
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Unexpected error: {exc}")
else:
    # Analysis exists — show Re-run button
    rerun_btn = st.button(
        "Re-run Analysis",
        type="secondary",
        disabled=not has_screenshot or not api_key_ok,
    )
    if rerun_btn:
        trade_ctx = {
            "asset": trade.asset,
            "direction": trade.direction,
            "result": trade.result,
            "pnl": trade.pnl,
            "session": trade.session,
            "setup_type": trade.setup_type,
            "bias": trade.bias,
            "notes": trade.notes,
        }
        with st.spinner("Re-analyzing chart…"):
            try:
                vision_result, usage = analyze_screenshot(
                    latest_screenshot.file_path,
                    trade_ctx,
                    strategy_profile=active_strategy,
                )
                analysis = create_or_update_analysis(selected_id, vision_result, usage)
                st.caption(f"AI: {usage}")
                st.success("Analysis updated!")
                st.rerun()
            except ScreenshotAnalysisError as exc:
                st.error(f"Screenshot analysis failed: {exc}")
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Unexpected error: {exc}")

# ── Editable labels (only when analysis exists) ───────────────────
if analysis is not None:
    st.markdown("#### AI Labels")
    st.caption(
        f"Model: {analysis.model or '—'}  |  "
        f"Tokens: {analysis.tokens_input or 0}↑ {analysis.tokens_output or 0}↓  |  "
        f"Cost: ${analysis.cost_usd:.5f}" if analysis.cost_usd else "Cost: —"
    )

    BIAS_OPTIONS = ["bullish", "bearish", "neutral"]
    SETUP_OPTIONS = [
        "", "FVG", "Order Block", "BOS", "CHoCH", "Liquidity Sweep",
        "S/R Bounce", "OB + FVG", "Other",
    ]

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        bias_idx = BIAS_OPTIONS.index(analysis.bias) if analysis.bias in BIAS_OPTIONS else 0
        new_bias = st.selectbox("Bias", BIAS_OPTIONS, index=bias_idx, key="chip_bias")
    with col_b:
        current_setup = analysis.detected_setup or ""
        if current_setup not in SETUP_OPTIONS:
            SETUP_OPTIONS.append(current_setup)
        setup_idx = SETUP_OPTIONS.index(current_setup)
        new_setup = st.selectbox("Detected Setup", SETUP_OPTIONS, index=setup_idx, key="chip_setup")
    with col_c:
        new_quality = st.slider(
            "Trade Quality",
            min_value=1, max_value=10,
            value=analysis.trade_quality or 5,
            key="chip_quality",
        )

    # Key zones (read-only structured view — editing is Day 7)
    try:
        zones = json.loads(analysis.zones_json or "[]")
    except (json.JSONDecodeError, TypeError):
        zones = []
    if zones:
        with st.expander(f"Key Zones ({len(zones)})", expanded=False):
            st.json(zones)

    # Mistakes / missed opportunities
    try:
        mistakes = json.loads(analysis.mistakes_json or "[]")
        missed = json.loads(analysis.missed_opps_json or "[]")
    except (json.JSONDecodeError, TypeError):
        mistakes, missed = [], []

    if mistakes or missed:
        m_col, mo_col = st.columns(2)
        with m_col:
            if mistakes:
                st.markdown("**Possible Mistakes**")
                for m in mistakes:
                    st.markdown(f"- {m}")
        with mo_col:
            if missed:
                st.markdown("**Missed Opportunities**")
                for mo in missed:
                    st.markdown(f"- {mo}")

    # Save labels button
    if st.button("💾 Save Labels", type="primary"):
        record_correction(selected_id, analysis.id, "bias", analysis.bias, new_bias)
        record_correction(selected_id, analysis.id, "detected_setup", analysis.detected_setup, new_setup or None)
        record_correction(selected_id, analysis.id, "trade_quality", analysis.trade_quality, new_quality)
        update_analysis_fields(
            analysis.id,
            bias=new_bias,
            detected_setup=new_setup or None,
            trade_quality=new_quality,
        )
        st.success("Labels saved!")
        st.rerun()

    # ── Journal Entry section ─────────────────────────────────────
    st.divider()
    st.subheader("Journal Entry")

    has_journal = bool(analysis.journal_entry_md)

    if has_journal:
        with st.expander("View Journal Entry", expanded=True):
            st.markdown(analysis.journal_entry_md)
        regen_btn = st.button(
            "Regenerate Journal",
            type="secondary",
            disabled=not api_key_ok,
        )
        run_journal = regen_btn
    else:
        st.info("No journal yet. Generate one after reviewing the AI labels above.")
        gen_btn = st.button(
            "Generate Journal Entry",
            type="primary",
            disabled=not api_key_ok,
        )
        run_journal = gen_btn

    if run_journal:
        with st.spinner("Writing journal entry… this may take 15–30 seconds."):
            try:
                trade_dict, ai_dict = build_journal_context(trade, analysis)
                markdown, j_usage = generate_journal(trade_dict, ai_dict, strategy_profile=active_strategy)
                save_journal(analysis.id, markdown)
                st.caption(f"AI: {j_usage}")
                st.success("Journal saved!")
                st.rerun()
            except JournalStructureError as exc:
                st.error(f"Journal structure error: {exc}")
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Journal generation failed: {exc}")

    # ── Grade section ─────────────────────────────────────────────
    st.divider()
    st.subheader("Trade Grade")

    _GRADE_COLORS = {"A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴"}

    # Read saved grading state
    try:
        saved_grading = json.loads(analysis.grading_json) if analysis.grading_json else None
    except (json.JSONDecodeError, TypeError):
        saved_grading = None

    ai_grade = trade.ai_grade
    user_grade = trade.user_grade

    if saved_grading is None:
        st.info("No grade yet. Click to grade this trade on process quality.")
        run_grade = st.button(
            "Grade Trade",
            type="primary",
            disabled=not api_key_ok,
        )
    else:
        # Show AI grade chip
        grade_icon = _GRADE_COLORS.get(ai_grade, "⚪")
        st.markdown(f"**AI Grade:** {grade_icon} **{ai_grade}** &nbsp;|&nbsp; Score: **{saved_grading.get('score', '—')}/10**")
        st.markdown(f"*{saved_grading.get('one_line_verdict', '')}*")

        # Rubric expander
        rubric = saved_grading.get("rubric", {})
        if rubric:
            with st.expander("Rubric Details", expanded=False):
                for dim, data in rubric.items():
                    label = dim.replace("_", " ").title()
                    score = data.get("score", "—")
                    note = data.get("note", "")
                    st.markdown(f"**{label}** — {score}/10: {note}")

        # User override
        GRADE_OPTS = ["(none)", "A", "B", "C", "D", "F"]
        current_override = user_grade if user_grade in GRADE_OPTS else "(none)"
        override_col, btn_col = st.columns([2, 1])
        with override_col:
            new_override = st.selectbox(
                "Your Grade Override",
                GRADE_OPTS,
                index=GRADE_OPTS.index(current_override),
                key="grade_override_select",
            )
        with btn_col:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Save Override", key="save_override_btn"):
                resolved_override = None if new_override == "(none)" else new_override
                record_correction(selected_id, analysis.id, "grade", trade.ai_grade, resolved_override)
                save_user_grade(selected_id, resolved_override)
                st.success("Grade override saved!")
                st.rerun()

        run_grade = st.button(
            "Re-grade Trade",
            type="secondary",
            disabled=not api_key_ok,
        )

    if run_grade:
        with st.spinner("Grading trade on process quality…"):
            try:
                trade_dict, vision_dict = build_grading_context(trade, analysis)
                grading_result, g_usage = grade_trade(trade_dict, active_strategy, vision_dict)
                save_grade(analysis.id, grading_result)
                st.caption(f"AI: {g_usage}")
                st.success("Grade saved!")
                st.rerun()
            except GradingError as exc:
                st.error(f"Grading failed: {exc}")
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Unexpected error during grading: {exc}")
