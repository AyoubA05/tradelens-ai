"""`POST /v1/trades/autofill` and `GET /v1/trades/autofill/{job_id}`.

The enqueue boundary carries the cost guarantees: a foreign or missing
screenshot costs nothing and reveals nothing, the rate limit is checked before
any `ai_jobs` row exists, and the same screenshot never buys a second billable
job — including after the first one failed.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api import jobs, worker
from src.tradelens.api.app import create_app
from src.tradelens.api.security import sign_request
from src.tradelens.db.models import AIJob, Screenshot, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import trade_autofill, trade_service
from src.tradelens.services.trade_autofill import (
    AUTOFILL_WINDOW_HOURS,
    JOB_KIND,
    MAX_AUTOFILLS_PER_WINDOW,
)

SECRET = "test-service-secret-value-at-least-32-bytes"
PATH = "/v1/trades/autofill"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TL_SERVICE_SECRET", SECRET)
    monkeypatch.delenv("TL_SERVICE_SECRET_PREVIOUS", raising=False)
    monkeypatch.setenv("TL_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@example.invalid/tradelens?sslmode=require",
    )
    return TestClient(create_app(), raise_server_exceptions=False)


def _headers(handle: str, method: str, path: str, body: bytes = b"") -> dict:
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, method, path, "", body)
    return {
        "Content-Type": "application/json",
        "X-TL-Signature": f"v1={ts}:{sig}",
        "X-TL-Session-Handle": handle,
    }


def _screenshot(user_id: int) -> int:
    """A trade with one promoted screenshot row, as `finalize_upload` leaves it."""
    trade = trade_service.create_trade(
        {"asset": "NQ", "trade_date": "2026-08-10"}, user_id=user_id
    )
    db = SessionLocal()
    try:
        row = Screenshot(
            trade_id=trade.id,
            file_path=f"u/{user_id}/t/{trade.id}/"
            "00000000-0000-4000-8000-000000000000.png",
            width=1200,
            height=800,
            uploaded_at=datetime.now(timezone.utc).isoformat(),
        )
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


def _post(client, handle, body_dict):
    body = json.dumps(body_dict, separators=(",", ":")).encode()
    return client.post(PATH, content=body, headers=_headers(handle, "POST", PATH, body))


def _job_count(user_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(AIJob).filter(AIJob.user_id == user_id).count()
    finally:
        db.close()


def _fill_window(user_id: int, count: int) -> None:
    db = SessionLocal()
    try:
        for index in range(count):
            db.add(
                AIJob(
                    user_id=user_id,
                    kind=JOB_KIND,
                    idempotency_key=f"{JOB_KIND}:filler-{index}",
                    payload="{}",
                    status="succeeded",
                    created_at=datetime.now(timezone.utc),
                )
            )
        db.commit()
    finally:
        db.close()


# ------------------------------------------------------------------ lock 1


def test_unsigned_enqueue_is_refused(client, website_session_handle):
    _, handle = website_session_handle
    body = json.dumps({"screenshot_id": 1}, separators=(",", ":")).encode()
    r = client.post(PATH, content=body, headers={"X-TL-Session-Handle": handle})
    assert r.status_code == 401


def test_enqueue_without_a_session_is_refused(client):
    body = json.dumps({"screenshot_id": 1}, separators=(",", ":")).encode()
    r = client.post(PATH, content=body, headers=_headers("", "POST", PATH, body))
    assert r.status_code == 401


@pytest.mark.parametrize("owner_field", ["user_id", "uid", "owner", "accountId"])
def test_enqueue_rejects_every_browser_supplied_owner_field(
    client, website_session_handle, owner_field
):
    owner, handle = website_session_handle
    screenshot_id = _screenshot(owner)
    r = _post(client, handle, {"screenshot_id": screenshot_id, owner_field: 999})
    assert r.status_code == 422
    assert _job_count(owner) == 0


# ------------------------------------------------------------ ownership 404


def test_a_missing_screenshot_is_a_404_and_costs_nothing(
    client, website_session_handle
):
    owner, handle = website_session_handle
    r = _post(client, handle, {"screenshot_id": 999999})
    assert r.status_code == 404
    assert _job_count(owner) == 0


def test_a_foreign_screenshot_is_byte_identical_to_a_missing_one(
    client, website_session_handle, two_users
):
    owner, handle = website_session_handle
    other = next(user_id for user_id in two_users if user_id != owner)
    foreign = _screenshot(other)

    foreign_response = _post(client, handle, {"screenshot_id": foreign})
    missing_response = _post(client, handle, {"screenshot_id": 999999})

    assert foreign_response.status_code == missing_response.status_code == 404
    assert foreign_response.content == missing_response.content
    assert _job_count(owner) == 0


def test_a_foreign_job_id_is_byte_identical_to_a_missing_one(
    client, website_session_handle, two_users
):
    owner, handle = website_session_handle
    other = next(user_id for user_id in two_users if user_id != owner)
    foreign_job, _ = jobs.enqueue(
        other, JOB_KIND, f"{JOB_KIND}:1", {"screenshot_id": 1}
    )

    def _get(job_id):
        path = f"{PATH}/{job_id}"
        return client.get(path, headers=_headers(handle, "GET", path))

    foreign_response = _get(foreign_job)
    missing_response = _get(999999)
    assert foreign_response.status_code == missing_response.status_code == 404
    assert foreign_response.content == missing_response.content


def test_a_job_of_another_kind_is_not_readable_as_an_autofill_job(
    client, website_session_handle
):
    """The owner's own summary job must not be polled through this route."""
    owner, handle = website_session_handle
    job_id, _ = jobs.enqueue(owner, "trade_summary", "trade_summary:x", {})
    path = f"{PATH}/{job_id}"
    r = client.get(path, headers=_headers(handle, "GET", path))
    assert r.status_code == 404


