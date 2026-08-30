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
from dataclasses import dataclass
from typing import List, Optional

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
# What `imaging.validate_and_normalise` is allowed to emit. It is declared
# HERE, not in imaging.py, because `_is_final_key` has to know it and imaging
# already imports this module (the reverse import would be a cycle). Both the
# normalizer's output type and the extensions `_is_final_key` accepts are
# derived from this one set, so they cannot drift: a hardcoded ".png" here and
# a normalizer that later emits WebP would make `delete_trade_objects` SKIP
# every object of the new format, leaving private images in the bucket after a
# trade deletion with nothing left pointing at them.
NORMALISED_CONTENT_TYPE = "image/png"
NORMALISED_CONTENT_TYPES = frozenset({NORMALISED_CONTENT_TYPE})
FINAL_KEY_EXTENSIONS = frozenset(
    ALLOWED_CONTENT_TYPES[content_type] for content_type in NORMALISED_CONTENT_TYPES
)
# What a quarantine key may end in: whatever the browser was allowed to PUT.
UPLOAD_KEY_EXTENSIONS = frozenset(ALLOWED_CONTENT_TYPES.values())
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PRESIGN_TTL_SECONDS = 300
_log = logging.getLogger(__name__)


class UploadRejected(ValueError):
    """Stable refusal for an invalid object in the upload quarantine."""


class UploadMissing(LookupError):
    """The named quarantine object is not there to promote.

    Distinct from `UploadRejected`, which means "these bytes are not an image
    we accept". This one means there are no bytes at all: a stale key, a
    second finalize of one already promoted and discarded, or a retry after
    the upload was abandoned. It is an ordinary thing for a client to hit,
    so the caller can answer it with something the trader can act on instead
    of letting a botocore error surface as a server fault.
    """


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


def _is_scoped_key(key: object, prefix: str, allowed_extensions: frozenset) -> bool:
    """Whether `key` is exactly `<prefix><uuid4>.<ext>` and nothing else.

    A `startswith` check alone is NOT enough, and this is the single reason
    this helper exists. Every key the server builds ends in one `<uuid>.<ext>`
    segment, so anything the client sends back that does not is forged — and
    the forgery that matters is a relative one:

        quarantine/u/<me>/t/<mine>/../../../../u/<victim>/t/9/<uuid>.png

    That passes the caller's own prefix while naming another tenant's object.
    botocore transmits the `..` segments literally and unencoded, so whether
    it resolves is entirely up to how the object store treats a key: on S3 a
    key is an opaque string and the traversal is inert, but that is a property
    of the backend, not of us, and it must not be what stands between an
    attacker and a cross-tenant read. Requiring the remainder to be a single
    filename segment removes the question: no separators, so no dot segments,
    so nothing to resolve.
    """
    if not isinstance(key, str) or not key.startswith(prefix):
        return False
    remainder = key[len(prefix) :]
    if "/" in remainder or "\\" in remainder:
        return False
    stem, dot, extension = remainder.rpartition(".")
    if not dot or extension not in allowed_extensions:
        return False
    try:
        uuid.UUID(stem)
    except (ValueError, AttributeError):
        return False
    return True


def _is_final_key(key: object, user_id: int, trade_id: int) -> bool:
    return _is_scoped_key(
        key,
        _expected_prefix(user_id, trade_id, quarantine=False),
        FINAL_KEY_EXTENSIONS,
    )


def _is_quarantine_key(key: object, user_id: int, trade_id: int) -> bool:
    """The same shape discipline as a final key, one prefix up.

    The extension set is wider because quarantine holds what the browser sent
    (PNG, JPEG or WebP) rather than what normalisation emits, and it is derived
    from the same declaration `presign_upload` signs against so the two cannot
    drift apart.
    """
    return _is_scoped_key(
        key,
        _expected_prefix(user_id, trade_id, quarantine=True),
        UPLOAD_KEY_EXTENSIONS,
    )


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


def _discard_object(client, bucket: str, key: str) -> None:
    try:
        client.delete_object(Bucket=bucket, Key=key)
    except Exception:  # noqa: BLE001 — cleanup is best effort, but observable
        _log.warning("Could not remove an object after an upload operation")


