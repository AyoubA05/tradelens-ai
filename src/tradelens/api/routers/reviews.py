"""`/v1/reviews` — AI Reviews: Patterns, review periods, saved notes.

Thin by design: validate input, call services with the session's owner, shape
the response. Patterns are deterministic (`patterns.generate_insights`, R9) and
need no AI. Every day/week boundary follows the owner's timezone through
`review_inputs.review_as_of` (`app_settings.today_for_owner`, C6).
"""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.tradelens.api import jobs
from src.tradelens.api.deps import current_user
from src.tradelens.api.schemas.reviews import (
    PatternInsight,
    PatternsLens,
    PeriodStats,
    ReviewJobAccepted,
    ReviewJobStatus,
    ReviewsResponse,
    DailyDebriefRequest,
    SavedNote,
    WeeklyRecapRequest,
)
from src.tradelens.services import (
    activation,
    daily_debriefs,
    debrief,
    patterns,
    review_inputs,
    review_periods,
    trade_analysis,
    weekly,
)
from src.tradelens.services.demo import is_demo
from src.tradelens.services.strategy import get_active_strategy
from src.tradelens.services.trade_service import get_trades
from src.tradelens.utils.ai_utils import is_ai_enabled

router = APIRouter(prefix="/v1", tags=["reviews"])

_KNOWN = frozenset({"week", "day"})
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")

# Copied verbatim from `ui/pages/6_Insights.py::_DF_COLS` (parity reference).
PATTERN_COLUMNS = [
    "id",
    "trade_date",
    "day_of_week",
    "session",
    "asset",
    "setup_type",
    "rr_realized",
    "pnl",
    "result",
    "killzone",
    "confirmation_model",
    "mistake_tags",
    "htf_bias",
    "direction",
    "followed_rules",
]


def _now_utc() -> dt.datetime:
    """The current instant. A seam so tests can pin 'today' across DST."""
    return dt.datetime.now(dt.timezone.utc)


def _today(owner: int) -> dt.date:
    """The owner's today through the one shared review rule (C6)."""
    return review_inputs.review_as_of(owner, now_utc=_now_utc())


def _iso_date(value: Optional[str], *, monday: bool = False) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not _ISO.fullmatch(value):
        raise HTTPException(status_code=422, detail="dates must be ISO YYYY-MM-DD")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="dates must be ISO YYYY-MM-DD"
        ) from None
    if monday and parsed.weekday() != 0:
        raise HTTPException(status_code=422, detail="week must be a Monday")
    return parsed.isoformat()


def _finite(value) -> float:
    number = float(value or 0.0)
    return number if math.isfinite(number) else 0.0


def _stats(raw: Optional[dict]) -> PeriodStats:
    raw = raw or {}
    pf = raw.get("profit_factor")
    pf = None if pf is None or not math.isfinite(float(pf)) else float(pf)
    trades = int(raw.get("trades") or 0)
    financial_status = raw.get("financial_status")
    if financial_status not in ("no_sample", "incomplete", "measured"):
        # Legacy saved rows predate the status and the old metric path flattened
        # missing P&L to zero. Unknown completeness must not be presented as a
        # confident measurement.
        financial_status = "no_sample" if trades == 0 else "incomplete"
    return PeriodStats(
        trades=trades,
        win_rate=_finite(raw.get("win_rate")),
        total_pnl=_finite(raw.get("total_pnl")),
        profit_factor=pf,
        total_edge_leak=_finite(raw.get("total_edge_leak")),
        financial_status=financial_status,
    )


def _note(saved: Optional[dict], key: str) -> Optional[SavedNote]:
    if saved is None or not saved.get("content_md"):
        return None
    stats = saved.get("stats") or {}
    return SavedNote(
        period=str(saved[key]),
        content_md=str(saved["content_md"]),
        stats=_stats(stats),
        reviewed_trades=int(stats.get("trades") or saved.get("reviewed_trades") or 0),
        created_at=str(saved["created_at"]),
    )


def _insight(raw: dict) -> PatternInsight:
    return PatternInsight(
        title=str(raw["title"]),
        body=str(raw["body"]),
        confidence=raw["confidence"],
        type=str(raw["type"]),
        min_trades=int(raw["min_trades"]),
    )


