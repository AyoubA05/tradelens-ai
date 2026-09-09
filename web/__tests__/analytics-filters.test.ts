import { describe, expect, it } from "vitest";

import {
  ANALYTICS_FILTER_KEYS,
  ANALYTICS_LENSES,
  DEFAULT_LENS,
  analyticsFiltersToParams,
  lensFromParams,
  parseAnalyticsFilters,
} from "@/lib/app/analytics-filters";

describe("Analytics URL filters", () => {
  it("owns exactly asset, session and strategy", () => {
    expect([...ANALYTICS_FILTER_KEYS]).toEqual(["asset", "session", "strategy"]);
  });

  it("reads the three filters and drops anything else", () => {
    const params = new URLSearchParams({
      asset: "NQ",
      session: "London",
      strategy: "Silver bullet",
      setup: "FVG + OB",
      debug: "1",
    });
    expect(parseAnalyticsFilters(params)).toEqual({
      asset: "NQ",
      session: "London",
      strategy: "Silver bullet",
    });
  });

  it("treats a blank value as absent so a cleared field does not sit in the URL", () => {
    expect(parseAnalyticsFilters(new URLSearchParams({ asset: "   " }))).toEqual({});
  });

  it("round-trips through the URL unchanged", () => {
    const filters = { asset: "NQ", session: "London", strategy: "Silver bullet" };
    const params = analyticsFiltersToParams(filters);
    expect(parseAnalyticsFilters(params)).toEqual(filters);
  });

  it("serialises only the keys it owns", () => {
    const params = analyticsFiltersToParams({ asset: "NQ" } as Record<string, string>);
    expect(params.toString()).toBe("asset=NQ");
  });
});

describe("The active lens", () => {
  it("offers exactly the four lenses", () => {
    expect(ANALYTICS_LENSES.map((lens) => lens.id)).toEqual([
      "performance",
      "risk",
      "timing",
      "setups",
    ]);
  });

  it("reads the active lens from the URL", () => {
    expect(lensFromParams(new URLSearchParams({ lens: "timing" }))).toBe("timing");
  });

  it("falls back to performance when the lens is absent", () => {
    expect(lensFromParams(new URLSearchParams())).toBe(DEFAULT_LENS);
    expect(DEFAULT_LENS).toBe("performance");
  });

  it("falls back to performance rather than rendering nothing for an unknown lens", () => {
    expect(lensFromParams(new URLSearchParams({ lens: "hour-of-day" }))).toBe("performance");
    expect(lensFromParams(new URLSearchParams({ lens: "" }))).toBe("performance");
  });
});
