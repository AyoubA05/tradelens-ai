import re
import io
import uuid

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
    """The ownership join, on its own, with every later gate satisfied.

    `Screenshot` has no `user_id`, so `Trade.user_id == owner` in the query's
    join is the ONLY ownership signal this function has. `_is_final_key` then
    happens to re-encode the caller's id in the expected prefix, which means
    a malformed or foreign-looking key is refused whoever asks — and a test
    built on one such key passes with the join deleted, defending nothing.

    So the key here is deliberately well-formed *for the caller*:
    `u/{caller}/t/{trade_id}/{uuid}.png` clears `_is_final_key` completely,
    leaving the join as the only thing that can refuse it. Remove
    `Trade.user_id == owner` and this test fails, which is the point.
    """
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
        shot = Screenshot(
            trade_id=theirs.id,
            file_path=f"u/{a}/t/{theirs.id}/{uuid.uuid4()}.png",
        )
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
            # Well-formed but for the WRONG owner prefix: this is the
            # `_is_final_key` gate's own case, distinct from the ownership
            # join above — the trade really is this caller's.
            file_path=f"u/{b}/t/{mine.id}/{uuid.uuid4()}.png",
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


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (3, 2), "teal").save(buf, format="JPEG")
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
    upload_key = (
        f"quarantine/u/{a}/t/{mine.id}/11111111-1111-4111-8111-111111111111.png"
    )
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


def test_finalize_rejects_bytes_that_do_not_match_the_presigned_content_type(
    two_users, monkeypatch
):
    """The signed Content-Type is a claim the decoded image must corroborate.

    A PNG presign produces a ``.png`` quarantine key. Uploading JPEG bytes
    with the signed ``image/png`` header must not become acceptable merely
    because JPEG is independently allowlisted; otherwise MIME/extension
    binding exists in the signature but is not enforced by finalization.
    """
    a, _ = two_users
    mine = _trade_for(a)
    upload_key = (
        f"quarantine/u/{a}/t/{mine.id}/" "12121212-1212-4212-8212-121212121212.png"
    )
    fake = _FakeS3(objects={upload_key: _jpeg()})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(storage.UploadRejected):
        storage.finalize_upload(a, mine.id, upload_key)

    assert fake.puts == {}
    assert upload_key in fake.deleted


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
    upload_key = (
        f"quarantine/u/{a}/t/{mine.id}/22222222-2222-4222-8222-222222222222.png"
    )
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
        storage.finalize_upload(
            a, 1, f"quarantine/u/{b}/t/1/33333333-3333-4333-8333-333333333333.png"
        )
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


# ------------------------------------------------ final-key extensions (B4)


def test_final_key_extensions_are_derived_from_what_normalisation_emits():
    """`_is_final_key` must accept exactly what `finalize_upload` can write.

    A hardcoded `.png` and a normalizer that later emits something else drift
    apart silently, and the drift is a privacy tail: `delete_trade_objects`
    SKIPS a key `_is_final_key` refuses, so every object of the new format
    survives a trade deletion.
    """
    assert storage.FINAL_KEY_EXTENSIONS == {
        storage.ALLOWED_CONTENT_TYPES[ct] for ct in storage.NORMALISED_CONTENT_TYPES
    }
    for extension in storage.FINAL_KEY_EXTENSIONS:
        key = f"u/3/t/9/00000000-0000-4000-8000-000000000000.{extension}"
        assert storage._is_final_key(key, 3, 9) is True


def test_an_extension_normalisation_never_emits_is_not_a_final_key():
    """`image/jpeg` is an accepted UPLOAD type but never a normalized OUTPUT.

    So a stored `.jpg` final key names something `finalize_upload` cannot have
    written, and must not be treated as this owner's object to delete.
    """
    unexpected = (
        set(storage.ALLOWED_CONTENT_TYPES.values()) - storage.FINAL_KEY_EXTENSIONS
    )
    assert unexpected, "the test needs at least one non-emitted extension"
    for extension in unexpected:
        key = f"u/3/t/9/00000000-0000-4000-8000-000000000000.{extension}"
        assert storage._is_final_key(key, 3, 9) is False