WEEKLY_LIMIT_MESSAGE = (
    "You've reached today's limit for weekly recaps. "
    "Recaps you've already generated are still available."
)
DAILY_LIMIT_MESSAGE = (
    "You've reached today's limit for daily debriefs. "
    "Debriefs you've already generated are still available."
)
REVIEW_OUT_OF_DATE = "This review is out of date. Generate it again."
_RESULT_UNAVAILABLE = "review result unavailable"
_REVIEW_KINDS = ("weekly_recap", "daily_debrief")
_DIGITS = re.compile(r"[0-9]+")


def _enqueue_review(
    user_id: int,
    kind: str,
    period: str,
    model_input: dict,
    *,
    limit: int,
    window_hours: int,
    limit_message: str,
) -> ReviewJobAccepted:
    """Key, payload and rate-limited enqueue shared by both review kinds.

    The payload carries the period, source trade ids and the captured
    fingerprint — never trade text (C3). An unreadable AI context refuses
    with a fixed 503 rather than keying on a guess.
    """
    try:
        corrections_block = review_inputs.review_corrections_block(user_id)
        fingerprint = review_inputs.review_input_fingerprint(
            kind,
            user_id,
            period,
            model_input,
            corrections_block=corrections_block,
        )
    except trade_analysis.AIInputVersionUnavailable:
        raise HTTPException(status_code=503, detail="review_unavailable") from None
    key = kind + ":" + fingerprint
    job_payload = {
        "period": period,
        "source_trade_ids": list(model_input["source_trade_ids"]),
        "fingerprint": fingerprint,
        "key": key,
    }
    job_id, created = jobs.enqueue_with_limit(
        user_id,
        kind,
        key,
        job_payload,
        since=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=window_hours),
        limit=limit,
    )
    if job_id is None:
        raise HTTPException(status_code=429, detail=limit_message)
    job = jobs.get_owned_job(job_id, user_id)
    if job is None:  # Defensive: enqueue committed this exact owner-scoped row.
        raise HTTPException(status_code=500, detail="review job unavailable")
    return ReviewJobAccepted(job_id=job_id, status=job.status, created=created)


@router.post("/reviews/weekly", status_code=status.HTTP_202_ACCEPTED)
def enqueue_weekly_recap(
    payload: WeeklyRecapRequest,
    user_id: int = Depends(current_user),
) -> ReviewJobAccepted:
    """Queue one weekly recap for a completed week of the owner's own trades."""
    monday = _iso_date(payload.week, monday=True)
    today = _today(user_id)
    options = review_periods.completed_week_options(user_id, today=today)
    if dt.date.fromisoformat(monday) not in options:
        raise HTTPException(status_code=409, detail="empty_period")
    model_input = weekly.build_weekly_model_input(user_id, monday, as_of=today)
    if not model_input["source_trade_ids"]:
        raise HTTPException(status_code=409, detail="empty_period")
    eligible_trades = review_inputs.on_or_before(get_trades(user_id=user_id), today)
    complete = sum(1 for t in eligible_trades if activation.is_complete_trade(t))
    if (
        complete < activation.TRADES_FOR_REVIEW
        and weekly.get_weekly_review(monday, user_id) is None
    ):
        raise HTTPException(status_code=409, detail="not_enough_trades")
    return _enqueue_review(
        user_id,
        weekly.WEEKLY_JOB_KIND,
        monday,
        model_input,
        limit=weekly.MAX_WEEKLY_PER_WINDOW,
        window_hours=weekly.REVIEW_WINDOW_HOURS,
        limit_message=WEEKLY_LIMIT_MESSAGE,
    )


@router.post("/reviews/daily", status_code=status.HTTP_202_ACCEPTED)
def enqueue_daily_debrief(
    payload: DailyDebriefRequest,
    user_id: int = Depends(current_user),
) -> ReviewJobAccepted:
    """Queue one daily debrief for a completed trading day of the owner's own."""
    day = _iso_date(payload.day)
    today = _today(user_id)
    options = review_periods.completed_day_options(user_id, today=today)
    if dt.date.fromisoformat(day) not in options:
        raise HTTPException(status_code=409, detail="empty_period")
    model_input = debrief.build_daily_model_input(user_id, day, as_of=today)
    if not model_input["source_trade_ids"]:
        raise HTTPException(status_code=409, detail="empty_period")
    return _enqueue_review(
        user_id,
        debrief.DAILY_JOB_KIND,
        day,
        model_input,
        limit=debrief.MAX_DAILY_PER_WINDOW,
        window_hours=debrief.REVIEW_WINDOW_HOURS,
        limit_message=DAILY_LIMIT_MESSAGE,
    )


