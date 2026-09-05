"""`POST /v1/trades/{id}/analysis` and `GET /v1/trades/analysis/{job_id}`.

The enqueue boundary carries the cost guarantees: a foreign or missing trade
or screenshot costs nothing and reveals nothing, the rate limit is checked
before any `ai_jobs` row exists, and unchanged inputs never buy a second
billable job. The poll boundary carries the isolation one: a job that is not
this owner's, or not a Phase 5 kind, is indistinguishable from one that does
not exist.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api.security import sign_request
from src.tradelens.db.models import AIJob, Screenshot
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import trade_analysis, trade_service
from src.tradelens.services.trade_analysis import (
    ANALYSIS_JOB_KIND,
    MAX_ANALYSES_PER_WINDOW,
)

SECRET = "test-service-secret-value-at-least-32-bytes"


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


def _trade_with_screenshot(user_id: int):
    """A trade with one promoted screenshot, as `finalize_upload` leaves it."""
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
        return int(trade.id), int(row.id)
    finally:
        db.close()


def _enqueue_analysis(client, handle, trade_id, screenshot_id):
    path = f"/v1/trades/{trade_id}/analysis"
    body = json.dumps({"screenshot_id": screenshot_id}, separators=(",", ":")).encode()
    return client.post(path, content=body, headers=_headers(handle, "POST", path, body))


def _poll(client, handle, job_id):
    path = f"/v1/trades/analysis/{job_id}"
    return client.get(path, headers=_headers(handle, "GET", path))


def _jobs_of(user_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(AIJob).filter(AIJob.user_id == user_id).count()
    finally:
        db.close()


def _insert_job(user_id: int, kind: str, key: str) -> int:
    db = SessionLocal()
    try:
        row = AIJob(
            user_id=user_id,
            kind=kind,
            idempotency_key=key,
            payload="{}",
            status="queued",
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        return int(row.id)
    finally:
        db.close()


def _fill_quota(user_id: int, kind: str = ANALYSIS_JOB_KIND) -> None:
    db = SessionLocal()
    try:
        for index in range(MAX_ANALYSES_PER_WINDOW):
            db.add(
                AIJob(
                    user_id=user_id,
                    kind=kind,
                    idempotency_key=f"{kind}:filler-{index}",
                    payload="{}",
                    status="succeeded",
                    created_at=datetime.now(timezone.utc),
                )
            )
        db.commit()
    finally:
        db.close()


# ------------------------------------------------------------- ownership


def test_a_foreign_trade_is_byte_identical_to_a_missing_one(
    client, website_session_handle, two_users
):
    """404 never 403, and the same bytes — no existence oracle."""
    owner, handle = website_session_handle
    other = next(u for u in two_users if u != owner)
    other_trade, other_shot = _trade_with_screenshot(other)

    foreign = _enqueue_analysis(client, handle, other_trade, other_shot)
    missing = _enqueue_analysis(client, handle, 99999999, other_shot)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.content == missing.content
    assert _jobs_of(owner) == 0


def test_a_foreign_trade_is_refused_even_with_the_caller_s_own_screenshot(
    client, website_session_handle, two_users
):
    """Isolates the TRADE check from the screenshot check.

    The byte-identical test above sends a foreign trade AND a foreign
    screenshot, so the screenshot gate refuses first and the trade gate is
    never exercised — dropping ownership from the trade lookup left that
    test green. Here the screenshot is genuinely the caller's, so only the
    trade check can refuse, and it must: analysing someone else's trade
    would attach a reading to a row the caller cannot even read.
    """
    owner, handle = website_session_handle
    other = next(u for u in two_users if u != owner)
    _own_trade, own_shot = _trade_with_screenshot(owner)
    other_trade, _other_shot = _trade_with_screenshot(other)

    response = _enqueue_analysis(client, handle, other_trade, own_shot)

    assert response.status_code == 404
    assert _jobs_of(owner) == 0


def test_a_foreign_screenshot_never_enqueues_billable_work(
    client, website_session_handle, two_users
):
    """A queued job is spend; ownership is settled before anything is written."""
    owner, handle = website_session_handle
    other = next(u for u in two_users if u != owner)
    own_trade, _own_shot = _trade_with_screenshot(owner)
    _other_trade, foreign_shot = _trade_with_screenshot(other)

    response = _enqueue_analysis(client, handle, own_trade, foreign_shot)

    assert response.status_code == 404
    assert _jobs_of(owner) == 0


def test_a_screenshot_from_another_of_the_caller_s_own_trades_is_refused(
    client, website_session_handle
):
    """Owning both trades is not permission to analyse one with the other's chart.

    No isolation break — same tenant throughout — which is exactly why an
    owner-only check misses it. The reading would be written onto trade A's
    row while describing trade B's chart, and nothing in the result would
    say so.
    """
    owner, handle = website_session_handle
    trade_a, _shot_a = _trade_with_screenshot(owner)
    _trade_b, shot_b = _trade_with_screenshot(owner)

    response = _enqueue_analysis(client, handle, trade_a, shot_b)

    assert response.status_code == 404
    assert _jobs_of(owner) == 0


# ------------------------------------------------------------ idempotency


def test_the_same_request_twice_is_one_job(client, website_session_handle):
    """A double-clicked button must not be a second Anthropic bill."""
    _owner, handle = website_session_handle
    trade_id, shot_id = _trade_with_screenshot(_owner)

    first = _enqueue_analysis(client, handle, trade_id, shot_id)
    second = _enqueue_analysis(client, handle, trade_id, shot_id)

    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert _jobs_of(_owner) == 1


def test_correcting_the_ai_makes_the_next_analysis_a_new_job(
    client, website_session_handle, monkeypatch
):
    """The fingerprint covers correction state, so a correction is not a retry.

    Without this the trader corrects the AI, asks for a fresh read, and gets
    the cached job the correction was meant to change.
    """
    owner, handle = website_session_handle
    trade_id, shot_id = _trade_with_screenshot(owner)

    first = _enqueue_analysis(client, handle, trade_id, shot_id)
    monkeypatch.setattr(trade_analysis, "_corrections_fingerprint", lambda uid: "99:99")
    second = _enqueue_analysis(client, handle, trade_id, shot_id)

    assert first.json()["job_id"] != second.json()["job_id"]
    assert second.json()["created"] is True


# ------------------------------------------------------------- cost gates


def test_the_rate_limit_returns_429_and_creates_no_job(client, website_session_handle):
    """Rejected requests are a clear non-500, and nothing billable is queued."""
    owner, handle = website_session_handle
    trade_id, shot_id = _trade_with_screenshot(owner)
    _fill_quota(owner)
    before = _jobs_of(owner)

    response = _enqueue_analysis(client, handle, trade_id, shot_id)

    assert response.status_code == 429
    assert _jobs_of(owner) == before


def test_an_unfingerprintable_context_refuses_instead_of_enqueuing(
    client, website_session_handle, monkeypatch
):
    """The fingerprint fails closed, and the route must honour that.

    Enqueuing under a placeholder identity would let two genuinely different
    AI contexts share one cached job. A 503 costs the trader a retry; the
    alternative costs them a wrong answer they cannot detect.
    """
    owner, handle = website_session_handle
    trade_id, shot_id = _trade_with_screenshot(owner)

    def boom(_uid):
        raise RuntimeError("db down")

    monkeypatch.setattr(trade_analysis, "_corrections_fingerprint", boom)
    response = _enqueue_analysis(client, handle, trade_id, shot_id)

    assert response.status_code == 503
    assert _jobs_of(owner) == 0


# -------------------------------------------------------------- polling


def test_polling_another_owner_s_job_is_a_404(
    client, website_session_handle, two_users
):
    """A foreign job id must not even confirm that a job by that id exists."""
    owner, handle = website_session_handle
    other = next(u for u in two_users if u != owner)
    foreign_job = _insert_job(other, ANALYSIS_JOB_KIND, "trade_analysis:theirs")

    response = _poll(client, handle, foreign_job)
    missing = _poll(client, handle, 99999999)

    assert response.status_code == missing.status_code == 404
    assert response.content == missing.content


def test_polling_a_job_of_another_kind_is_a_404(client, website_session_handle):
    """Without the kind check this route would read any of the owner's jobs
    and shape a summary's result into an analysis status."""
    owner, handle = website_session_handle
    summary_job = _insert_job(owner, "trade_summary", "trade_summary:mine")

    assert _poll(client, handle, summary_job).status_code == 404


