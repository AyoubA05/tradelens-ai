import "@testing-library/jest-dom/vitest";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PerformanceLens } from "@/components/app/analytics/performance-lens";
import { RiskLens } from "@/components/app/analytics/risk-lens";
import { TimingLens } from "@/components/app/analytics/timing-lens";
import { SetupsLens } from "@/components/app/analytics/setups-lens";
import { analyticsFixture, breakdown, undefinedValue, value } from "./fixtures/analytics";

/**
 * The four lens panels.
 *
 * Every assertion here is about a claim the page makes to a trader: that a
 * missing figure is missing rather than zero, that a measured zero is a
 * measurement, that a win rate is not quietly discredited by an unrelated
 * absent total, and that a category is only ranked when the sample earned it.
 */

const RANKING_WORDS = /\b(best|worst|strongest|weakest|top|leading|winner|winning category)\b/i;
const FABRICATED_ZERO = /(^|\s)(\$0\.00|0\.0%|0%|0\.00x|N\/A)(\s|$)/;

describe("Undefined figures never become zero", () => {
  it("renders an em-dash, not a zero, for every undefined performance figure", () => {
    const base = analyticsFixture();
    const { container } = render(
      <PerformanceLens
        performance={{
          ...base.performance,
          total_pnl: undefinedValue("undefined_no_sample"),
          expectancy: undefinedValue("undefined_nan"),
          profit_factor: undefinedValue("undefined_positive_infinity"),
        }}
        discipline={base.discipline}
      />,
    );
    const pnl = screen.getByTestId("figure-total-pnl");
    expect(pnl).toHaveTextContent("—");
    expect(pnl.textContent ?? "").not.toMatch(/0/);
    expect(screen.getByTestId("figure-expectancy")).toHaveTextContent("—");
    expect(screen.getByTestId("figure-profit-factor")).toHaveTextContent("—");
    // The whole panel: nothing anywhere may print a plausible zero for these.
    expect(container.textContent ?? "").not.toMatch(FABRICATED_ZERO);
  });

  it("renders a measured zero as a zero", () => {
    const base = analyticsFixture();
    render(
      <PerformanceLens
        performance={{ ...base.performance, total_pnl: value(0), win_rate: value(0) }}
        discipline={base.discipline}
      />,
    );
    expect(screen.getByTestId("figure-total-pnl")).toHaveTextContent("$0.00");
    expect(screen.getByTestId("figure-win-rate")).toHaveTextContent("0.0%");
  });

  it("renders an em-dash for an undefined risk figure and a zero for a measured one", () => {
    const base = analyticsFixture();
    render(
      <RiskLens
        risk={{
          ...base.risk,
          max_drawdown: undefinedValue("undefined_no_sample"),
          avg_loss: value(0),
        }}
      />,
    );
    expect(screen.getByTestId("figure-max-drawdown")).toHaveTextContent("—");
    expect(screen.getByTestId("figure-max-drawdown").textContent ?? "").not.toMatch(/0/);
    expect(screen.getByTestId("figure-avg-loss")).toHaveTextContent("$0.00");
    expect(screen.getByTestId("figure-avg-win")).toHaveTextContent("$140.00");
  });
});

describe("Win rate and P&L are separately sourced (design decision 6b)", () => {
  it("does not degrade, caveat or dim the win rate when the P&L beside it is undefined", () => {
    const base = analyticsFixture();
    const { container } = render(
      <PerformanceLens
        performance={{
          ...base.performance,
          total_pnl: undefinedValue("undefined_incomplete_sample"),
          win_rate: value(0.5),
        }}
        discipline={base.discipline}
      />,
    );

    const winRate = screen.getByTestId("figure-win-rate");
    // The real figure is on screen — this test must not pass by rendering nothing.
    expect(winRate).toHaveTextContent("50.0%");
    expect(screen.getByTestId("figure-total-pnl")).toHaveTextContent("—");

    // Not greyed, not disabled, not dimmed.
    const html = winRate.outerHTML;
    expect(html).not.toMatch(/opacity-|line-through|grayscale|aria-disabled|disabled|italic/);
    expect(winRate.querySelector('[class*="text-muted"]:not([class*="uppercase"])')).toBeNull();

    // No caveat of its own.
    expect(winRate.textContent ?? "").not.toMatch(/not|incomplete|unreliable|misleading/i);
    expect(winRate.querySelector("[title]")).toBeNull();

    // No shared banner covering both figures.
    expect(screen.queryByTestId("performance-incomplete-banner")).toBeNull();
    const banner = Array.from(container.querySelectorAll("*")).find(
      (el) =>
        /incomplete|not enough data/i.test(el.textContent ?? "") &&
        el.contains(winRate) &&
        el.contains(screen.getByTestId("figure-total-pnl")),
    );
    expect(banner).toBeUndefined();
  });
});

