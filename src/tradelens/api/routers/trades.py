# src/tradelens/api/routers/trades.py
"""The Trades list and Trade Detail endpoints.

Thin by design, matching `routers/overview.py`: validate input, call the
service with the session's owner, shape the response. All filtering,
pagination and ownership live in `services/trade_service`; screenshot
ownership and presigning live in `services/storage` (via `services.storage`
imported as a module, not the bare function, so tests can patch it).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError

from src.tradelens.api import imaging, jobs, storage
from src.tradelens.api.deps import current_user
from src.tradelens.api.routers.overview import _validated_period
from src.tradelens.api.schemas.trades import (
    ScreenshotCleanupFailedResponse,
    TradeAutofillJobAccepted,
    TradeAutofillJobRequest,
    TradeAutofillJobStatus,
    ScreenshotDescriptor,
    ScreenshotKeyRequest,
    ScreenshotPresignRequest,
    ScreenshotPresignResponse,
    ScreenshotUrlRequest,
    TradeConflictResponse,
    TradeCreate,
    TradeCreateResponse,
    TradeDetail,
    TradeDraftPayload,
    TradeDraftResponse,
    TradeListResponse,
    TradeSummary,
    TradeSummaryJobAccepted,
    TradeSummaryJobRequest,
    TradeSummaryJobStatus,
    TradeUpdate,
)
from src.tradelens.services import drafts, screenshot_service, url_ingest
from src.tradelens.services.trade_autofill import (
    AUTOFILL_WINDOW_HOURS,
    JOB_KIND as AUTOFILL_JOB_KIND,
    MAX_AUTOFILLS_PER_WINDOW,
)
from src.tradelens.services.assets import detect_asset_class
from src.tradelens.services.sessions import KILLZONE_LABELS
from src.tradelens.services.trade_service import (
    compute_trade_hash,
    create_trade,
    delete_trade,
    find_by_fingerprint,
    get_trade,
    list_trades,
    update_trade_if_unchanged,
)
from src.tradelens.services.app_settings import today_for_owner
from src.tradelens.services.trade_summary import (
    MAX_SUMMARIES_PER_WINDOW,
    MIN_SUMMARY_TRADES,
    SUMMARY_WINDOW_HOURS,
    build_trade_snapshot,
    get_trade_summary_result,
)
from src.tradelens.services.trade_validation import OutcomeMismatch

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["trades"])

# One phrase for every "these bytes are not a picture" refusal, matching what
# `finalize_upload` surfaces, so a URL and an upload are indistinguishable to
# anyone probing the validator.
NOT_AN_IMAGE_DETAIL = "not a supported image"


def _finite_or_none(value: Optional[float]) -> Optional[float]:
    """Represent corrupt historical NaN/Infinity as undefined strict JSON."""
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _killzone_label(raw: Optional[str]) -> Optional[str]:
    """The human label for a stored killzone key, or the raw value if unknown.

    Never the bare key for a value KILLZONE_LABELS does recognise — that was
    the Phase 2 defect Codex caught. An unrecognised value (e.g. legacy data
    predating the killzone engine) falls back to itself rather than raising,
    since a fully-typed response is still owed for rows the engine never
    touched.
    """
    if raw is None:
        return None
    return KILLZONE_LABELS.get(raw, raw)


@router.get("/trades")
def get_trades_list(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    asset: Optional[str] = Query(None),
    session: Optional[str] = Query(None),
    setup: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    user_id: int = Depends(current_user),
) -> TradeListResponse:
    """The Trades list for the authenticated owner.

    The owner is the session row's, never the query. `limit`/`offset` are
    clamped inside `list_trades` itself, so a caller requesting `limit=1000`
    gets 100 back rather than a 422 — the service is the one source of truth
    for the bound, matching `list_trades`'s own contract.
    """
    start, end = _validated_period(from_, to)
    page = list_trades(
        user_id=user_id,
        start_date=start,
        end_date=end,
        asset=asset,
        session=session,
        setup_type=setup,
        result=result,
        limit=limit,
        offset=offset,
    )
    trades = [
        TradeSummary(
            id=trade.id,
            trade_date=trade.trade_date,
            asset=trade.asset,
            direction=trade.direction,
            session=trade.session,
            setup_type=trade.setup_type,
            killzone=_killzone_label(trade.killzone),
            result=trade.result,
            pnl=_finite_or_none(trade.pnl),
            rr_realized=_finite_or_none(trade.rr_realized),
            ai_grade=trade.ai_grade,
            user_grade=trade.user_grade,
            # `list_trades` eager-loads `screenshots`, so this is a length,
            # not a query — the list stays one SELECT plus one for the
            # collection however many rows a page holds. No presigned URLs
            # here: the list shows an indicator, and minting a signed URL per
            # row would be a hundred pointless round trips to R2 for images
            # nothing on this page renders.
            screenshot_count=len(trade.screenshots),
        )
        for trade in page.trades
    ]
    return TradeListResponse(
        trades=trades, total=page.total, limit=page.limit, offset=page.offset
    )


@router.post("/trades", status_code=status.HTTP_201_CREATED)
def create_trade_route(
    payload: TradeCreate,
    response: Response,
    user_id: int = Depends(current_user),
) -> TradeCreateResponse:
    """Create one trade for the authenticated owner.

    The body is a positive allowlist (`TradeCreate`); ownership and
    server-owned metadata are unreachable no matter what is sent —
    `create_trade` also forces `user_id` from the session, so this is
    defense in depth, not the only gate.

    A submit whose fingerprint (`compute_trade_hash`) matches an existing
    trade for this owner creates nothing: it returns 200 with that trade and
    `duplicate_of` set, so a double-submit or a retried request after a
    dropped response never produces a second row (Decision 5). A genuinely
    new fingerprint creates and returns 201.

    `canonical_outcome` raises `OutcomeMismatch` on a P&L/label contradiction
    rather than picking a side; letting that escape here would be a 500, so
    it is caught and reported as 422 naming the contradiction.
    """
    data = payload.model_dump(exclude={"entry_time"})
    data["entry_time"] = payload.entry_time
    # These values are derived from server-owned facts. In particular,
    # session/killzone use the owner's persisted timezone and strategy_used
    # uses the owner's active profile; none is accepted by TradeCreate.
    data["asset_class"] = detect_asset_class(payload.asset)

    # The ceiling is the OWNER's calendar date, not the server's. A trader
    # ahead of UTC has their actual today rejected as "future" for hours
    # around UTC midnight — refusing legitimate work. Phase 3E hit the same
    # class in Overview's Today/This Week and `today_for_owner` is the single
    # source that fix established.
    today = today_for_owner(user_id).isoformat()
    if payload.trade_date > today:
        raise HTTPException(
            status_code=422, detail="trade_date must not be in the future"
        )

    fingerprint = compute_trade_hash(data)
    existing = find_by_fingerprint(user_id=user_id, trade_hash=fingerprint)
    if existing is not None:
        # 200, not 201: nothing was created. Status code alone tells a client
        # which branch it got before it even reads the body.
        # `find_by_fingerprint` closes its own session without eager-loading
        # relationships, so re-fetch through `get_trade` before `_detail`
        # touches `.screenshots`.
        response.status_code = status.HTTP_200_OK
        full = get_trade(existing.id, user_id)
        return TradeCreateResponse(
            **_detail(full, user_id).model_dump(), duplicate_of=existing.id
        )

    # The read above makes ordinary retries cheap, but cannot serialize two
    # requests that both observe "missing". This server-owned key is guarded
    # by a database unique constraint scoped to the authenticated owner.
    data["create_idempotency_key"] = fingerprint
    try:
        # This is the live "I just took this trade" path, the only caller
        # entitled to fill a missing strategy_used from the owner's
        # currently active Strategy Profile (the form omits the field).
        created = create_trade(data, user_id=user_id, derive_strategy=True)
    except IntegrityError:
        # The only authenticated create-path uniqueness rule is the scoped
        # idempotency key. The winning transaction has committed before the
        # losing INSERT receives its constraint error, so it is now visible.
        existing = find_by_fingerprint(user_id=user_id, trade_hash=fingerprint)
        if existing is None:
            raise
        response.status_code = status.HTTP_200_OK
        full = get_trade(existing.id, user_id)
        return TradeCreateResponse(
            **_detail(full, user_id).model_dump(), duplicate_of=existing.id
        )
    except OutcomeMismatch as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # `create_trade` closes its own session before returning, so relationship
    # access on that instance (e.g. `.screenshots` inside `_detail`) would
    # raise DetachedInstanceError. Re-fetch through `get_trade`, which
    # eager-loads everything `_detail` touches.
    trade = get_trade(created.id, user_id)
    return TradeCreateResponse(
        **_detail(trade, user_id).model_dump(), duplicate_of=None
    )


@router.post(
    "/trades/summary",
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_trade_summary(
    payload: TradeSummaryJobRequest,
    user_id: int = Depends(current_user),
) -> TradeSummaryJobAccepted:
    """Snapshot and enqueue one authenticated owner's filtered selection."""
    start, end = _validated_period(payload.from_, payload.to)
    page = list_trades(
        user_id=user_id,
        start_date=start,
        end_date=end,
        asset=payload.asset,
        session=payload.session,
        setup_type=payload.setup,
        result=payload.result,
        limit=100,
        offset=0,
    )
    snapshot = build_trade_snapshot(page)
    if len(snapshot) < MIN_SUMMARY_TRADES:
        raise HTTPException(
            status_code=422,
            detail=f"select at least {MIN_SUMMARY_TRADES} trades",
        )

    filters = {
        "from": start,
        "to": end,
        "asset": payload.asset,
        "session": payload.session,
        "setup": payload.setup,
        "result": payload.result,
    }
    job_payload = {
        "filters": filters,
        "period_label": f"{start} to {end}",
        "trades": snapshot,
    }
    canonical = json.dumps(
        {"owner": user_id, **job_payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    snapshot_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    job_payload["summary_key"] = snapshot_key
    key = "trade_summary:" + snapshot_key

    # Idempotency stops a double-click; it does not stop a trader walking
    # `from`/`to` a day at a time, since every distinct selection is a
    # legitimately distinct — and separately billable — Opus job. The count is
    # therefore over the owner's `trade_summary` jobs in a rolling window and
    # is deliberately blind to filters, so no filter permutation escapes it.
    # Checked here, before `enqueue`, so a refusal writes no `ai_jobs` row and
    # never reaches the worker or Anthropic. It is checked *after* the period
    # and floor validation above so a malformed or too-small request still
    # gets its 422.
    if (
        jobs.count_recent_jobs(
            user_id,
            "trade_summary",
            datetime.now(timezone.utc) - timedelta(hours=SUMMARY_WINDOW_HOURS),
        )
        >= MAX_SUMMARIES_PER_WINDOW
    ):
        # Being at the limit must never lock a trader out of a summary they
        # already have. Only work that would create a *new* job is refused.
        existing = jobs.get_owned_job_by_idempotency_key(user_id, "trade_summary", key)
        if existing is None:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"You've reached {MAX_SUMMARIES_PER_WINDOW} AI summaries for "
                    f"today. New summaries are available again "
                    f"{SUMMARY_WINDOW_HOURS} hours after your earliest one. "
                    "Summaries you've already generated are still available."
                ),
            )
        return TradeSummaryJobAccepted(
            job_id=int(existing.id), status=existing.status, created=False
        )

    job_id, created = jobs.enqueue(user_id, "trade_summary", key, job_payload)
    job = jobs.get_owned_job(job_id, user_id)
    if job is None:  # Defensive: enqueue committed this exact owner-scoped row.
        raise HTTPException(status_code=500, detail="summary job unavailable")
    return TradeSummaryJobAccepted(job_id=job_id, status=job.status, created=created)


