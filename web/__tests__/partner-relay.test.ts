import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The two AI Partner relays: POST /api/partner/turns and
 * POST /api/trades/{id}/partner/turns.
 *
 * These are the only routes in the app that spend money per call, so the
 * fail-shut order matters twice over: CSRF *before* the session is read, the
 * session from the cookie only, the eligibility gate — and nothing reaches
 * the backend until all three pass.
 *
 * On the way back, only the fixed codes this feature defines cross to the
 * browser. Neither an upstream message nor anything the model said may reach
 * a trader through an error path, and a 404 says nothing at all: whether the
 * trade is missing or someone else's is exactly what it must not reveal.
 */

const { postPartnerTurn, postTradePartnerTurn, authenticateSessionToken } = vi.hoisted(() => ({
  postPartnerTurn: vi.fn(),
  postTradePartnerTurn: vi.fn(),
  authenticateSessionToken: vi.fn(),
}));

vi.mock("@/lib/app/partner", () => ({ postPartnerTurn, postTradePartnerTurn }));

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

const TURN = {
  question: "Why did I move my stop on the second London trade?",
  conversation_id: null,
  transcript: [],
  client_turn_id: "0123456789abcdef",
};

const REPLY = {
  conversation_id: "c-1",
  turns: [],
  evidence: [],
  screenshot_attached: false,
};

type Route = {
  label: string;
  path: string;
  body: unknown;
  backend: ReturnType<typeof vi.fn>;
  modulePath: string;
  call: (request: Request) => Promise<Response>;
};

const globalRoute: Route = {
  label: "global",
  path: "/api/partner/turns",
  body: TURN,
  backend: postPartnerTurn,
  modulePath: "@/app/api/partner/turns/route",
  call: async (r) => (await import("@/app/api/partner/turns/route")).POST(r),
};

const tradeRoute: Route = {
  label: "per-trade",
  path: "/api/trades/42/partner/turns",
  body: { ...TURN, include_screenshot: true },
  backend: postTradePartnerTurn,
  modulePath: "@/app/api/trades/[id]/partner/turns/route",
  call: async (r) =>
    (await import("@/app/api/trades/[id]/partner/turns/route")).POST(r, {
      params: Promise.resolve({ id: "42" }),
    }),
};

const ROUTES = [globalRoute, tradeRoute];

function req(route: Route, headers: Record<string, string> = {}, raw?: string) {
  return new Request(`https://site.test${route.path}`, {
    method: "POST",
    headers: {
      cookie: "tl_session=browser-token",
      origin: "https://site.test",
      "content-type": "application/json",
      ...headers,
    },
    body: raw ?? JSON.stringify(route.body),
  });
}

beforeEach(() => {
  vi.resetModules();
  postPartnerTurn.mockReset().mockResolvedValue(REPLY);
  postTradePartnerTurn.mockReset().mockResolvedValue(REPLY);
  authenticateSessionToken.mockReset().mockResolvedValue(eligibleUser);
  process.env.SITE_ORIGIN = "https://site.test";
});

describe.each(ROUTES)("the $label partner relay's authorization", (route) => {
  it("refuses a missing SITE_ORIGIN with 403 without ever reading the session", async () => {
    delete process.env.SITE_ORIGIN;
    const response = await route.call(req(route));
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ ok: false });
    expect(authenticateSessionToken).not.toHaveBeenCalled();
    expect(route.backend).not.toHaveBeenCalled();
  });

  it("refuses a cross-origin request with 403 — nothing is spent", async () => {
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
    authenticateSessionToken.mockResolvedValue({
      ...eligibleUser,
      appSurface: "streamlit",
    });
    const response = await route.call(req(route));
    expect(response.status).toBe(403);
    expect(route.backend).not.toHaveBeenCalled();
  });

  it("lets an account through that has not completed the Strategy Profile", async () => {
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

  it("answers malformed JSON with 400 and never calls the backend", async () => {
    const response = await route.call(req(route, {}, "{not json"));
    expect(response.status).toBe(400);
    expect(route.backend).not.toHaveBeenCalled();
  });

  it("is dynamic, node-runtime, and allowed to outlive the default budget", async () => {
    const mod = await import(
      route.label === "global"
        ? "@/app/api/partner/turns/route"
        : "@/app/api/trades/[id]/partner/turns/route"
    );
    expect(mod.runtime).toBe("nodejs");
    expect(mod.dynamic).toBe("force-dynamic");
    expect(mod.maxDuration).toBe(60);
  });

  it("answers every response with no-store and no referrer", async () => {
    const response = await route.call(req(route));
    expect(response.headers.get("Cache-Control")).toBe("no-store, private");
    expect(response.headers.get("Referrer-Policy")).toBe("no-referrer");
  });
});

