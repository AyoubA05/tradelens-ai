import Link from "next/link";

import { EmptyState } from "@/components/app/states/empty-state";
import type { OverviewResponse } from "@/lib/app/overview";

const money = (n: number | null | undefined) =>
  n === null || n === undefined
    ? "—"
    : `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** The last few trades. Outcome is a word, so it never depends on colour. */
export function RecentTrades({ trades }: { trades: OverviewResponse["recent_trades"] }) {
  return (
    <section className="mt-10">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-xl font-bold">Recent trades</h2>
        <Link href="/app/journal" className="text-sm text-accent hover:underline">View all →</Link>
      </div>
      {trades.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            title="Nothing logged in this period"
            description="Trades you log appear here, most recent first."
            action={{ href: "/app/trades/new", label: "Log completed trade" }}
          />
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full min-w-[40rem] text-sm">
            <thead>
              <tr className="border-b border-line text-left font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                <th scope="col" className="px-4 py-3">Date</th>
                <th scope="col" className="px-4 py-3">Asset</th>
                <th scope="col" className="px-4 py-3">Session</th>
                <th scope="col" className="px-4 py-3">Setup</th>
                <th scope="col" className="px-4 py-3">Result</th>
                <th scope="col" className="px-4 py-3 text-right">P&amp;L</th>
                <th scope="col" className="px-4 py-3 text-right">R</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-3 font-mono text-xs">{t.trade_date ?? "—"}</td>
                  <td className="px-4 py-3">{t.asset ?? "—"}</td>
                  <td className="px-4 py-3 text-muted">{t.session ?? "—"}</td>
                  <td className="px-4 py-3 text-muted">{t.setup_type ?? "—"}</td>
                  <td className="px-4 py-3">{t.result ?? "—"}</td>
                  <td
                    className={`px-4 py-3 text-right font-mono ${(t.pnl ?? 0) > 0 ? "text-positive" : (t.pnl ?? 0) < 0 ? "text-negative" : ""}`}
                  >
                    {money(t.pnl)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-muted">
                    {t.rr_realized === null || t.rr_realized === undefined ? "—" : `${t.rr_realized.toFixed(2)}R`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
