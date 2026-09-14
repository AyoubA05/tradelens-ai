"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { components } from "@/lib/api/schema";

type SavedNote = components["schemas"]["SavedNote"];
type JobAccepted = components["schemas"]["ReviewJobAccepted"];
type JobStatus = components["schemas"]["ReviewJobStatus"];

export type ReviewJobState =
  | "idle"
  | "running"
  | "succeeded"
  | "failed"
  | "superseded"
  | "rate_limited"
  | "refused";

// Copied from `summary-panel.tsx`: the provider timeout is 120s and may include
// retries. Poll immediately, then back off to eight seconds.
const POLL_DELAYS_MS = [1_000, 2_000, 4_000, ...Array.from({ length: 23 }, () => 8_000)];

export const FAILURE_MESSAGE = "The review could not be generated. Try again.";
export const SUPERSEDED_MESSAGE = "This review is out of date. Generate it again.";
const RATE_LIMIT_FALLBACK =
  "You've reached today's limit for AI reviews. Reviews you've already generated are still available.";
const REFUSALS: Record<string, string> = {
  empty_period: "Nothing is logged for this period.",
  not_enough_trades: "Journal more completed trades before a weekly recap.",
};

class Aborted extends Error {}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new Aborted());
      },
      { once: true },
    );
  });
}

/**
 * Enqueue one review and poll it to an end state.
 *
 * Nothing here runs on its own: `start` is called only from an explicit click.
 * A second `start` while one is running is ignored, so a double click cannot
 * enqueue twice. A failure never retries automatically. Unmounting aborts the
 * run and no state is set afterwards.
 *
 * `note` is the last successfully generated note and is never cleared by a
 * later failure — the lens shows it (or the saved note) until a success
 * replaces it. Every message is a fixed client string or the relay's
 * rate-limit sentence; job error text is never shown.
 */
export function useReviewJob(endpoint: "/api/reviews/weekly" | "/api/reviews/daily") {
  const [state, setState] = useState<ReviewJobState>("idle");
  const [note, setNote] = useState<SavedNote | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);
  const running = useRef(false);

  useEffect(
    () => () => {
      active.current?.abort();
    },
    [],
  );

  const start = useCallback(
    async (body: object) => {
      if (running.current) return;
      running.current = true;
      const controller = new AbortController();
      active.current = controller;
      const { signal } = controller;
      const guard = () => {
        if (signal.aborted) throw new Aborted();
      };
      const settle = (next: ReviewJobState, text: string | null) => {
        if (signal.aborted || active.current !== controller) return;
        setState(next);
        setMessage(text);
      };

      setState("running");
      setMessage(null);

      try {
        const queuedResponse = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          cache: "no-store",
          credentials: "same-origin",
          signal,
        });
        guard();
        if (queuedResponse.status === 429 || queuedResponse.status === 409) {
          const payload = (await queuedResponse.json().catch(() => null)) as {
            detail?: unknown;
          } | null;
          guard();
          const detail = typeof payload?.detail === "string" ? payload.detail : null;
          if (queuedResponse.status === 429) {
            settle("rate_limited", detail ?? RATE_LIMIT_FALLBACK);
          } else if (detail && detail in REFUSALS) {
            settle("refused", REFUSALS[detail]!);
          } else {
            settle("failed", FAILURE_MESSAGE);
          }
          return;
        }
        if (!queuedResponse.ok) throw new Error("enqueue failed");
        const queued = (await queuedResponse.json()) as JobAccepted;
        guard();

        for (let attempt = 0; attempt <= POLL_DELAYS_MS.length; attempt += 1) {
          if (attempt > 0) await wait(POLL_DELAYS_MS[attempt - 1]!, signal);
          const pollResponse = await fetch(`/api/reviews/jobs/${queued.job_id}`, {
            cache: "no-store",
            credentials: "same-origin",
            signal,
          });
          guard();
          if (!pollResponse.ok) throw new Error("poll failed");
          const job = (await pollResponse.json()) as JobStatus;
          guard();
          if (job.status === "succeeded") {
            if (!job.note) throw new Error("no note");
            if (active.current === controller) setNote(job.note);
            settle("succeeded", null);
            return;
          }
          if (job.status === "superseded") {
            settle("superseded", SUPERSEDED_MESSAGE);
            return;
          }
          if (job.status === "failed") throw new Error("job failed");
        }
        throw new Error("poll timed out");
      } catch (caught) {
        if (caught instanceof Aborted || signal.aborted) return;
        settle("failed", FAILURE_MESSAGE);
      } finally {
        // Cleared on controller identity, not abortedness (see summary-panel).
        if (active.current === controller) running.current = false;
      }
    },
    [endpoint],
  );

  return { state, note, message, start };
}
