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
    QUEUE_KEY,
    QUESTION_DISCARDED,
    claim_question,
    current_run,
    queue_question,
    clear_conversation,
    context_used_for,
    error_key,
    history_key,
    partner_availability,
    send_turn,
)
from src.tradelens.utils.ai_utils import ai_available

# Both surfaces the conversation can be open on. Clearing has to reach every
# one of them, not just the one the button was pressed on.
PARTNER_SURFACES = ("drawer", "page")

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


def _availability(st):
    """This trader's availability, built through the one approved adapter.

    The context is read once per render and reused for every decision on the
    surface. It is NOT reused for the send: `send_turn` builds its own, because
    what was true when the page painted is not necessarily true when the
    question is asked.
    """
    from src.tradelens.ui.components.auth import current_user_id

    uid = current_user_id()
    context = None
    context_failed = False
    if isinstance(uid, int) and not isinstance(uid, bool) and uid > 0:
        try:
            context = build_global_partner_context(user_id=uid)
        except Exception:  # noqa: BLE001 — a render path must never raise
            # The failure is passed on rather than left to be inferred from a
            # context of None, which is also what an ownerless session
            # produces — and which the availability rules would otherwise read
            # as "no trades", sending a trader with a full journal to log one.
            context_failed = True
            _log_exception("AI Partner availability context failed")
    return uid, partner_availability(
        user_id=uid,
        ai_ready=ai_available(),
        context=context,
        context_failed=context_failed,
    )


def _route_link(st, label: str, slug: str, key: str) -> None:
    """A way out of a state the trader can actually fix.

    `page_link` needs the multipage registry, which registry-less AppTest boots
    do not build — the same fallback every other route in this product uses.
    """
    paths = {"/NewTrade": "pages/1_NewTrade.py", "/Strategy": "pages/5_Strategy.py"}
    try:
        st.page_link(paths[slug], label=f"{label} →")
    except Exception:  # noqa: BLE001 — registry-less boots only
        from src.tradelens.ui.components.sidebar import route_href

        href = escape(route_href(slug, st.query_params.get("auth")), quote=True)
        st.markdown(
            f'<a href="{href}" target="_self">{escape(label)} →</a>',
            unsafe_allow_html=True,
        )


def _unavailable(st, state, *, surface: str) -> None:
    """Say why the Partner cannot take a question, and offer the way out.

    `role="status"` rather than `alert`: nothing has gone wrong, and an alert
    would interrupt a screen reader to announce a condition the trader may
    already know about.
    """
    st.markdown(
        f'<p class="tl-partner-empty" role="status">{escape(str(state.reason))}</p>',
        unsafe_allow_html=True,
    )
    if state.route:
        _route_link(st, state.route[0], state.route[1], f"partner_{surface}_route")


