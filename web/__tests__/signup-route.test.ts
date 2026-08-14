import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Behaviour of POST /api/auth/signup.
 *
 * The database, rate limiter and account creation are stubbed so these run
 * fast and deterministically; the real database path is exercised separately by
 * the dev-Neon integration script. What is tested here is the endpoint's own
 * logic: validation, gating, enumeration behaviour, and what it does and does
 * not put in a response.
 */

// vi.hoisted so the mock factories can reference these directly, rather than
// wrapping them in spread forwarders that TypeScript cannot type.
const { createAccount, recordAttempt, isRateLimited, logAuthEvent } = vi.hoisted(
  () => ({
    createAccount: vi.fn(),
    recordAttempt: vi.fn(),
    isRateLimited: vi.fn(),
    logAuthEvent: vi.fn(),
  }),
);

vi.mock("@/lib/auth/signup", () => ({ createAccount, BCRYPT_COST: 12 }));

vi.mock("@/lib/auth/rate-limit", () => ({
  recordAttempt,
  isRateLimited,
  bucketFor: async (kind: string, value: string) => `${kind}:hashed(${value.length})`,
  clientIp: () => "203.0.113.7",
}));

vi.mock("@/lib/security/responses", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/security/responses")>();
  return { ...actual, logAuthEvent };
});

const VALID = {
  email: "New.Person@Example.COM",
  password: "Correct-Horse-Battery-9!",
  fullName: "New Person",
  birthday: "1994-02-17",
  referralSource: "Reddit",
  referralOther: null,
};

function post(body: unknown, headers: Record<string, string> = {}) {
  return new Request("https://site.test/api/auth/signup", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      origin: "https://site.test",
      ...headers,
    },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

async function callRoute(request: Request) {
  const { POST } = await import("@/app/api/auth/signup/route");
  return POST(request);
}

beforeEach(() => {
  vi.resetModules();
  createAccount.mockReset().mockResolvedValue({ status: "created", userId: 42 });
  recordAttempt.mockReset();
  isRateLimited.mockReset().mockResolvedValue(false);
  logAuthEvent.mockReset();
  process.env.SITE_ORIGIN = "https://site.test";
  process.env.SIGNUP_MODE = "open";
  delete process.env.TRADELENS_INVITE_CODE;
});

describe("valid signup", () => {
  it("creates the account and requires verification", async () => {
    const response = await callRoute(post(VALID));
    expect(response.status).toBe(201);
    const body = await response.json();
    expect(body.ok).toBe(true);
    expect(body.verificationRequired).toBe(true);
  });

  it("normalizes the email before creating", async () => {
    await callRoute(post(VALID));
    expect(createAccount).toHaveBeenCalledWith(
      expect.objectContaining({ email: "new.person@example.com" }),
    );
  });

  it("never claims an email was sent, because none was", async () => {
    // Which non-sent state this lands in depends on the database double, so
    // the assertion is the property that matters rather than the label: the
    // route must never report "sent" when nothing was delivered. The three
    // states are told apart from each other in __tests__/mail.test.ts.
    const body = await (await callRoute(post(VALID))).json();
    expect(body.emailDelivery).not.toBe("sent");
    expect(["unavailable", "failed"]).toContain(body.emailDelivery);
    expect(JSON.stringify(body).toLowerCase()).not.toMatch(
      /check your inbox|we sent|on its way|email sent/,
    );
  });

  it("returns no internal identifiers", async () => {
    const raw = JSON.stringify(await (await callRoute(post(VALID))).json());
    expect(raw).not.toContain("42");        // the user id
    expect(raw).not.toContain("u_");        // the opaque username
    expect(raw.toLowerCase()).not.toContain("hash");
  });
});

describe("duplicate email", () => {
  it("is refused without revealing anything about the existing account", async () => {
    createAccount.mockResolvedValue({ status: "duplicate_email" });
    const response = await callRoute(post(VALID));
    expect(response.status).toBe(409);
    const message = (await response.json()).error.toLowerCase();
    // Says an account exists; says nothing about legacy, verified, or unverified.
    expect(message).toContain("already exists");
    for (const leak of ["legacy", "verified", "unverified", "username", "id"]) {
      expect(message).not.toContain(`${leak} `);
    }
  });
});

describe("validation", () => {
  it.each([
    ["malformed email", { ...VALID, email: "not-an-email" }],
    ["missing email", { ...VALID, email: undefined }],
    ["malformed birthday", { ...VALID, birthday: "2026-02-31" }],
    ["future birthday", { ...VALID, birthday: "2099-01-01" }],
    ["unknown referral", { ...VALID, referralSource: "MySpace" }],
    ["referralOther without Other", { ...VALID, referralOther: "a discord" }],
    ["empty full name", { ...VALID, fullName: "   " }],
    ["oversized full name", { ...VALID, fullName: "x".repeat(200) }],
  ])("rejects %s", async (_label, body) => {
    const response = await callRoute(post(body));
    expect(response.status).toBe(400);
    expect(createAccount).not.toHaveBeenCalled();
  });

  it.each([
    "short1!A",
    "alllowercase1!",
    "ALLUPPERCASE1!",
    "NoDigitsHere!!",
    "NoSymbolsHere1",
  ])("rejects the weak password %s", async (password) => {
    const response = await callRoute(post({ ...VALID, password }));
    expect(response.status).toBe(400);
    // The message states the same four rules the strength meter displays.
    expect((await response.json()).error).toMatch(/12 characters/);
    expect(createAccount).not.toHaveBeenCalled();
  });

  it("rejects a non-object body", async () => {
    expect((await callRoute(post("[1,2,3]"))).status).toBe(400);
  });

  it("rejects unparseable JSON", async () => {
    expect((await callRoute(post("{not json"))).status).toBe(400);
  });

  it("rejects a body over the size limit", async () => {
    const huge = { ...VALID, fullName: "x".repeat(20_000) };
    expect((await callRoute(post(huge))).status).toBe(413);
  });

  it("rejects a wrong content type", async () => {
    const request = new Request("https://site.test/api/auth/signup", {
      method: "POST",
      headers: { "content-type": "text/plain", origin: "https://site.test" },
      body: JSON.stringify(VALID),
    });
    expect((await callRoute(request)).status).toBe(415);
  });
});

describe("CSRF / origin", () => {
  it("rejects a cross-origin post", async () => {
    const response = await callRoute(post(VALID, { origin: "https://evil.com" }));
    expect(response.status).toBe(403);
    expect(createAccount).not.toHaveBeenCalled();
  });

  it("rejects a post carrying neither Origin nor Referer", async () => {
    const request = new Request("https://site.test/api/auth/signup", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(VALID),
    });
    expect((await callRoute(request)).status).toBe(403);
  });
});

