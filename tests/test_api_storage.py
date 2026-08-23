import re
import io

import pytest
from PIL import Image

from src.tradelens.api import storage


def _create(data):
    from src.tradelens.services import trade_service

    return trade_service.create_trade(data, user_id=data["user_id"])


def test_keys_are_owner_scoped_and_random():
    a = storage.build_object_key(7, 12, "image/png")
    b = storage.build_object_key(7, 12, "image/png")
    assert a.startswith("u/7/t/12/")
    assert a.endswith(".png")
    assert a != b, "two uploads must never collide on one key"
    assert re.fullmatch(r"u/7/t/12/[0-9a-f-]{36}\.png", a)


def test_the_client_filename_never_reaches_the_key():
    """A user-chosen filename in a key is a path-traversal and overwrite
    primitive. The server chooses where bytes land."""
    key = storage.build_object_key(1, 1, "image/png")
    assert ".." not in key and "\\" not in key


@pytest.mark.parametrize(
    "content_type", ["image/svg+xml", "text/html", "application/pdf", ""]
)
def test_disallowed_types_are_refused(content_type):
    """SVG is script-bearing markup, not a picture."""
    with pytest.raises(ValueError):
        storage.build_object_key(1, 1, content_type)


def test_presign_refuses_a_trade_the_user_does_not_own(two_users, monkeypatch):
    a, b = two_users

    theirs = _create(
        {
            "user_id": b,
            "trade_date": "2026-08-12",
            "asset": "NQ",
            "result": "Win",
            "pnl": 1.0,
        }
    )
    monkeypatch.setattr(storage, "_client", lambda: _FakeS3())
    with pytest.raises(PermissionError):
        storage.presign_upload(a, theirs.id, "image/png")


def test_presign_upload_bounds_the_policy(two_users, monkeypatch):
    a, _ = two_users

    mine = _create(
        {
            "user_id": a,
            "trade_date": "2026-08-12",
            "asset": "NQ",
            "result": "Win",
            "pnl": 1.0,
        }
    )
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    result = storage.presign_upload(a, mine.id, "image/png")

    assert result["key"].startswith(f"quarantine/u/{a}/t/{mine.id}/")
    assert result["expires_in"] <= 300
    assert result["max_bytes"] == storage.MAX_UPLOAD_BYTES
    # Enforced in the policy, not merely checked in application code.
    assert fake.last_params["ContentType"] == "image/png"
    # A presigned PUT binds ContentLength to an EXACT size, not a maximum.
    # Binding it here would reject every upload that isn't exactly
    # MAX_UPLOAD_BYTES. max_bytes is returned as advisory information for
    # the client instead; the real size gate lives in imaging.py.
    assert "ContentLength" not in fake.last_params


def test_presign_download_refuses_another_users_screenshot(two_users, monkeypatch):
    a, b = two_users
    from src.tradelens.db.models import Screenshot
    from src.tradelens.db.session import SessionLocal

    theirs = _create(
        {
            "user_id": b,
            "trade_date": "2026-08-12",
            "asset": "NQ",
            "result": "Win",
            "pnl": 1.0,
        }
    )
    db = SessionLocal()
    try:
        shot = Screenshot(trade_id=theirs.id, file_path="u/2/t/1/x.png")
        db.add(shot)
        db.commit()
        shot_id = shot.id
    finally:
        db.close()

    monkeypatch.setattr(storage, "_client", lambda: _FakeS3())
    assert storage.presign_download(a, shot_id) is None


def test_presign_download_refuses_a_database_row_pointing_at_another_owners_key(
    two_users, monkeypatch
):
    a, b = two_users
    from src.tradelens.db.models import Screenshot
    from src.tradelens.db.session import SessionLocal

    mine = _create(
        {
            "user_id": a,
            "trade_date": "2026-08-12",
            "asset": "NQ",
            "result": "Win",
            "pnl": 1.0,
        }
    )
    db = SessionLocal()
    try:
        shot = Screenshot(
            trade_id=mine.id,
            file_path=f"u/{b}/t/{mine.id}/foreign.png",
        )
        db.add(shot)
        db.commit()
        shot_id = shot.id
    finally:
        db.close()

    monkeypatch.setattr(storage, "_client", lambda: _FakeS3())
    assert storage.presign_download(a, shot_id) is None


def _png():
    buf = io.BytesIO()
    Image.new("RGB", (3, 2), "teal").save(buf, format="PNG")
    return buf.getvalue()


def test_finalize_reencodes_then_deletes_the_untrusted_object(two_users, monkeypatch):
    a, _ = two_users
    mine = _create(
        {
            "user_id": a,
            "trade_date": "2026-08-12",
            "asset": "NQ",
            "result": "Win",
            "pnl": 1.0,
        }
    )
    upload_key = f"quarantine/u/{a}/t/{mine.id}/deadbeef.png"
    poisoned = _png() + b"<script>payload</script>"
    fake = _FakeS3(objects={upload_key: poisoned})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    result = storage.finalize_upload(a, mine.id, upload_key)

    assert result["key"].startswith(f"u/{a}/t/{mine.id}/")
    assert result["key"].endswith(".png")
    assert b"<script>" not in fake.puts[result["key"]]["Body"]
    assert fake.puts[result["key"]]["ContentType"] == "image/png"
    assert upload_key in fake.deleted
    assert fake.bodies[upload_key].closed is True