@router.get("/trades/summary/{job_id}")
def get_trade_summary_job(
    job_id: int,
    user_id: int = Depends(current_user),
) -> TradeSummaryJobStatus:
    """Return status for one owner-scoped job; foreign and missing are identical."""
    job = jobs.get_owned_job(job_id, user_id)
    if job is None or job.kind != "trade_summary":
        raise HTTPException(status_code=404, detail="summary job not found")
    result = None
    if job.status == "succeeded":
        if not job.result_ref:
            raise HTTPException(status_code=500, detail="summary result unavailable")
        prefix = "trade_summary:"
        if not job.result_ref.startswith(prefix):
            raise HTTPException(status_code=500, detail="summary result unavailable")
        try:
            result_id = int(job.result_ref[len(prefix) :])
        except ValueError as exc:
            raise HTTPException(
                status_code=500, detail="summary result unavailable"
            ) from exc
        result = get_trade_summary_result(result_id, user_id)
        if result is None:
            raise HTTPException(status_code=500, detail="summary result unavailable")
    return TradeSummaryJobStatus(
        job_id=job.id,
        status=job.status,
        result=result,
        error=job.error,
    )


@router.post("/trades/autofill", status_code=status.HTTP_202_ACCEPTED)
def enqueue_trade_autofill(
    payload: TradeAutofillJobRequest,
    user_id: int = Depends(current_user),
) -> TradeAutofillJobAccepted:
    """Queue AI autofill for one of the caller's own finalized screenshots.

    Ownership is settled FIRST, before anything is written and before any
    billable work can be scheduled: a foreign screenshot must not enqueue a
    job, because a queued job is spend and, on a poll, an existence oracle.
    A screenshot that is not the caller's returns the same 404 as one that
    does not exist.

    The job reads the PROMOTED object, not an upload: `finalize_upload` has
    already decoded, capped and re-encoded those bytes, so the model only ever
    sees bytes we produced.

    Nothing this endpoint starts can create a trade. The worker writes
    suggestions onto the owner's draft, and creation stays with
    `POST /v1/trades`.
    """
    if not storage.owns_screenshot(user_id, payload.screenshot_id):
        raise _not_found()

    key = f"{AUTOFILL_JOB_KIND}:{int(payload.screenshot_id)}"

    # Checked BEFORE `enqueue`, exactly as the summary endpoint does it, so a
    # refusal writes no `ai_jobs` row and never reaches the worker or
    # Anthropic. The count is over the owner's autofill jobs in a rolling
    # window and is deliberately blind to which screenshot, so re-uploading
    # the same chart under new ids buys nothing.
    if (
        jobs.count_recent_jobs(
            user_id,
            AUTOFILL_JOB_KIND,
            datetime.now(timezone.utc) - timedelta(hours=AUTOFILL_WINDOW_HOURS),
        )
        >= MAX_AUTOFILLS_PER_WINDOW
    ):
        # Being at the limit must never lock a trader out of a job they
        # already have — including one that failed, which they are entitled to
        # see rather than silently retry.
        existing = jobs.get_owned_job_by_idempotency_key(
            user_id, AUTOFILL_JOB_KIND, key
        )
        if existing is None:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"You've reached {MAX_AUTOFILLS_PER_WINDOW} AI autofills for "
                    f"today. New autofills are available again "
                    f"{AUTOFILL_WINDOW_HOURS} hours after your earliest one. "
                    "You can still fill the form in yourself."
                ),
            )
        return TradeAutofillJobAccepted(
            job_id=int(existing.id), status=existing.status, created=False
        )

    # The idempotency key is the screenshot, so a double-click, a retry, and a
    # resubmit after a failure all return the SAME job. A failed job therefore
    # stays terminal instead of quietly re-spending.
    job_id, created = jobs.enqueue(
        user_id, AUTOFILL_JOB_KIND, key, {"screenshot_id": int(payload.screenshot_id)}
    )
    job = jobs.get_owned_job(job_id, user_id)
    if job is None:  # Defensive: enqueue committed this exact owner-scoped row.
        raise HTTPException(status_code=500, detail="autofill job unavailable")
    return TradeAutofillJobAccepted(job_id=job_id, status=job.status, created=created)


