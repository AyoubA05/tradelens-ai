import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TradingCalendar } from "@/components/app/overview/trading-calendar";

const calendar = {
  year: 2026,
  month: 8,
  days: [
    { date: "2026-08-12", pnl: 480, outcome: "positive" },
    { date: "2026-08-13", pnl: -220, outcome: "negative" },
    { date: "2026-08-15", pnl: 410, outcome: "positive" },
  ],
};
const sample = {
  trades: 5, dated_points: 4, show_summary: true, show_series: true,
  show_dominant_series: true, show_comparisons: true, show_patterns: true,
};

describe("trading calendar", () => {
  it("names the month it is showing", () => {
    render(<TradingCalendar calendar={calendar} sample={sample} />);
    expect(screen.getByText(/August 2026/)).toBeInTheDocument();
  });

  it("marks traded days and leaves untraded ones blank", () => {
    render(<TradingCalendar calendar={calendar} sample={sample} />);
    expect(screen.getByLabelText(/12 August 2026, up \$480/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/13 August 2026, down \$220/i)).toBeInTheDocument();
    // The 14th had no trade, which is information rather than missing data.
    expect(screen.queryByLabelText(/14 August 2026, up/i)).not.toBeInTheDocument();
  });

  it("exposes labelled days by role, since aria-label alone is not reliably announced on a bare div", () => {
    render(<TradingCalendar calendar={calendar} sample={sample} />);
    expect(screen.getByRole("img", { name: /12 August 2026, up \$480/i })).toBeInTheDocument();
  });

  it("distinguishes outcome by SHAPE, not only by colour", () => {
    // The positive and negative tokens are ΔE 2.3 apart under deuteranopia.
    // Colour alone would make this calendar unreadable for those readers.
    const { container } = render(<TradingCalendar calendar={calendar} sample={sample} />);
    expect(container.querySelectorAll('[data-outcome="positive"] circle').length).toBe(2);
    expect(container.querySelectorAll('[data-outcome="negative"] rect').length).toBe(1);
  });

  it("explains itself when the month is too sparse to read", () => {
    render(
      <TradingCalendar
        calendar={{ ...calendar, days: calendar.days.slice(0, 1) }}
        sample={{ ...sample, show_dominant_series: false, dated_points: 1 }}
      />,
    );
    expect(screen.getByText(/not enough trading days/i)).toBeInTheDocument();
  });
});
