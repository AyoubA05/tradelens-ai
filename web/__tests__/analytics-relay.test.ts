import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * GET /api/analytics — the same-origin relay the analytics page reads through.
 *
 * The security shape is the load-bearing part: fail-shut CSRF *before* the
 * session is read, the session from the cookie only, the eligibility gate,
 * and the backend's 422 forwarded as itself (its `detail` is the only error
 * body here that says something actionable) while every other backend body
 * stays behind an opaque `{ ok: false }`.
 */

const { fetchAnalytics, authenticateSessionToken } = vi.hoisted(() => ({
  fetchAnalytics: vi.fn(),
  authenticateSessionToken: vi.fn(),
}));

vi.mock("@/lib/app/analytics", () => ({ fetchAnalytics }));

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

function req(
  query = "?from=2026-08-01&to=2026-08-31",
  headers: Record<string, string> = {},
) {
  return new Request(`https://site.test/api/analytics${query}`, {
    headers: {
      cookie: "tl_session=browser-token",
      origin: "https://site.test",
      ...headers,
    },
  });
}

async function callGet(request: Request) {
  const { GET } = await import("@/app/api/analytics/route");
  return GET(request);
}

beforeEach(() => {
  vi.resetModules();
  fetchAnalytics.mockReset();
  authenticateSessionToken.mockReset().mockResolvedValue(eligibleUser);
  process.env.SITE_ORIGIN = "https://site.test";
});

describe("authorizeAnalyticsRelay", () => {
  it("refuses with 403 when SITE_ORIGIN is unset", async () => {
    delete process.env.SITE_ORIGIN;
    const response = await callGet(req());
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ ok: false });
    expect(fetchAnalytics).not.toHaveBeenCalled();
  });

  it("refuses a missing SITE_ORIGIN without ever reading the session", async () => {
    delete process.env.SITE_ORIGIN;
    // A misconfigured deployment must not behave differently depending on
    // whether the caller happens to hold a valid cookie.
    const response = await callGet(req());
    expect(response.status).toBe(403);
    expect(authenticateSessionToken).not.toHaveBeenCalled();
  });

  it("refuses a cross-origin request with 403 when SITE_ORIGIN is set", async () => {
    const response = await callGet(req("?from=2026-08-01&to=2026-08-31", {
      origin: "https://evil.test",
    }));
    expect(response.status).toBe(403);
    expect(fetchAnalytics).not.toHaveBeenCalled();
  });

  it("refuses with 401 when there is no session", async () => {
    authenticateSessionToken.mockResolvedValue(null);
    const response = await callGet(req());
    expect(response.status).toBe(401);
    expect(fetchAnalytics).not.toHaveBeenCalled();
  });

  it("refuses an ineligible account with 403 before reaching the backend", async () => {
    authenticateSessionToken.mockResolvedValue({
      ...eligibleUser,
      onboardingCompleted: false,
    });
    const response = await callGet(req());
    expect(response.status).toBe(403);
    expect(fetchAnalytics).not.toHaveBeenCalled();
  });
});

describe("GET /api/analytics", () => {
  it("forwards the period and filters and returns the payload uncached", async () => {
    fetchAnalytics.mockResolvedValue({ period: { start: "2026-08-01" } });
    const response = await callGet(
      req("?from=2026-08-01&to=2026-08-31&asset=EURUSD&session=London&strategy=SMC"),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ period: { start: "2026-08-01" } });
    expect(response.headers.get("cache-control")).toContain("no-store");
    expect(fetchAnalytics).toHaveBeenCalledWith("browser-token", {
      from: "2026-08-01",
      to: "2026-08-31",
      asset: "EURUSD",
      session: "London",
      strategy: "SMC",
    });
  });

  it("never forwards browser-supplied owner identifiers", async () => {
    fetchAnalytics.mockResolvedValue({ period: { start: "2026-08-01" } });

    await callGet(
      req(
        "?from=2026-08-01&to=2026-08-31&user_id=1&uid=2&owner=3&accountId=4",
      ),
    );

    expect(fetchAnalytics).toHaveBeenCalledWith("browser-token", {
      from: "2026-08-01",
      to: "2026-08-31",
      asset: undefined,
      session: undefined,
      strategy: undefined,
    });
  });

  it("forwards the backend's 422 detail, which is the one actionable error body", async () => {
    const { ApiError } = await import("@/lib/api/client");
    fetchAnalytics.mockRejectedValue(
      new ApiError(422, { detail: "'to' must not be before 'from'." }),
    );
    const response = await callGet(req("?from=2026-08-31&to=2026-08-01"));
    expect(response.status).toBe(422);
    expect(await response.json()).toEqual({
      ok: false,
      detail: "'to' must not be before 'from'.",
    });
  });

  it("leaks no other backend error body, at any status", async () => {
    const { ApiError } = await import("@/lib/api/client");
    for (const status of [400, 401, 403, 404, 429, 500, 503]) {
      fetchAnalytics.mockRejectedValue(
        new ApiError(status, { detail: "owner 7 has no such row" }),
      );
      const response = await callGet(req());
      expect(response.status).toBe(status);
      const body = await response.json();
      expect(body).toEqual({ ok: false });
      expect(JSON.stringify(body)).not.toContain("owner 7");
    }
  });

  it("reports a non-ApiError fault as 502 and says nothing about it", async () => {
    fetchAnalytics.mockRejectedValue(new Error("connect ECONNREFUSED 10.0.0.4:8000"));
    const response = await callGet(req());
    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body).toEqual({ ok: false });
    expect(JSON.stringify(body)).not.toContain("ECONNREFUSED");
  });

  it("is dynamic and node-runtime, so no period is ever served from a cache", async () => {
    const route = await import("@/app/api/analytics/route");
    expect(route.runtime).toBe("nodejs");
    expect(route.dynamic).toBe("force-dynamic");
  });
});
