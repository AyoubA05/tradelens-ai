"""The send path's orderings, pinned.

Every collaborator is injected, so each ordering is proved without a database,
a model, or a cost table.
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple

import pytest

from src.tradelens.ui.components.partner_turn import (
    API_TURN_FIELDS,
    CONTEXT_FIELD,
    CONTEXT_USED_LABEL,
    NO_USER_ERROR,
    UNEXPECTED_ERROR,
    TurnResult,
    context_used_for,
    context_used_rows,
    error_key,
    history_key,
    send_turn,
    to_api_messages,
)


class FakePartnerError(Exception):
    pass


@dataclass(frozen=True)
class FakeSource:
    kind: str = "journal"
    record_id: int = 1
    user_id: int = 7
    label: str = "2026-08-01 NQ — sized up after a loss"
    occurred_on: Optional[str] = None


@dataclass(frozen=True)
class FakeContext:
    context_text: str = "## Journal notes\n- 2026-08-01: sized up after a loss"
    strategy_profile: Optional[dict] = None
    evidence_sources: Tuple[FakeSource, ...] = field(default_factory=tuple)
    completed_trade_count: int = 6
    journal_entry_count: int = 6


def _recorder():
    calls = []

    def fn(*args, **kwargs):
        calls.append((args, kwargs))

    fn.calls = calls
    return fn


def _reply_ok(*_a, **_k):
    return "You sized up after two losses.", {"input_tokens": 10, "output_tokens": 4}


def _wire(**overrides):
    wiring = dict(
        build_context=lambda *, user_id: FakeContext(),
        partner_reply=_reply_ok,
        log_ai_usage=_recorder(),
        partner_error=FakePartnerError,
        log_exception=_recorder(),
    )
    wiring.update(overrides)
    return wiring


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_a_successful_turn_appends_both_turns_in_order():
    state = {}
    result = send_turn(state, user_id=7, text="What did I do well?", **_wire())
    assert isinstance(result, TurnResult) and result.ok
    history = state[history_key(7)]
    assert [t["role"] for t in history] == ["user", "assistant"]
    assert history[0]["content"] == "What did I do well?"
    assert history[1]["content"] == "You sized up after two losses."


def test_the_reply_is_produced_in_general_reflective_mode():
    seen = {}

    def spy(messages, **kwargs):
        seen.update(kwargs)
        seen["messages"] = messages
        return _reply_ok()

    send_turn({}, user_id=7, text="q", **_wire(partner_reply=spy))
    assert seen["per_trade_qa"] is False


def test_the_authenticated_user_id_reaches_the_context_adapter():
    seen = {}

    def spy(*, user_id):
        seen["user_id"] = user_id
        return FakeContext()

    send_turn({}, user_id=7, text="q", **_wire(build_context=spy))
    assert seen["user_id"] == 7


def test_usage_is_logged_once_per_completed_response():
    logger = _recorder()
    send_turn({}, user_id=7, text="q", **_wire(log_ai_usage=logger))
    assert len(logger.calls) == 1
    args, kwargs = logger.calls[0]
    assert args[0] == "AI Partner"
    assert kwargs["user_id"] == 7


def test_blank_input_does_nothing_at_all():
    state = {}
    for blank in ("", "   ", "\n\t"):
        assert send_turn(state, user_id=7, text=blank, **_wire()).ok is False
    assert state == {}


def test_zero_completed_trades_never_calls_or_bills_the_model():
    """A post-trade Partner has nothing grounded to review without a trade."""
    model = _recorder()
    usage = _recorder()
    state = {}

    result = send_turn(
        state,
        user_id=7,
        text="What did I repeat?",
        **_wire(
            build_context=lambda *, user_id: FakeContext(
                context_text="",
                completed_trade_count=0,
                journal_entry_count=0,
            ),
            partner_reply=model,
            log_ai_usage=usage,
        ),
    )

    assert result.ok is False
    assert "completed trade" in (result.error or "").lower()
    assert model.calls == []
    assert usage.calls == []


# ---------------------------------------------------------------------------
# History projection and per-turn labels
# ---------------------------------------------------------------------------


def test_only_role_and_content_reach_the_model():
    history = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a", CONTEXT_FIELD: ["a label"]},
    ]
    projected = to_api_messages(history)
    assert projected == [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]
    for turn in projected:
        assert set(turn) <= set(API_TURN_FIELDS)


def test_the_model_never_sees_the_context_labels_as_conversation():
    seen = {}

    def spy(messages, **_k):
        seen["messages"] = messages
        return _reply_ok()

    state = {}
    wiring = _wire(
        build_context=lambda *, user_id: FakeContext(evidence_sources=(FakeSource(),)),
        partner_reply=spy,
    )
    send_turn(state, user_id=7, text="first", **wiring)
    send_turn(state, user_id=7, text="second", **wiring)
    for turn in seen["messages"]:
        assert CONTEXT_FIELD not in turn


def test_each_answer_keeps_the_labels_it_was_answered_from():
    """A rerun re-renders every turn. Labels stored globally would put the
    newest context under an answer that predates it."""
    state = {}
    first = FakeContext(evidence_sources=(FakeSource(label="older record"),))
    second = FakeContext(evidence_sources=(FakeSource(label="newer record"),))
    contexts = iter((first, second))
    wiring = _wire(build_context=lambda *, user_id: next(contexts))
    send_turn(state, user_id=7, text="one", **wiring)
    send_turn(state, user_id=7, text="two", **wiring)

    answers = [t for t in state[history_key(7)] if t["role"] == "assistant"]
    assert context_used_for(answers[0]) == ("older record",)
    assert context_used_for(answers[1]) == ("newer record",)


def test_a_user_turn_carries_no_context_labels():
    state = {}
    send_turn(state, user_id=7, text="q", **_wire())
    assert context_used_for(state[history_key(7)][0]) == ()


def test_context_rows_read_the_adapters_labels():
    ctx = FakeContext(evidence_sources=(FakeSource(label="A"), FakeSource(label="B")))
    assert context_used_rows(ctx) == ("A", "B")
    assert context_used_rows(FakeContext()) == ()
    assert context_used_rows(object()) == ()


def test_the_context_heading_is_not_a_citation_claim():
    """`partner_reply` returns text and usage only, so it cannot report which
    records a sentence drew on. The wording is a contract."""
    assert CONTEXT_USED_LABEL == "Context used"
    assert "source" not in CONTEXT_USED_LABEL.lower()
    assert "cited" not in CONTEXT_USED_LABEL.lower()


# ---------------------------------------------------------------------------
# Containment — three boundaries, not one
# ---------------------------------------------------------------------------


def test_a_context_failure_is_contained_like_any_other():
    """Assembling context opens a session, so it can raise a driver error
    carrying a DSN. Outside the containment it would reach the page."""

    def boom(*, user_id):
        raise RuntimeError("could not connect to postgres://user:pw@host/db")

    state = {}
    logs = _recorder()
    result = send_turn(
        state, user_id=7, text="q", **_wire(build_context=boom, log_exception=logs)
    )
    assert result.ok is False
    assert result.error == UNEXPECTED_ERROR
    assert state[error_key(7)] == UNEXPECTED_ERROR
    assert "postgres://" not in result.error
    assert len(logs.calls) == 1


def test_a_model_failure_is_contained_and_says_nothing_about_the_driver():
    def boom(*_a, **_k):
        raise RuntimeError("sk-ant-secret leaked in a driver string")

    state = {}
    result = send_turn(state, user_id=7, text="q", **_wire(partner_reply=boom))
    assert result.error == UNEXPECTED_ERROR
    assert "sk-ant" not in state[error_key(7)]


@pytest.mark.parametrize("failing", ["build_context", "partner_reply"])
def test_a_domain_error_keeps_its_trader_safe_wording(failing):
    """PartnerError is already phrased for a trader, so it is shown as-is."""

    def boom(*_a, **_k):
        raise FakePartnerError("Add a few journal notes and try again.")

    state = {}
    result = send_turn(state, user_id=7, text="q", **_wire(**{failing: boom}))
    assert result.ok is False
    assert result.error == "Add a few journal notes and try again."
    assert state[error_key(7)] == "Add a few journal notes and try again."


def test_a_failed_turn_still_leaves_the_question_on_screen():
    """Re-typing is the one thing an error must never cost."""

    def boom(*_a, **_k):
        raise FakePartnerError("nope")

    state = {}
    send_turn(state, user_id=7, text="What did I repeat?", **_wire(partner_reply=boom))
    assert state[history_key(7)][-1] == {
        "role": "user",
        "content": "What did I repeat?",
    }


def test_a_failed_cost_write_never_costs_the_trader_the_answer():
    """The reply is already the trader's. Bookkeeping that fails records the
    truth in `usage_logged` rather than discarding it."""

    def boom(*_a, **_k):
        raise RuntimeError("cost table is read-only")

    state = {}
    logs = _recorder()
    result = send_turn(
        state, user_id=7, text="q", **_wire(log_ai_usage=boom, log_exception=logs)
    )
    assert result.ok is True
    assert result.usage_logged is False
    assert state[history_key(7)][-1]["role"] == "assistant"
    assert len(logs.calls) == 1


def test_a_new_turn_clears_the_previous_error():
    state = {error_key(7): "old failure"}
    send_turn(state, user_id=7, text="q", **_wire())
    assert error_key(7) not in state


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def test_history_is_scoped_per_user():
    assert history_key(7) != history_key(8)
    assert error_key(7) != error_key(8)


def test_two_users_in_one_session_never_share_a_conversation():
    """Session state can outlive a sign-out in one tab."""
    state = {}
    send_turn(state, user_id=7, text="seven's question", **_wire())
    send_turn(state, user_id=8, text="eight's question", **_wire())
    seven = [t["content"] for t in state[history_key(7)]]
    eight = [t["content"] for t in state[history_key(8)]]
    assert "eight's question" not in seven
    assert "seven's question" not in eight


@pytest.mark.parametrize("bad", [None, 0, -1, "7", True])
def test_an_ownerless_send_is_refused_before_any_session_opens(bad):
    """The adapter rejects a missing owner by raising, which the containment
    would report as "temporarily unavailable" — sending the trader to retry
    something that cannot succeed. It is refused here, by name."""
    opened = _recorder()
    state = {}
    result = send_turn(
        state, user_id=bad, text="q", **_wire(build_context=lambda *, user_id: opened())
    )
    assert result.ok is False
    assert result.error == NO_USER_ERROR
    assert opened.calls == [], "a session was opened for an ownerless send"


# ---------------------------------------------------------------------------
# The retry path — a property the plan's suite does not reach.
# ---------------------------------------------------------------------------


def test_a_retry_replaces_the_question_it_is_retrying():
    """A failed turn leaves the question in history so the trader does not
    retype it. The moment they DO send again, the abandoned turn stops being
    conversation: left in place, the next call sends BOTH questions, the model
    answers a two-question prompt, and the trader is billed for the one that
    was never answered.

    Only a trailing USER turn is dropped — an assistant turn at the end means
    the previous exchange completed and must survive.
    """
    seen = {}

    def spy(messages, **_k):
        seen["messages"] = list(messages)
        return _reply_ok()

    def boom(*_a, **_k):
        raise FakePartnerError("nope")

    state = {}
    send_turn(state, user_id=7, text="first attempt", **_wire(partner_reply=boom))
    assert [t["content"] for t in state[history_key(7)]] == ["first attempt"]

    send_turn(state, user_id=7, text="second attempt", **_wire(partner_reply=spy))
    assert [t["content"] for t in seen["messages"]] == ["second attempt"]
    assert [t["content"] for t in state[history_key(7)]] == [
        "second attempt",
        "You sized up after two losses.",
    ]


def test_a_completed_exchange_is_never_dropped_by_the_next_question():
    state = {}
    send_turn(state, user_id=7, text="one", **_wire())
    send_turn(state, user_id=7, text="two", **_wire())
    assert [t["content"] for t in state[history_key(7)]] == [
        "one",
        "You sized up after two losses.",
        "two",
        "You sized up after two losses.",
    ]


def test_repeated_failures_never_stack_unanswered_questions():
    def boom(*_a, **_k):
        raise FakePartnerError("nope")

    state = {}
    for attempt in ("one", "two", "three"):
        send_turn(state, user_id=7, text=attempt, **_wire(partner_reply=boom))
    assert [t["content"] for t in state[history_key(7)]] == ["three"]


def test_the_send_path_holds_no_streamlit_import():
    """The orderings above are provable without a browser only while this
    stays true."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "src/tradelens/ui/components/partner_turn.py"
    ).read_text(encoding="utf-8")
    assert "import streamlit" not in source


