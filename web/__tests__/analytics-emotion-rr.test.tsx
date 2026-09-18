import "@testing-library/jest-dom/vitest";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SetupsLens } from "@/components/app/analytics/setups-lens";
import { analyticsFixture, undefinedValue, value } from "./fixtures/analytics";

/**
 * Average R by the emotional state recorded before the trade.
 *
 * This panel is the one place the journal puts a trader's own state of mind
 * beside a number, so the assertions are about restraint: it reports what was
 * recorded, it never ranks a state as good or bad, it never suggests what to
 * do next, and when nothing was recorded it says so rather than drawing an
 * empty table that reads as "you feel nothing".
 */

const ADVICE = /\b(should|avoid|stop trading|trade more|don't trade|next trade|recommend)\b/i;

const lens = (rows: AnalyticsSetups["by_emotion_rr"]) => {
  const base = analyticsFixture();
  return render(<SetupsLens setups={{ ...base.setups, by_emotion_rr: rows }} />);
};

type AnalyticsSetups = ReturnType<typeof analyticsFixture>["setups"];

describe("The emotion vs R panel", () => {
  it("lists each recorded emotion with its trade count and average R", () => {
    lens([
      { emotion: "Calm", trades: 12, avg_rr_realized: value(1.437) },
      { emotion: "FOMO", trades: 3, avg_rr_realized: value(-0.82) },
    ]);

    const panel = screen.getByTestId("setups-emotion-rr");
    expect(panel).toHaveAccessibleName("Average R by emotional state going in");

    const calm = within(panel).getByTestId("emotion-rr-row-Calm");
    expect(calm).toHaveTextContent("Calm");
    expect(calm).toHaveTextContent("12");
    expect(calm).toHaveTextContent("1.4R");

    const fomo = within(panel).getByTestId("emotion-rr-row-FOMO");
    expect(fomo).toHaveTextContent("3");
    // A negative average stays visibly negative — never an unsigned 0.8R.
    expect(fomo).toHaveTextContent("-0.8R");
  });

  it("renders the emotions in the order the server sent them", () => {
    lens([
      { emotion: "Calm", trades: 12, avg_rr_realized: value(1.437) },
      { emotion: "FOMO", trades: 3, avg_rr_realized: value(-0.82) },
    ]);

    const rows = within(screen.getByTestId("setups-emotion-rr")).getAllByRole("listitem");
    expect(rows.map((row) => row.getAttribute("data-testid"))).toEqual([
      "emotion-rr-row-Calm",
      "emotion-rr-row-FOMO",
    ]);
  });

  it("says nothing was recorded rather than drawing an empty table", () => {
    lens([]);

    const panel = screen.getByTestId("setups-emotion-rr");
    expect(within(panel).getByTestId("setups-emotion-rr-empty")).toHaveTextContent(
      "No trades in this range record how you felt going in.",
    );
    expect(within(panel).queryByRole("listitem")).toBeNull();
  });

  it("prints an em-dash, not a zero, for an emotion with no measurable average R", () => {
    lens([
      { emotion: "Rushed", trades: 2, avg_rr_realized: undefinedValue("undefined_no_sample") },
    ]);

    const row = screen.getByTestId("emotion-rr-row-Rushed");
    expect(row).toHaveTextContent("—");
    expect(row.textContent ?? "").not.toMatch(/0(\.0)?R/);
  });

  it("carries no ranking or advice about an emotional state", () => {
    const { container } = lens([
      { emotion: "Calm", trades: 12, avg_rr_realized: value(1.437) },
      { emotion: "FOMO", trades: 3, avg_rr_realized: value(-0.82) },
    ]);

    expect(container.textContent ?? "").not.toMatch(ADVICE);
    expect(container.textContent ?? "").not.toMatch(/\b(best|worst|strongest|weakest)\b/i);
  });
});
