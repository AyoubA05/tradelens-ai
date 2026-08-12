import { beforeEach, describe, expect, it, vi } from "vitest";
import { createHash } from "node:crypto";

/**
 * Reset-token service and both routes.
 *
 * Database calls are stubbed so the endpoint logic — enumeration, gating, what
 * is disclosed, what is logged — is exercised exhaustively and fast. Real SQL,
 * real atomicity, real session revocation and real concurrency are covered by
 * the dev-Neon integration script; neither substitutes for the other.
 */

const { runQuery, runTransaction, sendMail, recordAttempt, isRateLimited, logAuthEvent } =
  vi.hoisted(() => ({
    runQuery: vi.fn(),
    runTransaction: vi.fn(),
    sendMail: vi.fn(),
    recordAttempt: vi.fn(),
    isRateLimited: vi.fn(),
    logAuthEvent: vi.fn(),
  }));

vi.mock("@/lib/db/client", () => ({ query: runQuery, transaction: runTransaction }));
vi.mock("@/lib/mail/transport", () => ({
  mailTransport: () => ({ send: sendMail }),
}));
vi.mock("@/lib/auth/rate-limit", () => ({
  recordAttempt,
  isRateLimited,
  clearFailures: vi.fn(),
  bucketFor: async (k: string, v: string) => `${k}:hashed(${v.length})`,
  clientIp: () => "203.0.113.7",
}));
vi.mock("@/lib/security/responses", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/security/responses")>();
  return { ...actual, logAuthEvent };
});

import {
  RESET_TTL_SECONDS,
  inspectReset,
  issueReset,
  passwordHashFingerprint,
  resetEligibility,
  resetUrl,
} from "@/lib/auth/password-reset";

const sha256 = (v: string) => createHash("sha256").update(v, "utf8").digest("hex");
const HASH = "$2b$12$abcdefghijklmnopqrstuv";

beforeEach(() => {
  vi.resetModules();
  runQuery.mockReset().mockResolvedValue([]);
  runTransaction.mockReset();
  sendMail.mockReset().mockResolvedValue({ status: "unavailable", reason: "not_configured" });
  recordAttempt.mockReset();
  isRateLimited.mockReset().mockResolvedValue(false);
  logAuthEvent.mockReset();
  process.env.SITE_ORIGIN = "https://site.test";
});

// ---------------------------------------------------------------------------
// Token and fingerprint
// ---------------------------------------------------------------------------

function stubTransaction(results: unknown[][] = []) {
  const sqls: string[] = [];
  let i = 0;
  runTransaction.mockImplementation(async (fn: never) => {
    const run = async (sql: string, _p?: unknown[]) => {
      sqls.push(sql.replace(/\s+/g, " ").trim());
      return results[i++] ?? [];
    };
    return (fn as unknown as (r: typeof run) => Promise<unknown>)(run);
  });
  return sqls;
}

describe("reset token", () => {
  it("is 256 bits and opaque", async () => {
    stubTransaction();
    const { token } = await issueReset(1, "a@b.co", HASH);
    expect(Buffer.from(token, "base64url").length).toBe(32);
    expect(token).not.toContain("a@b.co");
    expect(() => JSON.parse(Buffer.from(token, "base64url").toString("utf8"))).toThrow();
  });

  it("lives 30 minutes, not the verification token's 24 hours", async () => {
    stubTransaction();
    expect(RESET_TTL_SECONDS).toBe(30 * 60);
    const now = new Date("2026-08-12T10:00:00Z");
    const { expiresAt } = await issueReset(1, "a@b.co", HASH, now);
    expect(expiresAt.toISOString()).toBe("2026-08-12T10:30:00.000Z");
  });

  it("stores only hashes, never the token, password hash, or password", async () => {
    const params: unknown[] = [];
    runTransaction.mockImplementation(async (fn: never) => {
      const run = async (_s: string, p: unknown[] = []) => { params.push(...p); return []; };
      return (fn as unknown as (r: typeof run) => Promise<unknown>)(run);
    });
    const { token } = await issueReset(1, "a@b.co", HASH);
    const flat = JSON.stringify(params);
    expect(flat).not.toContain(token);
    expect(flat).not.toContain(HASH);
    expect(flat).toContain(sha256(token));
    expect(flat).toContain(sha256(HASH));
  });

  it("supersedes prior tokens in the same transaction as the insert", async () => {
    const sqls = stubTransaction();
    await issueReset(1, "a@b.co", HASH);
    expect(sqls[0]).toMatch(/UPDATE password_resets SET superseded_at/);
    expect(sqls[1]).toMatch(/INSERT INTO password_resets/);
    expect(runTransaction).toHaveBeenCalledTimes(1);
  });
});

