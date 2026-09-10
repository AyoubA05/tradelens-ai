import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The three Strategy Profile relays: PUT /api/strategy, POST /api/strategy/skip
 * and POST /api/strategy/insights.
 *
 * The security shape is shared and load-bearing: fail-shut CSRF *before* the
 * session is read, the session from the cookie only, the eligibility gate —
 * and deliberately NOT the first-run flag, because these are the calls that
 * complete first run. Error bodies cross only in the fixed shapes this
 * feature defines; every other backend body stays behind `{ ok: false }`.
 */

const { saveStrategy, skipStrategy, appendStrategyInsight, authenticateSessionToken } =
  vi.hoisted(() => ({
    saveStrategy: vi.fn(),
    skipStrategy: vi.fn(),
    appendStrategyInsight: vi.fn(),
    authenticateSessionToken: vi.fn(),
  }));

vi.mock("@/lib/app/strategy", () => ({ saveStrategy, skipStrategy, appendStrategyInsight }));

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

const WRITE = {
  name: "Mine",
  trading_style: null,
  markets: null,
  timeframes: null,
  entry_rules: null,
  stop_rules: null,
  take_profit_rules: null,
  risk_rules: null,
  setups_traded: null,
  setups_avoided: null,
  news_session_rules: null,
  common_mistakes: null,
  expected_revision: "2026-09-10T12:00:00+00:00",
};

type Route = {
  label: string;
  method: "PUT" | "POST";
  path: string;
  body: unknown;
  backend: ReturnType<typeof vi.fn>;
  call: (request: Request) => Promise<Response>;
};

const ROUTES: Route[] = [
  {
    label: "save",
    method: "PUT",
    path: "/api/strategy",
    body: WRITE,
    backend: saveStrategy,
    call: async (r) => (await import("@/app/api/strategy/route")).PUT(r),
  },
  {
    label: "skip",
    method: "POST",
    path: "/api/strategy/skip",
    body: undefined,
    backend: skipStrategy,
    call: async (r) => (await import("@/app/api/strategy/skip/route")).POST(r),
  },
  {
    label: "insights",
    method: "POST",
    path: "/api/strategy/insights",
    body: { field: "bias", user_value: "bearish", expected_revision: null },
    backend: appendStrategyInsight,
    call: async (r) => (await import("@/app/api/strategy/insights/route")).POST(r),
  },
];

function req(route: Route, headers: Record<string, string> = {}, raw?: string) {
  return new Request(`https://site.test${route.path}`, {
    method: route.method,
    headers: {
      cookie: "tl_session=browser-token",
      origin: "https://site.test",
      "content-type": "application/json",
      ...headers,
    },
    body: raw ?? (route.body === undefined ? undefined : JSON.stringify(route.body)),
  });
}

beforeEach(() => {
  vi.resetModules();
  for (const fn of [saveStrategy, skipStrategy, appendStrategyInsight]) {
    fn.mockReset().mockResolvedValue({ profile: null, revision: null });
  }
  authenticateSessionToken.mockReset().mockResolvedValue(eligibleUser);
  process.env.SITE_ORIGIN = "https://site.test";
});

describe.each(ROUTES)("the $label relay's authorization", (route) => {
  it("refuses a missing SITE_ORIGIN with 403 without ever reading the session", async () => {
    delete process.env.SITE_ORIGIN;
    const response = await route.call(req(route));
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ ok: false });
    expect(authenticateSessionToken).not.toHaveBeenCalled();
    expect(route.backend).not.toHaveBeenCalled();
  });

  it("refuses a cross-origin request with 403", async () => {
    const response = await route.call(req(route, { origin: "https://evil.test" }));
    expect(response.status).toBe(403);
    expect(route.backend).not.toHaveBeenCalled();
  });

  it("refuses with 401 when there is no session", async () => {
    authenticateSessionToken.mockResolvedValue(null);
    const response = await route.call(req(route));
    expect(response.status).toBe(401);
    expect(route.backend).not.toHaveBeenCalled();
  });

  it("refuses an ineligible account with 403 before reaching the backend", async () => {
    authenticateSessionToken.mockResolvedValue({ ...eligibleUser, appSurface: "streamlit" });
    const response = await route.call(req(route));
    expect(response.status).toBe(403);
    expect(route.backend).not.toHaveBeenCalled();
  });

  it("lets a first-run account through — these calls are how first run completes", async () => {
    authenticateSessionToken.mockResolvedValue({
      ...eligibleUser,
      strategyProfileCompleted: false,
    });
    const response = await route.call(req(route));
    expect(response.status).toBe(200);
    expect(route.backend).toHaveBeenCalledTimes(1);
  });

  it("sends only the session token upstream, never a browser-named owner", async () => {
    await route.call(req(route));
    expect(route.backend.mock.calls[0]?.[0]).toBe("browser-token");
  });

  it("is dynamic and node-runtime", async () => {
    const mod =
      route.label === "save"
        ? await import("@/app/api/strategy/route")
        : route.label === "skip"
          ? await import("@/app/api/strategy/skip/route")
          : await import("@/app/api/strategy/insights/route");
    expect(mod.runtime).toBe("nodejs");
    expect(mod.dynamic).toBe("force-dynamic");
  });
});