def test_polling_another_phase5_kind_on_this_route_is_also_a_404(
    client, website_session_handle
):
    """Cross-kind is a 404 even for a sibling Phase 5 kind.

    A shared poll would let a journal id answer here with `kind` set
    correctly — honest, but it makes the id's existence and category
    observable from the wrong endpoint. Groups B and C get their own routes.
    """
    owner, handle = website_session_handle
    journal_job = _insert_job(owner, "trade_journal", "trade_journal:mine")

    missing = _poll(client, handle, 99999999)
    response = _poll(client, handle, journal_job)

    assert response.status_code == missing.status_code == 404
    assert response.content == missing.content


def test_a_queued_job_reports_its_kind_and_status(client, website_session_handle):
    owner, handle = website_session_handle
    trade_id, shot_id = _trade_with_screenshot(owner)
    job_id = _enqueue_analysis(client, handle, trade_id, shot_id).json()["job_id"]

    body = _poll(client, handle, job_id).json()

    assert body["job_id"] == job_id
    assert body["kind"] == ANALYSIS_JOB_KIND
    assert body["status"] == "queued"
    assert body["superseded"] is False


def test_a_superseded_result_is_not_reported_as_a_plain_success(
    client, website_session_handle
):
    """`succeeded` and `superseded` are both true at once, and saying only
    the first would tell the trader their re-run landed when it did not."""
    owner, handle = website_session_handle
    trade_id, shot_id = _trade_with_screenshot(owner)
    job_id = _enqueue_analysis(client, handle, trade_id, shot_id).json()["job_id"]

    db = SessionLocal()
    try:
        row = db.query(AIJob).filter(AIJob.id == job_id).one()
        row.status = "succeeded"
        row.result_ref = f"{ANALYSIS_JOB_KIND}:{trade_id}:superseded"
        db.commit()
    finally:
        db.close()

    body = _poll(client, handle, job_id).json()
    assert body["status"] == "succeeded"
    assert body["superseded"] is True


