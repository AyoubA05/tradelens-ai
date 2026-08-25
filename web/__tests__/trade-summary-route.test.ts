import { beforeEach, describe, expect, it, vi } from "vitest";

const { enqueueTradeSummaryRequest, fetchTradeSummaryJob, authenticateSessionToken } = vi.hoisted(
  () => ({
    enqueueTradeSummaryRequest: vi.fn(),
    fetchTradeSummaryJob: vi.fn(),
    authenticateSessionToken: vi.fn(),
  }),
);

vi.mock("@/lib/app/trades", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/app/trades")>();
  return { ...actual, enqueueTradeSummaryRequest, fetchTradeSummaryJob };
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

function request(method: string, url: string, body?: unknown, origin = "https://site.test") {
  return new Request(url, {
    method,
    headers: {
      cookie: "tl_session=browser-token",
      origin,
      ...(body === undefined ? {} : { "content-type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

beforeEach(() => {
  vi.resetModules();
  enqueueTradeSummaryRequest.mockReset();
  fetchTradeSummaryJob.mockReset();
  authenticateSessionToken.mockReset().mockResolvedValue(eligibleUser);
  process.env.SITE_ORIGIN = "https://site.test";
});

describe("POST /api/trades/summary", () => {
  it("relays the observable body and backend status without adding an owner", async () => {
    const body = { from: "2026-08-01", to: "2026-08-31", asset: "NQ" };
    enqueueTradeSummaryRequest.mockResolvedValue({ job_id: 12, status: "queued", created: true });
    const { POST } = await import("@/app/api/trades/summary/route");

    const response = await POST(request("POST", "https://site.test/api/trades/summary", body));

    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({ job_id: 12, status: "queued", created: true });
    expect(enqueueTradeSummaryRequest).toHaveBeenCalledWith("browser-token", body);
    expect(JSON.stringify(enqueueTradeSummaryRequest.mock.calls[0])).not.toMatch(
      /user|owner|account|uid/i,
    );
    expect(response.headers.get("cache-control")).toContain("no-store");
  });

  it("fails shut on cross-site or app-ineligible requests before FastAPI", async () => {
    const { POST } = await import("@/app/api/trades/summary/route");
    const crossSite = await POST(
      request("POST", "https://site.test/api/trades/summary", {}, "https://evil.test"),
    );
    expect(crossSite.status).toBe(403);

    authenticateSessionToken.mockResolvedValue({ ...eligibleUser, appSurface: "streamlit" });
    const ineligible = await POST(
      request("POST", "https://site.test/api/trades/summary", {}),
    );
    expect(ineligible.status).toBe(403);
    expect(enqueueTradeSummaryRequest).not.toHaveBeenCalled();
  });
});

describe("both relay routes with SITE_ORIGIN unset", () => {
  // The nine app/api/auth/* routes fall back to a permissive same-origin check
  // when SITE_ORIGIN is absent. These two deliberately do not: a summary is a
  // paid call, so a missing origin setting must fail shut, never open.
  it("refuses rather than falling back to a permissive origin check", async () => {
    delete process.env.SITE_ORIGIN;
    const { POST } = await import("@/app/api/trades/summary/route");
    const { GET } = await import("@/app/api/trades/summary/[jobId]/route");

    const enqueue = await POST(
      request("POST", "https://site.test/api/trades/summary", {}),
    );
    const poll = await GET(request("GET", "https://site.test/api/trades/summary/12"), {
      params: Promise.resolve({ jobId: "12" }),
    });

    expect(enqueue.status).toBe(403);
    expect(poll.status).toBe(403);
    expect(enqueueTradeSummaryRequest).not.toHaveBeenCalled();
    expect(fetchTradeSummaryJob).not.toHaveBeenCalled();
    expect(authenticateSessionToken).not.toHaveBeenCalled();
  });
});

describe("GET /api/trades/summary/[jobId]", () => {
  it("relays the actual owner-scoped job response", async () => {
    const payload = { job_id: 12, status: "running", result: null, error: null };
    fetchTradeSummaryJob.mockResolvedValue(payload);
    const { GET } = await import("@/app/api/trades/summary/[jobId]/route");
    const response = await GET(
      request("GET", "https://site.test/api/trades/summary/12"),
      { params: Promise.resolve({ jobId: "12" }) },
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(payload);
    expect(fetchTradeSummaryJob).toHaveBeenCalledWith("browser-token", 12);
    expect(response.headers.get("cache-control")).toContain("no-store");
  });

  it("passes a backend 404 through and rejects numeric aliases locally", async () => {
    const { ApiError } = await import("@/lib/api/client");
    fetchTradeSummaryJob.mockRejectedValue(new ApiError(404));
    const { GET } = await import("@/app/api/trades/summary/[jobId]/route");
    const missing = await GET(request("GET", "https://site.test/api/trades/summary/12"), {
      params: Promise.resolve({ jobId: "12" }),
    });
    const alias = await GET(request("GET", "https://site.test/api/trades/summary/1e3"), {
      params: Promise.resolve({ jobId: "1e3" }),
    });

    expect(missing.status).toBe(404);
    expect(alias.status).toBe(404);
    expect(fetchTradeSummaryJob).toHaveBeenCalledOnce();
  });
});
