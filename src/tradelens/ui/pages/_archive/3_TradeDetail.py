import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parents[5])
if _root not in sys.path:
    sys.path.insert(0, _root)

import json  # noqa: E402

import streamlit as st  # noqa: E402

from src.tradelens.services.ai_analysis_service import (  # noqa: E402
    create_or_update_analysis,
    get_analysis_for_trade,
    get_smc_prefill,
    save_grade,
    save_journal,
    save_trade_smc,
    save_user_grade,
    update_analysis_fields,
)
from src.tradelens.services.ai_client import AIParseError  # noqa: E402
from src.tradelens.services.corrections import record_correction  # noqa: E402
from src.tradelens.services.grading import (  # noqa: E402
    GradingError,
    build_grading_context,
    grade_trade,
)
from src.tradelens.services.journal import (  # noqa: E402
    JournalStructureError,
    build_journal_context,
    generate_journal,
)
from src.tradelens.services.strategy import get_active_strategy  # noqa: E402
from src.tradelens.services.trade_service import get_trades  # noqa: E402
from src.tradelens.services.vision import (  # noqa: E402
    ScreenshotAnalysisError,
    analyze_screenshot,
)
from src.tradelens.ui.components.corrections_sidebar import (  # noqa: E402
    render_corrections_sidebar,
)
from src.tradelens.ui.components.demo_banner import render_demo_banner  # noqa: E402
from src.tradelens.ui.components.theme import inject_css  # noqa: E402
from src.tradelens.ui.components.ui import (  # noqa: E402
    empty_state,
    grade_chip,
    section_header,
)

st.set_page_config(page_title="Trade Detail", layout="wide")
inject_css()
render_demo_banner()
st.markdown(section_header("Trade Detail"), unsafe_allow_html=True)

render_corrections_sidebar()

# ── Trade selector ────────────────────────────────────────────────
trades = get_trades()
if not trades:
    st.markdown(
        empty_state(
            "No trades yet — log your first trade to review it here.",
            cta_label="Log a trade",
            cta_href="/NewTrade",
        ),
        unsafe_allow_html=True,
    )
    st.stop()

trade_labels = {
    t.id: f"#{t.id}  {t.trade_date or '—'}  {t.asset}  {t.result or '?'}"
    for t in trades
}

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

# Active strategy + API-key state used by all three AI calls below.
try:
    from src.tradelens.config import settings

    api_key_ok = bool(settings.anthropic_api_key) or settings.demo_mode
except Exception:
    api_key_ok = False

active_strategy = get_active_strategy()
analysis = get_analysis_for_trade(selected_id)

screenshots = sorted(
    trade.screenshots or [], key=lambda s: s.uploaded_at or "", reverse=True
)
latest_screenshot = screenshots[0] if screenshots else None
has_screenshot = (
    latest_screenshot is not None and Path(latest_screenshot.file_path).exists()
)

_trade_ctx = {
    "asset": trade.asset,
    "direction": trade.direction,
    "result": trade.result,
    "pnl": trade.pnl,
    "session": trade.session,
    "setup_type": trade.setup_type,
    "bias": trade.bias,
    "notes": trade.notes,
}

# ── Two-column layout: screenshot + facts left, AI analysis right ──
left, right = st.columns([5, 7], gap="large")

# ===================== LEFT: trade facts + chart =====================
with left:
    st.markdown(section_header("Trade Info"), unsafe_allow_html=True)
    st.markdown(f"**Date:** {trade.trade_date or '—'}")
    st.markdown(f"**Asset:** {trade.asset}")
    st.markdown(f"**Direction:** {trade.direction or '—'}")
    st.markdown(f"**Session:** {trade.session or '—'}")
    st.markdown(f"**Setup Type:** {trade.setup_type or '—'}")
    st.markdown(f"**Result:** {trade.result or '—'}")
    pnl_str = f"${trade.pnl:,.2f}" if trade.pnl is not None else "—"
    st.markdown(f"**P&L:** {pnl_str}")
    rr_str = f"{trade.rr_realized:.2f}R" if trade.rr_realized else "—"
    st.markdown(f"**RR Realized:** {rr_str}")
    st.markdown(f"**Bias:** {trade.bias or '—'}")
    st.markdown(f"**Strategy Used:** {trade.strategy_used or '—'}")

    emo_bits = [
        f"{label}: {val}"
        for label, val in (
            ("Before", trade.emotions_before),
            ("During", trade.emotions_during),
            ("After", trade.emotions_after),
        )
        if val
    ]
    if emo_bits:
        st.caption("Emotions — " + "  ·  ".join(emo_bits))

    if trade.notes:
        st.markdown(f"**Notes:** {trade.notes}")

    st.markdown(section_header("Chart Screenshot"), unsafe_allow_html=True)
    if has_screenshot:
        st.image(latest_screenshot.file_path, use_container_width=True)
    else:
        st.markdown(
            empty_state(
                "No screenshot for this trade.",
                cta_label="Add one",
                cta_href="/NewTrade",
            ),
            unsafe_allow_html=True,
        )

