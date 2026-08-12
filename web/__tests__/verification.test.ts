import { beforeEach, describe, expect, it, vi } from "vitest";
import { createHash } from "node:crypto";

/**
 * Verification token service and the two routes.
 *
 * The database is stubbed with a small in-memory model so the *logic* — which
 * conditions gate a consume, what supersession does, what the routes disclose —
 * is tested exhaustively and fast. The real SQL, real atomicity and real
 * concurrency are covered by the dev-Neon integration script; these are two
 * different questions and neither substitutes for the other.
 */

const { runQuery, runTransaction } = vi.hoisted(() => ({
  runQuery: vi.fn(),
  runTransaction: vi.fn(),
}));

vi.mock("@/lib/db/client", () => ({
  query: runQuery,
  transaction: runTransaction,
}));

import {
  CaptureTransport,
  FailingTransport,
  SmtpTransport,
  verificationMessage,
} from "@/lib/mail/transport";
import {
  VERIFICATION_TTL_SECONDS,
  consumeVerification,
  inspectVerification,
  issueVerification,
  verificationUrl,
} from "@/lib/auth/verification";

const sha256 = (v: string) => createHash("sha256").update(v, "utf8").digest("hex");

beforeEach(() => {
  runQuery.mockReset().mockResolvedValue([]);
  runTransaction.mockReset();
  delete process.env.TRADELENS_SMTP_HOST;
  delete process.env.TRADELENS_SMTP_FROM;
});

// ---------------------------------------------------------------------------
// Token shape
// ---------------------------------------------------------------------------

describe("token", () => {
  it("is 256 bits, opaque, and carries no claims", async () => {
    const statements: { sql: string; params: unknown[] }[] = [];
    runTransaction.mockImplementation(async (fn: never) => {
      const run = async (sql: string, params: unknown[] = []) => {
        statements.push({ sql, params });
        return [];
      };
      return (fn as unknown as (r: typeof run) => Promise<unknown>)(run);
    });

    const { token } = await issueVerification(7, "person@example.com");

    expect(Buffer.from(token, "base64url").length).toBe(32);
    // Nothing recoverable from the token itself. Checking for a single
    // character would be meaningless — a random 43-character base64url string
    // contains almost any given character — so the assertions are structural:
    // the payload does not decode to anything, and multi-character identifying
    // fragments are absent.
    expect(token).not.toContain("person");
    expect(token).not.toContain("example.com");
    expect(() => JSON.parse(Buffer.from(token, "base64url").toString("utf8"))).toThrow();

    // Two tokens issued for the same account share nothing.
    const second = await issueVerification(7, "person@example.com");
    expect(second.token).not.toBe(token);
  });

  it("stores only the hash, never the raw token", async () => {
    const params: unknown[][] = [];
    runTransaction.mockImplementation(async (fn: never) => {
      const run = async (_sql: string, p: unknown[] = []) => {
        params.push(p);
        return [];
      };
      return (fn as unknown as (r: typeof run) => Promise<unknown>)(run);
    });

    const { token } = await issueVerification(7, "person@example.com");
    const flat = JSON.stringify(params);
    expect(flat).not.toContain(token);
    expect(flat).toContain(sha256(token));
  });

  it("expires 24 hours out", async () => {
    runTransaction.mockImplementation(async (fn: never) => {
      const run = async () => [];
      return (fn as unknown as (r: typeof run) => Promise<unknown>)(run);
    });
    expect(VERIFICATION_TTL_SECONDS).toBe(24 * 3600);

    const now = new Date("2026-08-11T10:00:00Z");
    const { expiresAt } = await issueVerification(7, "p@example.com", now);
    expect(expiresAt.toISOString()).toBe("2026-08-12T10:00:00.000Z");
  });

  it("supersedes outstanding tokens in the same transaction as the insert", async () => {
    const sqls: string[] = [];
    runTransaction.mockImplementation(async (fn: never) => {
      const run = async (sql: string) => {
        sqls.push(sql.replace(/\s+/g, " ").trim());
        return [];
      };
      return (fn as unknown as (r: typeof run) => Promise<unknown>)(run);
    });

    await issueVerification(7, "p@example.com");

    expect(sqls[0]).toMatch(/UPDATE email_verifications SET superseded_at/);
    expect(sqls[0]).toMatch(/consumed_at IS NULL AND superseded_at IS NULL/);
    expect(sqls[1]).toMatch(/INSERT INTO email_verifications/);
    // Both inside one transaction call — a racing resend cannot leave two live.
    expect(runTransaction).toHaveBeenCalledTimes(1);
  });

  it("builds a URL carrying the token exactly once", () => {
    const url = verificationUrl("https://site.test/", "abc-123");
    expect(url).toBe("https://site.test/verify-email?token=abc-123");
  });
});

// ---------------------------------------------------------------------------
// Inspect (GET) — must not mutate
// ---------------------------------------------------------------------------

