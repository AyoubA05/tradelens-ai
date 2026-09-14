import Link from "next/link";

import type { components } from "@/lib/api/schema";
import { EmptyState } from "@/components/app/states/empty-state";
import { PeriodStrip } from "@/components/app/reviews/period-strip";

type PatternsLensData = components["schemas"]["PatternsLens"];
type PatternInsight = components["schemas"]["PatternInsight"];

const CONFIDENCE_ORDER = { high: 0, medium: 1, low: 2 } as const;
const MIN_PATTERN_TRADES = 5;

/**
 * Patterns: deterministic findings from the journal. No AI call, so this lens
 * is available whether or not AI is.
 */
export function PatternsLens({
  patterns,
  completeTrades,
  tradesForReview,
}: {
  patterns: PatternsLensData;
  completeTrades: number;
  tradesForReview: number;
}) {
  const sorted = [...patterns.insights].sort(
    (a, b) => CONFIDENCE_ORDER[a.confidence] - CONFIDENCE_ORDER[b.confidence],
  );
  const [lead, ...others] = sorted;
  const findings = others.slice(0, 4);
  const remaining = Math.max(tradesForReview - completeTrades, 0);

  return (
    <div>
      <PeriodStrip stats={patterns.stats} />

      {patterns.trades < MIN_PATTERN_TRADES && (
        <p className="mt-4 text-sm text-muted">
          Fewer than five trades — these describe a handful of records, not a pattern.
        </p>
      )}

      {!lead ? (
        <div className="mt-6">
          <EmptyState
            title="No repeating patterns yet"
            description={
              remaining > 0
                ? `Journal ${remaining} more completed trades and patterns start to show.`
                : "Keep journaling — nothing repeats often enough to call a pattern yet."
            }
            action={{ href: "/app/journal", label: "Open the Journal" }}
          />
        </div>
      ) : (
        <>
          <section data-testid="patterns-lead" className="mt-6 rounded-xl border border-line bg-surface p-5">
            <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">Lead thesis</p>
            <h2 className="mt-1 font-display text-xl font-bold">{lead.title}</h2>
            <p className="mt-2 text-sm leading-6 text-muted">{lead.body}</p>
            <InsightMeta insight={lead} />
            <Link
              href="/app/journal"
              className="mt-4 inline-flex min-h-11 items-center text-sm text-accent hover:underline"
            >
              Re-read the trades behind “{lead.title}” in the Journal.
            </Link>
          </section>

          {findings.length > 0 && (
            <ol className="mt-4 space-y-3">
              {findings.map((insight, index) => (
                <li
                  key={`${index}:${insight.title}`}
                  data-testid="patterns-finding"
                  className="rounded-xl border border-line bg-surface p-4"
                >
                  <h3 className="font-display text-base font-semibold">{insight.title}</h3>
                  <p className="mt-1 text-sm leading-6 text-muted">{insight.body}</p>
                  <InsightMeta insight={insight} />
                </li>
              ))}
            </ol>
          )}
        </>
      )}

      <ul className="mt-6 space-y-1 text-xs text-muted">
        <li>Trades reviewed: {patterns.trades}</li>
        <li>Strategy profile: {patterns.strategy_included ? "included" : "not included"}</li>
        <li>Computed from your journal — no AI call</li>
      </ul>
    </div>
  );
}

function InsightMeta({ insight }: { insight: PatternInsight }) {
  return (
    <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
      Confidence: {insight.confidence} · Needs at least {insight.min_trades} trades
    </p>
  );
}
