import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

import {
  LEGACY_USERNAME_RE,
  NEW_ACCOUNT_DEFAULTS,
  OPAQUE_USERNAME_RE,
  generateInternalUsername,
  isValidBirthday,
  isValidEmail,
  isValidReferral,
  isValidReferralOther,
  normalizeEmail,
  validatePassword,
} from "@/lib/auth/contract";

/**
 * The TypeScript half of the cross-language account-rule contract.
 *
 * `tests/test_auth_contract_vectors.py` reads this same JSON file and makes the
 * equivalent assertions against `services/users.py`. Signup is implemented
 * independently in each language — importing across the boundary would mean a
 * Python HTTP service on the signup path — so these shared vectors are what
 * keeps the two from becoming unrelated definitions of the same rules.
 */
/** Shape of the shared vectors. Declared so `it.each` stays type-checked
 *  instead of degrading to `any[]` the moment it comes out of JSON.parse. */
type Vectors = {
  email_normalization: { vectors: { input: string; expected: string | null }[] };
  email_validity: { valid: string[]; invalid: string[] };
  opaque_username: {
    pattern: string;
    length: number;
    derivation_probe: { forbidden_fragments: string[] };
  };
  password_policy: {
    min_length: number;
    require_lower: boolean;
    require_upper: boolean;
    require_digit: boolean;
    require_symbol: boolean;
    accepted: string[];
    rejected: { value: string; reason: string }[];
  };
  new_account_defaults: Record<string, unknown>;
  legacy_account_behaviour: Record<string, unknown>;
};

const VECTORS = JSON.parse(
  readFileSync(
    path.resolve(__dirname, "..", "..", "docs", "contracts", "auth-contract-vectors.json"),
    "utf8",
  ),
) as Vectors;

describe("email normalization", () => {
  it.each(VECTORS.email_normalization.vectors)(
    "normalizes $input",
    ({ input, expected }) => {
      expect(normalizeEmail(input)).toBe(expected);
    },
  );

  it("preserves +tags rather than merging distinct addresses", () => {
    expect(normalizeEmail("a+tag@example.com")).toBe("a+tag@example.com");
  });
});

describe("email validity", () => {
  it.each(VECTORS.email_validity.valid)("accepts %s", (value) => {
    expect(isValidEmail(value)).toBe(true);
  });
  it.each(VECTORS.email_validity.invalid)("rejects %j", (value) => {
    expect(isValidEmail(value)).toBe(false);
  });
});

describe("opaque internal username", () => {
  const pattern = new RegExp(VECTORS.opaque_username.pattern);

  it("matches the contract pattern and the legacy constraint", () => {
    for (let i = 0; i < 200; i += 1) {
      const username = generateInternalUsername();
      expect(username).toMatch(pattern);
      expect(username).toMatch(OPAQUE_USERNAME_RE);
      // Must satisfy the constraint every legacy username already satisfies,
      // or a new account cannot coexist with the old ones.
      expect(username).toMatch(LEGACY_USERNAME_RE);
      expect(username).toHaveLength(VECTORS.opaque_username.length);
    }
  });

  it("is not derived from the email, the name, or the referral", () => {
    // The generator takes no arguments at all, which is the structural
    // guarantee. This asserts the observable consequence.
    const { forbidden_fragments } = VECTORS.opaque_username.derivation_probe;
    for (let i = 0; i < 200; i += 1) {
      const username = generateInternalUsername().toLowerCase();
      for (const fragment of forbidden_fragments) {
        expect(username).not.toContain(fragment.toLowerCase());
      }
    }
  });

  it("does not collide across many generations", () => {
    const seen = new Set<string>();
    for (let i = 0; i < 5000; i += 1) seen.add(generateInternalUsername());
    expect(seen.size).toBe(5000);
  });
});

describe("password policy matches what the meter shows", () => {
  it.each(VECTORS.password_policy.accepted)("accepts %s", (value) => {
    expect(validatePassword(value)).toEqual([]);
  });

  it.each(VECTORS.password_policy.rejected)(
    "rejects $value ($reason)",
    ({ value }) => {
      expect(validatePassword(value).length).toBeGreaterThan(0);
    },
  );

  it("enforces exactly the four advertised requirements", () => {
    const p = VECTORS.password_policy;
    expect(p.min_length).toBe(12);
    expect(p.require_lower && p.require_upper && p.require_digit && p.require_symbol).toBe(true);
  });
});

/** Drop the `$comment` annotations so only the rules themselves are compared. */
function rulesOnly(section: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(section).filter(([key]) => !key.startsWith("$comment")),
  );
}

describe("new account defaults", () => {
  it("matches the contract", () => {
    expect({ ...NEW_ACCOUNT_DEFAULTS }).toEqual(
      rulesOnly(VECTORS.new_account_defaults),
    );
  });

  it("requires verification, so a new account cannot inherit the legacy exemption", () => {
    expect(NEW_ACCOUNT_DEFAULTS.email_verification_required).toBe(true);
    expect(VECTORS.legacy_account_behaviour.email_verification_required).toBe(false);
    // The two must differ. If they ever match, either new accounts skip
    // verification or legacy accounts get locked out.
    expect(NEW_ACCOUNT_DEFAULTS.email_verification_required).not.toBe(
      VECTORS.legacy_account_behaviour.email_verification_required,
    );
  });

  it("starts unverified with no fabricated timestamp", () => {
    expect(NEW_ACCOUNT_DEFAULTS.email_verified_at).toBeNull();
    expect(VECTORS.legacy_account_behaviour.email_verified_at).toBeNull();
  });
});

describe("birthday validation", () => {
  const today = new Date("2026-08-11T00:00:00Z");
  it.each(["1994-02-17", "2000-01-01", "1970-12-31"])("accepts %s", (v) => {
    expect(isValidBirthday(v, today)).toBe(true);
  });
  it.each([
    "not-a-date",
    "2026-13-01", // month 13
    "2026-02-31", // rolls over to March; the round-trip check catches it
    "2027-01-01", // future
    "1800-01-01", // implausible
    "0005-02-18", // screenshot value; far outside the 130-year window
    "11/08/1994", // wrong format
    "",
  ])("rejects %j", (v) => {
    expect(isValidBirthday(v, today)).toBe(false);
  });
});

describe("referral validation", () => {
  it("accepts only the eight listed sources", () => {
    for (const source of ["TikTok", "Instagram", "YouTube", "Google/Search", "Friend", "Reddit", "X/Twitter", "Other"]) {
      expect(isValidReferral(source)).toBe(true);
    }
    expect(isValidReferral("MySpace")).toBe(false);
    expect(isValidReferral("")).toBe(false);
  });

  it("permits referralOther only alongside Other", () => {
    expect(isValidReferralOther("Other", "A Discord server")).toBe(true);
    expect(isValidReferralOther("Other", null)).toBe(true);
    // Rejected rather than silently dropped: a mismatched payload is a client
    // bug worth surfacing.
    expect(isValidReferralOther("TikTok", "A Discord server")).toBe(false);
  });

  it("bounds referralOther length", () => {
    expect(isValidReferralOther("Other", "x".repeat(121))).toBe(false);
    expect(isValidReferralOther("Other", "x".repeat(120))).toBe(true);
  });
});
