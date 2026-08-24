import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi, beforeEach } from "vitest";

const callApi = vi.fn();
vi.mock("@/lib/api/client", () => ({ callApi: (...a: unknown[]) => callApi(...a) }));

import { DEFAULT_TRADES_LIMIT, fetchTrades } from "@/lib/app/trades";

const period = { from: "2026-08-01", to: "2026-08-31", presetId: "custom" };

beforeEach(() => callApi.mockReset());

describe("fetchTrades", () => {
  it("asks for the period it was given, plus a default page", async () => {
    callApi.mockResolvedValue({ trades: [], total: 0, limit: 25, offset: 0 });
    await fetchTrades("tok", { period, filters: {} });
    const [path, token, init] = callApi.mock.calls[0];
    expect(path).toBe("/v1/trades");
    expect(token).toBe("tok");
    const params = new URLSearchParams(init.query);
    expect(params.get("from")).toBe("2026-08-01");
    expect(params.get("to")).toBe("2026-08-31");
    expect(params.get("limit")).toBe(String(DEFAULT_TRADES_LIMIT));
    expect(params.get("offset")).toBe("0");
  });

  it("forwards the filter set as query params", async () => {
    callApi.mockResolvedValue({ trades: [], total: 0, limit: 25, offset: 0 });
    await fetchTrades("tok", { period, filters: { asset: "NQ", result: "Win" } });
    const params = new URLSearchParams(callApi.mock.calls[0][2].query);
    expect(params.get("asset")).toBe("NQ");
    expect(params.get("result")).toBe("Win");
    expect(params.has("session")).toBe(false);
  });

  it("forwards an explicit limit and offset", async () => {
    callApi.mockResolvedValue({ trades: [], total: 0, limit: 25, offset: 25 });
    await fetchTrades("tok", { period, filters: {}, limit: 50, offset: 25 });
    const params = new URLSearchParams(callApi.mock.calls[0][2].query);
    expect(params.get("limit")).toBe("50");
    expect(params.get("offset")).toBe("25");
  });

  it("sends only the session token, the period, filters and paging — never an account identifier", async () => {
    callApi.mockResolvedValue({ trades: [], total: 0, limit: 25, offset: 0 });
    await fetchTrades("tok", { period, filters: { asset: "NQ" } });
    const call = callApi.mock.calls[0];
    expect(call).toHaveLength(3);
    expect(call[2].body).toBeUndefined();
    expect(Object.keys(call[2])).toEqual(["query"]);
    const outgoingKeys = [...new URLSearchParams(call[2].query).keys()].sort();
    expect(outgoingKeys).toEqual(["asset", "from", "limit", "offset", "to"]);
    // Keep the explicit spelling check as a readable diagnostic, but the
    // key allowlist above is what also catches an indirectly renamed owner.
    expect(JSON.stringify(call)).not.toMatch(/user|owner|account|uid/i);
  });

  it("passes the payload through untouched", async () => {
    const payload = { trades: [{ id: 1 }], total: 1, limit: 25, offset: 0 };
    callApi.mockResolvedValue(payload);
    await expect(fetchTrades("tok", { period, filters: {} })).resolves.toBe(payload);
  });

  it("lets an API error propagate rather than returning an empty page", async () => {
    // Swallowing this would render an empty Trades list indistinguishable
    // from a trader with no trades in the window.
    callApi.mockRejectedValueOnce(new Error("boom"));
    await expect(fetchTrades("tok", { period, filters: {} })).rejects.toThrow();
  });
});
