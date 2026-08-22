import { StatTile } from "@/components/app/overview/stat-tile";
import { money, undefinedReason, NO_VALUE } from "@/lib/app/format";
import type { OverviewResponse } from "@/lib/app/overview";

/**
 * Whether the headline numbers describe a process or a run of luck.
 *
 * A score the sample has not earned reads as a dash rather than a figure. A
 * consistency of 0.0 and a consistency that cannot yet be computed look
 * identical on screen and mean opposite things.
 */
export function RiskDiscipline({
  risk,
  sample,
}: {
  risk: OverviewResponse["risk"];
  sample: OverviewResponse["sample"];
}) {
  if (!sample.show_summary) return null;

  const adherence = risk.rule_adherence;
  const leak = risk.edge_leak.amount;

  // `metrics.compute_max_drawdown` reports the deepest peak-to-trough fall as
  // a POSITIVE magnitude, so the `value < 0` test this tile used to tone on
  // was never true: a $373.44 loss rendered in neutral white beside a green
  // net P&L, in the same glyphs. The figure is a fall, so it is written as one
  // — the minus sign and the hint carry that, and tone only reinforces it.
  const depth = risk.max_drawdown.value === null ? null : Math.abs(risk.max_drawdown.value);

  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Risk and discipline</h2>
      <p className="mt-1 text-sm text-muted">
        Whether the numbers above describe a process or a run of luck.
      </p>
      <div className="mt-4 grid grid-cols-2 rounded-xl border border-line bg-surface p-4 lg:grid-cols-4">
        <StatTile
          label="Max drawdown"
          value={depth === null ? NO_VALUE : depth === 0 ? money(0) : `-${money(depth)}`}
          hint={
            depth === null
              ? undefinedReason(risk.max_drawdown.state)
              : `deepest fall from a peak, over ${sample.dated_points} trading ${sample.dated_points === 1 ? "day" : "days"}`
          }
          tone={depth !== null && depth > 0 ? "negative" : "neutral"}
        />
        <StatTile
          label="Rule adherence"
          value={adherence.rate == null ? NO_VALUE : `${Math.round(adherence.rate * 100)}%`}
          hint={
            adherence.rate == null
              ? undefinedReason(null)
              : `${adherence.followed} of ${adherence.recorded}`
          }
        />
        <StatTile
          label="Edge leak"
          value={leak.value === null ? NO_VALUE : money(leak.value)}
          hint={
            leak.value === null
              ? undefinedReason(leak.state)
              : `${risk.edge_leak.trades} of ${risk.edge_leak.recorded} recorded`
          }
          tone={leak.value !== null && leak.value < 0 ? "negative" : "neutral"}
        />
        <StatTile
          label="Consistency"
          value={risk.consistency.value === null ? NO_VALUE : risk.consistency.value.toFixed(0)}
          hint={
            risk.consistency.value === null
              ? undefinedReason(risk.consistency.state)
              : "out of 100"
          }
        />
      </div>
    </section>
  );
}
