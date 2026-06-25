"""
AI-disabled behavior (Session C, Section 8).

When no API key is configured, AI calls must return a clean typed "unavailable"
result (or raise a friendly, typed error) — never a raw stack trace.
"""

import pytest

import src.tradelens.services.ai_client as ai_client
from src.tradelens.services.ai_client import AIUnavailable
from src.tradelens.services.ai_screenshot_service import _DUMMY_PNG
from src.tradelens.services.vision import ScreenshotAnalysisError, analyze_screenshot


def test_chat_returns_unavailable_without_key(monkeypatch):
    monkeypatch.setattr(ai_client, "_has_key", lambda: False)
    monkeypatch.setattr(ai_client.settings, "demo_mode", False)
    content, usage = ai_client.chat("hello")
    assert isinstance(content, AIUnavailable)
    assert content.category == "config"


def test_analyze_screenshot_raises_clean_error_without_key(monkeypatch, tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(_DUMMY_PNG)  # a real, tiny PNG so path/PIL checks pass
    monkeypatch.setattr(ai_client, "_has_key", lambda: False)
    monkeypatch.setattr(ai_client.settings, "demo_mode", False)
    with pytest.raises(ScreenshotAnalysisError):
        analyze_screenshot(img, {"asset": "NQ"})