def test_the_poll_never_returns_cost_or_raw_model_output(
    client, website_session_handle
):
    """Tokens, cost and the raw response are ours, not the browser's."""
    owner, handle = website_session_handle
    trade_id, shot_id = _trade_with_screenshot(owner)
    job_id = _enqueue_analysis(client, handle, trade_id, shot_id).json()["job_id"]

    body = _poll(client, handle, job_id).json()

    for leaked in ("cost_usd", "tokens_input", "tokens_output", "raw_response_json"):
        assert leaked not in body


# ------------------------------------------------- Group B3: journal/grade


def _analysed(user_id: int, trade_id: int, *, job_id: int = 1) -> None:
    """Give a trade a stored analysis, as Group A's job leaves it."""
    from src.tradelens.services.ai_client import Usage

    trade_analysis.store_analysis(
        user_id,
        trade_id,
        job_id=job_id,
        vision_result={"bias": "bullish", "trade_quality": 7},
        usage=Usage("claude-opus-5", 10, 20, 30, 0.01, 0.5),
    )


def _enqueue(client, handle, trade_id, what):
    path = f"/v1/trades/{trade_id}/{what}"
    body = b"{}"
    return client.post(path, content=body, headers=_headers(handle, "POST", path, body))


def _poll_kind(client, handle, what, job_id):
    path = f"/v1/trades/{what}/{job_id}"
    return client.get(path, headers=_headers(handle, "GET", path))


@pytest.mark.parametrize("what", ["journal", "grade"])
def test_a_foreign_trade_never_enqueues_derived_work(
    client, website_session_handle, two_users, what
):
    owner, handle = website_session_handle
    other = next(u for u in two_users if u != owner)
    other_trade, _shot = _trade_with_screenshot(other)
    _analysed(other, other_trade)

    response = _enqueue(client, handle, other_trade, what)

    assert response.status_code == 404
    assert _jobs_of(owner) == 0


