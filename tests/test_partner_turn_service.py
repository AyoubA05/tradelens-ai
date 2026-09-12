"""The AI Partner turn service (Phase 8, Task B3).

Order under test: question → chain verification → owner-scoped context →
text-free ticket (limit + duplicate) → provider → sign the reply the trader
sees → close the ticket. Nothing before the provider call may spend, and no
row may keep conversation text.

The provider is faked at `partner.partner_reply` unless a test needs the real
scope guard, in which case `partner.converse` is faked instead.
"""

from __future__ import annotations

import base64
import threading
import time

import pytest

from src.tradelens.db.models import AIJob, Screenshot, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import partner
from src.tradelens.services import partner_transcript as pt
from src.tradelens.services import partner_turns as turns

SECRET = "test-service-secret-value-at-least-32-bytes"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
REPLY = "Reviewing the completed trade: your entry waited for the sweep."


@pytest.fixture(autouse=True)
def service_secret(monkeypatch):
    monkeypatch.setenv("TL_SERVICE_SECRET", SECRET)
    monkeypatch.delenv("TL_SERVICE_SECRET_PREVIOUS", raising=False)


class FakeProvider:
    """Stands in for partner.partner_reply; records every call."""

    def __init__(self, reply=REPLY, usage="USAGE", raise_after_usage=None):
        self.calls = []
        self.reply = reply
        self.usage = usage
        self.raise_after_usage = raise_after_usage

    def __call__(self, messages, **kw):
        self.calls.append({"messages": messages, **kw})
        if kw.get("on_usage") is not None:
            kw["on_usage"](self.usage)
        if self.raise_after_usage is not None:
            raise self.raise_after_usage
        return self.reply, self.usage


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(partner, "partner_reply", fake)
    return fake


@pytest.fixture
def usage_log(monkeypatch):
    logged = []
    monkeypatch.setattr(
        turns,
        "log_ai_usage",
        lambda feature, usage, user_id: logged.append((feature, usage, user_id)),
    )
    return logged


def _trade(owner, **over):
    db = SessionLocal()
    try:
        row = Trade(user_id=owner, asset="NQ", direction="Long", result="Win", **over)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _screenshot(trade_id):
    db = SessionLocal()
    try:
        row = Screenshot(trade_id=trade_id, file_path="users/x/trades/y/final.png")
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _tickets(owner):
    db = SessionLocal()
    try:
        return (
            db.query(AIJob)
            .filter(AIJob.user_id == owner, AIJob.kind == turns.KIND)
            .order_by(AIJob.id)
            .all()
        )
    finally:
        db.close()


def _wire(result):
    return [
        {"idx": t.idx, "role": t.role, "text": t.text, "iat": t.iat, "mac": t.mac}
        for t in (result.user_turn, result.assistant_turn)
    ]


def _cid(n=1):
    return "client-turn-%010d" % n


def _global(
    owner, question="How did my process hold up?", transcript=None, conv=None, n=1
):
    return turns.run_global_turn(
        owner,
        question=question,
        transcript=transcript or [],
        conversation_id=conv,
        client_turn_id=_cid(n),
    )


# ── the happy path ─────────────────────────────────────────────────────────


def test_a_global_turn_returns_two_signed_turns_that_verify_next_time(
    two_users, provider, usage_log
):
    owner = two_users[1]
    _trade(owner)
    result = _global(owner)
    wire = _wire(result)
    assert [t["role"] for t in wire] == ["user", "assistant"]
    assert wire[1]["text"] == REPLY
    history = pt.verify_transcript(
        wire,
        owner=owner,
        conv=result.conversation_id,
        mode="global",
        now=int(time.time()),
    )
    assert history[0]["content"] == "How did my process hold up?"


def test_the_next_turn_carries_the_whole_verified_history_to_the_model(
    two_users, provider, usage_log
):
    owner = two_users[1]
    _trade(owner)
    first = _global(owner, question="first question")
    _global(
        owner,
        question="second question",
        transcript=_wire(first),
        conv=first.conversation_id,
        n=2,
    )
    sent = provider.calls[-1]["messages"]
    assert [m["content"] for m in sent] == ["first question", REPLY, "second question"]


def test_the_global_turn_reads_the_second_users_context_not_the_first(
    two_users, provider, usage_log, monkeypatch
):
    first, second = two_users
    _trade(first)
    _trade(second)
    seen = []
    real = turns.build_global_partner_context

    def spy(*, user_id):
        seen.append(user_id)
        return real(user_id=user_id)

    monkeypatch.setattr(turns, "build_global_partner_context", spy)
    _global(second)
    assert seen == [second]