def test_normalisation_only_ever_emits_a_declared_content_type():
    """The other half of the single source: what imaging actually returns."""
    from src.tradelens.api.imaging import validate_and_normalise

    _, content_type, _, _ = validate_and_normalise(_png())
    assert content_type in storage.NORMALISED_CONTENT_TYPES


def test_delete_trade_objects_reports_an_unemittable_extension_as_incomplete(
    two_users, monkeypatch
):
    """A key with an extension normalisation never emits is a SKIP, and a skip
    makes the cleanup incomplete — the caller must not answer "your
    screenshots are gone" over a bucket that still holds them."""
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
    stray = f"u/{a}/t/{mine.id}/00000000-0000-4000-8000-000000000000.jpg"
    _screenshot(mine.id, stray)
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    cleanup = storage.delete_trade_objects(a, mine.id)

    assert cleanup.skipped == [stray]
    assert fake.deleted == []
    assert cleanup.complete is False


# ------------------------------------------------------ abandon_upload (B3)


def test_abandon_removes_an_owned_quarantine_object(two_users, monkeypatch):
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
    key = f"quarantine/u/{a}/t/{mine.id}/00000000-0000-4000-8000-000000000000.png"
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    assert storage.abandon_upload(a, mine.id, key) is True
    assert fake.deleted == [key]
    # Idempotent: the object being gone already IS the desired end state.
    assert storage.abandon_upload(a, mine.id, key) is True


def test_abandon_refuses_a_quarantine_key_naming_another_owner(two_users, monkeypatch):
    """Ownership, not malformed input, is what refuses this.

    The trade IS the caller's and the key is perfectly well-formed — it simply
    names user `b`'s quarantine prefix. Nothing downstream can reject it, so
    the prefix re-derivation is the only thing standing between a forged key
    and a cross-tenant delete.
    """
    a, b = two_users
    mine = _create(
        {
            "user_id": a,
            "trade_date": "2026-08-12",
            "asset": "NQ",
            "result": "Win",
            "pnl": 1.0,
        }
    )
    forged = f"quarantine/u/{b}/t/{mine.id}/00000000-0000-4000-8000-000000000000.png"
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(PermissionError):
        storage.abandon_upload(a, mine.id, forged)
    assert fake.deleted == [], "a refused key must issue no delete call at all"


def test_abandon_never_touches_a_final_key(two_users, monkeypatch):
    """Abandon exists to drop quarantine. A final key is a promoted, recorded
    object; deleting it here would erase a screenshot the trader kept."""
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
    final = f"u/{a}/t/{mine.id}/00000000-0000-4000-8000-000000000000.png"
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(PermissionError):
        storage.abandon_upload(a, mine.id, final)
    assert fake.deleted == []


def test_abandon_refuses_a_trade_the_caller_does_not_own(two_users, monkeypatch):
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
    key = f"quarantine/u/{a}/t/{theirs.id}/00000000-0000-4000-8000-000000000000.png"
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(PermissionError):
        storage.abandon_upload(a, theirs.id, key)
    assert fake.deleted == []


# ------------------------------------------- recording a promoted object (B2)


def test_record_object_screenshot_writes_a_row_for_the_owner(two_users):
    from src.tradelens.services import screenshot_service

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
    key = f"u/{a}/t/{mine.id}/00000000-0000-4000-8000-000000000000.png"

    shot_id, uploaded_at = screenshot_service.record_object_screenshot(
        mine.id, key, user_id=a, width=3, height=2
    )
    assert uploaded_at

    from src.tradelens.db.models import Screenshot
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = db.query(Screenshot).filter(Screenshot.id == shot_id).one()
        assert row.file_path == key
        assert (row.width, row.height) == (3, 2)
        assert row.uploaded_at
    finally:
        db.close()


def test_record_object_screenshot_refuses_another_owners_trade(two_users):
    """The trade belongs to `b` and the key is well-formed for `a`, so the
    ownership lookup is the only thing that can refuse this."""
    from src.tradelens.services import screenshot_service

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
    key = f"u/{a}/t/{theirs.id}/00000000-0000-4000-8000-000000000000.png"

    with pytest.raises(PermissionError):
        screenshot_service.record_object_screenshot(
            theirs.id, key, user_id=a, width=3, height=2
        )

    from src.tradelens.db.models import Screenshot
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        assert db.query(Screenshot).count() == 0
    finally:
        db.close()


