"""
Tests for partner.py — the multi-turn AI trading-partner service.

The single AI call is mocked (no network/cost); the DEMO_MODE test exercises the
real ai_client short-circuit. The scope guard is verified both as a post-check
and as always-present text in the outbound system prompt.
"""

from unittest.mock import MagicMock

import pytest

from src.tradelens.services import ai_client


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _fake_message(text: str = "ok") -> MagicMock:
    resp = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp.content = [block]
    resp.stop_reason = "end_turn"
    resp.model = "claude-fable-5"
    resp.usage.input_tokens = 1500
    resp.usage.output_tokens = 400
    resp.usage.cache_read_input_tokens = 0
    return resp


@pytest.fixture()
def mock_client(monkeypatch):
    """Live mode + key; capture outbound payload; corrections neutralised (hermetic)."""
    monkeypatch.setattr(ai_client.settings, "demo_mode", False)
    monkeypatch.setattr(ai_client.settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", lambda **k: "", raising=False
    )
    client = MagicMock()
    client.messages.create.return_value = _fake_message("A clean order-block retest.")
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)
    return client


def _outbound_system(client) -> str:
    system = client.messages.create.call_args[1]["system"]
    return system if isinstance(system, str) else system[0]["text"]


# ---------------------------------------------------------------------------
# build_partner_system — scope guard always present
# ---------------------------------------------------------------------------


def test_build_partner_system_always_contains_scope_guard():
    from src.tradelens.services.partner import _SCOPE_GUARD, build_partner_system

    assert _SCOPE_GUARD in build_partner_system()
    assert _SCOPE_GUARD in build_partner_system({"name": "ICT"})
    assert _SCOPE_GUARD in build_partner_system(
        {"name": "ICT"}, running_summary="prior"
    )


def test_build_partner_system_includes_strategy_profile():
    from src.tradelens.services.partner import build_partner_system

    sysmsg = build_partner_system({"name": "ICT Precision", "entry_rules": "OB retest"})
    assert "ICT Precision" in sysmsg
    assert "OB retest" in sysmsg


# ---------------------------------------------------------------------------
# build_trade_context — must speak SMC/ICT precisely
# ---------------------------------------------------------------------------


def test_build_trade_context_uses_smc_vocabulary():
    from src.tradelens.services.partner import build_trade_context

    trade = {
        "asset": "NQ",
        "result": "Win",
        "pnl": 250.0,
        "killzone": "ny_am",
        "htf_bias": "bullish",
        "confirmation_model": "BOS",
        "setup_type": "OB",
        "fvg_used": 1,
        "order_block_used": 1,
        "followed_rules": 1,
    }
    analysis = {"detected_setup": "Order Block", "trade_quality": 8}

    ctx = build_trade_context(trade, analysis)
    for token in (
        "killzone",
        "ny_am",
        "htf_bias",
        "bullish",
        "confirmation_model",
        "order_block_used",
        "detected_setup",
    ):
        assert token in ctx, f"missing {token}"


# ---------------------------------------------------------------------------
# trim_history — last 10 turns + running summary
# ---------------------------------------------------------------------------


def test_trim_history_keeps_last_10_and_summarizes():
    from src.tradelens.services.partner import trim_history

    msgs = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
        for i in range(14)
    ]
    trimmed, summary = trim_history(msgs)
    assert len(trimmed) == 10
    assert trimmed[0]["content"] == "m4"  # last 10 → m4..m13
    assert summary is not None
    assert "m0" in summary  # earliest dropped message is summarized


def test_trim_history_under_limit_no_summary():
    from src.tradelens.services.partner import trim_history

    msgs = [{"role": "user", "content": f"m{i}"} for i in range(6)]
    trimmed, summary = trim_history(msgs)
    assert len(trimmed) == 6
    assert summary is None


# ---------------------------------------------------------------------------
# scope-guard post-check
# ---------------------------------------------------------------------------


def test_apply_scope_guard_fires_on_signal_seeking():
    from src.tradelens.services.partner import _REDIRECT_MESSAGE, _apply_scope_guard

    assert _apply_scope_guard("Sure — you should buy NQ tomorrow at the open.") == (
        _REDIRECT_MESSAGE
    )


def test_apply_scope_guard_passes_normal_review():
    from src.tradelens.services.partner import _apply_scope_guard

    review = "Your entry off the order block after the liquidity sweep was clean."
    assert _apply_scope_guard(review) == review


# ---------------------------------------------------------------------------
# _to_api_messages — image block + leading-assistant safety
# ---------------------------------------------------------------------------


def test_to_api_messages_attaches_image_to_first_user_turn():
    from src.tradelens.services.partner import _to_api_messages

    api = _to_api_messages(
        [{"role": "user", "content": "review this"}], image_b64="B64"
    )
    first = api[0]["content"]
    assert first[0]["type"] == "image"
    assert first[0]["source"]["data"] == "B64"
    assert first[1]["text"] == "review this"


def test_to_api_messages_drops_leading_assistant():
    from src.tradelens.services.partner import _to_api_messages

    api = _to_api_messages(
        [{"role": "assistant", "content": "a"}, {"role": "user", "content": "u"}]
    )
    assert api[0]["role"] == "user"


# ---------------------------------------------------------------------------
# partner_reply — integration via mocked client
# ---------------------------------------------------------------------------