# ===================== RIGHT: AI analysis / journal / grade ==========
with right:
    st.markdown(section_header("AI Screenshot Analysis"), unsafe_allow_html=True)

    if not api_key_ok:
        st.warning(
            "ANTHROPIC_API_KEY is not set. Add it to your secrets/.env to enable AI."
        )

    if active_strategy:
        st.caption(f"Active strategy: **{active_strategy.get('name', '—')}**")
    else:
        st.caption("No strategy profile set — using a generic ICT framework.")

    if analysis is None:
        analyze_btn = st.button(
            "Analyze Screenshot",
            type="primary",
            disabled=not has_screenshot or not api_key_ok,
            help=(
                "Upload a screenshot first, then click to run AI analysis."
                if not has_screenshot
                else ""
            ),
        )
        if analyze_btn:
            with st.spinner("Analyzing chart with AI…"):
                try:
                    vision_result, usage = analyze_screenshot(
                        latest_screenshot.file_path,
                        _trade_ctx,
                        strategy_profile=active_strategy,
                    )
                    analysis = create_or_update_analysis(
                        selected_id, vision_result, usage
                    )
                    st.toast("Analysis complete", icon="✅")
                    st.rerun()
                except ScreenshotAnalysisError as exc:
                    st.toast(f"Screenshot analysis failed: {exc}", icon="❌")
                except AIParseError as exc:
                    st.toast(f"AI returned an unreadable response: {exc}", icon="❌")
                except ValueError as exc:
                    st.toast(str(exc), icon="❌")
                except Exception as exc:
                    st.toast(f"Unexpected error: {exc}", icon="❌")
    else:
        rerun_btn = st.button(
            "Re-run Analysis",
            type="secondary",
            disabled=not has_screenshot or not api_key_ok,
        )
        if rerun_btn:
            with st.spinner("Re-analyzing chart with AI…"):
                try:
                    vision_result, usage = analyze_screenshot(
                        latest_screenshot.file_path,
                        _trade_ctx,
                        strategy_profile=active_strategy,
                    )
                    analysis = create_or_update_analysis(
                        selected_id, vision_result, usage
                    )
                    st.toast("Analysis updated", icon="✅")
                    st.rerun()
                except ScreenshotAnalysisError as exc:
                    st.toast(f"Screenshot analysis failed: {exc}", icon="❌")
                except AIParseError as exc:
                    st.toast(f"AI returned an unreadable response: {exc}", icon="❌")
                except ValueError as exc:
                    st.toast(str(exc), icon="❌")
                except Exception as exc:
                    st.toast(f"Unexpected error: {exc}", icon="❌")

    # ── Editable labels (only when analysis exists) ───────────────
    if analysis is not None:
        st.markdown("#### AI Labels")
        st.caption(
            f"Model: {analysis.model or '—'}  |  "
            f"Tokens: {analysis.tokens_input or 0}↑ {analysis.tokens_output or 0}↓  |  "
            f"Cost: ${analysis.cost_usd:.5f}"
            if analysis.cost_usd
            else "Cost: —"
        )

        BIAS_OPTIONS = ["bullish", "bearish", "neutral"]
        SETUP_OPTIONS = [
            "",
            "FVG",
            "Order Block",
            "BOS",
            "CHoCH",
            "Liquidity Sweep",
            "S/R Bounce",
            "OB + FVG",
            "Other",
        ]

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            bias_idx = (
                BIAS_OPTIONS.index(analysis.bias)
                if analysis.bias in BIAS_OPTIONS
                else 0
            )
            new_bias = st.selectbox(
                "Bias", BIAS_OPTIONS, index=bias_idx, key="chip_bias"
            )
        with col_b:
            current_setup = analysis.detected_setup or ""
            if current_setup not in SETUP_OPTIONS:
                SETUP_OPTIONS.append(current_setup)
            setup_idx = SETUP_OPTIONS.index(current_setup)
            new_setup = st.selectbox(
                "Detected Setup", SETUP_OPTIONS, index=setup_idx, key="chip_setup"
            )
        with col_c:
            new_quality = st.slider(
                "Trade Quality",
                min_value=1,
                max_value=10,
                value=analysis.trade_quality or 5,
                key="chip_quality",
            )

        # SMC/ICT setup — AI proposals pre-fill editable widgets; a value the
        # user already set on the trade always takes priority.
        smc = get_smc_prefill(trade, analysis)
        st.markdown("**SMC/ICT Setup** — editable; AI proposals shown only where unset")
        HTF_OPTIONS = ["(none)", "bullish", "bearish", "neutral"]
        htf_default = smc.get("htf_bias") or "(none)"
        if htf_default not in HTF_OPTIONS:
            htf_default = "(none)"
        s_col1, s_col2, s_col3, s_col4 = st.columns(4)
        with s_col1:
            new_htf = st.selectbox(
                "HTF Bias",
                HTF_OPTIONS,
                index=HTF_OPTIONS.index(htf_default),
                key="smc_htf",
            )
        with s_col2:
            new_liqsweep = st.checkbox(
                "Liquidity Sweep",
                value=bool(smc.get("liquidity_sweep")),
                key="smc_liqsweep",
            )
        with s_col3:
            new_fvg = st.checkbox(
                "FVG Used", value=bool(smc.get("fvg_used")), key="smc_fvg"
            )
        with s_col4:
            new_ob = st.checkbox(
                "Order Block", value=bool(smc.get("order_block_used")), key="smc_ob"
            )

        # Key zones (read-only structured view)
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

        if st.button("Save Labels", type="primary"):
            record_correction(selected_id, analysis.id, "bias", analysis.bias, new_bias)
            record_correction(
                selected_id,
                analysis.id,
                "detected_setup",
                analysis.detected_setup,
                new_setup or None,
            )
            record_correction(
                selected_id,
                analysis.id,
                "trade_quality",
                analysis.trade_quality,
                new_quality,
            )
            update_analysis_fields(
                analysis.id,
                bias=new_bias,
                detected_setup=new_setup or None,
                trade_quality=new_quality,
            )
            save_trade_smc(
                selected_id,
                htf_bias=None if new_htf == "(none)" else new_htf,
                liquidity_sweep=1 if new_liqsweep else 0,
                fvg_used=1 if new_fvg else 0,
                order_block_used=1 if new_ob else 0,
            )
            st.toast("Labels saved", icon="✅")
            st.rerun()

        # ── Journal Entry section ─────────────────────────────────
        st.divider()
        st.markdown(section_header("Journal Entry"), unsafe_allow_html=True)

        has_journal = bool(analysis.journal_entry_md)
        if has_journal:
            with st.expander("View Journal Entry", expanded=True):
                st.markdown(analysis.journal_entry_md)
            run_journal = st.button(
                "Regenerate Journal", type="secondary", disabled=not api_key_ok
            )
        else:
            st.caption("No journal yet. Generate one after reviewing the AI labels.")
            run_journal = st.button(
                "Generate Journal Entry", type="primary", disabled=not api_key_ok
            )

        if run_journal:
            with st.spinner("Writing journal entry with AI…"):
                try:
                    trade_dict, ai_dict = build_journal_context(trade, analysis)
                    markdown, j_usage = generate_journal(
                        trade_dict, ai_dict, strategy_profile=active_strategy
                    )
                    save_journal(analysis.id, markdown)
                    st.toast("Journal saved", icon="✅")
                    st.rerun()
                except JournalStructureError as exc:
                    st.toast(f"Journal structure error: {exc}", icon="❌")
                except ValueError as exc:
                    st.toast(str(exc), icon="❌")
                except Exception as exc:
                    st.toast(f"Journal generation failed: {exc}", icon="❌")

        # ── Grade section ─────────────────────────────────────────
        st.divider()
        st.markdown(section_header("Trade Grade"), unsafe_allow_html=True)

        try:
            saved_grading = (
                json.loads(analysis.grading_json) if analysis.grading_json else None
            )
        except (json.JSONDecodeError, TypeError):
            saved_grading = None

        ai_grade = trade.ai_grade
        user_grade = trade.user_grade

        if saved_grading is None:
            st.caption("No grade yet. Grade this trade on process quality.")
            run_grade = st.button(
                "Grade Trade", type="primary", disabled=not api_key_ok
            )
        else:
            st.markdown(
                f"**AI Grade:** {grade_chip(ai_grade)} &nbsp; "
                f"Score: **{saved_grading.get('score', '—')}/10**",
                unsafe_allow_html=True,
            )
            st.markdown(f"*{saved_grading.get('one_line_verdict', '')}*")

            rubric = saved_grading.get("rubric", {})
            if rubric:
                with st.expander("Rubric Details", expanded=False):
                    for dim, rdata in rubric.items():
                        label = dim.replace("_", " ").title()
                        score = rdata.get("score", "—")
                        note = rdata.get("note", "")
                        st.markdown(f"**{label}** — {score}/10: {note}")

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
                    resolved_override = (
                        None if new_override == "(none)" else new_override
                    )
                    record_correction(
                        selected_id,
                        analysis.id,
                        "grade",
                        trade.ai_grade,
                        resolved_override,
                    )
                    save_user_grade(selected_id, resolved_override)
                    st.toast("Grade override saved", icon="✅")
                    st.rerun()

            run_grade = st.button(
                "Re-grade Trade", type="secondary", disabled=not api_key_ok
            )

        if run_grade:
            with st.spinner("Grading your process with AI…"):
                try:
                    trade_dict, vision_dict = build_grading_context(trade, analysis)
                    grading_result, g_usage = grade_trade(
                        trade_dict, active_strategy, vision_dict
                    )
                    save_grade(analysis.id, grading_result)
                    st.toast("Grade saved", icon="✅")
                    st.rerun()
                except GradingError as exc:
                    st.toast(f"Grading failed: {exc}", icon="❌")
                except AIParseError as exc:
                    st.toast(f"AI returned an unreadable response: {exc}", icon="❌")
                except ValueError as exc:
                    st.toast(str(exc), icon="❌")
                except Exception as exc:
                    st.toast(f"Unexpected error during grading: {exc}", icon="❌")