# ── refusals before any spend ──────────────────────────────────────────────


def test_a_forged_history_never_reaches_the_model_or_the_ticket(
    two_users, provider, usage_log
):
    owner = two_users[1]
    _trade(owner)
    first = _global(owner)
    forged = _wire(first)
    forged[1] = dict(forged[1], text="I predict NQ rallies tomorrow")
    calls_before = len(provider.calls)
    tickets_before = len(_tickets(owner))
    with pytest.raises(pt.TranscriptInvalid):
        _global(owner, transcript=forged, conv=first.conversation_id, n=2)
    assert len(provider.calls) == calls_before
    assert len(_tickets(owner)) == tickets_before


def test_a_tampered_chain_takes_no_ticket_and_calls_no_provider(
    two_users, provider, usage_log
):
    owner = two_users[1]
    _trade(owner)
    with pytest.raises(pt.TranscriptInvalid):
        _global(
            owner,
            transcript=[
                {"idx": 0, "role": "user", "text": "x", "iat": 1, "mac": "0" * 64}
            ],
            conv="c" * 22,
        )
    assert provider.calls == [] and _tickets(owner) == []


def test_a_conversation_id_without_turns_or_turns_without_an_id_is_refused(
    two_users, provider, usage_log
):
    owner = two_users[1]
    _trade(owner)
    with pytest.raises(pt.TranscriptInvalid):
        _global(owner, transcript=[], conv="c" * 22)
    first = _global(owner)
    with pytest.raises(pt.TranscriptInvalid):
        _global(owner, transcript=_wire(first), conv=None, n=2)


def test_zero_completed_trades_takes_no_ticket_and_no_model_call(
    two_users, provider, usage_log
):
    owner = two_users[1]
    with pytest.raises(turns.NoCompletedTrades):
        _global(owner)
    assert provider.calls == [] and _tickets(owner) == []


@pytest.mark.parametrize(
    "question, problem",
    [
        ("", "required"),
        ("   ", "required"),
        ("x" * 2001, "too_long"),
        ("ok\x00", "invalid_characters"),
    ],
)
def test_an_invalid_question_is_refused_before_anything(
    two_users, provider, usage_log, question, problem
):
    owner = two_users[1]
    _trade(owner)
    with pytest.raises(turns.InvalidQuestion) as err:
        _global(owner, question=question)
    assert err.value.problem == problem
    assert provider.calls == [] and _tickets(owner) == []


@pytest.mark.parametrize(
    "client_turn_id", ["short", "has space " * 3, "x" * 65, None, 12345678901234567]
)
def test_an_invalid_client_turn_id_is_refused_before_anything(
    two_users, provider, usage_log, client_turn_id
):
    owner = two_users[1]
    _trade(owner)
    with pytest.raises(turns.InvalidQuestion):
        turns.run_global_turn(
            owner,
            question="q",
            transcript=[],
            conversation_id=None,
            client_turn_id=client_turn_id,
        )
    assert provider.calls == [] and _tickets(owner) == []


def test_the_limit_refuses_before_any_spend(
    two_users, provider, usage_log, monkeypatch
):
    owner = two_users[1]
    _trade(owner)
    monkeypatch.setattr(turns, "MAX_PARTNER_TURNS_PER_WINDOW", 1)
    _global(owner)
    with pytest.raises(turns.RateLimited):
        _global(owner, n=2)
    assert len(provider.calls) == 1


def test_a_full_conversation_is_refused_before_the_ticket(
    two_users, provider, usage_log, monkeypatch
):
    owner = two_users[1]
    _trade(owner)
    monkeypatch.setattr(pt, "MAX_TRANSCRIPT_TURNS", 2)
    first = _global(owner)
    with pytest.raises(turns.ConversationFull):
        _global(owner, transcript=_wire(first), conv=first.conversation_id, n=2)
    assert len(provider.calls) == 1 and len(_tickets(owner)) == 1


# ── duplicates: resolved before the provider is reachable ─────────────────


def test_a_double_submitted_first_question_reaches_the_provider_once(
    two_users, provider, usage_log
):
    """The first turn of a conversation has no conversation id yet — the server
    mints one per request. Keying the ticket on that fresh id made a
    double-clicked first question two different keys and two paid calls. The
    replay below is byte-identical to the first submit."""
    owner = two_users[1]
    _trade(owner)
    _global(owner)
    with pytest.raises(turns.DuplicateTurn):
        _global(owner)
    assert len(provider.calls) == 1
    assert len(_tickets(owner)) == 1


