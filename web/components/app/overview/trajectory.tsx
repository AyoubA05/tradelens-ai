import { EquityCurve } from "@/components/app/overview/equity-curve";
import { StatTile } from "@/components/app/overview/stat-tile";
import { money, undefinedReason, NO_VALUE } from "@/lib/app/format";
import type { OverviewResponse } from "@/lib/app/overview";

/**
 * The current run, as a word.
 *
 * `current_streak` is signed, so direction was carried by a minus sign alone
 * on the one figure where it matters most — and `streak_type` ("win" | "loss"
 * | "none") was fetched, typed, and never rendered. Three losses in a row now
 * says so.
 */
function streakLabel(
  count: number | null | undefined,
  type: string | null | undefined,
): { value: string; tone: "positive" | "negative" | "neutral" } {
  if (count === null || count === undefined) return { value: NO_VALUE, tone: "neutral" };
  const n = Math.abs(count);
  if (type === "win") return { value: `${n} ${n === 1 ? "win" : "wins"}`, tone: "positive" };
  if (type === "loss") return { value: `${n} ${n === 1 ? "loss" : "losses"}`, tone: "negative" };
  return { value: "No run", tone: "neutral" };
}

/** The path the account took to get here. */
export function Trajectory({
  trajectory,
  sample,
}: {
  trajectory: OverviewResponse["trajectory"];
  sample: OverviewResponse["sample"];
}) {
  if (!sample.show_summary) return null;

  const streak = streakLabel(trajectory.current_streak, trajectory.streak_type);

  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Performance trajectory</h2>
      <p className="mt-1 text-sm text-muted">The path the account took to get here.</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-[2fr_1fr]">
        <EquityCurve points={trajectory.equity_curve} sample={sample} />
        <div className="grid grid-cols-2 gap-x-2 rounded-xl border border-line bg-surface p-4 lg:grid-cols-1 lg:gap-y-2">
          <StatTile
            label="Current streak"
            value={streak.value}
            hint="consecutive, most recent first"
            tone={streak.tone}
          />
          <StatTile
            label="Best run"
            value={trajectory.best_streak === null || trajectory.best_streak === undefined ? NO_VALUE : String(trajectory.best_streak)}
            hint={
              trajectory.worst_streak === null || trajectory.worst_streak === undefined
                ? undefined
                : `longest losing run ${trajectory.worst_streak}`
            }
          />
          <StatTile
            label="Average win"
            value={trajectory.average_win.value === null ? NO_VALUE : money(trajectory.average_win.value)}
            // A dash with no explanation is the one thing worse than a wrong
            // number: KPI and Risk both say why theirs is empty, so this does too.
            hint={
              trajectory.average_win.value === null
                ? undefinedReason(trajectory.average_win.state)
                : "per winning trade"
            }
            tone={trajectory.average_win.value === null ? "neutral" : "positive"}
          />
          <StatTile
            label="Average loss"
            value={trajectory.average_loss.value === null ? NO_VALUE : money(trajectory.average_loss.value)}
            hint={
              trajectory.average_loss.value === null
                ? undefinedReason(trajectory.average_loss.state)
                : "per losing trade"
            }
            tone={trajectory.average_loss.value === null ? "neutral" : "negative"}
          />
        </div>
      </div>
    </section>
  );
}