def test_the_send_path_does_not_trim_history_behind_the_service():
    """`partner_reply` already trims to its own limit and carries a running
    summary of what it dropped. A second trimming rule here would disagree
    with the service's and silently drop turns it intended to summarise.

    Asserted behaviourally. A first draft scanned the source for the service's
    constant name and failed on the docstring that explains why it is absent —
    the same brittleness a comment triggered in the auth-screen contract in
    Task 13. What matters is that nothing is dropped, so that is what is run.
    """
    state = {}
    sent = []
    for i in range(24):
        send_turn(
            state,
            user_id=7,
            text=f"question {i}",
            **_wire(partner_reply=lambda m, **_k: (f"answer {len(m)}", {})),
        )
        sent.append(f"question {i}")

    stored = [t["content"] for t in state[history_key(7)] if t["role"] == "user"]
    assert stored == sent, "the UI dropped turns the service intended to keep"


# ---------------------------------------------------------------------------
# Availability — what the surface may offer, decided without Streamlit
# ---------------------------------------------------------------------------


def _avail(**over):
    from src.tradelens.ui.components.partner_turn import partner_availability

    kwargs = dict(user_id=7, ai_ready=True, context=FakeContext())
    kwargs.update(over)
    return partner_availability(**kwargs)


def test_ownerless_preview_never_reads_context_or_offers_a_launcher():
    """The panel owns context construction; this pure boundary must decide
    ownerlessness before it asks anything of the context it was handed."""
    from src.tradelens.ui.components import partner_turn

    class ContextMustNotBeRead:
        def __getattribute__(self, name):
            raise AssertionError(f"ownerless availability read context.{name}")

    state = partner_turn.partner_availability(
        user_id=None,
        ai_ready=True,
        context=ContextMustNotBeRead(),
        context_failed=False,
    )

    assert state.can_send is False
    assert state.show_launcher is False
    assert state.reason == partner_turn.OWNERLESS_PREVIEW


