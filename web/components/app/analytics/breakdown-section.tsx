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
  const ranked = breakdown.comparable
    ? breakdown.rows
        .filter((row) => row.total_pnl.value !== null)
        .sort((a, b) => (b.total_pnl.value ?? 0) - (a.total_pnl.value ?? 0))[0]
    : undefined;
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

          {ranked && comparableRows >= 2 ? (
            <p data-testid={`breakdown-${id}-ranking`} className="mt-3 text-xs text-muted">
              {`Largest recorded net P&L in this period: ${ranked.key}, over ${ranked.trades} trades.`}
            </p>
          ) : (
            <p data-testid={`breakdown-${id}-not-comparable`} className="mt-3 text-xs text-muted">
              These categories cannot be compared: this range does not hold enough of them, with
              enough recorded P&amp;L, for one category to be read against another.
            </p>
          )}
        </>
      )}
    </section>
  );
}
