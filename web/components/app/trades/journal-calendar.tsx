import Link from "next/link";

import { money } from "@/lib/app/format";
import { filtersToParams, type TradeFilters } from "@/lib/app/trade-filters";
import type { OverviewResponse } from "@/lib/app/overview";

const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"];

const DIRECTION: Record<string, string> = { positive: "up", negative: "down", flat: "flat" };

/**
 * The Journal's month calendar.
 *
 * Reuses Overview's `TradingCalendar` shape encoding exactly — filled circle
 * for a winning day, square for a losing day, dash for flat, diamond for P&L
 * not recorded — and its dashed/dimmed treatment for days outside the
 * selected period, because that encoding is what a returning reader already
 * knows how to read. It is a separate component rather than an import of
 * `TradingCalendar` because this one has to be interactive: a day with
 * trades links into the filtered Journal list for that single day, which
 * Overview's non-interactive calendar has no reason to do.
 *
 * The `calendar`/`period`/`sample` shape comes from `OverviewResponse` — the
 * Trades list endpoint has no per-day aggregate of its own, and re-deriving
 * one client-side from a paginated page of trades would only be correct for
 * a period with fewer trades than the page size. Overview already computes
 * this aggregate correctly over the whole period server-side, so the Journal
 * page fetches it the same way Overview does and reuses it here.
 *
 * A day's link carries the active filters forward (`asset`, `session`,
 * `setup`, `result`) and narrows the period to that single date — the URL
 * stays the filter and period state of record, so following the link is
 * indistinguishable from a reader hand-typing that day into the period lens.
 */
export function JournalCalendar({
  calendar,
  period,
  sample,
  filters,
}: {
  calendar: OverviewResponse["calendar"];
  period: OverviewResponse["period"];
  sample: OverviewResponse["sample"];
  filters: TradeFilters;
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

  const month = String(calendar.month).padStart(2, "0");
  const isoFor = (day: number) => `${calendar.year}-${month}-${String(day).padStart(2, "0")}`;
  // ISO dates sort lexicographically, so no Date parsing (and no timezone) is
  // needed to decide whether a day falls inside the analysed window.
  const inWindow = (day: number) => {
    const iso = isoFor(day);
    return iso >= period.from && iso <= period.to;
  };
  const hasOutside = cells.some((d) => d !== null && !inWindow(d));
  const hasActiveFilters = Object.values(filters).some(Boolean);

  function hrefForDay(day: number): string {
    const iso = isoFor(day);
    const params = filtersToParams(filters);
    params.set("from", iso);
    params.set("to", iso);
    return `/app/journal?${params.toString()}`;
  }

  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Trading days</h2>
      {hasActiveFilters && (
        <p className="mt-2 text-sm text-muted">
          Calendar totals include every trade in the selected period. Active filters apply to
          the table and day links, not these daily totals.
        </p>
      )}
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
              const outside = !inWindow(day);
              const label = entry
                ? entry.outcome === "unknown"
                  ? `${day} ${MONTHS[calendar.month - 1]} ${calendar.year}, P&L not recorded`
                  : `${day} ${MONTHS[calendar.month - 1]} ${calendar.year}, ${DIRECTION[entry.outcome]} ${money(entry.pnl ?? 0, { decimals: 0, sign: false })}`
                : outside
                  ? `${day} ${MONTHS[calendar.month - 1]} ${calendar.year}, outside the selected period`
                  : undefined;

              const dayGlyph = entry && (
                <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true" className="mt-0.5">
                  {entry.outcome === "positive" ? (
                    <circle cx="4" cy="4" r="3" fill="#22c55e" />
                  ) : entry.outcome === "negative" ? (
                    <rect x="1" y="1" width="6" height="6" fill="#f56565" />
                  ) : entry.outcome === "unknown" ? (
                    <path d="M4 0.8 7.2 4 4 7.2 0.8 4Z" fill="none" stroke="#9aa4b2" strokeWidth="1.2" />
                  ) : (
                    <line x1="1" y1="4" x2="7" y2="4" stroke="#9aa4b2" strokeWidth="1.5" />
                  )}
                </svg>
              );

              // Only a day that actually has trades links anywhere — an
              // untraded day inside the window has nothing to open, and an
              // out-of-window day was never asked about.
              if (entry) {
                return (
                  <Link
                    key={day}
                    href={hrefForDay(day)}
                    aria-label={label}
                    data-outcome={entry.outcome}
                    data-window="inside"
                    className="flex h-9 flex-col items-center justify-center rounded transition-colors duration-150 ease-tl hover:bg-surface-2"
                  >
                    <span className="font-mono text-[11px] text-muted">{day}</span>
                    {dayGlyph}
                  </Link>
                );
              }

              return (
                <div
                  key={day}
                  role={label ? "img" : undefined}
                  aria-label={label}
                  data-window={outside ? "outside" : "inside"}
                  className={`flex h-9 flex-col items-center justify-center rounded ${
                    outside ? "border border-dashed border-line/70 opacity-40" : ""
                  }`}
                >
                  <span className="font-mono text-[11px] text-muted">{day}</span>
                </div>
              );
            })}
          </div>
          <p className="mt-3 font-mono text-[10px] text-muted">
            ● winning day · ■ losing day · — flat · ◇ P&amp;L not recorded. Blank days inside {period.from} to {period.to}
            {" "}had no trade
            {hasOutside ? "; dashed, dimmed days fall outside the selected period." : "."}
            {" "}A day with trades opens that day&apos;s list.
          </p>
        </div>
      )}
    </section>
  );
}