def finalize_upload(user_id: int, trade_id: int, upload_key: str) -> dict:
    """Validate an R2 upload and promote only fresh normalized PNG bytes.

    The original object is in a non-downloadable quarantine prefix. It is
    discarded on every exit — success, content rejection, and object-store
    fault alike — because nothing else in the system can name it afterwards.
    Callers may persist only the returned final key in ``screenshots.file_path``.
    """
    owner = require_user_id(user_id)
    if not _owns_trade(owner, trade_id):
        raise PermissionError("trade not found")
    if not _is_quarantine_key(upload_key, owner, trade_id):
        raise PermissionError("upload not found")

    cfg = r2_config()
    bucket = cfg["bucket"]
    client = _client()
    final_key = None
    try:
        try:
            response = client.get_object(Bucket=bucket, Key=upload_key)
        except Exception as exc:  # noqa: BLE001 — classified, then re-raised
            if _is_already_gone(exc):
                raise UploadMissing("the upload is no longer available") from exc
            raise
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
            extension = upload_key.rpartition(".")[2]
            expected_content_type = next(
                content_type
                for content_type, configured_extension in ALLOWED_CONTENT_TYPES.items()
                if configured_extension == extension
            )
            normalized, content_type, width, height = validate_and_normalise(
                data, expected_content_type=expected_content_type
            )
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
    except Exception:  # noqa: BLE001 — cleanup on EVERY exit, then re-raise
        # Not just the rejection path. A `get_object` or `put_object` fault
        # would otherwise skip both the rejection discard and the success
        # discard, and nothing else in the system can ever name that object
        # again: quarantine has no `screenshots` row, so `delete_trade_objects`
        # cannot see it, and only an explicit `abandon_upload` from a client
        # that has already errored out could clear it. This is the one path
        # where nothing sweeps, so it sweeps itself.
        # A PUT can persist an object and then lose the response. Because the
        # destination key was chosen locally, try to remove that possible
        # orphan as well as quarantine before surfacing the ambiguous fault.
        if final_key is not None:
            _discard_object(client, bucket, final_key)
        _discard_object(client, bucket, upload_key)
        raise

    _discard_object(client, bucket, upload_key)
    return {
        "key": final_key,
        "content_type": content_type,
        "width": width,
        "height": height,
    }


def abandon_upload(user_id: int, trade_id: int, upload_key: str) -> bool:
    """Drop a quarantine object the trader chose not to keep.

    The supplied key is a claim. Ownership of the trade is checked and the
    caller's own quarantine prefix is re-derived, so a well-formed key naming
    another owner is refused before any delete is issued — nothing downstream
    would catch it, because a delete of an arbitrary key succeeds.

    A FINAL key is refused too: it does not sit under the quarantine prefix,
    and a promoted object is a screenshot the trader kept. Idempotent — an
    object that is already gone is the desired end state, so a second abandon
    is success rather than an error a retrying client can never clear.
    """
    owner = require_user_id(user_id)
    if not _owns_trade(owner, trade_id):
        raise PermissionError("upload not found")
    if not _is_quarantine_key(upload_key, owner, trade_id):
        raise PermissionError("upload not found")

    _client().delete_object(Bucket=r2_config()["bucket"], Key=upload_key)
    return True


def delete_owned_object(user_id: int, trade_id: int, key: str) -> bool:
    """Delete one normalized object only when its owner/trade prefix matches."""
    owner = require_user_id(user_id)
    if not _is_final_key(key, owner, trade_id):
        return False
    _client().delete_object(Bucket=r2_config()["bucket"], Key=key)
    return True


