import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi, beforeEach } from "vitest";

const callApi = vi.fn();
vi.mock("@/lib/api/client", () => ({
  callApi: (...a: unknown[]) => callApi(...a),
  ApiError: class ApiError extends Error {
    constructor(readonly status: number) {
      super(`api request failed with status ${status}`);
    }
  },
}));

import { deleteTrade, fetchTradeDetail, patchTrade } from "@/lib/app/trades";
import { ApiError } from "@/lib/api/client";

beforeEach(() => callApi.mockReset());

describe("fetchTradeDetail", () => {
  it("asks for the one trade by id", async () => {
    callApi.mockResolvedValue({ id: 42 });
    await fetchTradeDetail("tok", 42);
    const [path, token, init] = callApi.mock.calls[0];
    expect(path).toBe("/v1/trades/42");
    expect(token).toBe("tok");
    expect(init).toBeUndefined();
  });

  it("sends only the session token — never an account identifier", async () => {
    callApi.mockResolvedValue({ id: 42 });
    await fetchTradeDetail("tok", 42);
    expect(JSON.stringify(callApi.mock.calls[0])).not.toMatch(/user|owner|account|uid/i);
  });

  it("passes the payload through untouched", async () => {
    const payload = { id: 42, asset: "NQ" };
    callApi.mockResolvedValue(payload);
    await expect(fetchTradeDetail("tok", 42)).resolves.toBe(payload);
  });

  it("lets a 404 (own-vs-nonexistent, byte-identical) propagate rather than reshaping it", async () => {
    // Reshaping this here is the one place that could leak the distinction
    // GET /v1/trades/{id} deliberately does not carry.
    callApi.mockRejectedValueOnce(new ApiError(404));
    await expect(fetchTradeDetail("tok", 999)).rejects.toMatchObject({ status: 404 });
  });
});

describe("patchTrade", () => {
  const update = { expected_updated_at: "2026-08-01T00:00:00Z", asset: "NQ" };

  it("PATCHes the one trade with the given body", async () => {
    callApi.mockResolvedValue({ id: 42, asset: "NQ" });
    await patchTrade("tok", 42, update);
    const [path, token, init] = callApi.mock.calls[0];
    expect(path).toBe("/v1/trades/42");
    expect(token).toBe("tok");
    expect(init).toEqual({ method: "PATCH", body: update });
  });

  it("lets a 409 conflict propagate rather than retrying or discarding it", async () => {
    callApi.mockRejectedValueOnce(new ApiError(409));
    await expect(patchTrade("tok", 42, update)).rejects.toMatchObject({ status: 409 });
    expect(callApi).toHaveBeenCalledOnce();
  });
});

describe("deleteTrade", () => {
  it("DELETEs the one trade", async () => {
    callApi.mockResolvedValue(undefined);
    await deleteTrade("tok", 42);
    const [path, token, init] = callApi.mock.calls[0];
    expect(path).toBe("/v1/trades/42");
    expect(token).toBe("tok");
    expect(init).toEqual({ method: "DELETE" });
  });

  it("lets a 503 cleanup failure propagate — the row is intact, this is never partial success", async () => {
    callApi.mockRejectedValueOnce(new ApiError(503));
    await expect(deleteTrade("tok", 42)).rejects.toMatchObject({ status: 503 });
  });
});
