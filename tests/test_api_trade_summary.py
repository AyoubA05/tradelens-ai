"""Phase 3E enqueue/poll boundary for filtered-trade summaries."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api import jobs
from src.tradelens.api import worker
from src.tradelens.api.security import sign_request
from src.tradelens.db.models import AIJob, AIUsageLog
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import trade_service
from src.tradelens.services.trade_summary import (
    MAX_SUMMARIES_PER_WINDOW,
    SUMMARY_WINDOW_HOURS,
)

SECRET = "test-service-secret-value-at-least-32-bytes"
SUMMARY_PATH = "/v1/trades/summary"


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


def _signed_headers(handle: str, method: str, path: str, body: bytes = b"") -> dict:
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, method, path, "", body)
    return {
        "Content-Type": "application/json",
        "X-TL-Signature": f"v1={ts}:{sig}",
        "X-TL-Session-Handle": handle,
    }


def _create(user_id: int, **overrides):
    data = {
        "asset": "NQ",
        "trade_date": "2026-08-10",
        "result": "Win",
        "pnl": 100.0,
    }
    data.update(overrides)
    return trade_service.create_trade(data, user_id=user_id)


def test_enqueue_snapshots_only_authenticated_owners_filtered_trades(
    client, website_session_handle, two_users
):
    """Removing service-layer ownership would persist another trader's notes."""
    owner, handle = website_session_handle
    other = next(user_id for user_id in two_users if user_id != owner)
    _create(owner, notes="owner-one")
    _create(owner, trade_date="2026-08-11", notes="owner-two")
    _create(other, notes="FOREIGN_SECRET")
    body = json.dumps(
        {"from": "2026-08-01", "to": "2026-08-31"}, separators=(",", ":")
    ).encode()

    response = client.post(
        SUMMARY_PATH,
        content=body,
        headers=_signed_headers(handle, "POST", SUMMARY_PATH, body),
    )

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "queued"
    db = SessionLocal()
    try:
        job = db.get(AIJob, response.json()["job_id"])
        assert job.user_id == owner
        payload = json.loads(job.payload)
    finally:
        db.close()
    assert [row["notes"] for row in payload["trades"]] == [
        "owner-one",
        "owner-two",
    ]
    assert "FOREIGN_SECRET" not in json.dumps(payload)


@pytest.mark.parametrize("owner_field", ["user_id", "uid", "owner", "accountId"])
def test_enqueue_rejects_every_browser_supplied_owner_field(
    client, website_session_handle, owner_field
):
    owner, handle = website_session_handle
    _create(owner)
    _create(owner, trade_date="2026-08-11")
    body = json.dumps(
        {"from": "2026-08-01", "to": "2026-08-31", owner_field: 999},
        separators=(",", ":"),
    ).encode()

    response = client.post(
        SUMMARY_PATH,
        content=body,
        headers=_signed_headers(handle, "POST", SUMMARY_PATH, body),
    )

    assert response.status_code == 422
    db = SessionLocal()
    try:
        assert db.query(AIJob).count() == 0
    finally:
        db.close()


def test_enqueue_refuses_a_body_changed_after_hmac_signing(
    client, website_session_handle
):
    owner, handle = website_session_handle
    _create(owner)
    _create(owner, trade_date="2026-08-11")
    signed = b'{"from":"2026-08-01","to":"2026-08-31"}'
    tampered = b'{"from":"2026-01-01","to":"2026-08-31"}'

    response = client.post(
        SUMMARY_PATH,
        content=tampered,
        headers=_signed_headers(handle, "POST", SUMMARY_PATH, signed),
    )

    assert response.status_code == 401


def test_enqueue_refuses_a_selection_below_the_two_trade_floor(
    client, website_session_handle
):
    owner, handle = website_session_handle
    _create(owner)
    body = b'{"from":"2026-08-01","to":"2026-08-31"}'

    response = client.post(
        SUMMARY_PATH,
        content=body,
        headers=_signed_headers(handle, "POST", SUMMARY_PATH, body),
    )

    assert response.status_code == 422
    db = SessionLocal()
    try:
        assert db.query(AIJob).count() == 0
    finally:
        db.close()


