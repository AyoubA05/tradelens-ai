import { StatTile } from "@/components/app/overview/stat-tile";
import { EmptyState } from "@/components/app/states/empty-state";
import { money, undefinedReason, NO_VALUE } from "@/lib/app/format";
import type { OverviewResponse } from "@/lib/app/overview";

export function KpiRow({
  kpi,
  sample,
}: {
  kpi: OverviewResponse["kpi"];
  sample: OverviewResponse["sample"];
}) {
  if (!sample.show_summary) {
    return (
      <EmptyState
        title="No trades in this period"
        description="Widen the period, or log a completed trade to start the record."
        action={{ href: "/app/trades/new", label: "Log completed trade" }}
      />
    );
  }

  // A ternary isn't a literal expression, so `as const` on it is a type
  // error (TS1355) — an explicit return type gets the same narrowing.
  const tone = (n: number): "positive" | "negative" | "neutral" =>
    n > 0 ? "positive" : n < 0 ? "negative" : "neutral";

  return (
    <div className="grid grid-cols-2 rounded-xl border border-line bg-surface p-4 sm:grid-cols-3 lg:grid-cols-5">
      <StatTile
        label="Net P&L"
        value={money(kpi.net_pnl)}
        hint={`${kpi.trades} ${kpi.trades === 1 ? "trade" : "trades"}`}
        tone={tone(kpi.net_pnl)}
      />
      <StatTile
        label="Win rate"
        value={kpi.win_rate.value === null ? NO_VALUE : `${(kpi.win_rate.value * 100).toFixed(1)}%`}
        hint={kpi.win_rate.value === null ? undefinedReason(kpi.win_rate.state) : `${kpi.wins} of ${kpi.trades}`}
      />
      <StatTile
        label="Expectancy"
        value={kpi.expectancy == null ? NO_VALUE : money(kpi.expectancy)}
        hint={kpi.expectancy == null ? undefinedReason(kpi.expectancy_state) : "per trade"}
        tone={kpi.expectancy == null ? "neutral" : tone(kpi.expectancy)}
      />
      <StatTile
        label="Profit factor"
        value={kpi.profit_factor == null ? NO_VALUE : `${kpi.profit_factor.toFixed(2)}x`}
        hint={kpi.profit_factor == null ? undefinedReason(kpi.profit_factor_state) : undefined}
      />
      <StatTile label="Trades" value={String(kpi.trades)} hint={`${kpi.losses} losing`} />
    </div>
  );
}