describe("inspect", () => {
  it("issues a SELECT and never an UPDATE", async () => {
    runQuery.mockResolvedValue([{ ok: true }]);
    const result = await inspectVerification("tok");
    expect(result.status).toBe("valid");

    const sql = runQuery.mock.calls[0]![0] as string;
    expect(sql).toMatch(/^\s*SELECT/);
    expect(sql).not.toMatch(/UPDATE|INSERT|DELETE/i);
  });

  it("requires every gate, including the email match", async () => {
    runQuery.mockResolvedValue([{ ok: true }]);
    await inspectVerification("tok");
    const sql = (runQuery.mock.calls[0]![0] as string).replace(/\s+/g, " ");
    expect(sql).toContain("v.consumed_at IS NULL");
    expect(sql).toContain("v.superseded_at IS NULL");
    expect(sql).toContain("v.expires_at >");
    expect(sql).toContain("v.email = u.email");
  });

  it.each([null, undefined, "", 42, {}])("rejects the malformed token %j", async (t) => {
    expect((await inspectVerification(t)).status).toBe("rejected");
  });

  it("rejects when no row matches", async () => {
    runQuery.mockResolvedValue([]);
    expect((await inspectVerification("tok")).status).toBe("rejected");
  });
});

// ---------------------------------------------------------------------------
// Consume (POST)
// ---------------------------------------------------------------------------

function stubConsume(claimed: { user_id: number }[]) {
  const sqls: string[] = [];
  runTransaction.mockImplementation(async (fn: never) => {
    const run = async (sql: string) => {
      sqls.push(sql.replace(/\s+/g, " ").trim());
      return sqls.length === 1 ? claimed : [];
    };
    return (fn as unknown as (r: typeof run) => Promise<unknown>)(run);
  });
  return sqls;
}

describe("consume", () => {
  it("verifies and returns the user", async () => {
    stubConsume([{ user_id: 9 }]);
    expect(await consumeVerification("tok")).toEqual({ status: "verified", userId: 9 });
  });

  it("claims with one conditional UPDATE, not a read-then-write", async () => {
    const sqls = stubConsume([{ user_id: 9 }]);
    await consumeVerification("tok");
    expect(sqls[0]).toMatch(/^UPDATE email_verifications/);
    expect(sqls[0]).toContain("consumed_at IS NULL");
    expect(sqls[0]).toContain("superseded_at IS NULL");
    expect(sqls[0]).toContain("v.email = u.email");
  });

  it("sets both user flags in the same transaction", async () => {
    const sqls = stubConsume([{ user_id: 9 }]);
    await consumeVerification("tok");
    expect(sqls[1]).toContain("UPDATE users");
    expect(sqls[1]).toContain("email_verified_at");
    expect(sqls[1]).toContain("email_verification_required = false");
    expect(runTransaction).toHaveBeenCalledTimes(1);
  });

  it("leaves onboarding and strategy-profile state alone", async () => {
    const sqls = stubConsume([{ user_id: 9 }]);
    await consumeVerification("tok");
    const all = sqls.join(" ");
    expect(all).not.toContain("onboarding_completed");
    expect(all).not.toContain("strategy_profile_completed");
  });

  it("rejects when the conditional UPDATE claims nothing", async () => {
    // Covers expired, already-consumed, superseded, unknown, and an email that
    // no longer matches — all indistinguishable, by design.
    stubConsume([]);
    expect(await consumeVerification("tok")).toEqual({ status: "rejected" });
  });

  it.each([null, undefined, "", 42])("rejects the malformed token %j", async (t) => {
    expect(await consumeVerification(t)).toEqual({ status: "rejected" });
  });

  it("hashes the token before it reaches the query", async () => {
    const params: unknown[] = [];
    runTransaction.mockImplementation(async (fn: never) => {
      const run = async (_s: string, p: unknown[] = []) => {
        params.push(...p);
        return [{ user_id: 1 }];
      };
      return (fn as unknown as (r: typeof run) => Promise<unknown>)(run);
    });
    await consumeVerification("raw-token-value");
    expect(params).toContain(sha256("raw-token-value"));
    expect(params).not.toContain("raw-token-value");
  });
});

// ---------------------------------------------------------------------------
// Mail transport
// ---------------------------------------------------------------------------

describe("mail transport", () => {
  it("reports unavailable when SMTP is unconfigured, not sent", async () => {
    const outcome = await new SmtpTransport().send({ to: "a@b.co", subject: "s", text: "t" });
    expect(outcome).toEqual({ status: "unavailable", reason: "not_configured" });
  });

  it("reports failed, never a fabricated sent, when configured but broken", async () => {
    process.env.TRADELENS_SMTP_HOST = "smtp.example.com";
    process.env.TRADELENS_SMTP_FROM = "TradeLens <no-reply@example.com>";
    const outcome = await new SmtpTransport().send({ to: "a@b.co", subject: "s", text: "t" });
    expect(outcome.status).toBe("failed");
  });

  it("distinguishes all three delivery states", async () => {
    expect((await new CaptureTransport().send({ to: "a@b.co", subject: "s", text: "t" })).status).toBe("sent");
    expect((await new FailingTransport().send({ to: "a@b.co", subject: "s", text: "t" })).status).toBe("failed");
    expect((await new SmtpTransport().send({ to: "a@b.co", subject: "s", text: "t" })).status).toBe("unavailable");
  });

  it("lets a test read the verification URL it would have emailed", async () => {
    const capture = new CaptureTransport();
    const url = verificationUrl("https://site.test", "tok-abc");
    await capture.send(verificationMessage("a@b.co", url));
    expect(capture.lastVerificationUrl()).toBe(url);
  });

  it("puts the URL in the body exactly once and states the expiry", () => {
    const url = verificationUrl("https://site.test", "tok-abc");
    const message = verificationMessage("a@b.co", url);
    expect(message.text.split(url).length - 1).toBe(1);
    expect(message.text).toContain("24 hours");
  });
});