@pytest.mark.parametrize("what", ["journal", "grade"])
def test_a_trade_with_no_analysis_is_refused_without_spending(
    client, website_session_handle, what
):
    """409, not 404: the trade exists and is theirs — the prerequisite is missing.

    A 404 here would be a lie the trader cannot act on; they would look for
    a trade that is plainly on screen.
    """
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)

    response = _enqueue(client, handle, trade_id, what)

    assert response.status_code == 409
    assert _jobs_of(owner) == 0


@pytest.mark.parametrize("what", ["journal", "grade"])
def test_regenerating_an_unchanged_result_returns_the_same_job(
    client, website_session_handle, what
):
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)

    first = _enqueue(client, handle, trade_id, what)
    second = _enqueue(client, handle, trade_id, what)

    assert first.status_code == second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert second.json()["created"] is False


def test_a_journal_and_a_grade_for_one_trade_are_different_jobs(
    client, website_session_handle
):
    """They share every input, so only the kind namespace separates them.

    Without it one enqueue returns the other's job and the trader polls a
    grade expecting a journal.
    """
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)

    journal = _enqueue(client, handle, trade_id, "journal")
    grade = _enqueue(client, handle, trade_id, "grade")

    assert journal.json()["job_id"] != grade.json()["job_id"]
    assert grade.json()["created"] is True


@pytest.mark.parametrize("what", ["journal", "grade"])
def test_a_fresh_analysis_makes_the_derived_result_a_new_job(
    client, website_session_handle, what
):
    """Re-analysis genuinely makes a journal and a grade stale.

    The analysis row's `updated_at` is in the key precisely so the trader
    does not get the previous reading's journal handed back.
    """
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id, job_id=1)
    first = _enqueue(client, handle, trade_id, what)

    _analysed(owner, trade_id, job_id=2)
    second = _enqueue(client, handle, trade_id, what)

    assert first.json()["job_id"] != second.json()["job_id"]


@pytest.mark.parametrize(
    "what,kind",
    [("journal", "trade_journal"), ("grade", "trade_grade")],
)
def test_the_derived_limit_is_429_and_creates_no_job(
    client, website_session_handle, what, kind
):
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)
    _fill_quota(owner, kind=kind)
    before = _jobs_of(owner)

    response = _enqueue(client, handle, trade_id, what)

    assert response.status_code == 429
    assert _jobs_of(owner) == before


@pytest.mark.parametrize("what", ["journal", "grade"])
def test_an_unfingerprintable_context_refuses_derived_work(
    client, website_session_handle, monkeypatch, what
):
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)
    before = _jobs_of(owner)

    def boom(_uid):
        raise RuntimeError("db down")

    monkeypatch.setattr(trade_analysis, "_corrections_fingerprint", boom)
    response = _enqueue(client, handle, trade_id, what)

    assert response.status_code == 503
    assert _jobs_of(owner) == before


@pytest.mark.parametrize(
    "own,foreign",
    [("journal", "grade"), ("grade", "journal")],
)
def test_each_kind_polls_only_on_its_own_route(
    client, website_session_handle, own, foreign
):
    """Cross-kind is a 404 byte-identical to a missing job.

    A shared poll would let one kind's id answer on another's route with
    `kind` set correctly — honest, but it makes the id's existence and
    category observable from the wrong endpoint.
    """
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)
    job_id = _enqueue(client, handle, trade_id, own).json()["job_id"]

    good = _poll_kind(client, handle, own, job_id)
    wrong = _poll_kind(client, handle, foreign, job_id)
    missing = _poll_kind(client, handle, foreign, 99999999)

    assert good.status_code == 200
    assert good.json()["job_id"] == job_id
    assert wrong.status_code == missing.status_code == 404
    assert wrong.content == missing.content


@pytest.mark.parametrize("what", ["journal", "grade"])
def test_polling_another_owner_s_derived_job_is_a_404(
    client, website_session_handle, two_users, what
):
    owner, handle = website_session_handle
    other = next(u for u in two_users if u != owner)
    kind = "trade_journal" if what == "journal" else "trade_grade"
    foreign = _insert_job(other, kind, f"{kind}:theirs")

    response = _poll_kind(client, handle, what, foreign)
    missing = _poll_kind(client, handle, what, 99999999)

    assert response.status_code == missing.status_code == 404
    assert response.content == missing.content


# --------------------------------------------- Group C1: confirming labels


