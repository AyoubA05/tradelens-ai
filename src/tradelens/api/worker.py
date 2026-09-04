"""Job runner process.

A separate process from the API, in the same image. AI calls run 60-120s and
must not occupy a request worker.

Phase 3E registers the first handler, the filtered-trade summary. Later AI
features add their own entries to the same registry. An unknown kind fails its
job safely, which is the correct behaviour for a queue that outlives a deploy.
"""

from __future__ import annotations

import logging
import time

from src.tradelens.api.jobs import run_once
from src.tradelens.api import jobs
from src.tradelens.api.config import validate_worker_runtime
from src.tradelens.services.cost import log_ai_usage
from src.tradelens.services.trade_autofill import (
    JOB_KIND as AUTOFILL_JOB_KIND,
    suggest_from_screenshot,
)
from src.tradelens.services.trade_analysis import (
    ANALYSIS_JOB_KIND,
    run_analysis,
)
from src.tradelens.services.trade_summary import (
    generate_trade_summary,
    save_trade_summary_result,
)

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)


def _trade_summary_handler(user_id: int, payload: dict) -> str:
    # Usage is recorded through this callback the moment the provider answers,
    # not after the result is saved: generation raises on a malformed response
    # and that call is still billed. Cost tracking that goes silent exactly when
    # something went wrong is worse than none.
    result, _usage = generate_trade_summary(
        payload["trades"],
        period_label=payload["period_label"],
        on_usage=lambda usage: log_ai_usage("Trade Summary", usage, user_id=user_id),
    )
    result_id = save_trade_summary_result(
        user_id=user_id,
        summary_key=payload["summary_key"],
        filters=payload.get("filters") or {},
        result=result,
    )
    return f"trade_summary:{result_id}"


def _trade_autofill_handler(user_id: int, payload: dict) -> str:
    # Same usage discipline as the summary handler, and for the same reason:
    # the callback is handed down to the provider call so a response that then
    # fails to parse is still billed-and-visible.
    #
    # The handler writes suggestions onto the owner's draft and returns a
    # pointer, never a trade. An exception here leaves the job `failed` and
    # terminal — the enqueue idempotency key means a resubmit for the same
    # screenshot returns that failed job instead of spending again.
    screenshot_id = int(payload["screenshot_id"])
    key = f"{AUTOFILL_JOB_KIND}:{screenshot_id}"
    job = jobs.get_owned_job_by_idempotency_key(user_id, AUTOFILL_JOB_KIND, key)
    if job is None:
        raise RuntimeError("autofill job unavailable")
    suggest_from_screenshot(
        user_id,
        screenshot_id,
        job_id=int(job.id),
        on_usage=lambda usage: log_ai_usage("Trade Autofill", usage, user_id=user_id),
    )
    return f"{AUTOFILL_JOB_KIND}:{screenshot_id}"


def _phase5_job_id(user_id: int, kind: str, payload: dict) -> int:
    """The id of the job now running, resolved from its own payload.

    `run_once` hands a handler `(user_id, payload)` and not the job row, and
    every Phase 5 write is ordered by job id, so the handler has to recover
    it. The idempotency key is written into the payload at enqueue time
    rather than re-derived here: `ai_input_version` moves whenever the owner
    corrects something, so a handler that recomputed the key could fail to
    find its own job. Owner-scoped lookup, so a payload cannot name another
    tenant's row.
    """
    job = jobs.get_owned_job_by_idempotency_key(user_id, kind, payload["key"])
    if job is None:
        raise RuntimeError("job unavailable")
    return int(job.id)


def _trade_analysis_handler(user_id: int, payload: dict) -> str:
    # Same usage discipline as the summary and autofill handlers: the
    # callback is handed down to the provider call so a response that then
    # fails to parse is still billed-and-visible.
    outcome = run_analysis(
        user_id,
        int(payload["trade_id"]),
        int(payload["screenshot_id"]),
        job_id=_phase5_job_id(user_id, ANALYSIS_JOB_KIND, payload),
        on_usage=lambda usage: log_ai_usage("Trade Analysis", usage, user_id=user_id),
    )
    return (
        f"{ANALYSIS_JOB_KIND}:{payload['trade_id']}:"
        f"{'stored' if outcome.written else 'superseded'}"
    )


HANDLERS: dict = {
    "trade_summary": _trade_summary_handler,
    AUTOFILL_JOB_KIND: _trade_autofill_handler,
    ANALYSIS_JOB_KIND: _trade_analysis_handler,
}

IDLE_SLEEP_SECONDS = 2.0


def main() -> None:
    validate_worker_runtime()
    _log.info("worker started with %d handler(s)", len(HANDLERS))
    while True:
        try:
            if not run_once(HANDLERS):
                time.sleep(IDLE_SLEEP_SECONDS)
        except Exception as exc:  # noqa: BLE001 — a worker must outlive one bad job
            _log.error("worker loop error (%s)", type(exc).__name__)
            time.sleep(IDLE_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
