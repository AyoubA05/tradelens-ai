import io
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from src.tradelens.db.models import Screenshot, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ownership import require_user_id

# Relative to CWD (project root); consistent with session.py's sqlite:///./data/tradelens.db
SCREENSHOTS_DIR = Path("data/screenshots")


def _require_owned_trade(trade_id: int, user_id: int) -> int:
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        exists = (
            db.query(Trade.id)
            .filter(Trade.id == trade_id, Trade.user_id == owner)
            .first()
        )
    finally:
        db.close()
    if exists is None:
        raise PermissionError("trade not found")
    return owner


def save_screenshot(trade_id: int, uploaded_file, *, user_id: int) -> Screenshot:
    """
    Write an uploaded chart image to disk and insert a screenshots row.

    Model field mapping (verified against models.py):
      Screenshot.trade_id   <- trade_id arg
      Screenshot.file_path  <- str(dest)          (NOT 'filepath')
      Screenshot.uploaded_at <- ISO timestamp      (NOT 'uploadedat')
      Screenshot.width / .height <- from Pillow

    Session pattern: SessionLocal() directly, matching trade_service.py.
    uploaded_file: Streamlit UploadedFile object.
    """
    _require_owned_trade(trade_id, user_id)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    dest = SCREENSHOTS_DIR / f"{trade_id}_{uploaded_file.name}"

    # Single read — bytes used for both disk write and Pillow (no double-read / seek issue)
    file_bytes = uploaded_file.read()
    dest.write_bytes(file_bytes)

    try:
        img = Image.open(io.BytesIO(file_bytes))
        width, height = img.size
    except Exception:
        width, height = None, None

    db: Session = SessionLocal()
    try:
        record = Screenshot(
            trade_id=trade_id,
            file_path=str(dest),
            width=width,
            height=height,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_screenshot_url(trade_id: int, url: str, *, user_id: int) -> Screenshot:
    """Insert a screenshots row pointing at a remote image URL (no disk write).

    The file_path stores the URL as-is; the UI renders http(s) paths directly and
    only does a local-file existence check for non-URL paths.
    """
    _require_owned_trade(trade_id, user_id)
    db: Session = SessionLocal()
    try:
        record = Screenshot(
            trade_id=trade_id,
            file_path=str(url).strip(),
            width=None,
            height=None,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def record_object_screenshot(
    trade_id: int,
    file_path: str,
    *,
    user_id: int,
    width=None,
    height=None,
):
    """Record an already-promoted object-store key as a screenshots row.

    `save_screenshot` cannot serve the web path: it writes bytes to local disk
    for the Streamlit upload. Here the bytes already live in R2, re-encoded by
    `imaging.validate_and_normalise`, and only the row is missing.

    Returns `(id, uploaded_at)` rather than the ORM instance: the caller needs
    both after the session closes, and a detached instance would raise the
    moment anything touched a relationship.
    """
    _require_owned_trade(trade_id, user_id)
    db: Session = SessionLocal()
    try:
        record = Screenshot(
            trade_id=trade_id,
            file_path=str(file_path),
            width=width,
            height=height,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record.id, record.uploaded_at
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
