import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetricValueText } from "@/components/app/analytics/metric-value";

/**
 * The single place an undefined figure becomes text. Every rule about
 * never showing a fabricated zero ends here, so this is where it is pinned.
 */
describe("MetricValueText", () => {
  it("renders a measured zero as zero, because that is a real result", () => {
    render(<MetricValueText value={{ value: 0, state: null }} kind="money" />);
    expect(screen.getByText("$0.00")).toBeInTheDocument();
  });

  it("renders a measured zero for every kind, never as a missing figure", () => {
    const { rerender } = render(
      <MetricValueText value={{ value: 0, state: null }} kind="percent" />,
    );
    expect(screen.getByText("0.0%")).toBeInTheDocument();
    expect(screen.queryByText("—")).not.toBeInTheDocument();

    rerender(<MetricValueText value={{ value: 0, state: null }} kind="ratio" />);
    expect(screen.getByText("0.00x")).toBeInTheDocument();
    expect(screen.queryByText("—")).not.toBeInTheDocument();

    rerender(<MetricValueText value={{ value: 0, state: null }} kind="number" />);
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });

  it("never renders an undefined figure as a number", () => {
    render(
      <MetricValueText
        value={{ value: null, state: "undefined_no_sample" }}
        kind="money"
      />,
    );
    // The em-dash assertion is not decoration: without it, "no $0 on screen"
    // would also pass against a component that rendered nothing at all.
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText(/\$0/)).not.toBeInTheDocument();
  });

  /**
   * Every zero shape this product could plausibly emit, against every kind
   * and every state. A fabricated zero is the one failure mode that reads as
   * a real measurement, so the sweep is exhaustive rather than illustrative.
   */
  it("renders no zero form and no N/A for any undefined state, in any kind", () => {
    const states = [
      "undefined_nan",
      "undefined_positive_infinity",
      "undefined_negative_infinity",
      "undefined_no_sample",
      "undefined_incomplete_sample",
    ] as const;
    const kinds = ["money", "percent", "ratio", "number"] as const;

    for (const state of states) {
      for (const kind of kinds) {
        const { container, unmount } = render(
          <MetricValueText value={{ value: null, state }} kind={kind} />,
        );
        const text = container.textContent ?? "";
        expect(text).toContain("—");
        // No digits at all: `0`, `0.00`, `$0.00`, `0%` and `0.0%` are all
        // caught by this, as is any other number a future branch invents.
        expect(text).not.toMatch(/\d/);
        expect(text).not.toMatch(/N\/A/i);
        expect(text.trim()).not.toBe("");
        unmount();
      }
    }
  });

  it("says WHY a figure is missing, not just that it is", () => {
    render(
      <MetricValueText
        value={{ value: null, state: "undefined_incomplete_sample" }}
        kind="money"
      />,
    );
    // The distinction a trader needs: nothing to measure vs. rows that did
    // not record it. "—" alone leaves them unable to act.
    expect(
      screen.getByTitle(/not every trade in this range records/i),
    ).toBeInTheDocument();
  });

  it("gives each of the five undefined states its own distinct explanation", () => {
    const expected: Record<string, RegExp> = {
      undefined_no_sample: /no trades in this range to measure this/i,
      undefined_incomplete_sample: /not every trade in this range records this/i,
      undefined_positive_infinity: /no losing trades in this range/i,
      undefined_negative_infinity: /no winning trades in this range/i,
      undefined_nan: /could not be computed from the trades in this range/i,
    };

    const seen = new Set<string>();
    for (const [state, pattern] of Object.entries(expected)) {
      const { container, unmount } = render(
        <MetricValueText
          value={{ value: null, state: state as never }}
          kind="money"
        />,
      );
      const title = container.querySelector("[title]")?.getAttribute("title") ?? "";
      expect(title).toMatch(pattern);
      // Distinct, not merely present: five states sharing one sentence would
      // satisfy every individual match above.
      expect(seen.has(title)).toBe(false);
      seen.add(title);
      unmount();
    }
    expect(seen.size).toBe(5);
  });

  it("names an infinite profit factor rather than printing a symbol", () => {
    const { container } = render(
      <MetricValueText
        value={{ value: null, state: "undefined_positive_infinity" }}
        kind="ratio"
      />,
    );
    expect(container.textContent).not.toContain("∞");
    expect(
      screen.getByTitle(/no losing trades in this range, so there is no ratio/i),
    ).toBeInTheDocument();
  });

  it("formats a real figure by kind", () => {
    const { rerender } = render(
      <MetricValueText value={{ value: -1234.5, state: null }} kind="money" />,
    );
    expect(screen.getByText("-$1,234.50")).toBeInTheDocument();

    rerender(<MetricValueText value={{ value: 0.625, state: null }} kind="percent" />);
    expect(screen.getByText("62.5%")).toBeInTheDocument();

    rerender(<MetricValueText value={{ value: 1.8, state: null }} kind="ratio" />);
    expect(screen.getByText("1.80x")).toBeInTheDocument();

    rerender(<MetricValueText value={{ value: 42, state: null }} kind="number" />);
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("carries no title on a figure that is present", () => {
    const { container } = render(
      <MetricValueText value={{ value: 12, state: null }} kind="number" />,
    );
    expect(container.querySelector("[title]")).toBeNull();
  });
});
