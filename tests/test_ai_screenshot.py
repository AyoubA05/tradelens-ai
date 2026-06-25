"""
AI screenshot orchestration (Session C, Section 1): URL handling + clean fallback.

The actual vision call is exercised elsewhere (DEMO_MODE fixtures); here we lock
down the URL-vs-local routing and the non-image-URL rejection without hitting the
network.
"""

import pytest

import src.tradelens.services.ai_screenshot_service as svc
from src.tradelens.services.vision import ScreenshotAnalysisError


def test_is_image_url_by_extension():
    assert svc.is_image_url("https://example.com/chart.png")
    assert svc.is_image_url("https://example.com/A.JPG")
    assert svc.is_image_url("http://cdn.example.com/x.webp")


def test_is_image_url_rejects_non_urls_and_pages():
    assert not svc.is_image_url("not a url")
    assert not svc.is_image_url("")
    assert not svc.is_image_url(None)


def test_non_image_url_rejected_with_clean_message(monkeypatch):
    # Avoid the network: treat the page URL as a non-image.
    monkeypatch.setattr(svc, "is_image_url", lambda u: False)
    monkeypatch.setattr(svc, "is_demo", lambda: False)
    with pytest.raises(ScreenshotAnalysisError) as exc:
        svc.analyze_source("https://www.tradingview.com/chart/abc123/", {})
    assert "upload the chart screenshot" in str(exc.value)


def test_local_path_routes_to_vision(monkeypatch):
    captured = {}

    def fake_analyze(path, ctx, profile=None):
        captured["path"] = str(path)
        return {"bias": "neutral"}, object()

    monkeypatch.setattr(svc, "analyze_screenshot", fake_analyze)
    result, _usage = svc.analyze_source("/tmp/shot.png", {"asset": "NQ"})
    assert result == {"bias": "neutral"}
    assert captured["path"] == "/tmp/shot.png"
