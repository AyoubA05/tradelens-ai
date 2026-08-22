import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EquityCurve, buildCurvePath } from "@/components/app/overview/equity-curve";

const points = [
  { date: "2026-08-10", equity: 480 },
  { date: "2026-08-11", equity: 260 },
  { date: "2026-08-12", equity: 670 },
  { date: "2026-08-14", equity: 575 },
];
const earned = {
  show_series: true,
  show_dominant_series: true,
  dated_points: 4,
  pnl_complete: true,
};

describe("curve geometry", () => {
  it("maps the first point to the left edge and the last to the right", () => {
    const { line } = buildCurvePath(points, 100, 40);
    expect(line.startsWith("M0")).toBe(true);
    expect(line).toContain("L100");
  });

  it("puts the highest equity above the lowest on screen", () => {
    // SVG y grows downward, so the maximum must have the SMALLER y.
    const { line } = buildCurvePath(points, 100, 40);
    const ys = [...line.matchAll(/[ML]([\d.]+),([\d.]+)/g)].map((m) => Number(m[2]));
    expect(ys[2]).toBeLessThan(ys[1]); // 670 is above 260
  });

  it("closes the area path back to the baseline", () => {
    const { area } = buildCurvePath(points, 100, 40);
    expect(area.endsWith("Z")).toBe(true);
  });

  it("centres a flat curve instead of pinning it to an extreme", () => {
    const flat = [
      { date: "2026-08-10", equity: 100 },
      { date: "2026-08-11", equity: 100 },
    ];
    const { line } = buildCurvePath(flat, 100, 40);
    expect(line).not.toContain("NaN");
    expect(line).toBe("M0,20L100,20");
  });

  it("survives a single point", () => {
    const { line } = buildCurvePath([{ date: "2026-08-10", equity: 5 }], 100, 40);
    expect(line).not.toContain("NaN");
  });
});

describe("equity curve", () => {
  it("draws the curve when the sample has earned it", () => {
    const { container } = render(<EquityCurve points={points} sample={earned} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("explains itself instead of drawing a line from two points", () => {
    render(
      <EquityCurve points={points.slice(0, 2)} sample={{ ...earned, show_dominant_series: false, dated_points: 2 }} />,
    );
    expect(screen.getByText(/not enough dated trades/i)).toBeInTheDocument();
    expect(screen.getByText(/2 more trading days/i)).toBeInTheDocument();
  });

  it("does not draw an equity curve through missing P&L", () => {
    render(<EquityCurve points={points} sample={{ ...earned, pnl_complete: false }} />);
    expect(screen.queryByRole("img", { name: /equity/i })).not.toBeInTheDocument();
    expect(screen.getByText(/P&L data is incomplete/i)).toBeInTheDocument();
  });

  it("labels the curve so identity is never colour alone", () => {
    render(<EquityCurve points={points} sample={earned} />);
    expect(screen.getByText(/\$575/)).toBeInTheDocument();
  });

  it("gives the chart an accessible description", () => {
    render(<EquityCurve points={points} sample={earned} />);
    expect(screen.getByRole("img", { name: /equity/i })).toBeInTheDocument();
  });
});
