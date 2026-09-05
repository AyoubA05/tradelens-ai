import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The Phase 5 relays: `POST/PATCH /api/trades/{id}/analysis`,
 * `POST /api/trades/{id}/journal`, `POST /api/trades/{id}/grade`, and the
 * three per-kind job polls.
 *
 * The relay's one security property is that it fails SHUT when
 * `SITE_ORIGIN` is unset. That is a deliberate divergence from the nine
 * `app/api/auth/*` routes; do not "fix" it to match them.
 */

const {
  authenticateSessionToken,
  enqueueAnalysis,
  enqueueJournal,
  enqueueGrade,
  fetchAnalysisJob,
  fetchJournalJob,
  fetchGradeJob,
  patchAnalysisLabels,
} = vi.hoisted(() => ({
  authenticateSessionToken: vi.fn(),
  enqueueAnalysis: vi.fn(),
  enqueueJournal: vi.fn(),
  enqueueGrade: vi.fn(),
  fetchAnalysisJob: vi.fn(),
  fetchJournalJob: vi.fn(),
  fetchGradeJob: vi.fn(),
  patchAnalysisLabels: vi.fn(),
}));

vi.mock("@/lib/auth/session", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/auth/session")>();
  return { ...actual, authenticateSessionToken };
});

vi.mock("@/lib/app/trade-analysis", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/app/trade-analysis")>();
  return {
    ...actual,
    enqueueAnalysis,
    enqueueJournal,
    enqueueGrade,
    fetchAnalysisJob,
    fetchJournalJob,
    fetchGradeJob,
    patchAnalysisLabels,
  };
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

const ORIGINAL_SITE_ORIGIN = process.env.SITE_ORIGIN;

beforeEach(() => {
  vi.clearAllMocks();
  process.env.SITE_ORIGIN = "https://site.test";
  authenticateSessionToken.mockResolvedValue(eligibleUser);
});

afterEach(() => {
  if (ORIGINAL_SITE_ORIGIN === undefined) delete process.env.SITE_ORIGIN;
  else process.env.SITE_ORIGIN = ORIGINAL_SITE_ORIGIN;
});

function post(path: string, body: unknown, headers: Record<string, string> = {}) {
  return new Request(`https://site.test${path}`, {
    method: "POST",
    headers: {
      cookie: "tl_session=browser-token",
      origin: "https://site.test",
      "content-type": "application/json",
      ...headers,
    },
    body: JSON.stringify(body),
  });
}

function get(path: string, headers: Record<string, string> = {}) {
  return new Request(`https://site.test${path}`, {
    method: "GET",
    headers: {
      cookie: "tl_session=browser-token",
      origin: "https://site.test",
      ...headers,
    },
  });
}

describe("authorizeTradeAnalysisRelay", () => {
  it("refuses with 403 when SITE_ORIGIN is unset, without reading the session", async () => {
    delete process.env.SITE_ORIGIN;
    const { authorizeTradeAnalysisRelay } = await import("@/lib/app/trade-analysis-relay");
    const result = await authorizeTradeAnalysisRelay(
      new Request("https://site.test/api/trades/1/analysis", {
        method: "POST",
        headers: { origin: "https://site.test", cookie: "tl_session=browser-token" },
      }),
    );
    expect(result).toBeInstanceOf(Response);
    expect((result as Response).status).toBe(403);
    // Fail shut means fail BEFORE the session lookup — the refusal must not
    // depend on whether the caller happens to hold a valid session.
    expect(authenticateSessionToken).not.toHaveBeenCalled();
  });

  it("refuses a cross-origin request even when SITE_ORIGIN is set", async () => {
    const { authorizeTradeAnalysisRelay } = await import("@/lib/app/trade-analysis-relay");
    const result = await authorizeTradeAnalysisRelay(
      new Request("https://site.test/api/trades/1/analysis", {
        method: "POST",
        headers: { origin: "https://evil.example.com", cookie: "tl_session=browser-token" },
      }),
    );
    expect(result).toBeInstanceOf(Response);
    expect((result as Response).status).toBe(403);
    expect(authenticateSessionToken).not.toHaveBeenCalled();
  });

  it("refuses with 401 when the session cookie resolves to nobody", async () => {
    authenticateSessionToken.mockResolvedValue(null);
    const { authorizeTradeAnalysisRelay } = await import("@/lib/app/trade-analysis-relay");
    const result = await authorizeTradeAnalysisRelay(
      new Request("https://site.test/api/trades/1/analysis", {
        method: "POST",
        headers: { origin: "https://site.test", cookie: "tl_session=browser-token" },
      }),
    );
    expect((result as Response).status).toBe(401);
  });

  it("refuses with 403 an account the app surface gate would redirect", async () => {
    authenticateSessionToken.mockResolvedValue({ ...eligibleUser, onboardingCompleted: false });
    const { authorizeTradeAnalysisRelay } = await import("@/lib/app/trade-analysis-relay");
    const result = await authorizeTradeAnalysisRelay(
      new Request("https://site.test/api/trades/1/analysis", {
        method: "POST",
        headers: { origin: "https://site.test", cookie: "tl_session=browser-token" },
      }),
    );
    expect((result as Response).status).toBe(403);
  });

  it("returns the session token for an eligible same-origin caller", async () => {
    const { authorizeTradeAnalysisRelay } = await import("@/lib/app/trade-analysis-relay");
    const result = await authorizeTradeAnalysisRelay(
      new Request("https://site.test/api/trades/1/analysis", {
        method: "POST",
        headers: { origin: "https://site.test", cookie: "tl_session=browser-token" },
      }),
    );
    expect(result).not.toBeInstanceOf(Response);
    expect((result as { token: string }).token).toBe("browser-token");
  });
});

describe("POST /api/trades/{id}/analysis", () => {
  it("forwards the screenshot id and returns 202 with the backend's job handle", async () => {
    enqueueAnalysis.mockResolvedValue({ job_id: 31, status: "queued", created: true });
    const { POST } = await import("@/app/api/trades/[id]/analysis/route");
    const response = await POST(post("/api/trades/42/analysis", { screenshot_id: 12 }), {
      params: Promise.resolve({ id: "42" }),
    });
    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({ job_id: 31, status: "queued", created: true });
    expect(enqueueAnalysis).toHaveBeenCalledWith("browser-token", 42, 12);
    expect(response.headers.get("Cache-Control")).toBe("no-store, private");
  });

  it("rejects a trade id that is not a plain positive integer, without calling the backend", async () => {
    const { POST } = await import("@/app/api/trades/[id]/analysis/route");
    for (const id of ["1e3", "0x10", " 1", "0", "-1", "99999999999999999999"]) {
      const response = await POST(post(`/api/trades/${id}/analysis`, { screenshot_id: 12 }), {
        params: Promise.resolve({ id }),
      });
      expect(response.status, id).toBe(404);
    }
    expect(enqueueAnalysis).not.toHaveBeenCalled();
  });

  it("rejects a non-integer screenshot id without calling the backend", async () => {
    const { POST } = await import("@/app/api/trades/[id]/analysis/route");
    const response = await POST(post("/api/trades/42/analysis", { screenshot_id: "abc" }), {
      params: Promise.resolve({ id: "42" }),
    });
    expect(response.status).toBe(400);
    expect(enqueueAnalysis).not.toHaveBeenCalled();
  });

  it("forwards the backend's detail on 429 and on 503, but not on 404", async () => {
    const { ApiError } = await import("@/lib/api/client");
    const { POST } = await import("@/app/api/trades/[id]/analysis/route");

    enqueueAnalysis.mockRejectedValueOnce(
      new ApiError(429, { detail: "You've reached 20 AI analyses for today." }),
    );
    const limited = await POST(post("/api/trades/42/analysis", { screenshot_id: 12 }), {
      params: Promise.resolve({ id: "42" }),
    });
    expect(limited.status).toBe(429);
    expect(await limited.json()).toMatchObject({
      detail: "You've reached 20 AI analyses for today.",
    });

    enqueueAnalysis.mockRejectedValueOnce(
      new ApiError(503, { detail: "AI review is unavailable right now." }),
    );
    const unavailable = await POST(post("/api/trades/42/analysis", { screenshot_id: 12 }), {
      params: Promise.resolve({ id: "42" }),
    });
    expect(unavailable.status).toBe(503);
    expect(await unavailable.json()).toMatchObject({
      detail: "AI review is unavailable right now.",
    });

    // A 404 is an ownership answer. Its body says nothing, and nothing the
    // backend attached to it may leak through here.
    enqueueAnalysis.mockRejectedValueOnce(new ApiError(404, { detail: "trade 42 not found" }));
    const missing = await POST(post("/api/trades/42/analysis", { screenshot_id: 12 }), {
      params: Promise.resolve({ id: "42" }),
    });
    expect(missing.status).toBe(404);
    expect(await missing.json()).toEqual({ ok: false });
  });

  it("turns a non-ApiError failure into 502 and leaks nothing about it", async () => {
    enqueueAnalysis.mockRejectedValue(new Error("ECONNREFUSED 10.0.0.4:8000"));
    const { POST } = await import("@/app/api/trades/[id]/analysis/route");
    const response = await POST(post("/api/trades/42/analysis", { screenshot_id: 12 }), {
      params: Promise.resolve({ id: "42" }),
    });
    expect(response.status).toBe(502);
    expect(JSON.stringify(await response.json())).not.toContain("ECONNREFUSED");
  });
});

describe("PATCH /api/trades/{id}/analysis", () => {
  it("forwards the label patch body verbatim and returns the updated labels", async () => {
    patchAnalysisLabels.mockResolvedValue({
      bias: "bearish",
      detected_setup: null,
      trade_quality: null,
      matched_strategy: null,
      user_grade: null,
      confirmed_fields: ["bias"],
    });
    const { PATCH } = await import("@/app/api/trades/[id]/analysis/route");
    const request = new Request("https://site.test/api/trades/42/analysis", {
      method: "PATCH",
      headers: {
        cookie: "tl_session=browser-token",
        origin: "https://site.test",
        "content-type": "application/json",
      },
      body: JSON.stringify({ bias: "bearish" }),
    });
    const response = await PATCH(request, { params: Promise.resolve({ id: "42" }) });
    expect(response.status).toBe(200);
    expect(patchAnalysisLabels).toHaveBeenCalledWith("browser-token", 42, { bias: "bearish" });
    expect(await response.json()).toMatchObject({ confirmed_fields: ["bias"] });
  });

  it("forwards the backend's detail on 409", async () => {
    const { ApiError } = await import("@/lib/api/client");
    patchAnalysisLabels.mockRejectedValue(
      new ApiError(409, { detail: "This trade has not been analysed yet." }),
    );
    const { PATCH } = await import("@/app/api/trades/[id]/analysis/route");
    const request = new Request("https://site.test/api/trades/42/analysis", {
      method: "PATCH",
      headers: {
        cookie: "tl_session=browser-token",
        origin: "https://site.test",
        "content-type": "application/json",
      },
      body: JSON.stringify({ bias: "bearish" }),
    });
    const response = await PATCH(request, { params: Promise.resolve({ id: "42" }) });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({
      detail: "This trade has not been analysed yet.",
    });
  });
});

describe("the derived-kind enqueue relays", () => {
  it("POST /api/trades/{id}/journal enqueues without a body", async () => {
    enqueueJournal.mockResolvedValue({ job_id: 8, status: "queued", created: true });
    const { POST } = await import("@/app/api/trades/[id]/journal/route");
    const response = await POST(get("/api/trades/42/journal"), {
      params: Promise.resolve({ id: "42" }),
    });
    expect(response.status).toBe(202);
    expect(enqueueJournal).toHaveBeenCalledWith("browser-token", 42);
  });

  it("POST /api/trades/{id}/grade forwards the 409 detail when no analysis exists", async () => {
    const { ApiError } = await import("@/lib/api/client");
    enqueueGrade.mockRejectedValue(
      new ApiError(409, { detail: "Analyse the chart first, then this trade can be graded." }),
    );
    const { POST } = await import("@/app/api/trades/[id]/grade/route");
    const response = await POST(get("/api/trades/42/grade"), {
      params: Promise.resolve({ id: "42" }),
    });
    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({
      detail: "Analyse the chart first, then this trade can be graded.",
    });
  });
});

describe("the per-kind job polls", () => {
  it("each kind reaches only its own backend route", async () => {
    fetchAnalysisJob.mockResolvedValue({
      job_id: 1,
      kind: "trade_analysis",
      status: "running",
      error: null,
      superseded: false,
    });
    fetchJournalJob.mockResolvedValue({
      job_id: 2,
      kind: "trade_journal",
      status: "running",
      error: null,
      superseded: false,
    });
    fetchGradeJob.mockResolvedValue({
      job_id: 3,
      kind: "trade_grade",
      status: "running",
      error: null,
      superseded: false,
    });

    const analysis = await import("@/app/api/trades/analysis/[jobId]/route");
    const journal = await import("@/app/api/trades/journal/[jobId]/route");
    const grade = await import("@/app/api/trades/grade/[jobId]/route");

    const a = await analysis.GET(get("/api/trades/analysis/1"), {
      params: Promise.resolve({ jobId: "1" }),
    });
    expect(await a.json()).toMatchObject({ kind: "trade_analysis" });
    const j = await journal.GET(get("/api/trades/journal/2"), {
      params: Promise.resolve({ jobId: "2" }),
    });
    expect(await j.json()).toMatchObject({ kind: "trade_journal" });
    const g = await grade.GET(get("/api/trades/grade/3"), {
      params: Promise.resolve({ jobId: "3" }),
    });
    expect(await g.json()).toMatchObject({ kind: "trade_grade" });

    expect(fetchAnalysisJob).toHaveBeenCalledWith("browser-token", 1);
    expect(fetchJournalJob).toHaveBeenCalledWith("browser-token", 2);
    expect(fetchGradeJob).toHaveBeenCalledWith("browser-token", 3);
    // Cross-kind never happens at this layer either.
    expect(fetchAnalysisJob).toHaveBeenCalledTimes(1);
    expect(fetchJournalJob).toHaveBeenCalledTimes(1);
    expect(fetchGradeJob).toHaveBeenCalledTimes(1);
  });

  it("rejects a malformed job id without calling the backend", async () => {
    const { GET } = await import("@/app/api/trades/analysis/[jobId]/route");
    for (const jobId of ["0", "1e3", "0x10", "-4", "abc"]) {
      const response = await GET(get(`/api/trades/analysis/${jobId}`), {
        params: Promise.resolve({ jobId }),
      });
      expect(response.status, jobId).toBe(404);
    }
    expect(fetchAnalysisJob).not.toHaveBeenCalled();
  });

  it("passes a backend 404 through as an opaque 404", async () => {
    const { ApiError } = await import("@/lib/api/client");
    fetchAnalysisJob.mockRejectedValue(new ApiError(404, { detail: "job 9 not found" }));
    const { GET } = await import("@/app/api/trades/analysis/[jobId]/route");
    const response = await GET(get("/api/trades/analysis/9"), {
      params: Promise.resolve({ jobId: "9" }),
    });
    expect(response.status).toBe(404);
    expect(await response.json()).toEqual({ ok: false });
  });

  it("refuses every relay when SITE_ORIGIN is unset", async () => {
    delete process.env.SITE_ORIGIN;
    const analysis = await import("@/app/api/trades/[id]/analysis/route");
    const journal = await import("@/app/api/trades/[id]/journal/route");
    const grade = await import("@/app/api/trades/[id]/grade/route");
    const poll = await import("@/app/api/trades/analysis/[jobId]/route");

    const responses = [
      await analysis.POST(post("/api/trades/42/analysis", { screenshot_id: 1 }), {
        params: Promise.resolve({ id: "42" }),
      }),
      await journal.POST(get("/api/trades/42/journal"), {
        params: Promise.resolve({ id: "42" }),
      }),
      await grade.POST(get("/api/trades/42/grade"), { params: Promise.resolve({ id: "42" }) }),
      await poll.GET(get("/api/trades/analysis/1"), { params: Promise.resolve({ jobId: "1" }) }),
    ];
    for (const response of responses) expect(response.status).toBe(403);
    expect(enqueueAnalysis).not.toHaveBeenCalled();
    expect(enqueueJournal).not.toHaveBeenCalled();
    expect(enqueueGrade).not.toHaveBeenCalled();
    expect(fetchAnalysisJob).not.toHaveBeenCalled();
  });
});
