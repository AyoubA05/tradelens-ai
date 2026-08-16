import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * POST /api/auth/login.
 *
 * The credential check and session store are stubbed so the endpoint's own
 * behaviour — enumeration, rate limiting, cookie attributes, what it discloses
 * — is tested exhaustively. Real bcrypt, real case-sensitivity and the real
 * session row are covered by the dev-Neon integration script.
 */

const { attemptLogin, openWebsiteSession, recordAttempt, isRateLimited, clearFailures, logAuthEvent } =
  vi.hoisted(() => ({
    attemptLogin: vi.fn(),
    openWebsiteSession: vi.fn(),
    recordAttempt: vi.fn(),
    isRateLimited: vi.fn(),
    clearFailures: vi.fn(),
    logAuthEvent: vi.fn(),
  }));

vi.mock("@/lib/auth/login", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/auth/login")>();
  return { ...actual, attemptLogin, openWebsiteSession };
});

vi.mock("@/lib/auth/rate-limit", () => ({
  recordAttempt,
  isRateLimited,
  clearFailures,
  bucketFor: async (kind: string, value: string) => `${kind}:hashed(${value.length})`,
  clientIp: () => "203.0.113.7",
}));

vi.mock("@/lib/security/responses", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/security/responses")>();
  return { ...actual, logAuthEvent };
});

function post(body: unknown, headers: Record<string, string> = {}) {
  return new Request("https://site.test/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json", origin: "https://site.test", ...headers },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

async function call(request: Request) {
  const { POST } = await import("@/app/api/auth/login/route");
  return POST(request);
}

const GOOD = { identifier: "ayoub", password: "Correct-Horse-Battery-9!" };

beforeEach(() => {
  vi.resetModules();
  attemptLogin.mockReset().mockResolvedValue({
    ok: true,
    userId: 3,
    onboardingCompleted: true,
    strategyProfileCompleted: false,
  });
  openWebsiteSession.mockReset().mockResolvedValue({
    token: "session-token-value",
    expiresAt: new Date(Date.now() + 12 * 3600_000),
  });
  recordAttempt.mockReset();
  isRateLimited.mockReset().mockResolvedValue(false);
  clearFailures.mockReset();
  logAuthEvent.mockReset();
  process.env.SITE_ORIGIN = "https://site.test";
});

describe("successful login", () => {
  it("returns ok and a next destination", async () => {
    const response = await call(post(GOOD));
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body.ok).toBe(true);
    expect(body.next).toBe("/continue");
  });

  it("retains personal onboarding as a fallback for an actually incomplete account", async () => {
    attemptLogin.mockResolvedValue({
      ok: true,
      userId: 9,
      onboardingCompleted: false,
      strategyProfileCompleted: false,
    });
    const response = await call(post(GOOD));
    expect((await response.json()).next).toBe("/onboarding");
  });

  it("sets an HttpOnly, Secure, SameSite=Lax cookie", async () => {
    const response = await call(post(GOOD));
    const cookie = response.headers.get("set-cookie") ?? "";
    expect(cookie).toContain("tl_session=");
    expect(cookie.toLowerCase()).toContain("httponly");
    expect(cookie.toLowerCase()).toContain("secure");
    expect(cookie.toLowerCase()).toContain("samesite=lax");
    expect(cookie.toLowerCase()).toContain("path=/");
  });

  it("puts the session token in the cookie and nowhere in the body", async () => {
    const response = await call(post(GOOD));
    const body = JSON.stringify(await response.json());
    expect(response.headers.get("set-cookie")).toContain("session-token-value");
    expect(body).not.toContain("session-token-value");
  });

  it("returns no user id, username, or email", async () => {
    const body = JSON.stringify(await (await call(post(GOOD))).json());
    expect(body).not.toContain("ayoub");
    expect(body).not.toMatch(/"userId"/);
  });

  it("clears the identifier's failure counter", async () => {
    await call(post(GOOD));
    expect(clearFailures).toHaveBeenCalledWith(expect.any(String), "login");
  });

  it("is never cached", async () => {
    const response = await call(post(GOOD));
    expect(response.headers.get("cache-control")).toContain("no-store");
  });
});