def _saved_note(kind: str, result_id: int, user_id: int) -> Optional[SavedNote]:
    if kind == "weekly_recap":
        return _note(weekly.get_weekly_review_by_id(result_id, user_id), "week_start")
    return _note(daily_debriefs.get_daily_debrief_by_id(result_id, user_id), "day")


@router.get("/reviews/jobs/{job_id}")
def get_review_job(
    job_id: int,
    user_id: int = Depends(current_user),
) -> ReviewJobStatus:
    """One owner-scoped review job; foreign, missing and other kinds are 404."""
    job = jobs.get_owned_job(job_id, user_id)
    if job is None or job.kind not in _REVIEW_KINDS:
        raise HTTPException(status_code=404, detail="review job not found")
    if job.status != "succeeded":
        return ReviewJobStatus(
            job_id=job.id,
            kind=job.kind,
            status=job.status,
            note=None,
            error=job.error if job.status == "failed" else None,
        )
    ref = job.result_ref or ""
    prefix = job.kind + ":"
    tail = ref[len(prefix) :] if ref.startswith(prefix) else ""
    if tail == "superseded":
        return ReviewJobStatus(
            job_id=job.id,
            kind=job.kind,
            status="superseded",
            note=None,
            error=REVIEW_OUT_OF_DATE,
        )
    if not _DIGITS.fullmatch(tail):
        raise HTTPException(status_code=500, detail=_RESULT_UNAVAILABLE)
    note = _saved_note(job.kind, int(tail), user_id)
    if note is None:
        raise HTTPException(status_code=500, detail=_RESULT_UNAVAILABLE)
    return ReviewJobStatus(
        job_id=job.id, kind=job.kind, status="succeeded", note=note, error=None
    )


@router.get("/reviews")
def get_reviews(
    request: Request,
    week: Optional[str] = Query(default=None),
    day: Optional[str] = Query(default=None),
    user_id: int = Depends(current_user),
) -> ReviewsResponse:
    """Patterns, the owner's completed review periods, and saved notes."""
    if set(request.query_params) - _KNOWN:
        raise HTTPException(status_code=422, detail="unsupported query parameter(s)")
    week_iso, day_iso = _iso_date(week, monday=True), _iso_date(day)
    today = _today(user_id)
    trades = review_inputs.on_or_before(get_trades(user_id=user_id), today)
    frame = pd.DataFrame(
        [{c: getattr(t, c, None) for c in PATTERN_COLUMNS} for t in trades]
    )
    if not frame.empty:
        frame = frame[
            frame["trade_date"].notna() & (frame["trade_date"] != "")
        ].reset_index(drop=True)
    strategy = get_active_strategy(user_id)
    saved_week = weekly.get_weekly_review(week_iso, user_id) if week_iso else None
    saved_day = (
        daily_debriefs.get_daily_debrief(user_id=user_id, day=day_iso)
        if day_iso
        else None
    )
    return ReviewsResponse(
        patterns=PatternsLens(
            trades=len(frame),
            stats=_stats(review_periods.period_stats(frame)),
            insights=[_insight(i) for i in patterns.generate_insights(frame, strategy)],
            strategy_included=strategy is not None,
        ),
        weeks=[
            d.isoformat()
            for d in review_periods.completed_week_options(user_id, today=today)
        ],
        days=[
            d.isoformat()
            for d in review_periods.completed_day_options(user_id, today=today)
        ],
        complete_trades=sum(1 for t in trades if activation.is_complete_trade(t)),
        trades_for_review=activation.TRADES_FOR_REVIEW,
        ai_available=bool(is_ai_enabled() or is_demo()),
        weekly=_note(saved_week, "week_start"),
        daily=_note(saved_day, "day"),
    )
