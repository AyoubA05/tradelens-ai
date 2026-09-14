import type { components } from "@/lib/api/schema";
import { money } from "@/lib/app/format";

type PeriodStats = components["schemas"]["PeriodStats"];

/**
 * The five figures a review period is read against.
 *
 * Profit factor has two honest non-numbers: `∞` when there were trades and no
 * losses, and `N/A` when there were no trades at all — never a zero.
 */
export function profitFactorText(stats: PeriodStats): string {
  if (stats.trades === 0) return "N/A";
  if (stats.profit_factor === null || stats.profit_factor === undefined) return "∞";
  return `${stats.profit_factor.toFixed(1)}x`;
}

export function PeriodStrip({ stats }: { stats: PeriodStats }) {
  const figures: [string, string][] = [
    ["Trades", String(stats.trades)],
    ["Win rate", `${Math.round(stats.win_rate * 100)}%`],
    ["Net P&L", money(stats.total_pnl)],
    ["Profit factor", profitFactorText(stats)],
    ["Edge leak", money(stats.total_edge_leak)],
  ];
  return (
    <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
      {figures.map(([label, value]) => (
        <div key={label} className="min-w-0 rounded-lg border border-line bg-surface px-3 py-2">
          <dt className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">{label}</dt>
          <dd className="mt-1 truncate font-display text-lg font-semibold text-text">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