def test_finalize_enforces_the_real_size_cap_and_discards_quarantine(
    two_users, monkeypatch
):
    a, _ = two_users
    mine = _create(
        {
            "user_id": a,
            "trade_date": "2026-08-12",
            "asset": "NQ",
            "result": "Win",
            "pnl": 1.0,
        }
    )
    upload_key = f"quarantine/u/{a}/t/{mine.id}/too-big.png"
    fake = _FakeS3(objects={upload_key: b"x" * (storage.MAX_UPLOAD_BYTES + 1)})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(storage.UploadRejected):
        storage.finalize_upload(a, mine.id, upload_key)
    assert upload_key in fake.deleted
    assert fake.puts == {}


def test_finalize_refuses_object_key_manipulation_before_touching_r2(
    two_users, monkeypatch
):
    a, b = two_users
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)
    with pytest.raises(PermissionError):
        storage.finalize_upload(a, 1, f"quarantine/u/{b}/t/1/stolen.png")
    assert fake.gets == []


def test_delete_refuses_foreign_keys_and_deletes_only_owned_final_keys(
    two_users, monkeypatch
):
    a, b = two_users
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)
    owned = f"u/{a}/t/7/00000000-0000-4000-8000-000000000000.png"
    foreign = f"u/{b}/t/7/00000000-0000-4000-8000-000000000000.png"

    assert storage.delete_owned_object(a, 7, foreign) is False
    assert storage.delete_owned_object(a, 7, owned) is True
    assert fake.deleted == [owned]


class _Body:
    def __init__(self, data):
        self.data = data
        self.closed = False

    def read(self, amount=None):
        return self.data if amount is None else self.data[:amount]

    def close(self):
        self.closed = True


class _FakeS3:
    def __init__(self, objects=None):
        self.last_params = None
        self.objects = objects or {}
        self.puts = {}
        self.deleted = []
        self.gets = []
        self.bodies = {}

    def generate_presigned_url(self, operation, Params=None, ExpiresIn=None):
        self.last_params = Params
        return f"https://r2.example/{Params['Key']}?sig=x&exp={ExpiresIn}"

    def get_object(self, Bucket=None, Key=None):
        self.gets.append(Key)
        data = self.objects[Key]
        body = _Body(data)
        self.bodies[Key] = body
        return {"ContentLength": len(data), "Body": body}

    def put_object(self, Bucket=None, Key=None, **kwargs):
        self.puts[Key] = kwargs

    def delete_object(self, Bucket=None, Key=None):
        self.deleted.append(Key)


# ------------------------------------------------- delete_trade_objects (B2)


def _screenshot(trade_id, file_path):
    from src.tradelens.db.models import Screenshot
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        shot = Screenshot(trade_id=trade_id, file_path=file_path)
        db.add(shot)
        db.commit()
        return shot.id
    finally:
        db.close()


