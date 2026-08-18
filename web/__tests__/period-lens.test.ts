import { describe, expect, it } from "vitest";

import {
  PERIOD_PRESETS,
  formatPeriod,
  periodFromParams,
  periodToParams,
  routeUsesPeriod,
} from "@/lib/app/period";

const TODAY = new Date("2026-08-18T12:00:00Z");

describe("reading a period from the URL", () => {
  it("defaults to the last 30 days when nothing is set", () => {
    const p = periodFromParams(new URLSearchParams(), TODAY);
    expect(p.to).toBe("2026-08-18");
    expect(p.from).toBe("2026-07-20");
    expect(p.presetId).toBe("30d");
  });

  it("reads an explicit range", () => {
    const p = periodFromParams(
      new URLSearchParams("from=2026-08-01&to=2026-08-15"),
      TODAY,
    );
    expect(p).toEqual({ from: "2026-08-01", to: "2026-08-15", presetId: "custom" });
  });

  it("recognises a range that matches a preset", () => {
    const p = periodFromParams(
      new URLSearchParams("from=2026-08-12&to=2026-08-18"),
      TODAY,
    );
    expect(p.presetId).toBe("7d");
  });

  it("falls back to the default when a date is unparseable", () => {
    // A hand-edited URL must not produce a window no page can render.
    const p = periodFromParams(new URLSearchParams("from=yesterday&to=soon"), TODAY);
    expect(p.presetId).toBe("30d");
  });

  it("swaps a reversed range rather than returning an empty window", () => {
    const p = periodFromParams(
      new URLSearchParams("from=2026-08-18&to=2026-08-01"),
      TODAY,
    );
    expect(p.from).toBe("2026-08-01");
    expect(p.to).toBe("2026-08-18");
  });

  it("ignores a partial range", () => {
    expect(periodFromParams(new URLSearchParams("from=2026-08-01"), TODAY).presetId).toBe("30d");
  });
});

describe("writing a period back", () => {
  it("round-trips", () => {
    const p = periodFromParams(new URLSearchParams("from=2026-08-01&to=2026-08-15"), TODAY);
    expect(periodFromParams(periodToParams(p), TODAY)).toEqual(p);
  });

  it("emits both bounds so a link is self-contained", () => {
    const params = periodToParams({ from: "2026-08-01", to: "2026-08-15", presetId: "custom" });
    expect(params.get("from")).toBe("2026-08-01");
    expect(params.get("to")).toBe("2026-08-15");
  });
});

describe("presets", () => {
  it("offers windows a trader actually reviews in", () => {
    expect(PERIOD_PRESETS.map((p) => p.id)).toEqual(["7d", "30d", "90d", "ytd"]);
  });
});

describe("formatting", () => {
  it("reads as a range, in ISO order, for the mono top bar", () => {
    expect(formatPeriod({ from: "2026-08-12", to: "2026-08-18", presetId: "7d" })).toBe(
      "2026-08-12 → 2026-08-18",
    );
  });
});

describe("which routes the range governs", () => {
  it("governs the surfaces that aggregate performance", () => {
    expect(routeUsesPeriod("/app")).toBe(true);
    expect(routeUsesPeriod("/app/journal")).toBe(true);
    expect(routeUsesPeriod("/app/analytics")).toBe(true);
    expect(routeUsesPeriod("/app/reviews")).toBe(true);
  });

  it("leaves a single trade alone — a range means nothing there", () => {
    expect(routeUsesPeriod("/app/journal/42")).toBe(false);
  });

  it("leaves routes that are not time-scoped alone", () => {
    expect(routeUsesPeriod("/app/trades/new")).toBe(false);
    expect(routeUsesPeriod("/app/strategy")).toBe(false);
    expect(routeUsesPeriod("/app/settings")).toBe(false);
  });

  it("yields to a view that carries its own temporal control", () => {
    // Weekly Recap keeps its week selector and Daily Debrief its day selector.
    // Two controls claiming the same scope on one view is the thing this
    // allowlist exists to prevent.
    expect(routeUsesPeriod("/app/reviews/weekly")).toBe(false);
    expect(routeUsesPeriod("/app/reviews/daily")).toBe(false);
  });

  it("does not let a child route inherit the range by accident", () => {
    // Exact matching, deliberately: a new sub-route must opt in on purpose
    // rather than acquire a lens nobody decided it should have.
    expect(routeUsesPeriod("/app/analytics/setups")).toBe(false);
  });

  it("ignores a trailing slash", () => {
    expect(routeUsesPeriod("/app/journal/")).toBe(true);
  });
});
