import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The three AI Reviews relays under `app/api/reviews/`.
 *
 * Two of them start paid work, so the security shape is pinned: fail-shut CSRF
 * before the session is read, the eligibility gate, and a failure mapping that
 * forwards only fixed codes and the rate-limit sentence — never backend text.
 */

const env = { SITE_ORIGIN: "https://app.test" as string | undefined };
const authenticate = vi.fn();
const appRedirect = vi.fn();
const enqueueWeekly = vi.fn();
const enqueueDaily = vi.fn();
const fetchJob = vi.fn();

vi.mock("@/lib/env", () => ({
  optionalEnv: (k: string) => (env as Record<string, string | undefined>)[k],
}));
vi.mock("@/lib/auth/session", () => ({
  sessionTokenFrom: () => "tok",
  authenticateSessionToken: (...a: unknown[]) => authenticate(...a),
  appLayoutRedirect: (...a: unknown[]) => appRedirect(...a),
}));
vi.mock("@/lib/app/reviews", async (orig) => ({
  ...(await orig<typeof import("@/lib/app/reviews")>()),
  enqueueWeeklyRecap: (...a: unknown[]) => enqueueWeekly(...a),
  enqueueDailyDebrief: (...a: unknown[]) => enqueueDaily(...a),
  fetchReviewJob: (...a: unknown[]) => fetchJob(...a),
}));

import { ApiError } from "@/lib/api/client";
import { POST as weekly } from "@/app/api/reviews/weekly/route";
import { POST as daily } from "@/app/api/reviews/daily/route";
import { GET as job } from "@/app/api/reviews/jobs/[jobId]/route";

function post(body: unknown, origin = "https://app.test") {
  return new Request("https://app.test/api/reviews/weekly", {
    method: "POST",
    headers: { origin, "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  env.SITE_ORIGIN = "https://app.test";
  authenticate.mockReset().mockResolvedValue({ userId: 2 });
  appRedirect.mockReset().mockReturnValue(null);
  enqueueWeekly.mockReset();
  enqueueDaily.mockReset();
  fetchJob.mockReset();
});

describe.each([
  ["weekly", weekly, enqueueWeekly],
  ["daily", daily, enqueueDaily],
] as const)("the %s generate relay", (_name, route, enqueue) => {
  it("refuses with 403 before reading the session when SITE_ORIGIN is unset", async () => {
    env.SITE_ORIGIN = undefined;
    const res = await route(post({ week: "2026-09-07" }));
    expect(res.status).toBe(403);
    expect(authenticate).not.toHaveBeenCalled();
    expect(enqueue).not.toHaveBeenCalled();
  });

  it("refuses a cross-origin request", async () => {
    expect((await route(post({}, "https://evil.test"))).status).toBe(403);
    expect(authenticate).not.toHaveBeenCalled();
    expect(enqueue).not.toHaveBeenCalled();
  });

  it("refuses without a session", async () => {
    authenticate.mockResolvedValue(null);
    expect((await route(post({ week: "2026-09-07" }))).status).toBe(401);
    expect(enqueue).not.toHaveBeenCalled();
  });

  it("refuses an ineligible account before the backend", async () => {
    appRedirect.mockReturnValue("/onboarding");
    expect((await route(post({ week: "2026-09-07" }))).status).toBe(403);
    expect(enqueue).not.toHaveBeenCalled();
  });

  it("400s an unparseable body without the backend", async () => {
    const res = await route(
      new Request("https://app.test/api/reviews/weekly", {
        method: "POST",
        headers: { origin: "https://app.test", "content-type": "application/json" },
        body: "{not json",
      }),
    );
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ ok: false });
    expect(enqueue).not.toHaveBeenCalled();
  });

  it("400s an oversized body without the backend", async () => {
    const res = await route(post({ week: "2026-09-07", pad: "x".repeat(4096) }));
    expect(res.status).toBe(400);
    expect(enqueue).not.toHaveBeenCalled();
  });

  it("forwards 202, no-store, no-referrer", async () => {
    enqueue.mockResolvedValue({ job_id: 9, status: "queued", created: true });
    const res = await route(post({ week: "2026-09-07" }));
    expect(res.status).toBe(202);
    expect(res.headers.get("cache-control")).toContain("no-store");
    expect(res.headers.get("referrer-policy")).toBe("no-referrer");
    expect(await res.json()).toEqual({ job_id: 9, status: "queued", created: true });
    expect(enqueue).toHaveBeenCalledWith("tok", { week: "2026-09-07" });
  });

  it.each(["empty_period", "not_enough_trades"])(
    "maps a 409 %s to its fixed code and nothing else",
    async (code) => {
      enqueue.mockRejectedValue(new ApiError(409, { detail: code, secret: "x" }));
      const res = await route(post({ week: "2026-09-07" }));
      expect(res.status).toBe(409);
      expect(await res.json()).toEqual({ ok: false, detail: code });
    },
  );

  it("never forwards an unknown 409 detail", async () => {
    enqueue.mockRejectedValue(new ApiError(409, { detail: "driver said postgres://u:p@h" }));
    const res = await route(post({ week: "2026-09-07" }));
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual({ ok: false });
  });

  it("forwards a 429 sentence", async () => {
    enqueue.mockRejectedValue(new ApiError(429, { detail: "limit" }));
    const res = await route(post({ week: "2026-09-07" }));
    expect(res.status).toBe(429);
    expect(await res.json()).toEqual({ ok: false, error: "rate_limited", detail: "limit" });
  });

  it("maps a 503 review_unavailable to its fixed code", async () => {
    enqueue.mockRejectedValue(new ApiError(503, { detail: "review_unavailable" }));
    const res = await route(post({ week: "2026-09-07" }));
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ ok: false, detail: "review_unavailable" });
  });

  it("never forwards another 503 detail", async () => {
    enqueue.mockRejectedValue(new ApiError(503, { detail: "pool exhausted at db-3" }));
    const res = await route(post({ week: "2026-09-07" }));
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ ok: false });
  });

  it.each([401, 403, 404, 422])("forwards a %s as an opaque failure", async (status) => {
    enqueue.mockRejectedValue(new ApiError(status, { detail: "week must be a Monday" }));
    const res = await route(post({ week: "2026-09-07" }));
    expect(res.status).toBe(status);
    expect(await res.json()).toEqual({ ok: false });
  });

  it("maps anything else to 502", async () => {
    enqueue.mockRejectedValue(new TypeError("fetch failed"));
    const res = await route(post({ week: "2026-09-07" }));
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ ok: false });
  });
});