@router.get("/trades/autofill/{job_id}")
def get_trade_autofill_job(
    job_id: int,
    user_id: int = Depends(current_user),
) -> TradeAutofillJobStatus:
    """Status for one owner-scoped autofill job; foreign and missing are identical.

    The kind check is not decoration: without it this route would read any of
    the owner's jobs, and a summary's result would be shaped into a suggestion
    set. Suggestions are read back from the owner's own draft — the only place
    the worker put them.
    """
    job = jobs.get_owned_job(job_id, user_id)
    if job is None or job.kind != AUTOFILL_JOB_KIND:
        raise HTTPException(status_code=404, detail="autofill job not found")

    suggestions = None
    if job.status == "succeeded":
        draft = drafts.get_draft(user_id) or {}
        suggestions = draft.get("ai_suggestions") or {}
    return TradeAutofillJobStatus(
        job_id=job.id,
        status=job.status,
        suggestions=suggestions,
        error=job.error,
    )


def _not_found() -> HTTPException:
    """One refusal for both 'no such trade' and 'someone else's trade'.

    A 403 would confirm the row exists for a different owner — a cross-tenant
    existence oracle. Both cases return this exact object so the responses
    are byte-identical.
    """
    return HTTPException(status_code=404, detail="trade not found")


def _detail(trade, user_id: int) -> TradeDetail:
    """Shape one trade for the wire, screenshots and all.

    Shared by GET and PATCH so an edited trade comes back through exactly the
    contract the client already renders — a second hand-built projection is
    how a field ends up present on read and missing after a save.
    """
    screenshots = [
        ScreenshotDescriptor(
            id=shot.id,
            width=shot.width,
            height=shot.height,
            uploaded_at=shot.uploaded_at,
            url=storage.presign_download(user_id, shot.id),
        )
        for shot in trade.screenshots
    ]

    return TradeDetail(
        id=trade.id,
        trade_date=trade.trade_date,
        day_of_week=trade.day_of_week,
        session=trade.session,
        asset=trade.asset,
        asset_class=trade.asset_class,
        timeframe=trade.timeframe,
        direction=trade.direction,
        bias=trade.bias,
        setup_type=trade.setup_type,
        entry_price=_finite_or_none(trade.entry_price),
        stop_price=_finite_or_none(trade.stop_price),
        tp_price=_finite_or_none(trade.tp_price),
        exit_price=_finite_or_none(trade.exit_price),
        position_size=_finite_or_none(trade.position_size),
        risk_amount=_finite_or_none(trade.risk_amount),
        reward_amount=_finite_or_none(trade.reward_amount),
        rr_planned=_finite_or_none(trade.rr_planned),
        rr_realized=_finite_or_none(trade.rr_realized),
        result=trade.result,
        pnl=_finite_or_none(trade.pnl),
        strategy_used=trade.strategy_used,
        emotions_before=trade.emotions_before,
        emotions_during=trade.emotions_during,
        emotions_after=trade.emotions_after,
        notes=trade.notes,
        trade_process_notes=trade.trade_process_notes,
        ai_grade=trade.ai_grade,
        user_grade=trade.user_grade,
        htf_bias=trade.htf_bias,
        killzone=_killzone_label(trade.killzone),
        liquidity_sweep=trade.liquidity_sweep,
        fvg_used=trade.fvg_used,
        order_block_used=trade.order_block_used,
        bos=trade.bos,
        choch=trade.choch,
        confirmation_model=trade.confirmation_model,
        entry_type=trade.entry_type,
        mistake_tags=trade.mistake_tags,
        followed_rules=trade.followed_rules,
        created_at=trade.created_at,
        updated_at=trade.updated_at,
        screenshots=screenshots,
    )


