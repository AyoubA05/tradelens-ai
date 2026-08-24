import { beforeEach, describe, expect, it, vi } from "vitest";

const callApi = vi.fn();
vi.mock("@/lib/api/client", () => ({ callApi: (...args: unknown[]) => callApi(...args) }));

import { enqueueTradeSummary, fetchTradeSummaryJob } from "@/lib/app/trades";

beforeEach(() => callApi.mockReset());

describe("trade-summary server boundary", () => {
  it("POSTs only the period and canonical filters, never an owner identifier", async () => {
    callApi.mockResolvedValue({ job_id: 19, status: "queued", created: true });
    await enqueueTradeSummary(
      "browser-token",
      { from: "2026-08-01", to: "2026-08-31", presetId: "custom" },
      { asset: "NQ", result: "Win" },
    );

    const [path, token, init] = callApi.mock.calls[0];
    expect(path).toBe("/v1/trades/summary");
    expect(token).toBe("browser-token");
    expect(init).toEqual({
      method: "POST",
      body: { from: "2026-08-01", to: "2026-08-31", asset: "NQ", result: "Win" },
    });
    expect(Object.keys(init.body).sort()).toEqual(["asset", "from", "result", "to"]);
    expect(JSON.stringify(callApi.mock.calls[0])).not.toMatch(/user|owner|account|uid/i);
  });

  it("polls one job by id without browser-supplied ownership", async () => {
    callApi.mockResolvedValue({ job_id: 19, status: "running", result: null, error: null });
    await fetchTradeSummaryJob("browser-token", 19);

    expect(callApi).toHaveBeenCalledWith("/v1/trades/summary/19", "browser-token");
    expect(JSON.stringify(callApi.mock.calls[0])).not.toMatch(/user|owner|account|uid/i);
  });
});
