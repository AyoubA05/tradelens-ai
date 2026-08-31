"use client";

import { useState } from "react";

import type { components } from "@/lib/api/schema";

/**
 * Per-field AI suggestion review (Task D2).
 *
 * Rendered once a trade and its screenshot both exist (design decision #4:
 * autofill keys on a `screenshot_id`, which cannot exist before the trade
 * does). This is strictly additive to the existing New Trade flow — the
 * trader can always "Skip" straight to the trade they already have,
 * unchanged from what happened before this task.
 *
 * **Assistive, not authoritative** (global rule): nothing here is a form
 * field. A suggestion never becomes a value in `NewTradeForm`'s own state —
 * it lives only in this component's own `suggestions`/`accepted` state,
 * inside cards visibly labelled "Suggested," until the trader clicks
 * "Apply," which sends exactly the accepted subset in one `PATCH`. That is
 * what keeps an unreviewed suggestion structurally distinguishable from
 * something a human typed: there is no code path that could confuse the
 * two, because they are never represented the same way.
 *
 * `autocheck` is not a second confidence policy — it is
 * `should_autocheck`'s own decision, carried on the wire (see
 * `AutofillSuggestion` in the generated schema). This component only
 * renders it as the checkbox's initial state; it invents no threshold of
 * its own.
 */

type TradeAutofillJobStatus = components["schemas"]["TradeAutofillJobStatus"];
type AutofillSuggestion = components["schemas"]["AutofillSuggestion"];
type TradeUpdate = components["schemas"]["TradeUpdate"];

/**
 * Suggested fields this component can actually apply — every field
 * `PATCH /v1/trades/{id}` accepts, in the component's own vocabulary.
 *
 * A suggestion that cannot be applied is NOT rendered. An earlier version
 * showed those as read-only cards, which reads as generosity and is not:
 * a review affordance a trader cannot act on spends their attention and
 * returns nothing, and it invites them to retype a number the model read
 * off a chart, which is the least reviewed way a value can enter a journal.
 *
 * The gap itself is closed on the server where it can be: `bias` and the
 * five SMC evidence flags are patchable as of Phase 4E's fix wave. The
 * suggested prices deliberately are not — they feed `rr_planned` and
 * `rr_realized`, so making them patchable means re-deriving both inside the
 * atomic UPDATE. `tests/test_api_trade_autofill.py` pins exactly which
 * suggestible fields have no apply path, so the two sets cannot drift apart
 * without a test saying so.
 */
export const APPLIABLE_FIELDS = [
  "asset",
  "bias",
  "bos",
  "choch",
  "direction",
  "followed_rules",
  "fvg_used",
  "htf_bias",
  "liquidity_sweep",
  "mistake_tags",
  "notes",
  "order_block_used",
  "pnl",
  "result",
  "risk_amount",
  "rr_realized",
  "setup_type",
  "timeframe",
  "trade_date",
] as const satisfies readonly (keyof TradeUpdate)[];

type AppliableField = (typeof APPLIABLE_FIELDS)[number];

function isAppliable(field: string): field is AppliableField {
  return (APPLIABLE_FIELDS as readonly string[]).includes(field);
}

/** Only what the trader can act on ever reaches the review list. */
function appliableOnly(
  suggestions: Record<string, AutofillSuggestion>,
): Record<string, AutofillSuggestion> {
  const kept: Record<string, AutofillSuggestion> = {};
  for (const [field, suggestion] of Object.entries(suggestions)) {
    if (isAppliable(field)) kept[field] = suggestion;
  }
  return kept;
}

function fieldLabel(field: string): string {
  return field
    .split("_")
    .map((w) => w[0]?.toUpperCase() + w.slice(1))
    .join(" ");
}

function suggestionValueText(s: AutofillSuggestion): string {
  const v = s.value;
  if (v === null || v === undefined) return "(no value)";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  return String(v);
}

const POLL_INTERVAL_MS = 1500;
const MAX_POLLS = 30; // ~45s, generous for a vision call without hanging forever

