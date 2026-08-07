"""The AI Partner send path, kept free of Streamlit so it can be tested.

`partner_panel.py` renders; this decides what one turn does. The split follows
`trade_wizard.py`: the rules that must be right do not need a browser to prove,
and proving them in one costs a suite that nobody runs.

Six behaviours here are load-bearing and each is pinned by a test:

1. **The user's turn is appended before anything can fail.** A failed turn must
   leave the trader's question on screen; re-typing it is the one thing an
   error must never cost.
2. **A retry replaces the question it is retrying.** Once the trader has
   retyped, the abandoned turn is not history — leaving it would send the model
   two questions and bill for both.
3. **Context construction is inside the containment.** Assembling context opens
   a database session, so it can fail with a driver error carrying a DSN. That
   failure has to be caught exactly like a model failure, not left to escape as
   a raw exception onto the page.
4. **Usage logging is contained separately, after the reply.** A cost-table
   write that fails must not discard an answer the trader already paid for. The
   turn stays successful; only `usage_logged` records the truth.
5. **Each assistant turn carries the context it was answered from.** The labels
   are stored on the turn, so a rerun re-renders the right list under the right
   answer instead of showing the newest context under every one.
6. **Stored history is projected to role and content before the model sees it.**
   Presentation metadata is ours, not the API's.

History length is deliberately NOT managed here. `partner_reply` already trims
to `MAX_TURNS` and carries a running summary of what it dropped; a second
trimming rule in the UI would silently disagree with the service's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, MutableMapping, Optional, Sequence, Tuple

# What the UI shows when something outside the domain fails. Fixed copy: the
# exception may carry a DSN, a driver string, or an API key.
UNEXPECTED_ERROR = "AI is temporarily unavailable. Please try again."

# Shown when the surface is reached without an authenticated user. Not the same
# thing as the AI being unavailable, and saying so would send a trader to
# retry something that cannot succeed.
NO_USER_ERROR = "Sign in to use the AI Partner."

# A global reflective answer must have at least one completed record behind it.
# This is enforced in the send path even when the presentation fails to hide
# its composer, so an empty account can never spend on an invented review.
NO_TRADES_ERROR = "Log at least one completed trade before using the AI Partner."

# The model is not configured. Deliberately says nothing about which secret is
# missing or where it lives — that is operator information, and a trader can do
# nothing with it.
AI_UNAVAILABLE = "The AI Partner is unavailable right now."

# The context read failed. Deliberately NOT the no-trades message: reading a
# driver failure as "you have no trades" tells a trader with a full journal to
# go and log one, and offers a route that fixes nothing.
CONTEXT_UNAVAILABLE = "Your journal could not be read just now. Try again in a moment."

# A question was queued, and by the time the sending pass ran the Partner
# could no longer answer it. Saying so beats both sending it anyway and
# dropping it in silence.
QUESTION_DISCARDED = (
    "That question was not sent. Ask it again when the Partner is available."
)

HISTORY_PREFIX = "partner_history_"
ERROR_PREFIX = "partner_error_"

# The heading the drawer and the Partner page put above the record list. It is
# part of the contract, not a caption choice — see context_used_rows.
CONTEXT_USED_LABEL = "Context used"

# Where a turn keeps the labels it was answered from. Stripped before the
# history reaches the model.
CONTEXT_FIELD = "context_used"

# The only keys the message API may receive from a stored turn.
API_TURN_FIELDS = ("role", "content")


def history_key(user_id: object) -> str:
    """Per-user history slot. Session state can outlive a sign-out in one tab,
    so the key carries the owner rather than trusting the session."""
    return f"{HISTORY_PREFIX}{user_id}"


def error_key(user_id: object) -> str:
    return f"{ERROR_PREFIX}{user_id}"


@dataclass(frozen=True)
class TurnResult:
    """What the render path needs to know about the turn that just ran."""

    ok: bool
    reply: Optional[str] = None
    error: Optional[str] = None
    usage_logged: bool = False
    context_used: Tuple[str, ...] = ()


def to_api_messages(history: Sequence[dict]) -> List[dict]:
    """Project stored turns down to what the model API accepts.

    Stored turns carry presentation metadata — the context labels each answer
    was produced from. That belongs to the UI. Sending it would put unrequested
    fields into the API payload and, worse, feed the model a list of record
    labels as though it were part of the conversation.
    """
    return [
        {field: turn[field] for field in API_TURN_FIELDS if field in turn}
        for turn in history
    ]


def context_used_for(turn: dict) -> Tuple[str, ...]:
    """The labels a single stored assistant turn was answered from.

    Empty for a user turn, and empty for an assistant turn produced when the
    trader had no records yet — in which case the UI renders no heading at all
    rather than an empty one.
    """
    return tuple(turn.get(CONTEXT_FIELD) or ())


def context_used_rows(context) -> Tuple[str, ...]:
    """Labels for the records fed into the prompt — not citations for an answer.

    `partner_reply` returns only text and usage. It cannot report which records
    a given sentence drew on, so presenting these as per-answer citations would
    assert a relationship the service never established. They are labelled
    "Context used" for that reason, and the wording is part of the contract
    rather than a caption choice.
    """
    return tuple(source.label for source in getattr(context, "evidence_sources", ()))


def _drop_abandoned_question(history: List[Dict]) -> None:
    """Remove a trailing user turn that never got an answer.

    A failed turn leaves the question on screen so the trader does not have to
    retype it (rule 1). The moment they DO send again, that turn is not
    conversation any more — it is a question the model never saw an answer to.
    Left in place, the next call sends both questions, the model answers a
    two-question prompt, and the trader is billed for the abandoned one.

    Only ever removes the LAST turn, and only when it is a user turn: an
    assistant turn at the end means the previous exchange completed.
    """
    if history and history[-1].get("role") == "user":
        history.pop()


@dataclass(frozen=True)
class PartnerAvailability:
    """What the surface may offer this trader, and what to say when it may not.

    Decided here rather than in the panel so it can be proved without a
    browser, and so the presentation and Codex's send-path gate cannot drift
    into disagreeing about when a turn is allowed — a surface that offers a
    composer whose every submission is refused is worse than one that explains
    itself.

    `reason` is trader-facing copy. `route` is the destination that fixes the
    reason, or None when nothing the trader can do would.
    """

    can_send: bool
    reason: Optional[str] = None
    route: Optional[Tuple[str, str]] = None
    profile_missing: bool = False
    profile_route: Optional[Tuple[str, str]] = None


def partner_availability(
    *, user_id: object, ai_ready: bool, context: object, context_failed: bool = False
) -> PartnerAvailability:
    """Whether the Partner can take a question, and what to say if not.

    `context` is a `PartnerContext` from the approved adapter, or None when
    there was no owner to build one for. Nothing here queries anything: the
    caller has already built the context through the one approved path, and a
    second read here would be a second data path.

    Order matters, and the order is: no owner, no model, no context, no trade.
    A missing model outranks a missing trade because both are true on a fresh
    install and only one is something a trader can fix by logging a trade. A
    failed context outranks the trade count because a read that did not happen
    reports no trades, and that is not the same fact.

    `context_failed` is the caller telling us the adapter raised. It is passed
    rather than inferred, because a context of None is also what an ownerless
    session produces, and those two need different answers.
    """
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        # No owner means no scope. The adapter refuses this before it opens a
        # session, and there is no route out of a legacy login from here.
        return PartnerAvailability(can_send=False, reason=NO_USER_ERROR)

    if not ai_ready:
        return PartnerAvailability(can_send=False, reason=AI_UNAVAILABLE)

    if context_failed:
        # Nothing downstream can be trusted once the read failed, and the
        # trader can do nothing about it — so no route is offered. This sits
        # ABOVE the trade count on purpose: a failed read has no trade count,
        # and the absent one must not be read as zero.
        return PartnerAvailability(can_send=False, reason=CONTEXT_UNAVAILABLE)

    trades = getattr(context, "completed_trade_count", None)
    try:
        trades = int(trades or 0)
    except (TypeError, ValueError):
        trades = 0
    if trades <= 0:
        return PartnerAvailability(
            can_send=False,
            reason=NO_TRADES_ERROR,
            route=("Log a completed trade", "/NewTrade"),
        )

    profile_missing = not getattr(context, "strategy_profile", None)
    return PartnerAvailability(
        can_send=True,
        profile_missing=profile_missing,
        profile_route=(
            ("Add your Strategy Profile", "/Strategy") if profile_missing else None
        ),
    )


def clear_conversation(
    state: MutableMapping, *, user_id: object, surfaces: Sequence[str]
) -> None:
    """Remove this user's conversation and everything attached to it.

    Every surface is cleared, not just the one the button was pressed on: a
    pending suggestion left on the page would fire the moment the trader
    navigated there after clearing in the drawer.

    Scoped to one owner. Another user's history in the same session is not
    this user's to delete.
    """
    state.pop(history_key(user_id), None)
    state.pop(error_key(user_id), None)
    for surface in surfaces:
        for prefix in ("_partner_pending_", "_partner_busy_", "partner_in_"):
            state.pop(f"{prefix}{surface}", None)


def send_turn(
    state: MutableMapping,
    *,
    user_id: int,
    text: str,
    build_context: Callable,
    partner_reply: Callable,
    log_ai_usage: Callable,
    partner_error: type,
    log_exception: Optional[Callable] = None,
) -> TurnResult:
    """Run one Partner turn against the authenticated user's own context.

    Every collaborator is injected rather than imported here, so a test can
    prove the ordering without a database, a model, or a cost table. The page
    wires the real ones.
    """
    question = (text or "").strip()
    if not question:
        return TurnResult(ok=False, error=None)

    # An ownerless send cannot succeed: the context adapter rejects a missing
    # user id before it opens a session. Saying so beats containing it as
    # "temporarily unavailable" and inviting a retry that cannot work.
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        state[error_key(user_id)] = NO_USER_ERROR
        return TurnResult(ok=False, error=NO_USER_ERROR)

    history: List[Dict] = state.setdefault(history_key(user_id), [])
    state.pop(error_key(user_id), None)

    # 1 and 2. The retry supersedes the question it retries, then the trader's
    #          turn lands and stays, whatever happens next.
    _drop_abandoned_question(history)
    history.append({"role": "user", "content": question})

    def _contain(exc_label: str) -> TurnResult:
        """Log the failure, store fixed copy, and tell the trader nothing about
        the driver, the DSN, or the key that produced it."""
        if log_exception is not None:
            log_exception(exc_label)
        state[error_key(user_id)] = UNEXPECTED_ERROR
        return TurnResult(ok=False, error=UNEXPECTED_ERROR)

    # 3. Context assembly opens a session, so it fails like anything else that
    #    touches a database — inside the containment, never outside it.
    try:
        context = build_context(user_id=user_id)
    except partner_error as exc:
        state[error_key(user_id)] = str(exc)
        return TurnResult(ok=False, error=str(exc))
    except Exception:
        return _contain("AI Partner context assembly failed")

    if int(getattr(context, "completed_trade_count", 0) or 0) <= 0:
        state[error_key(user_id)] = NO_TRADES_ERROR
        return TurnResult(ok=False, error=NO_TRADES_ERROR)

    labels = context_used_rows(context)

    try:
        reply, usage = partner_reply(
            to_api_messages(history),
            trade_context=context.context_text,
            strategy_profile=context.strategy_profile,
            per_trade_qa=False,
        )
    except partner_error as exc:
        # Domain failure: the service already phrased this for a trader.
        state[error_key(user_id)] = str(exc)
        return TurnResult(ok=False, error=str(exc))
    except Exception:
        return _contain("AI Partner turn failed")

    # 5. The answer is the trader's now. Append it before anything else can go
    #    wrong, and carry the labels it was produced from.
    history.append({"role": "assistant", "content": reply, CONTEXT_FIELD: list(labels)})

    # 4. Cost logging is bookkeeping. If it fails, the answer still stands; the
    #    result records that the write did not happen rather than pretending.
    usage_logged = False
    try:
        log_ai_usage("AI Partner", usage, user_id=user_id)
        usage_logged = True
    except Exception:
        if log_exception is not None:
            log_exception("AI Partner usage logging failed")

    return TurnResult(
        ok=True, reply=reply, usage_logged=usage_logged, context_used=labels
    )
