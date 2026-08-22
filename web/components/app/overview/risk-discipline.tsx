import { StatTile } from "@/components/app/overview/stat-tile";
import type { OverviewResponse } from "@/lib/app/overview";

const money = (n: number) =>
  `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** Why a figure has no number, in words a trader can act on. */
function undefinedReason(state: string | null | undefined): string {
  if (state === "undefined_positive_infinity") return "No losses yet";
  if (state === "undefined_negative_infinity") return "No wins yet";
  return "Not enough data";
}

/**
 * Whether the headline numbers describe a process or a run of luck.
 *
 * A score the sample has not earned reads "Not yet" rather than a figure. A
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
  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Risk and discipline</h2>
      <p className="mt-1 text-sm text-muted">
        Whether the numbers above describe a process or a run of luck.
      </p>
      <div className="mt-4 grid grid-cols-2 rounded-xl border border-line bg-surface p-4 lg:grid-cols-4">
        <StatTile
          label="Max drawdown"
          value={risk.max_drawdown.value === null ? "—" : money(risk.max_drawdown.value)}
          hint={
            risk.max_drawdown.value === null
              ? undefinedReason(risk.max_drawdown.state)
              : `${sample.dated_points} trading ${sample.dated_points === 1 ? "day" : "days"}`
          }
          tone={risk.max_drawdown.value !== null && risk.max_drawdown.value < 0 ? "negative" : "neutral"}
        />
        <StatTile
          label="Rule adherence"
          value={adherence.rate == null ? "—" : `${Math.round(adherence.rate * 100)}%`}
          hint={`${adherence.followed} of ${adherence.recorded}`}
        />
        <StatTile
          label="Edge leak"
          value={leak.value === null ? "—" : money(leak.value)}
          hint={
            leak.value === null
              ? undefinedReason(leak.state)
              : `${risk.edge_leak.trades} of ${risk.edge_leak.recorded} recorded`
          }
          tone={leak.value !== null && leak.value < 0 ? "negative" : "neutral"}
        />
        <StatTile
          label="Consistency"
          value={risk.consistency.value === null ? "Not yet" : risk.consistency.value.toFixed(0)}
          hint={risk.consistency.value === null ? "More trades needed to score it" : "out of 100"}
        />
      </div>
    </section>
  );
}
