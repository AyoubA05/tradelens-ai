import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * POST /api/trades/{id}/screenshot — the relay the upload island uses to
 * reach the three FastAPI screenshot endpoints.
 *
 * The security shape is the load-bearing part: fail-shut CSRF, the session
 * from the cookie only, the eligibility gate, and the backend's 422/409
 * forwarded as themselves so the client can tell "not a usable image" from
 * "the upload is gone."
 */

const { presignScreenshot, finalizeScreenshot, abandonScreenshot, authenticateSessionToken } =
  vi.hoisted(() => ({
    presignScreenshot: vi.fn(),
    finalizeScreenshot: vi.fn(),
    abandonScreenshot: vi.fn(),
    authenticateSessionToken: vi.fn(),
  }));

vi.mock("@/lib/app/new-trade-create", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/app/new-trade-create")>();
  return { ...actual, presignScreenshot, finalizeScreenshot, abandonScreenshot };
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

function req(body: unknown, headers: Record<string, string> = {}) {
  return new Request("https://site.test/api/trades/42/screenshot", {
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

async function callPost(request: Request, id = "42") {
  const { POST } = await import("@/app/api/trades/[id]/screenshot/route");
  return POST(request, { params: Promise.resolve({ id }) });
}

beforeEach(() => {
  vi.resetModules();
  presignScreenshot.mockReset();
  finalizeScreenshot.mockReset();
  abandonScreenshot.mockReset();
  authenticateSessionToken.mockReset().mockResolvedValue(eligibleUser);
  process.env.SITE_ORIGIN = "https://site.test";
});

describe("POST /api/trades/{id}/screenshot", () => {
  it("presigns with the trade id from the path and the content type from the body", async () => {
    presignScreenshot.mockResolvedValue({
      url: "https://r2.test/put",
      key: "u/7/t/42/q/abc",
      max_bytes: 10485760,
      expires_in: 300,
    });
    const response = await callPost(req({ action: "presign", content_type: "image/png" }));
    expect(response.status).toBe(200);
    expect(presignScreenshot).toHaveBeenCalledWith("browser-token", 42, "image/png");
    expect((await response.json()).max_bytes).toBe(10485760);
  });

  it("finalizes with the key exactly as the browser returned it", async () => {
    finalizeScreenshot.mockResolvedValue({
      id: 5,
      url: "https://r2.test/get",
      width: 1,
      height: 1,
      uploaded_at: null,
    });
    const response = await callPost(req({ action: "finalize", key: "u/7/t/42/q/abc" }));
    expect(response.status).toBe(201);
    expect(finalizeScreenshot).toHaveBeenCalledWith("browser-token", 42, "u/7/t/42/q/abc");
  });

  it("abandons and answers 204", async () => {
    abandonScreenshot.mockResolvedValue(undefined);
    const response = await callPost(req({ action: "abandon", key: "u/7/t/42/q/abc" }));
    expect(response.status).toBe(204);
    expect(abandonScreenshot).toHaveBeenCalledWith("browser-token", 42, "u/7/t/42/q/abc");
  });

  it("rejects a cross-site POST without reaching the backend", async () => {
    const response = await callPost(
      req({ action: "presign", content_type: "image/png" }, { origin: "https://evil.test" }),
    );
    expect(response.status).toBe(403);
    expect(presignScreenshot).not.toHaveBeenCalled();
  });

  it("fails shut when SITE_ORIGIN is unset", async () => {
    delete process.env.SITE_ORIGIN;
    const response = await callPost(req({ action: "presign", content_type: "image/png" }));
    expect(response.status).toBe(403);
    expect(presignScreenshot).not.toHaveBeenCalled();
  });

  it("rejects an unauthenticated request without signing an upload", async () => {
    authenticateSessionToken.mockResolvedValue(null);
    const response = await callPost(req({ action: "presign", content_type: "image/png" }));
    expect(response.status).toBe(401);
    expect(presignScreenshot).not.toHaveBeenCalled();
  });

  it("never takes identity from the body", async () => {
    presignScreenshot.mockResolvedValue({ url: "u", key: "k", max_bytes: 1, expires_in: 1 });
    await callPost(req({ action: "presign", content_type: "image/png", user_id: 999 }));
    expect(presignScreenshot).toHaveBeenCalledWith("browser-token", 42, "image/png");
  });

  it.each([
    { user: { ...eligibleUser, appSurface: "streamlit" }, label: "a Streamlit-only account" },
    { user: { ...eligibleUser, onboardingCompleted: false }, label: "an account before onboarding" },
  ])("refuses $label before reaching FastAPI", async ({ user }) => {
    authenticateSessionToken.mockResolvedValue(user);
    const response = await callPost(req({ action: "presign", content_type: "image/png" }));
    expect(response.status).toBe(403);
    expect(presignScreenshot).not.toHaveBeenCalled();
  });

  it("answers 404 for a trade id that is not a plain positive integer", async () => {
    const response = await callPost(req({ action: "presign", content_type: "image/png" }), "0x10");
    expect(response.status).toBe(404);
    expect(presignScreenshot).not.toHaveBeenCalled();
  });

  it("forwards a finalize 422 as 422 so a rejected image is not a generic failure", async () => {
    const { ApiError } = await import("@/lib/api/client");
    finalizeScreenshot.mockRejectedValue(new ApiError(422));
    const response = await callPost(req({ action: "finalize", key: "k" }));
    expect(response.status).toBe(422);
  });

  it("forwards a finalize 409 as 409 so a vanished upload is not a generic failure", async () => {
    const { ApiError } = await import("@/lib/api/client");
    finalizeScreenshot.mockRejectedValue(new ApiError(409));
    const response = await callPost(req({ action: "finalize", key: "k" }));
    expect(response.status).toBe(409);
  });

  it("forwards a 404 for another owner's trade rather than reshaping it", async () => {
    const { ApiError } = await import("@/lib/api/client");
    presignScreenshot.mockRejectedValue(new ApiError(404));
    const response = await callPost(req({ action: "presign", content_type: "image/png" }));
    expect(response.status).toBe(404);
  });

  it("uses 502 only for a fault that is not the backend's own status", async () => {
    presignScreenshot.mockRejectedValue(new TypeError("fetch failed"));
    const response = await callPost(req({ action: "presign", content_type: "image/png" }));
    expect(response.status).toBe(502);
  });

  it("refuses an unknown action and a missing key", async () => {
    expect((await callPost(req({ action: "promote", key: "k" }))).status).toBe(400);
    expect((await callPost(req({ action: "finalize" }))).status).toBe(400);
    expect(finalizeScreenshot).not.toHaveBeenCalled();
  });

  it("sets no-store on every response", async () => {
    presignScreenshot.mockResolvedValue({ url: "u", key: "k", max_bytes: 1, expires_in: 1 });
    const ok = await callPost(req({ action: "presign", content_type: "image/png" }));
    expect(ok.headers.get("cache-control")).toContain("no-store");
    const forbidden = await callPost(
      req({ action: "presign", content_type: "image/png" }, { origin: "https://evil.test" }),
    );
    expect(forbidden.headers.get("cache-control")).toContain("no-store");
  });
});
