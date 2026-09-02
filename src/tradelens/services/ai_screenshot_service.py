"""
Post-trade screenshot analysis orchestration (Session C, Section 1).

Thin, Streamlit-free wrapper over services/vision.analyze_screenshot that adds
direct-image-URL support:

  * A direct image URL (.png/.jpg/.jpeg/.webp/.gif, or a HEAD Content-Type of
    image/*) is downloaded to a temp file (5s timeout), analyzed, then deleted.
  * A non-image URL (e.g. a TradingView chart *page*) is rejected with a clean
    message — no scraping is attempted.

SSRF hardening lives in `services/url_ingest`, which owns the single
public-address policy and the only fetcher: it resolves the host once, refuses
loopback / private / link-local / reserved / multicast / unspecified targets,
and then connects to that validated address so the connection cannot resolve
the name a second time (DNS rebinding). Redirects are refused and the body is
capped there too. This module only writes the returned bytes to a temp file for
the vision call.

The locked screenshot_v2 prompt and the existing AIAnalysis persistence are
reused unchanged.
"""

from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional, Union
from urllib.parse import urlparse

from src.tradelens.services import url_ingest
from src.tradelens.services.demo import is_demo
from src.tradelens.services.vision import ScreenshotAnalysisError, analyze_screenshot

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

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


def _is_url(value) -> bool:
    return isinstance(value, str) and value.lower().startswith(("http://", "https://"))


def _has_image_extension(url: str) -> bool:
    return any(urlparse(url).path.lower().endswith(ext) for ext in _IMAGE_EXTS)


# One policy, one definition. `url_ingest` owns it because that is where the
# fetch happens; a second copy here is how the two would drift apart.
_is_public_url = url_ingest.is_public_url


def is_image_url(url: str) -> bool:
    """True when `url` is a SAFE, direct image URL (public host; extension or
    HEAD Content-Type of image/*)."""
    if not _is_url(url) or not _is_public_url(url):
        return False
    if _has_image_extension(url):
        return True
    # The probe is a request too, so it goes through the pinned fetcher rather
    # than an opener that would resolve the host a second time.
    content_type = url_ingest.probe_content_type(url)
    return bool(content_type and content_type.startswith("image/"))


def _download_image(url: str) -> Path:
    """Fetch through the rebinding-safe fetcher, then stage for the vision call.

    The bytes are still untrusted here — this path predates quarantine and
    feeds only the model, never the bucket. Anything that reaches storage goes
    through `POST /trades/{id}/screenshot/ingest-url` instead, which promotes
    through `finalize_upload` and its re-encode.
    """
    try:
        data = url_ingest.fetch_image_bytes(url)
    except url_ingest.UrlIngestError as exc:
        raise ScreenshotAnalysisError(str(exc)) from exc

    # This legacy Streamlit caller does not have a trade id with which to use
    # R2 quarantine, but it must still have the same byte trust boundary as
    # the website ingest route.  Decode, dimension-check and re-encode before
    # staging anything for vision; a polyglot/trailing payload, EXIF, animation
    # or decompression bomb therefore cannot reach the model through this
    # older URL entry point.
    from src.tradelens.api.imaging import (
        ImageRejected,
        sniff_content_type,
        validate_and_normalise,
    )

    claimed_type = sniff_content_type(data)
    if claimed_type is None:
        raise ScreenshotAnalysisError(NOT_AN_IMAGE_MSG)
    try:
        normalized, _content_type, _width, _height = validate_and_normalise(
            data, expected_content_type=claimed_type
        )
    except ImageRejected as exc:
        raise ScreenshotAnalysisError(NOT_AN_IMAGE_MSG) from exc

    # The normalizer always emits PNG; keeping the source extension after a
    # re-encode would make MIME inference disagree with the bytes.
    fd, tmp = tempfile.mkstemp(suffix=".png")
    with os.fdopen(fd, "wb") as fh:
        fh.write(normalized)
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
