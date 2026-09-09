import "@testing-library/jest-dom/vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { buildCurvePath } from "@/components/app/overview/equity-curve";
import { LineChart } from "@/components/app/analytics/line-chart";
import { DistributionChart } from "@/components/app/analytics/distribution-chart";
import { BreakdownTable } from "@/components/app/analytics/breakdown-table";
import { breakdown } from "./fixtures/analytics";

/**
 * The analytics pictures.
 *
 * A chart is a claim about a trader's record, so every assertion here is about
 * a claim: that an absent series is stated in words rather than drawn as an
 * empty frame that reads "zero", that a day with nothing recorded is a break
 * in the line rather than an invented value, that a lone category is not drawn
 * as though it dominated a field of one, and that a losing day sits below zero
 * where a reader will look for it.
 */

/** Pull the "x,y" pairs out of an SVG path, grouped into its subpaths. */
function subpaths(d: string): Array<Array<[number, number]>> {
  return d
    .split("M")
    .filter(Boolean)
    .map((run) =>
      run
        .split("L")
        .filter(Boolean)
        .map((pair) => {
          const [x, y] = pair.split(",").map(Number);
          return [x, y] as [number, number];
        }),
    );
}

function linePath(container: HTMLElement, id = "equity"): string {
  const path = container.querySelector(`[data-testid="chart-${id}-line"]`);
  expect(path).not.toBeNull();
  return path!.getAttribute("d") ?? "";
}

const SERIES = [
  { date: "2026-08-01", value: 100 },
  { date: "2026-08-02", value: 250 },
  { date: "2026-08-03", value: 180 },
];

