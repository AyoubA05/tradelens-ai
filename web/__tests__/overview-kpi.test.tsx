import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatTile } from "@/components/app/overview/stat-tile";
import { KpiRow } from "@/components/app/overview/kpi-row";
import { CurrentStanding } from "@/components/app/overview/current-standing";

// win_rate is `Undefinable` ({ value, state }) in the generated schema, not a
// bare number — the schema is the source of truth, so the fixture follows it.
const kpi = {
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
};
const sample = {
  trades: 5, dated_points: 5, show_summary: true, show_series: true,
  show_dominant_series: true, show_comparisons: true, show_patterns: true,
  pnl_recorded: 5, pnl_complete: true,
};

describe("stat tile", () => {
  it("shows its label and value", () => {
    render(<StatTile label="Net P&L" value="$575.00" />);
    expect(screen.getByText("Net P&L")).toBeInTheDocument();
    expect(screen.getByText("$575.00")).toBeInTheDocument();
  });

  it("carries the sign in the text, not only in colour", () => {
    // Green and red are ΔE 2.3 apart for a deuteranope — colour alone is not a
    // distinction for a large share of readers.
    render(<StatTile label="Net P&L" value="-$220.00" tone="negative" />);
    expect(screen.getByText("-$220.00")).toBeInTheDocument();
  });
});

describe("kpi row", () => {
  it("shows the five headline figures", () => {
    render(<KpiRow kpi={kpi} sample={sample} />);
    for (const label of ["Net P&L", "Win rate", "Expectancy", "Profit factor", "Trades"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("names an undefined profit factor instead of printing a number", () => {
    render(
      <KpiRow
        kpi={{ ...kpi, profit_factor: null, profit_factor_state: "undefined_positive_infinity" }}
        sample={sample}
      />,
    );
    expect(screen.getByText(/no losses yet/i)).toBeInTheDocument();
  });

  it("distinguishes incomplete P&L from a legitimate zero", () => {
    render(
      <KpiRow
        kpi={{ ...kpi, expectancy: null, expectancy_state: "undefined_incomplete_sample" }}
        sample={sample}
      />,
    );
    expect(screen.getByText(/P&L data is incomplete/i)).toBeInTheDocument();
  });

  it("does not present missing net P&L as a flat period", () => {
    render(
      <KpiRow
        kpi={{
          ...kpi,
          net_pnl: { value: null, state: "undefined_incomplete_sample" },
        }}
        sample={{ ...sample, pnl_complete: false, pnl_recorded: 0 }}
      />,
    );
    expect(screen.getByText(/P&L data is incomplete/i)).toBeInTheDocument();
  });

  it("says the sample is too small rather than showing confident figures", () => {
    render(<KpiRow kpi={{ ...kpi, trades: 0 }} sample={{ ...sample, trades: 0, show_summary: false }} />);
    expect(screen.getByText(/no trades in this period/i)).toBeInTheDocument();
  });
});

describe("current standing", () => {
  it("shows today and the running week, spec §8's pair", () => {
    render(<CurrentStanding kpi={{ ...kpi, today_pnl: { value: -120, state: null } }} />);
    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByText("This week")).toBeInTheDocument();
    expect(screen.getByText("-$120.00")).toBeInTheDocument();
    expect(screen.getByText("$575.00")).toBeInTheDocument();
  });

  it("says these two are not scoped to the selected period", () => {
    render(<CurrentStanding kpi={kpi} />);
    expect(screen.getByText(/not the period selected below/i)).toBeInTheDocument();
  });

  it("carries direction in a word, not only in colour", () => {
    render(<CurrentStanding kpi={{ ...kpi, today_pnl: { value: -120, state: null } }} />);
    expect(screen.getByText("down")).toBeInTheDocument();
    expect(screen.getByText("up")).toBeInTheDocument();
  });

  it("does not call an unrecorded current P&L flat", () => {
    render(
      <CurrentStanding
        kpi={{
          ...kpi,
          today_pnl: { value: null, state: "undefined_incomplete_sample" },
        }}
      />,
    );
    expect(screen.getByText(/P&L data is incomplete/i)).toBeInTheDocument();
    expect(screen.queryByText("flat")).not.toBeInTheDocument();
  });
});
