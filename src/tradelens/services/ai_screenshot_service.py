"""
Post-trade screenshot analysis orchestration (Session C, Section 1).

Thin, Streamlit-free wrapper over services/vision.analyze_screenshot that adds
direct-image-URL support:

  * A direct image URL (.png/.jpg/.jpeg/.webp/.gif, or a HEAD Content-Type of
    image/*) is downloaded to a temp file (5s timeout), analyzed, then deleted.
  * A non-image URL (e.g. a TradingView chart *page*) is rejected with a clean
    message — no scraping is attempted.

SSRF hardening (the URL is user-supplied): before any request the host is
resolved and rejected if it maps to a loopback / private / link-local / reserved
address (this blocks cloud-metadata endpoints like 169.254.169.254 and internal
services); redirects are disabled (a redirect is a classic SSRF pivot); and the
download is size-capped. Residual note: this does not fully defeat DNS-rebinding
(urllib re-resolves at connect time), which is an acceptable risk for this app.

The locked screenshot_v2 prompt and the existing AIAnalysis persistence are
reused unchanged.
"""

from __future__ import annotations

import base64
import ipaddress
import os
import socket
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Union
from urllib.parse import urlparse

from src.tradelens.services.demo import is_demo
from src.tradelens.services.vision import ScreenshotAnalysisError, analyze_screenshot

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_ALLOWED_SCHEMES = {"http", "https"}
_URL_TIMEOUT = 5  # seconds
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB cap on downloaded images
_USER_AGENT = "TradeLens/1.0"

NOT_AN_IMAGE_MSG = (
    "This link could not be read as an image. "
    "Please upload the chart screenshot instead."
)
TOO_LARGE_MSG = "That image is too large to analyze (max 10 MB)."

# 1×1 PNG — used only in DEMO_MODE so URL analysis stays zero-network.
_DUMMY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Block all HTTP redirects — a redirect is a classic SSRF pivot to an
    internal host that bypasses the pre-request host check."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _is_url(value) -> bool:
    return isinstance(value, str) and value.lower().startswith(("http://", "https://"))


def _has_image_extension(url: str) -> bool:
    return any(urlparse(url).path.lower().endswith(ext) for ext in _IMAGE_EXTS)


def _is_public_url(url: str) -> bool:
    """True only when the URL is http(s) and its host resolves entirely to public
    IPs. Rejects loopback / private / link-local / reserved / multicast targets."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or None)
    except (socket.gaierror, UnicodeError, ValueError, OSError):
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
            or ip.is_multicast
        ):
            return False
    return True


def is_image_url(url: str) -> bool:
    """True when `url` is a SAFE, direct image URL (public host; extension or
    HEAD Content-Type of image/*)."""
    if not _is_url(url) or not _is_public_url(url):
        return False
    if _has_image_extension(url):
        return True
    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": _USER_AGENT}
        )
        with _OPENER.open(req, timeout=_URL_TIMEOUT) as resp:
            return resp.headers.get("Content-Type", "").lower().startswith("image/")
    except Exception:  # noqa: BLE001 — any failure means "not a usable image URL"
        return False


def _download_image(url: str) -> Path:
    if not _is_public_url(url):  # defense-in-depth re-check before the GET
        raise ScreenshotAnalysisError(NOT_AN_IMAGE_MSG)
    ext = Path(urlparse(url).path).suffix.lower()
    if ext not in _IMAGE_EXTS:
        ext = ".png"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with _OPENER.open(req, timeout=_URL_TIMEOUT) as resp:
        data = resp.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise ScreenshotAnalysisError(TOO_LARGE_MSG)
    fd, tmp = tempfile.mkstemp(suffix=ext)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return Path(tmp)


def _dummy_tempfile() -> Path:
    fd, tmp = tempfile.mkstemp(suffix=".png")
    with os.fdopen(fd, "wb") as fh:
        fh.write(_DUMMY_PNG)
    return Path(tmp)


def analyze_source(
    source: Union[str, Path],
    trade_ctx: dict,
    strategy_profile: Optional[dict] = None,
    analyzer: Optional[Callable] = None,
) -> tuple[dict, object]:
    """Analyze a local image path OR a direct image URL.

    Returns (analysis_dict, usage). Raises ScreenshotAnalysisError with a clean,
    user-facing message when a URL cannot be read as a direct image.

    ``analyzer`` selects the vision analyzer — defaults to the screenshot_v2
    ``analyze_screenshot`` (resolved at call time so tests can monkeypatch it);
    the screenshot-first New Trade flow passes ``analyze_screenshot_v3``. The
    SSRF-hardened URL/temp-file handling is shared by both.
    """
    run = analyzer or analyze_screenshot
    if _is_url(source):
        tmp = None
        try:
            if is_demo():
                tmp = _dummy_tempfile()  # zero-network; vision serves a fixture
            elif is_image_url(source):
                tmp = _download_image(source)
            else:
                raise ScreenshotAnalysisError(NOT_AN_IMAGE_MSG)
            return run(tmp, trade_ctx, strategy_profile)
        finally:
            if tmp is not None:
                try:
                    tmp.unlink()
                except OSError:
                    pass

    return run(Path(source), trade_ctx, strategy_profile)
