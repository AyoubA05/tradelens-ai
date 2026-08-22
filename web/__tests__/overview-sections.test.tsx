import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OverviewSections } from "@/components/app/overview/sections";
import type { OverviewResponse } from "@/lib/app/overview";

// Shaped against the generated schema (lib/api/schema.d.ts), not the brief's
// original fixture: win_rate and edge_leak.amount are Undefinable
// {value, state} pairs, and period uses `from`, not `from_`.
const data: OverviewResponse = {
  period: { from: "2026-08-01", to: "2026-08-31" },
  sample: {
    trades: 5,
    dated_points: 4,
    show_summary: true,
    show_series: true,
    show_dominant_series: true,
    show_comparisons: true,
    show_patterns: true,
    pnl_recorded: 5,
    pnl_complete: true,
  },
  kpi: {
    net_pnl: { value: 575, state: null },
    win_rate: { value: 0.4, state: null },
    expectancy: 115,
    expectancy_state: null,
    profit_factor: 2.9,
    profit_factor_state: null,
    trades: 5,
    wins: 2,
    losses: 2,
    today_pnl: { value: 0, state: null },
    week_pnl: { value: 575, state: null },
  },
  risk: {
    max_drawdown: { value: 220, state: null },
    rule_adherence: { rate: 0.67, followed: 2, recorded: 3 },
    edge_leak: { amount: { value: -220, state: null }, trades: 1, recorded: 3 },
    consistency: { value: null, state: "undefined_nan" },
  },
  trajectory: {
    equity_curve: [
      { date: "2026-08-10", equity: 480 },
      { date: "2026-08-11", equity: 260 },
      { date: "2026-08-12", equity: 670 },
      { date: "2026-08-14", equity: 575 },
    ],
    current_streak: 1,
    streak_type: "win",
    best_streak: 1,
    worst_streak: 1,
    average_win: { value: 445, state: null },
    average_loss: { value: -157.5, state: null },
  },
  recurring_edge: {
    killzones: [{ label: "New York AM", net_pnl: 670, trades: 3 }],
    setups: [{ label: "Liquidity Sweep + FVG", net_pnl: 670, trades: 3 }],
  },
  calendar: {
    year: 2026,
    month: 8,
    days: [{ date: "2026-08-12", pnl: 480, outcome: "positive" }],
  },
  next_review_action: {
    completed: 2,
    total: 3,
    next_key: "weekly_review",
    is_activated: false,
    trades_until_review: 2,
  },
  recent_trades: [
    {
      id: 1,
      trade_date: "2026-08-15",
      asset: "NQ",
      session: "New York Open",
      setup_type: "Liquidity Sweep + FVG",
      result: "Win",
      pnl: 410,
      rr_realized: 2.7,
    },
  ],
};

describe("overview sections", () => {
  it("renders every section in reading order", () => {
    render(<OverviewSections data={data} />);
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual([
      "Risk and discipline",
      "Performance trajectory",
      "Recurring edge",
      "Trading days",
      "Next review action",
      "Recent trades",
    ]);
  });

  it("shows the headline figures above everything else", () => {
    render(<OverviewSections data={data} />);
    expect(screen.getByText("Net P&L")).toBeInTheDocument();
  });
});
