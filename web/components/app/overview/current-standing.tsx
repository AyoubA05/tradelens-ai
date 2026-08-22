import { money } from "@/lib/app/format";
import type { OverviewResponse } from "@/lib/app/overview";

/**
 * Today and the running week, as current state.
 *
 * Deliberately not part of the KPI row below it: every figure there is scoped
 * to the selected period, and these two are not — the service computes them
 * off the lifetime frame so that today's P&L does not vanish when the trader
 * narrows the window. Sitting them inside the same bordered row would make
 * that difference invisible, so they sit above it, smaller, and say so.
 *
 * The sign lives in the text (`money` writes the minus), and the direction is
 * spelled out as a word, because the positive and negative tokens are ΔE 2.3
 * apart under deuteranopia — tone here only reinforces what is already read.
 */
function Figure({ label, value }: { label: string; value: number }) {
  const direction = value > 0 ? "up" : value < 0 ? "down" : "flat";
  const toneClass =
    value > 0 ? "text-positive" : value < 0 ? "text-negative" : "text-text";
  return (
    <div className="flex items-baseline gap-2">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</span>
      <span className={`font-mono text-sm ${toneClass}`}>{money(value)}</span>
      <span className="font-mono text-[10px] text-muted">{direction}</span>
    </div>
  );
}

export function CurrentStanding({ kpi }: { kpi: OverviewResponse["kpi"] }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 mb-6 border-b border-line pb-4">
      <Figure label="Today" value={kpi.today_pnl} />
      <Figure label="This week" value={kpi.week_pnl} />
      <p className="font-mono text-[10px] text-muted">
        Always today and the current week — not the period selected below.
      </p>
    </div>
  );
}
