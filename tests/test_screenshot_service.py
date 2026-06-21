"""
Coverage + behavior tests for screenshot_service.py (Phase 5, week6-d5).

Screenshot upload across formats and degenerate inputs. Disk and DB are isolated:
SCREENSHOTS_DIR -> tmp_path, SessionLocal -> in-memory SQLite.
"""

import io

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.screenshot_service as screenshot_service
from src.tradelens.db.models import Base


class _FakeUpload:
    """Minimal stand-in for a Streamlit UploadedFile (name + read())."""

    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def read(self) -> bytes:
        return self._data


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    InMemorySession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(screenshot_service, "SessionLocal", InMemorySession)
    monkeypatch.setattr(screenshot_service, "SCREENSHOTS_DIR", tmp_path / "shots")
    yield
    Base.metadata.drop_all(engine)


def _image_bytes(fmt: str) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), (100, 150, 200)).save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.parametrize(
    "name,fmt",
    [("chart.png", "PNG"), ("chart.jpg", "JPEG"), ("chart.webp", "WEBP")],
)
def test_save_valid_image_formats(isolated, name, fmt):
    rec = screenshot_service.save_screenshot(1, _FakeUpload(name, _image_bytes(fmt)))

    assert rec.id is not None
    assert rec.trade_id == 1
    assert rec.width == 2 and rec.height == 2
    from pathlib import Path

    assert Path(rec.file_path).exists()


def test_save_oversized_image_still_persists(isolated):
    big = b"\x00" * (11 * 1024 * 1024)  # 11 MB, not a decodable image
    rec = screenshot_service.save_screenshot(2, _FakeUpload("big.png", big))

    from pathlib import Path

    assert Path(rec.file_path).exists()
    assert Path(rec.file_path).stat().st_size > 10 * 1024 * 1024
    # Undecodable -> dimensions are None, but the upload is saved, not crashed.
    assert rec.width is None and rec.height is None


def test_save_corrupt_file_persists_with_null_dims(isolated):
    rec = screenshot_service.save_screenshot(3, _FakeUpload("bad.png", b"not an image"))

    from pathlib import Path

    assert Path(rec.file_path).exists()
    assert rec.width is None and rec.height is None