# --------------------------------------- quarantine key shape and sweeping (M)


def _trade_for(user_id):
    return _create(
        {
            "user_id": user_id,
            "trade_date": "2026-08-12",
            "asset": "NQ",
            "result": "Win",
            "pnl": 1.0,
        }
    )


TRAVERSAL_SUFFIX = "../../../../u/999999/t/9/00000000-0000-4000-8000-000000000000.png"


@pytest.mark.parametrize(
    "suffix",
    [
        TRAVERSAL_SUFFIX,
        r"..\..\u\999\t\9\00000000-0000-4000-8000-000000000000.png",
        "%2e%2e%2f%2e%2e%2fu%2f999%2ft%2f9%2f00000000-0000-4000-8000-000000000000.png",
        "%252e%252e%252f00000000-0000-4000-8000-000000000000.png",
        "..\u2215..\u221500000000-0000-4000-8000-000000000000.png",
        "..\uff0f..\uff0f00000000-0000-4000-8000-000000000000.png",
        "./00000000-0000-4000-8000-000000000000.png",
        "00000000-0000-4000-8000-000000000000.png/..",
        "00000000-0000-4000-8000-000000000000.png?ignored=1",
        "00000000-0000-4000-8000-000000000000.png#fragment",
    ],
)
def test_quarantine_key_rejects_traversal_and_encoding_variants(suffix):
    key = f"quarantine/u/7/t/12/{suffix}"
    assert storage._is_quarantine_key(key, 7, 12) is False


def test_finalize_refuses_a_traversal_key_under_the_callers_own_prefix(
    two_users, monkeypatch
):
    """A `startswith` gate is not a gate.

    The key begins with the caller's own quarantine prefix, so a prefix check
    passes it, and the trade is the caller's, so ownership passes it too. What
    follows the prefix walks back out into another tenant's namespace, and
    botocore sends the `..` segments literally: whether they resolve is the
    object store's decision, not ours. Nothing may be read, written or deleted
    on the strength of it.
    """
    a, _ = two_users
    mine = _trade_for(a)
    forged = f"quarantine/u/{a}/t/{mine.id}/{TRAVERSAL_SUFFIX}"
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(PermissionError):
        storage.finalize_upload(a, mine.id, forged)

    assert fake.gets == [], "a traversal key must never be read from the bucket"
    assert fake.puts == {}
    assert fake.deleted == []


def test_abandon_refuses_a_traversal_key_under_the_callers_own_prefix(
    two_users, monkeypatch
):
    """Same forgery, and here a delete of an arbitrary key would just succeed."""
    a, _ = two_users
    mine = _trade_for(a)
    forged = f"quarantine/u/{a}/t/{mine.id}/{TRAVERSAL_SUFFIX}"
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(PermissionError):
        storage.abandon_upload(a, mine.id, forged)

    assert fake.deleted == [], "a refused key must issue no delete at all"


def test_finalize_refuses_the_callers_own_prefix_naming_another_owners_trade(
    two_users, monkeypatch
):
    """Only `_owns_trade` can refuse this shape.

    The key is under the CALLER's own `u/<me>/` prefix and is perfectly
    well-formed, so re-deriving the prefix passes it — the trade id inside it
    belongs to someone else. Remove the `_owns_trade` check from
    `finalize_upload` and this call reads and promotes bytes for a trade the
    caller has no claim to.
    """
    a, b = two_users
    theirs = _trade_for(b)
    key = f"quarantine/u/{a}/t/{theirs.id}/00000000-0000-4000-8000-000000000000.png"
    fake = _FakeS3(objects={key: _png()})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(PermissionError):
        storage.finalize_upload(a, theirs.id, key)

    assert fake.gets == []
    assert fake.puts == {}


