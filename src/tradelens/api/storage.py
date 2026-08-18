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

    key = build_object_key(owner, trade_id, content_type)
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
            db.query(Screenshot.file_path)
            .join(Trade, Trade.id == Screenshot.trade_id)
            .filter(Screenshot.id == screenshot_id, Trade.user_id == owner)
            .first()
        )
    finally:
        db.close()
    if row is None:
        return None

    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": r2_config()["bucket"], "Key": row[0]},
        ExpiresIn=PRESIGN_TTL_SECONDS,
    )
