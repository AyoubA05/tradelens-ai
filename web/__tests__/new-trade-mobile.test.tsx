import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { NewTradeForm } from "@/components/app/new-trade/new-trade-form";

/**
 * Task D3 — the form at ~375px.
 *
 * jsdom computes no layout, so these assert the structural facts that
 * decide it: every multi-column grid has a single-column base, every
 * horizontal button row has a stacking base, no element opts out of
 * wrapping, and the controls a trader reaches one-handed are full-size tap
 * targets. A visual check cannot be automated here; these keep the classes
 * that make the visual result possible from being removed silently.
 */

beforeEach(() => {
  push.mockReset();
});

describe("NewTradeForm at ~375px", () => {
  it("gives every multi-column grid a single-column base so the groups stack", () => {
    const { container } = render(<NewTradeForm />);
    const grids = container.querySelectorAll('[class*="grid-cols"]');
    expect(grids.length).toBeGreaterThan(0);
    for (const grid of grids) {
      // A `sm:`-prefixed column count only applies above 640px; the base
      // must be one column or the groups sit side by side on a phone.
      expect(grid.className).toContain("grid-cols-1");
    }
  });

  it("never lets content opt out of wrapping", () => {
    const { container } = render(<NewTradeForm />);
    expect(container.querySelectorAll('[class*="whitespace-nowrap"]')).toHaveLength(0);
    expect(container.querySelectorAll('[class*="overflow-x"]')).toHaveLength(0);
    // A fixed pixel width would be the other way to force a sideways scroll.
    expect(container.querySelectorAll('[class*="w-["]')).toHaveLength(0);
  });

  it("keeps the primary action a full-width, full-height tap target on a phone", () => {
    render(<NewTradeForm />);
    const submit = screen.getByRole("button", { name: /save trade/i });
    expect(submit.className).toContain("min-h-[44px]");
    expect(submit.className).toContain("w-full");
    expect(submit.className).toContain("sm:w-auto");
  });

  it("keeps the upload control reachable one-handed and full-width", () => {
    render(<NewTradeForm />);
    const label = screen.getByText(/choose a screenshot/i);
    expect(label.className).toContain("min-h-[44px]");
    expect(label.className).toContain("w-full");
  });

  it("stacks the duplicate panel's buttons rather than crowding them", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ id: 9, duplicate_of: 9 }) })),
    );
    render(<NewTradeForm />);
    fireEvent.click(screen.getByRole("button", { name: /save trade/i }));
    const view = await screen.findByRole("button", { name: /view existing trade/i });
    expect(view.className).toContain("min-h-[44px]");
    expect(view.parentElement?.className).toContain("flex-col");
    expect(view.parentElement?.className).toContain("sm:flex-row");
    vi.unstubAllGlobals();
  });

  it("wraps long unbroken text a trader typed instead of pushing the page sideways", () => {
    render(<NewTradeForm />);
    // The completeness warnings render on an empty form (global rule 5).
    const warnings = screen.getByText(/thin record is allowed/i).closest("div");
    expect(warnings?.className).toContain("break-words");
  });
});
