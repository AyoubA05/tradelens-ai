import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { continuePageRedirect, nextDestinationFor, type WebsiteUser } from "@/lib/auth/session";

function user(overrides: Partial<WebsiteUser> = {}): WebsiteUser {
  return {
    userId: 1,
    email: "trader@example.com",
    emailVerifiedAt: new Date(),
    emailVerificationRequired: true,
    onboardingCompleted: true,
    strategyProfileCompleted: true,
    appSurface: "streamlit",
    ...overrides,
  };
}

describe("app_surface routing", () => {
  it("sends a migrated account to the new app", () => {
    expect(nextDestinationFor(user({ appSurface: "nextjs" }))).toBe("/app");
  });

  it("leaves every other account on the existing handoff", () => {
    expect(nextDestinationFor(user({ appSurface: "streamlit" }))).toBe("/continue");
  });

  it("treats an unrecognised value as not migrated", () => {
    // Fail closed: an unknown surface must not strand a trader on a shell that
    // cannot yet show their journal.
    expect(nextDestinationFor(user({ appSurface: "something-else" }))).toBe("/continue");
  });

  it("still gates on email and onboarding before surface is considered", () => {
    expect(
      nextDestinationFor(user({ appSurface: "nextjs", emailVerifiedAt: null })),
    ).toBe("/verify-email");
    expect(
      nextDestinationFor(user({ appSurface: "nextjs", onboardingCompleted: false })),
    ).toBe("/onboarding");
  });
});

describe("the cutover is opt-in", () => {
  it("moves nobody by default", () => {
    // Reading the column must not migrate anyone. Every account arrives here
    // as "streamlit" because the Phase 0 migration set that server-side
    // default and backfilled nothing.
    expect(nextDestinationFor(user())).toBe("/continue");
  });

  it("has no write to app_surface anywhere under web/", () => {
    // Phase 1 has no legitimate reason to write this column at all, so the
    // strongest simple invariant is asserted directly: no assignment to
    // app_surface anywhere in lib/, app/, or scripts/. A later phase that adds
    // a deliberate, reviewed, per-account opt-in path will have to touch this
    // test to add one back.
    const roots = ["lib", "app", "scripts"].map((d) => path.join(__dirname, "..", d));
    const selfPath = path.join(__dirname, "app-surface-routing.test.ts");
    const files: string[] = [];
    function walk(d: string) {
      if (!fs.existsSync(d)) return;
      for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
        const full = path.join(d, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (/\.(ts|tsx)$/.test(entry.name)) files.push(full);
      }
    }
    roots.forEach(walk);

    for (const file of files) {
      if (file === selfPath) continue;
      const source = fs.readFileSync(file, "utf8");
      // Any assignment to the column — `SET app_surface = ...` or
      // `app_surface = ...` in a write clause — regardless of what else
      // precedes it in the statement or how it claims to be scoped.
      expect(
        /app_surface\s*=(?!=)/.test(source),
        `${file} appears to write app_surface`,
      ).toBe(false);
    }
  });
});

describe("continuePageRedirect", () => {
  // This is what /continue itself calls. It exists so the ordering — gates
  // before the surface check — is pinned by an assertion here rather than by
  // trusting the page's control flow, which is exactly what regressed:
  // review round 1 found the page redirecting a migrated-but-unverified
  // account straight to /app.
  it("sends an eligible, migrated account to /app", () => {
    expect(continuePageRedirect(user({ appSurface: "nextjs" }), true)).toBe("/app");
  });

  it("leaves an eligible, unmigrated account on /continue", () => {
    expect(continuePageRedirect(user({ appSurface: "streamlit" }), true)).toBeNull();
  });

  it("never returns /app for an ineligible account, migrated or not", () => {
    // The regression this pins: appSurface alone must not be enough. An
    // account that failed the email/onboarding gate is ineligible regardless
    // of appSurface, and must be sent by nextDestinationFor's own gates, not
    // to /app.
    expect(
      continuePageRedirect(user({ appSurface: "nextjs", emailVerifiedAt: null }), false),
    ).toBe("/verify-email");
    expect(
      continuePageRedirect(user({ appSurface: "nextjs", onboardingCompleted: false }), false),
    ).toBe("/onboarding");
  });
});
