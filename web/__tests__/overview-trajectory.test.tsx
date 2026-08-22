import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Trajectory } from "@/components/app/overview/trajectory";
import { RecurringEdge } from "@/components/app/overview/recurring-edge";
import type { OverviewResponse } from "@/lib/app/overview";

const trajectory: OverviewResponse["trajectory"] = {
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
};
const sample = {
  trades: 5, dated_points: 4, show_summary: true, show_series: true,
  show_dominant_series: true, show_comparisons: true, show_patterns: true,
  pnl_recorded: 5, pnl_complete: true,
};

describe("trajectory", () => {
  it("shows the path the account took", () => {
    render(<Trajectory trajectory={trajectory} sample={sample} />);
    expect(screen.getByText(/Performance trajectory/i)).toBeInTheDocument();
    expect(screen.getByText("Average win")).toBeInTheDocument();
    expect(screen.getByText("Average loss")).toBeInTheDocument();
  });

  it("says which way a streak runs, in a word", () => {
    render(<Trajectory trajectory={{ ...trajectory, current_streak: -3, streak_type: "loss" }} sample={sample} />);
    const value = screen.getByText("3 losses");
    expect(value).toBeInTheDocument();
    expect(value).toHaveClass("text-negative");
  });

  it("does not leave a win streak to be told apart by colour", () => {
    render(<Trajectory trajectory={{ ...trajectory, current_streak: 2, streak_type: "win" }} sample={sample} />);
    expect(screen.getByText("2 wins")).toBeInTheDocument();
  });

  it("names an absent streak rather than printing a zero", () => {
    render(<Trajectory trajectory={{ ...trajectory, current_streak: 0, streak_type: "none" }} sample={sample} />);
    expect(screen.getByText("No run")).toBeInTheDocument();
  });

  it("explains an empty average instead of leaving a bare dash", () => {
    render(
      <Trajectory
        trajectory={{ ...trajectory, average_win: { value: null, state: "undefined_no_sample" } }}
        sample={sample}
      />,
    );
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText(/not enough data/i)).toBeInTheDocument();
  });
});

describe("recurring edge", () => {
  it("shows where the account repeats itself, with sample sizes", () => {
    render(
      <RecurringEdge
        edge={{
          killzones: [{ label: "New York AM", net_pnl: 670, trades: 3 }],
          setups: [{ label: "Liquidity Sweep + FVG", net_pnl: 670, trades: 3 }],
        }}
        sample={sample}
      />,
    );
    expect(screen.getByText("New York AM")).toBeInTheDocument();
    expect(screen.getByText("Liquidity Sweep + FVG")).toBeInTheDocument();
    expect(screen.getAllByText(/n=3/).length).toBeGreaterThan(0);
  });

  it("withholds comparisons the sample has not earned", () => {
    render(
      <RecurringEdge
        edge={{ killzones: [{ label: "New York AM", net_pnl: 1, trades: 1 }], setups: [] }}
        sample={{ ...sample, show_comparisons: false }}
      />,
    );
    expect(screen.queryByText("New York AM")).not.toBeInTheDocument();
    expect(screen.getByText(/not enough trades to compare/i)).toBeInTheDocument();
  });

  it("withholds monetary comparisons when P&L is incomplete", () => {
    render(
      <RecurringEdge
        edge={{ killzones: [], setups: [] }}
        sample={{ ...sample, pnl_complete: false, pnl_recorded: 4 }}
      />,
    );
    expect(screen.getByText(/P&L data is incomplete/i)).toBeInTheDocument();
  });
});
