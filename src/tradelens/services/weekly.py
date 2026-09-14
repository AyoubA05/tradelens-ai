"""
Weekly AI review service.

Gathers a Monday→Sunday window of trades, computes week stats + a deterministic
pattern pre-pass, folds in recent corrections as a few-shot block, and asks
Claude Opus 5 (effort="high", thinking summarized) for a structured 5-section
review via prompts/weekly_v2.txt. Reviews persist to the weekly_reviews table;
re-running the same week overwrites only with explicit confirmation.

This is post-trade reflection only — never live signals, predictions, or advice.
No Streamlit imports here. DEMO_MODE returns a canned review (zero API spend).
"""

import datetime as dt
import json
import math
from typing import Callable, Optional, Union

import pandas as pd

from src.tradelens.db.models import WeeklyReview
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ai_client import AIUnavailable, Usage, chat, load_prompt
from src.tradelens.services.metrics import (
    compute_basic_metrics,
    compute_profit_factor_raw,
    total_edge_leak,
)
from src.tradelens.services.ownership import require_user_id
from src.tradelens.services.patterns import compute_candidates
from src.tradelens.services.reflection_guard import reject_forward_looking
from src.tradelens.services.trade_service import get_trades

# Item 10 — unified Weekly Recap: one AI call covers the review AND the
# pattern signals (the app renders the performance snapshot from stats).
_REQUIRED_SECTIONS = [
    "### What Worked",
    "### What Didn't",
    "### Observed Patterns",
    "### Rule Adherence",
    "### Focus for Next Week",
]

# Columns the metrics/patterns engines expect from each trade row.
_TRADE_COLS = [
    "trade_date",
    "day_of_week",
    "result",
    "pnl",
    "rr_realized",
    "killzone",
    "confirmation_model",
    "mistake_tags",
    "htf_bias",
    "setup_type",
    "followed_rules",
]

# Job-backed generation (Phase 10A, R3/R4). The kind names the `ai_jobs` row;
# the effort literal is part of the effective-input fingerprint (C2).
WEEKLY_JOB_KIND = "weekly_recap"
MAX_WEEKLY_PER_WINDOW = 10
REVIEW_WINDOW_HOURS = 24
WEEKLY_EFFORT = "high"

_UNSET = object()

# Canned review returned in DEMO_MODE (zero spend) — satisfies the 5-section contract.
_DEMO_REVIEW_MD = "\n\n".join(
    f"{h}\n\n_DEMO MODE_ — sample reflection for this section."
    for h in _REQUIRED_SECTIONS
)


_NO_PROFILE_BLOCK = (
    "No strategy profile provided — use the generic SMC/ICT process framework "
    "(price action, risk management, entry quality, exit quality, "
    "emotional discipline, journaling quality)."
)


class WeeklyReviewError(Exception):
    """Raised when the AI weekly review is unavailable or missing required sections."""


class WeeklyReviewExistsError(Exception):
    """Raised when saving a review for a week that already has one (without overwrite)."""


# ---------------------------------------------------------------------------
# Week window
# ---------------------------------------------------------------------------


def week_bounds(value: Union[str, dt.date, dt.datetime]) -> tuple:
    """Return (monday_iso, sunday_iso) for the ISO week containing `value`."""
    if isinstance(value, str):
        d = dt.date.fromisoformat(value[:10])
    elif isinstance(value, dt.datetime):
        d = value.date()
    else:
        d = value
    monday = d - dt.timedelta(days=d.weekday())
    sunday = monday + dt.timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------


def _trades_to_df(trades: list) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=_TRADE_COLS)
    return pd.DataFrame([{c: getattr(t, c, None) for c in _TRADE_COLS} for t in trades])


def _week_stats(df: pd.DataFrame) -> dict:
    """Headline week stats for the sidebar + persisted history. JSON-safe (no inf)."""
    if df is None or df.empty:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "profit_factor": None,
            "total_edge_leak": 0.0,
        }
    m = compute_basic_metrics(df)
    pf = compute_profit_factor_raw(df)
    return {
        "trades": int(m["total_trades"]),
        "win_rate": m["win_rate"],
        "total_pnl": m["total_pnl"],
        "profit_factor": None if math.isinf(pf) else pf,
        "total_edge_leak": total_edge_leak(df),
    }


def _build_user_message(
    monday: str,
    sunday: str,
    stats: dict,
    candidates: dict,
    strategy_profile: Optional[dict] = None,
) -> str:
    strategy_block = (
        json.dumps(strategy_profile, indent=2, default=str)
        if strategy_profile
        else _NO_PROFILE_BLOCK
    )
    return (
        "WEEKLY REVIEW REQUEST\n\n"
        f"Week: {monday} (Mon) to {sunday} (Sun)\n\n"
        f"Headline stats:\n{json.dumps(stats, indent=2, default=str)}\n\n"
        "Deterministic pattern statistics for the week:\n"
        f"{json.dumps(candidates, indent=2, default=str)}\n\n"
        f"Strategy profile:\n{strategy_block}\n\n"
        "Write the 5-section weekly review now."
    )


