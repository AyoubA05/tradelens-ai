import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { nextDestinationFor, type WebsiteUser } from "@/lib/auth/session";

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

  it("has no bulk switch anywhere in the web layer", () => {
    // The invariant that survives review and then dies in a later convenience
    // commit. If a "migrate all users" path is ever added, this fails.
    const dir = path.join(__dirname, "..", "lib");
    const files: string[] = [];
    (function walk(d: string) {
      for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
        const full = path.join(d, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (entry.name.endsWith(".ts")) files.push(full);
      }
    })(dir);

    for (const file of files) {
      const source = fs.readFileSync(file, "utf8");
      // A write to app_surface that is not scoped to a single id.
      expect(
        /UPDATE\s+users\s+SET\s+app_surface(?![\s\S]{0,200}WHERE[\s\S]{0,40}id)/i.test(source),
        `${file} appears to switch app_surface without scoping to one account`,
      ).toBe(false);
    }
  });
});