describe("the save relay", () => {
  const save = ROUTES[0];

  it("forwards the body unchanged — the allowlist is FastAPI's, not the relay's", async () => {
    await save.call(req(save));
    expect(saveStrategy).toHaveBeenCalledWith("browser-token", WRITE);
  });

  it("answers malformed JSON with 400 and never calls the backend", async () => {
    const response = await save.call(req(save, {}, "{not json"));
    expect(response.status).toBe(400);
    expect(saveStrategy).not.toHaveBeenCalled();
  });

  it("forwards a stale-tab 409 as 409 with its fixed code", async () => {
    const { ApiError } = await import("@/lib/api/client");
    saveStrategy.mockRejectedValue(new ApiError(409, { detail: "stale_profile" }));
    const response = await save.call(req(save));
    expect(response.status).toBe(409);
    expect(await response.json()).toEqual({ ok: false, detail: "stale_profile" });
  });

  it("forwards a 422 as field names and codes only", async () => {
    const { ApiError } = await import("@/lib/api/client");
    saveStrategy.mockRejectedValue(
      new ApiError(422, {
        detail: [
          { field: "entry_rules", problem: "too_long", input: "SENSITIVE rule text" },
          { msg: "no field here" },
        ],
      }),
    );
    const response = await save.call(req(save));
    expect(response.status).toBe(422);
    const body = await response.json();
    expect(body).toEqual({ ok: false, detail: [{ field: "entry_rules", problem: "too_long" }] });
    expect(JSON.stringify(body)).not.toContain("SENSITIVE");
  });
});

describe("the insights relay", () => {
  const insights = ROUTES[2];

  it("forwards the named group unchanged and adds nothing", async () => {
    await insights.call(req(insights));
    expect(appendStrategyInsight).toHaveBeenCalledWith("browser-token", {
      field: "bias",
      user_value: "bearish",
      expected_revision: null,
    });
  });

  it.each(["no_profile", "rules_full", "stale_profile"])(
    "forwards the %s refusal as a 409 with its code",
    async (code) => {
      const { ApiError } = await import("@/lib/api/client");
      appendStrategyInsight.mockRejectedValue(new ApiError(409, { detail: code }));
      const response = await insights.call(req(insights));
      expect(response.status).toBe(409);
      expect(await response.json()).toEqual({ ok: false, detail: code });
    },
  );
});

describe.each(ROUTES)("the $label relay's error bodies", (route) => {
  it("leaks no other backend body, at any status", async () => {
    const { ApiError } = await import("@/lib/api/client");
    for (const [status, detail] of [
      [404, "Not Found"],
      [409, "owner 7 row 12 is locked"],
      [422, "owner 7 has no such field"],
      [500, "Traceback: owner 7"],
      [503, "db down at 10.0.0.4"],
    ] as const) {
      route.backend.mockRejectedValue(new ApiError(status, { detail }));
      const response = await route.call(req(route));
      expect(response.status).toBe(status);
      const body = await response.json();
      expect(body).toEqual({ ok: false });
    }
  });

  it("reports a non-ApiError fault as 502 and says nothing about it", async () => {
    route.backend.mockRejectedValue(new Error("connect ECONNREFUSED 10.0.0.4:8000"));
    const response = await route.call(req(route));
    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ ok: false });
  });
});