def _client_error(code, status=400):
    from botocore.exceptions import ClientError

    return ClientError(
        {"Error": {"Code": code}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "DeleteObject",
    )


class _ExplodingS3(_FakeS3):
    """An object store that refuses to delete. Models R2 being down mid-delete."""

    def __init__(self, error=None):
        super().__init__()
        self.attempted = []
        self._error = error or _client_error("InternalError", 500)

    def delete_object(self, Bucket=None, Key=None):
        self.attempted.append(Key)
        raise self._error


def test_delete_trade_objects_removes_the_owners_objects(two_users, monkeypatch):
    a, _ = two_users
    mine = _create({"user_id": a, "trade_date": "2026-08-12", "asset": "NQ"})
    key = storage.build_object_key(a, mine.id, "image/png")
    _screenshot(mine.id, key)

    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    cleanup = storage.delete_trade_objects(a, mine.id)

    assert fake.deleted == [key]
    assert cleanup.deleted == [key]
    assert cleanup.failed == []
    assert cleanup.complete is True


def test_delete_trade_objects_issues_no_call_for_another_owners_trade(
    two_users, monkeypatch
):
    """`Screenshot` has no `user_id`: ownership exists only as
    `trade_id -> trades.user_id`. Enumerating by screenshot id would be a
    cross-tenant delete, so the join is the whole guard — and a call that
    fails it must reach the object store not at all."""
    a, b = two_users
    theirs = _create({"user_id": b, "trade_date": "2026-08-12", "asset": "NQ"})
    key = storage.build_object_key(b, theirs.id, "image/png")
    _screenshot(theirs.id, key)

    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    cleanup = storage.delete_trade_objects(a, theirs.id)

    assert fake.deleted == [], "a cross-owner cleanup must delete nothing"
    # Every list empty, not merely `deleted`: the key must never be RESOLVED.
    # Asserting only on `deleted` would pass an implementation that dropped
    # the ownership join and was saved by the per-key prefix check further
    # down — leaving the one guard that `Screenshot` has no substitute for
    # untested.
    assert cleanup.deleted == []
    assert cleanup.failed == []
    assert cleanup.skipped == []


def test_delete_trade_objects_is_idempotent_for_a_missing_object(
    two_users, monkeypatch
):
    """A missing object is success. Retries and double-clicks converge, and a
    half-finished earlier attempt stays completable."""
    a, _ = two_users
    mine = _create({"user_id": a, "trade_date": "2026-08-12", "asset": "NQ"})
    key = storage.build_object_key(a, mine.id, "image/png")
    _screenshot(mine.id, key)

    monkeypatch.setattr(
        storage, "_client", lambda: _ExplodingS3(_client_error("NoSuchKey", 404))
    )

    cleanup = storage.delete_trade_objects(a, mine.id)

    assert cleanup.failed == []
    assert cleanup.deleted == [key]
    assert cleanup.complete is True


def test_delete_trade_objects_reports_a_real_failure(two_users, monkeypatch):
    a, _ = two_users
    mine = _create({"user_id": a, "trade_date": "2026-08-12", "asset": "NQ"})
    key = storage.build_object_key(a, mine.id, "image/png")
    _screenshot(mine.id, key)

    monkeypatch.setattr(storage, "_client", lambda: _ExplodingS3())

    cleanup = storage.delete_trade_objects(a, mine.id)

    assert cleanup.failed == [key]
    assert cleanup.deleted == []
    assert cleanup.complete is False


def test_delete_trade_objects_repeats_cleanly_after_a_partial_failure(
    two_users, monkeypatch
):
    """The retryable state is the point: a failed cleanup must be finishable."""
    a, _ = two_users
    mine = _create({"user_id": a, "trade_date": "2026-08-12", "asset": "NQ"})
    key = storage.build_object_key(a, mine.id, "image/png")
    _screenshot(mine.id, key)

    monkeypatch.setattr(storage, "_client", lambda: _ExplodingS3())
    assert storage.delete_trade_objects(a, mine.id).complete is False

    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)
    assert storage.delete_trade_objects(a, mine.id).complete is True
    assert fake.deleted == [key]


def test_delete_trade_objects_skips_a_row_pointing_outside_the_owners_prefix(
    two_users, monkeypatch
):
    """A file_path that is not this owner's normalized key names no object we
    are entitled to delete — skipped, never handed to the object store."""
    a, b = two_users
    mine = _create({"user_id": a, "trade_date": "2026-08-12", "asset": "NQ"})
    foreign = f"u/{b}/t/999/{'0' * 8}-0000-0000-0000-000000000000.png"
    _screenshot(mine.id, foreign)
    _screenshot(mine.id, "data/screenshots/legacy-local-file.png")

    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    cleanup = storage.delete_trade_objects(a, mine.id)

    assert fake.deleted == []
    assert cleanup.failed == []
    assert sorted(cleanup.skipped) == sorted(
        [foreign, "data/screenshots/legacy-local-file.png"]
    )
    # NOT complete. A skip means an object may still exist that this cleanup
    # did not remove, so reporting completion would let the caller tell a
    # trader their screenshots are gone over a bucket that still holds them
    # — the same false privacy assurance a failure causes, arriving through
    # a different list. `complete` must not depend on which list it is.
    assert cleanup.complete is False


def test_cleanup_is_complete_only_when_both_failed_and_skipped_are_empty():
    """The completeness rule, stated directly.

    A mutation making `complete` ignore `skipped` is invisible to the
    end-to-end tests whenever every key happens to be a well-formed current
    key — which is every test that does not deliberately construct a legacy
    row. Pinning the rule itself is what survives that.
    """
    key = "u/1/t/2/00000000-0000-0000-0000-000000000000.png"
    assert storage.ObjectCleanup(deleted=[key], failed=[], skipped=[]).complete is True
    assert storage.ObjectCleanup(deleted=[], failed=[key], skipped=[]).complete is False
    assert storage.ObjectCleanup(deleted=[], failed=[], skipped=[key]).complete is False
    assert (
        storage.ObjectCleanup(deleted=[], failed=[key], skipped=[key]).complete is False
    )


def test_delete_trade_objects_needs_no_object_store_when_there_is_nothing_to_do(
    two_users, monkeypatch
):
    a, _ = two_users
    mine = _create({"user_id": a, "trade_date": "2026-08-12", "asset": "NQ"})

    def _explode():
        raise AssertionError("no client should be built for a trade with no objects")

    monkeypatch.setattr(storage, "_client", _explode)
    assert storage.delete_trade_objects(a, mine.id).complete is True