describe("password hash fingerprint", () => {
  it("is SHA-256 hex of the exact hash string", () => {
    expect(passwordHashFingerprint(HASH)).toBe(sha256(HASH));
    expect(passwordHashFingerprint(HASH)).toMatch(/^[0-9a-f]{64}$/);
  });

  it("changes when the hash changes", () => {
    expect(passwordHashFingerprint(HASH)).not.toBe(passwordHashFingerprint(HASH + "x"));
  });

  it("is not reversible to the hash", () => {
    expect(passwordHashFingerprint(HASH)).not.toContain("$2b$");
  });
});

// ---------------------------------------------------------------------------
// Eligibility
// ---------------------------------------------------------------------------

describe("eligibility", () => {
  it("requires a verified, active, non-pending account", async () => {
    runQuery.mockResolvedValue([]);
    expect((await resetEligibility("a@b.co")).eligible).toBe(false);
    const sql = (runQuery.mock.calls[0]![0] as string).replace(/\s+/g, " ");
    expect(sql).toContain("email_verified_at IS NOT NULL");
    expect(sql).toContain("email_verification_required = false");
    expect(sql).toContain("is_active = 1");
  });

  it("returns the account when eligible", async () => {
    runQuery.mockResolvedValue([{ id: 9, email: "a@b.co", password_hash: HASH }]);
    const e = await resetEligibility("a@b.co");
    expect(e).toEqual({ eligible: true, userId: 9, email: "a@b.co", passwordHash: HASH });
  });
});

// ---------------------------------------------------------------------------
// Scanner-safe inspection
// ---------------------------------------------------------------------------

describe("inspect", () => {
  it("issues a SELECT and never mutates", async () => {
    runQuery.mockResolvedValue([{ fingerprint: sha256(HASH), current_hash: HASH }]);
    expect((await inspectReset("tok")).status).toBe("valid");
    const sql = runQuery.mock.calls[0]![0] as string;
    expect(sql.trimStart()).toMatch(/^SELECT/);
    expect(sql).not.toMatch(/UPDATE|INSERT|DELETE/i);
  });

  it("checks every live condition", async () => {
    runQuery.mockResolvedValue([{ fingerprint: sha256(HASH), current_hash: HASH }]);
    await inspectReset("tok");
    const sql = (runQuery.mock.calls[0]![0] as string).replace(/\s+/g, " ");
    for (const c of [
      "r.consumed_at IS NULL",
      "r.superseded_at IS NULL",
      "r.expires_at >",
      "r.email = u.email",
      "u.email_verified_at IS NOT NULL",
      "u.email_verification_required = false",
    ]) expect(sql).toContain(c);
  });

  it("rejects when the password changed since issuance", async () => {
    runQuery.mockResolvedValue([{ fingerprint: sha256(HASH), current_hash: HASH + "changed" }]);
    expect((await inspectReset("tok")).status).toBe("rejected");
  });

  it.each([null, undefined, "", 42])("rejects the malformed token %j", async (t) => {
    expect((await inspectReset(t)).status).toBe("rejected");
  });
});

// ---------------------------------------------------------------------------
// Forgot endpoint
// ---------------------------------------------------------------------------

