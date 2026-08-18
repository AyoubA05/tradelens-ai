"""Cloudflare R2 adapter for chart screenshots.

The bucket is private: no public access, no listing, no website endpoint. Bytes
move directly between the browser and R2 using short-lived presigned URLs, which
is the one exception to "the browser only talks to Next.js".

Because a presigned upload arrives without passing through application code, the
object is untrusted until `imaging.validate_and_normalise` has seen it.

A presigned PUT's policy binds ContentType only. It does NOT bind ContentLength:
on an S3-compatible presigned PUT, ContentLength constrains an *exact* size, not
a maximum, so binding it to MAX_UPLOAD_BYTES would reject every upload that is
not exactly that size. A true maximum needs `generate_presigned_post` with a
`content-length-range` condition, and R2's support for presigned POST is not
verified here. `max_bytes` is returned as advisory information for the client;
the real size gate is enforced server-side in `imaging.validate_and_normalise`.
"""

from __future__ import annotations

import uuid
import logging
from typing import Optional

import boto3
from botocore.config import Config

from src.tradelens.api.config import r2_config
from src.tradelens.db.models import Screenshot, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ownership import require_user_id

# SVG is deliberately absent: it is script-bearing markup that browsers execute.
ALLOWED_CONTENT_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PRESIGN_TTL_SECONDS = 300
_log = logging.getLogger(__name__)


class UploadRejected(ValueError):
    """Stable refusal for an invalid object in the upload quarantine."""


def _client():
    cfg = r2_config()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{cfg['account_id']}.r2.cloudflarestorage.com",
        aws_access_key_id=cfg["access_key_id"],
        aws_secret_access_key=cfg["secret_access_key"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def build_object_key(user_id: int, trade_id: int, content_type: str) -> str:
    """Where an upload lands. Chosen by the server, always.

    The client's filename is never used: a user-supplied component in a key is a
    path-traversal and overwrite primitive. The uuid4 makes the key unguessable
    even to someone who knows both ids.
    """
    owner = require_user_id(user_id)
    extension = ALLOWED_CONTENT_TYPES.get(content_type)
    if extension is None:
        raise ValueError(f"unsupported content type: {content_type!r}")
    return f"u/{owner}/t/{int(trade_id)}/{uuid.uuid4()}.{extension}"


def _build_quarantine_key(user_id: int, trade_id: int, content_type: str) -> str:
    return f"quarantine/{build_object_key(user_id, trade_id, content_type)}"


def _expected_prefix(user_id: int, trade_id: int, *, quarantine: bool) -> str:
    base = f"u/{user_id}/t/{int(trade_id)}/"
    return f"quarantine/{base}" if quarantine else base


def _is_final_key(key: object, user_id: int, trade_id: int) -> bool:
    if not isinstance(key, str) or not key.startswith(
        _expected_prefix(user_id, trade_id, quarantine=False)
    ):
        return False
    filename = key.rsplit("/", 1)[-1]
    if not filename.endswith(".png"):
        return False
    try:
        uuid.UUID(filename[:-4])
    except (ValueError, AttributeError):
        return False
    return True


def _owns_trade(user_id: int, trade_id: int) -> bool:
    db = SessionLocal()
    try:
        return (
            db.query(Trade.id)
            .filter(Trade.id == trade_id, Trade.user_id == user_id)
            .first()
            is not None
        )
    finally:
        db.close()


def presign_upload(user_id: int, trade_id: int, content_type: str) -> dict:
    """A short-lived PUT URL for one specific object.

    ContentType is bound INTO the policy rather than merely validated here: a
    check in application code is advice, a signed policy is a rule R2 itself
    enforces on the upload. ContentLength is NOT bound (see module docstring);
    `max_bytes` is advisory, and the real size gate lives in imaging.py.
    """
    owner = require_user_id(user_id)
    if not _owns_trade(owner, trade_id):
        raise PermissionError("trade not found")

    # Direct uploads land in a namespace that is never downloadable. Only
    # `finalize_upload` can promote decoded/re-encoded bytes to `u/...`.
    key = _build_quarantine_key(owner, trade_id, content_type)
    url = _client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": r2_config()["bucket"],
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=PRESIGN_TTL_SECONDS,
    )
    return {
        "url": url,
        "key": key,
        "expires_in": PRESIGN_TTL_SECONDS,
        "max_bytes": MAX_UPLOAD_BYTES,
    }


