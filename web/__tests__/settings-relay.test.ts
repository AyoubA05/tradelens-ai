import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The six Settings relays under `app/api/settings/`.
 *
 * The security shape is shared and load-bearing: fail-shut CSRF *before* the
 * session is read, the session from the cookie only, the eligibility gate, and
 * nothing reaching the backend until all three pass. Two of these routes erase
 * data, so the failure mapping is pinned too: a blocked screenshot cleanup
 * crosses as a fixed code and one boolean, never counts or keys, and account
 * deletion clears the session cookie only after the backend's 204.
 */

const {
  writeTimezone,
  loadSampleTrades,
  clearSampleTrades,
  exportTradesCsv,
  importTradesCsv,
  deleteAllTrades,
  deleteAccount,
  authenticateSessionToken,
} = vi.hoisted(() => ({
  writeTimezone: vi.fn(),
  loadSampleTrades: vi.fn(),
  clearSampleTrades: vi.fn(),
  exportTradesCsv: vi.fn(),
  importTradesCsv: vi.fn(),
  deleteAllTrades: vi.fn(),
  deleteAccount: vi.fn(),
  authenticateSessionToken: vi.fn(),
}));

vi.mock("@/lib/app/settings", () => ({
  writeTimezone,
  loadSampleTrades,
  clearSampleTrades,
  exportTradesCsv,
  importTradesCsv,
  deleteAllTrades,
  deleteAccount,
}));

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

type Handler = (request: Request) => Promise<Response>;

type Route = {
  label: string;
  method: "GET" | "PUT" | "POST" | "DELETE";
  path: string;
  body: unknown;
  backend: ReturnType<typeof vi.fn>;
  load: () => Promise<Handler>;
};

const ROUTES: Route[] = [
  {
    label: "timezone",
    method: "PUT",
    path: "/api/settings/timezone",
    body: { timezone: "UTC" },
    backend: writeTimezone,
    load: async () => (await import("@/app/api/settings/timezone/route")).PUT,
  },
  {
    label: "load samples",
    method: "POST",
    path: "/api/settings/sample-trades",
    body: undefined,
    backend: loadSampleTrades,
    load: async () => (await import("@/app/api/settings/sample-trades/route")).POST,
  },
  {
    label: "clear samples",
    method: "DELETE",
    path: "/api/settings/sample-trades",
    body: undefined,
    backend: clearSampleTrades,
    load: async () => (await import("@/app/api/settings/sample-trades/route")).DELETE,
  },
  {
    label: "export",
    method: "GET",
    path: "/api/settings/export",
    body: undefined,
    backend: exportTradesCsv,
    load: async () => (await import("@/app/api/settings/export/route")).GET,
  },
  {
    label: "import",
    method: "POST",
    path: "/api/settings/import",
    body: { csv: "trade_date,asset\n" },
    backend: importTradesCsv,
    load: async () => (await import("@/app/api/settings/import/route")).POST,
  },
  {
    label: "delete trades",
    method: "POST",
    path: "/api/settings/delete-trades",
    body: { confirm: "DELETE" },
    backend: deleteAllTrades,
    load: async () => (await import("@/app/api/settings/delete-trades/route")).POST,
  },
  {
    label: "delete account",
    method: "POST",
    path: "/api/settings/delete-account",
    body: { confirm: "DELETE MY ACCOUNT" },
    backend: deleteAccount,
    load: async () => (await import("@/app/api/settings/delete-account/route")).POST,
  },
];

function req(route: Route, headers: Record<string, string> = {}, raw?: string) {
  const body = raw ?? (route.body === undefined ? undefined : JSON.stringify(route.body));
  return new Request(`https://site.test${route.path}`, {
    method: route.method,
    headers: {
      cookie: "tl_session=browser-token",
      origin: "https://site.test",
      "content-type": "application/json",
      ...headers,
    },
    body: route.method === "GET" ? undefined : body,
  });
}

const byLabel = (label: string) => ROUTES.find((r) => r.label === label)!;

beforeEach(() => {
  vi.resetModules();
  for (const fn of [
    writeTimezone,
    loadSampleTrades,
    clearSampleTrades,
    importTradesCsv,
    deleteAllTrades,
  ]) {
    fn.mockReset().mockResolvedValue({});
  }
  exportTradesCsv.mockReset().mockResolvedValue({ filename: "trades.csv", row_count: 0, csv: "" });
  deleteAccount.mockReset().mockResolvedValue(undefined);
  authenticateSessionToken.mockReset().mockResolvedValue(eligibleUser);
  process.env.SITE_ORIGIN = "https://site.test";
});

