import io
import struct
import zlib

import pytest
from PIL import Image

from src.tradelens.api.imaging import ImageRejected, validate_and_normalise
from src.tradelens.api.storage import MAX_UPLOAD_BYTES


def _png(size=(64, 48), mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, "teal").save(buf, format="PNG")
    return buf.getvalue()


def test_a_real_png_is_accepted_and_normalised():
    data, content_type, w, h = validate_and_normalise(_png())
    assert content_type == "image/png"
    assert (w, h) == (64, 48)
    assert data.startswith(b"\x89PNG")


def test_a_renamed_text_file_is_refused():
    """Magic bytes, not the declared type. A client's Content-Type is a claim."""
    with pytest.raises(ImageRejected):
        validate_and_normalise(b"<script>alert(1)</script>")


def test_svg_is_refused():
    with pytest.raises(ImageRejected):
        validate_and_normalise(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')


def test_trailing_bytes_do_not_survive_normalisation():
    """A polyglot file — valid image plus an appended payload — must not be
    stored or handed to AI with the payload intact."""
    poisoned = _png() + b"<?php system($_GET['c']); ?>"
    data, _, _, _ = validate_and_normalise(poisoned)
    assert b"<?php" not in data


def test_exif_is_stripped():
    """Chart screenshots can carry EXIF the trader never meant to share."""
    buf = io.BytesIO()
    image = Image.new("RGB", (32, 32), "black")
    exif = Image.Exif()
    exif[271] = "TestMake"  # Make tag: a real value, not an empty EXIF block.
    image.save(buf, format="JPEG", exif=exif.tobytes())
    data, _, _, _ = validate_and_normalise(buf.getvalue())
    assert Image.open(io.BytesIO(data)).getexif() == {}


def test_an_oversized_image_is_refused():
    # One pixel past MAX_DIMENSION on one axis — cheap to allocate (12001x10),
    # unlike a 20000x20000 image which would trip Pillow's own decompression
    # bomb guard inside the test itself rather than inside the validator.
    with pytest.raises(ImageRejected):
        validate_and_normalise(_png(size=(12001, 10)))


def test_a_pillow_decompression_bomb_is_a_stable_rejection_not_a_500():
    """Trigger Pillow's own >2x bomb error without allocating the pixels."""
    data = bytearray(_png(size=(1, 1)))
    ihdr_data = struct.pack(">II", 12001, 12001) + bytes(data[24:29])
    data[16:29] = ihdr_data
    data[29:33] = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data))

    with pytest.raises(ImageRejected):
        validate_and_normalise(bytes(data))


def test_empty_input_is_refused():
    with pytest.raises(ImageRejected):
        validate_and_normalise(b"")


def test_an_animated_gif_is_refused():
    """Multi-frame payloads are not chart screenshots."""
    buf = io.BytesIO()
    frames = [Image.new("P", (8, 8), i) for i in range(3)]
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:])
    with pytest.raises(ImageRejected):
        validate_and_normalise(buf.getvalue())


def test_an_oversized_upload_is_refused():
    """The real MAX_UPLOAD_BYTES gate. The presigned PUT policy only binds
    ContentType (see storage.py), so this is the only place that enforces
    the size limit. Imported from storage so the two limits cannot drift."""
    oversized = _png(size=(1, 1)) + b"\x00" * (MAX_UPLOAD_BYTES + 1)
    with pytest.raises(ImageRejected):
        validate_and_normalise(oversized)
