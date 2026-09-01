"""Prove an uploaded object is an image before anything else touches it.

A presigned upload reaches R2 without passing through application code, so what
lands there is whatever the client sent. Everything downstream — the AI vision
call, the browser rendering it — treats it as a picture, so this is the only
place that can decide whether it is one.

The output is a re-encoded PNG, not the original bytes. Re-encoding is what
defeats polyglot files: a valid image with an appended payload survives every
header check ever written and does not survive being decoded and written out
fresh. It also drops EXIF, including location data a trader never meant to share.

The presigned PUT's policy (storage.py) binds ContentType only — it cannot bind
a maximum size, since a presigned PUT's ContentLength constrains an EXACT size,
not a ceiling. MAX_UPLOAD_BYTES is therefore enforced here, on the input bytes,
as the real size gate. Imported from storage.py rather than redefined so the
two limits cannot drift apart.
"""

from __future__ import annotations

import io
from typing import Optional

from PIL import Image, UnidentifiedImageError

from src.tradelens.api.storage import MAX_UPLOAD_BYTES, NORMALISED_CONTENT_TYPE

MAX_PIXELS = 50_000_000
MAX_DIMENSION = 12_000

# Guards Pillow against decompression bombs: a small file that expands into
# gigabytes of pixels. Set below Pillow's own default so the check is ours.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"\xff\xd8\xff", "JPEG"),
    (b"RIFF", "WEBP"),
)
_FORMAT_FOR_CONTENT_TYPE = {
    "image/png": "PNG",
    "image/jpeg": "JPEG",
    "image/webp": "WEBP",
}


_CONTENT_TYPE_FOR_FORMAT = {
    format_name: content_type
    for content_type, format_name in _FORMAT_FOR_CONTENT_TYPE.items()
}


class ImageRejected(ValueError):
    """The object is not an image we will process.

    Carries no detail about why beyond a stable phrase: an attacker probing the
    validator should not be told which check they failed.
    """


def _looks_like_an_image(data: bytes) -> bool:
    return any(data.startswith(prefix) for prefix, _ in _MAGIC)


def sniff_content_type(data: bytes) -> Optional[str]:
    """The content type these bytes CLAIM to be, from magic alone, or None.

    Only a claim, and deliberately so. It exists because a URL ingest has no
    presigned Content-Type to name the quarantine key with, and the key's
    extension is what `finalize_upload` later feeds back in as
    `expected_content_type`. Whether the bytes really are that format is still
    decided by `validate_and_normalise` decoding them — this only picks which
    claim has to be corroborated.
    """
    if not isinstance(data, bytes):
        return None
    for prefix, format_name in _MAGIC:
        if not data.startswith(prefix):
            continue
        # RIFF alone is a container family, not WebP: the four bytes at offset
        # 8 are what distinguish it from WAV or AVI.
        if format_name == "WEBP" and data[8:12] != b"WEBP":
            return None
        return _CONTENT_TYPE_FOR_FORMAT[format_name]
    return None


def validate_and_normalise(
    data: bytes, *, expected_content_type: Optional[str] = None
) -> tuple[bytes, str, int, int]:
    """Return `(png_bytes, "image/png", width, height)` or raise `ImageRejected`."""
    if not data or len(data) > MAX_UPLOAD_BYTES or not _looks_like_an_image(data):
        raise ImageRejected("not a supported image")

    try:
        with Image.open(io.BytesIO(data)) as image:
            expected_format = _FORMAT_FOR_CONTENT_TYPE.get(expected_content_type)
            if expected_content_type is not None and image.format != expected_format:
                raise ImageRejected("not a supported image")
            if getattr(image, "n_frames", 1) > 1:
                raise ImageRejected("not a supported image")

            width, height = image.size
            if (
                width > MAX_DIMENSION
                or height > MAX_DIMENSION
                or width * height > MAX_PIXELS
            ):
                raise ImageRejected("not a supported image")

            image.load()
            # Re-create through the pixel data only. Nothing from the source
            # container — metadata, trailing bytes, ancillary chunks — travels.
            clean = Image.new("RGB", image.size)
            clean.paste(image.convert("RGB"))
    except ImageRejected:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise ImageRejected("not a supported image") from exc

    out = io.BytesIO()
    clean.save(out, format="PNG", optimize=True)
    return out.getvalue(), NORMALISED_CONTENT_TYPE, width, height
