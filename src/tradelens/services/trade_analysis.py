"""Per-trade AI review as queued work: analysis, journal, grading.

Three properties the happy path does not show:

1. **A result write is conditional, never a read-then-write.** Two jobs for
   one trade can be in flight, and the one that finishes last is not
   necessarily the one the trader started last. Every write is an UPDATE
   predicated on the stored job id being older, with `rowcount` checked.
2. **A confirmation is a fence.** A job enqueued before the trader confirmed
   a label may not replace that label. Being newest is not enough; it has to
   be newer than the trader's own decision.
3. **The idempotency key is a fingerprint of the inputs.** An unchanged
   re-request is the same job — including a failed one, which stays terminal.
   A genuinely edited trade is a different key and a different job. There is
   no separate cache: the queue row is the cache entry.

No Streamlit imports here.
"""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy import func

from src.tradelens.config import ANTHROPIC_MODEL_ID, settings
from src.tradelens.db.models import Correction, Strategy
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ownership import require_user_id

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
    """A stable digest of the owner's correction memory.

    Corrections are append-only — `record_correction` only ever INSERTs — so
    `(count, max(id))` moves whenever the `<past_corrections>` block would
    change, and never otherwise. Two numbers, one query, no block to render.

    This term is what makes "correct the AI, then re-run" work: without it
    the re-run matches the cached job the correction was meant to change.
    """
    db = SessionLocal()
    try:
        count, newest = (
            db.query(func.count(Correction.id), func.max(Correction.id))
            .filter(Correction.user_id == user_id)
            .one()
        )
    finally:
        db.close()
    return f"{int(count or 0)}:{int(newest or 0)}"


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
