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
