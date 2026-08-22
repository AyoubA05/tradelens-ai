import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDiscipline } from "@/components/app/overview/risk-discipline";

// edge_leak.amount is `Undefinable` ({ value, state }) in the generated
// schema, not a bare number — the schema is the source of truth.
const risk = {
  max_drawdown: { value: -220, state: null },
  rule_adherence: { rate: 0.67, followed: 2, recorded: 3 },
  edge_leak: { amount: { value: -220, state: null }, trades: 1, recorded: 3 },
  consistency: { value: null, state: "undefined_nan" },
};
const sample = {
  trades: 5, dated_points: 5, show_summary: true, show_series: true,
  show_dominant_series: true, show_comparisons: true, show_patterns: true,
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
    expect(screen.getByText(/not yet/i)).toBeInTheDocument();
  });

  it("renders nothing measurable when the sample has not earned it", () => {
    render(<RiskDiscipline risk={risk} sample={{ ...sample, show_summary: false }} />);
    expect(screen.queryByText("Max drawdown")).not.toBeInTheDocument();
  });
});
