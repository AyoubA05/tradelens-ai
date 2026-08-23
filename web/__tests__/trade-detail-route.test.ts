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

describe("relay hardening", () => {
  describe("CSRF fails shut", () => {
    it("refuses rather than allows when SITE_ORIGIN is unset", async () => {
      // The nine `app/api/auth/*` routes guard with `if (siteOrigin && ...)`,
      // so an unset SITE_ORIGIN skips their origin check entirely. This relay
      // deliberately diverges: it is the first of that family to guard trade
      // data rather than an auth flow, so a missing origin refuses. If this
      // test ever fails because the guard was "made consistent" with the auth
      // routes, that is the regression, not the test.
      delete process.env.SITE_ORIGIN;
      const patch = await callPatch(req("PATCH", "42", { expected_updated_at: "x" }), "42");
      expect(patch.status).toBe(403);
      expect(patchTrade).not.toHaveBeenCalled();

      const del = await callDelete(req("DELETE", "42"), "42");
      expect(del.status).toBe(403);
      expect(deleteTrade).not.toHaveBeenCalled();
    });
  });

  describe("parseTradeId rejects every non-plain-integer id", () => {
    // Bare `Number()` accepts JavaScript's other numeric literal forms, so
    // "1e3", "0x10", "0b11" and " 1" would each alias a different trade's
    // row, and "999999999999999999999" would survive `Number.isInteger` only
    // to be re-serialised as "1e+21" into the upstream path AND the
    // HMAC-signed canonical path.
    const rejected: Array<[string, string]> = [
      ["1e3", "exponent notation would alias trade 1000"],
      ["0x10", "hex would alias trade 16"],
      ["0b11", "binary would alias trade 3"],
      ["0o17", "octal would alias trade 15"],
      [" 1", "leading whitespace would alias trade 1"],
      ["1 ", "trailing whitespace would alias trade 1"],
      ["+1", "a signed literal would alias trade 1"],
      ["1.0", "a decimal literal would alias trade 1"],
      ["01", "a leading zero would alias trade 1"],
      ["999999999999999999999", "beyond exact-integer range; serialises as 1e+21"],
      ["0", "there is no trade 0"],
      ["-1", "negative ids do not exist"],
      ["", "an empty id is not a trade"],
      ["abc", "not a number at all"],
      ["Infinity", "Number('Infinity') is not an id"],
    ];

    it.each(rejected)("404s %j without calling the backend (%s)", async (id) => {
      const patch = await callPatch(req("PATCH", id, { expected_updated_at: "x" }), id);
      expect(patch.status).toBe(404);
      expect(patchTrade).not.toHaveBeenCalled();

      const del = await callDelete(req("DELETE", id), id);
      expect(del.status).toBe(404);
      expect(deleteTrade).not.toHaveBeenCalled();
    });

    it("accepts a plain positive integer and forwards it as a number", async () => {
      deleteTrade.mockResolvedValue(undefined);
      const response = await callDelete(req("DELETE", "1234567890123456"), "1234567890123456");
      expect(response.status).toBe(204);
      expect(deleteTrade).toHaveBeenCalledWith("browser-token", 1234567890123456);
    });
  });

  describe("backend status passthrough", () => {
    // A relay that collapsed a backend status into its own 502 would break
    // the chain each status drives: 404 becomes notFound() (the existence
    // non-disclosure property), 401/403 mean the session or ownership check
    // said no. Only a non-ApiError fault is this relay's own 502.
    it.each([404, 401, 403, 422, 500])("forwards a backend %i as itself", async (status) => {
      const { ApiError } = await import("@/lib/api/client");
      patchTrade.mockRejectedValue(new ApiError(status));
      const patch = await callPatch(req("PATCH", "42", { expected_updated_at: "x" }), "42");
      expect(patch.status).toBe(status);

      deleteTrade.mockRejectedValue(new ApiError(status));
      const del = await callDelete(req("DELETE", "42"), "42");
      expect(del.status).toBe(status);
    });

    it("uses 502 only for a fault that is not the backend's own status", async () => {
      patchTrade.mockRejectedValue(new TypeError("fetch failed"));
      const response = await callPatch(req("PATCH", "42", { expected_updated_at: "x" }), "42");
      expect(response.status).toBe(502);
    });
  });

  describe("no-store on every response", () => {
    // A trade cached by an intermediary is another account's data one shared
    // proxy away. The header has to be on the failure paths too, not just the
    // happy one.
    it("sets Cache-Control: no-store on success, 403, 401, 404, 409 and 503", async () => {
      const { ApiError } = await import("@/lib/api/client");
      const responses: Response[] = [];

      patchTrade.mockResolvedValue({ id: 42, updated_at: "2026-08-02T00:00:00Z" });
      responses.push(await callPatch(req("PATCH", "42", { expected_updated_at: "x" }), "42"));

      responses.push(
        await callPatch(
          req("PATCH", "42", { expected_updated_at: "x" }, { origin: "https://evil.test" }),
          "42",
        ),
      );

      responses.push(await callPatch(req("PATCH", "abc", { expected_updated_at: "x" }), "abc"));

      patchTrade.mockRejectedValue(new ApiError(409));
      responses.push(await callPatch(req("PATCH", "42", { expected_updated_at: "x" }), "42"));

      deleteTrade.mockRejectedValue(new ApiError(503));
      responses.push(await callDelete(req("DELETE", "42"), "42"));

      deleteTrade.mockResolvedValue(undefined);
      responses.push(await callDelete(req("DELETE", "42"), "42"));

      authenticateSessionToken.mockResolvedValue(null);
      responses.push(await callDelete(req("DELETE", "42"), "42"));

      expect(responses).toHaveLength(7);
      for (const response of responses) {
        expect(response.headers.get("cache-control")).toContain("no-store");
      }
    });
  });

  describe("the 503 cleanup split reaches the caller", () => {
    // The backend reports `remaining` (an object-store fault a retry clears)
    // separately from `unresolvable` (a screenshot row a retry can never
    // clear) so that nobody tells a trader to keep retrying something that
    // cannot succeed. If the relay flattened them, that split would die here.
    async function delete503(detail: unknown) {
      const { ApiError } = await import("@/lib/api/client");
      deleteTrade.mockRejectedValue(new ApiError(503, detail));
      const response = await callDelete(req("DELETE", "42"), "42");
      expect(response.status).toBe(503);
      return response.json();
    }

    it("marks a retryable cleanup failure as resolvable", async () => {
      const body = await delete503({
        detail: { error: "screenshot_cleanup_failed", remaining: 2, unresolvable: 0 },
      });
      expect(body).toEqual({ error: "screenshot_cleanup_failed", unresolvable: false });
    });

    it("forwards unresolvable when a retry can never clear the failure", async () => {
      const body = await delete503({
        detail: { error: "screenshot_cleanup_failed", remaining: 0, unresolvable: 1 },
      });
      expect(body).toEqual({ error: "screenshot_cleanup_failed", unresolvable: true });
    });

    it("treats an unreadable body as retryable — the weaker claim", async () => {
      expect(await delete503(undefined)).toEqual({
        error: "screenshot_cleanup_failed",
        unresolvable: false,
      });
      expect(await delete503({ detail: "not an object" })).toEqual({
        error: "screenshot_cleanup_failed",
        unresolvable: false,
      });
    });

    it("never reshapes a 503 into anything that could read as deleted", async () => {
      const body = await delete503({
        detail: { error: "screenshot_cleanup_failed", remaining: 0, unresolvable: 3 },
      });
      expect(body).not.toHaveProperty("ok", true);
      expect(JSON.stringify(body)).not.toMatch(/deleted|removed/i);
    });
  });
});
