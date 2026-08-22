import type { OverviewResponse } from "@/lib/app/overview";

const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"];

const money = (n: number) => `$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

/**
 * The month's trading days.
 *
 * **Outcome is encoded by shape as well as colour.** Measured against a dark
 * surface, the positive and negative tokens are ΔE 2.3 apart under
 * deuteranopia — the same colour to the most common colour-vision deficiency,
 * and obviously different to everyone else, which is exactly how a calendar
 * like this ships unreadable. A winning day is a filled circle; a losing day
 * is a square.
 *
 * A day with no trade is left blank rather than greyed: an untraded day is
 * information, not missing data, and a sparse month is a truthful picture of a
 * sparse month.
 */
export function TradingCalendar({
  calendar,
  sample,
}: {
  calendar: OverviewResponse["calendar"];
  sample: OverviewResponse["sample"];
}) {
  if (!sample.show_summary) return null;

  const byDay = new Map(calendar.days.map((d) => [Number(d.date.slice(8, 10)), d]));
  const first = new Date(Date.UTC(calendar.year, calendar.month - 1, 1));
  const daysInMonth = new Date(Date.UTC(calendar.year, calendar.month, 0)).getUTCDate();
  // Monday-first: JS getUTCDay() is 0=Sunday.
  const leading = (first.getUTCDay() + 6) % 7;
  const cells: Array<number | null> = [
    ...Array(leading).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Trading days</h2>
      {!sample.show_dominant_series ? (
        <div className="mt-4 rounded-xl border border-line bg-surface p-6">
          <p className="text-sm text-muted">
            Not enough trading days to read a month yet. The calendar fills in as you log trades.
          </p>
        </div>
      ) : (
        <div className="mt-4 rounded-xl border border-line bg-surface p-4">
          <div className="font-mono text-sm text-text">
            {MONTHS[calendar.month - 1]} {calendar.year}
          </div>
          <div className="mt-3 grid grid-cols-7 gap-1">
            {WEEKDAYS.map((d, i) => (
              <div key={i} className="pb-1 text-center font-mono text-[10px] text-muted">{d}</div>
            ))}
            {cells.map((day, i) => {
              if (day === null) return <div key={`pad-${i}`} />;
              const entry = byDay.get(day);
              const label = entry
                ? `${day} ${MONTHS[calendar.month - 1]} ${calendar.year}, ${entry.pnl >= 0 ? "up" : "down"} ${money(entry.pnl)}`
                : undefined;
              return (
                <div
                  key={day}
                  aria-label={label}
                  data-outcome={entry?.outcome}
                  className="flex h-9 flex-col items-center justify-center rounded"
                >
                  <span className="font-mono text-[11px] text-muted">{day}</span>
                  {entry && (
                    <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true" className="mt-0.5">
                      {entry.outcome === "positive" ? (
                        <circle cx="4" cy="4" r="3" fill="#22c55e" />
                      ) : entry.outcome === "negative" ? (
                        <rect x="1" y="1" width="6" height="6" fill="#f56565" />
                      ) : (
                        <line x1="1" y1="4" x2="7" y2="4" stroke="#9aa4b2" strokeWidth="1.5" />
                      )}
                    </svg>
                  )}
                </div>
              );
            })}
          </div>
          <p className="mt-3 font-mono text-[10px] text-muted">
            ● winning day · ■ losing day · — flat. Blank days had no trade.
          </p>
        </div>
      )}
    </section>
  );
}