describe.each(ROUTES)("the $label relay's authorization", (route) => {
  it("refuses a missing SITE_ORIGIN with 403 without ever reading the session", async () => {
    delete process.env.SITE_ORIGIN;
    const response = await (await route.load())(req(route));
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ ok: false });
    expect(authenticateSessionToken).not.toHaveBeenCalled();
    expect(route.backend).not.toHaveBeenCalled();
  });

  it("refuses a cross-origin request with 403", async () => {
    const response = await (await route.load())(req(route, { origin: "https://evil.test" }));
    expect(response.status).toBe(403);
    expect(route.backend).not.toHaveBeenCalled();
  });

  it("refuses with 401 when there is no session", async () => {
    authenticateSessionToken.mockResolvedValue(null);
    const response = await (await route.load())(req(route));
    expect(response.status).toBe(401);
    expect(route.backend).not.toHaveBeenCalled();
  });

  it("refuses an ineligible account with 403 before reaching the backend", async () => {
    authenticateSessionToken.mockResolvedValue({ ...eligibleUser, appSurface: "streamlit" });
    const response = await (await route.load())(req(route));
    expect(response.status).toBe(403);
    expect(route.backend).not.toHaveBeenCalled();
  });

  it("refuses an unverified account with 403 before reaching the backend", async () => {
    authenticateSessionToken.mockResolvedValue({ ...eligibleUser, emailVerifiedAt: null });
    const response = await (await route.load())(req(route));
    expect(response.status).toBe(403);
    expect(route.backend).not.toHaveBeenCalled();
  });

  it("sends only the session token upstream, never a browser-named owner", async () => {
    await (await route.load())(req(route));
    expect(route.backend.mock.calls[0]?.[0]).toBe("browser-token");
  });

  it("answers with no-store and no referrer", async () => {
    const response = await (await route.load())(req(route));
    expect(response.headers.get("Cache-Control")).toBe("no-store, private");
    expect(response.headers.get("Referrer-Policy")).toBe("no-referrer");
  });

  it("is dynamic and node-runtime", async () => {
    const modules: Record<string, () => Promise<{ runtime: string; dynamic: string }>> = {
      timezone: () => import("@/app/api/settings/timezone/route"),
      "load samples": () => import("@/app/api/settings/sample-trades/route"),
      "clear samples": () => import("@/app/api/settings/sample-trades/route"),
      export: () => import("@/app/api/settings/export/route"),
      import: () => import("@/app/api/settings/import/route"),
      "delete trades": () => import("@/app/api/settings/delete-trades/route"),
      "delete account": () => import("@/app/api/settings/delete-account/route"),
    };
    const mod = await modules[route.label]();
    expect(mod.runtime).toBe("nodejs");
    expect(mod.dynamic).toBe("force-dynamic");
  });
});

describe("bodies are forwarded unchanged — the allowlists are FastAPI's", () => {
  it.each(["timezone", "import", "delete trades", "delete account"])(
    "%s forwards exactly what the browser sent",
    async (label) => {
      const route = byLabel(label);
      await (await route.load())(req(route));
      expect(route.backend).toHaveBeenCalledWith("browser-token", route.body);
    },
  );

  it.each(["timezone", "delete trades", "delete account"])(
    "%s answers malformed JSON with 400 and never calls the backend",
    async (label) => {
      const route = byLabel(label);
      const response = await (await route.load())(req(route, {}, "{not json"));
      expect(response.status).toBe(400);
      expect(route.backend).not.toHaveBeenCalled();
    },
  );
});