describe.each(ROUTES)("the $label partner relay's failure mapping", (route) => {
  async function reject(status: number, body: unknown) {
    const { ApiError } = await import("@/lib/api/client");
    route.backend.mockRejectedValue(new ApiError(status, body));
    return route.call(req(route));
  }

  it.each(["transcript_invalid", "conversation_full", "no_trades", "duplicate_turn"])(
    "forwards the 409 code %s unchanged",
    async (code) => {
      const response = await reject(409, { detail: code });
      expect(response.status).toBe(409);
      expect(await response.json()).toEqual({ ok: false, detail: code });
    },
  );

  it("does not forward a 409 code it does not define", async () => {
    const response = await reject(409, { detail: "some_upstream_state" });
    expect(response.status).toBe(409);
    expect(await response.json()).toEqual({ ok: false });
  });

  it("forwards a 422 as field names and codes only", async () => {
    const response = await reject(422, {
      detail: [
        {
          field: "question",
          problem: "too_long",
          input: "SENSITIVE question text",
        },
        { msg: "no field here" },
      ],
    });
    expect(response.status).toBe(422);
    const body = await response.json();
    expect(body).toEqual({
      ok: false,
      detail: [{ field: "question", problem: "too_long" }],
    });
    expect(JSON.stringify(body)).not.toContain("SENSITIVE");
  });

  it("says rate_limited on a 429 from the status, not from the body", async () => {
    const response = await reject(429, {
      detail: "you have used 60 of 60 turns, retry at …",
    });
    expect(response.status).toBe(429);
    expect(await response.json()).toEqual({
      ok: false,
      detail: "rate_limited",
    });
  });

  it("says partner_unavailable on a 503 and never the provider's reason", async () => {
    const response = await reject(503, {
      detail: "anthropic: overloaded_error (request id req_SENSITIVE)",
    });
    expect(response.status).toBe(503);
    const body = await response.json();
    expect(body).toEqual({ ok: false, detail: "partner_unavailable" });
    expect(JSON.stringify(body)).not.toContain("SENSITIVE");
  });

  it("says nothing at all on a 404", async () => {
    const response = await reject(404, {
      detail: "trade 42 belongs to user 9",
    });
    expect(response.status).toBe(404);
    const body = await response.json();
    expect(body).toEqual({ ok: false });
    expect(JSON.stringify(body)).not.toContain("9");
  });

  it("turns a non-ApiError fault into a 502 with no detail", async () => {
    route.backend.mockRejectedValue(new Error("ECONNREFUSED 10.0.0.4:8000"));
    const response = await route.call(req(route));
    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body).toEqual({ ok: false });
    expect(JSON.stringify(body)).not.toContain("10.0.0.4");
  });
});

describe("the global partner relay", () => {
  it("forwards the body unchanged — the allowlist is FastAPI's, not the relay's", async () => {
    await globalRoute.call(req(globalRoute));
    expect(postPartnerTurn).toHaveBeenCalledWith("browser-token", TURN);
  });

  it("returns the signed turns the backend minted, untouched", async () => {
    const signed = {
      conversation_id: "c-9",
      turns: [
        { idx: 0, role: "user", text: "Why?", iat: 1, mac: "a".repeat(64) },
        {
          idx: 1,
          role: "assistant",
          text: "Because…",
          iat: 2,
          mac: "b".repeat(64),
        },
      ],
      evidence: [
        {
          kind: "trade",
          label: "NQ 2026-09-01",
          occurred_on: "2026-09-01",
          trade_id: 42,
        },
      ],
      screenshot_attached: false,
    };
    postPartnerTurn.mockResolvedValue(signed);
    const response = await globalRoute.call(req(globalRoute));
    expect(await response.json()).toEqual(signed);
  });
});

describe("the per-trade partner relay", () => {
  it("takes the trade from the path and passes it as its own argument", async () => {
    await tradeRoute.call(req(tradeRoute));
    expect(postTradePartnerTurn).toHaveBeenCalledWith("browser-token", 42, {
      ...TURN,
      include_screenshot: true,
    });
  });

  it.each(["0", "-1", "1.5", "abc", "42abc", "", " 42"])(
    "answers the unusable trade id %j with the same empty 404",
    async (id) => {
      const response = await (
        await import("@/app/api/trades/[id]/partner/turns/route")
      ).POST(req(tradeRoute), { params: Promise.resolve({ id }) });
      expect(response.status).toBe(404);
      expect(await response.json()).toEqual({ ok: false });
      expect(postTradePartnerTurn).not.toHaveBeenCalled();
    },
  );
});