describe("A line chart never draws a picture the data does not support", () => {
  it("explains an empty series in words instead of rendering an empty axis", () => {
    const { container } = render(
      <LineChart id="equity" title="Equity curve" description="What the account did." points={[]} kind="money" />,
    );
    // Not vacuous: the component rendered, and it said why there is no line.
    expect(screen.getByTestId("chart-equity")).toBeInTheDocument();
    expect(screen.getByTestId("chart-equity-empty")).toHaveTextContent(
      /nothing recorded in this range to draw/i,
    );
    expect(container.querySelector("svg")).toBeNull();
    expect(container.querySelector("path")).toBeNull();
  });

  it("explains a single-point series rather than drawing a line through one value", () => {
    render(
      <LineChart
        id="equity"
        title="Equity curve"
        description="What the account did."
        points={[{ date: "2026-08-01", value: 100 }]}
        kind="money"
      />,
    );
    expect(screen.getByTestId("chart-equity-empty")).toHaveTextContent(/one recorded point/i);
    expect(screen.queryByTestId("chart-equity-line")).toBeNull();
  });

  it("breaks the line at a gap rather than interpolating across it or drawing a zero", () => {
    const withGap = [
      { date: "2026-08-01", value: 100 },
      { date: "2026-08-02", value: 250 },
      { date: "2026-08-03", value: null },
      { date: "2026-08-04", value: 180 },
      { date: "2026-08-05", value: 220 },
    ];
    const { container } = render(
      <LineChart id="equity" title="Equity curve" description="d" points={withGap} kind="money" />,
    );
    const runs = subpaths(linePath(container));
    // Two separate strokes, not one bridged line.
    expect(runs.length).toBe(2);
    expect(runs[0].length).toBe(2);
    expect(runs[1].length).toBe(2);
    // Four plotted coordinates, never five: the gap contributed no point.
    expect(runs.flat().length).toBe(4);
    // The plotted coordinates are exactly the four recorded points, scaled
    // together — no value was invented at zero, and none was interpolated.
    const expected = subpaths(
      buildCurvePath(
        withGap
          .filter((p) => p.value !== null)
          .map((p) => ({ date: p.date, equity: p.value as number })),
        720,
        180,
      ).line,
    )[0];
    expect(runs.flat()).toEqual(expected);
    expect(screen.getByTestId("chart-equity-gaps")).toHaveTextContent(/1 .*not drawn/i);
  });

  it("puts a negative value below zero and keeps zero inside the frame when values straddle it", () => {
    const straddling = [
      { date: "2026-08-01", value: 120 },
      { date: "2026-08-02", value: -80 },
      { date: "2026-08-03", value: 40 },
    ];
    const { container } = render(
      <LineChart id="daily" title="Daily P&L" description="d" points={straddling} kind="money" />,
    );
    const zero = screen.getByTestId("chart-daily-zero-line");
    const zeroY = Number(zero.getAttribute("y1"));
    const coords = subpaths(linePath(container, "daily"))[0];
    const [, yPositive] = coords[0];
    const [, yNegative] = coords[1];
    // SVG y grows downward: the loss must be BELOW the zero rule.
    expect(yNegative).toBeGreaterThan(zeroY);
    expect(yPositive).toBeLessThan(zeroY);
    // And it is at the exact row the shared scale puts 0 on — not the middle
    // of the frame, which would flatter a losing series.
    const expectedZeroY = Number(
      buildCurvePath(
        [-80, 0, 120].map((v) => ({ date: "", equity: v })),
        720,
        180,
      ).line
        .split(/[ML]/)
        .filter(Boolean)[1]
        .split(",")[1],
    );
    expect(zeroY).toBe(expectedZeroY);
    // Zero is inside the drawn frame, not clipped off an axis that starts at the minimum.
    expect(zeroY).toBeGreaterThan(0);
    expect(zeroY).toBeLessThan(180);
    // Meaning is not carried by colour alone.
    expect(zero.getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByTestId("chart-daily")).toHaveTextContent(/zero/i);
  });

  it("omits the zero rule when the series never crosses zero", () => {
    render(<LineChart id="equity" title="Equity" description="d" points={SERIES} kind="money" />);
    expect(screen.queryByTestId("chart-equity-zero-line")).toBeNull();
  });

  it("derives its line geometry from buildCurvePath rather than re-deriving coordinates", () => {
    const { container } = render(
      <LineChart id="equity" title="Equity" description="d" points={SERIES} kind="money" />,
    );
    const expected = buildCurvePath(
      SERIES.map((p) => ({ date: p.date, equity: p.value })),
      720,
      180,
    ).line;
    expect(linePath(container)).toBe(expected);

    const source = readFileSync(
      path.join(process.cwd(), "components/app/analytics/line-chart.tsx"),
      "utf8",
    );
    expect(source).toMatch(/import \{[^}]*buildCurvePath[^}]*\} from "@\/components\/app\/overview\/equity-curve"/);
    // No second implementation: no local pixel arithmetic over the series.
    expect(source).not.toMatch(/height\s*-\s*\(/);
  });

  it("gives the line a text alternative in its own scroll container", () => {
    render(<LineChart id="equity" title="Equity" description="d" points={SERIES} kind="money" />);
    const scroller = screen.getByTestId("chart-equity-scroll");
    expect(scroller.className).toContain("overflow-x-auto");
    const table = within(scroller).getByRole("table");
    expect(scroller.contains(table)).toBe(true);
    expect(within(table).getByText("2026-08-02")).toBeInTheDocument();
    within(table)
      .getAllByRole("cell")
      .forEach((cell) => expect(cell.className).toContain("font-mono"));
  });
});

describe("A distribution never implies a dominance the sample cannot show", () => {
  it("explains an empty distribution instead of drawing an empty axis", () => {
    const { container } = render(
      <DistributionChart id="r-multiples" title="R-multiples" description="d" buckets={[]} />,
    );
    expect(screen.getByTestId("chart-r-multiples-empty")).toHaveTextContent(
      /nothing recorded in this range to draw/i,
    );
    expect(container.querySelector("[data-testid$='-bar']")).toBeNull();
  });

  it("draws no bar for a lone bucket and says there is nothing to compare it against", () => {
    render(
      <DistributionChart
        id="r-multiples"
        title="R-multiples"
        description="d"
        buckets={[{ label: "0.0 to 1.0", count: 3 }]}
      />,
    );
    // The count is still on screen — the bucket is not hidden, only unranked.
    expect(screen.getByTestId("chart-r-multiples")).toHaveTextContent("0.0 to 1.0");
    expect(screen.getByTestId("chart-r-multiples")).toHaveTextContent("3");
    expect(screen.queryByTestId("chart-r-multiples-bar-0")).toBeNull();
    expect(screen.getByTestId("chart-r-multiples-incomparable")).toHaveTextContent(
      /only one .* nothing to compare/i,
    );
  });

  it("scales every bar from the real maximum count", () => {
    render(
      <DistributionChart
        id="r-multiples"
        title="R-multiples"
        description="d"
        buckets={[
          { label: "-1.0 to 0.0", count: 2 },
          { label: "0.0 to 1.0", count: 8 },
          { label: "1.0 to 2.0", count: 0 },
        ]}
      />,
    );
    expect(screen.getByTestId("chart-r-multiples-bar-0").style.width).toBe("25%");
    expect(screen.getByTestId("chart-r-multiples-bar-1").style.width).toBe("100%");
    expect(screen.getByTestId("chart-r-multiples-bar-2").style.width).toBe("0%");
    // Colour is not the message: every bar's count is written out.
    expect(screen.getByTestId("chart-r-multiples")).toHaveTextContent("8");
  });
});