def test_poll_hides_another_owners_job_like_a_missing_job(
    client, website_session_handle, two_users
):
    """Removing the owner predicate would expose job state and later its prose."""
    owner, handle = website_session_handle
    other = next(user_id for user_id in two_users if user_id != owner)
    own_id, _ = jobs.enqueue(owner, "trade_summary", "own", {})
    foreign_id, _ = jobs.enqueue(other, "trade_summary", "foreign", {})

    own_path = f"{SUMMARY_PATH}/{own_id}"
    own = client.get(own_path, headers=_signed_headers(handle, "GET", own_path))
    foreign_path = f"{SUMMARY_PATH}/{foreign_id}"
    foreign = client.get(
        foreign_path, headers=_signed_headers(handle, "GET", foreign_path)
    )
    missing_path = f"{SUMMARY_PATH}/999999"
    missing = client.get(
        missing_path, headers=_signed_headers(handle, "GET", missing_path)
    )

    assert own.status_code == 200
    assert own.json() == {
        "job_id": own_id,
        "status": "queued",
        "result": None,
        "error": None,
    }
    assert foreign.status_code == missing.status_code == 404
    assert foreign.content == missing.content


def test_poll_refuses_a_foreign_result_even_if_an_owned_job_pointer_is_corrupt(
    client, website_session_handle, two_users
):
    """The result lookup needs its own owner predicate, not only the job lookup."""
    owner, handle = website_session_handle
    other = next(user_id for user_id in two_users if user_id != owner)
    from src.tradelens.services.trade_summary import save_trade_summary_result

    foreign_id = save_trade_summary_result(
        user_id=other,
        summary_key="foreign-result",
        filters={},
        result={"content_md": "FOREIGN_SECRET", "reviewed_trades": 2},
    )
    job_id, _ = jobs.enqueue(owner, "trade_summary", "corrupt-pointer", {})
    jobs.complete(job_id, f"trade_summary:{foreign_id}")
    path = f"{SUMMARY_PATH}/{job_id}"

    response = client.get(path, headers=_signed_headers(handle, "GET", path))

    assert response.status_code == 500
    assert "FOREIGN_SECRET" not in response.text


def test_poll_does_not_report_success_when_the_result_pointer_is_missing(
    client, website_session_handle
):
    """A succeeded/null response would leave the panel polling a terminal job forever."""
    owner, handle = website_session_handle
    job_id, _ = jobs.enqueue(owner, "trade_summary", "missing-pointer", {})
    jobs.complete(job_id, "")
    path = f"{SUMMARY_PATH}/{job_id}"

    response = client.get(path, headers=_signed_headers(handle, "GET", path))

    assert response.status_code == 500
    assert response.json() == {"detail": "summary result unavailable"}


def test_worker_persists_result_and_poll_returns_it_to_the_owner(
    client, website_session_handle, monkeypatch
):
    """Dropping the handler/result lookup would leave a paid job unreadable."""
    owner, handle = website_session_handle
    from src.tradelens.services import trade_summary
    from src.tradelens.services.ai_client import Usage

    markdown = "\n\n".join(
        [
            "### Session Summary\n\nTwo completed trades were reviewed.",
            "### Discipline & Rule Adherence\n\nBoth records contain evidence.",
            "### Emotional Review\n\nEmotion logging was limited.",
            "### Recurring Patterns\n\nThe sample remains small.",
            "### Improvement Actions\n\nKeep recording the same fields.",
        ]
    )

    monkeypatch.setattr(
        trade_summary,
        "chat",
        lambda **kwargs: (markdown, Usage("test", 1, 1, 2, 0.01, 0.1)),
    )
    job_id, _ = jobs.enqueue(
        owner,
        "trade_summary",
        "worker-success",
        {
            "period_label": "2026-08-01 to 2026-08-31",
            "filters": {"from": "2026-08-01", "to": "2026-08-31"},
            "trades": [{"id": 1}, {"id": 2}],
            "summary_key": "snapshot-1",
        },
    )

    assert jobs.run_once(worker.HANDLERS) is True
    path = f"{SUMMARY_PATH}/{job_id}"
    response = client.get(path, headers=_signed_headers(handle, "GET", path))

    assert response.status_code == 200, response.text
    assert response.json() == {
        "job_id": job_id,
        "status": "succeeded",
        "result": {"content_md": markdown, "reviewed_trades": 2},
        "error": None,
    }


