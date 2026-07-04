"""
"Ask AI About This Trade" chat panel (Session D1).

A scoped, conversational, post-trade review panel for a single SAVED trade.
Wraps services/partner.py (which owns the scope guard + Anthropic call) and keeps
per-trade chat history in session_state only — never persisted to the DB.

Post-trade only: the underlying system prompt forbids live signals, predictions,
and entry/exit recommendations.
"""

from __future__ import annotations

import html

from src.tradelens.services.partner import (
    PartnerError,
    build_trade_context,
    partner_reply,
)
from src.tradelens.utils.ai_utils import ai_available

_PROMPT_CHIPS = [
    "What did I do well?",
    "What rule did I break?",
    "How can I improve this setup?",
    "Summarize this trade in journal format.",
]

_UNAVAILABLE = "AI is temporarily unavailable. Please try again."


def _chat_key(trade_id) -> str:
    return f"trade_chat_{trade_id}"


def _send(st, chat_key: str, trade, strategy_profile, user_message, analysis) -> None:
    """Append the user turn, call the partner, append the reply, and rerun.

    Item 9: the saved AI observations (analysis row) ground the answer, and the
    per-trade Q&A preamble scopes it to this one completed trade.
    """
    history = st.session_state.setdefault(chat_key, [])
    history.append({"role": "user", "content": user_message})
    try:
        with st.spinner("Reflecting on this trade…"):
            reply, usage = partner_reply(
                history,
                trade_context=build_trade_context(trade, analysis),
                strategy_profile=strategy_profile,
                per_trade_qa=True,
            )
        # Cost telemetry: partner chat has no persistence row of its own, so log
        # the call to ai_usage_log (best-effort) for the Settings dashboard.
        from src.tradelens.services.cost import log_ai_usage
        from src.tradelens.ui.components.auth import current_user_id

        log_ai_usage("AI Partner", usage, user_id=current_user_id())
    except PartnerError:
        reply = _UNAVAILABLE
    except Exception:  # noqa: BLE001 — never leak a stack trace to the chat
        reply = _UNAVAILABLE
    history.append({"role": "assistant", "content": reply})
    st.session_state[chat_key] = history
    st.rerun()


def _render_coach_notes(st, analysis) -> None:
    """Item 9: read-only, collapsed view of the AI observations saved with the
    trade — notes, quality estimate, mistakes, missed opportunities, structure."""
    import json

    if analysis is None or not getattr(analysis, "raw_response_json", None):
        return
    try:
        saved = json.loads(analysis.raw_response_json)
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(saved, dict):
        return
    notes = saved.get("notes_to_user")
    quality = saved.get("trade_quality")
    mistakes = saved.get("possible_mistakes") or []
    missed = saved.get("missed_opportunities") or []
    structure = saved.get("structure")
    if not any((notes, quality, mistakes, missed, structure)):
        return
    with st.expander("AI Coach Notes", expanded=False):
        st.caption("Saved from the original screenshot review — read-only.")
        if quality is not None:
            st.markdown(f"**AI quality estimate:** {quality}/10")
        if structure:
            st.markdown(f"**Structure:** {structure}")
        if notes:
            st.markdown(f"**Notes:** {notes}")
        if mistakes:
            st.markdown("**Possible mistakes:** " + ", ".join(str(m) for m in mistakes))
        if missed:
            st.markdown(
                "**Missed opportunities:** " + ", ".join(str(m) for m in missed)
            )


def render_ask_ai(trade, strategy_profile=None) -> None:
    """Render the Ask-AI panel for the selected trade (or guidance if none)."""
    import streamlit as st

    st.divider()
    st.subheader("🤖 Ask AI About This Trade")
    st.caption("AI reflects on past trades only — no live signals.")

    if not ai_available():
        st.info(
            "🤖 AI features are off. Add your Anthropic API key in Settings to "
            "enable them."
        )
        return

    if trade is None:
        st.info("Select a trade above to ask AI about it.")
        return

    # Item 9: the saved AI observations render read-only above the Q&A and
    # ground its answers. Best-effort — a DB hiccup must not kill the chat.
    try:
        from src.tradelens.services.ai_analysis_service import get_analysis_for_trade

        analysis = get_analysis_for_trade(trade.id)
    except Exception:  # noqa: BLE001
        analysis = None
    _render_coach_notes(st, analysis)

    chat_key = _chat_key(trade.id)
    history = st.session_state.setdefault(chat_key, [])

    # ── Prompt chips (auto-submit on click) ───────────────────────
    pending = None
    chip_cols = st.columns(len(_PROMPT_CHIPS))
    for i, (col, chip) in enumerate(zip(chip_cols, _PROMPT_CHIPS)):
        if col.button(chip, key=f"{chat_key}_chip_{i}", use_container_width=True):
            pending = chip

    # ── Conversation ──────────────────────────────────────────────
    for msg in history:
        css = "tl-chat-user" if msg["role"] == "user" else "tl-chat-ai"
        st.markdown(
            f'<div class="{css}">{html.escape(str(msg["content"]))}</div>',
            unsafe_allow_html=True,
        )

    # ── Input ─────────────────────────────────────────────────────
    with st.form(f"{chat_key}_form", clear_on_submit=True):
        typed = st.text_input(
            "Ask the AI about this trade…",
            key=f"{chat_key}_input",
            label_visibility="collapsed",
            placeholder="Ask the AI about this trade…",
        )
        sent = st.form_submit_button("Send", use_container_width=True)

    user_message = pending or (typed.strip() if sent and typed.strip() else None)
    if user_message:
        _send(st, chat_key, trade, strategy_profile, user_message, analysis)

    if history and st.button("Clear chat", type="secondary", key=f"{chat_key}_clear"):
        st.session_state[chat_key] = []
        st.rerun()
