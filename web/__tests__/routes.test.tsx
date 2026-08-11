import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

const WEB = path.resolve(__dirname, "..");

const ROUTES = [
  "login",
  "signup",
  "verify-email",
  "forgot-password",
  "reset-password",
  "onboarding",
];

describe("auth route structure", () => {
  it.each(ROUTES)("/%s has a page", (route) => {
    expect(existsSync(path.join(WEB, "app", route, "page.tsx"))).toBe(true);
  });

  it("serves the existing marketing site at / rather than a React rewrite", () => {
    const config = readFileSync(path.join(WEB, "next.config.mjs"), "utf8");
    expect(config).toContain('source: "/"');
    expect(config).toContain('destination: "/index.html"');
    // The authored marketing site is still where it was; nothing moved into web/.
    expect(existsSync(path.resolve(WEB, "..", "site", "index.html"))).toBe(true);
  });

  it("sets clickjacking and referrer headers", () => {
    const config = readFileSync(path.join(WEB, "next.config.mjs"), "utf8");
    expect(config).toContain("X-Frame-Options");
    expect(config).toContain("DENY");
    // The Streamlit session credential rides in a URL during the beta, so the
    // Referer must not carry it to another origin.
    expect(config).toContain("no-referrer");
    expect(config).toContain("nosniff");
  });
});

describe("controls that do not work are not shown", () => {
  /**
   * Comments are stripped first. The component's docstring explains *why* the
   * Google button and Remember me are omitted, so it necessarily names both —
   * that is documentation, not a rendered control.
   */
  function rendered(file: string): string {
    return readFileSync(path.join(WEB, file), "utf8")
      .split("\n")
      .filter((line) => {
        const t = line.trim();
        return !t.startsWith("//") && !t.startsWith("*") && !t.startsWith("/*");
      })
      .join("\n")
      .toLowerCase();
  }

  const card = rendered("components/ui/sign-in-card-2.tsx");

  it("shows no Google button until real OAuth exists", () => {
    expect(card).not.toContain("google");
  });

  it("shows no Remember me until it changes session behaviour", () => {
    expect(card).not.toContain("remember me");
  });

  it("does not fake a successful sign-in", () => {
    const form = readFileSync(path.join(WEB, "app", "login", "login-form.tsx"), "utf8");
    expect(form).toContain("not connected yet");
  });
});