def test_an_ownerless_session_may_not_send_and_says_why():
    """A legacy login with no user id cannot be scoped to an owner, so the
    adapter would refuse it anyway. The surface must say so rather than offer
    a composer that produces an error on every submission."""
    from src.tradelens.ui.components.partner_turn import OWNERLESS_PREVIEW

    for bad in (None, 0, -1, "7", True):
        state = _avail(user_id=bad, context=None)
        assert state.can_send is False
        assert state.reason == OWNERLESS_PREVIEW
        assert state.show_launcher is False
        assert state.route is None, "there is no route out of a legacy login"


def test_an_ownerless_session_is_decided_before_any_context_is_needed():
    """`build_global_partner_context` raises on a missing owner, so the
    decision cannot depend on having called it."""
    assert _avail(user_id=None, context=None).can_send is False


def test_the_partner_is_unavailable_when_no_model_is_configured():
    from src.tradelens.ui.components.partner_turn import AI_UNAVAILABLE

    state = _avail(ai_ready=False)
    assert state.can_send is False
    assert state.show_launcher is True
    assert state.reason == AI_UNAVAILABLE
    assert "key" not in state.reason.lower(), "never name the secret"
    assert "ANTHROPIC" not in state.reason


def test_a_missing_model_outranks_a_missing_trade():
    """Both are true on a fresh install; the one the trader cannot fix by
    logging a trade is the one to state."""
    from src.tradelens.ui.components.partner_turn import AI_UNAVAILABLE

    state = _avail(ai_ready=False, context=FakeContext(completed_trade_count=0))
    assert state.reason == AI_UNAVAILABLE


