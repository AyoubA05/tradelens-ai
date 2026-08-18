"""Job runner process.

A separate process from the API, in the same image. AI calls run 60-120s and
must not occupy a request worker.

Phase 0 ships the loop with no handlers registered — the handlers arrive with
the features that need them, from Phase 5. An unknown kind fails its job
safely, which is the correct behaviour for a queue that outlives a deploy.
"""

from __future__ import annotations

import logging
import time

from src.tradelens.api.jobs import run_once
from src.tradelens.api.config import validate_worker_runtime

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)

HANDLERS: dict = {}

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
