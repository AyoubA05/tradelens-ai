import { describe, expect, it } from "vitest";

import config from "../tailwind.config";

const colors = (config.theme?.extend?.colors ?? {}) as Record<string, string>;

describe("marketing tokens are load-bearing and must not drift", () => {
  // These exact values are what site/styles.css ships. The app joins the
  // marketing system; it does not get to redefine it. If one of these changes,
  // the live site changes with it.
  it.each([
    ["bg", "#0d1117"],
    ["surface", "#161b22"],
    ["surface-2", "#1c232b"],
    ["border", "#252a32"],
    ["text", "#e8eaed"],
    ["muted", "#9aa4b2"],
    ["accent", "#00e5cc"],
  ])("%s is still %s", (name, value) => {
    expect(colors[name]).toBe(value);
  });
});

describe("app layer tokens", () => {
  it.each(["surface-3", "line", "line-strong", "positive", "negative", "warning", "chart", "focus"])(
    "defines %s",
    (name) => {
      expect(colors[name]).toBeTruthy();
    },
  );

  it("keeps one accent, so teal stays the action colour rather than decoration", () => {
    const teals = Object.entries(colors).filter(
      ([, v]) => typeof v === "string" && v.toLowerCase() === "#00e5cc",
    );
    expect(teals.map(([k]) => k).sort()).toEqual(["accent", "focus"]);
  });

  it("separates profit and loss from the accent", () => {
    expect(colors.positive).not.toBe(colors.accent);
    expect(colors.negative).not.toBe(colors.accent);
  });
});