def test_a_double_submitted_later_question_reaches_the_provider_once(
    two_users, provider, usage_log
):
    owner = two_users[1]
    _trade(owner)
    first = _global(owner)
    _global(
        owner, question="next", transcript=_wire(first), conv=first.conversation_id, n=2
    )
    with pytest.raises(turns.DuplicateTurn):
        _global(
            owner,
            question="next",
            transcript=_wire(first),
            conv=first.conversation_id,
            n=2,
        )
    assert len(provider.calls) == 2


def test_one_client_turn_id_reused_at_two_positions_is_not_a_duplicate(
    two_users, provider, usage_log
):
    """The ticket key binds the position as well as the id. A browser that
    reuses one id across questions in the same conversation must not have its
    later question swallowed as a duplicate of the earlier one."""
    owner = two_users[1]
    _trade(owner)
    first = _global(owner, n=1)
    second = _global(
        owner, question="q2", transcript=_wire(first), conv=first.conversation_id, n=9
    )
    _global(
        owner,
        question="q3",
        transcript=_wire(first) + _wire(second),
        conv=first.conversation_id,
        n=9,
    )
    assert len(provider.calls) == 3


def test_a_new_question_with_a_new_client_turn_id_is_not_a_duplicate(
    two_users, provider, usage_log
):
    owner = two_users[1]
    _trade(owner)
    _global(owner, n=1)
    _global(owner, n=2)  # a genuinely new first question: a new id
    assert len(provider.calls) == 2


def test_the_duplicate_check_runs_before_partner_reply_is_reachable(
    two_users, usage_log, monkeypatch
):
    owner = two_users[1]
    _trade(owner)
    ok = FakeProvider()
    monkeypatch.setattr(partner, "partner_reply", ok)
    first = _global(owner, question="first")
    second = _global(
        owner,
        question="second",
        transcript=_wire(first),
        conv=first.conversation_id,
        n=2,
    )

    def must_not_run(*_a, **_k):
        raise AssertionError("the provider was reached for a duplicate turn")

    monkeypatch.setattr(partner, "partner_reply", must_not_run)
    # Replay the SAME second submit: same conversation, same position, same id.
    with pytest.raises(turns.DuplicateTurn):
        _global(
            owner,
            question="second",
            transcript=_wire(first),
            conv=first.conversation_id,
            n=2,
        )
    assert second.assistant_turn.text == REPLY


def test_two_concurrent_identical_submits_reach_the_provider_exactly_once(
    two_users, usage_log, monkeypatch
):
    owner = two_users[1]
    _trade(owner)
    calls = []

    def slow_provider(messages, **kw):
        calls.append(1)
        time.sleep(0.3)
        return REPLY, None

    monkeypatch.setattr(partner, "partner_reply", slow_provider)
    first = _global(owner)
    calls.clear()
    barrier = threading.Barrier(2, timeout=5)
    outcomes = []

    def submit():
        barrier.wait()
        try:
            _global(
                owner,
                question="again",
                transcript=_wire(first),
                conv=first.conversation_id,
                n=7,
            )
            outcomes.append("answered")
        except turns.DuplicateTurn:
            outcomes.append("duplicate")

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(outcomes) == ["answered", "duplicate"]
    assert len(calls) == 1


# ── billing ───────────────────────────────────────────────────────────────


def test_usage_is_logged_once_even_when_the_scope_guard_replaces_the_reply(
    two_users, usage_log, monkeypatch
):
    owner = two_users[1]
    _trade(owner)
    monkeypatch.setattr(
        partner, "converse", lambda *a, **k: ("You should buy NQ now.", "USAGE")
    )
    result = _global(owner)
    assert result.assistant_turn.text == partner._REDIRECT_MESSAGE
    assert usage_log == [("AI Partner", "USAGE", owner)]


def test_the_server_signs_the_text_it_returned_after_the_scope_guard(
    two_users, usage_log, monkeypatch
):
    owner = two_users[1]
    _trade(owner)
    monkeypatch.setattr(
        partner, "converse", lambda *a, **k: ("Price will rally tomorrow.", None)
    )
    result = _global(owner)
    assert result.assistant_turn.text == partner._REDIRECT_MESSAGE
    assert "rally" not in result.assistant_turn.text
    pt.verify_transcript(
        _wire(result),
        owner=owner,
        conv=result.conversation_id,
        mode="global",
        now=int(time.time()),
    )


