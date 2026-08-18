import re

import pytest

from src.tradelens.api import storage


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


@pytest.mark.parametrize("content_type", ["image/svg+xml", "text/html", "application/pdf", ""])
def test_disallowed_types_are_refused(content_type):
    """SVG is script-bearing markup, not a picture."""
    with pytest.raises(ValueError):
        storage.build_object_key(1, 1, content_type)


def test_presign_refuses_a_trade_the_user_does_not_own(two_users, monkeypatch):
    a, b = two_users
    from src.tradelens.services import trade_service

    theirs = trade_service.create_trade(
        {"user_id": b, "trade_date": "2026-08-12", "asset": "NQ", "result": "Win", "pnl": 1.0}
    )
    monkeypatch.setattr(storage, "_client", lambda: _FakeS3())
    with pytest.raises(PermissionError):
        storage.presign_upload(a, theirs.id, "image/png")


def test_presign_upload_bounds_the_policy(two_users, monkeypatch):
    a, _ = two_users
    from src.tradelens.services import trade_service

    mine = trade_service.create_trade(
        {"user_id": a, "trade_date": "2026-08-12", "asset": "NQ", "result": "Win", "pnl": 1.0}
    )
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    result = storage.presign_upload(a, mine.id, "image/png")

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
    from src.tradelens.services import trade_service

    theirs = trade_service.create_trade(
        {"user_id": b, "trade_date": "2026-08-12", "asset": "NQ", "result": "Win", "pnl": 1.0}
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


class _FakeS3:
    def __init__(self):
        self.last_params = None

    def generate_presigned_url(self, operation, Params=None, ExpiresIn=None):
        self.last_params = Params
        return f"https://r2.example/{Params['Key']}?sig=x&exp={ExpiresIn}"