@router.get("/trades/draft")
def get_trade_draft(
    user_id: int = Depends(current_user),
) -> TradeDraftResponse:
    """Return the authenticated owner's saved New Trade draft, if any.

    Declared before `/trades/{trade_id}` so `"draft"` is never routed to that
    handler's `int` path converter.
    """
    payload = drafts.get_draft(user_id)
    if payload is None:
        return TradeDraftResponse(draft=None)
    return TradeDraftResponse(draft=TradeDraftPayload(**payload))


@router.put("/trades/draft")
def put_trade_draft(
    payload: TradeDraftPayload,
    user_id: int = Depends(current_user),
) -> TradeDraftResponse:
    """Save (or replace) the authenticated owner's one live draft.

    This never touches `trades` — `services.drafts.save_draft` writes only to
    `trade_drafts`, a table `POST /v1/trades` does not read from and cannot
    be reached from. The body is `TradeDraftPayload`, a positive allowlist
    with `extra="forbid"`: no derived field (`session`, `killzone`,
    `strategy_used`, `asset_class`, ...) has anywhere to go, whatever the
    request contains.
    """
    drafts.save_draft(user_id, payload.model_dump(exclude_unset=True))
    return TradeDraftResponse(draft=payload)


@router.get("/trades/{trade_id}")
def get_trade_detail(
    trade_id: int,
    user_id: int = Depends(current_user),
) -> TradeDetail:
    """One trade, plus presigned URLs for its screenshots.

    `get_trade` already filters on `Trade.user_id == owner`, so a trade
    belonging to another account is indistinguishable from a nonexistent one
    at the ORM layer — this handler preserves that by raising the identical
    404 either way, never a 403.
    """
    trade = get_trade(trade_id, user_id)
    if trade is None:
        raise _not_found()
    return _detail(trade, user_id)