def test_no_completed_trades_offers_the_route_that_fixes_it():
    from src.tradelens.ui.components.partner_turn import NO_TRADES_ERROR

    state = _avail(context=FakeContext(completed_trade_count=0))
    assert state.can_send is False
    assert state.reason == NO_TRADES_ERROR
    assert state.route == ("Log a completed trade", "/NewTrade")


def test_a_missing_strategy_profile_is_a_notice_not_a_blocker():
    """The Partner reads three sources and can answer from two of them. A
    missing playbook makes the answers thinner, not impossible."""
    state = _avail(context=FakeContext(strategy_profile=None))
    assert state.can_send is True
    assert state.profile_missing is True
    assert state.profile_route == ("Add your Strategy Profile", "/Strategy")


def test_a_present_strategy_profile_raises_no_notice():
    state = _avail(context=FakeContext(strategy_profile={"name": "ICT"}))
    assert state.can_send is True
    assert state.profile_missing is False


def test_a_ready_partner_states_no_reason_at_all():
    state = _avail()
    assert state.can_send is True
    assert state.reason is None
    assert state.route is None


def test_availability_never_raises_on_a_context_it_cannot_read():
    """It runs inside a render path."""
    for junk in (None, object(), 123):
        state = _avail(context=junk)
        assert state.can_send in (True, False)


def test_the_send_gate_and_the_surface_gate_agree_about_zero_trades():
    """Codex's send-path gate is the enforcement; this is the presentation.
    They must name the same condition, or the surface offers a composer whose
    every submission is refused."""
    from src.tradelens.ui.components.partner_turn import NO_TRADES_ERROR

    state = {}
    result = send_turn(
        state,
        user_id=7,
        text="q",
        **_wire(build_context=lambda *, user_id: FakeContext(completed_trade_count=0)),
    )
    assert result.error == NO_TRADES_ERROR
    assert _avail(context=FakeContext(completed_trade_count=0)).reason == (
        NO_TRADES_ERROR
    )


