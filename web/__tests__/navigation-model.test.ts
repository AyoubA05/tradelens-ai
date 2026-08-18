import { describe, expect, it } from "vitest";

import {
  APP_DESTINATIONS,
  PRIMARY_ACTION,
  isActiveDestination,
} from "@/lib/app/navigation";

describe("destinations", () => {
  it("reproduces the journal's information architecture", () => {
    expect(APP_DESTINATIONS.map((d) => d.label)).toEqual([
      "Overview",
      "Journal",
      "Analytics",
      "AI Reviews",
      "Strategy Profile",
      "Settings",
    ]);
  });

  it("gives every destination a route under /app", () => {
    for (const d of APP_DESTINATIONS) expect(d.href.startsWith("/app")).toBe(true);
  });

  it("has no duplicate routes", () => {
    const hrefs = APP_DESTINATIONS.map((d) => d.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("marks exactly four destinations for the phone bar", () => {
    // Four plus More. A fifth makes the targets too narrow to hit at 375px.
    expect(APP_DESTINATIONS.filter((d) => d.phonePriority)).toHaveLength(4);
  });

  it("keeps logging a trade as the primary action, not a destination", () => {
    expect(PRIMARY_ACTION.label).toBe("Log completed trade");
    expect(APP_DESTINATIONS.map((d) => d.href)).not.toContain(PRIMARY_ACTION.href);
  });
});

describe("active matching", () => {
  it("matches a destination exactly", () => {
    expect(isActiveDestination("/app/journal", "/app/journal")).toBe(true);
  });

  it("matches a child route", () => {
    expect(isActiveDestination("/app/journal/42", "/app/journal")).toBe(true);
  });

  it("does not let Overview swallow every other route", () => {
    // "/app" is a prefix of everything under it, so a naive startsWith would
    // light up Overview on every screen in the product.
    expect(isActiveDestination("/app/journal", "/app")).toBe(false);
    expect(isActiveDestination("/app", "/app")).toBe(true);
  });

  it("does not match a route that merely shares a prefix", () => {
    expect(isActiveDestination("/app/journalling", "/app/journal")).toBe(false);
  });

  it("ignores a trailing slash", () => {
    expect(isActiveDestination("/app/journal/", "/app/journal")).toBe(true);
  });
});