describe("failed login", () => {
  it("returns one generic message for wrong credentials", async () => {
    attemptLogin.mockResolvedValue({ ok: false, reason: "bad_credentials" });
    const response = await call(post(GOOD));
    expect(response.status).toBe(401);
    expect((await response.json()).error).toMatch(/not correct/i);
  });

  it("gives a disabled account the same answer as a wrong password", async () => {
    attemptLogin.mockResolvedValue({ ok: false, reason: "bad_credentials" });
    const wrong = await (await call(post(GOOD))).json();
    attemptLogin.mockResolvedValue({ ok: false, reason: "inactive" });
    const inactiveResponse = await call(post(GOOD));
    const inactive = await inactiveResponse.json();
    // Whether an account exists but is disabled must not be answerable.
    expect(inactive.error).toBe(wrong.error);
    expect(inactiveResponse.status).toBe(401);
  });

  it("sets no cookie on failure", async () => {
    attemptLogin.mockResolvedValue({ ok: false, reason: "bad_credentials" });
    const response = await call(post(GOOD));
    expect(response.headers.get("set-cookie") ?? "").not.toContain("tl_session=session-token-value");
    expect(openWebsiteSession).not.toHaveBeenCalled();
  });

  it("reserves both rate-limit buckets before checking credentials", async () => {
    attemptLogin.mockResolvedValue({ ok: false, reason: "bad_credentials" });
    await call(post(GOOD));
    expect(isRateLimited).toHaveBeenCalledTimes(2);
    expect(isRateLimited).toHaveBeenCalledWith(expect.any(String), "login", "login:ip");
    expect(isRateLimited).toHaveBeenCalledWith(expect.any(String), "login", "login:id");
  });
});

describe("unverified email", () => {
  it("is rejected, and says so only because the password was already correct", async () => {
    attemptLogin.mockResolvedValue({ ok: false, reason: "email_unverified" });
    const response = await call(post(GOOD));
    expect(response.status).toBe(403);
    const body = await response.json();
    expect(body.ok).toBe(false);
    expect(body.verificationRequired).toBe(true);
    expect(body.error).toMatch(/verify your email/i);
  });

  it("opens no session", async () => {
    attemptLogin.mockResolvedValue({ ok: false, reason: "email_unverified" });
    await call(post(GOOD));
    expect(openWebsiteSession).not.toHaveBeenCalled();
  });
});

describe("rate limiting", () => {
  it("refuses when over the limit, without checking credentials", async () => {
    isRateLimited.mockResolvedValue(true);
    const response = await call(post(GOOD));
    expect(response.status).toBe(429);
    expect(attemptLogin).not.toHaveBeenCalled();
  });
});

describe("request validation", () => {
  it("rejects a cross-origin post", async () => {
    const response = await call(post(GOOD, { origin: "https://evil.com" }));
    expect(response.status).toBe(403);
    expect(attemptLogin).not.toHaveBeenCalled();
  });

  it("rejects a post with neither Origin nor Referer", async () => {
    const request = new Request("https://site.test/api/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(GOOD),
    });
    expect((await call(request)).status).toBe(403);
  });

  it("rejects a wrong content type", async () => {
    const request = new Request("https://site.test/api/auth/login", {
      method: "POST",
      headers: { "content-type": "text/plain", origin: "https://site.test" },
      body: JSON.stringify(GOOD),
    });
    expect((await call(request)).status).toBe(415);
  });

  it("rejects an oversized body", async () => {
    expect((await call(post({ ...GOOD, password: "x".repeat(9000) }))).status).toBe(413);
  });

  it("treats unparseable JSON as a failed attempt, not an error", async () => {
    attemptLogin.mockResolvedValue({ ok: false, reason: "bad_credentials" });
    expect((await call(post("{not json"))).status).toBe(401);
  });
});

describe("logging", () => {
  it("never logs the password or the identifier", async () => {
    attemptLogin.mockResolvedValue({ ok: false, reason: "bad_credentials" });
    await call(post(GOOD));
    const logged = JSON.stringify(logAuthEvent.mock.calls);
    expect(logged).not.toContain(GOOD.password);
    expect(logged).not.toContain("ayoub");
  });
});