describe("the failure mapping", () => {
  it("maps a cleanup 503 to a fixed code and a boolean, never counts, keys or paths", async () => {
    const { settingsRelayFailure } = await import("@/lib/app/settings-relay");
    const { ApiError } = await import("@/lib/api/client");
    for (const [unresolvable, expected] of [
      [1, true],
      [0, false],
      ["3", false],
      [undefined, false],
    ] as const) {
      const response = settingsRelayFailure(
        new ApiError(503, {
          detail: {
            error: "screenshot_cleanup_failed",
            remaining: 2,
            unresolvable,
            key: "u/9/t/1/secret.png",
          },
        }),
        ApiError,
      );
      expect(response.status).toBe(503);
      const body = await response.json();
      expect(body).toEqual({ ok: false, detail: "screenshot_cleanup_failed", unresolvable: expected });
      expect(JSON.stringify(body)).not.toMatch(/secret|remaining|u\/9/);
    }
  });

  it("forwards a 422 by field and code only", async () => {
    const { settingsRelayFailure } = await import("@/lib/app/settings-relay");
    const { ApiError } = await import("@/lib/api/client");
    const response = settingsRelayFailure(
      new ApiError(422, {
        detail: [
          { field: "csv", problem: "too_many_rows", input: "SECRET row text" },
          { type: "literal_error", loc: ["body", "confirm"], msg: "Input should be 'DELETE'" },
        ],
      }),
      ApiError,
    );
    const body = await response.json();
    expect(response.status).toBe(422);
    expect(body).toEqual({ ok: false, detail: [{ field: "csv", problem: "too_many_rows" }] });
    expect(JSON.stringify(body)).not.toContain("SECRET");
  });

  it("says nothing but the status for any other backend failure", async () => {
    const { settingsRelayFailure } = await import("@/lib/app/settings-relay");
    const { ApiError } = await import("@/lib/api/client");
    const response = settingsRelayFailure(new ApiError(404, { detail: "account 9 is gone" }), ApiError);
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ ok: false });
  });

  it("turns a non-ApiError fault into a 502 with no detail", async () => {
    const { settingsRelayFailure } = await import("@/lib/app/settings-relay");
    const { ApiError } = await import("@/lib/api/client");
    const response = settingsRelayFailure(new Error("ECONNREFUSED 10.0.0.4"), ApiError);
    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ ok: false });
  });
});

describe("the export relay", () => {
  it("serves the CSV as an attachment with a fixed filename and no-store", async () => {
    exportTradesCsv.mockResolvedValue({ filename: "trades.csv", row_count: 1, csv: "a,b\n1,'=2\n" });
    const route = byLabel("export");
    const response = await (await route.load())(req(route));
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe("text/csv; charset=utf-8");
    expect(response.headers.get("Content-Disposition")).toBe('attachment; filename="trades.csv"');
    expect(response.headers.get("Cache-Control")).toBe("no-store, private");
    expect(await response.text()).toBe("a,b\n1,'=2\n");
  });
});

describe("the import relay", () => {
  it("refuses a request declaring more than 1 MB before reading or forwarding it", async () => {
    const route = byLabel("import");
    const response = await (await route.load())(
      req(route, { "content-length": String(1_048_577) }),
    );
    expect(response.status).toBe(413);
    expect(importTradesCsv).not.toHaveBeenCalled();
  });

  it("refuses an oversized body even when Content-Length understates it", async () => {
    const route = byLabel("import");
    const big = JSON.stringify({ csv: "x".repeat(1_048_577) });
    const response = await (await route.load())(req(route, { "content-length": "10" }, big));
    expect(response.status).toBe(413);
    expect(importTradesCsv).not.toHaveBeenCalled();
  });

  it("answers malformed JSON with 400", async () => {
    const route = byLabel("import");
    const response = await (await route.load())(req(route, {}, "{nope"));
    expect(response.status).toBe(400);
    expect(importTradesCsv).not.toHaveBeenCalled();
  });
});

describe("the delete-account relay", () => {
  it("clears the session cookie only after the account is really deleted", async () => {
    const route = byLabel("delete account");
    const response = await (await route.load())(req(route));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true, next: "/account-deleted" });
    expect(response.headers.get("set-cookie") ?? "").toMatch(/tl_session=;/);
  });

  it.each([
    [503, { detail: { error: "screenshot_cleanup_failed", remaining: 1, unresolvable: 0 } }],
    [404, { detail: "Not Found" }],
    [422, { detail: [{ type: "literal_error", loc: ["body", "confirm"], msg: "x" }] }],
  ])("keeps the session cookie when the backend answers %i", async (status, body) => {
    const { ApiError } = await import("@/lib/api/client");
    deleteAccount.mockRejectedValue(new ApiError(status, body));
    const route = byLabel("delete account");
    const response = await (await route.load())(req(route));
    expect(response.status).toBe(status);
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("keeps the session cookie when the backend is unreachable", async () => {
    deleteAccount.mockRejectedValue(new Error("socket hang up"));
    const route = byLabel("delete account");
    const response = await (await route.load())(req(route));
    expect(response.status).toBe(502);
    expect(response.headers.get("set-cookie")).toBeNull();
  });
});

describe("the delete-trades relay", () => {
  it("reports a blocked cleanup as 503, never as a deletion", async () => {
    const { ApiError } = await import("@/lib/api/client");
    deleteAllTrades.mockRejectedValue(
      new ApiError(503, { detail: { error: "screenshot_cleanup_failed", remaining: 0, unresolvable: 2 } }),
    );
    const route = byLabel("delete trades");
    const response = await (await route.load())(req(route));
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({
      ok: false,
      detail: "screenshot_cleanup_failed",
      unresolvable: true,
    });
  });
});
