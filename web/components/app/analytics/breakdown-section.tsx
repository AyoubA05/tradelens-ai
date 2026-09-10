import { BreakdownTable } from "@/components/app/analytics/breakdown-table";
import type { AnalyticsResponse } from "@/lib/app/analytics";

type Breakdown = AnalyticsResponse["timing"]["by_day_of_week"];

/**
 * One category breakdown, as a table.
 *
 * `comparable` is decided server-side by `sample_policy.enough_categories`,
 * and this component obeys it rather than second-guessing it. When the sample
 * has not earned a comparison there is NO ranking language of any kind — no
 * best, no strongest, no top — and the reason is stated plainly instead,
 * because a reader who sees categories listed with no explanation will supply
 * a ranking of their own.
 *
 * When it is comparable, the ranking is a description of what was recorded,
 * not a recommendation: it names the category with the largest recorded net
 * P&L in this period and stops there. Nothing here says what to do next.
 *
 * The table scrolls inside its own container so the page body never scrolls
 * sideways on a narrow screen.
 */
export function BreakdownSection({
  id,
  title,
  description,
  breakdown,
}: {
  id: string;
  title: string;
  description: string;
  breakdown: Breakdown;
}) {
  const comparableRows = breakdown.rows.filter((row) => row.total_pnl.value !== null).length;

  return (
    <section
      data-testid={`breakdown-${id}`}
      aria-label={title}
      className="mt-6 rounded-xl border border-line bg-surface p-4"
    >
      <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{title}</h3>
      <p className="mt-1 text-xs text-muted">{description}</p>

      {breakdown.rows.length === 0 ? (
        <p data-testid={`breakdown-${id}-empty`} className="mt-3 text-sm text-muted">
          No trades in this range record this, so there is nothing to break down.
        </p>
      ) : (
        <>
          <BreakdownTable id={id} breakdown={breakdown} />

          {/*
            Three outcomes, not two. The server's `comparable` answers one
            question — are there enough categories — and a local P&L check
            answers a different one. Collapsing them into a single caption
            printed a cause that was untrue whenever the server said yes and
            the money was merely incomplete, AND put a bare "cannot be
            compared" directly under a Win rate column that is complete and
            independently sourced. That is the shared caveat decision 6b
            forbids: an undefined P&L may never discredit a valid win rate.
          */}
          {breakdown.leader ? (
            <p data-testid={`breakdown-${id}-ranking`} className="mt-3 text-xs text-muted">
              {`Largest recorded net P&L in this period: ${breakdown.leader.key}, over ${breakdown.leader.trades} trades.`}
            </p>
          ) : breakdown.comparable && comparableRows < 2 ? (
            <p data-testid={`breakdown-${id}-pnl-incomplete`} className="mt-3 text-xs text-muted">
              Too few of these categories record a P&amp;L to order them by money. The win rates
              above are measured from recorded outcomes and are unaffected.
            </p>
          ) : breakdown.comparable ? (
            <p data-testid={`breakdown-${id}-low-sample`} className="mt-3 text-xs text-muted">
              This range has too few trades to name a leading category. The rows above are
              measurements, not yet a pattern.
            </p>
          ) : (
            <p data-testid={`breakdown-${id}-not-comparable`} className="mt-3 text-xs text-muted">
              These categories cannot be compared: this range does not hold enough of them for one
              category to be read against another.
            </p>
          )}
        </>
      )}
    </section>
  );
}
