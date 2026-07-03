"""
Tests for vision.py — all AI calls are mocked; no network traffic, no cost.
"""

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from src.tradelens.services.vision import (
    ScreenshotAnalysisError,
    _EXPECTED_KEYS,
    analyze_screenshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jpeg(tmp_path: Path, name: str = "chart.jpg") -> Path:
    """Create a minimal 1×1 JPEG that Pillow can open."""
    p = tmp_path / name
    img = Image.new("RGB", (1, 1), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    p.write_bytes(buf.getvalue())
    return p


def _mock_vision_response(analysis: dict):
    """Return (json_string, mock_Usage) matching the ai_client.vision signature."""
    from src.tradelens.services.ai_client import Usage

    usage = Usage(
        model="claude-fable-5",
        tokens_in=300,
        tokens_out=150,
        total_tokens=450,
        estimated_cost_usd=0.00375,
        latency_s=1.5,
    )
    return json.dumps(analysis), usage


_VALID_ANALYSIS = {
    "bias": "bullish",
    "bias_confidence": 0.8,
    "detected_timeframe": "15m",
    "detected_asset": "NQ",
    "structure": "Higher highs and higher lows; bullish trend intact.",
    "bos": True,
    "choch": False,
    "key_zones": [
        {
            "type": "order_block",
            "description": "Bearish OB at 19,250 acting as support",
            "approx_price": 19250.0,
            "confidence": 0.75,
        }
    ],
    "matched_strategy": None,
    "matched_strategy_reason": None,
    "possible_mistakes": ["Entry slightly late after BOS confirmation"],
    "missed_opportunities": ["Could have scaled in at OB retest"],
    "trade_quality": 7,
    "notes_to_user": "Solid structure read. Entry timing can be tightened on future setups.",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_analyze_screenshot_success(tmp_path):
    image = _make_jpeg(tmp_path)
    trade_ctx = {"asset": "NQ", "direction": "Long", "result": "Win", "pnl": 250}

    with patch(
        "src.tradelens.services.vision.vision",
        return_value=_mock_vision_response(_VALID_ANALYSIS),
    ), patch(
        "src.tradelens.services.vision.load_prompt",
        return_value="mock system prompt",
    ):
        result, usage = analyze_screenshot(image, trade_ctx)

    assert set(result.keys()) == _EXPECTED_KEYS
    assert result["bias"] == "bullish"
    assert result["trade_quality"] == 7
    assert isinstance(result["key_zones"], list)
    assert usage.model == "claude-fable-5"
    assert usage.tokens_in == 300


def test_analyze_screenshot_no_strategy_fallback(tmp_path):
    image = _make_jpeg(tmp_path)
    trade_ctx = {"asset": "BTCUSD", "direction": "Short", "result": "Loss"}

    analysis = {
        **_VALID_ANALYSIS,
        "matched_strategy": None,
        "matched_strategy_reason": None,
    }

    with patch(
        "src.tradelens.services.vision.vision",
        return_value=_mock_vision_response(analysis),
    ), patch(
        "src.tradelens.services.vision.load_prompt",
        return_value="mock system prompt",
    ):
        result, usage = analyze_screenshot(image, trade_ctx, strategy_profile=None)

    assert set(result.keys()) == _EXPECTED_KEYS
    assert result["matched_strategy"] is None
    assert result["matched_strategy_reason"] is None


def test_analyze_screenshot_missing_image(tmp_path):
    missing = tmp_path / "does_not_exist.png"
    with pytest.raises(ScreenshotAnalysisError, match="Image not found"):
        analyze_screenshot(missing, {})


def test_analyze_screenshot_unsupported_extension(tmp_path):
    bad_file = tmp_path / "chart.bmp"
    bad_file.write_bytes(b"\x00\x01")
    with pytest.raises(ScreenshotAnalysisError, match="Unsupported file type"):
        analyze_screenshot(bad_file, {})


def test_analyze_screenshot_empty_file(tmp_path):
    empty = tmp_path / "empty.jpg"
    empty.write_bytes(b"")
    with pytest.raises(ScreenshotAnalysisError, match="Image file is empty"):
        analyze_screenshot(empty, {})


def test_analyze_screenshot_missing_prompt(tmp_path):
    image = _make_jpeg(tmp_path)
    with patch(
        "src.tradelens.services.vision.load_prompt",
        side_effect=FileNotFoundError("Prompt file not found"),
    ):
        with pytest.raises(FileNotFoundError, match="Prompt file not found"):
            analyze_screenshot(image, {"asset": "NQ"})


def test_analyze_screenshot_malformed_json(tmp_path):
    image = _make_jpeg(tmp_path)
    from src.tradelens.services.ai_client import Usage

    bad_usage = Usage("claude-fable-5", 10, 5, 15, 0.0001, 0.5)

    with patch(
        "src.tradelens.services.vision.vision",
        return_value=("not valid json {{", bad_usage),
    ), patch(
        "src.tradelens.services.vision.load_prompt",
        return_value="mock system prompt",
    ):
        from src.tradelens.services.ai_client import AIParseError

        with pytest.raises(AIParseError, match="malformed"):
            analyze_screenshot(image, {"asset": "NQ"})


def test_fill_defaults_handles_missing_keys(tmp_path):
    """Partial API response — missing keys get filled with safe defaults."""
    image = _make_jpeg(tmp_path)
    partial = {"bias": "bearish", "trade_quality": 5}

    from src.tradelens.services.ai_client import Usage

    usage = Usage("claude-fable-5", 10, 5, 15, 0.0001, 0.5)

    with patch(
        "src.tradelens.services.vision.vision",
        return_value=(json.dumps(partial), usage),
    ), patch(
        "src.tradelens.services.vision.load_prompt",
        return_value="mock system prompt",
    ):
        result, _ = analyze_screenshot(image, {})

    assert set(result.keys()) == _EXPECTED_KEYS
    assert result["bias"] == "bearish"
    assert result["key_zones"] == []
    assert result["possible_mistakes"] == []
    assert result["notes_to_user"] is None


def test_analyze_screenshot_uses_v2_and_returns_smc_keys(tmp_path):
    """vision.py must load screenshot_v2 and return the 4 new SMC proposal keys."""
    image = _make_jpeg(tmp_path)
    analysis = {
        **_VALID_ANALYSIS,
        "htf_bias": "bullish",
        "liquidity_sweep": True,
        "fvg_used": False,
        "order_block_used": True,
    }
    captured = {}

    def fake_load_prompt(name):
        captured["name"] = name
        return "mock system prompt"

    with patch(
        "src.tradelens.services.vision.vision",
        return_value=_mock_vision_response(analysis),
    ), patch("src.tradelens.services.vision.load_prompt", side_effect=fake_load_prompt):
        result, _ = analyze_screenshot(image, {"asset": "NQ"})

    assert captured["name"] == "screenshot_v2"
    assert {"htf_bias", "liquidity_sweep", "fvg_used", "order_block_used"} <= set(
        result.keys()
    )
    assert result["htf_bias"] == "bullish"
    assert result["liquidity_sweep"] is True
    assert result["fvg_used"] is False
    assert result["order_block_used"] is True


def test_analyze_screenshot_smc_keys_default_when_absent(tmp_path):
    """When the AI omits SMC keys, they are filled with safe None defaults."""
    image = _make_jpeg(tmp_path)
    with patch(
        "src.tradelens.services.vision.vision",
        return_value=_mock_vision_response(_VALID_ANALYSIS),  # no SMC keys
    ), patch("src.tradelens.services.vision.load_prompt", return_value="mock"):
        result, _ = analyze_screenshot(image, {"asset": "NQ"})

    assert result["htf_bias"] is None
    assert result["liquidity_sweep"] is None
    assert result["fvg_used"] is None
    assert result["order_block_used"] is None


def test_analyze_screenshot_ai_unavailable_raises(tmp_path):
    """A refusal/outage (AIUnavailable) is surfaced as a typed ScreenshotAnalysisError."""
    from src.tradelens.services.ai_client import AIUnavailable, Usage

    image = _make_jpeg(tmp_path)
    usage = Usage("claude-fable-5", 0, 0, 0, 0.0, 0.0, refused=True)
    with patch(
        "src.tradelens.services.vision.vision",
        return_value=(AIUnavailable("AI declined", category="refusal"), usage),
    ), patch(
        "src.tradelens.services.vision.load_prompt",
        return_value="mock system prompt",
    ):
        with pytest.raises(ScreenshotAnalysisError, match="AI declined"):
            analyze_screenshot(image, {"asset": "NQ"})


# ---------------------------------------------------------------------------
# screenshot_v3 defaults — the extraction-contract additions get safe defaults
# ---------------------------------------------------------------------------


def test_fill_defaults_v3_includes_new_extraction_fields():
    from src.tradelens.services.vision import _fill_defaults_v3

    out = _fill_defaults_v3({})
    # descriptive gains instrument_name; overlay gains pnl / RR / confidence / labels
    assert out["descriptive"]["instrument_name"] is None
    assert out["trade_overlay"]["pnl"] is None
    assert out["trade_overlay"]["risk_reward_ratio"] is None
    assert out["trade_overlay"]["overall_confidence"] is None
    assert out["trade_overlay"]["visible_labels"] == []


def test_fill_defaults_v3_preserves_present_extraction_fields():
    from src.tradelens.services.vision import _fill_defaults_v3

    data = {
        "descriptive": {
            "detected_asset": "MNQU2026",
            "instrument_name": "Micro E-mini Nasdaq-100",
        },
        "trade_overlay": {
            "pnl": 172.25,
            "risk_reward_ratio": "2.01:1",
            "overall_confidence": "high",
            "visible_labels": ["MNQU2026", "1m"],
            "source": "visible_trade_box",
        },
    }
    out = _fill_defaults_v3(data)
    assert out["descriptive"]["detected_asset"] == "MNQU2026"
    assert out["descriptive"]["instrument_name"] == "Micro E-mini Nasdaq-100"
    assert out["trade_overlay"]["pnl"] == 172.25
    assert out["trade_overlay"]["risk_reward_ratio"] == "2.01:1"
    assert out["trade_overlay"]["overall_confidence"] == "high"
    assert out["trade_overlay"]["visible_labels"] == ["MNQU2026", "1m"]


# ---------------------------------------------------------------------------
# check_screenshot_quality — local pre-check before spending on a vision call
# ---------------------------------------------------------------------------


def _make_png(tmp_path: Path, name: str = "chart.png", size=(1600, 900)) -> Path:
    p = tmp_path / name
    Image.new("RGB", size, color=(40, 40, 40)).save(p, format="PNG")
    return p


def test_quality_good_image_has_no_warnings(tmp_path):
    from src.tradelens.services.vision import check_screenshot_quality

    q = check_screenshot_quality(_make_png(tmp_path))
    assert q.usable is True
    assert q.warnings == []


def test_quality_low_resolution_warns_but_stays_usable(tmp_path):
    from src.tradelens.services.vision import check_screenshot_quality

    q = check_screenshot_quality(_make_png(tmp_path, size=(320, 200)))
    assert q.usable is True  # degraded, not blocked
    assert any("resolution" in w.lower() for w in q.warnings)


def test_quality_extreme_aspect_ratio_warns_as_possible_crop(tmp_path):
    from src.tradelens.services.vision import check_screenshot_quality

    q = check_screenshot_quality(_make_png(tmp_path, size=(3000, 400)))
    assert q.usable is True
    assert any("crop" in w.lower() for w in q.warnings)


def test_quality_corrupt_file_is_unusable(tmp_path):
    from src.tradelens.services.vision import check_screenshot_quality

    p = tmp_path / "broken.png"
    p.write_bytes(b"this is not an image at all")
    q = check_screenshot_quality(p)
    assert q.usable is False
    assert q.warnings  # says why


def test_quality_missing_or_empty_file_is_unusable(tmp_path):
    from src.tradelens.services.vision import check_screenshot_quality

    q = check_screenshot_quality(tmp_path / "nope.png")
    assert q.usable is False

    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    assert check_screenshot_quality(empty).usable is False