describe("the job poll relay", () => {
  const params = (jobId: string) => ({ params: Promise.resolve({ jobId }) });
  const get = () =>
    new Request("https://app.test/api/reviews/jobs/9", { headers: { origin: "https://app.test" } });

  it("refuses with 403 before reading the session when SITE_ORIGIN is unset", async () => {
    env.SITE_ORIGIN = undefined;
    expect((await job(get(), params("9"))).status).toBe(403);
    expect(authenticate).not.toHaveBeenCalled();
    expect(fetchJob).not.toHaveBeenCalled();
  });

  it.each(["0", "-1", "abc", "1e3", "99999999999999999"])(
    "404s a malformed id %s without the backend",
    async (id) => {
      expect((await job(get(), params(id))).status).toBe(404);
      expect(fetchJob).not.toHaveBeenCalled();
    },
  );

  it("forwards a job", async () => {
    const body = { job_id: 9, kind: "weekly_recap", status: "running", note: null, error: null };
    fetchJob.mockResolvedValue(body);
    const res = await job(get(), params("9"));
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toContain("no-store");
    expect(await res.json()).toEqual(body);
    expect(fetchJob).toHaveBeenCalledWith("tok", 9);
  });

  it("forwards a foreign or missing job as an opaque 404", async () => {
    fetchJob.mockRejectedValue(new ApiError(404, { detail: "review job not found" }));
    const res = await job(get(), params("9"));
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ ok: false });
  });

  it("maps a backend 500 to 502", async () => {
    fetchJob.mockRejectedValue(new ApiError(500, { detail: "review result unavailable" }));
    const res = await job(get(), params("9"));
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ ok: false });
  });
});

describe("the job poll relay error field", () => {
  const params = { params: Promise.resolve({ jobId: "9" }) };
  const get = () =>
    new Request("https://app.test/api/reviews/jobs/9", { headers: { origin: "https://app.test" } });
  const OUT_OF_DATE = "This review is out of date. Generate it again.";

  it.each(["failed", "queued", "running", "succeeded"])(
    "relays a %s job's arbitrary error as null",
    async (status) => {
      fetchJob.mockResolvedValue({
        job_id: 9,
        kind: "daily_debrief",
        status,
        note: null,
        error: "psycopg2.OperationalError: host=db.internal password=secret",
      });
      const body = await (await job(get(), params)).json();
      expect(body.error).toBeNull();
      expect(body.status).toBe(status);
    },
  );

  it("keeps the fixed sentence on a superseded job", async () => {
    fetchJob.mockResolvedValue({
      job_id: 9, kind: "weekly_recap", status: "superseded", note: null, error: OUT_OF_DATE,
    });
    expect((await (await job(get(), params)).json()).error).toBe(OUT_OF_DATE);
  });

  it.each(["Something else.", "", null])("drops other superseded text %j", async (error) => {
    fetchJob.mockResolvedValue({
      job_id: 9, kind: "weekly_recap", status: "superseded", note: null, error,
    });
    expect((await (await job(get(), params)).json()).error).toBeNull();
  });
});
