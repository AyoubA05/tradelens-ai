import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * GET/PUT /api/trades/draft — the relay `useDraftAutosave` uses (Task D3).
 *
 * The security shape is the load-bearing part, same family as every other
 * trade-mutating relay: fail-shut CSRF, session from the cookie only, the
 * app-eligibility gate, and the backend's status forwarded rather than
 * reshaped.
 */

const { getDraft, saveDraft, authenticateSessionToken } = vi.hoisted(() => ({
  getDraft: vi.fn(),
  saveDraft: vi.fn(),
  authenticateSessionToken: vi.fn(),
}));

vi.mock("@/lib/app/trade-draft", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/app/trade-draft")>();
  return { ...actual, getDraft, saveDraft };
});

vi.mock("@/lib/auth/session", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/auth/session")>();
  return { ...actual, authenticateSessionToken };
});

const eligibleUser = {
  userId: 7,
  email: "trader@example.test",
  emailVerifiedAt: new Date("2026-08-01T00:00:00Z"),
  emailVerificationRequired: true,
  onboardingCompleted: true,
  strategyProfileCompleted: true,
  appSurface: "nextjs",
};

function req(method: string, body?: unknown, headers: Record<string, string> = {}) {
  return new Request("https://site.test/api/trades/draft", {
    method,
    headers: {
      cookie: "tl_session=browser-token",
      origin: "https://site.test",
      "content-type": "application/json",
      ...headers,
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
}

async function callGet(request: Request) {
  const { GET } = await import("@/app/api/trades/draft/route");
  return GET(request);
}

async function callPut(request: Request) {
  const { PUT } = await import("@/app/api/trades/draft/route");
  return PUT(request);
}

beforeEach(() => {
  vi.resetModules();
  getDraft.mockReset();
  saveDraft.mockReset();
  authenticateSessionToken.mockReset().mockResolvedValue(eligibleUser);
  process.env.SITE_ORIGIN = "https://site.test";
});

describe("GET /api/trades/draft", () => {
  it("returns the caller's own draft, resolved from the cookie", async () => {
    getDraft.mockResolvedValue({ draft: { asset: "NQ" } });
    const response = await callGet(req("GET"));
    expect(response.status).toBe(200);
    expect(getDraft).toHaveBeenCalledWith("browser-token");
    expect((await response.json()).draft.asset).toBe("NQ");
  });

  it("fails shut when SITE_ORIGIN is unset", async () => {
    delete process.env.SITE_ORIGIN;
    const response = await callGet(req("GET"));
    expect(response.status).toBe(403);
    expect(getDraft).not.toHaveBeenCalled();
  });

  it("rejects a cross-site GET without reaching the backend", async () => {
    const response = await callGet(req("GET", undefined, { origin: "https://evil.test" }));
    expect(response.status).toBe(403);
    expect(getDraft).not.toHaveBeenCalled();
  });

  it("rejects an unauthenticated request", async () => {
    authenticateSessionToken.mockResolvedValue(null);
    const response = await callGet(req("GET"));
    expect(response.status).toBe(401);
    expect(getDraft).not.toHaveBeenCalled();
  });

  it("refuses an ineligible account before reaching FastAPI", async () => {
    authenticateSessionToken.mockResolvedValue({ ...eligibleUser, appSurface: "streamlit" });
    const response = await callGet(req("GET"));
    expect(response.status).toBe(403);
    expect(getDraft).not.toHaveBeenCalled();
  });

  it("sets no-store", async () => {
    getDraft.mockResolvedValue({ draft: null });
    const response = await callGet(req("GET"));
    expect(response.headers.get("cache-control")).toContain("no-store");
  });
});

describe("PUT /api/trades/draft", () => {
  it("saves the body exactly as sent, with the session's own token", async () => {
    saveDraft.mockResolvedValue({ draft: { asset: "NQ" } });
    const response = await callPut(req("PUT", { asset: "NQ" }));
    expect(response.status).toBe(200);
    expect(saveDraft).toHaveBeenCalledWith("browser-token", { asset: "NQ" });
  });

  it("fails shut when SITE_ORIGIN is unset", async () => {
    delete process.env.SITE_ORIGIN;
    const response = await callPut(req("PUT", { asset: "NQ" }));
    expect(response.status).toBe(403);
    expect(saveDraft).not.toHaveBeenCalled();
  });

  it("rejects a cross-site PUT without reaching the backend", async () => {
    const response = await callPut(req("PUT", { asset: "NQ" }, { origin: "https://evil.test" }));
    expect(response.status).toBe(403);
    expect(saveDraft).not.toHaveBeenCalled();
  });

  it("never takes identity from the body", async () => {
    saveDraft.mockResolvedValue({ draft: {} });
    await callPut(req("PUT", { asset: "NQ", user_id: 999 }));
    expect(saveDraft).toHaveBeenCalledWith("browser-token", { asset: "NQ", user_id: 999 });
    // The relay forwards the body verbatim; it is the backend's own
    // `extra="forbid"` allowlist that refuses `user_id`, not this layer —
    // this test only pins that the relay never substitutes its own
    // identity claim into the call, i.e. always "browser-token".
  });

  it("answers 400 for an unparseable body", async () => {
    const response = await callPut(
      new Request("https://site.test/api/trades/draft", {
        method: "PUT",
        headers: {
          cookie: "tl_session=browser-token",
          origin: "https://site.test",
          "content-type": "application/json",
        },
        body: "{not json",
      }),
    );
    expect(response.status).toBe(400);
    expect(saveDraft).not.toHaveBeenCalled();
  });
});