# ---------------------------------------------------------------------------
# Clearing a conversation
# ---------------------------------------------------------------------------


def test_clearing_removes_every_trace_of_the_conversation():
    from src.tradelens.ui.components.partner_turn import clear_conversation

    state = {
        history_key(7): [{"role": "user", "content": "q"}],
        error_key(7): "something failed",
        "_partner_pending_drawer": "a queued suggestion",
        "_partner_busy_drawer": True,
        "partner_in_drawer": "half-typed text",
        history_key(8): [{"role": "user", "content": "someone else"}],
        "unrelated": "keep me",
    }
    clear_conversation(state, user_id=7, surfaces=("drawer", "page"))

    assert history_key(7) not in state
    assert error_key(7) not in state
    assert "_partner_pending_drawer" not in state
    assert "_partner_busy_drawer" not in state
    assert "partner_in_drawer" not in state
    # Another user's conversation is not this user's to clear.
    assert state[history_key(8)] == [{"role": "user", "content": "someone else"}]
    assert state["unrelated"] == "keep me"


def test_clearing_an_empty_conversation_is_harmless():
    from src.tradelens.ui.components.partner_turn import clear_conversation

    state = {}
    clear_conversation(state, user_id=7, surfaces=("drawer",))
    assert state == {}


def test_clearing_covers_every_surface_the_conversation_can_be_open_on():
    """A pending suggestion left on the page would fire the moment the trader
    navigated there after clearing in the drawer."""
    from src.tradelens.ui.components.partner_turn import clear_conversation

    state = {
        "_partner_pending_drawer": "x",
        "_partner_pending_page": "y",
        "_partner_busy_page": True,
    }
    clear_conversation(state, user_id=7, surfaces=("drawer", "page"))
    assert state == {}


# ---------------------------------------------------------------------------
# A context that could not be built is not an empty account
# ---------------------------------------------------------------------------


def test_a_failed_context_is_temporary_not_a_missing_trade():
    """`build_global_partner_context` opens a session, so it can fail with a
    driver error. Reading that failure as "you have no trades" tells a trader
    with a full journal to go and log one, and offers a route that fixes
    nothing — the database is down, not their account.
    """
    from src.tradelens.ui.components.partner_turn import (
        CONTEXT_UNAVAILABLE,
        NO_TRADES_ERROR,
    )

    state = _avail(context=None, context_failed=True)
    assert state.can_send is False
    assert state.reason == CONTEXT_UNAVAILABLE
    assert state.reason != NO_TRADES_ERROR
    assert state.route is None, "there is no route that fixes a failed read"


def test_a_failed_context_says_nothing_about_the_driver():
    from src.tradelens.ui.components.partner_turn import CONTEXT_UNAVAILABLE

    lowered = CONTEXT_UNAVAILABLE.lower()
    for leak in ("postgres", "sqlite", "dsn", "traceback", "psycopg"):
        assert leak not in lowered


def test_a_genuinely_empty_account_still_gets_the_new_trade_route():
    """The fix must not blunt the real no-trades state into a shrug."""
    from src.tradelens.ui.components.partner_turn import NO_TRADES_ERROR

    state = _avail(context=FakeContext(completed_trade_count=0), context_failed=False)
    assert state.reason == NO_TRADES_ERROR
    assert state.route == ("Log a completed trade", "/NewTrade")


def test_a_failed_context_outranks_every_other_reason_except_ownership():
    """Nothing downstream can be trusted once the read failed — but an
    ownerless session never attempted one, so it keeps its own message."""
    from src.tradelens.ui.components.partner_turn import (
        CONTEXT_UNAVAILABLE,
        OWNERLESS_PREVIEW,
    )

    assert _avail(context=None, context_failed=True).reason == CONTEXT_UNAVAILABLE
    assert (
        _avail(user_id=None, context=None, context_failed=True).reason
        == OWNERLESS_PREVIEW
    )


def test_a_missing_model_still_outranks_a_failed_context():
    """Both are infrastructure, and the AI one is the more specific truth."""
    from src.tradelens.ui.components.partner_turn import AI_UNAVAILABLE

    assert (
        _avail(ai_ready=False, context=None, context_failed=True).reason
        == AI_UNAVAILABLE
    )