def test_usage_is_logged_when_the_model_refuses_after_billing(
    two_users, usage_log, monkeypatch
):
    owner = two_users[1]
    _trade(owner)
    monkeypatch.setattr(
        partner,
        "partner_reply",
        FakeProvider(raise_after_usage=partner.PartnerError("declined")),
    )
    with pytest.raises(partner.PartnerError):
        _global(owner)
    assert usage_log == [("AI Partner", "USAGE", owner)]
    assert [t.status for t in _tickets(owner)] == ["failed"]


def test_a_failed_cost_write_never_costs_the_trader_the_answer(
    two_users, provider, monkeypatch
):
    owner = two_users[1]
    _trade(owner)

    def broken(*_a, **_k):
        raise RuntimeError("cost table down: postgresql://secret@host")

    monkeypatch.setattr(turns, "log_ai_usage", broken)
    result = _global(owner)
    assert result.assistant_turn.text == REPLY


def test_the_ticket_is_failed_with_a_fixed_code_when_the_model_call_raises(
    two_users, usage_log, monkeypatch
):
    owner = two_users[1]
    _trade(owner)
    monkeypatch.setattr(
        partner,
        "partner_reply",
        FakeProvider(
            raise_after_usage=RuntimeError("driver: postgresql://secret@host")
        ),
    )
    with pytest.raises(RuntimeError):
        _global(owner)
    ticket = _tickets(owner)[0]
    assert ticket.status == "failed"
    assert ticket.error == turns.RESULT_ERROR
    assert "secret" not in (ticket.error or "")


def test_after_a_turn_the_ticket_row_holds_no_question_reply_or_transcript_text(
    two_users, provider, usage_log
):
    owner = two_users[1]
    _trade(owner)
    first = _global(owner, question="ZZQUESTION one")
    _global(
        owner,
        question="ZZQUESTION two",
        transcript=_wire(first),
        conv=first.conversation_id,
        n=2,
    )
    for ticket in _tickets(owner):
        assert ticket.payload == "{}"
        assert ticket.status == "succeeded"
        assert ticket.result_ref == turns.RESULT_OK
        assert len(ticket.idempotency_key) == 64
        row = " ".join(str(getattr(ticket, c.name)) for c in AIJob.__table__.columns)
        assert (
            "ZZQUESTION" not in row
            and REPLY not in row
            and first.conversation_id not in row
        )


def test_demo_mode_returns_the_canned_reply_and_bills_nothing(
    two_users, usage_log, monkeypatch
):
    from src.tradelens.services import ai_client

    owner = two_users[1]
    _trade(owner)
    monkeypatch.setattr(ai_client.settings, "demo_mode", True)
    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", lambda **k: "", raising=False
    )
    result = _global(owner)
    assert result.assistant_turn.text == partner._DEMO_PARTNER_REPLY
    (_feature, usage, _owner) = usage_log[0]
    assert usage.estimated_cost_usd == 0.0


# ── the per-trade mode ────────────────────────────────────────────────────


def _trade_turn(
    owner, trade_id, include_screenshot=False, transcript=None, conv=None, n=1
):
    return turns.run_trade_turn(
        owner,
        trade_id,
        question="Was my stop placement consistent with my rules?",
        transcript=transcript or [],
        conversation_id=conv,
        client_turn_id=_cid(n),
        include_screenshot=include_screenshot,
    )


def test_another_owners_trade_is_not_found_before_any_ticket(
    two_users, provider, usage_log
):
    first, second = two_users
    theirs = _trade(first)
    with pytest.raises(turns.TradeNotFound):
        _trade_turn(second, theirs)
    with pytest.raises(turns.TradeNotFound):
        _trade_turn(second, 999_999)
    assert provider.calls == [] and _tickets(second) == []


