import { EmptyState } from "@/components/app/states/empty-state";
import { money, NO_VALUE } from "@/lib/app/format";
import type { TradeSummary } from "@/lib/app/trades";

/** A P&L a trade may never have recorded. Absent is not zero. */
const optionalMoney = (n: number | null | undefined) =>
  n === null || n === undefined ? NO_VALUE : money(n);

/**
 * The Trades table.
 *
 * Columns: date, asset, session, setup, result, P&L, R. `TradeSummary` — the
 * row shape `GET /v1/trades` actually returns — carries none of `ai_grade`,
 * `user_grade`, or a screenshot count; those live only on `TradeDetail`. A
 * grade or screenshot column here would have to be invented client-side or
 * fetched per row, defeating the point of a list endpoint, so this table
 * renders exactly the fields the contract carries and nothing implied by
 * wording elsewhere.
 *
 * Outcome is the `Result` column's own text ("Win"/"Loss"/"Breakeven"), never
 * inferred from the P&L figure's colour — a `0` result and a not-recorded
 * result must not collapse into the same "no colour" reading.
 */
export function TradesTable({ trades }: { trades: TradeSummary[] }) {
  if (trades.length === 0) {
    return (
      <div className="mt-4">
        <EmptyState
          title="Nothing matches this view"
          description="Trades logged for the selected period and filters appear here."
          action={{ href: "/app/trades/new", label: "Log completed trade" }}
        />
      </div>
    );
  }

  return (
    <div className="mt-4 overflow-x-auto rounded-xl border border-line bg-surface">
      <table className="w-full min-w-[44rem] text-sm">
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
              <td className="px-4 py-3 font-mono text-xs">{t.trade_date ?? NO_VALUE}</td>
              <td className="px-4 py-3">{t.asset ?? NO_VALUE}</td>
              <td className="px-4 py-3 text-muted">{t.session ?? NO_VALUE}</td>
              <td className="px-4 py-3 text-muted">{t.setup_type ?? NO_VALUE}</td>
              <td className="px-4 py-3">{t.result ?? NO_VALUE}</td>
              <td
                className={`px-4 py-3 text-right font-mono ${(t.pnl ?? 0) > 0 ? "text-positive" : (t.pnl ?? 0) < 0 ? "text-negative" : ""}`}
              >
                {optionalMoney(t.pnl)}
              </td>
              <td className="px-4 py-3 text-right font-mono text-muted">
                {t.rr_realized === null || t.rr_realized === undefined
                  ? NO_VALUE
                  : `${t.rr_realized.toFixed(2)}R`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
