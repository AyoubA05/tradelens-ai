import { MetricValueText } from "@/components/app/analytics/metric-value";
import type { AnalyticsResponse } from "@/lib/app/analytics";

type Breakdown = AnalyticsResponse["timing"]["by_day_of_week"];

/**
 * The rows of one category breakdown.
 *
 * The table lives inside its own horizontal scroller, because the alternative
 * is a page body that scrolls sideways on a phone and takes the rest of the
 * lens with it. Numbers are mono so columns line up down the page.
 *
 * Each category carries a share bar sized against the busiest row — and only
 * when there is more than one row. A single row's bar is always full width,
 * which reads as dominance over a field of one.
 *
 * The bar is aria-hidden and carries no meaning of its own: the trade count is
 * written out in its own column. Nothing here ranks, recommends or suggests.
 */
export function BreakdownTable({ id, breakdown }: { id: string; breakdown: Breakdown }) {
  const busiest = breakdown.rows.reduce((acc, row) => Math.max(acc, row.trades), 0);
  const comparable = breakdown.rows.length > 1 && busiest > 0;

  return (
    <div data-testid={`breakdown-${id}-scroll`} className="mt-3 overflow-x-auto">
      <table className="w-full min-w-[28rem] border-collapse text-sm">
        <thead>
          <tr className="border-b border-line text-left">
            <th
              scope="col"
              className="py-2 pr-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted"
            >
              Category
            </th>
            <th
              scope="col"
              className="py-2 pr-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted"
            >
              Trades
            </th>
            <th
              scope="col"
              className="py-2 pr-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted"
            >
              Net P&amp;L
            </th>
            <th
              scope="col"
              className="py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted"
            >
              Win rate
            </th>
          </tr>
        </thead>
        <tbody>
          {breakdown.rows.map((row) => (
            <tr key={row.key} className="border-b border-line/60 last:border-b-0">
              <th scope="row" className="py-2 pr-4 text-left font-normal text-text">
                <span className="block">{row.key}</span>
                {comparable ? (
                  <span className="mt-1 block h-1 w-full max-w-[8rem] rounded-full bg-line/60">
                    <span
                      data-testid={`breakdown-${id}-bar-${row.key}`}
                      aria-hidden="true"
                      className="block h-1 rounded-full bg-line"
                      style={{ width: `${(row.trades / busiest) * 100}%` }}
                    />
                  </span>
                ) : null}
              </th>
              <td className="py-2 pr-4 font-mono text-text">{row.trades}</td>
              <td className="py-2 pr-4 font-mono text-text">
                <MetricValueText value={row.total_pnl} kind="money" />
              </td>
              <td className="py-2 font-mono text-text">
                <MetricValueText value={row.win_rate} kind="percent" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
