import { describe, expect, it } from "vitest";

import { filtersToParams, parseFilters, TRADE_FILTER_KEYS } from "@/lib/app/trade-filters";

describe("reading filters from the URL", () => {
  it("returns nothing when no filter params are present", () => {
    expect(parseFilters(new URLSearchParams())).toEqual({});
  });

  it("reads each known filter", () => {
    const params = new URLSearchParams("asset=NQ&session=London&setup=FVG&result=Win");
    expect(parseFilters(params)).toEqual({
      asset: "NQ",
      session: "London",
      setup: "FVG",
      result: "Win",
    });
  });

  it("drops an unknown parameter rather than forwarding it", () => {
    const params = new URLSearchParams("asset=NQ&debug=1&from=2026-08-01");
    const filters = parseFilters(params);
    expect(filters).toEqual({ asset: "NQ" });
    expect(Object.keys(filters)).not.toContain("debug");
    expect(Object.keys(filters)).not.toContain("from");
  });

  it("treats an empty or whitespace value as absent", () => {
    const params = new URLSearchParams("asset=&session=%20%20");
    expect(parseFilters(params)).toEqual({});
  });

  it("trims surrounding whitespace on a real value", () => {
    const params = new URLSearchParams("asset=%20NQ%20");
    expect(parseFilters(params).asset).toBe("NQ");
  });
});

describe("writing filters back to the URL", () => {
  it("serialises only the set filters", () => {
    const params = filtersToParams({ asset: "NQ", result: "Loss" });
    expect([...params.entries()].sort()).toEqual([
      ["asset", "NQ"],
      ["result", "Loss"],
    ]);
  });

  it("omits an unset filter entirely, not as an empty param", () => {
    const params = filtersToParams({ asset: "NQ" });
    expect(params.has("session")).toBe(false);
    expect(params.toString()).toBe("asset=NQ");
  });

  it("round-trips through parseFilters unchanged", () => {
    const original = { asset: "NQ", session: "London", setup: "FVG", result: "Win" };
    const roundTripped = parseFilters(filtersToParams(original));
    expect(roundTripped).toEqual(original);
  });

  it("produces nothing for an empty filter set", () => {
    expect(filtersToParams({}).toString()).toBe("");
  });
});

describe("the allowlist itself", () => {
  it("does not include the period lens fields", () => {
    expect(TRADE_FILTER_KEYS).not.toContain("from");
    expect(TRADE_FILTER_KEYS).not.toContain("to");
  });

  it("is exactly the four filter fields the API accepts", () => {
    expect([...TRADE_FILTER_KEYS].sort()).toEqual(["asset", "result", "session", "setup"]);
  });
});