describe("A breakdown table stays inside its own container", () => {
  const rows = [
    { key: "Monday", trades: 4, pnl: 300, win: 0.5 },
    { key: "Tuesday", trades: 8, pnl: 120, win: 0.25 },
  ];

  it("scrolls horizontally inside its own container so the page body never does", () => {
    const { container } = render(
      <BreakdownTable id="by_day_of_week" breakdown={breakdown(rows, true)} />,
    );
    const scroller = screen.getByTestId("breakdown-by_day_of_week-scroll");
    expect(scroller.className).toContain("overflow-x-auto");
    expect(scroller.contains(within(scroller).getByRole("table"))).toBe(true);
    // Nothing wider than the viewport escapes the scroller.
    container.querySelectorAll("[class*='min-w-']").forEach((wide) => {
      expect(scroller.contains(wide)).toBe(true);
    });
  });

  it("renders every numeric cell with the app's tabular mono treatment", () => {
    render(<BreakdownTable id="by_day_of_week" breakdown={breakdown(rows, true)} />);
    const table = screen.getByRole("table");
    within(table)
      .getAllByRole("cell")
      .forEach((cell) => expect(cell.className).toContain("font-mono"));
  });

  it("scales the share bar from the largest row, and draws none for a lone row", () => {
    const { rerender } = render(
      <BreakdownTable id="by_day_of_week" breakdown={breakdown(rows, true)} />,
    );
    expect(screen.getByTestId("breakdown-by_day_of_week-bar-Monday").style.width).toBe("50%");
    expect(screen.getByTestId("breakdown-by_day_of_week-bar-Tuesday").style.width).toBe("100%");

    rerender(
      <BreakdownTable id="by_day_of_week" breakdown={breakdown([rows[0]], false)} />,
    );
    expect(screen.getByText("Monday")).toBeInTheDocument();
    expect(screen.queryByTestId("breakdown-by_day_of_week-bar-Monday")).toBeNull();
  });
});

describe("LineChart — isolated recorded points", () => {
  it("draws a mark for a lone recorded point instead of an empty frame", () => {
    // A run of one produces a bare `M` with no `L`, so nothing renders: a
    // chart captioned "3 recorded points" showing an empty frame. Real
    // journals are sparse, so alternating gaps are not exotic, and an empty
    // axis reads as a flat zero — a claim about the trader's record.
    render(
      <LineChart
        id="equity"
        title="Account equity"
        description="The account's running total through this period, as recorded."
        kind="money"
        points={[
          { date: "2026-09-01", value: 100 },
          { date: "2026-09-02", value: null as unknown as number },
          { date: "2026-09-03", value: -50 },
          { date: "2026-09-04", value: null as unknown as number },
          { date: "2026-09-05", value: 200 },
        ]}
      />,
    );

    const region = screen.getByTestId("chart-equity");
    // Not vacuous: the recorded values are on screen in the text equivalent.
    expect(within(region).getByText("$100.00")).toBeInTheDocument();
    expect(within(region).getByText("-$50.00")).toBeInTheDocument();

    // Every recorded point is marked, so none of them is invisible.
    const marks = region.querySelectorAll("[data-testid='chart-equity-point']");
    expect(marks.length).toBe(3);
  });
});