describe("Breakdowns only rank when the sample can be compared", () => {
  const rows = [
    { key: "Monday", trades: 4, pnl: 300, win: 0.5 },
    { key: "Tuesday", trades: 6, pnl: 120, win: 0.25 },
  ];

  it("ranks a comparable breakdown and names the largest recorded category", () => {
    const base = analyticsFixture();
    render(
      <TimingLens
        timing={{
          ...base.timing,
          by_day_of_week: {
            ...breakdown(rows, true),
            // Deliberately disagrees with the row values. The browser must
            // display the backend's policy result, not recalculate money.
            leader: { key: "Tuesday", trades: 6 },
          },
        }}
      />,
    );
    const panel = screen.getByTestId("breakdown-by_day_of_week");
    expect(within(panel).getByText("Monday")).toBeInTheDocument();
    expect(within(panel).getByText("Tuesday")).toBeInTheDocument();
    const ranking = within(panel).getByTestId("breakdown-by_day_of_week-ranking");
    expect(ranking).toHaveTextContent(/Tuesday/);
    expect(ranking).toHaveTextContent(/largest recorded/i);
    expect(within(panel).queryByTestId("breakdown-by_day_of_week-not-comparable")).toBeNull();
  });

  it("does not name a leader when comparable rows are below the pattern threshold", () => {
    const base = analyticsFixture();
    render(
      <TimingLens
        timing={{
          ...base.timing,
          by_day_of_week: { ...breakdown(rows, true), leader: null },
        }}
      />,
    );

    const panel = screen.getByTestId("breakdown-by_day_of_week");
    expect(within(panel).queryByTestId("breakdown-by_day_of_week-ranking")).toBeNull();
    expect(within(panel).getByTestId("breakdown-by_day_of_week-low-sample")).toHaveTextContent(
      /too few trades/i,
    );
  });

  it("blames the missing P&L, not the categories, and leaves the win rates alone", () => {
    // The server said these categories ARE comparable; only the P&L is
    // incomplete. Printing "this range does not hold enough of them" states
    // a cause that is untrue, and a bare "cannot be compared" sitting under
    // a complete Win rate column is a shared caveat implying an undefined
    // P&L discredits a valid win rate — the thing decision 6b forbids.
    const base = analyticsFixture();
    const mixed = [
      { key: "Monday", trades: 4, pnl: 300, win: 0.5 },
      { key: "Tuesday", trades: 6, pnl: null, win: 0.25 },
    ];
    render(
      <TimingLens
        timing={{ ...base.timing, by_day_of_week: breakdown(mixed, true) }}
      />,
    );
    const panel = screen.getByTestId("breakdown-by_day_of_week");

    // Not vacuous: both rows and both win rates are on screen.
    expect(within(panel).getByText("Monday")).toBeInTheDocument();
    expect(within(panel).getByText("50.0%")).toBeInTheDocument();
    expect(within(panel).getByText("25.0%")).toBeInTheDocument();

    // No ranking, because there is not enough money data to order by.
    expect(within(panel).queryByTestId("breakdown-by_day_of_week-ranking")).toBeNull();
    expect(panel.textContent ?? "").not.toMatch(RANKING_WORDS);

    // ...but the reason names the P&L, never the category count.
    const note = within(panel).getByTestId("breakdown-by_day_of_week-pnl-incomplete");
    expect(note).toHaveTextContent(/P&L/i);
    expect(note.textContent ?? "").not.toMatch(/enough of them|enough categories/i);
    // ...and it explicitly does not implicate the win rates.
    expect(note).toHaveTextContent(/win rate/i);
    // The not-comparable caption, which blames the categories, must be absent.
    expect(
      within(panel).queryByTestId("breakdown-by_day_of_week-not-comparable"),
    ).toBeNull();
  });

  it("uses no ranking language when the breakdown is not comparable, and says why", () => {
    const base = analyticsFixture();
    render(
      <TimingLens
        timing={{ ...base.timing, by_day_of_week: breakdown(rows, false) }}
      />,
    );
    const panel = screen.getByTestId("breakdown-by_day_of_week");
    // Not vacuous: the rows themselves are still on screen.
    expect(within(panel).getByText("Monday")).toBeInTheDocument();
    expect(within(panel).getByText("$300.00")).toBeInTheDocument();
    expect(within(panel).queryByTestId("breakdown-by_day_of_week-ranking")).toBeNull();
    expect(panel.textContent ?? "").not.toMatch(RANKING_WORDS);
    expect(within(panel).getByTestId("breakdown-by_day_of_week-not-comparable")).toHaveTextContent(
      /cannot be compared/i,
    );
  });

  it("says in words that a breakdown has no rows rather than rendering an empty table", () => {
    const base = analyticsFixture();
    render(<TimingLens timing={{ ...base.timing, by_session: breakdown([], false) }} />);
    const panel = screen.getByTestId("breakdown-by_session");
    expect(within(panel).queryByRole("table")).toBeNull();
    expect(within(panel).getByTestId("breakdown-by_session-empty")).toHaveTextContent(
      /no trades in this range/i,
    );
  });

  it("gives every breakdown table real column headers and its own horizontal scroll", () => {
    const base = analyticsFixture();
    render(<TimingLens timing={{ ...base.timing, by_day_of_week: breakdown(rows, true) }} />);
    const panel = screen.getByTestId("breakdown-by_day_of_week");
    const table = within(panel).getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Category",
      "Trades",
      "Net P&L",
      "Win rate",
    ]);
    within(table)
      .getAllByRole("rowheader")
      .forEach((cell) => expect(cell.tagName).toBe("TH"));
    const scroller = within(panel).getByTestId("breakdown-by_day_of_week-scroll");
    expect(scroller.className).toContain("overflow-x-auto");
    expect(scroller.contains(table)).toBe(true);
  });
});

