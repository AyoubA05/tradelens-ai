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

from PIL import Image, UnidentifiedImageError

from src.tradelens.api.storage import MAX_UPLOAD_BYTES

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


class ImageRejected(ValueError):
    """The object is not an image we will process.

    Carries no detail about why beyond a stable phrase: an attacker probing the
    validator should not be told which check they failed.
    """


def _looks_like_an_image(data: bytes) -> bool:
    return any(data.startswith(prefix) for prefix, _ in _MAGIC)


def validate_and_normalise(data: bytes) -> tuple[bytes, str, int, int]:
    """Return `(png_bytes, "image/png", width, height)` or raise `ImageRejected`."""
    if not data or len(data) > MAX_UPLOAD_BYTES or not _looks_like_an_image(data):
        raise ImageRejected("not a supported image")

    try:
        with Image.open(io.BytesIO(data)) as image:
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
    return out.getvalue(), "image/png", width, height