def _validate_sections(markdown: str) -> None:
    positions = []
    for section in _REQUIRED_SECTIONS:
        idx = markdown.find(section)
        if idx == -1:
            raise WeeklyReviewError(
                f"Weekly review is missing required section: '{section}'"
            )
        positions.append(idx)
    if positions != sorted(positions):
        raise WeeklyReviewError("Weekly review sections are out of order.")


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def _ordered(trades: list) -> list:
    """`get_trades` order (newest date first) with a stable id tiebreak.

    Streak candidates depend on row order, so the same trades must always
    arrive in the same order for the fingerprint and the prompt to agree.
    """
    by_id = sorted(trades, key=lambda t: getattr(t, "id", None) or 0)
    return sorted(
        by_id, key=lambda t: str(getattr(t, "trade_date", "") or ""), reverse=True
    )


def build_weekly_model_input(
    user_id: int,
    monday: Union[str, dt.date, dt.datetime],
    *,
    strategy_profile=_UNSET,
    trades: Optional[list] = None,
) -> dict:
    """The exact object the weekly user message is built from (decision C2).

    `strategy_profile` defaults to the owner's active profile; `trades`
    defaults to the owner's trades for the week (the worker passes rows read
    through its locking session). JSON-safe apart from numpy scalars, which
    the fingerprint canonicalises.
    """
    owner = require_user_id(user_id)
    week_monday, sunday = week_bounds(monday)
    if trades is None:
        trades = get_trades(start_date=week_monday, end_date=sunday, user_id=owner)
    if strategy_profile is _UNSET:
        from src.tradelens.services.strategy import get_active_strategy

        strategy_profile = get_active_strategy(owner)
    rows = _ordered(list(trades))
    df = _trades_to_df(rows)
    return {
        "week_start": week_monday,
        "week_end": sunday,
        "stats": _week_stats(df),
        "candidates": None if df.empty else compute_candidates(df),
        "strategy_profile": strategy_profile or None,
        "source_trade_ids": sorted(
            int(t.id) for t in rows if getattr(t, "id", None) is not None
        ),
    }


