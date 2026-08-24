import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JournalCalendar } from "@/components/app/trades/journal-calendar";
import type { OverviewResponse } from "@/lib/app/overview";

const sample: OverviewResponse["sample"] = {
  show_summary: true,
  show_dominant_series: true,
} as OverviewResponse["sample"];

const period: OverviewResponse["period"] = { from: "2026-08-01", to: "2026-08-18" } as OverviewResponse["period"];

const calendar: OverviewResponse["calendar"] = {
  year: 2026,
  month: 8,
  days: [
    { date: "2026-08-05", outcome: "positive", pnl: 200 },
    { date: "2026-08-06", outcome: "negative", pnl: -80 },
    { date: "2026-08-07", outcome: "unknown", pnl: null },
  ],
};

describe("JournalCalendar", () => {
  it("renders nothing when the sample doesn't support a summary", () => {
    const { container } = render(
      <JournalCalendar
        calendar={calendar}
        period={period}
        sample={{ ...sample, show_summary: false }}
        filters={{}}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("links a day with trades into that day's filtered list", () => {
    render(<JournalCalendar calendar={calendar} period={period} sample={sample} filters={{}} />);
    const link = screen.getByRole("link", { name: /5 August 2026/i });
    expect(link).toHaveAttribute("href", "/app/journal?from=2026-08-05&to=2026-08-05");
  });

  it("carries the active filters onto the day link", () => {
    render(
      <JournalCalendar
        calendar={calendar}
        period={period}
        sample={sample}
        filters={{ asset: "NQ", result: "Win" }}
      />,
    );
    const link = screen.getByRole("link", { name: /5 August 2026/i });
    const params = new URLSearchParams(link.getAttribute("href")!.split("?")[1]);
    expect(params.get("asset")).toBe("NQ");
    expect(params.get("result")).toBe("Win");
    expect(params.get("from")).toBe("2026-08-05");
    expect(params.get("to")).toBe("2026-08-05");
  });

  it("names that the calendar aggregate is unfiltered when the table is filtered", () => {
    render(
      <JournalCalendar
        calendar={calendar}
        period={period}
        sample={sample}
        filters={{ asset: "NQ", result: "Win" }}
      />,
    );

    expect(
      screen.getByText(/active filters apply to the table and day links, not these daily totals/i),
    ).toBeInTheDocument();
  });

  it("does not link an untraded day", () => {
    render(<JournalCalendar calendar={calendar} period={period} sample={sample} filters={{}} />);
    // Day 10 has no calendar entry and is inside the window.
    expect(screen.queryByRole("link", { name: /10 August 2026/i })).not.toBeInTheDocument();
  });

  it("marks a day outside the selected period as dimmed, not linked", () => {
    render(<JournalCalendar calendar={calendar} period={period} sample={sample} filters={{}} />);
    const outside = screen.getByLabelText(/20 August 2026, outside the selected period/i);
    expect(outside.tagName).toBe("DIV");
  });
});
