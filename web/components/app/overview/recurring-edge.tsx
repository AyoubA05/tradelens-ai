import { money } from "@/lib/app/format";
import type { OverviewResponse } from "@/lib/app/overview";

function Breakdown({ title, rows }: { title: string; rows: OverviewResponse["recurring_edge"]["killzones"] }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{title}</h3>
      <ul className="mt-3 space-y-2">
        {rows.length === 0 && <li className="text-sm text-muted">Nothing recorded yet.</li>}
        {rows.map((row) => (
          <li key={row.label} className="flex items-baseline justify-between gap-4">
            <span className="min-w-0 truncate text-sm text-text">
              {row.label}
              <span className="ml-2 font-mono text-[11px] text-muted">n={row.trades}</span>
            </span>
            <span
              className={`shrink-0 font-mono text-sm ${row.net_pnl > 0 ? "text-positive" : row.net_pnl < 0 ? "text-negative" : "text-text"}`}
            >
              {money(row.net_pnl)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Where the account repeats itself, and how large the sample is.
 *
 * The sample size sits beside every row on purpose: a killzone that "wins"
 * over three trades is a sentence about three trades.
 */
export function RecurringEdge({
  edge,
  sample,
}: {
  edge: OverviewResponse["recurring_edge"];
  sample: OverviewResponse["sample"];
}) {
  if (!sample.show_summary) return null;

  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Recurring edge</h2>
      <p className="mt-1 text-sm text-muted">
        Where the account repeats itself, and how large the sample is.
      </p>
      {!sample.pnl_complete ? (
        <div className="mt-4 rounded-xl border border-line bg-surface p-6">
          <p className="text-sm text-muted">
            P&amp;L data is incomplete. Record P&amp;L for every trade before comparing monetary performance.
          </p>
        </div>
      ) : !sample.show_comparisons ? (
        <div className="mt-4 rounded-xl border border-line bg-surface p-6">
          <p className="text-sm text-muted">
            Not enough trades to compare sessions or setups yet. Two trades is the minimum for a
            comparison to mean anything.
          </p>
        </div>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Breakdown title="Killzone performance" rows={edge.killzones} />
          <Breakdown title="Setup performance" rows={edge.setups} />
        </div>
      )}
    </section>
  );
}
