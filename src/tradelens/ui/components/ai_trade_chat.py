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
from src.tradelens.utils.ai_utils import is_ai_enabled

_PROMPT_CHIPS = [
    "What did I do well?",
    "What rule did I break?",
    "How can I improve this setup?",
    "Summarize this trade in journal format.",
]

_UNAVAILABLE = "AI is temporarily unavailable. Please try again."


def _chat_key(trade_id) -> str:
    return f"trade_chat_{trade_id}"


def _send(st, chat_key: str, trade, strategy_profile, user_message: str) -> None:
    """Append the user turn, call the partner, append the reply, and rerun."""
    history = st.session_state.setdefault(chat_key, [])
    history.append({"role": "user", "content": user_message})
    try:
        reply, _usage = partner_reply(
            history,
            trade_context=build_trade_context(trade),
            strategy_profile=strategy_profile,
        )
    except PartnerError:
        reply = _UNAVAILABLE
    except Exception:  # noqa: BLE001 — never leak a stack trace to the chat
        reply = _UNAVAILABLE
    history.append({"role": "assistant", "content": reply})
    st.session_state[chat_key] = history
    st.rerun()


def render_ask_ai(trade, strategy_profile=None) -> None:
    """Render the Ask-AI panel for the selected trade (or guidance if none)."""
    import streamlit as st

    st.divider()
    st.subheader("🤖 Ask AI About This Trade")
    st.caption("AI reflects on past trades only — no live signals.")

    if not is_ai_enabled():
        st.info("🤖 AI features disabled. Add your ANTHROPIC_API_KEY in Settings.")
        return

    if trade is None:
        st.info("Select a trade above to ask AI about it.")
        return

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
            "Ask something about this trade...",
            key=f"{chat_key}_input",
            label_visibility="collapsed",
            placeholder="Ask something about this trade...",
        )
        sent = st.form_submit_button("Send", use_container_width=True)

    user_message = pending or (typed.strip() if sent and typed.strip() else None)
    if user_message:
        _send(st, chat_key, trade, strategy_profile, user_message)

    if history and st.button("Clear chat", type="secondary", key=f"{chat_key}_clear"):
        st.session_state[chat_key] = []
        st.rerun()
