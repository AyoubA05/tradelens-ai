"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import type { AIAnalysisDetail, AIJobAccepted, AIJobStatus } from "@/lib/app/trade-analysis";
import type { TradeDetail } from "@/lib/app/trades";

/**
 * The Trade Detail AI review panel (Task D2).
 *
 * Three steps, each with its own job and its own poll route: analyse the
 * chart screenshot, write the journal entry from that analysis, grade the
 * trade from it. Every one of them looks backwards at a trade that is
 * already closed — nothing here names a setup to look for or a next action.
 *
 * Poll, don't stream (design decision #9): a job is enqueued, then its own
 * route is polled every two seconds up to a five-minute ceiling. Each kind
 * polls ONLY its own route, because the backend enforces the kind and a
 * job of another kind is a 404 there.
 *
 * The panel re-implements no backend rule. Whether an analysis exists at
 * all, whether the owner is over their ceiling, and whether a newer result
 * has replaced this one are all answers that arrive from the server; this
 * component's job is to state them without inventing a result shape.
 */

/** Two seconds, 150 times: a little over five minutes. */
const POLL_INTERVAL_MS = 2_000;
const POLL_ATTEMPTS = 150;

const FAILURE_MESSAGE =
  "This step didn't finish. Nothing was recorded on the trade. You can run it again.";
const RATE_LIMIT_FALLBACK =
  "You've reached today's limit for AI reviews. Reviews you've already run are still here.";
const SUPERSEDED_MESSAGE =
  "A newer analysis replaced this one, so this run's result was not kept. Re-run the step to work from the current analysis.";
const NEEDS_ANALYSIS = "Available once the chart has been analysed.";

type Kind = "analysis" | "journal" | "grade";

type JobState =
  | { phase: "idle" }
  | { phase: "running" }
  | { phase: "failed" }
  | { phase: "superseded" }
  | { phase: "limited"; message: string }
  | { phase: "blocked"; message: string }
  | { phase: "done" };

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

/** The backend's own sentence, when the relay forwarded one. */
async function detailOf(response: Response, fallback: string): Promise<string> {
  const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null;
  return typeof payload?.detail === "string" && payload.detail.trim() !== ""
    ? payload.detail
    : fallback;
}