# ------------------------------------------------------------------- cost


def test_enqueue_queues_one_owner_scoped_job(client, website_session_handle):
    owner, handle = website_session_handle
    screenshot_id = _screenshot(owner)
    r = _post(client, handle, {"screenshot_id": screenshot_id})
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "queued"
    assert r.json()["created"] is True
    db = SessionLocal()
    try:
        job = db.get(AIJob, r.json()["job_id"])
        assert job.user_id == owner
        assert job.kind == JOB_KIND
        assert json.loads(job.payload) == {"screenshot_id": screenshot_id}
    finally:
        db.close()


def test_the_same_screenshot_never_buys_a_second_job(client, website_session_handle):
    owner, handle = website_session_handle
    screenshot_id = _screenshot(owner)
    first = _post(client, handle, {"screenshot_id": screenshot_id})
    second = _post(client, handle, {"screenshot_id": screenshot_id})
    assert first.json()["job_id"] == second.json()["job_id"]
    assert second.json()["created"] is False
    assert _job_count(owner) == 1


def test_owner_at_the_limit_is_refused_without_creating_a_billable_job(
    client, website_session_handle
):
    owner, handle = website_session_handle
    screenshot_id = _screenshot(owner)
    _fill_window(owner, MAX_AUTOFILLS_PER_WINDOW)
    before = _job_count(owner)

    r = _post(client, handle, {"screenshot_id": screenshot_id})

    assert r.status_code == 429, r.text
    assert _job_count(owner) == before
    detail = r.json()["detail"]
    assert str(MAX_AUTOFILLS_PER_WINDOW) in detail
    assert str(AUTOFILL_WINDOW_HOURS) in detail


