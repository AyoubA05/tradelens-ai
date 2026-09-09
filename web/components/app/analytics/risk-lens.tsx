import { DistributionChart } from "@/components/app/analytics/distribution-chart";
import { FigureRow, LensFigure } from "@/components/app/analytics/lens-figure";
import { LineChart } from "@/components/app/analytics/line-chart";
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

      <LineChart
        id="drawdown"
        title="Drawdown"
        description="How far below its own high-water mark the record sat on each dated day."
        points={risk.drawdown_series}
        kind="money"
      />

      <DistributionChart
        id="r-multiples"
        title="R-multiple distribution"
        description="How many recorded trades fell into each R-multiple bucket."
        buckets={risk.r_multiples}
      />
    </div>
  );
}
