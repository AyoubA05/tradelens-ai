import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDiscipline } from "@/components/app/overview/risk-discipline";
import type { OverviewResponse } from "@/lib/app/overview";

// edge_leak.amount is `Undefinable` ({ value, state }) in the generated
// schema, not a bare number — the schema is the source of truth.
// max_drawdown is a POSITIVE magnitude from metrics.compute_max_drawdown —
// the fixture used to carry -220, which no service ever emits, and that hid
// the fact that the component's `value < 0` tone test could never fire.
const risk: OverviewResponse["risk"] = {
  max_drawdown: { value: 220, state: null },
  rule_adherence: { rate: 0.67, followed: 2, recorded: 3 },
  edge_leak: { amount: { value: -95, state: null }, trades: 1, recorded: 3 },
  consistency: { value: null, state: "undefined_nan" },
};
const sample = {
  trades: 5, dated_points: 5, show_summary: true, show_series: true,
  show_dominant_series: true, show_comparisons: true, show_patterns: true,
  pnl_recorded: 5, pnl_complete: true,
};

describe("risk and discipline", () => {
  it("asks whether the numbers describe a process or a run of luck", () => {
    render(<RiskDiscipline risk={risk} sample={sample} />);
    expect(screen.getByText(/Risk and discipline/i)).toBeInTheDocument();
    for (const label of ["Max drawdown", "Rule adherence", "Edge leak", "Consistency"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("shows adherence as a rate with its sample size", () => {
    render(<RiskDiscipline risk={risk} sample={sample} />);
    expect(screen.getByText("67%")).toBeInTheDocument();
    expect(screen.getByText(/2 of 3/)).toBeInTheDocument();
  });

  it("says a consistency score is not yet earned rather than showing zero", () => {
    render(<RiskDiscipline risk={risk} sample={sample} />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText(/not enough data/i)).toBeInTheDocument();
  });

  it("writes a drawdown as the loss it is, in text and not only in colour", () => {
    render(<RiskDiscipline risk={risk} sample={sample} />);
    const value = screen.getByText("-$220.00");
    expect(value).toBeInTheDocument();
    expect(value).toHaveClass("text-negative");
    expect(screen.getByText(/deepest fall from a peak/i)).toBeInTheDocument();
  });

  it("leaves a drawdown of nothing unsigned and untoned", () => {
    render(<RiskDiscipline risk={{ ...risk, max_drawdown: { value: 0, state: null } }} sample={sample} />);
    const value = screen.getByText("$0.00");
    expect(value).toHaveClass("text-text");
  });

  it("warns that profitable rule-breaking is not repeatable edge", () => {
    render(
      <RiskDiscipline
        risk={{
          ...risk,
          edge_leak: { amount: { value: 95, state: null }, trades: 1, recorded: 3 },
        }}
        sample={sample}
      />,
    );
    expect(screen.getByText(/rule-breaking trades were profitable/i)).toBeInTheDocument();
    expect(screen.getByText(/not repeatable edge/i)).toBeInTheDocument();
  });

  it("renders nothing measurable when the sample has not earned it", () => {
    render(<RiskDiscipline risk={risk} sample={{ ...sample, show_summary: false }} />);
    expect(screen.queryByText("Max drawdown")).not.toBeInTheDocument();
  });
});
