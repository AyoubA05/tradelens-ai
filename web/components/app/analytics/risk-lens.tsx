import { FigureRow, LensFigure } from "@/components/app/analytics/lens-figure";
import type { AnalyticsResponse } from "@/lib/app/analytics";

/**
 * Lens 2 — what the record cost at its worst, and the size of a typical
 * winner against a typical loser.
 *
 * A drawdown that could not be measured stays unmeasured. `$0.00` here would
 * read as "this account never drew down", which is the opposite claim.
 */
export function RiskLens({ risk }: { risk: AnalyticsResponse["risk"] }) {
  return (
    <div>
      <FigureRow>
        <LensFigure
          testId="figure-max-drawdown"
          label="Max drawdown"
          value={risk.max_drawdown}
          kind="money"
        />
        <LensFigure testId="figure-avg-win" label="Average win" value={risk.avg_win} kind="money" />
        <LensFigure testId="figure-avg-loss" label="Average loss" value={risk.avg_loss} kind="money" />
      </FigureRow>

      <section
        data-testid="risk-series-pending"
        aria-label="Drawdown and R-multiples"
        className="mt-6 rounded-xl border border-line bg-surface p-4"
      >
        <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          Drawdown and R-multiples
        </h3>
        <p className="mt-1 text-xs text-muted">
          {`${risk.drawdown_series.length} drawdown points and ${risk.r_multiples.length} R-multiple buckets are recorded for this period. These series are not drawn yet.`}
        </p>
      </section>
    </div>
  );
}
