"""Per-trade AI review as queued work: analysis, journal, grading.

Three properties the happy path does not show:

1. **A result write is conditional, never a read-then-write.** Two jobs for
   one trade can be in flight, and the one that finishes last is not
   necessarily the one the trader started last. Every write is an UPDATE
   predicated on the stored job id being older, with `rowcount` checked.
2. **A confirmation is an absolute fence.** A label the trader confirmed is
   never written by any job, whatever the ordering — there is no timestamp
   comparison on the write path at all. Being the newest job is not enough,
   because clicking re-analyse asks for analysis, not for the trader's own
   judgement to be discarded. Unlocking is an explicit PATCH.
3. **The idempotency key is a fingerprint of the inputs.** An unchanged
   re-request is the same job — including a failed one, which stays terminal.
   A genuinely edited trade is a different key and a different job. There is
   no separate cache: the queue row is the cache entry.

No Streamlit imports here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from src.tradelens.api import storage
from src.tradelens.config import ANTHROPIC_MODEL_ID, settings
from src.tradelens.db.models import AIAnalysis, Strategy, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ai_text_guard import (
    ForwardLookingContent,
    fence,
    reject_forward_looking,
)
from src.tradelens.services.corrections import build_correction_few_shot
from src.tradelens.services.journal import (
    JournalStructureError,
    build_journal_context,
    generate_journal,
)
from src.tradelens.services.ownership import require_user_id
from src.tradelens.services.strategy import get_active_strategy
from src.tradelens.services.vision import (
    ScreenshotAnalysisError,
    analyze_screenshot_v3,
    check_screenshot_quality,
)

ANALYSIS_JOB_KIND = "trade_analysis"
JOURNAL_JOB_KIND = "trade_journal"
GRADE_JOB_KIND = "trade_grade"

# The prompt files these kinds consume. `prompts/` is LOCKED — these names
# select an existing template, and a change here is a change of input, which
# is why each one is part of its fingerprint below.
ANALYSIS_PROMPT_VERSION = "screenshot_v3"
JOURNAL_PROMPT_VERSION = "journal_v1"
GRADE_PROMPT_VERSION = "grade_v1"

# One paid Opus call per job, so the same ceiling shape as autofill and
# summaries: generous enough that a trader never feels it, bounded enough
# that an authenticated account cannot mint unlimited billable work. Per
# kind, deliberately — see design decision 7.
MAX_ANALYSES_PER_WINDOW = 20
MAX_JOURNALS_PER_WINDOW = 20
MAX_GRADES_PER_WINDOW = 20
ANALYSIS_WINDOW_HOURS = 24

_log = logging.getLogger(__name__)


def _strategy_fingerprint(user_id: int) -> str:
    """A stable digest of the owner's ACTIVE Strategy Profile.

    `generate_journal` and `grade_trade` both take this profile, so editing
    it in Settings genuinely changes the answer. Its `updated_at` is enough
    to catch an edit: the profile upsert sets it on every write.

    The `is_active == 1` filter mirrors `strategy.get_active_strategy`, which
    is what actually feeds those two calls, and it is load-bearing rather
    than tidy. An owner may hold several profiles. Without it this function
    takes an arbitrary row, so *switching which profile is active* — a real
    change of AI input — could leave the digest still, and the cached job
    would be served back carrying the other profile's reasoning. Two
    requests may share a job only if they would produce the same answer, and
    selecting a different row than the caller does breaks exactly that.

    Both columns are included: `id` moves when the active profile changes,
    `updated_at` when the active one is edited in place.
    """
    db = SessionLocal()
    try:
        row = (
            db.query(Strategy.id, Strategy.updated_at)
            .filter(Strategy.user_id == user_id, Strategy.is_active == 1)
            .first()
        )
    finally:
        db.close()
    return "none" if row is None else f"{row[0]}:{row[1]}"


def _corrections_fingerprint(user_id: int) -> str:
    """A digest of the exact `<past_corrections>` block this owner's calls get.

    Fingerprints the rendered block rather than a proxy for it. An earlier
    version used `(count, max(id))` and justified it as "corrections are
    append-only". That premise is false: `trade_service.delete_all_trades`
    and `account` deletion both bulk-DELETE `Correction` rows, so the count
    falls. And on SQLite a rowid is reused once the highest row is gone — so
    deleting an owner's only correction and recording another returns the
    same `(1, 1)` pair for a genuinely different block. The proxy could
    collide exactly, which is the one thing a cache key may not do.

    Digesting the block itself makes the term exact by construction: two
    states share a key only when the text injected into the prompt is
    byte-identical, which is precisely when they would produce the same
    answer. Budget truncation is included for free — if two histories render
    the same truncated block, the prompts really are the same.

    This term is what makes "correct the AI, then re-run" work: without it
    the re-run matches the cached job the correction was meant to change.
    """
    block = build_correction_few_shot(user_id=user_id) or ""
    return hashlib.sha256(block.encode("utf-8")).hexdigest()[:16]


class AIInputVersionUnavailable(Exception):
    """Raised when the AI context cannot be fingerprinted right now.

    Not a failure of the AI — a refusal to guess at cache identity. Callers
    must decline to enqueue and tell the trader to try again; they must
    never substitute a placeholder digest.
    """


def ai_input_version(user_id: int) -> str:
    """Everything OTHER than the trade that can change an AI answer.

    Model, effort, demo mode, the Strategy Profile and the correction memory.
    Collapsed into one short digest so each key stays readable and so a
    future input is added in exactly one place.

    **Fails closed.** An earlier draft degraded to a constant on any lookup
    error, on the reasoning that a raising digest takes enqueue down for all
    three kinds. That trade was wrong, and the reasoning that excused it —
    "it can never make one owner read another's work" — answered a question
    nobody was asking. Cross-tenant reuse was never the risk: `ai_jobs` is
    unique on `(user_id, idempotency_key)`. The risk is entirely inside one
    trader's own account, which is where it is hardest to notice.

    Concretely, with a constant: the trader corrects the AI, the lookup is
    briefly unavailable, and the new request keys to the same `unavailable`
    digest as an earlier one. `enqueue_with_limit` then returns that earlier
    job — a finished result computed under the previous Strategy Profile or
    the previous correction set — presented as the answer to the new
    question. The key IS the cache here; there is no second layer that would
    catch it, and nothing anywhere says the answer is stale.

    So this raises, and every key built from it raises with it. Refusing
    costs the trader a retry. Guessing costs them a wrong answer they have
    no way to detect.
    """
    owner = require_user_id(user_id)
    try:
        state = (
            _strategy_fingerprint(owner),
            _corrections_fingerprint(owner),
        )
    except Exception as exc:  # noqa: BLE001 — re-raised as a typed refusal
        _log.error("ai_input_version unavailable (%s)", type(exc).__name__)
        raise AIInputVersionUnavailable("the AI context could not be read") from exc
    return hashlib.sha256(
        "|".join(
            (
                ANTHROPIC_MODEL_ID,
                str(settings.effort_default),
                str(bool(settings.demo_mode)),
                *state,
            )
        ).encode("utf-8")
    ).hexdigest()[:16]


def _fingerprint(kind: str, *parts) -> str:
    """A stable key over the inputs that actually change the answer.

    Namespaced by kind because journal and grading share every input: without
    the prefix, enqueuing a grade would return the journal's job and the
    trader would poll one feature and be shown the other.
    """
    digest = hashlib.sha256(
        "|".join(str(part) for part in parts).encode("utf-8")
    ).hexdigest()
    return f"{kind}:{digest}"


def analysis_key(
    user_id: int, trade_id: int, screenshot_id: int, trade_updated_at
) -> str:
    return _fingerprint(
        ANALYSIS_JOB_KIND,
        trade_id,
        screenshot_id,
        trade_updated_at,
        ANALYSIS_PROMPT_VERSION,
        ai_input_version(user_id),
    )


def journal_key(
    user_id: int, trade_id: int, trade_updated_at, analysis_updated_at
) -> str:
    return _fingerprint(
        JOURNAL_JOB_KIND,
        trade_id,
        trade_updated_at,
        analysis_updated_at,
        JOURNAL_PROMPT_VERSION,
        ai_input_version(user_id),
    )


def grade_key(
    user_id: int, trade_id: int, trade_updated_at, analysis_updated_at
) -> str:
    return _fingerprint(
        GRADE_JOB_KIND,
        trade_id,
        trade_updated_at,
        analysis_updated_at,
        GRADE_PROMPT_VERSION,
        ai_input_version(user_id),
    )


# The AI-owned label columns on `aianalysis` that an analysis job writes,
# mapped from the vision result. Anything not here is not an analysis output.
# Task C1's confirm endpoint reads this same list, so the write and the
# confirm can never disagree about what a label is.
_ANALYSIS_LABEL_FIELDS = ("bias", "trade_quality", "matched_strategy")


@dataclass(frozen=True)
class WriteOutcome:
    """What happened to one worker's attempt to store its result.

    `superseded` is not an error: being overtaken by a newer job is a normal
    outcome of a queue, and a job that reports it did its work correctly.

    `locked` names the fields this write deliberately did not touch because
    the trader has confirmed them. Reported rather than inferred, so the
    panel can say "your bias was kept" instead of leaving the trader to
    notice that one value did not move.
    """

    written: bool
    superseded: bool
    locked: frozenset = frozenset()


def confirmed_fields(analysis) -> frozenset:
    """Which label fields the trader has confirmed, from the stored JSON.

    Parsed defensively: a row that outlives a deploy, or one written before
    this column existed, yields the empty set — which fences nothing and lets
    the normal write through. That is the safe direction, because the
    alternative is a stored value nobody can ever refresh.
    """
    if analysis is None:
        return frozenset()
    try:
        parsed = json.loads(analysis.confirmed_fields_json or "[]")
    except (ValueError, TypeError):
        return frozenset()
    if not isinstance(parsed, list):
        return frozenset()
    return frozenset(str(item) for item in parsed)


def _owned_trade_id(db, trade_id: int, owner: int) -> Optional[int]:
    row = (
        db.query(Trade.id).filter(Trade.id == trade_id, Trade.user_id == owner).first()
    )
    return None if row is None else int(row[0])


def store_analysis(
    user_id: int,
    trade_id: int,
    *,
    job_id: int,
    vision_result: dict,
    usage,
) -> WriteOutcome:
    """Store one analysis result under the ordering guard and the lock.

    Two rules, and they are independent:

    * **Ordering.** The job-id predicate lives in the UPDATE's WHERE clause,
      so a slow older job writes zero rows rather than landing on a newer
      result. Deliberately not a read-then-write: between a SELECT and an
      UPDATE the other job commits, which is precisely the race this exists
      to lose safely. `<` and not `<=`, so a redelivered job does not rewrite
      its own result.
    * **The confirmation lock.** A field the trader has confirmed is dropped
      from the write, whenever this job was enqueued. There is no timestamp
      comparison anywhere on this path, on purpose: "the trader's value
      stands until the trader changes it" is a rule with no window in which
      it fails, and ordering was never a good reason to discard a human
      judgement. See design decision 3 for why the first draft of this plan
      had it the other way round, and why that was wrong. Unlocking is an
      explicit PATCH (Task C1), never a race.

    The locked field's fresh reading is still stored in `raw_response_json`,
    which always holds the newest complete model output. Locked means "not
    applied", never "hidden": the panel offers the new proposal for one-click
    adoption (Task D3).

    Raises `ValueError` when the trade is not this owner's: `aianalysis` has
    no `user_id`, so the trade join is the only ownership statement there is.
    """
    owner = require_user_id(user_id)
    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        if _owned_trade_id(db, trade_id, owner) is None:
            raise ValueError("trade not found")

        existing = db.query(AIAnalysis).filter(AIAnalysis.trade_id == trade_id).first()

        values = {
            "model": getattr(usage, "model", None),
            "prompt_version": ANALYSIS_PROMPT_VERSION,
            "bias": vision_result.get("bias"),
            "zones_json": json.dumps(vision_result.get("key_zones", [])),
            "matched_strategy": vision_result.get("matched_strategy"),
            "mistakes_json": json.dumps(vision_result.get("possible_mistakes", [])),
            "missed_opps_json": json.dumps(
                vision_result.get("missed_opportunities", [])
            ),
            "trade_quality": vision_result.get("trade_quality"),
            "raw_response_json": json.dumps(vision_result),
            "tokens_input": getattr(usage, "tokens_in", None),
            "tokens_output": getattr(usage, "tokens_out", None),
            "cost_usd": getattr(usage, "estimated_cost_usd", None),
            "analysis_job_id": job_id,
            "updated_at": now,
        }

        if existing is None:
            # The only write on this path without a predicate, because there
            # is no row yet to predicate on. Two first-ever jobs for one
            # trade both see None; the `trade_id` unique constraint decides,
            # and the loser reports `superseded` rather than failing a job
            # over a race it handled correctly. Caught, not pre-checked —
            # between a SELECT and an INSERT the other job commits.
            try:
                db.add(AIAnalysis(trade_id=trade_id, created_at=now, **values))
                db.commit()
                return WriteOutcome(written=True, superseded=False)
            except IntegrityError:
                db.rollback()
                return WriteOutcome(written=False, superseded=True)

        # The confirmation lock. Intersected with `values` first, so a stored
        # name that is not one of this write's own keys — a stray entry, a
        # renamed column, a hostile string — can never make an unrelated
        # column unwritable. `raw_response_json` is deliberately NOT lockable:
        # it is the newest model output, and keeping it current is what lets
        # the panel offer the locked field's fresh proposal.
        locked = frozenset(confirmed_fields(existing)) & set(values)
        locked -= {"raw_response_json", "analysis_job_id", "updated_at"}
        for field in locked:
            values.pop(field, None)

        written = db.execute(
            update(AIAnalysis)
            .where(
                AIAnalysis.trade_id == trade_id,
                (AIAnalysis.analysis_job_id.is_(None))
                | (AIAnalysis.analysis_job_id < job_id),
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        if written.rowcount != 1:
            return WriteOutcome(written=False, superseded=True, locked=locked)
        return WriteOutcome(written=True, superseded=False, locked=locked)
    finally:
        db.close()


# The promoted object always has this extension: `finalize_upload` normalises
# every image to one content type, so this is not a guess.
_FINAL_SUFFIX = ".png"


class AnalysisUnavailable(Exception):
    """Raised when analysis cannot run — no readable image, or a bad response.

    Terminal by construction: the job runner marks the job failed, and the
    input fingerprint means a resubmit for the same inputs returns that failed
    job instead of spending again.
    """


def _analyse_bytes(data: bytes, on_usage) -> dict:
    """Quality-check then analyse promoted bytes, returning raw v3 output.

    The bytes are materialised to a temp file only because the vision client
    takes a path. This is not a second image path: these bytes already passed
    `imaging.validate_and_normalise` and were written by us. The file is
    removed on every exit.
    """
    handle, temp_path = tempfile.mkstemp(suffix=_FINAL_SUFFIX)
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(data)
        if not check_screenshot_quality(temp_path).usable:
            # Refused before any billable call: an image the local pre-check
            # cannot open will not be readable by the model either.
            raise AnalysisUnavailable("that screenshot could not be read")
        try:
            analysis, _usage = analyze_screenshot_v3(
                temp_path, {}, None, on_usage=on_usage
            )
        except ScreenshotAnalysisError as exc:
            raise AnalysisUnavailable(str(exc)) from exc
        return analysis
    finally:
        try:
            os.unlink(temp_path)
        except OSError:  # pragma: no cover — best effort, never masks a result
            pass


def run_analysis(
    user_id: int,
    trade_id: int,
    screenshot_id: int,
    *,
    job_id: int,
    on_usage,
) -> WriteOutcome:
    """Analyse one owned screenshot and store the result under the guards.

    Bytes come from `storage.read_owned_final_object` and from nowhere else:
    that function enforces the ownership join AND `_is_final_key`, so a
    quarantine-keyed row cannot be turned into a read of un-re-encoded bytes.

    `Usage` is captured through the callback rather than returned, because it
    must reach cost tracking the instant the provider answers — everything
    after that can raise, and a billed call that never appears in cost
    tracking is worse than no tracking at all.
    """
    owner = require_user_id(user_id)
    data = storage.read_owned_final_object(owner, screenshot_id)
    if not data:
        raise AnalysisUnavailable("that screenshot could not be read")

    captured = {}

    def _capture(usage):
        # Fires the instant the provider answers, before anything below can
        # raise. The caller's callback runs first so cost tracking never
        # depends on the rest of this function succeeding.
        on_usage(usage)
        captured["usage"] = usage

    analysis = _analyse_bytes(data, _capture)
    descriptive = analysis.get("descriptive") or {}
    return store_analysis(
        owner,
        trade_id,
        job_id=job_id,
        vision_result=descriptive,
        usage=captured.get("usage"),
    )


# Trader-typed fields that reach a prompt. Each is bounded and fenced, so a
# note cannot lengthen the prompt without limit and cannot forge the end of
# its own block. See `ai_text_guard` for why this is a floor, not a cure.
_UNTRUSTED_TRADE_FIELDS = (
    "notes",
    "emotions_before",
    "emotions_during",
    "emotions_after",
)


def _sanitised_trade_context(trade_dict: dict) -> dict:
    """Bound and fence every trader-typed value in a prompt context dict.

    Returns a copy: the caller's dict is built from ORM columns and must not
    be mutated into a shape that could be written back anywhere.
    """
    out = dict(trade_dict)
    for field in _UNTRUSTED_TRADE_FIELDS:
        if out.get(field):
            out[field] = fence(field, out[field])
    return out


def _generate_journal_markdown(trade_dict: dict, ai_dict: dict, strategy, on_usage):
    """The provider call, isolated so tests can replace exactly this seam."""
    markdown, usage = generate_journal(trade_dict, ai_dict, strategy_profile=strategy)
    # Before validation, deliberately: the call was billed whether or not the
    # response turns out to be usable, and the post-trade-only check below
    # rejects some responses outright.
    on_usage(usage)
    return markdown


def _load_for_generation(owner: int, trade_id: int):
    """The trade and its analysis, or a refusal. Shared by journal and grade."""
    db = SessionLocal()
    try:
        if _owned_trade_id(db, trade_id, owner) is None:
            raise ValueError("trade not found")
        trade = db.query(Trade).filter(Trade.id == trade_id).one()
        analysis = db.query(AIAnalysis).filter(AIAnalysis.trade_id == trade_id).first()
        if analysis is None:
            raise AnalysisUnavailable(
                "run the screenshot analysis first — this builds on it"
            )
        return trade, analysis
    finally:
        db.close()


def run_journal(user_id: int, trade_id: int, *, job_id: int, on_usage) -> WriteOutcome:
    """Generate and store one journal entry, under the same ordering guard.

    The output is validated twice and stored once: `generate_journal` already
    enforces the eight ordered headings, and `reject_forward_looking` refuses
    anything that reads as a trade idea rather than a reflection. A response
    failing either is a failed job — never stored, never shown. A journal
    telling a trader what to buy next session is the single worst thing this
    product could emit, so it is checked rather than asked for.

    Writes `journal_entry_md` and its own job column only. The analysis
    labels are untouched, confirmed or not: a journal is prose about a trade,
    not a new reading of it.
    """
    owner = require_user_id(user_id)
    trade, analysis = _load_for_generation(owner, trade_id)
    trade_dict, ai_dict = build_journal_context(trade, analysis)

    try:
        markdown = _generate_journal_markdown(
            _sanitised_trade_context(trade_dict),
            ai_dict,
            get_active_strategy(owner),
            on_usage,
        )
        reject_forward_looking(markdown)
    except (JournalStructureError, ForwardLookingContent, ValueError) as exc:
        raise AnalysisUnavailable(str(exc)) from exc

    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        written = db.execute(
            update(AIAnalysis)
            .where(
                AIAnalysis.trade_id == trade_id,
                (AIAnalysis.journal_job_id.is_(None))
                | (AIAnalysis.journal_job_id < job_id),
            )
            .values(journal_entry_md=markdown, journal_job_id=job_id, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        if written.rowcount != 1:
            return WriteOutcome(written=False, superseded=True)
        return WriteOutcome(written=True, superseded=False)
    finally:
        db.close()
