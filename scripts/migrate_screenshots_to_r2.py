"""Move one owner's legacy local screenshots into R2. Owner-run; dry-run by default.

Object first, row second: the row is rewritten to the R2 key only after the
upload has been confirmed by R2 and its stored size matched against the bytes sent. A
failure leaves the row naming the local file, so a retry converges and nothing
is lost. The local file is never deleted by this script.

Only files inside ``screenshot_service.SCREENSHOTS_DIR``, named for their own
trade (``<trade_id>_*``), belonging to ``--owner``, and passing the same image
validation/re-encoding boundary as browser uploads are migrated. Remote ``http(s)``
references, path escapes, another trade's file and invalid images are skipped;
missing files are reported, never raised.

PNG only, deliberately: ``storage._is_final_key`` accepts exactly the extensions
``imaging`` is allowed to emit (``FINAL_KEY_EXTENSIONS``). A key ending ``.jpg``
would therefore be unreadable to the serving path and — worse — invisible to
``delete_trade_objects``, leaving a private image in the bucket after a trade or
account deletion. A legacy JPEG/WebP is reported as ``skipped`` rather than
stored under a key the rest of the system does not recognise.

    python -m scripts.migrate_screenshots_to_r2 --owner 42          # report only
    python -m scripts.migrate_screenshots_to_r2 --owner 42 --apply  # upload + rewrite
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from src.tradelens.api import imaging, storage
from src.tradelens.db.models import Screenshot, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import screenshot_service
from src.tradelens.services.ownership import require_user_id

_log = logging.getLogger(__name__)

_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


@dataclass
class MigrationReport:
    """Screenshot ids by outcome. `failed` is the only non-benign bucket."""

    migrated: List[int] = field(default_factory=list)
    missing: List[int] = field(default_factory=list)
    skipped: List[int] = field(default_factory=list)
    failed: List[int] = field(default_factory=list)


def _content_type(head: bytes) -> Optional[str]:
    """The image type of these leading bytes, or None if they are not an image."""
    for magic, kind in _MAGIC:
        if head.startswith(magic):
            return kind
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def _local_file(raw: str, trade_id: int) -> Optional[Path]:
    """The resolved file if `raw` is this trade's legacy file inside the root, else None.

    `resolve()` follows symlinks before the containment check, so a link inside
    the root that points outside it is rejected like any other escape.
    """
    if "://" in raw:
        return None
    root = Path(screenshot_service.SCREENSHOTS_DIR).resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = Path(screenshot_service.PROJECT_ROOT) / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if root not in resolved.parents:
        return None
    if not resolved.name.startswith("{}_".format(int(trade_id))):
        return None
    return resolved


def _upload_and_verify(body: bytes, key: str, content_type: str) -> bool:
    """Put the object, then confirm R2 reports the exact stored byte length."""
    client = storage._client()
    bucket = storage.r2_config()["bucket"]
    client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)
    head = client.head_object(Bucket=bucket, Key=key)
    return int(head.get("ContentLength", -1)) == len(body)


def _discard_uploaded(owner: int, trade_id: int, key: str) -> None:
    """Best-effort rollback for an object no database row references."""
    try:
        storage.delete_owned_object(owner, trade_id, key)
    except Exception:  # noqa: BLE001 — the failed migration remains visible
        _log.warning("Unreferenced screenshot object %s could not be removed", key)


def _reference_points_to(shot_id: int, key: str) -> Optional[bool]:
    """Resolve an ambiguous commit: True/False, or None if DB is unavailable."""
    db = SessionLocal()
    try:
        value = db.query(Screenshot.file_path).filter(Screenshot.id == shot_id).scalar()
        return value == key
    except Exception:  # noqa: BLE001 — ambiguity must not delete referenced bytes
        return None
    finally:
        db.close()


def migrate_owner(owner: int, *, apply: bool) -> MigrationReport:
    """Report (and with `apply`, perform) the migration of one owner's screenshots."""
    owner = require_user_id(owner)
    report = MigrationReport()
    db = SessionLocal()
    try:
        rows = (
            db.query(Screenshot.id, Screenshot.trade_id, Screenshot.file_path)
            .join(Trade, Trade.id == Screenshot.trade_id)
            .filter(Trade.user_id == owner)
            .order_by(Screenshot.id)
            .all()
        )
    finally:
        db.close()

    for shot_id, trade_id, raw in rows:
        if storage._is_final_key(raw, owner, trade_id):
            continue  # already this owner's R2 object — idempotent re-run
        path = _local_file(raw, trade_id)
        if path is None:
            report.skipped.append(shot_id)
            continue
        if not path.exists():
            report.missing.append(shot_id)
            continue
        try:
            if path.stat().st_size > storage.MAX_UPLOAD_BYTES:
                report.skipped.append(shot_id)
                continue
            body = path.read_bytes()
        except OSError:
            report.missing.append(shot_id)
            continue
        kind = _content_type(body[:16])
        if kind not in storage.NORMALISED_CONTENT_TYPES:
            _log.warning("Screenshot %s is not a storable image; skipped", int(shot_id))
            report.skipped.append(shot_id)
            continue
        try:
            body, kind, width, height = imaging.validate_and_normalise(
                body, expected_content_type=kind
            )
        except imaging.ImageRejected:
            _log.warning("Screenshot %s is not a valid image; skipped", int(shot_id))
            report.skipped.append(shot_id)
            continue
        if not apply:
            report.migrated.append(shot_id)
            continue
        key = storage.build_object_key(owner, trade_id, kind)
        try:
            verified = _upload_and_verify(body, key, kind)
        except Exception:  # noqa: BLE001 — a store fault is a reported failure
            _log.warning("Screenshot %s could not be uploaded", int(shot_id))
            verified = False
        if not verified:
            # The row still names the local file, which still exists. Retry converges.
            _log.warning("Screenshot %s did not verify in the store", int(shot_id))
            _discard_uploaded(owner, trade_id, key)
            report.failed.append(shot_id)
            continue
        db = SessionLocal()
        write_failed = False
        try:
            updated = (
                db.query(Screenshot)
                .filter(
                    Screenshot.id == shot_id,
                    Screenshot.trade_id == trade_id,
                    Screenshot.file_path == raw,
                    Screenshot.trade.has(Trade.user_id == owner),
                )
                .update(
                    {
                        Screenshot.file_path: key,
                        Screenshot.width: width,
                        Screenshot.height: height,
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
        except Exception:  # noqa: BLE001 — report and make a safe recovery decision
            write_failed = True
            db.rollback()
            _log.warning(
                "Screenshot %s database reference could not be updated", shot_id
            )
        finally:
            db.close()
        if write_failed:
            committed = _reference_points_to(shot_id, key)
            if committed is True:
                report.migrated.append(shot_id)
            else:
                if committed is False:
                    _discard_uploaded(owner, trade_id, key)
                report.failed.append(shot_id)
            continue
        if updated == 1:
            report.migrated.append(shot_id)
        else:
            _discard_uploaded(owner, trade_id, key)
            report.failed.append(shot_id)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--owner", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    report = migrate_owner(args.owner, apply=args.apply)
    print(
        "migrated=%d missing=%d skipped=%d failed=%d apply=%s"
        % (
            len(report.migrated),
            len(report.missing),
            len(report.skipped),
            len(report.failed),
            args.apply,
        )
    )
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