def _patch_labels(client, handle, trade_id, body_dict):
    path = f"/v1/trades/{trade_id}/analysis"
    body = json.dumps(body_dict, separators=(",", ":")).encode()
    return client.patch(
        path, content=body, headers=_headers(handle, "PATCH", path, body)
    )


def test_confirming_a_label_returns_it_as_confirmed(client, website_session_handle):
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)

    response = _patch_labels(client, handle, trade_id, {"bias": "bearish"})

    assert response.status_code == 200
    assert response.json()["bias"] == "bearish"
    assert response.json()["confirmed_fields"] == ["bias"]


def test_a_server_owned_field_is_refused_by_the_schema(client, website_session_handle):
    """422, not a silent drop: `extra="forbid"` is the contract."""
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)

    response = _patch_labels(client, handle, trade_id, {"cost_usd": 0.0})

    assert response.status_code == 422


def test_release_cannot_name_a_column_outside_the_allowlist(
    client, website_session_handle
):
    """The release list is typed, so a column name is a 422 not a no-op."""
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)

    response = _patch_labels(client, handle, trade_id, {"release": ["analysis_job_id"]})

    assert response.status_code == 422


def test_confirming_on_another_owner_s_trade_is_a_404(
    client, website_session_handle, two_users
):
    owner, handle = website_session_handle
    other = next(u for u in two_users if u != owner)
    other_trade, _shot = _trade_with_screenshot(other)
    _analysed(other, other_trade)

    response = _patch_labels(client, handle, other_trade, {"bias": "bearish"})
    missing = _patch_labels(client, handle, 99999999, {"bias": "bearish"})

    assert response.status_code == missing.status_code == 404
    assert response.content == missing.content
    assert _analysis_row_of(other_trade).bias == "bullish"


def test_a_grade_override_never_touches_the_ai_grade(client, website_session_handle):
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)
    _set_ai_grade(trade_id, "B")

    response = _patch_labels(client, handle, trade_id, {"user_grade": "A"})

    assert response.status_code == 200
    assert response.json()["user_grade"] == "A"
    assert _trade_of(trade_id).ai_grade == "B"


def test_a_null_grade_override_clears_it_rather_than_being_ignored(
    client, website_session_handle
):
    """`None` is a meaningful value here — it is how the trader takes it back."""
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)
    _patch_labels(client, handle, trade_id, {"user_grade": "A"})

    response = _patch_labels(client, handle, trade_id, {"user_grade": None})

    assert response.status_code == 200
    assert response.json()["user_grade"] is None


def _analysis_row_of(trade_id):
    from src.tradelens.db.models import AIAnalysis

    db = SessionLocal()
    try:
        return db.query(AIAnalysis).filter(AIAnalysis.trade_id == trade_id).one()
    finally:
        db.close()


def _trade_of(trade_id):
    from src.tradelens.db.models import Trade

    db = SessionLocal()
    try:
        return db.query(Trade).filter(Trade.id == trade_id).one()
    finally:
        db.close()


def _set_ai_grade(trade_id, grade):
    from src.tradelens.db.models import Trade

    db = SessionLocal()
    try:
        row = db.query(Trade).filter(Trade.id == trade_id).one()
        row.ai_grade = grade
        db.commit()
    finally:
        db.close()


# ---------------------------------------------- C1: confirm, lock, release


def _corrections_of(user_id: int):
    from src.tradelens.db.models import Correction
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        return [
            (c.field, c.ai_value, c.user_value)
            for c in db.query(Correction).filter(Correction.user_id == user_id).all()
        ]
    finally:
        db.close()


def _patch_labels(client, handle, trade_id, body):
    path = f"/v1/trades/{trade_id}/analysis"
    raw = json.dumps(body, separators=(",", ":")).encode()
    return client.patch(path, content=raw, headers=_headers(handle, "PATCH", path, raw))


def _confirmed_fields(trade_id):
    from src.tradelens.services.trade_analysis import confirmed_fields

    from src.tradelens.db.models import AIAnalysis
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = db.query(AIAnalysis).filter(AIAnalysis.trade_id == trade_id).first()
        return sorted(confirmed_fields(row))
    finally:
        db.close()


def _stored_bias(trade_id):
    from src.tradelens.db.models import AIAnalysis
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        return db.query(AIAnalysis).filter(AIAnalysis.trade_id == trade_id).one().bias
    finally:
        db.close()


