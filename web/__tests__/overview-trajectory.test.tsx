import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Trajectory } from "@/components/app/overview/trajectory";
import { RecurringEdge } from "@/components/app/overview/recurring-edge";

const trajectory = {
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
};

describe("trajectory", () => {
  it("shows the path the account took", () => {
    render(<Trajectory trajectory={trajectory} sample={sample} />);
    expect(screen.getByText(/Performance trajectory/i)).toBeInTheDocument();
    expect(screen.getByText("Average win")).toBeInTheDocument();
    expect(screen.getByText("Average loss")).toBeInTheDocument();
  });
});

describe("recurring edge", () => {
  it("shows where the account repeats itself, with sample sizes", () => {
    render(
      <RecurringEdge
        edge={{
          killzones: [{ label: "NY AM", net_pnl: 670, trades: 3 }],
          setups: [{ label: "Liquidity Sweep + FVG", net_pnl: 670, trades: 3 }],
        }}
        sample={sample}
      />,
    );
    expect(screen.getByText("NY AM")).toBeInTheDocument();
    expect(screen.getByText("Liquidity Sweep + FVG")).toBeInTheDocument();
    expect(screen.getAllByText(/n=3/).length).toBeGreaterThan(0);
  });

  it("withholds comparisons the sample has not earned", () => {
    render(
      <RecurringEdge
        edge={{ killzones: [{ label: "NY AM", net_pnl: 1, trades: 1 }], setups: [] }}
        sample={{ ...sample, show_comparisons: false }}
      />,
    );
    expect(screen.queryByText("NY AM")).not.toBeInTheDocument();
    expect(screen.getByText(/not enough trades to compare/i)).toBeInTheDocument();
  });
});