def test_partner_reply_outbound_system_always_has_scope_guard(mock_client):
    from src.tradelens.services.partner import _SCOPE_GUARD, partner_reply

    # vary trade/strategy/history — the guard must appear every time
    partner_reply(
        [{"role": "user", "content": "hi"}],
        trade_context="COMPLETED TRADE: NQ",
        strategy_profile={"name": "ICT"},
    )
    assert _SCOPE_GUARD in _outbound_system(mock_client)

    partner_reply([{"role": "user", "content": "and again?"}])
    assert _SCOPE_GUARD in _outbound_system(mock_client)


def test_partner_reply_includes_vision_block_when_image(mock_client):
    from src.tradelens.services.partner import partner_reply

    partner_reply([{"role": "user", "content": "review"}], image_b64="B64DATA")
    out_messages = mock_client.messages.create.call_args[1]["messages"]
    image_blocks = [
        b
        for b in out_messages[0]["content"]
        if isinstance(b, dict) and b.get("type") == "image"
    ]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["data"] == "B64DATA"


def test_partner_reply_scope_guard_post_check_fires(monkeypatch):
    from src.tradelens.services.partner import _REDIRECT_MESSAGE, partner_reply

    monkeypatch.setattr(ai_client.settings, "demo_mode", False)
    monkeypatch.setattr(ai_client.settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", lambda **k: "", raising=False
    )
    client = MagicMock()
    client.messages.create.return_value = _fake_message(
        "Based on momentum, you should buy NQ tomorrow at the open."
    )
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    reply, _usage = partner_reply([{"role": "user", "content": "what next?"}])
    assert reply == _REDIRECT_MESSAGE


def test_partner_reply_demo_mode_returns_canned(monkeypatch):
    import src.tradelens.services.ai_client as ai_client_mod
    from src.tradelens.services.partner import _DEMO_PARTNER_REPLY, partner_reply

    monkeypatch.setattr(ai_client_mod.settings, "demo_mode", True)
    monkeypatch.setattr(
        ai_client_mod, "build_correction_few_shot", lambda **k: "", raising=False
    )

    reply, usage = partner_reply([{"role": "user", "content": "review my trade"}])
    assert reply == _DEMO_PARTNER_REPLY
    assert usage.estimated_cost_usd == 0.0


def test_partner_reply_ai_unavailable_raises(monkeypatch):
    from src.tradelens.services.ai_client import AIUnavailable
    from src.tradelens.services.partner import PartnerError, partner_reply

    monkeypatch.setattr(ai_client.settings, "demo_mode", False)
    monkeypatch.setattr(ai_client.settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", lambda **k: "", raising=False
    )
    monkeypatch.setattr(
        "src.tradelens.services.partner.converse",
        lambda *a, **k: (AIUnavailable("AI declined"), _fake_usage()),
    )
    with pytest.raises(PartnerError, match="AI declined"):
        partner_reply([{"role": "user", "content": "hi"}])


def _fake_usage():
    from src.tradelens.services.ai_client import Usage

    return Usage("claude-fable-5", 0, 0, 0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Item 9 — per-trade Q&A grounded in the SAVED AI observations.
# ---------------------------------------------------------------------------


def test_per_trade_qa_system_prompt_wording(monkeypatch):
    from src.tradelens.services import partner

    monkeypatch.setattr(partner, "load_prompt", lambda name: "BASE")
    system = partner.build_partner_system(per_trade_qa=True)
    assert (
        "You are reviewing a specific completed trade from the trader's journal."
        in system
    )
    assert (
        "Answer their question based only on this trade's data and your original "
        "observations." in system
    )
    assert "Do not give live trading signals. Reflection and analysis only." in system
    # The always-on scope guard stays too.
    assert "STRICT SCOPE" in system


def test_per_trade_qa_off_by_default(monkeypatch):
    from src.tradelens.services import partner

    monkeypatch.setattr(partner, "load_prompt", lambda name: "BASE")
    assert "specific completed trade" not in partner.build_partner_system()


def test_trade_context_includes_saved_observations_and_process_notes():
    from types import SimpleNamespace

    from src.tradelens.services.partner import build_trade_context

    trade = SimpleNamespace(
        asset="MNQ",
        result="Win",
        trade_process_notes="Moved to BE after the 2nd IFVG break.",
    )
    analysis = SimpleNamespace(
        bias="bullish",
        detected_setup=None,
        trade_quality=7,
        matched_strategy=None,
        mistakes_json='["Late entry"]',
        missed_opps_json="[]",
        raw_response_json=(
            '{"notes_to_user": "Entry aligned with the sweep.", '
            '"structure": "downtrend", '
            '"possible_mistakes": ["Late entry"], '
            '"missed_opportunities": ["Earlier FVG"]}'
        ),
    )
    ctx = build_trade_context(trade, analysis)
    assert "Moved to BE after the 2nd IFVG break." in ctx
    assert "Entry aligned with the sweep." in ctx  # saved observation text
    assert "ORIGINAL AI OBSERVATIONS" in ctx
    assert "downtrend" in ctx


def test_trade_context_tolerates_junk_raw_json():
    from types import SimpleNamespace

    from src.tradelens.services.partner import build_trade_context

    analysis = SimpleNamespace(raw_response_json="not json")
    ctx = build_trade_context(SimpleNamespace(asset="NQ"), analysis)
    assert "NQ" in ctx  # never raises


def test_ask_ai_panel_has_coach_notes_and_qa_input():
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "tradelens"
        / "ui"
        / "components"
        / "ai_trade_chat.py"
    ).read_text(encoding="utf-8")
    assert "AI Coach Notes" in src
    assert "Ask the AI about this trade…" in src
    assert "per_trade_qa=True" in src
    assert "get_analysis_for_trade" in src  # saved observations feed the context
