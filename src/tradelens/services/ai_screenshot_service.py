"""
Post-trade screenshot analysis orchestration (Session C, Section 1).

Thin, Streamlit-free wrapper over services/vision.analyze_screenshot that adds
direct-image-URL support:

  * A direct image URL (.png/.jpg/.jpeg/.webp/.gif, or a HEAD Content-Type of
    image/*) is downloaded to a temp file (5s timeout), analyzed, then deleted.
  * A non-image URL (e.g. a TradingView chart *page*) is rejected with a clean
    message — no scraping is attempted.

The locked screenshot_v2 prompt and the existing AIAnalysis persistence are
reused unchanged. The UI gates the analyze button on is_ai_enabled(); this layer
just runs the analysis (and surfaces AIUnavailable as ScreenshotAnalysisError via
vision).
"""

from __future__ import annotations

import base64
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

from src.tradelens.services.demo import is_demo
from src.tradelens.services.vision import ScreenshotAnalysisError, analyze_screenshot

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_URL_TIMEOUT = 5  # seconds
_USER_AGENT = "TradeLens/1.0"

NOT_AN_IMAGE_MSG = (
    "This link could not be read as an image. "
    "Please upload the chart screenshot instead."
)

# 1×1 PNG — used only in DEMO_MODE so URL analysis stays zero-network.
_DUMMY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _is_url(value) -> bool:
    return isinstance(value, str) and value.lower().startswith(("http://", "https://"))


def is_image_url(url: str) -> bool:
    """True when `url` points at a direct image (by extension, else HEAD type)."""
    if not _is_url(url):
        return False
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in _IMAGE_EXTS):
        return True
    try:
        req = urllib.request.Request(
            url, method="HEAD", headers={"User-Agent": _USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=_URL_TIMEOUT) as resp:
            return resp.headers.get("Content-Type", "").lower().startswith("image/")
    except Exception:  # noqa: BLE001 — any failure means "not a usable image URL"
        return False


def _download_image(url: str) -> Path:
    ext = Path(urlparse(url).path).suffix.lower()
    if ext not in _IMAGE_EXTS:
        ext = ".png"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_URL_TIMEOUT) as resp:
        data = resp.read()
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
) -> tuple[dict, object]:
    """Analyze a local image path OR a direct image URL.

    Returns (analysis_dict, usage). Raises ScreenshotAnalysisError with a clean,
    user-facing message when a URL cannot be read as a direct image.
    """
    if _is_url(source):
        tmp = None
        try:
            if is_demo():
                tmp = _dummy_tempfile()  # zero-network; vision serves a fixture
            elif is_image_url(source):
                tmp = _download_image(source)
            else:
                raise ScreenshotAnalysisError(NOT_AN_IMAGE_MSG)
            return analyze_screenshot(tmp, trade_ctx, strategy_profile)
        finally:
            if tmp is not None:
                try:
                    tmp.unlink()
                except OSError:
                    pass

    return analyze_screenshot(Path(source), trade_ctx, strategy_profile)
