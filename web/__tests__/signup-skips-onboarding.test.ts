import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

import { NEW_ACCOUNT_DEFAULTS } from "@/lib/auth/contract";
import { nextDestinationFor, type WebsiteUser } from "@/lib/auth/session";

/**
 * A completed site signup must not be asked for the same details twice.
 *
 * Signup requires and stores full name, birthday and referral source. The
 * account was nevertheless created with `onboarding_completed = false`, so the
 * first login after verifying an email routed to `/onboarding` and presented
 * exactly the fields the person had already filled in.
 *
 * The fix is one value, which makes it easy to revert by accident — hence a
 * test that asserts the *destination* rather than the flag. `/onboarding`
 * itself is deliberately kept for accounts that really are incomplete, so this
 * also pins that it still works for them.
 */

function user(overrides: Partial<WebsiteUser> = {}): WebsiteUser {
  return {
    userId: 1,
    email: "trader@example.test",
    emailVerifiedAt: new Date("2026-08-14T00:00:00Z"),
    emailVerificationRequired: false,
    onboardingCompleted: true,
    strategyProfileCompleted: false,
    appSurface: "streamlit",
    ...overrides,
  };
}

describe("a fresh site signup", () => {
  it("starts with personal onboarding already complete", () => {
    expect(NEW_ACCOUNT_DEFAULTS.onboarding_completed).toBe(true);
  });

  it("still starts with the Strategy Profile gate closed", () => {
    // The whole point of separating the two: Streamlit owns this one, and a
    // new account must still be sent through the first-run Strategy Profile.
    expect(NEW_ACCOUNT_DEFAULTS.strategy_profile_completed).toBe(false);
  });

  it("still requires email verification", () => {
    expect(NEW_ACCOUNT_DEFAULTS.email_verification_required).toBe(true);
    expect(NEW_ACCOUNT_DEFAULTS.email_verified_at).toBeNull();
  });

  it("routes the first login to /continue, not /onboarding", () => {
    expect(nextDestinationFor(user())).toBe("/continue");
  });

  it("routes to verification before anything else when unverified", () => {
    expect(
      nextDestinationFor(
        user({ emailVerifiedAt: null, emailVerificationRequired: true }),
      ),
    ).toBe("/verify-email");
  });
});

describe("the /onboarding fallback still exists for incomplete accounts", () => {
  it("routes a verified but incomplete account to /onboarding", () => {
    expect(nextDestinationFor(user({ onboardingCompleted: false }))).toBe(
      "/onboarding",
    );
  });

  it("keeps the route and its endpoint in the tree", () => {
    for (const relative of [
      "app/onboarding/page.tsx",
      "app/onboarding/onboarding-form.tsx",
      "app/api/auth/onboarding/route.ts",
    ]) {
      expect(() =>
        readFileSync(path.resolve(__dirname, "..", relative), "utf8"),
      ).not.toThrow();
    }
  });
});

describe("the account defaults are what signup actually writes", () => {
  /**
   * The contract constant is only meaningful if the INSERT reads from it. If
   * signup hardcoded its own literal, every assertion above would pass while
   * production kept creating accounts the old way.
   */
  it("signup inserts the contract defaults rather than literals", () => {
    const source = readFileSync(
      path.resolve(__dirname, "..", "lib/auth/signup.ts"),
      "utf8",
    );
    expect(source).toContain("NEW_ACCOUNT_DEFAULTS.onboarding_completed");
    expect(source).toContain("NEW_ACCOUNT_DEFAULTS.strategy_profile_completed");
    expect(source).toContain("NEW_ACCOUNT_DEFAULTS.email_verification_required");

    // No literal booleans in the users INSERT parameter list.
    const insert = source.slice(
      source.indexOf("INSERT INTO users"),
      source.indexOf("RETURNING id"),
    );
    expect(insert).not.toMatch(/\bfalse\b/);
  });
});