def test_the_rate_limit_is_checked_before_any_provider_work(
    client, website_session_handle, monkeypatch
):
    """A refusal must never reach the worker, the bucket or Anthropic."""
    owner, handle = website_session_handle
    screenshot_id = _screenshot(owner)
    _fill_window(owner, MAX_AUTOFILLS_PER_WINDOW)

    calls = []
    monkeypatch.setattr(
        trade_autofill,
        "analyze_screenshot_v3",
        lambda *a, **k: calls.append(1),
    )
    r = _post(client, handle, {"screenshot_id": screenshot_id})
    assert r.status_code == 429
    assert worker.run_once(worker.HANDLERS) is False
    assert calls == []


def test_an_owner_at_the_limit_can_still_poll_a_job_they_already_have(
    client, website_session_handle
):
    owner, handle = website_session_handle
    screenshot_id = _screenshot(owner)
    first = _post(client, handle, {"screenshot_id": screenshot_id})
    _fill_window(owner, MAX_AUTOFILLS_PER_WINDOW)

    again = _post(client, handle, {"screenshot_id": screenshot_id})
    assert again.status_code == 202
    assert again.json()["job_id"] == first.json()["job_id"]
    assert again.json()["created"] is False


def test_a_failed_job_is_not_re_run_on_resubmit(client, website_session_handle):
    """Terminal means terminal: a resubmit returns the failure, not new spend."""
    owner, handle = website_session_handle
    screenshot_id = _screenshot(owner)
    first = _post(client, handle, {"screenshot_id": screenshot_id})
    job_id = first.json()["job_id"]
    jobs.fail(job_id, "This could not be generated. Please try again.")

    again = _post(client, handle, {"screenshot_id": screenshot_id})
    assert again.json()["job_id"] == job_id
    assert again.json()["created"] is False
    assert again.json()["status"] == "failed"
    assert _job_count(owner) == 1
    # And nothing is left queued for the worker to pick up and re-spend on.
    assert worker.run_once(worker.HANDLERS) is False


# ---------------------------------------------------- the poll, end to end


def test_a_completed_job_returns_suggestions_and_creates_no_trade_row(
    client, website_session_handle, monkeypatch
):
    owner, handle = website_session_handle
    screenshot_id = _screenshot(owner)
    monkeypatch.setattr(
        trade_autofill.storage, "read_owned_final_object", lambda u, s: b"fake-png"
    )
    monkeypatch.setattr(
        trade_autofill,
        "check_screenshot_quality",
        lambda p: type("Q", (), {"usable": True, "warnings": []})(),
    )
    monkeypatch.setattr(
        trade_autofill,
        "analyze_screenshot_v3",
        lambda *a, **k: (
            {
                "descriptive": {"detected_asset": "NQ", "session": "NY AM"},
                "trade_overlay": {
                    "source": "visible_trade_box",
                    "entry_price": 20100.25,
                    "confidence": {"entry_price": 0.9},
                },
            },
            "usage",
        ),
    )

    enqueued = _post(client, handle, {"screenshot_id": screenshot_id})
    assert worker.run_once(worker.HANDLERS) is True

    path = f"{PATH}/{enqueued.json()['job_id']}"
    r = client.get(path, headers=_headers(handle, "GET", path))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "succeeded"
    assert body["suggestions"]["entry_price"]["value"] == 20100.25
    assert body["suggestions"]["entry_price"]["autocheck"] is True
    # The derived field the model volunteered had nowhere to go.
    assert "session" not in body["suggestions"]

    db = SessionLocal()
    try:
        # Exactly the one trade the fixture created to hang the screenshot on;
        # autofill added none.
        assert db.query(Trade).count() == 1
    finally:
        db.close()


def test_a_queued_job_has_no_suggestions_yet(client, website_session_handle):
    owner, handle = website_session_handle
    screenshot_id = _screenshot(owner)
    enqueued = _post(client, handle, {"screenshot_id": screenshot_id})
    path = f"{PATH}/{enqueued.json()['job_id']}"
    r = client.get(path, headers=_headers(handle, "GET", path))
    assert r.status_code == 200
    assert r.json()["status"] == "queued"
    assert r.json()["suggestions"] is None
