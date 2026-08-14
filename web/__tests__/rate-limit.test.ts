import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The rate limiter's own behaviour, with the database faked at the query layer.
 *
 * Every route suite mocks this module out, so until now nothing exercised the
 * limiter itself — which is how a retention sweep that no caller ever invoked
 * survived under a comment claiming no scheduled job was needed.
 */

const { runQuery } = vi.hoisted(() => ({ runQuery: vi.fn() }));

vi.mock("@/lib/db/client", () => ({
  query: runQuery,
  transaction: vi.fn(),
}));

import {
  RULES,
  bucketFor,
  clientIp,
  isRateLimited,
  recordAttempt,
  sweepOldAttempts,
} from "@/lib/auth/rate-limit";

function headers(map: Record<string, string>) {
  return { get: (name: string) => map[name.toLowerCase()] ?? null };
}

beforeEach(() => {
  runQuery.mockReset().mockResolvedValue([{ n: "0" }]);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("bucket keys", () => {
  it("hashes identifiers so the table is not a list of everyone's email", async () => {
    const bucket = await bucketFor("id", "Someone@Example.com");
    expect(bucket.startsWith("id:")).toBe(true);
    expect(bucket).not.toContain("someone");
    expect(bucket).not.toContain("example.com");
  });

  it("buckets an identifier case-insensitively", async () => {
    expect(await bucketFor("id", "A@B.co")).toBe(await bucketFor("id", "a@b.co"));
  });

  it("keeps IP buckets readable, since an IP is not personal data to hide here", async () => {
    expect(await bucketFor("ip", "203.0.113.7")).toBe("ip:203.0.113.7");
  });
});

describe("client IP", () => {
  it("takes the first hop of x-forwarded-for", () => {
    expect(clientIp(headers({ "x-forwarded-for": "203.0.113.7, 10.0.0.1" }))).toBe(
      "203.0.113.7",
    );
  });

  it("falls back to a shared constant, never to something attacker-supplied", () => {
    // A fresh bucket per unknown request would be unlimited attempts.
    expect(clientIp(headers({}))).toBe("unknown");
  });
});

describe("limits", () => {
  it("refuses once the count reaches the limit", async () => {
    runQuery.mockResolvedValueOnce([{ n: String(RULES["login:ip"].limit) }]);
    expect(await isRateLimited("ip:1.2.3.4", "login", "login:ip")).toBe(true);
  });

  it("allows one below the limit", async () => {
    runQuery.mockResolvedValueOnce([{ n: String(RULES["login:ip"].limit - 1) }]);
    expect(await isRateLimited("ip:1.2.3.4", "login", "login:ip")).toBe(false);
  });

  it("refuses nothing for an unknown rule, so the mistake is visible", async () => {
    expect(await isRateLimited("ip:1.2.3.4", "login", "no-such-rule")).toBe(false);
    expect(runQuery).not.toHaveBeenCalled();
  });

  it("counts failures only where locking an account out would otherwise be free", () => {
    // A per-identifier limit that counted successes lets anyone lock a known
    // account by burning its quota.
    expect(RULES["login:id"].failuresOnly).toBe(true);
    expect(RULES["signup:id"].failuresOnly).toBe(true);
  });

  it("keys the verification limit to the bucket it is actually applied to", () => {
    // It was `verify:id` while being handed an IP bucket. A real per-identifier
    // limit here would let anyone stop an address from being confirmed.
    expect(RULES["verify:ip"]).toBeDefined();
    expect(RULES["verify:id"]).toBeUndefined();
  });
});

describe("retention", () => {
  it("deletes rows past the window", async () => {
    await sweepOldAttempts();
    const sql = runQuery.mock.calls[0][0] as string;
    expect(sql).toMatch(/DELETE FROM auth_attempts/i);
    expect(sql).toMatch(/30 days/);
  });

  it("is actually reached from recordAttempt", async () => {
    // The defect this pins: the sweep existed and nothing called it, so the
    // table had no retention at all.
    vi.spyOn(Math, "random").mockReturnValue(0);
    await recordAttempt("ip:1.2.3.4", "login", false);

    const statements = runQuery.mock.calls.map((call) => String(call[0]));
    expect(statements.some((sql) => /INSERT INTO auth_attempts/i.test(sql))).toBe(true);
    expect(statements.some((sql) => /DELETE FROM auth_attempts/i.test(sql))).toBe(true);
  });

  it("does not sweep on a typical write", async () => {
    vi.spyOn(Math, "random").mockReturnValue(0.9);
    await recordAttempt("ip:1.2.3.4", "login", false);
    expect(runQuery).toHaveBeenCalledTimes(1);
  });

  it("never lets a failed sweep break the request it rode in on", async () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    runQuery
      .mockResolvedValueOnce([])
      .mockRejectedValueOnce(new Error("delete blew up"));
    await expect(recordAttempt("ip:1.2.3.4", "login", true)).resolves.toBeUndefined();
  });
});
