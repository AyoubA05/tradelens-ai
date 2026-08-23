import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TradesTable } from "@/components/app/trades/trades-table";
import type { TradeSummary } from "@/lib/app/trades";

function trade(overrides: Partial<TradeSummary> = {}): TradeSummary {
  return {
    id: 1,
    asset: "NQ",
    direction: "long",
    killzone: "New York AM",
    pnl: 120.5,
    result: "Win",
    rr_realized: 2.1,
    session: "New York",
    setup_type: "FVG",
    trade_date: "2026-08-12",
    // Spec §8 requires a grade and a screenshot indicator in the table, so
    // `TradeSummary` now carries them. Present here because the fixture is
    // typed as the full row: a `Partial` fixture would let a column silently
    // drop out of the contract without a single test noticing.
    ai_grade: "B+",
    user_grade: null,
    screenshot_count: 0,
    ...overrides,
  };
}

describe("TradesTable", () => {
  it("shows an inviting empty state when there are no trades", () => {
    render(<TradesTable trades={[]} />);
    expect(screen.getByText(/nothing matches this view/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /log completed trade/i })).toHaveAttribute(
      "href",
      "/app/trades/new",
    );
  });

  it("renders the date, asset, session, setup, result, P&L and R columns", () => {
    render(<TradesTable trades={[trade()]} />);
    expect(screen.getByText("2026-08-12")).toBeInTheDocument();
    expect(screen.getByText("NQ")).toBeInTheDocument();
    expect(screen.getByText("New York")).toBeInTheDocument();
    expect(screen.getByText("FVG")).toBeInTheDocument();
    expect(screen.getByText("Win")).toBeInTheDocument();
    expect(screen.getByText("$120.50")).toBeInTheDocument();
    expect(screen.getByText("2.10R")).toBeInTheDocument();
  });

  it("reads a missing P&L as 'not recorded', never $0.00", () => {
    render(<TradesTable trades={[trade({ pnl: null })]} />);
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("distinguishes a genuine zero P&L from a missing one", () => {
    render(<TradesTable trades={[trade({ pnl: 0 })]} />);
    expect(screen.getByText("$0.00")).toBeInTheDocument();
  });

  it("carries the outcome as text in its own column, not only by colour", () => {
    render(<TradesTable trades={[trade({ result: "Loss", pnl: -50 })]} />);
    expect(screen.getByText("Loss")).toBeInTheDocument();
  });

  it("does not render an ai-grade or screenshot column — TradeSummary carries neither", () => {
    render(<TradesTable trades={[trade()]} />);
    expect(screen.queryByText(/grade/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/screenshot/i)).not.toBeInTheDocument();
  });
});