def generate_weekly_review(
    week_start: Union[str, dt.date, dt.datetime],
    user_id: int,
    strategy_profile: Optional[dict] = None,
    *,
    on_usage: Optional[Callable[[Usage], None]] = None,
    model_input: Optional[dict] = None,
) -> tuple[dict, Usage]:
    """
    Generate (but do not persist) the weekly review for the week containing
    `week_start`. A zero-trade week returns an empty result WITHOUT any API call.

    The owner is required. Only `user_id`'s trades feed the review. When a
    Strategy Profile is provided, discipline is judged against those rules;
    otherwise the generic process framework applies.

    Returns (review_dict, usage). review_dict keys: week_start (ISO Monday),
    empty, content_md, thinking_summary, stats, cost_usd.

    Raises:
        ValueError: user_id is not a valid owner.
        FileNotFoundError: prompts/weekly_v2.txt missing.
        WeeklyReviewError: AI unavailable or response missing required sections.
    """
    owner = require_user_id(user_id)
    if model_input is None:
        model_input = build_weekly_model_input(
            owner, week_start, strategy_profile=strategy_profile
        )
    monday, sunday = model_input["week_start"], model_input["week_end"]
    stats = model_input["stats"]

    if model_input["candidates"] is None:
        return (
            {
                "week_start": monday,
                "empty": True,
                "content_md": None,
                "thinking_summary": None,
                "stats": stats,
                "cost_usd": 0.0,
            },
            Usage("none", 0, 0, 0, 0.0, 0.0),
        )

    system_message = load_prompt("weekly_recap_v1")
    user_message = _build_user_message(
        monday,
        sunday,
        stats,
        model_input["candidates"],
        model_input["strategy_profile"],
    )

    # Past corrections are injected centrally by ai_client for every call.
    content, usage = chat(
        user_message=user_message,
        system_message=system_message,
        effort=WEEKLY_EFFORT,
        demo_response=_DEMO_REVIEW_MD,
    )
    # Recorded the moment the provider answers: a response that then fails
    # validation or the guard was still billed.
    if on_usage is not None:
        on_usage(usage)

    if isinstance(content, AIUnavailable):
        raise WeeklyReviewError(content.reason)

    _validate_sections(content)
    # Lexical defense-in-depth, not a semantic guarantee (decision C4).
    reject_forward_looking(content, WeeklyReviewError)
    return (
        {
            "week_start": monday,
            "empty": False,
            "content_md": content,
            "thinking_summary": usage.thinking_summary,
            "stats": stats,
            "cost_usd": usage.estimated_cost_usd,
        },
        usage,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _row_to_dict(row: WeeklyReview) -> dict:
    try:
        stats = json.loads(row.stats_json) if row.stats_json else {}
    except (json.JSONDecodeError, TypeError):
        stats = {}
    return {
        "id": row.id,
        "week_start": row.week_start,
        "content_md": row.content_md,
        "thinking_summary": row.thinking_summary,
        "stats": stats,
        "cost_usd": row.cost_usd,
        "created_at": row.created_at,
    }


def save_weekly_review(review: dict, user_id: int, overwrite: bool = False) -> dict:
    """
    Persist a generated review, scoped to `user_id`. The owner is required —
    it used to default to None, which filtered and stamped rows with
    `user_id IS NULL`: a write-side hole into the legacy shared tenant that
    the rest of the isolation work exists to close.

    If a review already exists for the same (user, week_start) and overwrite is
    False, raises WeeklyReviewExistsError (the page asks the user to confirm before
    retrying with overwrite=True). Returns the saved row as a dict.

    Raises:
        ValueError: user_id is not a valid owner.
    """
    owner = require_user_id(user_id)
    week_start = review["week_start"]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    db = SessionLocal()
    try:
        existing = (
            db.query(WeeklyReview)
            .filter(
                WeeklyReview.week_start == week_start,
                WeeklyReview.user_id == owner,
            )
            .first()
        )
        if existing is not None and not overwrite:
            raise WeeklyReviewExistsError(
                f"A review for the week of {week_start} already exists."
            )

        if existing is None:
            row = WeeklyReview(week_start=week_start, created_at=now, user_id=owner)
            db.add(row)
        else:
            row = existing

        row.content_md = review.get("content_md")
        row.thinking_summary = review.get("thinking_summary")
        row.stats_json = json.dumps(review.get("stats") or {}, default=str)
        row.cost_usd = review.get("cost_usd")

        db.commit()
        db.refresh(row)
        return _row_to_dict(row)
    finally:
        db.close()


def save_weekly_review_from_sources(
    *,
    user_id: int,
    review: dict,
    source_trade_ids: list,
    input_fingerprint: str,
    job_id: Optional[int],
    verify: Callable,
) -> int:
    """Job-path save: overwrite this week's recap only while its sources hold.

    In one transaction: lock the source trades `FOR UPDATE` (missing or foreign
    → `daily_debriefs.ReviewSourceGone`), run `verify(db)` against that locked
    state (False → `ReviewSourceChanged`), then write with provenance
    (decisions R8, C1, C3). Nothing is written on any failure. Returns the id.
    """
    # Imported here: daily_debriefs is a sibling service; keep import order free.
    from src.tradelens.services.daily_debriefs import lock_and_verify_sources

    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        lock_and_verify_sources(db, owner, source_trade_ids, verify)
        now = dt.datetime.now(dt.timezone.utc)
        row = (
            db.query(WeeklyReview)
            .filter(
                WeeklyReview.week_start == review["week_start"],
                WeeklyReview.user_id == owner,
            )
            .order_by(WeeklyReview.id)
            .with_for_update()
            .first()
        )
        if row is None:
            row = WeeklyReview(
                week_start=review["week_start"],
                created_at=now.isoformat(),
                user_id=owner,
            )
            db.add(row)
        row.content_md = review.get("content_md")
        row.thinking_summary = review.get("thinking_summary")
        row.stats_json = json.dumps(review.get("stats") or {}, default=str)
        row.cost_usd = review.get("cost_usd")
        row.input_fingerprint = str(input_fingerprint)
        row.job_id = None if job_id is None else int(job_id)
        row.updated_at = now
        db.commit()
        return int(row.id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_weekly_review(week_start: str, user_id: int) -> Optional[dict]:
    """Return this user's persisted review for the given ISO Monday, or None.

    The owner is required. It was `Optional[int]` defaulting to None, which
    matched only legacy NULL-owner reviews rather than raising — a missing
    owner looked like a missing review instead of a programming error.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = (
            db.query(WeeklyReview)
            .filter(
                WeeklyReview.week_start == week_start,
                WeeklyReview.user_id == owner,
            )
            .first()
        )
        return _row_to_dict(row) if row else None
    finally:
        db.close()


def get_weekly_review_by_id(result_id: int, user_id: int) -> Optional[dict]:
    """Return one of this owner's saved reviews by id; foreign and missing are None."""
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = (
            db.query(WeeklyReview)
            .filter(WeeklyReview.id == result_id, WeeklyReview.user_id == owner)
            .first()
        )
        return _row_to_dict(row) if row else None
    finally:
        db.close()


def get_weekly_reviews(user_id: int, limit: int = 10) -> list:
    """Return this user's saved reviews (newest week first), capped at `limit`.

    The owner is required, for the same reason as `get_weekly_review`.
    Strictly scoped: a user never sees another user's reviews.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        rows = (
            db.query(WeeklyReview)
            .filter(WeeklyReview.user_id == owner)
            .order_by(WeeklyReview.week_start.desc(), WeeklyReview.id.desc())
            .limit(limit)
            .all()
        )
        return [_row_to_dict(r) for r in rows]
    finally:
        db.close()
