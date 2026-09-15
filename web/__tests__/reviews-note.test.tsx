import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReviewNote, SMALL_SAMPLE_LIMITATION, sampleConfidence, sampleLimitation } from "@/components/app/reviews/review-note";
import { PeriodStrip } from "@/components/app/reviews/period-strip";

/**
 * Generated review notes are model output. They render as React text — bold
 * and `- ` lists only — and never through any HTML path.
 */

const MD =
  "### What Worked\nKept **rules**.\n\n### What Didn't\n- late entries\n\n### Observed Patterns\n<img src=x onerror=alert(1)>";

describe("ReviewNote", () => {
  it("renders model markdown as text, never as HTML", () => {
    const { container } = render(
      <ReviewNote title="Week in review" sample="2026-09-07" content={MD} confidence="low" />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  });

  it("renders bold and list items as elements, nothing else", () => {
    const { container } = render(
      <ReviewNote title="Week in review" sample="2026-09-07" content={MD} confidence="low" />,
    );
    expect(screen.getByText("rules", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { hidden: true })).toHaveTextContent("late entries");
    expect(container.innerHTML).not.toContain("<img");
  });

  it("shows the first section and discloses the rest", () => {
    const { container } = render(
      <ReviewNote title="Week in review" sample="2026-09-07" content={MD} confidence="low" />,
    );
    expect(screen.getByRole("heading", { name: "What Worked", level: 3 })).toBeVisible();
    expect(screen.getByText("Read full note")).toBeInTheDocument();
    const details = container.querySelector("details");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
    expect(details!.textContent).toContain("What Didn't");
    expect(details!.textContent).toContain("Observed Patterns");
    expect(details!.textContent).not.toContain("What Worked");
  });

  it("has no disclosure for a single-section note", () => {
    const { container } = render(
      <ReviewNote title="Day in review" sample="2026-09-08" content={"### Session Summary\nQuiet."} confidence="low" />,
    );
    expect(container.querySelector("details")).toBeNull();
    expect(screen.queryByText("Read full note")).toBeNull();
  });

  it("states the sample and confidence", () => {
    render(
      <ReviewNote
        title="Day in review"
        sample="2026-09-08"
        content={MD}
        confidence="medium"
        limitation="Small sample — read this as a description, not a rule."
      />,
    );
    expect(screen.getByRole("heading", { name: "Day in review" })).toBeInTheDocument();
    expect(screen.getByText(/2026-09-08/)).toBeInTheDocument();
    expect(screen.getByText(/confidence: medium/i)).toBeInTheDocument();
    expect(screen.getByText(/Small sample/)).toBeInTheDocument();
  });
});

describe("PeriodStrip", () => {
  it("shows the five figures", () => {
    render(
      <PeriodStrip
        stats={{ trades: 12, win_rate: 0.5, total_pnl: -120.5, profit_factor: 1.43, total_edge_leak: 20 }}
      />,
    );
    expect(screen.getByText("Trades").nextSibling).toHaveTextContent("12");
    expect(screen.getByText("Win rate").nextSibling).toHaveTextContent("50%");
    expect(screen.getByText("Net P&L").nextSibling).toHaveTextContent("-$120.50");
    expect(screen.getByText("Profit factor").nextSibling).toHaveTextContent("1.4x");
    expect(screen.getByText("Edge leak").nextSibling).toHaveTextContent("$20.00");
  });

  it("writes ∞ for a lossless period with trades", () => {
    render(
      <PeriodStrip stats={{ trades: 3, win_rate: 1, total_pnl: 90, profit_factor: null, total_edge_leak: 0 }} />,
    );
    expect(screen.getByText("Profit factor").nextSibling).toHaveTextContent("∞");
  });

  it("writes N/A for an empty period", () => {
    render(
      <PeriodStrip stats={{ trades: 0, win_rate: 0, total_pnl: 0, profit_factor: null, total_edge_leak: 0 }} />,
    );
    expect(screen.getByText("Profit factor").nextSibling).toHaveTextContent("N/A");
  });
});

describe("sampleConfidence and sampleLimitation (Streamlit parity)", () => {
  it.each([
    [0, "low"],
    [4, "low"],
    [5, "low"],
    [9, "low"],
    [10, "medium"],
    [19, "medium"],
    [20, "high"],
    [40, "high"],
  ] as const)("%i trades read as %s confidence", (trades, level) => {
    expect(sampleConfidence(trades)).toBe(level);
  });

  it.each([
    [4, SMALL_SAMPLE_LIMITATION],
    [5, undefined],
    [0, SMALL_SAMPLE_LIMITATION],
    [20, undefined],
  ] as const)("%i trades carry the small-sample line only under five", (trades, line) => {
    expect(sampleLimitation(trades)).toBe(line);
  });
});
