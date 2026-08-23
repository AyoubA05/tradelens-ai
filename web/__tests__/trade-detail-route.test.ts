import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * PATCH/DELETE /api/trades/[id] — the relay a Trade Detail Client Component
 * uses to reach FastAPI, since `callApi` is `server-only` and cannot be
 * imported into a client bundle.
 *
 * `patchTrade`/`deleteTrade` and session resolution are stubbed so this
 * covers the relay's own behaviour: CSRF, auth, status-code passthrough, and
 * that a 409/503 is reported plainly rather than reshaped into something
 * that could read as success. The real HTTP call to FastAPI is covered by
 * `trade-detail-fetch.test.ts` and the backend's own test suite.
 */

const { patchTrade, deleteTrade, authenticateSessionToken } = vi.hoisted(() => ({
  patchTrade: vi.fn(),
  deleteTrade: vi.fn(),
  authenticateSessionToken: vi.fn(),
}));

vi.mock("@/lib/app/trades", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/app/trades")>();
  return { ...actual, patchTrade, deleteTrade };
});

vi.mock("@/lib/auth/session", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/auth/session")>();
  return { ...actual, authenticateSessionToken };
});

function req(method: string, id: string, body?: unknown, headers: Record<string, string> = {}) {
  return new Request(`https://site.test/api/trades/${id}`, {
    method,
    headers: {
      cookie: "tl_session=browser-token",
      origin: "https://site.test",
      ...(body !== undefined ? { "content-type": "application/json" } : {}),
      ...headers,
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

async function callPatch(request: Request, id: string) {
  const { PATCH } = await import("@/app/api/trades/[id]/route");
  return PATCH(request, { params: Promise.resolve({ id }) });
}

async function callDelete(request: Request, id: string) {
  const { DELETE } = await import("@/app/api/trades/[id]/route");
  return DELETE(request, { params: Promise.resolve({ id }) });
}

beforeEach(() => {
  vi.resetModules();
  patchTrade.mockReset();
  deleteTrade.mockReset();
  authenticateSessionToken.mockReset().mockResolvedValue({ userId: 7, appSurface: "nextjs" });
  process.env.SITE_ORIGIN = "https://site.test";
});

describe("PATCH /api/trades/[id]", () => {
  it("forwards the body and the session token, and returns the updated trade", async () => {
    patchTrade.mockResolvedValue({ id: 42, asset: "NQ", updated_at: "2026-08-02T00:00:00Z" });
    const response = await callPatch(
      req("PATCH", "42", { asset: "NQ", expected_updated_at: "2026-08-01T00:00:00Z" }),
      "42",
    );
    expect(response.status).toBe(200);
    expect(patchTrade).toHaveBeenCalledWith("browser-token", 42, {
      asset: "NQ",
      expected_updated_at: "2026-08-01T00:00:00Z",
    });
    expect((await response.json()).asset).toBe("NQ");
  });

  it("rejects a cross-site POST", async () => {
    const response = await callPatch(
      req("PATCH", "42", { expected_updated_at: "x" }, { origin: "https://evil.test" }),
      "42",
    );
    expect(response.status).toBe(403);
    expect(patchTrade).not.toHaveBeenCalled();
  });

  it("rejects an unauthenticated request without calling the backend", async () => {
    authenticateSessionToken.mockResolvedValue(null);
    const response = await callPatch(req("PATCH", "42", { expected_updated_at: "x" }), "42");
    expect(response.status).toBe(401);
    expect(patchTrade).not.toHaveBeenCalled();
  });

  it("reports a 409 conflict plainly, never as success", async () => {
    const { ApiError } = await import("@/lib/api/client");
    patchTrade.mockRejectedValue(new ApiError(409));
    const response = await callPatch(
      req("PATCH", "42", { expected_updated_at: "stale" }),
      "42",
    );
    expect(response.status).toBe(409);
    expect((await response.json()).error).toBe("stale_trade");
  });

  it("rejects a body that is not valid JSON", async () => {
    const request = new Request("https://site.test/api/trades/42", {
      method: "PATCH",
      headers: { cookie: "tl_session=browser-token", origin: "https://site.test", "content-type": "application/json" },
      body: "{not json",
    });
    const response = await callPatch(request, "42");
    expect(response.status).toBe(400);
    expect(patchTrade).not.toHaveBeenCalled();
  });

  it("404s a non-numeric id without calling the backend", async () => {
    const response = await callPatch(req("PATCH", "abc", { expected_updated_at: "x" }), "abc");
    expect(response.status).toBe(404);
    expect(patchTrade).not.toHaveBeenCalled();
  });
});

describe("DELETE /api/trades/[id]", () => {
  it("deletes and returns 204 with no body", async () => {
    deleteTrade.mockResolvedValue(undefined);
    const response = await callDelete(req("DELETE", "42"), "42");
    expect(response.status).toBe(204);
    expect(deleteTrade).toHaveBeenCalledWith("browser-token", 42);
  });

  it("reports a 503 cleanup failure plainly — never partial success", async () => {
    const { ApiError } = await import("@/lib/api/client");
    deleteTrade.mockRejectedValue(new ApiError(503));
    const response = await callDelete(req("DELETE", "42"), "42");
    expect(response.status).toBe(503);
    expect((await response.json()).error).toBe("screenshot_cleanup_failed");
  });

  it("rejects a cross-site DELETE", async () => {
    const response = await callDelete(req("DELETE", "42", undefined, { origin: "https://evil.test" }), "42");
    expect(response.status).toBe(403);
    expect(deleteTrade).not.toHaveBeenCalled();
  });

  it("rejects an unauthenticated request without calling the backend", async () => {
    authenticateSessionToken.mockResolvedValue(null);
    const response = await callDelete(req("DELETE", "42"), "42");
    expect(response.status).toBe(401);
    expect(deleteTrade).not.toHaveBeenCalled();
  });
});
