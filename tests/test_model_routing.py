"""
Single-model guarantee: every AI call in TradeLens runs on Claude Opus 5.

These tests are the regression fence around three rules:
  1. The Opus 5 model ID is configured in exactly one place (config.py).
  2. Every request the Anthropic SDK receives carries that model ID —
     asserted directly for screenshot analysis (which autofill builds on),
     grading, journal, patterns and AI Partner chat, and for the three
     ai_client entrypoints (chat / vision / converse) that weekly recap and
     daily debrief go through.
  3. No caller can select a model, no service touches the SDK directly, and a
     refusal is never retried on a different model.

No network traffic: the Anthropic client is mocked throughout.
"""

from __future__ import annotations

import ast
import json
import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.tradelens.config import ANTHROPIC_MODEL_ID
from src.tradelens.services import ai_client

_SERVICES_DIR = Path(ai_client.__file__).resolve().parent
# Production package root (src/tradelens). The retired-model scan below is
# scoped to this tree only — NOT the whole repository. Historical documents
# (docs/), scripts/, and this test file itself may legitimately name the old
# models when describing what the system used to do.
_PACKAGE_ROOT = _SERVICES_DIR.parent

# Model IDs that must no longer appear in production code under src/tradelens.
_RETIRED_MODEL_IDS = ("claude-fable-5", "claude-haiku-4-5", "claude-opus-4-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_message(text: str) -> MagicMock:
    resp = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp.content = [block]
    resp.stop_reason = "end_turn"
    resp.model = ANTHROPIC_MODEL_ID
    resp.usage.input_tokens = 10
    resp.usage.output_tokens = 5
    resp.usage.cache_read_input_tokens = 0
    resp.usage.cache_creation_input_tokens = 0
    return resp


@pytest.fixture
def recording_client(monkeypatch):
    """A mocked Anthropic client that records every messages.create() call."""
    monkeypatch.setattr(ai_client.settings, "demo_mode", False)
    monkeypatch.setattr(ai_client.settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", lambda **k: "", raising=False
    )
    monkeypatch.setattr(ai_client, "encode_image", lambda *a, **k: "B64")

    client = MagicMock()
    client.messages.create.return_value = _fake_message("ok")
    monkeypatch.setattr(ai_client, "_get_client", lambda: client)
    return client


def _models_used(client) -> list[str]:
    return [call[1]["model"] for call in client.messages.create.call_args_list]


# ---------------------------------------------------------------------------
# The configured model ID
# ---------------------------------------------------------------------------


def test_configured_model_is_opus_5():
    assert ANTHROPIC_MODEL_ID == "claude-opus-5"


def test_no_retired_model_ids_in_production_code():
    """Retired model IDs are gone from production code under src/tradelens/.

    Scope note: this scan covers the shipped package only. It deliberately does
    NOT scan the repository root — docs/ keeps historical write-ups that still
    name the old models in past tense, and flagging those would be a false
    positive.
    """
    offenders = []
    for path in _PACKAGE_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for retired in _RETIRED_MODEL_IDS:
            if retired in text:
                offenders.append(f"{path.relative_to(_PACKAGE_ROOT)}: {retired}")
    assert offenders == [], (
        "Retired model IDs found in production code under src/tradelens: "
        f"{offenders}"
    )


# ---------------------------------------------------------------------------
# Callers cannot choose a model
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fn_name", ["chat", "vision", "converse"])
def test_public_entrypoints_accept_no_model_argument(fn_name):
    params = inspect.signature(getattr(ai_client, fn_name)).parameters
    assert "model" not in params


def _ai_calls_with_model_kwarg(path: Path) -> list[str]:
    """AST-scan a module for chat()/vision()/converse() calls passing `model=`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name not in {"chat", "vision", "converse"}:
            continue
        if any(kw.arg == "model" for kw in node.keywords):
            hits.append(f"{path.name}:{node.lineno}")
    return hits


def test_no_service_passes_a_model_argument():
    """Services render and call — model choice is not theirs to make."""
    offenders = []
    for path in _SERVICES_DIR.glob("*.py"):
        if path.name == "ai_client.py":
            continue
        offenders.extend(_ai_calls_with_model_kwarg(path))
    assert offenders == []


# ---------------------------------------------------------------------------
# Every ai_client entrypoint sends Opus 5
# ---------------------------------------------------------------------------


def test_chat_sends_opus_5(recording_client):
    ai_client.chat("hello")
    assert _models_used(recording_client) == [ANTHROPIC_MODEL_ID]


def test_vision_sends_opus_5(recording_client, tmp_path):
    img = tmp_path / "chart.jpg"
    img.write_bytes(b"x")
    ai_client.vision(str(img), "analyze this chart")
    assert _models_used(recording_client) == [ANTHROPIC_MODEL_ID]


def test_converse_sends_opus_5(recording_client):
    ai_client.converse([{"role": "user", "content": "hi"}])
    assert _models_used(recording_client) == [ANTHROPIC_MODEL_ID]


def test_usage_reports_opus_5(recording_client):
    _, usage = ai_client.chat("hello")
    assert usage.model == ANTHROPIC_MODEL_ID
    # Cost is priced from the Opus 5 table, not silently zeroed.
    assert usage.estimated_cost_usd > 0


def test_refusal_does_not_retry_on_another_model(recording_client):
    refused = _fake_message("")
    refused.stop_reason = "refusal"
    recording_client.messages.create.return_value = refused

    ai_client.chat("borderline request")
    assert _models_used(recording_client) == [ANTHROPIC_MODEL_ID]


# ---------------------------------------------------------------------------
# Every feature service reaches the SDK on Opus 5
# ---------------------------------------------------------------------------


def _sample_trade() -> dict:
    return {
        "id": 1,
        "asset": "NQ",
        "direction": "Long",
        "result": "Win",
        "pnl": 250.0,
        "rr": 2.0,
        "session": "New York",
        "notes": "Took the retest after the sweep.",
    }


def _sample_labels() -> dict:
    return {
        "bias": "bullish",
        "structure": "Higher highs.",
        "bos": True,
        "choch": False,
        "key_zones": [],
    }


def test_grading_uses_opus_5(recording_client, monkeypatch):
    from src.tradelens.services import grading

    recording_client.messages.create.return_value = _fake_message(
        '{"grade": "B", "score": 7, "one_line_verdict": "Solid.", "rubric": {'
        '"entry_quality": {"score": 7, "note": "n"},'
        '"risk_management": {"score": 7, "note": "n"},'
        '"exit_quality": {"score": 7, "note": "n"},'
        '"rule_adherence": {"score": 7, "note": "n"},'
        '"emotional_control": {"score": 7, "note": "n"}}}'
    )
    monkeypatch.setattr(grading, "is_demo", lambda: False, raising=False)

    # Grading was the one feature that used to route to a cheaper model.
    grading.grade_trade(_sample_trade(), None, _sample_labels())
    assert _models_used(recording_client) == [ANTHROPIC_MODEL_ID]


def test_journal_uses_opus_5(recording_client):
    from src.tradelens.services import journal

    recording_client.messages.create.return_value = _fake_message(
        "\n\n".join(f"{h}\n\nSample." for h in journal._REQUIRED_SECTIONS)
    )
    journal.generate_journal(_sample_trade(), _sample_labels(), None)
    assert _models_used(recording_client) == [ANTHROPIC_MODEL_ID]


def test_partner_chat_uses_opus_5(recording_client):
    from src.tradelens.services import partner

    recording_client.messages.create.return_value = _fake_message(
        "Looking back at the entry, the retest was the cleanest part of it."
    )
    partner.partner_reply(
        [{"role": "user", "content": "What did I do well on this trade?"}]
    )
    assert _models_used(recording_client) == [ANTHROPIC_MODEL_ID]


def test_screenshot_analysis_uses_opus_5(recording_client, tmp_path, monkeypatch):
    """Screenshot analysis (and autofill on top of it) runs on Opus 5."""
    from src.tradelens.services import vision as vision_service

    monkeypatch.setattr(vision_service, "is_demo", lambda: False, raising=False)
    img = tmp_path / "chart.png"
    img.write_bytes(b"x")
    recording_client.messages.create.return_value = _fake_message(
        json.dumps(
            {
                "bias": "bullish",
                "bias_confidence": 0.8,
                "structure": "Higher highs.",
                "bos": True,
                "choch": False,
                "key_zones": [],
            }
        )
    )
    vision_service.analyze_screenshot(str(img), _sample_trade())
    assert _models_used(recording_client) == [ANTHROPIC_MODEL_ID]


def test_patterns_uses_opus_5(recording_client):
    from src.tradelens.services import patterns

    recording_client.messages.create.return_value = _fake_message(
        json.dumps(
            {
                "patterns": [
                    {
                        "insight": "Re-entries after a loss underperform.",
                        "evidence_stat": "Win rate 58% → 24%.",
                        "sample_size": 11,
                        "confidence": "medium",
                        "impact": "-$430",
                        "suggested_rule": "Pause 15 minutes after a loss.",
                    }
                ]
            }
        )
    )
    patterns.generate_cards({"total_trades": 11})
    assert _models_used(recording_client) == [ANTHROPIC_MODEL_ID]


def test_no_service_imports_anthropic_directly():
    """Only ai_client may touch the SDK — that is what makes routing enforceable."""
    offenders = []
    for path in _SERVICES_DIR.glob("*.py"):
        if path.name == "ai_client.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                a.name.split(".")[0] == "anthropic" for a in node.names
            ):
                offenders.append(path.name)
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "anthropic"
            ):
                offenders.append(path.name)
    assert offenders == []
