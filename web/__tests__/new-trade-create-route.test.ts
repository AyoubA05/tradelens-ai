import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * POST /api/trades/create — the relay the New Trade Client Component uses
 * to reach FastAPI, since `callApi` is `server-only`. Same security shape as
 * `trade-detail-route.test.ts` for `[id]/route.ts`; this file focuses on
 * what is specific to create: status forwarding (422, and 200 with
 * duplicate_of), and that the eligibility gate is enforced here too since
 * this route can be called directly.
 */

const { createTrade, authenticateSessionToken } = vi.hoisted(() => ({
  createTrade: vi.fn(),
  authenticateSessionToken: vi.fn(),
}));

vi.mock("@/lib/app/new-trade-create", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/app/new-trade-create")>();
  return { ...actual, createTrade };
});

vi.mock("@/lib/auth/session", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/auth/session")>();
  return { ...actual, authenticateSessionToken };
});

function req(body?: unknown, headers: Record<string, string> = {}) {
  return new Request("https://site.test/api/trades/create", {
    method: "POST",
    headers: {
      cookie: "tl_session=browser-token",
      origin: "https://site.test",
      ...(body !== undefined ? { "content-type": "application/json" } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

const eligibleUser = {
  userId: 7,
  email: "trader@example.test",
  emailVerifiedAt: new Date("2026-08-01T00:00:00Z"),
  emailVerificationRequired: true,
  onboardingCompleted: true,
  strategyProfileCompleted: true,
  appSurface: "nextjs",
};

async function callPost(request: Request) {
  const { POST } = await import("@/app/api/trades/create/route");
  return POST(request);
}

beforeEach(() => {
  vi.resetModules();
  createTrade.mockReset();
  authenticateSessionToken.mockReset().mockResolvedValue(eligibleUser);
  process.env.SITE_ORIGIN = "https://site.test";
});

describe("POST /api/trades/create", () => {
  it("forwards the body and the session token, and returns the created trade", async () => {
    createTrade.mockResolvedValue({ id: 42, asset: "NQ", duplicate_of: null });
    const response = await callPost(req({ trade_date: "2026-08-20", asset: "NQ" }));
    expect(response.status).toBe(200);
    expect(createTrade).toHaveBeenCalledWith("browser-token", {
      trade_date: "2026-08-20",
      asset: "NQ",
    });
    expect((await response.json()).asset).toBe("NQ");
  });

  it("surfaces duplicate_of in the body rather than hiding it", async () => {
    createTrade.mockResolvedValue({ id: 42, duplicate_of: 42 });
    const response = await callPost(req({ trade_date: "2026-08-20", asset: "NQ" }));
    expect(response.status).toBe(200);
    expect((await response.json()).duplicate_of).toBe(42);
  });

  it("rejects a cross-site POST", async () => {
    const response = await callPost(req({ asset: "NQ" }, { origin: "https://evil.test" }));
    expect(response.status).toBe(403);
    expect(createTrade).not.toHaveBeenCalled();
  });

  it("fails shut when SITE_ORIGIN is unset, matching the trade-detail relay", async () => {
    delete process.env.SITE_ORIGIN;
    const response = await callPost(req({ asset: "NQ" }));
    expect(response.status).toBe(403);
    expect(createTrade).not.toHaveBeenCalled();
  });

  it("rejects an unauthenticated request without calling the backend", async () => {
    authenticateSessionToken.mockResolvedValue(null);
    const response = await callPost(req({ asset: "NQ" }));
    expect(response.status).toBe(401);
    expect(createTrade).not.toHaveBeenCalled();
  });

  it("rejects a body that is not valid JSON", async () => {
    const request = new Request("https://site.test/api/trades/create", {
      method: "POST",
      headers: { cookie: "tl_session=browser-token", origin: "https://site.test", "content-type": "application/json" },
      body: "{not json",
    });
    const response = await callPost(request);
    expect(response.status).toBe(400);
    expect(createTrade).not.toHaveBeenCalled();
  });

  it.each([
    { user: { ...eligibleUser, appSurface: "streamlit" }, label: "a Streamlit-only account" },
    { user: { ...eligibleUser, onboardingCompleted: false }, label: "an account before onboarding" },
  ])("refuses $label before reaching FastAPI", async ({ user }) => {
    authenticateSessionToken.mockResolvedValue(user);
    const response = await callPost(req({ asset: "NQ" }));
    expect(response.status).toBe(403);
    expect(createTrade).not.toHaveBeenCalled();
  });

  it("forwards a 422 (allowlist rejection or future trade_date) plainly", async () => {
    const { ApiError } = await import("@/lib/api/client");
    createTrade.mockRejectedValue(new ApiError(422, { detail: "trade_date must not be in the future" }));
    const response = await callPost(req({ asset: "NQ" }));
    expect(response.status).toBe(422);
    expect((await response.json()).ok).toBe(false);
  });

  it("uses 502 only for a fault that is not the backend's own status", async () => {
    createTrade.mockRejectedValue(new TypeError("fetch failed"));
    const response = await callPost(req({ asset: "NQ" }));
    expect(response.status).toBe(502);
  });

  it("sets no-store and referrer-policy headers on every response", async () => {
    createTrade.mockResolvedValue({ id: 1, duplicate_of: null });
    const ok = await callPost(req({ asset: "NQ" }));
    expect(ok.headers.get("cache-control")).toContain("no-store");
    expect(ok.headers.get("referrer-policy")).toBe("no-referrer");

    const forbidden = await callPost(req({ asset: "NQ" }, { origin: "https://evil.test" }));
    expect(forbidden.headers.get("cache-control")).toContain("no-store");
  });
});
