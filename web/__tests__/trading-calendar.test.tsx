import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TradingCalendar } from "@/components/app/overview/trading-calendar";
import type { OverviewResponse } from "@/lib/app/overview";

const calendar: OverviewResponse["calendar"] = {
  year: 2026,
  month: 8,
  days: [
    { date: "2026-08-12", pnl: 480, outcome: "positive" },
    { date: "2026-08-13", pnl: -220, outcome: "negative" },
    { date: "2026-08-15", pnl: 410, outcome: "positive" },
  ],
};
// The whole of August: the default case, where every rendered cell is inside
// the window.
const wholeMonth = { from: "2026-08-01", to: "2026-08-31" };
const sample = {
  trades: 5, dated_points: 4, show_summary: true, show_series: true,
  show_dominant_series: true, show_comparisons: true, show_patterns: true,
  pnl_recorded: 5, pnl_complete: true,
};

describe("trading calendar", () => {
  it("names the month it is showing", () => {
    render(<TradingCalendar calendar={calendar} period={wholeMonth} sample={sample} />);
    expect(screen.getByText(/August 2026/)).toBeInTheDocument();
  });

  it("marks traded days and leaves untraded ones blank", () => {
    render(<TradingCalendar calendar={calendar} period={wholeMonth} sample={sample} />);
    expect(screen.getByLabelText(/12 August 2026, up \$480/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/13 August 2026, down \$220/i)).toBeInTheDocument();
    // The 14th had no trade, which is information rather than missing data.
    expect(screen.queryByLabelText(/14 August 2026, up/i)).not.toBeInTheDocument();
  });

  it("exposes labelled days by role, since aria-label alone is not reliably announced on a bare div", () => {
    render(<TradingCalendar calendar={calendar} period={wholeMonth} sample={sample} />);
    expect(screen.getByRole("img", { name: /12 August 2026, up \$480/i })).toBeInTheDocument();
  });

  it("distinguishes outcome by SHAPE, not only by colour", () => {
    // The positive and negative tokens are ΔE 2.3 apart under deuteranopia.
    // Colour alone would make this calendar unreadable for those readers.
    const { container } = render(<TradingCalendar calendar={calendar} period={wholeMonth} sample={sample} />);
    expect(container.querySelectorAll('[data-outcome="positive"] circle').length).toBe(2);
    expect(container.querySelectorAll('[data-outcome="negative"] rect').length).toBe(1);
  });

  it("marks a flat day flat rather than announcing it as up", () => {
    // The glyph used the three-way outcome field while the label tested
    // pnl >= 0, so a $0 day was announced "up $0".
    render(
      <TradingCalendar
        calendar={{ ...calendar, days: [{ date: "2026-08-12", pnl: 0, outcome: "flat" }] }}
        period={wholeMonth}
        sample={sample}
      />,
    );
    expect(screen.getByLabelText(/12 August 2026, flat \$0/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/12 August 2026, up/i)).not.toBeInTheDocument();
  });

  it("distinguishes a trade with missing P&L from a flat trade", () => {
    render(
      <TradingCalendar
        calendar={{
          ...calendar,
          days: [{ date: "2026-08-12", pnl: null, outcome: "unknown" }],
        }}
        period={wholeMonth}
        sample={{ ...sample, pnl_complete: false, pnl_recorded: 4 }}
      />,
    );
    expect(screen.getByLabelText(/12 August 2026, P&L not recorded/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/12 August 2026, flat/i)).not.toBeInTheDocument();
  });

  it("separates days outside the period from days inside it with no trade", () => {
    // The month comes from the period END but the days come from the
    // period-filtered frame, so a window that starts and ends mid-month leaves
    // real calendar cells the trader was never asked about. Drawn like plain
    // untraded days under "Blank days had no trade", they asserted something
    // false.
    const { container } = render(
      <TradingCalendar
        calendar={calendar}
        period={{ from: "2026-08-10", to: "2026-08-20" }}
        sample={sample}
      />,
    );
    const outside = container.querySelectorAll('[data-window="outside"]');
    expect(outside.length).toBe(20); // 1–9 and 21–31
    expect(screen.getByLabelText(/25 August 2026, outside the selected period/i)).toBeInTheDocument();
    // A day inside the window with no trade stays plainly blank.
    expect(container.querySelector('[data-window="inside"]')).toBeTruthy();
    expect(screen.getByText(/dashed, dimmed days fall outside the selected period/i)).toBeInTheDocument();
  });

  it("explains itself when the month is too sparse to read", () => {
    render(
      <TradingCalendar
        calendar={{ ...calendar, days: calendar.days.slice(0, 1) }}
        period={wholeMonth}
        sample={{ ...sample, show_dominant_series: false, dated_points: 1 }}
      />,
    );
    expect(screen.getByText(/not enough trading days/i)).toBeInTheDocument();
  });
});