describe("signup mode", () => {
  it("refuses everything when closed", async () => {
    process.env.SIGNUP_MODE = "closed";
    expect((await callRoute(post(VALID))).status).toBe(403);
    expect(createAccount).not.toHaveBeenCalled();
  });

  it("fails shut on an unrecognised mode", async () => {
    process.env.SIGNUP_MODE = "banana";
    expect((await callRoute(post(VALID))).status).toBe(403);
  });

  it("requires a matching invite when invite-gated", async () => {
    process.env.SIGNUP_MODE = "invite";
    process.env.TRADELENS_INVITE_CODE = "let-me-in-2026";

    expect((await callRoute(post({ ...VALID, invite: "wrong" }))).status).toBe(403);
    expect(createAccount).not.toHaveBeenCalled();

    const ok = await callRoute(post({ ...VALID, invite: "let-me-in-2026" }));
    expect(ok.status).toBe(201);
  });

  it("never returns the configured invite code", async () => {
    process.env.SIGNUP_MODE = "invite";
    process.env.TRADELENS_INVITE_CODE = "let-me-in-2026";
    const raw = JSON.stringify(
      await (await callRoute(post({ ...VALID, invite: "wrong" }))).json(),
    );
    expect(raw).not.toContain("let-me-in-2026");
  });

  it("needs no invite when open", async () => {
    process.env.SIGNUP_MODE = "open";
    expect((await callRoute(post(VALID))).status).toBe(201);
  });
});

describe("rate limiting", () => {
  it("refuses when the IP bucket is over its limit", async () => {
    isRateLimited.mockResolvedValue(true);
    const response = await callRoute(post(VALID));
    expect(response.status).toBe(429);
    expect(createAccount).not.toHaveBeenCalled();
  });

  it("records the attempt outcome", async () => {
    await callRoute(post(VALID));
    expect(recordAttempt).toHaveBeenCalledWith(
      expect.any(String),
      "signup",
      true,
    );
  });
});

describe("logging", () => {
  it("never logs the password, the email, or the invite code", async () => {
    process.env.SIGNUP_MODE = "invite";
    process.env.TRADELENS_INVITE_CODE = "let-me-in-2026";
    await callRoute(post({ ...VALID, invite: "wrong" }));
    const logged = JSON.stringify(logAuthEvent.mock.calls);
    expect(logged).not.toContain(VALID.password);
    expect(logged).not.toContain("let-me-in-2026");
    expect(logged.toLowerCase()).not.toContain("new.person@example.com");
  });
});

describe("server errors", () => {
  it("returns nothing from the driver when creation throws", async () => {
    createAccount.mockRejectedValue(
      new Error('duplicate key value violates unique constraint "ix_users_email" DETAIL: postgres://user:pw@host/db'),
    );
    const response = await callRoute(post(VALID));
    expect(response.status).toBe(500);
    const raw = JSON.stringify(await response.json());
    for (const leak of ["postgres://", "ix_users_email", "constraint", "DETAIL"]) {
      expect(raw).not.toContain(leak);
    }
  });
});