@router.patch(
    "/trades/{trade_id}",
    responses={409: {"model": TradeConflictResponse}},
)
def patch_trade(
    trade_id: int,
    payload: TradeUpdate,
    user_id: int = Depends(current_user),
) -> TradeDetail:
    """Edit the user-editable fields of one trade.

    The body is a positive allowlist (`schemas.trades.TradeUpdate`), so
    ownership and server-owned metadata are unreachable no matter what is
    sent. `exclude_unset=True` is what separates "leave this alone" from
    "clear this": both are legitimate intentions and both are expressible.

    `expected_updated_at` is enforced inside a single conditional UPDATE in
    the service — see `update_trade_if_unchanged`. A stale value returns 409
    carrying the current timestamp so the client can show what changed rather
    than silently discarding the trader's typing.
    """
    fields = payload.model_dump(exclude_unset=True)
    expected = fields.pop("expected_updated_at")

    try:
        outcome = update_trade_if_unchanged(trade_id, user_id, expected, fields)
    except (OutcomeMismatch, ValueError) as exc:
        # A label contradicting the stored P&L is a bad request, not a server
        # fault: the row would otherwise say "Win" about a loss.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if outcome.status == "not_found":
        raise _not_found()
    if outcome.status == "conflict":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "stale_trade",
                "current_updated_at": outcome.current_updated_at,
            },
        )
    return _detail(outcome.trade, user_id)


