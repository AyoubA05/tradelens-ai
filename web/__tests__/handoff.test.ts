import { beforeEach, describe, expect, it, vi } from "vitest";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import pathMod from "node:path";

/**
 * Handoff issuer, redirect construction, and the credential-separation
 * invariant.
 *
 * Several tests here exist specifically to fail if someone takes the shortcut
 * of reusing the website cookie as the handoff. That shortcut would work
 * perfectly in manual testing and would put a 12-hour HttpOnly credential into
 * an address bar, so it needs a test rather than a comment.
 */

const { runTransaction, runQuery, recordAttempt, isRateLimited, logAuthEvent, authenticate } =
  vi.hoisted(() => ({
    runTransaction: vi.fn(),
    runQuery: vi.fn(),
    recordAttempt: vi.fn(),
    isRateLimited: vi.fn(),
    logAuthEvent: vi.fn(),
    authenticate: vi.fn(),
  }));

vi.mock("@/lib/db/client", () => ({ query: runQuery, transaction: runTransaction }));
vi.mock("@/lib/auth/rate-limit", () => ({
  recordAttempt, isRateLimited, clearFailures: vi.fn(),
  bucketFor: async (k: string, v: string) => `${k}:${v.length}`,
  clientIp: () => "203.0.113.7",
}));
vi.mock("@/lib/security/responses", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/security/responses")>();
  return { ...actual, logAuthEvent };
});
vi.mock("@/lib/auth/session", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/auth/session")>();
  return { ...actual, authenticateWebsiteRequest: authenticate };
});

import type { WebsiteUser } from "@/lib/auth/session";
import { HANDOFF_TTL_SECONDS, handoffEligibility, issueHandoff } from "@/lib/auth/handoff";
import { InvalidAppOriginError, handoffRedirectUrl, validatedAppOrigin } from "@/lib/security/app-origin";

const CONTRACT = JSON.parse(
  readFileSync(
    pathMod.resolve(__dirname, "..", "..", "docs", "contracts", "auth-contract-vectors.json"),
    "utf8",
  ),
).handoff as {
  ttl_seconds: number;
  token_entropy_bytes: number;
  hash_encoding: string;
  query_parameter: string;
  claims_in_token: string[];
  eligibility: Record<string, boolean>;
};

const ELIGIBLE: WebsiteUser = {
  userId: 9,
  email: "a@b.co",
  emailVerifiedAt: new Date(),
  emailVerificationRequired: false,
  onboardingCompleted: true,
  strategyProfileCompleted: false,
};

const APP = "https://app.example.test";
const COOKIE_VALUE = "website-cookie-credential-value";

function stubTransaction(voided: number = 0) {
  const statements: { sql: string; params: unknown[] }[] = [];
  runTransaction.mockImplementation(async (fn: never) => {
    const run = async (sql: string, params: unknown[] = []) => {
      statements.push({ sql: sql.replace(/\s+/g, " ").trim(), params });
      return sql.includes("UPDATE auth_handoffs")
        ? Array.from({ length: voided }, (_, i) => ({ id: i + 1 }))
        : [];
    };
    return (fn as unknown as (r: typeof run) => Promise<unknown>)(run);
  });
  return statements;
}

async function post(headers: Record<string, string> = {}, body = "") {
  const { POST } = await import("@/app/api/auth/handoff/route");
  return POST(new Request("https://site.test/api/auth/handoff", {
    method: "POST",
    headers: { origin: "https://site.test", ...headers },
    body,
  }));
}

beforeEach(() => {
  vi.resetModules();
  runTransaction.mockReset();
  runQuery.mockReset().mockResolvedValue([]);
  recordAttempt.mockReset();
  isRateLimited.mockReset().mockResolvedValue(false);
  logAuthEvent.mockReset();
  authenticate.mockReset().mockResolvedValue(ELIGIBLE);
  process.env.SITE_ORIGIN = "https://site.test";
  process.env.APP_ORIGIN = APP;
});

// ---------------------------------------------------------------------------
// Token shape — pinned against the shared contract
// ---------------------------------------------------------------------------

