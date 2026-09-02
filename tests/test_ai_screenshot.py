"""
AI screenshot orchestration (Session C, Section 1): URL handling, SSRF guard, and
clean fallback.

The actual vision call is exercised elsewhere (DEMO_MODE fixtures); here we lock
down URL-vs-local routing, the non-image-URL rejection, and the SSRF host check —
all without hitting the network.
"""

import io

import pytest
from PIL import Image

import src.tradelens.services.ai_screenshot_service as svc
from src.tradelens.services import url_ingest
from src.tradelens.services.vision import ScreenshotAnalysisError


def _fake_getaddrinfo(ip):
    return lambda host, port=None: [(2, 1, 6, "", (ip, port or 0))]


def test_is_image_url_by_extension(monkeypatch):
    # Treat the host as public so we test the extension path without DNS.
    monkeypatch.setattr(svc, "_is_public_url", lambda u: True)
    assert svc.is_image_url("https://example.com/chart.png")
    assert svc.is_image_url("https://example.com/A.JPG")
    assert svc.is_image_url("http://cdn.example.com/x.webp")


def test_is_image_url_rejects_non_urls_and_pages():
    assert not svc.is_image_url("not a url")
    assert not svc.is_image_url("")
    assert not svc.is_image_url(None)


def test_is_image_url_blocks_private_host(monkeypatch):
    # SSRF: even a .png on a loopback/private host must be rejected.
    monkeypatch.setattr(
        url_ingest.socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1")
    )
    assert not svc.is_image_url("http://localhost/chart.png")
    monkeypatch.setattr(
        url_ingest.socket, "getaddrinfo", _fake_getaddrinfo("169.254.169.254")
    )
    assert not svc.is_image_url("http://metadata/latest.png")
    monkeypatch.setattr(url_ingest.socket, "getaddrinfo", _fake_getaddrinfo("10.0.0.5"))
    assert not svc.is_image_url("http://internal/chart.png")


def test_is_public_url_allows_public_ip(monkeypatch):
    monkeypatch.setattr(
        url_ingest.socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34")
    )
    assert svc._is_public_url("https://example.com/x.png")


def test_downloaded_url_image_is_reencoded_before_the_vision_model(monkeypatch):
    """A valid image's trailing payload must not reach the model."""
    image = Image.new("RGB", (2, 2), color=(10, 20, 30))
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    fetched = encoded.getvalue() + b"PROMPT-OVERRIDE-TRAILER"

    monkeypatch.setattr(svc.url_ingest, "fetch_image_bytes", lambda _url: fetched)
    path = svc._download_image("https://charts.example/trade.png")
    try:
        normalized = path.read_bytes()
        assert normalized != fetched
        assert b"PROMPT-OVERRIDE-TRAILER" not in normalized
        with Image.open(path) as reopened:
            assert reopened.format == "PNG"
            assert reopened.size == (2, 2)
    finally:
        path.unlink(missing_ok=True)


def test_download_image_rejects_private_host(monkeypatch):
    monkeypatch.setattr(
        url_ingest.socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1")
    )
    with pytest.raises(ScreenshotAnalysisError):
        svc._download_image("http://localhost/evil.png")


def test_non_image_url_rejected_with_clean_message(monkeypatch):
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
