import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * POST /api/trades/autofill and GET /api/trades/autofill/{jobId} — the
 * relays `AutofillReview` uses (Task D2).
 */

const { enqueueTradeAutofill, fetchTradeAutofillJob, authenticateSessionToken } = vi.hoisted(
  () => ({
    enqueueTradeAutofill: vi.fn(),
    fetchTradeAutofillJob: vi.fn(),
    authenticateSessionToken: vi.fn(),
  }),
);

vi.mock("@/lib/app/trade-autofill", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/app/trade-autofill")>();
  return { ...actual, enqueueTradeAutofill, fetchTradeAutofillJob };
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

function postReq(body: unknown, headers: Record<string, string> = {}) {
  return new Request("https://site.test/api/trades/autofill", {
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

function getReq(headers: Record<string, string> = {}) {
  return new Request("https://site.test/api/trades/autofill/42", {
    method: "GET",
    headers: { cookie: "tl_session=browser-token", origin: "https://site.test", ...headers },
  });
}

async function callPost(request: Request) {
  const { POST } = await import("@/app/api/trades/autofill/route");
  return POST(request);
}

async function callGet(request: Request, jobId = "42") {
  const { GET } = await import("@/app/api/trades/autofill/[jobId]/route");
  return GET(request, { params: Promise.resolve({ jobId }) });
}

beforeEach(() => {
  vi.resetModules();
  enqueueTradeAutofill.mockReset();
  fetchTradeAutofillJob.mockReset();
  authenticateSessionToken.mockReset().mockResolvedValue(eligibleUser);
  process.env.SITE_ORIGIN = "https://site.test";
});

describe("POST /api/trades/autofill", () => {
  it("enqueues with the screenshot id from the body and the session's token", async () => {
    enqueueTradeAutofill.mockResolvedValue({ created: true, job_id: 5, status: "queued" });
    const response = await callPost(postReq({ screenshot_id: 3 }));
    expect(response.status).toBe(202);
    expect(enqueueTradeAutofill).toHaveBeenCalledWith("browser-token", 3);
  });

  it("fails shut when SITE_ORIGIN is unset", async () => {
    delete process.env.SITE_ORIGIN;
    const response = await callPost(postReq({ screenshot_id: 3 }));
    expect(response.status).toBe(403);
    expect(enqueueTradeAutofill).not.toHaveBeenCalled();
  });

  it("rejects a cross-site POST without reaching the backend", async () => {
    const response = await callPost(postReq({ screenshot_id: 3 }, { origin: "https://evil.test" }));
    expect(response.status).toBe(403);
    expect(enqueueTradeAutofill).not.toHaveBeenCalled();
  });

  it("rejects an unauthenticated request", async () => {
    authenticateSessionToken.mockResolvedValue(null);
    const response = await callPost(postReq({ screenshot_id: 3 }));
    expect(response.status).toBe(401);
    expect(enqueueTradeAutofill).not.toHaveBeenCalled();
  });

  it("refuses a non-positive-integer screenshot id before reaching FastAPI", async () => {
    const response = await callPost(postReq({ screenshot_id: -1 }));
    expect(response.status).toBe(400);
    expect(enqueueTradeAutofill).not.toHaveBeenCalled();
  });

  it("forwards a 429's detail so the trader sees the backend's own rate-limit message", async () => {
    const { ApiError } = await import("@/lib/api/client");
    enqueueTradeAutofill.mockRejectedValue(
      new ApiError(429, { detail: "You've reached 5 AI autofills for today." }),
    );
    const response = await callPost(postReq({ screenshot_id: 3 }));
    expect(response.status).toBe(429);
    const body = await response.json();
    expect(body.detail).toBe("You've reached 5 AI autofills for today.");
  });

  it("forwards a 404 for a screenshot the caller does not own", async () => {
    const { ApiError } = await import("@/lib/api/client");
    enqueueTradeAutofill.mockRejectedValue(new ApiError(404));
    const response = await callPost(postReq({ screenshot_id: 3 }));
    expect(response.status).toBe(404);
  });
});

describe("GET /api/trades/autofill/{jobId}", () => {
  it("polls with the job id from the path and the session's token", async () => {
    fetchTradeAutofillJob.mockResolvedValue({
      job_id: 42,
      status: "succeeded",
      error: null,
      suggestions: { asset: { value: "NQ", confidence: 0.9, autocheck: true } },
    });
    const response = await callGet(getReq());
    expect(response.status).toBe(200);
    expect(fetchTradeAutofillJob).toHaveBeenCalledWith("browser-token", 42);
  });

  it("answers 404 for a job id that is not a plain positive integer", async () => {
    const response = await callGet(getReq(), "0x10");
    expect(response.status).toBe(404);
    expect(fetchTradeAutofillJob).not.toHaveBeenCalled();
  });

  it("fails shut when SITE_ORIGIN is unset", async () => {
    delete process.env.SITE_ORIGIN;
    const response = await callGet(getReq());
    expect(response.status).toBe(403);
    expect(fetchTradeAutofillJob).not.toHaveBeenCalled();
  });

  it("forwards a foreign-or-missing job's 404 rather than reshaping it", async () => {
    const { ApiError } = await import("@/lib/api/client");
    fetchTradeAutofillJob.mockRejectedValue(new ApiError(404));
    const response = await callGet(getReq());
    expect(response.status).toBe(404);
  });
});