def test_confirming_records_an_owner_scoped_correction(client, website_session_handle):
    """The correction is what personalization learns from, so it must land."""
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)

    response = _patch_labels(client, handle, trade_id, {"bias": "bearish"})

    assert response.status_code == 200
    assert response.json()["confirmed_fields"] == ["bias"]
    assert ("bias", "bullish", "bearish") in _corrections_of(owner)


def test_confirming_an_unchanged_value_records_nothing(client, website_session_handle):
    """A correction is a DIFFERENCE. Recording a no-op would teach noise."""
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)

    _patch_labels(client, handle, trade_id, {"bias": "bullish"})

    assert _corrections_of(owner) == []
    # Still locked, though: the trader affirmed this value deliberately.
    assert _confirmed_fields(trade_id) == ["bias"]


def test_confirming_on_another_owner_s_trade_is_byte_identical_to_missing(
    client, website_session_handle, two_users
):
    owner, handle = website_session_handle
    other = next(u for u in two_users if u != owner)
    other_trade, _shot = _trade_with_screenshot(other)
    _analysed(other, other_trade)

    foreign = _patch_labels(client, handle, other_trade, {"bias": "bearish"})
    missing = _patch_labels(client, handle, 99999999, {"bias": "bearish"})

    assert foreign.status_code == missing.status_code == 404
    assert foreign.content == missing.content
    assert _corrections_of(owner) == []
    # And the other owner's label is untouched.
    assert _stored_bias(other_trade) == "bullish"


def test_a_confirmed_field_stays_locked_against_every_later_job(
    client, website_session_handle
):
    """Confirm, then let a NEWER analysis job run. The trader's value stands."""
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id, job_id=1)
    _patch_labels(client, handle, trade_id, {"bias": "bearish"})

    _analysed(owner, trade_id, job_id=50)  # much newer job

    assert _stored_bias(trade_id) == "bearish"


def test_release_is_the_only_path_that_makes_a_field_ai_writable_again(
    client, website_session_handle
):
    """Release, and only release, lowers the lock.

    Re-sending a value re-confirms it; nothing else in the API unlocks. And
    releasing does not revert the value — it only lets a LATER job replace
    it, so the trader's decision stands until something newer arrives.
    """
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id, job_id=1)
    _patch_labels(client, handle, trade_id, {"bias": "bearish"})

    # Re-confirming with a different value keeps it locked, not unlocked.
    _patch_labels(client, handle, trade_id, {"bias": "neutral"})
    assert _confirmed_fields(trade_id) == ["bias"]
    _analysed(owner, trade_id, job_id=60)
    assert _stored_bias(trade_id) == "neutral"

    # Now release it explicitly.
    released = _patch_labels(client, handle, trade_id, {"release": ["bias"]})
    assert released.status_code == 200
    assert released.json()["confirmed_fields"] == []
    assert _stored_bias(trade_id) == "neutral"  # release does not revert

    _analysed(owner, trade_id, job_id=70)
    assert _stored_bias(trade_id) == "bullish"  # now AI-writable again


def test_a_stale_job_still_cannot_win_after_a_release(client, website_session_handle):
    """Release lowers the lock; it does not disable the ordering guard.

    Both rules have to keep holding independently, or releasing one field
    would quietly reopen the door to every older job in the queue.
    """
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id, job_id=40)
    _patch_labels(client, handle, trade_id, {"bias": "bearish"})
    _patch_labels(client, handle, trade_id, {"release": ["bias"]})

    _analysed(owner, trade_id, job_id=5)  # older than the stored job

    assert _stored_bias(trade_id) == "bearish"


def test_release_cannot_name_a_field_outside_the_allowlist(
    client, website_session_handle
):
    """A release list is not a way to name arbitrary columns."""
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)

    response = _patch_labels(
        client, handle, trade_id, {"release": ["analysis_job_id", "cost_usd"]}
    )

    assert response.status_code == 422


def test_a_server_owned_field_cannot_be_confirmed(client, website_session_handle):
    """The confirm body is a positive allowlist, not a column editor."""
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)

    response = _patch_labels(
        client, handle, trade_id, {"cost_usd": 0.0, "analysis_job_id": 999}
    )

    assert response.status_code == 422