@router.delete(
    "/trades/{trade_id}",
    status_code=204,
    responses={503: {"model": ScreenshotCleanupFailedResponse}},
)
def delete_trade_endpoint(
    trade_id: int,
    user_id: int = Depends(current_user),
) -> Response:
    """Delete one trade, its screenshot rows, and its stored images.

    **Objects go before the row, and only a complete cleanup earns the row's
    removal.** `screenshots.trade_id` is `ondelete="CASCADE"`, so dropping the
    trade drops the screenshot ROW while leaving the R2 OBJECT behind — and
    the row was the only record of that object's key. Deleting the row first,
    or deleting it anyway after a failed cleanup, would strand private images
    in the bucket with nothing left pointing at them.

    So an INCOMPLETE cleanup returns 503 with the row intact — incomplete
    meaning anything left behind, whether it failed or was skipped as a key
    this owner may not delete. That is deliberately the less tidy outcome:
    telling a trader their screenshots are gone while they remain in the
    bucket is a false privacy assurance, and a blocked delete is recoverable
    where a silent orphan is not.
    """
    if get_trade(trade_id, user_id) is None:
        # Checked before anything is removed, so a trade we do not own reaches
        # neither the object store nor `delete_trade`. 404, never 403.
        raise _not_found()

    cleanup = storage.delete_trade_objects(user_id, trade_id)
    if not cleanup.complete:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "screenshot_cleanup_failed",
                "remaining": len(cleanup.failed),
                # Reported separately from `remaining`: a skipped key is a row
                # naming a path this owner may not delete, so retrying will
                # never shrink it. Collapsing the two into one number would
                # tell the caller to keep retrying something that cannot
                # succeed.
                "unresolvable": len(cleanup.skipped),
            },
        )

    if not delete_trade(trade_id, user_id):
        # Removed by a concurrent request between the check and here. The
        # caller's intent is satisfied either way, but the resource is gone.
        raise _not_found()

    return Response(status_code=204)