export function AIReviewPanel({
  trade,
  analysis,
}: {
  trade: TradeDetail;
  analysis: AIAnalysisDetail | null;
}) {
  const router = useRouter();
  const screenshotId = trade.screenshots[0]?.id ?? null;
  const hasAnalysis = analysis !== null;

  const [states, setStates] = useState<Record<Kind, JobState>>({
    analysis: { phase: "idle" },
    journal: { phase: "idle" },
    grade: { phase: "idle" },
  });
  const controllers = useRef<Record<Kind, AbortController | null>>({
    analysis: null,
    journal: null,
    grade: null,
  });
  const inFlight = useRef<Record<Kind, boolean>>({
    analysis: false,
    journal: false,
    grade: false,
  });

  useEffect(() => {
    const active = controllers.current;
    return () => {
      active.analysis?.abort();
      active.journal?.abort();
      active.grade?.abort();
    };
  }, []);

  const setState = useCallback((kind: Kind, next: JobState) => {
    setStates((current) => ({ ...current, [kind]: next }));
  }, []);

  const run = useCallback(
    async (kind: Kind) => {
      // A second click while a job is in flight starts nothing. The disabled
      // button is the visible half of that; this flag is the half that a
      // programmatic or double-fired click cannot get past.
      if (inFlight.current[kind]) return;
      if (kind === "analysis" && screenshotId === null) return;
      inFlight.current[kind] = true;

      controllers.current[kind]?.abort();
      const controller = new AbortController();
      controllers.current[kind] = controller;
      setState(kind, { phase: "running" });

      try {
        const enqueueResponse = await fetch(`/api/trades/${trade.id}/${kind}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(kind === "analysis" ? { screenshot_id: screenshotId } : {}),
          cache: "no-store",
          credentials: "same-origin",
          signal: controller.signal,
        });

        // A 429 is the owner ceiling, not a failure: it is stated in the
        // backend's own words and offers no retry, because the retry would
        // only be refused again.
        if (enqueueResponse.status === 429) {
          setState(kind, {
            phase: "limited",
            message: await detailOf(enqueueResponse, RATE_LIMIT_FALLBACK),
          });
          return;
        }
        // A 409 means the analysis this step reads from is not there. That
        // is a precondition, not a breakage.
        if (enqueueResponse.status === 409) {
          setState(kind, {
            phase: "blocked",
            message: await detailOf(enqueueResponse, NEEDS_ANALYSIS),
          });
          return;
        }
        if (!enqueueResponse.ok) throw new Error("enqueue failed");
        const accepted = (await enqueueResponse.json()) as AIJobAccepted;

        for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt += 1) {
          if (attempt > 0) await wait(POLL_INTERVAL_MS, controller.signal);
          const pollResponse = await fetch(`/api/trades/${kind}/${accepted.job_id}`, {
            cache: "no-store",
            credentials: "same-origin",
            signal: controller.signal,
          });
          if (!pollResponse.ok) throw new Error("poll failed");
          const job = (await pollResponse.json()) as AIJobStatus;
          // A response about some other job says nothing about this one.
          // Same discipline the draft autosave applies to its own saves.
          if (job.job_id !== accepted.job_id) continue;
          if (job.status === "failed") throw new Error("job failed");
          if (job.status === "succeeded") {
            // `superseded` and `succeeded` are both true when a newer
            // analysis took the row. Reporting only the success would tell
            // the trader this run landed when it did not.
            if (job.superseded) {
              setState(kind, { phase: "superseded" });
              return;
            }
            setState(kind, { phase: "done" });
            router.refresh();
            return;
          }
        }
        throw new Error("poll timed out");
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setState(kind, { phase: "failed" });
      } finally {
        inFlight.current[kind] = false;
      }
    },
    [router, screenshotId, setState, trade.id],
  );

  return (
    <section className="mt-10 rounded-xl border border-line bg-surface p-5">
      <h2 className="font-display text-xl font-bold">AI review</h2>
      <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">
        A reflection on this closed trade — what the chart showed, what you wrote about it,
        and how the execution held up against your own rules. It never comments on future
        market direction.
      </p>

      <div className="mt-6 space-y-6">
        <Step
          title="Chart analysis"
          description="Reads the chart screenshot you attached and describes what it shows about the trade you already took."
          actionLabel="Analyse the chart"
          runningLabel="Analysing…"
          state={states.analysis}
          onRun={() => run("analysis")}
          unavailable={
            screenshotId === null
              ? "Add a chart screenshot to this trade before it can be reviewed."
              : null
          }
        >
          {analysis ? (
            <AnalysisBody analysis={analysis} />
          ) : (
            <p className="mt-3 text-sm text-muted">This trade is not analysed yet.</p>
          )}
        </Step>

        <Step
          title="Journal entry"
          description="Turns the stored analysis into a written reflection you can edit and keep."
          actionLabel="Write the journal entry"
          runningLabel="Writing…"
          state={states.journal}
          onRun={() => run("journal")}
          blockedReason={hasAnalysis ? null : NEEDS_ANALYSIS}
        >
          {analysis?.journal_entry_md ? (
            <p className="mt-3 whitespace-pre-line text-sm leading-6 text-muted">
              {analysis.journal_entry_md}
            </p>
          ) : null}
        </Step>

        <Step
          title="Execution grade"
          description="Scores how the trade was executed against the rules you recorded for it."
          actionLabel="Grade this trade"
          runningLabel="Grading…"
          state={states.grade}
          onRun={() => run("grade")}
          blockedReason={hasAnalysis ? null : NEEDS_ANALYSIS}
        >
          {analysis?.grading ? <GradingBody grading={analysis.grading} /> : null}
        </Step>
      </div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</dt>
      <dd className="mt-1 text-sm text-text">{value}</dd>
    </div>
  );
}

function List({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</p>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm leading-6 text-muted">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

/**
 * The stored analysis. Only fields the model actually returned are shown —
 * an absent label is left out rather than rendered as a blank or a zero,
 * which would read as a finding the review never made.
 */
function AnalysisBody({ analysis }: { analysis: AIAnalysisDetail }) {
  const rows: Array<[string, string]> = [];
  if (analysis.detected_setup) rows.push(["Setup described", analysis.detected_setup]);
  if (analysis.bias) rows.push(["Bias at entry", analysis.bias]);
  if (analysis.matched_strategy) rows.push(["Matched strategy", analysis.matched_strategy]);
  if (analysis.trade_quality !== null) {
    rows.push(["Trade quality", `${analysis.trade_quality} / 5`]);
  }
  if (analysis.user_grade) rows.push(["Your grade", analysis.user_grade]);
  else if (analysis.ai_grade) rows.push(["AI grade", analysis.ai_grade]);

  return (
    <div className="mt-3">
      {rows.length > 0 && (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
          {rows.map(([label, value]) => (
            <Row key={label} label={label} value={value} />
          ))}
        </dl>
      )}
      <List label="Key zones" items={analysis.key_zones} />
      <List label="Possible mistakes" items={analysis.possible_mistakes} />
      <List label="Missed opportunities" items={analysis.missed_opportunities} />
    </div>
  );
}

function GradingBody({
  grading,
}: {
  grading: NonNullable<AIAnalysisDetail["grading"]>;
}) {
  const entries = Object.entries(grading.rubric);
  return (
    <div className="mt-3">
      {grading.grade && (
        <p className="font-mono text-sm font-semibold text-text">{grading.grade}</p>
      )}
      {grading.one_line_verdict && (
        <p className="mt-1 text-sm leading-6 text-muted">{grading.one_line_verdict}</p>
      )}
      {entries.length > 0 && (
        <dl className="mt-4 space-y-2">
          {entries.map(([name, entry]) => (
            <div key={name} className="text-sm">
              <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                {name}
              </dt>
              <dd className="mt-0.5 text-muted">{entry.note ?? ""}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

/**
 * One step: its heading, its own control, its own status line, and whatever
 * of the stored review belongs to it.
 *
 * `unavailable` removes the control entirely — a step that cannot run at
 * all should not offer a button that would only be refused. `blockedReason`
 * keeps the control visible but disabled, because that step becomes
 * available the moment the analysis exists.
 */
function Step({
  title,
  description,
  actionLabel,
  runningLabel,
  state,
  onRun,
  unavailable = null,
  blockedReason = null,
  children,
}: {
  title: string;
  description: string;
  actionLabel: string;
  runningLabel: string;
  state: JobState;
  onRun: () => void;
  unavailable?: string | null;
  blockedReason?: string | null;
  children?: React.ReactNode;
}) {
  const running = state.phase === "running";
  const label =
    running || state.phase === "idle" || state.phase === "done"
      ? running
        ? runningLabel
        : actionLabel
      : "Try again";

  return (
    <div className="border-t border-line pt-5 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-base font-semibold text-text">{title}</h3>
          <p className="mt-1 max-w-xl text-sm leading-6 text-muted">{description}</p>
        </div>
        {unavailable === null && state.phase !== "limited" && (
          <button
            type="button"
            onClick={onRun}
            disabled={running || blockedReason !== null}
            className="min-h-11 rounded-lg border border-line-strong px-4 py-2 text-sm font-semibold text-text transition-colors duration-150 ease-tl hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {label}
          </button>
        )}
      </div>

      {unavailable !== null && <p className="mt-3 text-sm text-muted">{unavailable}</p>}
      {unavailable === null && blockedReason !== null && (
        <p className="mt-3 text-sm text-muted">{blockedReason}</p>
      )}
      {running && (
        <p className="mt-3 text-sm text-muted" role="status">
          Running. This can take a minute; the rest of the trade stays available.
        </p>
      )}
      {state.phase === "failed" && (
        <p className="mt-3 text-sm text-muted" role="alert">
          {FAILURE_MESSAGE}
        </p>
      )}
      {state.phase === "superseded" && (
        <p className="mt-3 text-sm text-muted" role="status">
          {SUPERSEDED_MESSAGE}
        </p>
      )}
      {state.phase === "limited" && (
        <p className="mt-3 text-sm text-muted" role="status">
          {state.message}
        </p>
      )}
      {state.phase === "blocked" && (
        <p className="mt-3 text-sm text-muted" role="status">
          {state.message}
        </p>
      )}
      {children}
    </div>
  );
}