describe("The setups lens", () => {
  it("renders each setups breakdown and the recorded mistakes", () => {
    const base = analyticsFixture();
    render(
      <SetupsLens
        setups={{
          ...base.setups,
          by_setup: breakdown([{ key: "FVG", trades: 3, pnl: 90, win: 0.66 }], false),
        }}
      />,
    );
    for (const id of ["by_setup", "by_asset", "by_strategy", "by_timeframe", "by_confirmation"]) {
      expect(screen.getByTestId(`breakdown-${id}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("setups-mistakes")).toHaveTextContent("Moved stop");
    expect(screen.getByTestId("setups-mistakes")).toHaveTextContent("2");
  });
});

describe("Series panels draw the recorded series", () => {
  it("gives the performance and risk lenses their real chart regions", () => {
    const base = analyticsFixture();
    render(<PerformanceLens performance={base.performance} discipline={base.discipline} />);
    expect(screen.getByTestId("chart-equity-curve")).toBeInTheDocument();
    expect(screen.getByTestId("chart-daily-pnl")).toBeInTheDocument();
    render(<RiskLens risk={base.risk} />);
    expect(screen.getByTestId("chart-drawdown")).toBeInTheDocument();
    expect(screen.getByTestId("chart-r-multiples")).toBeInTheDocument();
    // No placeholder survives anywhere on either lens.
    expect(screen.queryByTestId("performance-series-pending")).toBeNull();
    expect(screen.queryByTestId("risk-series-pending")).toBeNull();
  });

  it("shows the discipline figures on the performance lens", () => {
    const base = analyticsFixture();
    render(<PerformanceLens performance={base.performance} discipline={base.discipline} />);
    expect(screen.getByTestId("figure-rule-adherence")).toHaveTextContent("80.0%");
    expect(screen.getByTestId("figure-consistency")).toHaveTextContent("70");
    expect(screen.getByTestId("figure-edge-leak")).toHaveTextContent("-$120.00");
  });

  it("explains that incomplete P&L suppresses money charts instead of claiming no trades exist", () => {
    const base = analyticsFixture();
    render(
      <PerformanceLens
        performance={{
          ...base.performance,
          total_pnl: undefinedValue("undefined_incomplete_sample"),
          equity_curve: [],
          daily_pnl: [],
        }}
        discipline={base.discipline}
      />,
    );

    for (const id of ["equity-curve", "daily-pnl"]) {
      const empty = screen.getByTestId(`chart-${id}-empty`);
      expect(empty).toHaveTextContent(/not every trade.*P&L/i);
      expect(empty).not.toHaveTextContent(/nothing recorded/i);
    }
  });

  it("labels profitable rule-breaking as historical and not repeatable edge", () => {
    const base = analyticsFixture();
    render(
      <PerformanceLens
        performance={base.performance}
        discipline={{ ...base.discipline, edge_leak: value(95) }}
      />,
    );

    expect(screen.getByTestId("performance-discipline")).toHaveTextContent(
      /profitable.*not repeatable edge/i,
    );
  });
});