@router.post("/trades/{trade_id}/screenshot/presign")
def presign_screenshot_upload(
    trade_id: int,
    payload: ScreenshotPresignRequest,
    user_id: int = Depends(current_user),
) -> ScreenshotPresignResponse:
    """Ask permission to upload one chart image for a trade.

    The trade is what authorises the upload (Decision 1): `presign_upload`
    requires the trade to exist and belong to the caller, so there is exactly
    one ownership rule in the system and no trade-less draft namespace with a
    second one.

    The signed URL points into a quarantine prefix that has NO download path.
    Only `finalize_upload` can promote bytes out of it, and only after
    re-encoding them. The key is chosen entirely by the server; the request
    body carries the content type and nothing else.

    A trade that is not the caller's returns 404, byte-identical to a missing
    one, and signs nothing — a 403 would confirm the row exists, and a URL
    would be an upload slot in another owner's namespace.
    """
    try:
        signed = storage.presign_upload(user_id, trade_id, payload.content_type)
    except PermissionError:
        raise _not_found() from None
    return ScreenshotPresignResponse(**signed)


@router.post(
    "/trades/{trade_id}/screenshot/finalize",
    status_code=status.HTTP_201_CREATED,
)
def finalize_screenshot_upload(
    trade_id: int,
    payload: ScreenshotKeyRequest,
    user_id: int = Depends(current_user),
) -> ScreenshotDescriptor:
    """Validate a quarantined upload, promote re-encoded bytes, record the row.

    The `key` in the body is a claim, never a location. `finalize_upload`
    re-derives this owner's own quarantine prefix and refuses anything outside
    it, so a forged key naming another tenant is a 404 that never reads a byte
    from the bucket.

    **The row write is what makes the promoted object reachable, and also what
    makes it sweepable.** `delete_trade_objects` resolves keys FROM
    `screenshots.file_path`, so a promoted object with no row is an orphan
    nothing can find and nothing can remove — strictly worse than a quarantine
    orphan, which at least has no download path. If the row write fails, the
    just-promoted object is deleted before the error is surfaced, leaving the
    bucket as it was and the retry safe.
    """
    try:
        promoted = storage.finalize_upload(user_id, trade_id, payload.key)
    except PermissionError:
        raise _not_found() from None
    except storage.UploadMissing as exc:
        # A stale key, a second finalize, or a retry after abandon. The bytes
        # are simply not there, which is a client-side situation and not a
        # server fault: it used to escape as a botocore error and surface as a
        # 500, which told the trader nothing. Say what happened and what to do,
        # and be explicit that the trade itself is unaffected.
        raise HTTPException(
            status_code=409,
            detail=(
                "that upload is no longer available, so no screenshot was "
                "attached. Your trade is unchanged — upload the image again."
            ),
        ) from exc
    except storage.UploadRejected as exc:
        # A stable phrase, not a reason: telling a prober which check they
        # failed hands them the shape of the validator.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _attach_promoted(trade_id, promoted, user_id)


def _attach_promoted(
    trade_id: int, promoted: dict, user_id: int
) -> ScreenshotDescriptor:
    """Record the row for a just-promoted object, and sign it for the client.

    Shared by finalize and URL ingest so both reach the bucket through exactly
    one promote-then-record sequence. A second copy of this is how one of the
    two would end up writing a promoted object with no row — an orphan nothing
    can name, since `delete_trade_objects` resolves keys FROM the rows.
    """
    try:
        screenshot_id, uploaded_at = screenshot_service.record_object_screenshot(
            trade_id,
            promoted["key"],
            user_id=user_id,
            width=promoted["width"],
            height=promoted["height"],
        )
    except Exception:
        # The row write failed, so the just-promoted object has nothing
        # pointing at it. Removing it is the whole point of this block, and
        # the removal can itself fail or raise — in which case the object is
        # a permanent orphan that `delete_trade_objects` can never reach,
        # because that resolves keys FROM the rows we just failed to write.
        # Never let that failure replace the 503 with a 500: the trader's
        # answer is the same either way, and swallowing the cleanup error
        # silently would hide the one case worth knowing about.
        try:
            removed = storage.delete_owned_object(user_id, trade_id, promoted["key"])
        except Exception:  # noqa: BLE001 — logged, never masks the 503
            removed = False
        if not removed:
            _log.error(
                "Orphaned a promoted screenshot object for trade %s: the "
                "database row failed and the object could not be removed",
                int(trade_id),
            )
        raise HTTPException(
            status_code=503, detail="the screenshot could not be attached"
        ) from None

    try:
        download_url = storage.presign_download(user_id, screenshot_id)
    except Exception:  # noqa: BLE001 — the row is already durable
        # Signing decorates the response; it is not part of the database
        # commit. Returning 500 here would tell the browser "not attached"
        # after the screenshot row and object both exist, inviting a duplicate
        # upload. The nullable contract already represents "no URL now".
        _log.warning(
            "Could not sign the newly attached screenshot for trade %s",
            int(trade_id),
        )
        download_url = None

    return ScreenshotDescriptor(
        id=screenshot_id,
        width=promoted["width"],
        height=promoted["height"],
        uploaded_at=uploaded_at,
        url=download_url,
    )