describe("handoff token", () => {
  it("matches the contract TTL of 120 seconds", async () => {
    expect(HANDOFF_TTL_SECONDS).toBe(CONTRACT.ttl_seconds);
    expect(HANDOFF_TTL_SECONDS).toBe(120);
    stubTransaction();
    const now = new Date("2026-08-13T10:00:00Z");
    const { expiresAt } = await issueHandoff(9, now);
    expect(expiresAt.toISOString()).toBe("2026-08-13T10:02:00.000Z");
  });

  it("carries the contract entropy and is opaque", async () => {
    stubTransaction();
    const { token } = await issueHandoff(9);
    expect(Buffer.from(token, "base64url").length).toBe(CONTRACT.token_entropy_bytes);
    expect(CONTRACT.claims_in_token).toEqual([]);
    expect(() => JSON.parse(Buffer.from(token, "base64url").toString("utf8"))).toThrow();
  });

  it("stores only a lowercase hex sha256, never the raw token", async () => {
    const statements = stubTransaction();
    const { token } = await issueHandoff(9);
    const insert = statements.find((s) => s.sql.startsWith("INSERT INTO auth_handoffs"))!;
    const stored = insert.params[0] as string;
    expect(stored).toBe(createHash("sha256").update(token, "utf8").digest("hex"));
    expect(stored).toMatch(/^[0-9a-f]{64}$/);
    expect(CONTRACT.hash_encoding).toContain("hex");
    expect(JSON.stringify(statements)).not.toContain(token);
  });

  it("differs on every issue", async () => {
    stubTransaction();
    const seen = new Set<string>();
    for (let i = 0; i < 50; i += 1) seen.add((await issueHandoff(9)).token);
    expect(seen.size).toBe(50);
  });
});

// ---------------------------------------------------------------------------
// One outstanding handoff, and the lock that makes it true
// ---------------------------------------------------------------------------

describe("outstanding handoff policy", () => {
  it("invalidates prior handoffs and inserts, in one transaction", async () => {
    const statements = stubTransaction(2);
    const { invalidated } = await issueHandoff(9);
    expect(invalidated).toBe(2);
    expect(runTransaction).toHaveBeenCalledTimes(1);
    const sqls = statements.map((s) => s.sql);
    expect(sqls.some((s) => s.includes("UPDATE auth_handoffs SET consumed_at"))).toBe(true);
    expect(sqls.some((s) => s.startsWith("INSERT INTO auth_handoffs"))).toBe(true);
    expect(sqls.findIndex((s) => s.includes("UPDATE auth_handoffs")))
      .toBeLessThan(sqls.findIndex((s) => s.startsWith("INSERT INTO auth_handoffs")));
  });

  it("takes a row lock first, so concurrent issues cannot both leave a live token", async () => {
    const statements = stubTransaction();
    await issueHandoff(9);
    // Without FOR UPDATE, two transactions each read "no live handoff", each
    // invalidate nothing, and both insert.
    expect(statements[0]!.sql).toContain("FOR UPDATE");
    expect(statements[0]!.sql).toContain("FROM users WHERE id = $1");
  });

  it("scopes invalidation to the one user", async () => {
    const statements = stubTransaction();
    await issueHandoff(9);
    const update = statements.find((s) => s.sql.includes("UPDATE auth_handoffs"))!;
    expect(update.sql).toContain("WHERE user_id = $1");
    expect(update.params[0]).toBe(9);
  });
});

// ---------------------------------------------------------------------------
// Eligibility
// ---------------------------------------------------------------------------