type Phase =
  | { kind: "prompt" }
  | { kind: "working" }
  | { kind: "ready"; suggestions: Record<string, AutofillSuggestion> }
  | { kind: "empty" } // succeeded with nothing this review can apply
  | { kind: "superseded" } // a later run replaced this job's suggestions
  | { kind: "error"; message: string };

async function pollJob(jobId: number): Promise<TradeAutofillJobStatus | null> {
  for (let attempt = 0; attempt < MAX_POLLS; attempt++) {
    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    let response: Response;
    try {
      response = await fetch(`/api/trades/autofill/${jobId}`, { method: "GET" });
    } catch {
      continue; // transient — keep polling within the attempt budget
    }
    if (!response.ok) return null;
    const job = (await response.json()) as TradeAutofillJobStatus;
    if (job.status === "succeeded" || job.status === "failed") return job;
  }
  return null;
}

export function AutofillReview({
  tradeId,
  screenshotId,
  expectedUpdatedAt,
  onDone,
}: {
  tradeId: number;
  screenshotId: number;
  expectedUpdatedAt: string | null;
  onDone: () => void;
}) {
  const [phase, setPhase] = useState<Phase>({ kind: "prompt" });
  const [accepted, setAccepted] = useState<Record<string, boolean>>({});
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  async function startAutofill() {
    setPhase({ kind: "working" });
    try {
      const enqueueResponse = await fetch("/api/trades/autofill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ screenshot_id: screenshotId }),
      });
      if (!enqueueResponse.ok) {
        let message = "AI suggestions aren't available right now. Your trade is unaffected.";
        try {
          const body = (await enqueueResponse.json()) as { detail?: unknown };
          if (typeof body?.detail === "string") message = body.detail;
        } catch {
          // no body — keep the generic message
        }
        setPhase({ kind: "error", message });
        return;
      }
      const accepted202 = (await enqueueResponse.json()) as { job_id: number };
      const job = await pollJob(accepted202.job_id);
      if (!job || job.status === "failed") {
        setPhase({
          kind: "error",
          message: job?.error ?? "AI suggestions didn't finish. Your trade is unaffected.",
        });
        return;
      }
      if (job.superseded) {
        // A later autofill run replaced this job's suggestions, so the
        // server will not say which chart they came from. Nothing is shown
        // rather than a set that might describe a different screenshot.
        setPhase({ kind: "superseded" });
        return;
      }
      const suggestions = appliableOnly(job.suggestions ?? {});
      if (Object.keys(suggestions).length === 0) {
        setPhase({ kind: "empty" });
        return;
      }
      // Pre-check exactly what the server's own confidence policy decided
      // to pre-check — never a second, client-invented threshold.
      const initial: Record<string, boolean> = {};
      for (const [field, s] of Object.entries(suggestions)) {
        initial[field] = s.autocheck;
      }
      setAccepted(initial);
      setPhase({ kind: "ready", suggestions });
    } catch {
      setPhase({
        kind: "error",
        message: "AI suggestions aren't available right now. Your trade is unaffected.",
      });
    }
  }

  async function applyAccepted() {
    if (phase.kind !== "ready") return;
    setApplyError(null);
    const body: Partial<TradeUpdate> = {};
    let any = false;
    for (const field of APPLIABLE_FIELDS) {
      if (!accepted[field]) continue;
      const suggestion = phase.suggestions[field];
      if (!suggestion) continue;
      // The value is exactly what the model returned — shape-validated by
      // the server when it was written to the draft, never re-derived here.
      (body as Record<string, unknown>)[field] = suggestion.value;
      any = true;
    }
    if (!any || !expectedUpdatedAt) {
      onDone();
      return;
    }
    setApplying(true);
    try {
      const response = await fetch(`/api/trades/${tradeId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, expected_updated_at: expectedUpdatedAt }),
      });
      if (!response.ok) {
        // Nothing here may claim the TRADE is at risk — only the suggested
        // edits did not apply. The trade itself was already durable before
        // this component ever rendered (design decision #6).
        setApplyError(
          "These suggestions did not save. Your trade is unchanged — you can edit it from its own page instead.",
        );
        return;
      }
      onDone();
    } catch {
      setApplyError(
        "We could not reach the server. Your trade is unchanged — you can edit it from its own page instead.",
      );
    } finally {
      setApplying(false);
    }
  }

  const sectionClass = "rounded-xl border border-line bg-surface p-5";
  const sectionTitleClass = "font-display text-sm font-semibold text-text";

  return (
    <div className={sectionClass}>
      <h2 className={sectionTitleClass}>Your trade is saved. Review AI suggestions?</h2>
      <p className="mt-2 max-w-md text-sm text-muted">
        Optional. TradeLens can read the chart you attached and suggest values for a few fields —
        nothing here is a signal or a prediction, only a reading of what is already on your
        screenshot. Every suggestion stays clearly marked until you choose to apply it.
      </p>

      {phase.kind === "prompt" && (
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            onClick={startAutofill}
            className="min-h-[44px] rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90"
          >
            Get AI suggestions from this screenshot
          </button>
          <button
            type="button"
            onClick={onDone}
            className="min-h-[44px] rounded-lg border border-line-strong px-4 py-2 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
          >
            Skip
          </button>
        </div>
      )}

      {phase.kind === "working" && (
        <p className="mt-4 text-sm text-muted" aria-live="polite" role="status">
          Reading the screenshot…
        </p>
      )}

      {(phase.kind === "error" ||
        phase.kind === "empty" ||
        phase.kind === "superseded") && (
        <div className="mt-4">
          {phase.kind === "error" && (
            <p role="alert" className="max-w-md break-words text-sm text-negative">
              {phase.message}
            </p>
          )}
          {phase.kind === "empty" && (
            <p className="text-sm text-muted">Nothing to suggest from this screenshot.</p>
          )}
          {phase.kind === "superseded" && (
            <p className="text-sm text-muted">
              These suggestions were replaced by a newer screenshot&apos;s. Your trade is
              unaffected.
            </p>
          )}
          <button
            type="button"
            onClick={onDone}
            className="mt-4 min-h-[44px] rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90"
          >
            Open the trade
          </button>
        </div>
      )}

      {phase.kind === "ready" && (
        <div className="mt-4">
          <ul className="flex flex-col gap-2" data-testid="autofill-suggestion-list">
            {Object.entries(phase.suggestions).map(([field, suggestion]) => {
              return (
                <li
                  key={field}
                  data-testid={`autofill-suggestion-${field}`}
                  className="flex items-start gap-3 rounded-lg border border-line bg-surface-2/40 px-3 py-2"
                >
                  <input
                    type="checkbox"
                    checked={!!accepted[field]}
                    onChange={(e) =>
                      setAccepted((a) => ({ ...a, [field]: e.target.checked }))
                    }
                    aria-label={`Accept suggested ${fieldLabel(field)}`}
                    className="mt-1"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-text">{fieldLabel(field)}</p>
                    {/* The "Suggested" badge is what keeps this visibly
                        distinct from a human-entered value everywhere it
                        renders — never color alone (courtesy of the same
                        rule `format.ts`'s `money` follows). */}
                    <p className="mt-0.5 break-words text-xs text-muted">
                      <span className="rounded-full border border-accent/40 bg-accent/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent">
                        Suggested
                      </span>{" "}
                      <span data-testid={`autofill-suggestion-${field}-value`}>
                        {suggestionValueText(suggestion)}
                      </span>
                      {typeof suggestion.confidence === "number" && (
                        <span> · {Math.round(suggestion.confidence * 100)}% confidence</span>
                      )}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>

          {applyError && (
            <p role="alert" className="mt-3 max-w-md break-words text-sm text-negative">
              {applyError}
            </p>
          )}

          <div className="mt-4 flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              disabled={applying}
              onClick={applyAccepted}
              className="min-h-[44px] rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {applying ? "Applying…" : "Apply accepted & continue"}
            </button>
            <button
              type="button"
              disabled={applying}
              onClick={onDone}
              className="min-h-[44px] rounded-lg border border-line-strong px-4 py-2 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Skip
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