def render_partner_status(reason: object) -> str:
    """One non-action status for a launcher that cannot open a useful drawer."""
    return (
        '<p class="tl-partner-launcher-note" role="status">'
        f"{escape(str(reason))}</p>"
    )


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
    uid, state = _availability(st)
    history = st.session_state.get(history_key(uid)) or []
    run_id = current_run(st.session_state)
    # This presentation is "sending" only if the queue is its own AND was made
    # by the run immediately before this one. Both bodies execute on every run
    # regardless of which the width shows, so a queue that survives longer
    # belongs to a run nobody finished watching.
    queued = st.session_state.get(QUEUE_KEY)
    mine = isinstance(queued, dict) and queued.get("surface") == surface
    busy = mine and int(queued.get("run") or 0) + 1 == run_id
    if mine and not busy:
        # Mine, but from a run that never came back — the trader navigated
        # away, the socket dropped, the tab closed. Discard it HERE, on the
        # healthy path too: skipping it would leave it in place for whichever
        # run next happened to land adjacent, which is the invisible send this
        # whole mechanism exists to prevent.
        st.session_state.pop(QUEUE_KEY, None)

    # Turns first, always. Whatever else this render is doing — refusing,
    # sending, or reporting a failure — the conversation the trader already
    # has stays exactly where it was.
    if history:
        for turn in history:
            _render_turn(st, turn)

    if not state.can_send:
        # A question queued on a previous pass cannot be sent now, and must not
        # survive to be sent by some later pass that happens to find
        # availability restored — that would be model usage, and a bill, that
        # the trader never asked for. Discard it here and say so.
        discarded = claim_question(st.session_state, surface=surface, run_id=run_id)

        # No composer at all. A disabled one would still read as "type here",
        # and an enabled one would refuse every submission.
        _unavailable(st, state, surface=surface)
        if discarded:
            st.markdown(
                f'<p class="tl-partner-error" role="alert">'
                f"{escape(QUESTION_DISCARDED)}</p>",
                unsafe_allow_html=True,
            )
        if history:
            _clear_control(st, uid, surface)
        return

    # The notice belongs to the surface, not to its empty state: it was
    # rendered only when there was no history, so the reason a trader's
    # answers were thin vanished the moment they asked anything.
    if state.profile_missing:
        st.markdown(
            '<p class="tl-partner-empty" role="status">'
            "No Strategy Profile yet, so answers cannot weigh your trades "
            "against your own rules.</p>",
            unsafe_allow_html=True,
        )
        _route_link(
            st,
            state.profile_route[0],
            state.profile_route[1],
            f"partner_{surface}_profile",
        )

    if not history:
        st.markdown(
            f'<p class="tl-partner-empty">{escape(EMPTY_STATE_BODY)}</p>',
            unsafe_allow_html=True,
        )
        for i, question in enumerate(SUGGESTED_QUESTIONS):
            if st.button(
                question,
                key=f"secondary_partner_{surface}_chip_{i}",
                disabled=busy,
            ):
                queue_question(
                    st.session_state, surface=surface, text=question, run_id=run_id
                )
                st.rerun()

    error = st.session_state.get(error_key(uid))
    if error and not busy:
        st.markdown(
            f'<p class="tl-partner-error" role="alert">{escape(str(error))}</p>',
            unsafe_allow_html=True,
        )

    typed = st.chat_input(
        "Ask about a trade you have logged",
        key=f"partner_in_{surface}",
        disabled=busy,
    )

    if history and not busy:
        _clear_control(st, uid, surface)

    if busy:
        # Second pass. The composer above is already rendered disabled and the
        # turns are already on screen, so the status line changes nothing above
        # it and the page does not jump.
        st.markdown(
            '<p class="tl-partner-status" role="status" aria-live="polite">'
            "Reading your journal…</p>",
            unsafe_allow_html=True,
        )
        question = claim_question(st.session_state, surface=surface, run_id=run_id)
        if question:
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
        return

    if typed:
        # First pass records the intent and reruns. A Streamlit widget cannot
        # become disabled inside its own handler — the script run is blocking,
        # so the browser holds a live composer for the whole call unless the
        # disabled state is rendered on a pass of its own. The queue is stamped
        # with this run, which is what limits it to the single rerun it needs.
        queue_question(st.session_state, surface=surface, text=typed, run_id=run_id)
        st.rerun()


def _clear_control(st, uid, surface: str) -> None:
    """Start again. Immediate, because a confirmation step on something with
    no lasting consequence is friction — the conversation was never saved."""
    if st.button("Clear conversation", key=f"secondary_partner_{surface}_clear"):
        clear_conversation(st.session_state, user_id=uid, surfaces=PARTNER_SURFACES)
        st.rerun()


def render_partner_launcher(st) -> None:
    """The closed-state control, bottom right, above the workspace.

    A real Streamlit button in a keyed container rather than authored HTML, so
    it is keyboard-reachable and needs no script to work.

    When a normal owned account cannot take a question, one status explains
    why and no dead button is rendered. Ownerless preview accounts have no
    desktop launcher at all; their dedicated page states the truthful reason.
    """
    if st.session_state.get(PARTNER_OPEN_KEY):
        return
    _uid, state = _availability(st)
    if not state.show_launcher:
        return
    if not state.can_send:
        st.markdown(render_partner_status(state.reason), unsafe_allow_html=True)
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
