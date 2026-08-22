import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi, beforeEach } from "vitest";

const callApi = vi.fn();
vi.mock("@/lib/api/client", () => ({ callApi: (...a: unknown[]) => callApi(...a) }));

import { fetchOverview } from "@/lib/app/overview";

beforeEach(() => callApi.mockReset());

describe("fetchOverview", () => {
  it("asks for the period it was given", async () => {
    callApi.mockResolvedValue({ kpi: { trades: 0 } });
    await fetchOverview("tok", { from: "2026-08-01", to: "2026-08-31", presetId: "custom" });
    const [path, token, init] = callApi.mock.calls[0];
    expect(path).toBe("/v1/overview");
    expect(token).toBe("tok");
    expect(init.query).toContain("from=2026-08-01");
    expect(init.query).toContain("to=2026-08-31");
  });

  it("sends the session token, never a user id", () => {
    // The API derives the owner from the session row. A caller that could name
    // an account would defeat the whole boundary.
    const source = String(fetchOverview);
    expect(source).not.toMatch(/user_?[Ii]d/);
  });

  it("passes the payload through untouched", async () => {
    const payload = { kpi: { trades: 5, net_pnl: 575 } };
    callApi.mockResolvedValue(payload);
    await expect(
      fetchOverview("tok", { from: "2026-08-01", to: "2026-08-31", presetId: "custom" }),
    ).resolves.toBe(payload);
  });

  it("lets an API error propagate rather than returning empty data", async () => {
    // Swallowing this would render an Overview of zeros — indistinguishable
    // from a trader who had a flat month.
    // mockRejectedValueOnce (not the persistent form) matches the convention
    // used elsewhere in this suite: a persistent mockRejectedValue() paired
    // with mockReset() in beforeEach trips a Vitest 4.1.10 spy-tracking
    // false positive ("unhandled rejection") unrelated to the code under
    // test — reproducible with a bare vi.fn() with no relation to fetchOverview.
    callApi.mockRejectedValueOnce(new Error("boom"));
    await expect(
      fetchOverview("tok", { from: "2026-08-01", to: "2026-08-31", presetId: "custom" }),
    ).rejects.toThrow();
  });
});