describe("eligibility", () => {
  it("accepts an eligible user", () => {
    expect(handoffEligibility(ELIGIBLE).eligible).toBe(true);
  });

  it("stays eligible with strategy_profile_completed false", () => {
    // Required, not incidental: that false is what routes a new user into the
    // first-run Strategy Profile. Requiring it would make it unreachable.
    expect(CONTRACT.eligibility.requires_strategy_profile_completed).toBe(false);
    expect(handoffEligibility({ ...ELIGIBLE, strategyProfileCompleted: false }).eligible).toBe(true);
  });

  it("accepts a legacy account on the verification exemption", () => {
    expect(handoffEligibility({
      ...ELIGIBLE, email: null, emailVerifiedAt: null,
      emailVerificationRequired: false, onboardingCompleted: true,
    }).eligible).toBe(true);
  });

  it.each([
    ["no session", null, "no_session"],
    ["unverified", { ...ELIGIBLE, emailVerificationRequired: true, emailVerifiedAt: null }, "email_unverified"],
    ["onboarding incomplete", { ...ELIGIBLE, onboardingCompleted: false }, "onboarding_incomplete"],
  ])("refuses %s", (_l, user, reason) => {
    const r = handoffEligibility(user as WebsiteUser | null);
    expect(r.eligible).toBe(false);
    expect(r.eligible === false && r.reason).toBe(reason);
  });
});

// ---------------------------------------------------------------------------
// Redirect construction
// ---------------------------------------------------------------------------

describe("redirect", () => {
  it("carries only ht", () => {
    const url = new URL(handoffRedirectUrl("tok-abc"));
    expect(url.origin).toBe(APP);
    expect([...url.searchParams.keys()]).toEqual([CONTRACT.query_parameter]);
    expect(url.searchParams.get("ht")).toBe("tok-abc");
  });

  it("preserves a configured subpath", () => {
    const url = new URL(handoffRedirectUrl("tok", "https://app.example.test/journal"));
    expect(url.pathname).toBe("/journal");
    expect(url.searchParams.get("ht")).toBe("tok");
  });

  it("percent-encodes the token rather than concatenating", () => {
    const url = handoffRedirectUrl("a b&c=d#e");
    expect(url).not.toContain("&c=");
    expect(new URL(url).searchParams.get("ht")).toBe("a b&c=d#e");
  });

  it.each([
    ["javascript:", "javascript:alert(1)"],
    ["data:", "data:text/html,x"],
    ["protocol-relative", "//evil.test"],
    ["userinfo", "https://app.example.test@evil.test"],
    ["query string", "https://app.example.test/?next=x"],
    ["fragment", "https://app.example.test/#x"],
    ["not a URL", "not a url"],
    ["empty", ""],
  ])("refuses a %s origin", (_l, value) => {
    expect(() => validatedAppOrigin(value)).toThrow(InvalidAppOriginError);
  });

  it("refuses plain HTTP in production", () => {
    const prior = process.env.NODE_ENV;
    // @ts-expect-error - overridden for this assertion only
    process.env.NODE_ENV = "production";
    try {
      expect(() => validatedAppOrigin("http://app.example.test")).toThrow(InvalidAppOriginError);
      expect(validatedAppOrigin("https://app.example.test").protocol).toBe("https:");
    } finally {
      // @ts-expect-error - restoring
      process.env.NODE_ENV = prior;
    }
  });

  it("allows localhost HTTP outside production, as an explicit dev exception", () => {
    expect(validatedAppOrigin("http://localhost:8501").protocol).toBe("http:");
  });
});

// ---------------------------------------------------------------------------
// Credential separation — the shortcut these exist to catch
// ---------------------------------------------------------------------------