def test_finalize_discards_quarantine_when_the_promote_itself_faults(
    two_users, monkeypatch
):
    """The one path where nothing else ever sweeps.

    A `put_object` fault skips both the rejection discard and the success
    discard. The leftover has no `screenshots` row, so `delete_trade_objects`
    cannot see it, and the client has already errored out — so if finalize
    does not clear it here, nothing ever will.
    """
    a, _ = two_users
    mine = _trade_for(a)
    upload_key = (
        f"quarantine/u/{a}/t/{mine.id}/44444444-4444-4444-8444-444444444444.png"
    )

    class _FaultyPut(_FakeS3):
        def put_object(self, Bucket=None, Key=None, **kwargs):
            raise _client_error("InternalError", 500)

    fake = _FaultyPut(objects={upload_key: _png()})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(Exception):
        storage.finalize_upload(a, mine.id, upload_key)

    assert upload_key in fake.deleted


def test_finalize_cleans_the_possible_final_object_after_an_ambiguous_put_fault(
    two_users, monkeypatch
):
    """A lost PUT response may mean R2 stored the object before raising.

    The final key is already known locally. If finalize only discards
    quarantine on the exception path, the possibly-written final object has
    no screenshots row and is therefore unreachable and unsweepable. Cleanup
    must target both keys before the fault escapes.
    """
    a, _ = two_users
    mine = _trade_for(a)
    upload_key = (
        f"quarantine/u/{a}/t/{mine.id}/" "45454545-4545-4545-8545-454545454545.png"
    )

    class _StoredThenFaulted(_FakeS3):
        def put_object(self, Bucket=None, Key=None, **kwargs):
            self.puts[Key] = kwargs
            self.objects[Key] = kwargs["Body"]
            raise _client_error("InternalError", 500)

    fake = _StoredThenFaulted(objects={upload_key: _png()})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(Exception):
        storage.finalize_upload(a, mine.id, upload_key)

    promoted_key = next(iter(fake.puts))
    assert promoted_key in fake.deleted
    assert upload_key in fake.deleted


def test_finalize_reports_a_missing_quarantine_object_as_missing(
    two_users, monkeypatch
):
    """A stale key, a double finalize, or a retry after abandon.

    None of those are server faults, and none are "these bytes are not an
    image" either, so they get their own signal the router can turn into
    something the trader can act on.
    """
    a, _ = two_users
    mine = _trade_for(a)
    upload_key = (
        f"quarantine/u/{a}/t/{mine.id}/55555555-5555-4555-8555-555555555555.png"
    )

    class _EmptyBucket(_FakeS3):
        def get_object(self, Bucket=None, Key=None):
            self.gets.append(Key)
            raise _client_error("NoSuchKey", 404)

    fake = _EmptyBucket()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(storage.UploadMissing):
        storage.finalize_upload(a, mine.id, upload_key)


# ----------------------------------------------- put_quarantine_object (A2)


def test_put_quarantine_object_refuses_a_trade_the_caller_does_not_own(
    two_users, monkeypatch
):
    """The service's own ownership check, exercised directly.

    The URL-ingest route checks ownership before it fetches, so this check is
    never reached through the API and a route-level test cannot see it. That is
    exactly why it is pinned here: it is the guard that survives a future
    caller which forgets, and an unreachable guard nothing tests is a guard
    that gets deleted as dead code.
    """
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
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    with pytest.raises(PermissionError):
        storage.put_quarantine_object(a, theirs.id, _png(), "image/png")

    assert fake.puts == {}, "a refused ingest must write nothing at all"


def test_put_quarantine_object_lands_under_the_callers_own_quarantine_prefix(
    two_users, monkeypatch
):
    """Server-fetched bytes enter the SAME non-downloadable namespace an upload
    does. Anywhere else would be a second image path with none of the guards
    that promotion out of quarantine applies."""
    a, _ = two_users
    mine = _create({"user_id": a, "trade_date": "2026-08-12", "asset": "NQ"})
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    key = storage.put_quarantine_object(a, mine.id, _png(), "image/png")

    assert key.startswith(f"quarantine/u/{a}/t/{mine.id}/")
    assert key.endswith(".png")
    assert list(fake.puts) == [key]
    assert fake.puts[key]["ContentType"] == "image/png"


def test_owns_trade_is_false_for_another_owners_trade(two_users):
    a, b = two_users
    theirs = _create({"user_id": b, "trade_date": "2026-08-12", "asset": "NQ"})
    mine = _create({"user_id": a, "trade_date": "2026-08-12", "asset": "NQ"})

    assert storage.owns_trade(a, theirs.id) is False
    assert storage.owns_trade(a, mine.id) is True
