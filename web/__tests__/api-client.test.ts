import { createHash } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";

import { callApi } from "@/lib/api/client";
import { WEBSITE_DOMAIN } from "@/lib/auth/domains";

describe("FastAPI client credential boundary", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("forwards a non-browser-replayable session handle, never the raw cookie", async () => {
    vi.stubEnv("TL_API_ORIGIN", "https://api.example.test");
    vi.stubEnv("TL_SERVICE_SECRET", "service-secret");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ user_id: 7 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const raw = "raw-browser-cookie-value";
    await callApi("/v1/session/whoami", raw);

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers["X-TL-Session-Handle"]).toBe(
      createHash("sha256").update(WEBSITE_DOMAIN + raw, "utf8").digest("hex"),
    );
    expect(headers).not.toHaveProperty("X-TL-Session");
    expect(JSON.stringify(init)).not.toContain(raw);
  });

  it("resolves a 204 without calling .json() on the empty body", async () => {
    // The trade-delete endpoint's success response carries no body; `.json()`
    // on an empty stream throws rather than resolving, so a 204 has to be
    // special-cased rather than parsed like every other response here.
    vi.stubEnv("TL_API_ORIGIN", "https://api.example.test");
    vi.stubEnv("TL_SERVICE_SECRET", "service-secret");
    const json = vi.fn().mockRejectedValue(new SyntaxError("Unexpected end of JSON input"));
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204, json });
    vi.stubGlobal("fetch", fetchMock);

    await expect(callApi("/v1/trades/1", "tok", { method: "DELETE" })).resolves.toBeUndefined();
    expect(json).not.toHaveBeenCalled();
  });
});

describe("FastAPI client error status", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  /**
   * The status on the thrown `ApiError` must be the backend's own. Every
   * other test in the suite constructs `new ApiError(404 | 409 | 503)` by
   * hand, which proves only how a caller reacts to a status it was handed
   * — nothing proved the status `callApi` puts there is real. Replacing
   * `response.status` with a literal used to leave the whole suite green,
   * and the entire error chain hangs off this one value: 404 →
   * `notFound()` (existence non-disclosure), 409 → the conflict view,
   * 503 → "nothing was deleted."
   */
  it.each([404, 409, 503])("throws with the backend's own status (%i)", async (status) => {
    vi.stubEnv("TL_API_ORIGIN", "https://api.example.test");
    vi.stubEnv("TL_SERVICE_SECRET", "service-secret");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status, json: async () => ({}) }),
    );

    await expect(callApi("/v1/trades/1", "tok")).rejects.toMatchObject({ status });
  });

  it("carries the error body so a caller can read what the status cannot say", async () => {
    // The delete 503 reports `remaining` (retryable) separately from
    // `unresolvable` (a retry can never clear it) — a distinction the status
    // alone cannot carry, and the relay needs it to avoid telling a trader
    // to keep retrying something that cannot succeed.
    vi.stubEnv("TL_API_ORIGIN", "https://api.example.test");
    vi.stubEnv("TL_SERVICE_SECRET", "service-secret");
    const detail = { error: "screenshot_cleanup_failed", remaining: 0, unresolvable: 2 };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({ detail }) }),
    );

    await expect(callApi("/v1/trades/1", "tok", { method: "DELETE" })).rejects.toMatchObject({
      status: 503,
      body: { detail },
    });
  });

  it("still throws the right status when the error body is unreadable", async () => {
    // An unparseable body must not mask the fault it accompanies.
    vi.stubEnv("TL_API_ORIGIN", "https://api.example.test");
    vi.stubEnv("TL_SERVICE_SECRET", "service-secret");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new SyntaxError("Unexpected end of JSON input");
        },
      }),
    );

    await expect(callApi("/v1/trades/1", "tok")).rejects.toMatchObject({
      status: 502,
      body: undefined,
    });
  });
});
