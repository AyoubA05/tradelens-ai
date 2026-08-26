"use client";

import { useEffect, useRef, useState } from "react";

import type { components } from "@/lib/api/schema";
import type { Period } from "@/lib/app/period";
import type { TradeFilters } from "@/lib/app/trade-filters";

type JobAccepted = components["schemas"]["TradeSummaryJobAccepted"];
type JobStatus = components["schemas"]["TradeSummaryJobStatus"];
type SummaryResult = components["schemas"]["TradeSummaryResult"];

// The provider timeout is 120s and may include retries. Poll immediately,
// then back off to eight seconds for a little over three minutes total.
const POLL_DELAYS_MS = [
  1_000,
  2_000,
  4_000,
  ...Array.from({ length: 23 }, () => 8_000),
];
const FAILURE_MESSAGE =
  "This review didn't finish. To avoid duplicate processing, this exact selection will not run again automatically. Update the selection before requesting another review.";
const RATE_LIMIT_FALLBACK_MESSAGE =
  "You've reached today's limit for AI summaries. Summaries you've already generated are still available.";

function InlineMarkdown({ text }: { text: string }) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**") ? (
      <strong key={index} className="font-semibold text-text">
        {part.slice(2, -2)}
      </strong>
    ) : (
      part
    ),
  );
}

function MarkdownBody({ body }: { body: string }) {
  return (
    <div className="mt-2 space-y-2 text-sm leading-6 text-muted">
      {body.split(/\n\s*\n/).map((block, index) => {
        const lines = block.split("\n").filter(Boolean);
        if (lines.length > 0 && lines.every((line) => /^[-*] /.test(line))) {
          return (
            <ul key={index} className="list-disc space-y-1 pl-5">
              {lines.map((line, lineIndex) => (
                <li key={`${lineIndex}:${line}`}>
                  <InlineMarkdown text={line.slice(2)} />
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={index} className="whitespace-pre-line">
            <InlineMarkdown text={block} />
          </p>
        );
      })}
    </div>
  );
}

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

function SummaryMarkdown({ content }: { content: string }) {
  const sections = content
    .split(/^### /m)
    .slice(1)
    .map((chunk) => {
      const [title = "", ...body] = chunk.trim().split("\n");
      return { title: title.trim(), body: body.join("\n").trim() };
    });

  return (
    <div className="mt-5 space-y-5">
      {sections.map((section) => (
        <section key={section.title}>
          <h3 className="font-display text-base font-bold text-text">{section.title}</h3>
          <MarkdownBody body={section.body} />
        </section>
      ))}
    </div>
  );
}

export function TradeSummaryPanel({
  period,
  filters,
  tradeCount,
}: {
  period: Period;
  filters: TradeFilters;
  tradeCount: number;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [rateLimitMessage, setRateLimitMessage] = useState<string | null>(null);
  const [result, setResult] = useState<SummaryResult | null>(null);
  const [stateSelectionKey, setStateSelectionKey] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);
  const selectionKey = [
    period.from,
    period.to,
    filters.asset ?? "",
    filters.session ?? "",
    filters.setup ?? "",
    filters.result ?? "",
  ].join("\u0000");
  const stateIsCurrent = stateSelectionKey === selectionKey;
  const currentLoading = stateIsCurrent && loading;
  const currentError = stateIsCurrent && error;
  const currentRateLimitMessage = stateIsCurrent ? rateLimitMessage : null;
  const currentResult = stateIsCurrent ? result : null;

  useEffect(() => () => active.current?.abort(), []);
  useEffect(() => {
    active.current?.abort();
  }, [selectionKey]);

  async function generate() {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setStateSelectionKey(selectionKey);
    setLoading(true);
    setError(false);
    setRateLimitMessage(null);
    setResult(null);

    try {
      const body = { from: period.from, to: period.to, ...filters };
      const queuedResponse = await fetch("/api/trades/summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        cache: "no-store",
        credentials: "same-origin",
        signal: controller.signal,
      });
      if (queuedResponse.status === 429) {
        // A 429 is not a failure to recover from — it is the backend saying
        // no. Surface its own message rather than the generic failure text,
        // and never retry automatically: the retry would just fail again.
        const payload = (await queuedResponse.json().catch(() => null)) as {
          detail?: unknown;
        } | null;
        setRateLimitMessage(
          typeof payload?.detail === "string" ? payload.detail : RATE_LIMIT_FALLBACK_MESSAGE,
        );
        return;
      }
      if (!queuedResponse.ok) throw new Error("enqueue failed");
      const queued = (await queuedResponse.json()) as JobAccepted;

      for (let attempt = 0; attempt <= POLL_DELAYS_MS.length; attempt += 1) {
        if (attempt > 0) {
          await wait(POLL_DELAYS_MS[attempt - 1]!, controller.signal);
        }
        const pollResponse = await fetch(`/api/trades/summary/${queued.job_id}`, {
          cache: "no-store",
          credentials: "same-origin",
          signal: controller.signal,
        });
        if (!pollResponse.ok) throw new Error("poll failed");
        const job = (await pollResponse.json()) as JobStatus;
        if (job.status === "succeeded" && job.result) {
          setResult(job.result);
          return;
        }
        if (job.status === "failed") throw new Error("job failed");
      }
      throw new Error("poll timed out");
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setError(true);
      }
    } finally {
      // Clear on controller identity, not on abortedness. A filter change
      // aborts this run without starting another, and keying off
      // `signal.aborted` left `loading` true forever for that selection:
      // switching back to it rendered a permanently disabled button over a
      // job that may have succeeded and been paid for.
      if (active.current === controller) setLoading(false);
    }
  }

  return (
    <section className="mt-10 rounded-xl border border-line bg-surface p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-display text-xl font-bold">AI summary</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">
            A post-trade reflection on the trades matching these filters. It reviews
            execution and discipline, never future market direction.
          </p>
        </div>
        {tradeCount >= 2 && !currentRateLimitMessage && (
          <button
            type="button"
            onClick={generate}
            disabled={currentLoading}
            className="min-h-11 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-background disabled:cursor-wait disabled:opacity-60"
          >
            {currentLoading
              ? "Reviewing trades…"
              : currentError
                ? "Try again"
                : `Summarize these ${tradeCount} trades`}
          </button>
        )}
      </div>

      {tradeCount < 2 && (
        <p className="mt-4 text-sm text-muted">
          Select at least two trades before asking AI to compare recurring behaviour.
        </p>
      )}
      {tradeCount > 40 && (
        <p className="mt-4 text-xs text-muted">The newest 40 matching trades are reviewed.</p>
      )}
      {currentLoading && (
        <p className="mt-4 text-sm text-muted" role="status">
          Reviewing this completed-trade selection. The journal remains available.
        </p>
      )}
      {currentRateLimitMessage && (
        <p className="mt-4 text-sm text-muted" role="status">
          {currentRateLimitMessage}
        </p>
      )}
      {currentError && !currentRateLimitMessage && (
        <p className="mt-4 text-sm text-muted" role="alert">
          {FAILURE_MESSAGE}
        </p>
      )}
      {currentResult && (
        <div aria-live="polite">
          <p className="mt-4 font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
            Reviewed {currentResult.reviewed_trades} trades
          </p>
          <SummaryMarkdown content={currentResult.content_md} />
        </div>
      )}
    </section>
  );
}
