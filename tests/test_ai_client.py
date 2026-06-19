"""
Tests for ai_client.py — the single Anthropic wrapper.

No network traffic: every test either runs in DEMO_MODE or mocks _get_client.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.tradelens.services import ai_client
from src.tradelens.services.ai_client import (
    AIUnavailable,
    Usage,
    _estimate_cost,
    chat,
    load_prompt,
    vision,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_message(
    text: str = "",
    *,
    stop_reason: str = "end_turn",
    in_tok: int = 10,
    out_tok: int = 5,
    cache_read: int = 0,
    thinking: str | None = None,
    model: str = "claude-fable-5",
) -> MagicMock:
    """Build a fake Anthropic Message with text/thinking content blocks."""
    resp = MagicMock()
    blocks = []
    if thinking is not None:
        tb = MagicMock()
        tb.type = "thinking"
        tb.thinking = thinking
        blocks.append(tb)
    txt = MagicMock()
    txt.type = "text"
    txt.text = text
    blocks.append(txt)
    resp.content = blocks
    resp.stop_reason = stop_reason
    resp.model = model
    resp.usage.input_tokens = in_tok
    resp.usage.output_tokens = out_tok
    resp.usage.cache_read_input_tokens = cache_read
    return resp


def _client_returning(*responses) -> MagicMock:
    """A mock Anthropic client whose messages.create yields the given responses in order."""
    client = MagicMock()
    client.messages.create.side_effect = list(responses)
    return client


@pytest.fixture(autouse=True)
def _live_mode(monkeypatch):
    """Default every test to live (non-demo) mode with a key present.

    Also neutralise correction injection so prompt assertions stay hermetic
    regardless of DB state (tests that want corrections re-patch this).
    """
    monkeypatch.setattr(ai_client.settings, "demo_mode", False)
    monkeypatch.setattr(ai_client.settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", lambda **k: "", raising=False
    )


# ---------------------------------------------------------------------------
# _estimate_cost — pure function
# ---------------------------------------------------------------------------


def test_estimate_cost_fable5():
    # $10/M input + $50/M output
    assert _estimate_cost("claude-fable-5", 1_000_000, 1_000_000) == pytest.approx(60.0)


def test_estimate_cost_haiku():
    assert _estimate_cost("claude-haiku-4-5", 1_000_000, 1_000_000) == pytest.approx(
        6.0
    )


def test_estimate_cost_cache_read_billed_at_tenth():
    # cache reads ~0.1x input price → ~$1/M on fable-5
    assert _estimate_cost(
        "claude-fable-5", 0, 0, cache_read_tokens=1_000_000
    ) == pytest.approx(1.0)


def test_estimate_cost_unknown_model_returns_zero():
    assert _estimate_cost("unknown-model", 500, 500) == 0.0


# ---------------------------------------------------------------------------
# load_prompt
# ---------------------------------------------------------------------------


def test_load_prompt_returns_stripped_text():
    assert "prompt loader OK" in load_prompt("example_v1")


def test_load_prompt_raises_for_missing_file():
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_prompt_v99")


# ---------------------------------------------------------------------------
# DEMO_MODE — no client is ever created
# ---------------------------------------------------------------------------


def test_chat_demo_mode_returns_demo_response(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "demo_mode", True)

    def _boom():
        raise AssertionError("DEMO_MODE must not create an API client")

    monkeypatch.setattr(ai_client, "_get_client", _boom)

    content, usage = chat("hi", demo_response="DEMO OK")
    assert content == "DEMO OK"
    assert usage.estimated_cost_usd == 0.0
    assert usage.tokens_in == 0


def test_vision_demo_mode_returns_demo_response(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_client.settings, "demo_mode", True)
    monkeypatch.setattr(
        ai_client,
        "_get_client",
        lambda: (_ for _ in ()).throw(AssertionError("no client")),
    )
    img = tmp_path / "c.jpg"
    img.write_bytes(b"x")
    content, usage = vision(str(img), "analyze", demo_response='{"ok": true}')
    assert content == '{"ok": true}'
    assert usage.estimated_cost_usd == 0.0


# ---------------------------------------------------------------------------
# chat() — live path with mocked client
# ---------------------------------------------------------------------------


def test_chat_returns_content_and_usage(monkeypatch):
    client = _client_returning(_fake_message("hello world", in_tok=10, out_tok=5))
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    content, usage = chat("say hi")
    assert content == "hello world"
    assert usage.tokens_in == 10
    assert usage.tokens_out == 5
    assert usage.total_tokens == 15
    assert isinstance(usage.estimated_cost_usd, float)
    assert usage.latency_s >= 0


def test_chat_defaults_to_primary_model(monkeypatch):
    client = _client_returning(_fake_message("ok"))
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    chat("ping")
    assert client.messages.create.call_args[1]["model"] == "claude-fable-5"


def test_chat_routes_grading_model_when_requested(monkeypatch):
    client = _client_returning(_fake_message("ok", model="claude-haiku-4-5"))
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    chat("grade this", model=ai_client.settings.model_grading)
    assert client.messages.create.call_args[1]["model"] == "claude-haiku-4-5"


def test_chat_passes_system_message(monkeypatch):
    client = _client_returning(_fake_message("ok"))
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    chat("hello", system_message="You are a test assistant.")
    assert client.messages.create.call_args[1]["system"] == "You are a test assistant."


def test_chat_cache_system_sets_cache_control(monkeypatch):
    client = _client_returning(_fake_message("ok"))
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    chat("hello", system_message="STRATEGY PROFILE", cache_system=True)
    system = client.messages.create.call_args[1]["system"]
    assert isinstance(system, list)
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_chat_uses_adaptive_thinking_and_effort(monkeypatch):
    client = _client_returning(_fake_message("ok"))
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    chat("hello", effort="high")
    kwargs = client.messages.create.call_args[1]
    assert kwargs["thinking"]["type"] == "adaptive"
    assert kwargs["output_config"]["effort"] == "high"


def test_chat_captures_thinking_summary(monkeypatch):
    client = _client_returning(_fake_message("answer", thinking="I reasoned about X"))
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    _, usage = chat("hello")
    assert usage.thinking_summary == "I reasoned about X"


def test_chat_injects_few_shot_block(monkeypatch):
    client = _client_returning(_fake_message("ok"))
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    chat("hello", system_message="BASE", few_shot="PAST CORRECTIONS: foo->bar")
    system = client.messages.create.call_args[1]["system"]
    blob = system if isinstance(system, str) else system[0]["text"]
    assert "PAST CORRECTIONS: foo->bar" in blob


# ---------------------------------------------------------------------------
# Correction memory — auto-injection of <past_corrections> into every call
# ---------------------------------------------------------------------------


def test_chat_injects_past_corrections_block(monkeypatch):
    monkeypatch.setattr(
        ai_client,
        "build_correction_few_shot",
        lambda **k: "<past_corrections>\nbias: prefer 'bearish'\n</past_corrections>",
        raising=False,
    )
    client = _client_returning(_fake_message("ok"))
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    chat("hello", system_message="BASE")
    system = client.messages.create.call_args[1]["system"]
    blob = system if isinstance(system, str) else system[0]["text"]
    assert "<past_corrections>" in blob
    assert "bias: prefer 'bearish'" in blob
    assert "BASE" in blob


def test_chat_without_corrections_keeps_system_exact(monkeypatch):
    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", lambda **k: "", raising=False
    )
    client = _client_returning(_fake_message("ok"))
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    chat("hello", system_message="BASE ONLY")
    assert client.messages.create.call_args[1]["system"] == "BASE ONLY"


def test_vision_injects_past_corrections_block(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ai_client,
        "build_correction_few_shot",
        lambda **k: "<past_corrections>\nX\n</past_corrections>",
        raising=False,
    )
    img = tmp_path / "c.jpg"
    img.write_bytes(b"x")
    client = _client_returning(_fake_message("{}"))
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)
    monkeypatch.setattr(ai_client, "encode_image", lambda *a, **k: "B64")

    vision(str(img), "analyze", system_message="VBASE")
    system = client.messages.create.call_args[1]["system"]
    blob = system if isinstance(system, str) else system[0]["text"]
    assert "<past_corrections>" in blob
    assert "VBASE" in blob


def test_demo_mode_still_builds_corrections(monkeypatch):
    """Injection is deterministic (no API) — the builder runs even in DEMO_MODE."""
    monkeypatch.setattr(ai_client.settings, "demo_mode", True)
    called = {}

    def fake_build(**k):
        called["ran"] = True
        return ""

    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", fake_build, raising=False
    )

    def _boom():
        raise AssertionError("DEMO_MODE must not create an API client")

    monkeypatch.setattr(ai_client, "_get_client", _boom)

    content, _ = chat("hi", demo_response="DEMO")
    assert content == "DEMO"
    assert called.get("ran") is True


# ---------------------------------------------------------------------------
# Refusal handling — retry once with fallback, then AIUnavailable
# ---------------------------------------------------------------------------


def test_refusal_retries_with_fallback_model(monkeypatch):
    refused = _fake_message("", stop_reason="refusal")
    rescued = _fake_message(
        "recovered", stop_reason="end_turn", model="claude-opus-4-8"
    )
    client = _client_returning(refused, rescued)
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    content, usage = chat("borderline request")
    assert content == "recovered"
    # second call used the fallback model
    second_call_model = client.messages.create.call_args_list[1][1]["model"]
    assert second_call_model == "claude-opus-4-8"


def test_refusal_then_refusal_returns_ai_unavailable(monkeypatch):
    refused = _fake_message("", stop_reason="refusal")
    client = _client_returning(
        refused, _fake_message("", stop_reason="refusal", model="claude-opus-4-8")
    )
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    result, usage = chat("disallowed")
    assert isinstance(result, AIUnavailable)
    assert usage.refused is True


def test_missing_key_returns_ai_unavailable(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "anthropic_api_key", "")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def _boom():
        raise AssertionError("must not create a client without a key")

    monkeypatch.setattr(ai_client, "_get_client", _boom)
    result, _ = chat("hello")
    assert isinstance(result, AIUnavailable)


# ---------------------------------------------------------------------------
# vision() — live path
# ---------------------------------------------------------------------------


def test_vision_returns_content_and_usage(monkeypatch, tmp_path):
    img = tmp_path / "chart.jpg"
    img.write_bytes(b"x")
    client = _client_returning(
        _fake_message('{"bias": "bullish"}', in_tok=200, out_tok=80)
    )
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)
    monkeypatch.setattr(ai_client, "encode_image", lambda *a, **k: "base64data")

    content, usage = vision(str(img), "Analyze this chart.")
    assert content == '{"bias": "bullish"}'
    assert usage.tokens_in == 200
    assert usage.tokens_out == 80


def test_vision_builds_image_block(monkeypatch, tmp_path):
    img = tmp_path / "chart.jpg"
    img.write_bytes(b"x")
    client = _client_returning(_fake_message("{}"))
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)
    monkeypatch.setattr(ai_client, "encode_image", lambda *a, **k: "B64")

    vision(str(img), "analyze")
    content = client.messages.create.call_args[1]["messages"][0]["content"]
    image_blocks = [b for b in content if b.get("type") == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0]["source"]["data"] == "B64"


# ---------------------------------------------------------------------------
# Usage.__str__
# ---------------------------------------------------------------------------


def test_usage_str_format():
    u = Usage(
        model="claude-fable-5",
        tokens_in=100,
        tokens_out=50,
        total_tokens=150,
        estimated_cost_usd=0.0015,
        latency_s=1.23,
    )
    s = str(u)
    assert "claude-fable-5" in s