@dataclass
class ObjectCleanup:
    """What a trade's object cleanup actually managed to do.

    Three lists rather than a bool because the caller has to tell three
    different situations apart: objects removed, objects that could not be
    removed, and rows naming no object this owner is entitled to delete.
    A bare `True` would let a caller report "your screenshots are gone" over
    a bucket that still holds them.
    """

    deleted: List[str]
    failed: List[str]
    skipped: List[str]

    @property
    def complete(self) -> bool:
        """True only when NOTHING was left behind — failed or skipped.

        `skipped` counts too, deliberately. A skipped key is a stored
        `file_path` this owner is not entitled to delete: a corrupted row
        pointing at another tenant's object, a legacy local path, or — the
        case that makes this load-bearing — a key `_is_final_key` refuses
        because its filename is not `<uuid>.png`. That gate hardcodes one
        output format, so the day `finalize_upload` learns to emit a second
        (WebP, AVIF), every existing key of that format silently becomes a
        skip. Under `not self.failed` alone the caller would answer 204 —
        "your screenshots are gone" — over a bucket that still holds them.
        That is the false privacy assurance the whole three-list design
        exists to prevent, so it must not turn on which list the leftover
        landed in.

        The cost is accepted knowingly: a trade whose screenshot rows carry
        unresolvable paths can no longer be deleted through the API until
        those rows are repaired. A blocked, visible delete is recoverable;
        a silent orphan with nothing left pointing at it is not.
        """
        return not self.failed and not self.skipped


# R2 and S3 both answer a delete of an absent key with success, but a proxy or
# a partially-applied earlier attempt can still surface one of these. A missing
# object IS the desired end state, so it counts as deleted rather than failed —
# that is what makes a retry able to finish a half-done cleanup.
_ALREADY_GONE_CODES = frozenset({"NoSuchKey", "NotFound", "404"})


def _owned_object_keys(user_id: int, trade_id: int) -> List[str]:
    """The stored keys for one trade, resolved through its owner.

    `Screenshot` carries no `user_id`, so `trade_id -> trades.user_id` is the
    only ownership signal that exists. Querying screenshots by id alone would
    be a cross-tenant delete, so the join is not an optimisation — it is the
    entire guard, and it stays in the WHERE clause where it cannot be skipped.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(Screenshot.file_path)
            .join(Trade, Trade.id == Screenshot.trade_id)
            .filter(Screenshot.trade_id == trade_id, Trade.user_id == user_id)
            .all()
        )
    finally:
        db.close()
    return [row[0] for row in rows]


def delete_trade_objects(user_id: int, trade_id: int) -> ObjectCleanup:
    """Remove every R2 object belonging to one of this user's trades.

    Owner-scoped, idempotent and failure-aware, because the caller deletes a
    trade on the strength of it:

    * **Owner-scoped** — keys come from `_owned_object_keys`, and each is
      re-checked against this owner's prefix, so a row whose `file_path` was
      corrupted to point at another tenant's object is skipped rather than
      deleted on their behalf.
    * **Idempotent** — an object that is already gone is success, so a retry
      after a partial failure converges instead of erroring forever.
    * **Failure-aware** — what could not be removed comes back in `failed`.
      Deleting the `screenshots` row is what erases the only record of the
      key (the FK cascades), so a caller that dropped the row after a failed
      cleanup would strand the object permanently.

    Never raises for an object-store fault: the caller needs the partial
    result to decide what to tell the trader, and an exception would throw it
    away.
    """
    owner = require_user_id(user_id)
    deleted: List[str] = []
    failed: List[str] = []
    skipped: List[str] = []

    keys = _owned_object_keys(owner, trade_id)
    if not keys:
        # Nothing owned here — either no screenshots, or not this user's trade.
        # Deliberately before `_client()`: a cross-owner call must not so much
        # as construct a connection to the object store.
        return ObjectCleanup(deleted=deleted, failed=failed, skipped=skipped)

    bucket = r2_config()["bucket"]
    client = _client()
    for key in keys:
        if not _is_final_key(key, owner, trade_id):
            # A legacy local path, or a row pointing outside this owner's
            # prefix. Neither names an object we may delete.
            skipped.append(key)
            continue
        try:
            client.delete_object(Bucket=bucket, Key=key)
            deleted.append(key)
        except Exception as exc:  # noqa: BLE001 — partial results beat raising
            if _is_already_gone(exc):
                deleted.append(key)
                continue
            _log.warning(
                "Could not remove a stored screenshot for trade %s", int(trade_id)
            )
            failed.append(key)

    return ObjectCleanup(deleted=deleted, failed=failed, skipped=skipped)


def _is_already_gone(exc: Exception) -> bool:
    """Whether this failure means the object is absent, which is the goal."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    code = str(response.get("Error", {}).get("Code", ""))
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in _ALREADY_GONE_CODES or status == 404