describe("credential separation", () => {
  it("never puts the website cookie in the redirect URL", async () => {
    stubTransaction();
    const response = await post({ cookie: `tl_session=${COOKIE_VALUE}` });
    const location = response.headers.get("location")!;
    expect(location).not.toContain(COOKIE_VALUE);
    expect(new URL(location).searchParams.get("ht")).not.toBe(COOKIE_VALUE);
  });

  it("issues a handoff distinct from the cookie", async () => {
    const statements = stubTransaction();
    await post({ cookie: `tl_session=${COOKIE_VALUE}` });
    expect(JSON.stringify(statements)).not.toContain(COOKIE_VALUE);
    expect(JSON.stringify(statements)).not.toContain(
      createHash("sha256").update(COOKIE_VALUE, "utf8").digest("hex"));
  });

  it("takes a user id, so a session credential cannot be passed in by mistake", async () => {
    const raw = readFileSync(
      pathMod.resolve(__dirname, "..", "lib", "auth", "handoff.ts"), "utf8");
    // Comments are stripped: the docstring necessarily discusses the cookie
    // shortcut it exists to warn against, and that must not read as a
    // violation. Only executable lines are inspected.
    const code = raw
      .split("\n")
      .filter((l) => {
        const t = l.trim();
        return !(t.startsWith("*") || t.startsWith("/*") || t.startsWith("//") || t.startsWith("*/"));
      })
      .join("\n");
    expect(code).toContain("userId: number");
    expect(code).not.toMatch(/SESSION_COOKIE|sessionTokenFrom|cookie/i);
  });

  it("puts no identity in the URL at all", async () => {
    stubTransaction();
    const location = (await post({ cookie: "tl_session=x" })).headers.get("location")!;
    const url = new URL(location);
    // The meaningful assertion is the parameter set, not substring hunting: a
    // random 43-character base64url token contains almost any short string by
    // chance, so only distinctive multi-character values are checked.
    expect([...url.searchParams.keys()]).toEqual(["ht"]);
    expect(url.pathname).toBe("/");
    for (const leak of ["a@b.co", COOKIE_VALUE, "onboarding"]) {
      expect(url.search).not.toContain(leak);
    }
  });

  it("creates no Streamlit session row", async () => {
    const statements = stubTransaction();
    await post({ cookie: "tl_session=x" });
    expect(JSON.stringify(statements)).not.toContain("auth_sessions");
  });
});

// ---------------------------------------------------------------------------
// Route behaviour
// ---------------------------------------------------------------------------

describe("route", () => {
  it("redirects 303 on success", async () => {
    stubTransaction();
    const response = await post({ cookie: "tl_session=x" });
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toContain(`${APP}/?ht=`);
  });

  it("is no-store and no-referrer", async () => {
    stubTransaction();
    const response = await post({ cookie: "tl_session=x" });
    expect(response.headers.get("cache-control")).toContain("no-store");
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
  });

  it("refuses GET", async () => {
    const { GET } = await import("@/app/api/auth/handoff/route");
    const response = await GET();
    expect(response.status).toBe(405);
    expect(response.headers.get("allow")).toBe("POST");
    expect(runTransaction).not.toHaveBeenCalled();
  });

  it("rejects cross-origin", async () => {
    stubTransaction();
    const response = await post({ cookie: "tl_session=x", origin: "https://evil.com" });
    expect(response.status).toBe(403);
    expect(runTransaction).not.toHaveBeenCalled();
  });

  it.each([
    ["logged out", null, 401],
    ["unverified", { ...ELIGIBLE, emailVerificationRequired: true, emailVerifiedAt: null }, 403],
    ["onboarding incomplete", { ...ELIGIBLE, onboardingCompleted: false }, 403],
  ])("refuses %s without issuing", async (_l, user, status) => {
    authenticate.mockResolvedValue(user);
    stubTransaction();
    expect((await post({ cookie: "tl_session=x" })).status).toBe(status);
    expect(runTransaction).not.toHaveBeenCalled();
  });

  it("rejects an oversized body", async () => {
    stubTransaction();
    expect((await post({ cookie: "tl_session=x" }, "x".repeat(2000))).status).toBe(413);
    expect(runTransaction).not.toHaveBeenCalled();
  });

  it("rate limits without blocking an ordinary retry", async () => {
    isRateLimited.mockResolvedValue(true);
    stubTransaction();
    expect((await post({ cookie: "tl_session=x" })).status).toBe(429);
  });

  it("never logs the token or the destination", async () => {
    stubTransaction();
    await post({ cookie: `tl_session=${COOKIE_VALUE}` });
    const logged = JSON.stringify(logAuthEvent.mock.calls);
    expect(logged).not.toContain(COOKIE_VALUE);
    expect(logged).not.toContain("ht=");
    expect(logged).not.toContain(APP);
  });
});

describe("continue page", () => {
  it("does not issue on render", () => {
    const source = readFileSync(
      pathMod.resolve(__dirname, "..", "app", "continue", "page.tsx"), "utf8");
    expect(source).not.toContain("issueHandoff");
    // The button is a form POST, not a link or an effect.
    expect(source).toContain('method="POST"');
    expect(source).toContain('action="/api/auth/handoff"');
  });
});