@router.post(
    "/trades/{trade_id}/screenshot/ingest-url",
    status_code=status.HTTP_201_CREATED,
)
def ingest_screenshot_url(
    trade_id: int,
    payload: ScreenshotUrlRequest,
    user_id: int = Depends(current_user),
) -> ScreenshotDescriptor:
    """Attach a chart image the server fetches from a link.

    This is the only place bytes enter the system without a browser upload, and
    it is deliberately not a second image path: the fetched bytes are PUT into
    this caller's own quarantine key and then go through the same
    `finalize_upload` — the same decode, the same size and dimension caps, the
    same re-encode, the same row write — as anything a trader uploads. A temp
    file handed to the model instead would inherit none of that.

    Ownership is settled FIRST, before a single packet leaves the server. A
    foreign trade must not cause an outbound request: the fetch is observable
    to whoever controls the URL, so issuing one would turn this endpoint into a
    cross-tenant existence oracle regardless of what status code came back.

    The URL is attacker-controlled, so `fetch_image_bytes` — not this handler —
    decides what may be connected to.
    """
    if not storage.owns_trade(user_id, trade_id):
        raise _not_found()

    try:
        data = url_ingest.fetch_image_bytes(payload.url)
    except url_ingest.UrlIngestError as exc:
        # A plain sentence the trader can act on. It names no address and no
        # check, so it is not a probe of the network the server can see.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Which content type the bytes CLAIM, only so the quarantine key carries an
    # extension. `finalize_upload` feeds that extension back in as the expected
    # type and makes the decoder corroborate it, exactly as it does for the
    # Content-Type a presigned upload was signed against.
    content_type = imaging.sniff_content_type(data)
    if content_type is None:
        raise HTTPException(status_code=422, detail=NOT_AN_IMAGE_DETAIL)

    try:
        upload_key = storage.put_quarantine_object(
            user_id, trade_id, data, content_type
        )
    except PermissionError:
        raise _not_found() from None

    try:
        promoted = storage.finalize_upload(user_id, trade_id, upload_key)
    except PermissionError:
        raise _not_found() from None
    except storage.UploadMissing as exc:
        # The object was written moments ago by this same request, so this
        # means the bucket lost it rather than a client sending a stale key.
        raise HTTPException(
            status_code=503, detail="the screenshot could not be attached"
        ) from exc
    except storage.UploadRejected as exc:
        # A stable phrase, not a reason: a decompression bomb, a polyglot and a
        # renamed executable all land here and are told the same thing.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _attach_promoted(trade_id, promoted, user_id)


@router.post(
    "/trades/{trade_id}/screenshot/abandon",
    status_code=status.HTTP_204_NO_CONTENT,
)
def abandon_screenshot_upload(
    trade_id: int,
    payload: ScreenshotKeyRequest,
    user_id: int = Depends(current_user),
) -> Response:
    """Drop a quarantined upload the trader chose not to keep.

    Backing out of an upload is a normal thing to do, and the object left
    behind has no download path but does occupy the bucket forever. This is
    the only way to clear one, since nothing else can name it: a quarantine
    object has no `screenshots` row, so `delete_trade_objects` cannot see it.

    The `key` is a claim. `abandon_upload` re-derives this caller's own
    quarantine prefix, which is the ONLY thing standing between a forged key
    and a deleted object — a delete of an arbitrary key would otherwise just
    succeed. A final key is refused for the same reason it is not quarantine:
    a promoted object is a screenshot the trader kept, and a `screenshots` row
    points at it.

    Idempotent. An object already gone is the end state this asks for, so a
    retry is success rather than an error the client can never clear.
    """
    try:
        storage.abandon_upload(user_id, trade_id, payload.key)
    except PermissionError:
        raise _not_found() from None

    return Response(status_code=204)
