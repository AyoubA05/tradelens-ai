import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

/**
 * SITE_ORIGIN and APP_ORIGIN must never trade places.
 *
 * They are both public https origins of the same product, one string apart in
 * every config screen, and swapping them is silent: the app still builds, the
 * pages still render, and the only symptom is that verification and password
 * reset links point at a Streamlit host with no route to consume them. The
 * credential would be emailed to the wrong origin, the user would click a dead
 * link, and — worse than a visible failure — it would teach people that a
 * TradeLens auth link legitimately arrives on a `streamlit.app` domain.
 *
 * So the separation is asserted structurally rather than trusted:
 *
 *   APP_ORIGIN   is read in exactly ONE module, the handoff destination.
 *   SITE_ORIGIN  is read for CSRF comparison, mail links, and return links,
 *                and never used as a redirect destination for the app.
 */

const WEB = path.resolve(__dirname, "..");

function sources(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (["node_modules", ".next", "public", "__tests__", "scripts"].includes(entry)) {
      continue;
    }
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) sources(full, acc);
    else if (/\.(ts|tsx)$/.test(entry)) acc.push(full);
  }
  return acc;
}

/** Strip comments — several modules explain the rule by naming both variables. */
function code(text: string): string {
  return text
    .split("\n")
    .filter((line) => {
      const t = line.trim();
      return !t.startsWith("//") && !t.startsWith("*") && !t.startsWith("/*");
    })
    .join("\n");
}

const FILES = sources(WEB);

/** Modules allowed to name APP_ORIGIN at all. */
const APP_ORIGIN_READERS = ["lib/security/app-origin.ts", "lib/env.ts"];

describe("origin separation", () => {
  it("reads APP_ORIGIN in exactly one place", () => {
    const readers = FILES.filter((file) => code(readFileSync(file, "utf8")).includes("APP_ORIGIN"))
      .map((file) => path.relative(WEB, file))
      .sort();
    expect(readers).toEqual(APP_ORIGIN_READERS.slice().sort());
  });

  it("never builds a mail link from APP_ORIGIN", () => {
    // The failure mode that matters most: a credential emailed to the app host.
    const mail = code(readFileSync(path.join(WEB, "lib/mail/messages.ts"), "utf8"));
    expect(mail).not.toContain("APP_ORIGIN");

    for (const modulePath of ["lib/auth/verification.ts", "lib/auth/password-reset.ts"]) {
      expect(code(readFileSync(path.join(WEB, modulePath), "utf8"))).not.toContain("APP_ORIGIN");
    }
  });

  it("never compares CSRF against APP_ORIGIN", () => {
    // Accepting cross-origin POSTs from the app host would let anything hosted
    // on streamlit.app drive this site's state-changing endpoints.
    for (const file of FILES) {
      const text = code(readFileSync(file, "utf8"));
      if (!text.includes("isSameOriginRequest")) continue;
      const calls = text.match(/isSameOriginRequest\([^)]*\)/g) ?? [];
      for (const call of calls) {
        expect(call, path.relative(WEB, file)).not.toContain("appOrigin");
        expect(call, path.relative(WEB, file)).not.toContain("APP_ORIGIN");
      }
    }
  });

  it("routes the handoff to the app host and nothing else there", () => {
    const handoff = code(readFileSync(path.join(WEB, "lib/security/app-origin.ts"), "utf8"));
    expect(handoff).toContain("APP_ORIGIN");
    // The one module that knows the app host must not also mint mail links.
    expect(handoff).not.toContain("verify-email");
    expect(handoff).not.toContain("reset-password");
  });

  it("keeps the two names distinct in the example configuration", () => {
    const example = readFileSync(path.join(WEB, ".env.example"), "utf8");
    const site = example.match(/^SITE_ORIGIN=(.*)$/m)?.[1]?.trim();
    const app = example.match(/^APP_ORIGIN=(.*)$/m)?.[1]?.trim();
    expect(site).toBeTruthy();
    expect(app).toBeTruthy();
    expect(site).not.toBe(app);
  });
});