def test_repeated_selection_returns_the_existing_jobs_actual_terminal_status(
    client, website_session_handle, monkeypatch
):
    """Hard-coding queued would lie after idempotency returns a completed job."""
    owner, handle = website_session_handle
    _create(owner, notes="one")
    _create(owner, trade_date="2026-08-11", notes="two")
    body = json.dumps(
        {"from": "2026-08-01", "to": "2026-08-31"}, separators=(",", ":")
    ).encode()
    first = client.post(
        SUMMARY_PATH,
        content=body,
        headers=_signed_headers(handle, "POST", SUMMARY_PATH, body),
    )

    from src.tradelens.services import trade_summary
    from src.tradelens.services.ai_client import Usage

    markdown = "\n\n".join(
        f"{heading}\n\nEvidence."
        for heading in (
            "### Session Summary",
            "### Discipline & Rule Adherence",
            "### Emotional Review",
            "### Recurring Patterns",
            "### Improvement Actions",
        )
    )
    monkeypatch.setattr(
        trade_summary,
        "chat",
        lambda **kwargs: (markdown, Usage("test", 1, 1, 2, 0.01, 0.1)),
    )
    assert jobs.run_once(worker.HANDLERS) is True

    repeated = client.post(
        SUMMARY_PATH,
        content=body,
        headers=_signed_headers(handle, "POST", SUMMARY_PATH, body),
    )

    assert repeated.status_code == 202
    assert repeated.json() == {
        "job_id": first.json()["job_id"],
        "status": "succeeded",
        "created": False,
    }
    db = SessionLocal()
    try:
        assert db.query(AIJob).filter(AIJob.user_id == owner).count() == 1
    finally:
        db.close()


def test_editing_a_trade_changes_the_snapshot_key_instead_of_reusing_stale_prose(
    client, website_session_handle
):
    """Hashing filters alone would return prose about facts the trader already changed."""
    owner, handle = website_session_handle
    first_trade = _create(owner, notes="before")
    _create(owner, trade_date="2026-08-11", notes="two")
    body = b'{"from":"2026-08-01","to":"2026-08-31"}'
    first = client.post(
        SUMMARY_PATH,
        content=body,
        headers=_signed_headers(handle, "POST", SUMMARY_PATH, body),
    )

    trade_service.update_trade(first_trade.id, owner, notes="after")
    second = client.post(
        SUMMARY_PATH,
        content=body,
        headers=_signed_headers(handle, "POST", SUMMARY_PATH, body),
    )

    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] != second.json()["job_id"]
    db = SessionLocal()
    try:
        assert db.query(AIJob).filter(AIJob.user_id == owner).count() == 2
    finally:
        db.close()


def test_repeating_a_failed_selection_does_not_automatically_rerun_paid_work(
    client, website_session_handle
):
    """A post-provider failure cannot be safely retried without provider idempotency."""
    owner, handle = website_session_handle
    _create(owner, notes="one")
    _create(owner, trade_date="2026-08-11", notes="two")
    body = b'{"from":"2026-08-01","to":"2026-08-31"}'
    first = client.post(
        SUMMARY_PATH,
        content=body,
        headers=_signed_headers(handle, "POST", SUMMARY_PATH, body),
    )
    job_id = first.json()["job_id"]
    jobs.fail(job_id, "safe failure")

    retried = client.post(
        SUMMARY_PATH,
        content=body,
        headers=_signed_headers(handle, "POST", SUMMARY_PATH, body),
    )

    assert retried.status_code == 202
    assert retried.json() == {
        "job_id": job_id,
        "status": "failed",
        "created": False,
    }
    db = SessionLocal()
    try:
        rows = db.query(AIJob).filter(AIJob.user_id == owner).all()
        assert len(rows) == 1
        assert rows[0].error == "safe failure"
    finally:
        db.close()


