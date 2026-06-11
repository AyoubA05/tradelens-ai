"""
Tests for openai_client.py — all OpenAI calls are mocked; no network traffic, no cost.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.tradelens.services.openai_client import (
    Usage,
    _estimate_cost,
    chat,
    load_prompt,
    vision,
)


# ---------------------------------------------------------------------------
# _estimate_cost — pure function, no mocks needed
# ---------------------------------------------------------------------------

def test_estimate_cost_gpt4o_mini():
    cost = _estimate_cost("gpt-4o-mini", 1000, 500)
    expected = (1000 * 0.000150 + 500 * 0.000600) / 1000
    assert abs(cost - expected) < 1e-9


def test_estimate_cost_gpt4o():
    cost = _estimate_cost("gpt-4o", 2000, 1000)
    expected = (2000 * 0.005 + 1000 * 0.015) / 1000
    assert abs(cost - expected) < 1e-9


def test_estimate_cost_unknown_model_returns_zero():
    assert _estimate_cost("unknown-model", 500, 500) == 0.0


# ---------------------------------------------------------------------------
# load_prompt — uses real prompts/ directory
# ---------------------------------------------------------------------------

def test_load_prompt_returns_stripped_text():
    text = load_prompt("example_v1")
    assert "prompt loader OK" in text


def test_load_prompt_raises_for_missing_file():
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_prompt_v99")


# ---------------------------------------------------------------------------
# chat() — mocked OpenAI client
# ---------------------------------------------------------------------------

def _mock_completion(content: str, tokens_in: int = 10, tokens_out: int = 5) -> MagicMock:
    resp = MagicMock()
    resp.choices[0].message.content = content
    resp.usage.prompt_tokens = tokens_in
    resp.usage.completion_tokens = tokens_out
    return resp


def test_chat_returns_content_and_usage():
    mock_resp = _mock_completion("hello world", tokens_in=10, tokens_out=5)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("src.tradelens.services.openai_client._get_client", return_value=mock_client):
        content, usage = chat("say hi")

    assert content == "hello world"
    assert usage.tokens_in == 10
    assert usage.tokens_out == 5
    assert usage.total_tokens == 15
    assert isinstance(usage.estimated_cost_usd, float)
    assert usage.latency_s >= 0


def test_chat_uses_default_text_model():
    mock_resp = _mock_completion("ok")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("src.tradelens.services.openai_client._get_client", return_value=mock_client):
        _, usage = chat("ping")

    assert usage.model == "gpt-4o-mini"


def test_chat_passes_system_message():
    mock_resp = _mock_completion("ok")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("src.tradelens.services.openai_client._get_client", return_value=mock_client):
        chat("hello", system_message="You are a test assistant.")

    call_kwargs = mock_client.chat.completions.create.call_args[1]
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_chat_passes_response_format():
    mock_resp = _mock_completion('{"result": "ok"}')
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("src.tradelens.services.openai_client._get_client", return_value=mock_client):
        chat("return json", response_format={"type": "json_object"})

    call_kwargs = mock_client.chat.completions.create.call_args[1]
    assert call_kwargs["response_format"] == {"type": "json_object"}


# ---------------------------------------------------------------------------
# vision() — mocked client + mocked encode_image
# ---------------------------------------------------------------------------

def test_vision_returns_content_and_usage(tmp_path):
    # Create a minimal 1x1 JPEG so PIL doesn't error if encode_image runs
    dummy_img = tmp_path / "chart.jpg"
    dummy_img.write_bytes(b"")  # won't be read — encode_image is mocked

    mock_resp = _mock_completion('{"bias": "bullish"}', tokens_in=200, tokens_out=80)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("src.tradelens.services.openai_client._get_client", return_value=mock_client), \
         patch("src.tradelens.services.openai_client.encode_image", return_value="base64data"):
        content, usage = vision(str(dummy_img), "Analyze this chart.")

    assert content == '{"bias": "bullish"}'
    assert usage.tokens_in == 200
    assert usage.tokens_out == 80
    assert usage.model == "gpt-4o"


def test_vision_uses_default_vision_model(tmp_path):
    dummy_img = tmp_path / "chart.jpg"
    dummy_img.write_bytes(b"")

    mock_resp = _mock_completion("{}")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("src.tradelens.services.openai_client._get_client", return_value=mock_client), \
         patch("src.tradelens.services.openai_client.encode_image", return_value="x"):
        _, usage = vision(str(dummy_img), "analyze")

    assert usage.model == "gpt-4o"


# ---------------------------------------------------------------------------
# Usage.__str__
# ---------------------------------------------------------------------------

def test_usage_str_format():
    u = Usage(
        model="gpt-4o-mini",
        tokens_in=100, tokens_out=50,
        total_tokens=150,
        estimated_cost_usd=0.000045,
        latency_s=1.23,
    )
    s = str(u)
    assert "gpt-4o-mini" in s
    assert "0.00005" in s or "4.5e" in s  # float formatting varies