def test_the_trade_screenshot_is_read_through_the_owner_scoped_storage_path(
    two_users, provider, usage_log, monkeypatch
):
    owner = two_users[1]
    trade_id = _trade(owner)
    older = _screenshot(trade_id)
    newer = _screenshot(trade_id)
    calls = []

    def belongs(user_id, screenshot_id, tid):
        calls.append(("belongs", user_id, screenshot_id, tid))
        return True

    def read(user_id, screenshot_id):
        calls.append(("read", user_id, screenshot_id))
        return PNG

    monkeypatch.setattr(turns.storage, "screenshot_belongs_to_trade", belongs)
    monkeypatch.setattr(turns.storage, "read_owned_final_object", read)
    result = _trade_turn(owner, trade_id, include_screenshot=True)
    assert result.screenshot_attached is True
    assert calls == [("belongs", owner, newer, trade_id), ("read", owner, newer)]
    assert older != newer
    sent = provider.calls[0]["image_png_b64"]
    assert base64.b64decode(sent) == PNG


def test_a_screenshot_that_is_not_this_trades_is_never_read_or_attached(
    two_users, provider, usage_log, monkeypatch
):
    """`screenshot_belongs_to_trade` keeps another of the owner's OWN trades'
    images out of this trade's conversation. The read is owner-scoped either
    way, so without this test the trade binding could be deleted and every
    other screenshot assertion would still pass (E6 review, mutant M8)."""
    owner = two_users[1]
    trade_id = _trade(owner)
    _screenshot(trade_id)
    reads = []

    def read(*args):
        reads.append(args)
        return PNG

    monkeypatch.setattr(turns.storage, "screenshot_belongs_to_trade", lambda *a: False)
    monkeypatch.setattr(turns.storage, "read_owned_final_object", read)
    result = _trade_turn(owner, trade_id, include_screenshot=True)
    assert result.screenshot_attached is False
    assert reads == []
    assert provider.calls[-1]["image_png_b64"] is None


def test_no_screenshot_or_no_flag_means_nothing_attached(
    two_users, provider, usage_log, monkeypatch
):
    owner = two_users[1]
    trade_id = _trade(owner)
    assert (
        _trade_turn(owner, trade_id, include_screenshot=True).screenshot_attached
        is False
    )
    _screenshot(trade_id)
    monkeypatch.setattr(turns.storage, "screenshot_belongs_to_trade", lambda *a: True)
    monkeypatch.setattr(turns.storage, "read_owned_final_object", lambda *a: PNG)
    assert (
        _trade_turn(owner, trade_id, include_screenshot=False, n=2).screenshot_attached
        is False
    )
    assert provider.calls[-1]["image_png_b64"] is None


@pytest.mark.parametrize("flag", ["false", "0", "true", 1, [1], {"on": True}])
def test_only_a_real_true_attaches_the_screenshot(
    two_users, provider, usage_log, monkeypatch, flag
):
    """`include_screenshot is True`, not truthiness: the relay forwards the
    browser's JSON, and a stringified "false" is the classic way a flag turns
    itself on. Mutation testing showed only `False` was pinned."""
    owner = two_users[1]
    trade_id = _trade(owner)
    _screenshot(trade_id)
    monkeypatch.setattr(turns.storage, "screenshot_belongs_to_trade", lambda *a: True)
    monkeypatch.setattr(turns.storage, "read_owned_final_object", lambda *a: PNG)
    assert (
        _trade_turn(owner, trade_id, include_screenshot=flag).screenshot_attached
        is False
    )
    assert provider.calls[-1]["image_png_b64"] is None


def test_the_per_trade_mode_cannot_verify_a_global_transcript(
    two_users, provider, usage_log
):
    owner = two_users[1]
    trade_id = _trade(owner)
    global_turn = _global(owner)
    with pytest.raises(pt.TranscriptInvalid):
        _trade_turn(
            owner,
            trade_id,
            transcript=_wire(global_turn),
            conv=global_turn.conversation_id,
            n=2,
        )


def test_a_conversation_about_one_trade_cannot_continue_on_another(
    two_users, provider, usage_log
):
    owner = two_users[1]
    trade_a = _trade(owner)
    trade_b = _trade(owner)
    first = _trade_turn(owner, trade_a)
    with pytest.raises(pt.TranscriptInvalid):
        _trade_turn(
            owner, trade_b, transcript=_wire(first), conv=first.conversation_id, n=2
        )


def test_the_per_trade_turn_is_grounded_in_the_trade_and_uses_the_preamble(
    two_users, provider, usage_log
):
    owner = two_users[1]
    trade_id = _trade(owner, notes="ZZ-own-trade-note")
    _trade_turn(owner, trade_id)
    call = provider.calls[0]
    assert call["per_trade_qa"] is True
    assert "ZZ-own-trade-note" in call["trade_context"]
    assert call["reflective_context"] == ""
