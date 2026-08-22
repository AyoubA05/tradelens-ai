import { EquityCurve } from "@/components/app/overview/equity-curve";
import { StatTile } from "@/components/app/overview/stat-tile";
import type { OverviewResponse } from "@/lib/app/overview";

const money = (n: number) =>
  `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** The path the account took to get here. */
export function Trajectory({
  trajectory,
  sample,
}: {
  trajectory: OverviewResponse["trajectory"];
  sample: OverviewResponse["sample"];
}) {
  if (!sample.show_summary) return null;

  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Performance trajectory</h2>
      <p className="mt-1 text-sm text-muted">The path the account took to get here.</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-[2fr_1fr]">
        <EquityCurve points={trajectory.equity_curve} sample={sample} />
        <div className="grid grid-cols-2 gap-x-2 rounded-xl border border-line bg-surface p-4 lg:grid-cols-1 lg:gap-y-2">
          <StatTile
            label="Current streak"
            value={trajectory.current_streak === null || trajectory.current_streak === undefined ? "—" : String(trajectory.current_streak)}
            hint="most recent first"
          />
          <StatTile
            label="Best run"
            value={trajectory.best_streak === null || trajectory.best_streak === undefined ? "—" : String(trajectory.best_streak)}
            hint={
              trajectory.worst_streak === null || trajectory.worst_streak === undefined
                ? undefined
                : `longest losing run ${trajectory.worst_streak}`
            }
          />
          <StatTile
            label="Average win"
            value={trajectory.average_win.value === null ? "—" : money(trajectory.average_win.value)}
            tone={trajectory.average_win.value === null ? "neutral" : "positive"}
          />
          <StatTile
            label="Average loss"
            value={trajectory.average_loss.value === null ? "—" : money(trajectory.average_loss.value)}
            tone={trajectory.average_loss.value === null ? "neutral" : "negative"}
          />
        </div>
      </div>
    </section>
  );
}
