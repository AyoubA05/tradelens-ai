"""
Screenshot Analyzer panel (Session C, Section 1).

Renders the "Analyze Screenshot" button + editable AI-results panel for a SAVED
trade (used in the Journal detail). Reuses the existing services:
  * ai_screenshot_service.analyze_source — local path OR direct image URL
  * ai_analysis_service.create_or_update_analysis / get_analysis_for_trade
  * corrections.record_correction — correction memory (only writes on a change)
  * trade_service.update_trade — applies confirmed labels to the trade

AI output is retrospective review only; "Apply to Trade" never auto-applies
without an explicit click.
"""

from __future__ import annotations

import json

from src.tradelens.services.ai_analysis_service import (
    create_or_update_analysis,
    get_analysis_for_trade,
)
from src.tradelens.services.ai_screenshot_service import analyze_source
from src.tradelens.services.corrections import record_correction
from src.tradelens.services.trade_service import update_trade
from src.tradelens.services.vision import ScreenshotAnalysisError
from src.tradelens.ui.components.ui import error_box
from src.tradelens.utils.ai_utils import ai_available

_BIAS_OPTIONS = ["Bullish", "Bearish", "Neutral"]


def render_screenshot_analyzer(trade, strategy_profile=None) -> None:
    """Render the AI screenshot analysis panel for a saved trade."""
    import streamlit as st

    st.markdown("**AI Screenshot Analysis**")
    st.caption(
        "Post-trade review of your saved chart — reflection only, never signals."
    )

    # ai_available includes DEMO_MODE (cached fixtures, zero spend) so demo users
    # see the same panel as the AI Review and Ask-AI sections below it.
    if not ai_available():
        st.info(
            "🤖 AI features are off. Add your Anthropic API key in Settings to "
            "enable them."
        )
        return

    shots = sorted(
        trade.screenshots or [], key=lambda s: s.uploaded_at or "", reverse=True
    )
    if not shots:
        st.caption("Add a screenshot to this trade to analyze it.")
        return

    shot_path = shots[0].file_path
    existing = get_analysis_for_trade(trade.id)
    trade_ctx = {
        "id": trade.id,
        "asset": trade.asset,
        "direction": trade.direction,
        "result": trade.result,
        "pnl": trade.pnl,
        "setup_type": trade.setup_type,
    }

    label = "Re-analyze" if existing else "🔍 Analyze Screenshot"
    if st.button(label, key=f"analyze_{trade.id}"):
        with st.spinner("Analyzing your chart…"):
            try:
                result, usage = analyze_source(shot_path, trade_ctx, strategy_profile)
                create_or_update_analysis(trade.id, result, usage)
                st.toast("Analysis complete", icon="✅")
                st.rerun()
            except ScreenshotAnalysisError as exc:
                st.markdown(error_box(str(exc)), unsafe_allow_html=True)
            except Exception:  # noqa: BLE001 — no raw stack traces to the trader
                st.markdown(
                    error_box("The analysis couldn't run. Please try again."),
                    unsafe_allow_html=True,
                )

    if existing is None:
        return

    try:
        ai = json.loads(existing.raw_response_json or "{}")
    except (json.JSONDecodeError, TypeError):
        ai = {}

    st.caption("🤖 AI detected — edit any field, then Apply. Changes are remembered.")
    c1, c2 = st.columns(2)
    cur_bias = (ai.get("bias") or "").title()
    bias = c1.selectbox(
        "Bias",
        _BIAS_OPTIONS,
        index=_BIAS_OPTIONS.index(cur_bias) if cur_bias in _BIAS_OPTIONS else 2,
        key=f"ai_bias_{trade.id}",
    )
    setup = c2.text_input(
        "Setup",
        value=ai.get("setup_type") or ai.get("detected_setup") or "",
        key=f"ai_setup_{trade.id}",
    )
    quality = st.slider(
        "Trade Quality",
        1,
        10,
        int(ai.get("trade_quality") or 5),
        key=f"ai_quality_{trade.id}",
    )
    if ai.get("notes_to_user"):
        st.markdown(f"**AI review:** {ai['notes_to_user']}")

    mistakes = ai.get("possible_mistakes") or []
    if mistakes:
        st.caption("Possible mistakes: " + ", ".join(str(m) for m in mistakes))
    confluences = [
        name
        for name, key in (
            ("FVG", "fvg_used"),
            ("Order Block", "order_block_used"),
            ("Liquidity Sweep", "liquidity_sweep"),
        )
        if ai.get(key)
    ]
    if confluences:
        st.caption("Confluences: " + ", ".join(confluences))

    a1, a2 = st.columns(2)
    if a1.button("Apply to Trade", type="primary", key=f"ai_apply_{trade.id}"):
        # Record only genuine overrides (record_correction no-ops on equal values).
        record_correction(trade.id, existing.id, "bias", ai.get("bias"), bias.lower())
        record_correction(
            trade.id,
            existing.id,
            "setup_type",
            ai.get("setup_type") or ai.get("detected_setup"),
            setup or None,
        )
        record_correction(
            trade.id, existing.id, "trade_quality", ai.get("trade_quality"), quality
        )
        update_trade(trade.id, bias=bias.lower(), setup_type=setup or None)
        st.toast("Applied to trade", icon="✅")
        st.rerun()
    if a2.button("Dismiss", key=f"ai_dismiss_{trade.id}"):
        st.rerun()