function forgot(body: unknown, headers: Record<string, string> = {}) {
  return new Request("https://site.test/api/auth/forgot-password", {
    method: "POST",
    headers: { "content-type": "application/json", origin: "https://site.test", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}
const callForgot = async (r: Request) =>
  (await import("@/app/api/auth/forgot-password/route")).POST(r);

describe("forgot-password enumeration", () => {
  it("returns one identical response for every case", async () => {
    const bodies: string[] = [];
    const statuses: number[] = [];

    // unknown / unverified / legacy-without-email all produce no eligible row
    runQuery.mockResolvedValue([]);
    for (const email of ["nobody@example.com", "unverified@example.com", "legacy@example.com"]) {
      const r = await callForgot(forgot({ email }));
      statuses.push(r.status);
      bodies.push(JSON.stringify(await r.json()));
    }

    // eligible verified account
    runQuery.mockResolvedValue([{ id: 9, email: "real@example.com", password_hash: HASH }]);
    stubTransaction();
    const ok = await callForgot(forgot({ email: "real@example.com" }));
    statuses.push(ok.status);
    bodies.push(JSON.stringify(await ok.json()));

    // malformed
    runQuery.mockResolvedValue([]);
    const bad = await callForgot(forgot({ email: "not-an-email" }));
    statuses.push(bad.status);
    bodies.push(JSON.stringify(await bad.json()));

    // rate limited
    isRateLimited.mockResolvedValue(true);
    const limited = await callForgot(forgot({ email: "real@example.com" }));
    statuses.push(limited.status);
    bodies.push(JSON.stringify(await limited.json()));

    expect(new Set(bodies).size).toBe(1);
    expect(new Set(statuses)).toEqual(new Set([200]));
  });

  it("never returns the raw token or the reset URL", async () => {
    runQuery.mockResolvedValue([{ id: 9, email: "real@example.com", password_hash: HASH }]);
    stubTransaction();
    const body = JSON.stringify(await (await callForgot(forgot({ email: "real@example.com" }))).json());
    expect(body).not.toContain("reset-password?token=");
    expect(body).not.toContain(HASH);
    expect(body.toLowerCase()).not.toContain("fingerprint");
  });

  it("never logs the email, token, or hash", async () => {
    runQuery.mockResolvedValue([{ id: 9, email: "real@example.com", password_hash: HASH }]);
    stubTransaction();
    await callForgot(forgot({ email: "real@example.com" }));
    const logged = JSON.stringify(logAuthEvent.mock.calls);
    expect(logged).not.toContain("real@example.com");
    expect(logged).not.toContain(HASH);
  });

  it("rejects a cross-origin post", async () => {
    expect((await callForgot(forgot({ email: "a@b.co" }, { origin: "https://evil.com" }))).status).toBe(403);
  });

  it.each([
    ["unavailable", { status: "unavailable", reason: "not_configured" }],
    ["failed", { status: "failed" }],
    ["sent", { status: "sent" }],
  ])("responds identically when delivery is %s", async (_l, outcome) => {
    runQuery.mockResolvedValue([{ id: 9, email: "real@example.com", password_hash: HASH }]);
    stubTransaction();
    sendMail.mockResolvedValue(outcome);
    const r = await callForgot(forgot({ email: "real@example.com" }));
    expect(r.status).toBe(200);
    expect((await r.json()).message).toMatch(/if an eligible account exists/i);
  });
});

// ---------------------------------------------------------------------------
// Reset endpoint
// ---------------------------------------------------------------------------

const callResetGet = async (url: string) =>
  (await import("@/app/api/auth/reset-password/route")).GET(new Request(url));
const callResetPost = async (body: unknown, headers: Record<string, string> = {}) =>
  (await import("@/app/api/auth/reset-password/route")).POST(
    new Request("https://site.test/api/auth/reset-password", {
      method: "POST",
      headers: { "content-type": "application/json", origin: "https://site.test", ...headers },
      body: JSON.stringify(body),
    }),
  );

const STRONG = "Correct-Horse-Battery-9!";

describe("reset endpoint", () => {
  it("GET does not consume", async () => {
    runQuery.mockResolvedValue([{ fingerprint: sha256(HASH), current_hash: HASH }]);
    const r = await callResetGet("https://site.test/api/auth/reset-password?token=tok");
    expect(r.status).toBe(200);
    expect(runTransaction).not.toHaveBeenCalled();
    for (const call of runQuery.mock.calls) {
      expect(call[0] as string).not.toMatch(/UPDATE|INSERT|DELETE/i);
    }
  });

  it("enforces the same password policy as signup", async () => {
    for (const weak of ["short1!A", "alllowercase1!", "ALLUPPERCASE1!", "NoDigitsHere!!", "NoSymbolsHere1"]) {
      const r = await callResetPost({ token: "tok", password: weak });
      expect(r.status).toBe(400);
      expect((await r.json()).error).toMatch(/12 characters/);
    }
    expect(runTransaction).not.toHaveBeenCalled();
  });

  it("rejects an invalid token without disclosing why", async () => {
    stubTransaction([[]]);
    const r = await callResetPost({ token: "tok", password: STRONG });
    expect(r.status).toBe(400);
    expect((await r.json()).error).toMatch(/no longer valid/i);
  });

  it("revokes sessions and voids handoffs on success", async () => {
    const sqls = stubTransaction([
      [{ id: 5, user_id: 9, fingerprint: sha256(HASH), current_hash: HASH }], // candidate
      [{ id: 5 }],            // claim
      [],                     // users update
      [],                     // supersede others
      [{ id: 1 }, { id: 2 }], // sessions revoked
      [{ id: 3 }],            // handoffs voided
    ]);
    const r = await callResetPost({ token: "tok", password: STRONG });
    expect(r.status).toBe(200);
    const joined = sqls.join(" ");
    expect(joined).toContain("UPDATE users SET password_hash");
    expect(joined).toContain("UPDATE auth_sessions SET revoked_at");
    expect(joined).toContain("UPDATE auth_handoffs SET consumed_at");
    // Every statement in one transaction: no consumed token with an unchanged
    // password, and no changed password with a reusable token.
    expect(runTransaction).toHaveBeenCalledTimes(1);
  });

  it("scopes revocation to the one user", async () => {
    const sqls = stubTransaction([
      [{ id: 5, user_id: 9, fingerprint: sha256(HASH), current_hash: HASH }],
      [{ id: 5 }], [], [], [], [],
    ]);
    await callResetPost({ token: "tok", password: STRONG });
    for (const sql of sqls.filter((s) => s.includes("auth_sessions") || s.includes("auth_handoffs"))) {
      expect(sql).toContain("user_id = $1");
    }
  });

  it("rejects when the password changed since issuance", async () => {
    stubTransaction([[{ id: 5, user_id: 9, fingerprint: sha256(HASH), current_hash: HASH + "changed" }]]);
    expect((await callResetPost({ token: "tok", password: STRONG })).status).toBe(400);
  });

  it("does not sign the user in", async () => {
    stubTransaction([
      [{ id: 5, user_id: 9, fingerprint: sha256(HASH), current_hash: HASH }],
      [{ id: 5 }], [], [], [], [],
    ]);
    const r = await callResetPost({ token: "tok", password: STRONG });
    expect(r.headers.get("set-cookie")).toBeNull();
    expect((await r.json()).next).toBe("/login");
  });

  it("never logs the token, password, or hash", async () => {
    stubTransaction([
      [{ id: 5, user_id: 9, fingerprint: sha256(HASH), current_hash: HASH }],
      [{ id: 5 }], [], [], [], [],
    ]);
    await callResetPost({ token: "secret-token", password: STRONG });
    const logged = JSON.stringify(logAuthEvent.mock.calls);
    expect(logged).not.toContain("secret-token");
    expect(logged).not.toContain(STRONG);
    expect(logged).not.toContain(HASH);
  });

  it("rejects cross-origin and rate-limited posts", async () => {
    expect((await callResetPost({ token: "t", password: STRONG }, { origin: "https://evil.com" })).status).toBe(403);
    isRateLimited.mockResolvedValue(true);
    expect((await callResetPost({ token: "t", password: STRONG })).status).toBe(429);
  });
});

describe("reset URL", () => {
  it("carries the token once", () => {
    expect(resetUrl("https://site.test/", "abc")).toBe("https://site.test/reset-password?token=abc");
  });
});
