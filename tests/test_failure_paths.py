"""
Failure-path sweep: every AI call path must surface a typed, friendly error —
never a raw stack trace. No network, no cost.
"""

from unittest.mock import MagicMock

import pytest

from src.tradelens.services import ai_client
from src.tradelens.services.ai_client import AIParseError, AIUnavailable, Usage


def _fake_message(text: str = "ok", *, stop_reason: str = "end_turn") -> MagicMock:
    resp = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp.content = [block]
    resp.stop_reason = stop_reason
    resp.model = "claude-fable-5"
    resp.usage.input_tokens = 10
    resp.usage.output_tokens = 5
    resp.usage.cache_read_input_tokens = 0
    return resp


def _usage() -> Usage:
    return Usage("claude-fable-5", 0, 0, 0, 0.0, 0.0)


@pytest.fixture()
def live(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "demo_mode", False)
    monkeypatch.setattr(ai_client.settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", lambda **k: "", raising=False
    )


# ---------------------------------------------------------------------------
# parse_ai_json → AIParseError on malformed JSON
# ---------------------------------------------------------------------------


def test_parse_ai_json_valid_object():
    from src.tradelens.services.ai_client import parse_ai_json

    assert parse_ai_json('{"a": 1}') == {"a": 1}


def test_parse_ai_json_strips_code_fence():
    from src.tradelens.services.ai_client import parse_ai_json

    assert parse_ai_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_ai_json_malformed_raises_typed_error():
    from src.tradelens.services.ai_client import parse_ai_json

    with pytest.raises(AIParseError, match="malformed"):
        parse_ai_json("definitely not json {")


# ---------------------------------------------------------------------------
# transport failures → AIUnavailable (returned, not raised)
# ---------------------------------------------------------------------------


def test_network_error_returns_ai_unavailable(live, monkeypatch):
    client = MagicMock()
    client.messages.create.side_effect = ConnectionError("network down")
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    result, usage = ai_client.chat("hi")
    assert isinstance(result, AIUnavailable)
    assert result.category == "network"
    assert "unavailable" in result.reason.lower()


def test_timeout_error_returns_ai_unavailable(live, monkeypatch):
    client = MagicMock()
    client.messages.create.side_effect = TimeoutError("slow")
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    result, _usage = ai_client.chat("hi")
    assert isinstance(result, AIUnavailable)


def test_double_refusal_returns_ai_unavailable(live, monkeypatch):
    refusal = _fake_message("", stop_reason="refusal")
    client = MagicMock()
    client.messages.create.side_effect = [refusal, refusal]
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)

    result, usage = ai_client.chat("borderline request")
    assert isinstance(result, AIUnavailable)
    assert usage.refused is True


# ---------------------------------------------------------------------------
# missing screenshot → clear typed error, not a raw FileNotFoundError
# ---------------------------------------------------------------------------


def test_missing_screenshot_gives_clear_error():
    from src.tradelens.services.vision import (
        ScreenshotAnalysisError,
        analyze_screenshot,
    )

    with pytest.raises(ScreenshotAnalysisError, match="Image not found"):
        analyze_screenshot("/no/such/path/chart.png", {"asset": "NQ"})


# ---------------------------------------------------------------------------
# malformed AI JSON in feature services → AIParseError
# ---------------------------------------------------------------------------


def test_grading_malformed_json_raises_parse_error(monkeypatch):
    from src.tradelens.services.grading import grade_trade

    monkeypatch.setattr(
        "src.tradelens.services.grading.chat", lambda *a, **k: ("not json!!", _usage())
    )
    monkeypatch.setattr(
        "src.tradelens.services.grading.load_prompt", lambda *a, **k: "system"
    )
    with pytest.raises(AIParseError):
        grade_trade({"asset": "NQ"}, None, {})


def test_patterns_malformed_json_raises_parse_error(monkeypatch):
    from src.tradelens.services.patterns import generate_cards

    monkeypatch.setattr(
        "src.tradelens.services.patterns.chat", lambda *a, **k: ("not json!!", _usage())
    )
    monkeypatch.setattr(
        "src.tradelens.services.patterns.load_prompt", lambda *a, **k: "system"
    )
    with pytest.raises(AIParseError):
        generate_cards({"total_trades": 3})


def test_vision_malformed_json_raises_parse_error(monkeypatch, tmp_path):
    from src.tradelens.services.vision import analyze_screenshot

    img = tmp_path / "chart.jpg"
    img.write_bytes(b"x")
    monkeypatch.setattr(
        "src.tradelens.services.vision.vision", lambda *a, **k: ("not json!!", _usage())
    )
    monkeypatch.setattr(
        "src.tradelens.services.vision.load_prompt", lambda *a, **k: "system"
    )
    with pytest.raises(AIParseError):
        analyze_screenshot(str(img), {"asset": "NQ"})
