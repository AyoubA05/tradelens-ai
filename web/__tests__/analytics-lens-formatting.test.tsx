import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MetricValue } from "@/lib/app/analytics";

/**
 * No lens formats a number itself.
 *
 * `MetricValueText` is the single place a `{value, state}` pair becomes text,
 * because a lens that reaches for `toFixed` or `money` directly is one branch
 * away from printing `$0.00` for a figure nobody measured. Stubbing the
 * component makes that structural: if a figure still shows its real formatted
 * value with the renderer replaced, the lens formatted it locally.
 */
vi.mock("@/components/app/analytics/metric-value", () => ({
  MetricValueText: ({ value, kind }: { value: MetricValue; kind: string }) => (
    <span>{`[${kind}:${value.value === null ? `undefined/${value.state}` : value.value}]`}</span>
  ),
}));

import { PerformanceLens } from "@/components/app/analytics/performance-lens";
import { RiskLens } from "@/components/app/analytics/risk-lens";
import { TimingLens } from "@/components/app/analytics/timing-lens";
import { SetupsLens } from "@/components/app/analytics/setups-lens";
import { analyticsFixture, breakdown } from "./fixtures/analytics";

const NUMBER_FORMATTING = /\$[\d,]+\.\d\d|\d+\.\d%|\d+\.\d\dx/;

describe("Every figure goes through MetricValueText", () => {
  it("leaves the performance lens with no locally formatted number", () => {
    const base = analyticsFixture();
    const { container } = render(
      <PerformanceLens performance={base.performance} discipline={base.discipline} />,
    );
    expect(container.textContent ?? "").not.toMatch(NUMBER_FORMATTING);
    expect(container.textContent).toContain("[money:500]");
    expect(container.textContent).toContain("[percent:0.5]");
    expect(container.textContent).toContain("[ratio:1.8]");
  });

  it("leaves the risk lens with no locally formatted number", () => {
    const { container } = render(<RiskLens risk={analyticsFixture().risk} />);
    expect(container.textContent ?? "").not.toMatch(NUMBER_FORMATTING);
    expect(container.textContent).toContain("[money:-80]");
  });

  it("leaves breakdown rows with no locally formatted number", () => {
    const base = analyticsFixture();
    render(
      <TimingLens
        timing={{
          ...base.timing,
          by_day_of_week: breakdown([{ key: "Monday", trades: 4, pnl: 300, win: 0.5 }], false),
        }}
      />,
    );
    const panel = screen.getByTestId("breakdown-by_day_of_week");
    expect(panel.textContent ?? "").not.toMatch(NUMBER_FORMATTING);
    expect(panel.textContent).toContain("[money:300]");
    expect(panel.textContent).toContain("[percent:0.5]");
  });

  it("leaves the setups lens with no locally formatted number", () => {
    const { container } = render(<SetupsLens setups={analyticsFixture().setups} />);
    expect(container.textContent ?? "").not.toMatch(NUMBER_FORMATTING);
  });
});
