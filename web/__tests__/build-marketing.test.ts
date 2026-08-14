import { describe, expect, it } from "vitest";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

/**
 * The marketing build's guard rails.
 *
 * This step is the entire integration between the committed vanilla site and
 * the Next app, and it runs as `prebuild` — which means `npx next build` skips
 * it and `npm run build` does not. Every build check up to Step 11 used the
 * former, so this script had never actually run in a verification pass, and a
 * clean-clone build was what finally exposed that it silently ignored
 * `__SUPPORT_EMAIL__` and published the literal token to visitors.
 *
 * The tests below are therefore mostly about failing, not about succeeding.
 */

import {
  buildMarketing,
  validateOrigin,
  validateSupportEmail,
} from "../scripts/build-marketing.mjs";

describe("origin validation", () => {
  it("accepts a real production origin", () => {
    expect(validateOrigin("https://www.tradelensai.io", "SITE_ORIGIN")).toBe(
      "https://www.tradelensai.io",
    );
  });

  it("rejects a reserved placeholder domain", () => {
    // Syntactically perfect and completely wrong. It would be baked into
    // canonical, og:url and og:image, which is what the token exists to catch.
    for (const host of [
      "https://www.example.test",
      "https://tradelens.invalid",
      "https://site.example",
    ]) {
      expect(() => validateOrigin(host, "SITE_ORIGIN")).toThrow(/reserved placeholder/);
    }
  });

  it("rejects a host with no dot", () => {
    expect(() => validateOrigin("https://intranet", "SITE_ORIGIN")).toThrow(
      /fully-qualified/,
    );
  });

  it("rejects plain http off loopback", () => {
    expect(() => validateOrigin("http://www.tradelensai.io", "SITE_ORIGIN")).toThrow(
      /https/,
    );
  });

  it("allows loopback for development, and only when asked", () => {
    expect(validateOrigin("http://localhost:3000", "SITE_ORIGIN")).toBe(
      "http://localhost:3000",
    );
    expect(() =>
      validateOrigin("http://localhost:3000", "SITE_ORIGIN", { allowLocal: false }),
    ).toThrow(/loopback/);
  });

  it("rejects an origin carrying a path or query", () => {
    expect(() => validateOrigin("https://a.io/site", "SITE_ORIGIN")).toThrow(/bare origin/);
    expect(() => validateOrigin("https://a.io/?x=1", "SITE_ORIGIN")).toThrow(/bare origin/);
  });

  it("rejects an unset value rather than defaulting", () => {
    expect(() => validateOrigin("", "APP_ORIGIN")).toThrow(/not set/);
    expect(() => validateOrigin(undefined, "APP_ORIGIN")).toThrow(/not set/);
  });
});

describe("support email validation", () => {
  it("accepts a real address", () => {
    expect(validateSupportEmail(" support@tradelensai.io ")).toBe(
      "support@tradelensai.io",
    );
  });

  it("refuses to build without one", () => {
    // The defect: this was not checked at all, and the page shipped the token.
    expect(() => validateSupportEmail("")).toThrow(/not set/);
    expect(() => validateSupportEmail(undefined)).toThrow(/not set/);
  });

  it("rejects malformed addresses", () => {
    for (const bad of ["nobody", "no@domain", "two@@at.io", "has space@a.io"]) {
      expect(() => validateSupportEmail(bad), bad).toThrow(/not a valid address/);
    }
  });
});

describe("the surviving-token guard", () => {
  /**
   * Exercised against a throwaway source tree rather than the real site/, so
   * it tests the rule and not today's content.
   */
  async function buildFixture(html: string, env: Record<string, string>) {
    const root = await mkdtemp(path.join(tmpdir(), "tl-marketing-"));
    const sourceDir = path.join(root, "site");
    const outputDir = path.join(root, "public");
    await mkdir(sourceDir, { recursive: true });
    await writeFile(path.join(sourceDir, "index.html"), html, "utf8");
    await buildMarketing({ ...env, sourceDir, outputDir });
    return path.join(outputDir, "index.html");
  }

  const ENV = {
    siteOrigin: "https://www.tradelensai.io",
    appOrigin: "https://journal.streamlit.app",
    supportEmail: "support@tradelensai.io",
  };

  it("substitutes all three tokens", async () => {
    const out = await buildFixture(
      `<a href="__SITE_ORIGIN__/x">s</a><a href="__APP_ORIGIN__">a</a>` +
        `<a href="mailto:__SUPPORT_EMAIL__">__SUPPORT_EMAIL__</a>`,
      ENV,
    );
    const html = await readFile(out, "utf8");
    expect(html).toContain("https://www.tradelensai.io/x");
    expect(html).toContain("https://journal.streamlit.app");
    expect(html).toContain("mailto:support@tradelensai.io");
    expect(html).not.toMatch(/__[A-Z_]+__/);
  });

  it("fails the build when an unknown token survives", async () => {
    // The general case: a token this script has never heard of must stop the
    // deploy, not reach a visitor.
    await expect(
      buildFixture(`<p>Contact __PHONE_NUMBER__ today</p>`, ENV),
    ).rejects.toThrow(/deploy token survived/);
  });

  it("names the file and the token it found", async () => {
    await expect(buildFixture(`<p>__PHONE_NUMBER__</p>`, ENV)).rejects.toThrow(
      /index\.html.*__PHONE_NUMBER__/s,
    );
  });
});