def test_worker_logs_spend_for_a_paid_call_whose_response_fails_validation(
    website_session_handle, monkeypatch
):
    """Logging only after the save would drop a billed but unusable call."""
    owner, _handle = website_session_handle
    from src.tradelens.services import trade_summary
    from src.tradelens.services.ai_client import Usage

    monkeypatch.setattr(
        trade_summary,
        "chat",
        lambda **kwargs: (
            "### Not The Contract\n\nTruncated.",
            Usage("t", 1, 1, 2, 0.5, 0.1),
        ),
    )
    job_id, _ = jobs.enqueue(
        owner,
        "trade_summary",
        "worker-validation-failure",
        {
            "period_label": "2026-08-01 to 2026-08-31",
            "filters": {},
            "trades": [{"id": 1}, {"id": 2}],
            "summary_key": "snapshot-invalid",
        },
    )

    assert jobs.run_once(worker.HANDLERS) is True

    db = SessionLocal()
    try:
        job = db.query(AIJob).filter(AIJob.id == job_id).one()
        assert job.status == "failed"
        rows = (
            db.query(AIUsageLog)
            .filter(AIUsageLog.user_id == owner, AIUsageLog.feature == "Trade Summary")
            .all()
        )
        assert [row.cost_usd for row in rows] == [0.5]
    finally:
        db.close()


# --- Owner-scoped rate limit -------------------------------------------------
#
# Idempotency alone leaves the endpoint open: every distinct selection is a
# distinct, legitimately billable Opus job, so walking `from`/`to` a day at a
# time mints unbounded spend. These tests pin the ceiling, and — as much as the
# ceiling itself — pin that hitting it never costs a trader access to a summary
# they already paid for.


def _handle_for(user_id: int) -> str:
    """A live website session handle for an arbitrary owner.

    Inserted directly, exactly as the `website_session` fixture does: the point
    is the API's owner resolution, not the sign-in form.
    """
    import datetime as dt
    import hashlib
    import secrets

    from sqlalchemy import text as sa_text

    from src.tradelens.services import auth_sessions

    token = secrets.token_urlsafe(32)
    now = dt.datetime.now(dt.timezone.utc)
    digest = hashlib.sha256(
        (auth_sessions.WEBSITE_DOMAIN + token).encode("utf-8")
    ).hexdigest()
    db = SessionLocal()
    try:
        db.execute(
            sa_text(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, "
                "expires_at, last_seen_at, surface) VALUES (:h,:u,:c,:e,:l,:s)"
            ),
            {
                "h": digest,
                "u": user_id,
                "c": now,
                "e": now + dt.timedelta(hours=12),
                "l": now,
                "s": auth_sessions.SURFACE_WEBSITE,
            },
        )
        db.commit()
    finally:
        db.close()
    return digest


def _fill_window(user_id: int, count: int) -> None:
    """Put `count` recent trade_summary jobs in the window for one owner."""
    from datetime import datetime, timezone

    db = SessionLocal()
    try:
        for index in range(count):
            db.add(
                AIJob(
                    user_id=user_id,
                    kind="trade_summary",
                    idempotency_key=f"trade_summary:filler-{index}",
                    payload="{}",
                    status="succeeded",
                    created_at=datetime.now(timezone.utc),
                )
            )
        db.commit()
    finally:
        db.close()


