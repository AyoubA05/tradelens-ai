import "@testing-library/jest-dom/vitest";

import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { APP_DESTINATIONS, PRIMARY_ACTION } from "@/lib/app/navigation";

const APP_DIR = path.join(__dirname, "..", "app");

function pageFileFor(href: string): string {
  const segments = href.replace(/^\/app\/?/, "");
  return path.join(APP_DIR, "app", segments, "page.tsx");
}

describe("every navigation target resolves to a route", () => {
  it.each(APP_DESTINATIONS.map((d) => [d.label, d.href]))(
    "%s has a page at %s",
    (_label, href) => {
      expect(fs.existsSync(pageFileFor(href))).toBe(true);
    },
  );

  it("the primary action has a page", () => {
    expect(fs.existsSync(pageFileFor(PRIMARY_ACTION.href))).toBe(true);
  });

  it("no destination links somewhere that does not exist", () => {
    // A nav entry pointing at a 404 is worse than a missing entry: it looks
    // like the product is broken rather than incomplete.
    const missing = APP_DESTINATIONS.filter((d) => !fs.existsSync(pageFileFor(d.href)));
    expect(missing.map((d) => d.href)).toEqual([]);
  });
});
