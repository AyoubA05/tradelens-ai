import Link from "next/link";

import { EmptyState } from "@/components/app/states/empty-state";
import { money, NO_VALUE } from "@/lib/app/format";
import type { TradeSummary } from "@/lib/app/trades";

/** A P&L a trade may never have recorded. Absent is not zero. */
const optionalMoney = (n: number | null | undefined) =>
  n === null || n === undefined ? NO_VALUE : money(n);

/**
 * The accessible name of a row's link.
 *
 * Built from what the row already shows, so a screen reader hears which
 * trade it is about to open. A column of identical "View" links would be
 * navigable but useless: the visible cell text is the date alone, which on
 * a day with several trades identifies nothing.
 */
function tradeLinkLabel(t: TradeSummary): string {
  const parts = [t.trade_date, t.asset, t.session, t.setup_type, t.result].filter(
    (part): part is string => Boolean(part),
  );
  return parts.length > 0 ? parts.join(", ") : `Trade ${t.id}`;
}

/**
 * The Trades table.
 *
 * Columns: date, asset, session, setup, result, P&L, R — every one of them a
 * field `GET /v1/trades` actually returns. `TradeSummary` also carries
 * `ai_grade`, `user_grade` and `screenshot_count`; those are available to
 * render but are not columns here yet. The rule the other way round is the
 * load-bearing one: nothing may appear in this table that the contract does
 * not supply, because the alternative is a column invented client-side or
 * fetched per row, which defeats the point of a list endpoint.
 *
 * Each row's date cell is a link into `/app/trades/[id]` — opening a trade
 * from the list is spec §8 behaviour.
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
            <tr
              key={t.id}
              className="border-b border-line/60 transition-colors duration-150 ease-tl last:border-0 hover:bg-surface-2"
            >
              <td className="px-4 py-3 font-mono text-xs">
                {/*
                  A real anchor, not a row `onClick`: middle-click, cmd-click
                  and "open in new tab" all have to work, and a keyboard user
                  needs a focusable target — none of which a click handler on
                  a <tr> gives. Rendered in the date cell so each row has
                  exactly one link, named for the trade it opens.
                */}
                <Link
                  href={`/app/trades/${t.id}`}
                  aria-label={tradeLinkLabel(t)}
                  className="rounded-sm underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-accent"
                >
                  {t.trade_date ?? NO_VALUE}
                </Link>
              </td>
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