def _job_count(user_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(AIJob).filter(AIJob.user_id == user_id).count()
    finally:
        db.close()


def _post(client, handle, body_dict):
    body = json.dumps(body_dict, separators=(",", ":")).encode()
    return client.post(
        SUMMARY_PATH,
        content=body,
        headers=_signed_headers(handle, "POST", SUMMARY_PATH, body),
    )


def test_owner_at_the_limit_is_refused_without_creating_a_billable_job(
    client, website_session_handle
):
    """Returning 429 while still writing the row would refuse the trader and bill anyway."""
    owner, handle = website_session_handle
    _create(owner, notes="one")
    _create(owner, trade_date="2026-08-11", notes="two")
    _fill_window(owner, MAX_SUMMARIES_PER_WINDOW)
    before = _job_count(owner)

    response = _post(client, handle, {"from": "2026-08-01", "to": "2026-08-31"})

    assert response.status_code == 429, response.text
    assert _job_count(owner) == before
    detail = response.json()["detail"]
    assert str(MAX_SUMMARIES_PER_WINDOW) in detail
    assert str(SUMMARY_WINDOW_HOURS) in detail


def test_walking_filters_and_date_ranges_does_not_buy_extra_summaries(
    client, website_session_handle
):
    """Keying the count on filters would let a day-at-a-time walk mint unbounded spend."""
    owner, handle = website_session_handle
    for day in range(10, 20):
        _create(owner, trade_date=f"2026-08-{day}", asset="NQ")
        _create(owner, trade_date=f"2026-08-{day}", asset="ES")
    _fill_window(owner, MAX_SUMMARIES_PER_WINDOW)
    before = _job_count(owner)

    selections = [
        {"from": "2026-08-10", "to": "2026-08-12"},
        {"from": "2026-08-11", "to": "2026-08-13"},
        {"from": "2026-08-10", "to": "2026-08-19", "asset": "NQ"},
        {"from": "2026-08-10", "to": "2026-08-19", "asset": "ES"},
        {"from": "2026-08-14", "to": "2026-08-19"},
    ]
    for selection in selections:
        response = _post(client, handle, selection)
        assert response.status_code == 429, (selection, response.text)

    assert _job_count(owner) == before


def test_at_the_limit_an_existing_selection_is_still_returned(
    client, website_session_handle
):
    """Refusing a key that already exists would lock a trader out of work already paid for."""
    owner, handle = website_session_handle
    _create(owner, notes="one")
    _create(owner, trade_date="2026-08-11", notes="two")
    selection = {"from": "2026-08-01", "to": "2026-08-31"}

    first = _post(client, handle, selection)
    assert first.status_code == 202
    assert first.json()["created"] is True

    _fill_window(owner, MAX_SUMMARIES_PER_WINDOW)
    before = _job_count(owner)

    repeated = _post(client, handle, selection)

    assert repeated.status_code == 202, repeated.text
    assert repeated.json()["job_id"] == first.json()["job_id"]
    assert repeated.json()["created"] is False
    assert _job_count(owner) == before


def test_the_limit_is_per_owner_not_global(client, two_users, website_session_handle):
    """A global count would let one busy trader silence everyone else's journal."""
    owner, _ = website_session_handle
    other = next(user_id for user_id in two_users if user_id != owner)
    other_handle = _handle_for(other)
    _create(other, notes="one")
    _create(other, trade_date="2026-08-11", notes="two")
    _fill_window(owner, MAX_SUMMARIES_PER_WINDOW + 5)
    before = _job_count(other)

    response = _post(client, other_handle, {"from": "2026-08-01", "to": "2026-08-31"})

    assert response.status_code == 202, response.text
    assert response.json()["created"] is True
    assert _job_count(other) == before + 1


def test_an_owner_under_the_limit_is_unaffected(client, website_session_handle):
    """The ceiling must be generous enough that ordinary journalling never meets it."""
    owner, handle = website_session_handle
    _create(owner, notes="one")
    _create(owner, trade_date="2026-08-11", notes="two")
    _fill_window(owner, MAX_SUMMARIES_PER_WINDOW - 1)
    before = _job_count(owner)

    response = _post(client, handle, {"from": "2026-08-01", "to": "2026-08-31"})

    assert response.status_code == 202, response.text
    assert response.json()["created"] is True
    assert _job_count(owner) == before + 1


def test_a_too_small_selection_at_the_limit_still_gets_its_422(
    client, website_session_handle
):
    """Ordering matters: a malformed request must not be masked as a rate limit."""
    owner, handle = website_session_handle
    _create(owner, notes="only-one")
    _fill_window(owner, MAX_SUMMARIES_PER_WINDOW)

    response = _post(client, handle, {"from": "2026-08-01", "to": "2026-08-31"})

    assert response.status_code == 422, response.text