def test_a_failure_after_the_correction_write_leaves_nothing_behind(
    client, website_session_handle, monkeypatch
):
    """THE atomicity property, tested by injecting a real failure.

    Split across transactions, a failure here lands the correction while
    leaving the lock down — personalization learns from the trader's
    decision AND the next job overwrites the value they decided on. Both
    halves commit or neither does.
    """
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)

    # Break the denormalize step, which runs AFTER the correction insert and
    # after the lock update, inside the same transaction.
    monkeypatch.setattr(
        trade_analysis, "_LABEL_DENORMALIZATION", (("bias", "no_such_column"),)
    )
    response = _patch_labels(client, handle, trade_id, {"bias": "bearish"})

    assert response.status_code >= 500
    assert _corrections_of(owner) == []  # rolled back with everything else
    assert _confirmed_fields(trade_id) == []  # lock never went up
    assert _stored_bias(trade_id) == "bullish"  # label untouched


def test_reading_the_stored_analysis_omits_cost_and_raw_model_output(
    client, website_session_handle
):
    """Tokens, cost, job ids and the raw response are ours, not the browser's.

    The raw response is unvalidated model output; cost is billing detail.
    Both sit on the row and neither belongs on the wire.
    """
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)

    path = f"/v1/trades/{trade_id}/analysis"
    body = client.get(path, headers=_headers(handle, "GET", path)).json()

    for leaked in (
        "cost_usd",
        "tokens_input",
        "tokens_output",
        "raw_response_json",
        "analysis_job_id",
        "journal_job_id",
        "grading_job_id",
    ):
        assert leaked not in body
    assert body["bias"] == "bullish"


def test_a_trade_with_no_analysis_reads_as_a_404_not_an_empty_object(
    client, website_session_handle
):
    """'Not run yet' is a state the panel renders differently from 'ran'."""
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)

    path = f"/v1/trades/{trade_id}/analysis"
    assert client.get(path, headers=_headers(handle, "GET", path)).status_code == 404


def test_another_owner_s_analysis_is_byte_identical_to_a_missing_one(
    client, website_session_handle, two_users
):
    owner, handle = website_session_handle
    other = next(u for u in two_users if u != owner)
    other_trade, _shot = _trade_with_screenshot(other)
    _analysed(other, other_trade)

    fp = f"/v1/trades/{other_trade}/analysis"
    mp = "/v1/trades/99999999/analysis"
    foreign = client.get(fp, headers=_headers(handle, "GET", fp))
    missing = client.get(mp, headers=_headers(handle, "GET", mp))

    assert foreign.status_code == missing.status_code == 404
    assert foreign.content == missing.content


def test_the_read_reports_which_labels_the_trader_confirmed(
    client, website_session_handle
):
    """The panel must tell an AI guess from a decision the trader stands
    behind — that difference is the entire point of the lock."""
    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)
    _patch_labels(client, handle, trade_id, {"bias": "bearish"})

    path = f"/v1/trades/{trade_id}/analysis"
    body = client.get(path, headers=_headers(handle, "GET", path)).json()

    assert body["confirmed_fields"] == ["bias"]
    assert body["bias"] == "bearish"


def test_an_unparseable_stored_list_reads_as_empty_not_a_500(
    client, website_session_handle
):
    """These columns hold model output written by an earlier deploy.

    A row that no longer parses must render as "nothing recorded" rather
    than break a page the trader is trying to read.
    """
    from src.tradelens.db.models import AIAnalysis
    from src.tradelens.db.session import SessionLocal

    owner, handle = website_session_handle
    trade_id, _shot = _trade_with_screenshot(owner)
    _analysed(owner, trade_id)
    db = SessionLocal()
    try:
        row = db.query(AIAnalysis).filter(AIAnalysis.trade_id == trade_id).one()
        row.mistakes_json = "{not json"
        row.grading_json = "[]"
        db.commit()
    finally:
        db.close()

    path = f"/v1/trades/{trade_id}/analysis"
    response = client.get(path, headers=_headers(handle, "GET", path))

    assert response.status_code == 200
    assert response.json()["possible_mistakes"] == []
    assert response.json()["grading"] is None