def presign_download(user_id: int, screenshot_id: int) -> Optional[str]:
    """A short-lived GET URL, or None if this user may not see the object.

    Ownership is resolved through the screenshot's trade before anything is
    signed. Returning None rather than raising means "no such screenshot for
    you" — a missing object and someone else's object are indistinguishable.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = (
            db.query(Screenshot.file_path, Screenshot.trade_id)
            .join(Trade, Trade.id == Screenshot.trade_id)
            .filter(Screenshot.id == screenshot_id, Trade.user_id == owner)
            .first()
        )
    finally:
        db.close()
    if row is None:
        return None
    if not _is_final_key(row[0], owner, row[1]):
        return None

    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": r2_config()["bucket"], "Key": row[0]},
        ExpiresIn=PRESIGN_TTL_SECONDS,
    )


def _discard_quarantine(client, bucket: str, key: str) -> None:
    try:
        client.delete_object(Bucket=bucket, Key=key)
    except Exception:  # noqa: BLE001 — cleanup is best effort, but observable
        _log.warning("Could not remove an object from the upload quarantine")


def finalize_upload(user_id: int, trade_id: int, upload_key: str) -> dict:
    """Validate an R2 upload and promote only fresh normalized PNG bytes.

    The original object is in a non-downloadable quarantine prefix. It is
    discarded on both successful validation and content rejection. Callers may
    persist only the returned final key in ``screenshots.file_path``.
    """
    owner = require_user_id(user_id)
    if not _owns_trade(owner, trade_id):
        raise PermissionError("trade not found")
    prefix = _expected_prefix(owner, trade_id, quarantine=True)
    if not isinstance(upload_key, str) or not upload_key.startswith(prefix):
        raise PermissionError("upload not found")

    cfg = r2_config()
    bucket = cfg["bucket"]
    client = _client()
    try:
        response = client.get_object(Bucket=bucket, Key=upload_key)
        body = response.get("Body")
        try:
            length = response.get("ContentLength")
            if (
                body is None
                or not isinstance(length, int)
                or length <= 0
                or length > MAX_UPLOAD_BYTES
            ):
                raise UploadRejected("not a supported image")
            data = body.read(MAX_UPLOAD_BYTES + 1)
            if not data or len(data) > MAX_UPLOAD_BYTES:
                raise UploadRejected("not a supported image")
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()

        from src.tradelens.api.imaging import ImageRejected, validate_and_normalise

        try:
            normalized, content_type, width, height = validate_and_normalise(data)
        except ImageRejected as exc:
            raise UploadRejected("not a supported image") from exc

        final_key = build_object_key(owner, trade_id, content_type)
        client.put_object(
            Bucket=bucket,
            Key=final_key,
            Body=normalized,
            ContentType=content_type,
            CacheControl="private, no-store",
        )
    except UploadRejected:
        _discard_quarantine(client, bucket, upload_key)
        raise

    _discard_quarantine(client, bucket, upload_key)
    return {
        "key": final_key,
        "content_type": content_type,
        "width": width,
        "height": height,
    }


def delete_owned_object(user_id: int, trade_id: int, key: str) -> bool:
    """Delete one normalized object only when its owner/trade prefix matches."""
    owner = require_user_id(user_id)
    if not _is_final_key(key, owner, trade_id):
        return False
    _client().delete_object(Bucket=r2_config()["bucket"], Key=key)
    return True
