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
