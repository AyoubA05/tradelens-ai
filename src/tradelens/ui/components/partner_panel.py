"""The AI Partner surface: a bottom-right launcher and a non-modal drawer.

Presentation only. Handoff §1 approves the global Partner **through the
existing service and nothing else** — so this module opens no endpoint, imports
no SDK, and runs no query of its own. Context comes from the Task 4 adapter,
answers come from `partner_reply(..., per_trade_qa=False)`, and the decisions
about what one turn does live in `partner_turn.py`, which has no Streamlit in
it and can therefore be proved without a browser.

Two structural choices are worth stating.

**Open/close is state-driven, not CSS-driven.** `partner_open` gates whether
the drawer renders at all, so closed means its widgets are not in the DOM and
cannot be tabbed to. A CSS-hidden drawer would still be in the tab order, and
there is no script here to manage that.

**The drawer claims no modal semantics.** A focus trap needs JavaScript, which
this phase forbids, so `aria-modal` would promise assistive technology
something the page cannot deliver. It is an `<aside>` with a label and a
visible Close control first in reading order — no scrim, nothing blocked.
"""

from __future__ import annotations

from html import escape

from src.tradelens.services.cost import log_ai_usage
from src.tradelens.services.partner import PartnerError, partner_reply
from src.tradelens.services.partner_context import build_global_partner_context
from src.tradelens.ui.components.partner_turn import (
    CONTEXT_USED_LABEL,
    context_used_for,
    error_key,
    history_key,
    send_turn,
)

PARTNER_OPEN_KEY = "partner_open"

# Retrospective by construction. Every one asks about trades that have already
# closed; none can be answered with a view about what to do next, which is the
# boundary the scope guard also enforces on the way back.
SUGGESTED_QUESTIONS = (
    "What did I repeat most last week?",
    "Where did I break my own rules?",
    "Which of my logged mistakes cost the most?",
)

EMPTY_STATE_BODY = (
    "Ask about trades you have already closed. Answers are drawn from your "
    "journal notes, your completed trades, and your active Strategy Profile. "
    "This conversation is not saved — it clears when you sign out or reload."
)

# The scope sentence, shown once on the surface rather than repeated per turn.
SCOPE_NOTE = "Reflection on trades you have logged. Never signals or advice."


def _log_exception(label: str) -> None:
    import logging

    logging.getLogger(__name__).exception(label)


def _render_turn(st, turn: dict) -> None:
    """One stored turn. Model text takes Streamlit's safe Markdown path."""
    with st.chat_message("user" if turn.get("role") == "user" else "assistant"):
        st.markdown(str(turn.get("content") or ""))
        labels = context_used_for(turn)
        if labels:
            # Labels, not citations. `partner_reply` returns text and usage
            # only, so it cannot report which records a sentence drew on —
            # naming these "Context used" is the contract, not a caption.
            items = "".join(f"<li>{escape(str(row))}</li>" for row in labels)
            st.markdown(
                '<details class="tl-partner-context">'
                f"<summary>{escape(CONTEXT_USED_LABEL)}</summary>"
                f"<ul>{items}</ul></details>",
                unsafe_allow_html=True,
            )


def render_partner_body(st, *, surface: str) -> None:
    """The conversation itself, shared by the drawer and the phone page.

    `surface` keys the widgets so the drawer and the full page can both exist
    without colliding on a Streamlit key. History is keyed by user, not by
    surface, so a conversation started in the drawer is the same one the phone
    page shows.
    """
    from src.tradelens.ui.components.auth import current_user_id

    uid = current_user_id()
    history = st.session_state.get(history_key(uid)) or []

    if not history:
        st.markdown(
            '<p class="tl-partner-empty">' f"{escape(EMPTY_STATE_BODY)}</p>",
            unsafe_allow_html=True,
        )
        for i, question in enumerate(SUGGESTED_QUESTIONS):
            if st.button(question, key=f"secondary_partner_{surface}_chip_{i}"):
                st.session_state[f"_partner_pending_{surface}"] = question
                st.rerun()
    else:
        for turn in history:
            _render_turn(st, turn)

    error = st.session_state.get(error_key(uid))
    if error:
        st.markdown(
            '<p class="tl-partner-error" role="alert">' f"{escape(str(error))}</p>",
            unsafe_allow_html=True,
        )

    pending = st.session_state.pop(f"_partner_pending_{surface}", None)
    typed = st.chat_input(
        "Ask about a trade you have logged", key=f"partner_in_{surface}"
    )
    question = pending or typed

    if question:
        with st.spinner("Reading your journal…"):
            send_turn(
                st.session_state,
                user_id=uid,
                text=question,
                build_context=build_global_partner_context,
                partner_reply=partner_reply,
                log_ai_usage=log_ai_usage,
                partner_error=PartnerError,
                log_exception=_log_exception,
            )
        st.rerun()


def render_partner_launcher(st) -> None:
    """The closed-state control, bottom right, above the workspace.

    A real Streamlit button in a keyed container rather than authored HTML, so
    it is keyboard-reachable and needs no script to work.
    """
    if st.session_state.get(PARTNER_OPEN_KEY):
        return
    with st.container(key="tl_partner_launcher"):
        if st.button("Ask about a trade", key="partner_open_btn", type="primary"):
            st.session_state[PARTNER_OPEN_KEY] = True
            st.rerun()


def render_partner_drawer(st) -> None:
    """The open state. Renders nothing at all when closed, so its controls are
    not in the tab order."""
    if not st.session_state.get(PARTNER_OPEN_KEY):
        return
    with st.container(key="tl_partner_drawer"):
        st.markdown(
            '<aside class="tl-partner-head" aria-label="AI Partner">'
            '<p class="tl-partner-title">AI Partner</p>'
            f'<p class="tl-partner-scope">{escape(SCOPE_NOTE)}</p></aside>',
            unsafe_allow_html=True,
        )
        # First in DOM order: with no script there is no Esc-to-close, so the
        # visible control is the only way out and must be reachable first.
        if st.button("Close", key="partner_close_btn"):
            st.session_state[PARTNER_OPEN_KEY] = False
            st.rerun()
        render_partner_body(st, surface="drawer")
