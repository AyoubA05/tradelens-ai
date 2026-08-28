import "@testing-library/jest-dom/vitest";
import { beforeEach, describe, expect, it, vi } from "vitest";

const callApi = vi.fn();
vi.mock("@/lib/api/client", () => ({
  callApi: (...a: unknown[]) => callApi(...a),
  ApiError: class ApiError extends Error {
    constructor(readonly status: number) {
      super(`api request failed with status ${status}`);
    }
  },
}));

import { createTrade } from "@/lib/app/new-trade-create";
import { buildTradeCreatePayload, emptyNewTradeFormValues } from "@/lib/app/new-trade";
import { ApiError } from "@/lib/api/client";

const OTHER = "Other / Custom";

beforeEach(() => callApi.mockReset());

function payload() {
  return buildTradeCreatePayload(
    { ...emptyNewTradeFormValues(), asset: "NQ", tradeDate: "2026-08-20", entryTime: "09:30" },
    OTHER,
  );
}

describe("createTrade", () => {
  it("POSTs the payload and returns the response untouched", async () => {
    const response = { id: 1, duplicate_of: null };
    callApi.mockResolvedValue(response);
    const body = payload();
    await expect(createTrade("tok", body)).resolves.toBe(response);
    const [path, token, init] = callApi.mock.calls[0];
    expect(path).toBe("/v1/trades");
    expect(token).toBe("tok");
    expect(init).toEqual({ method: "POST", body });
  });

  it("lets a 422 outcome-mismatch the client missed propagate — the server is the real gate", async () => {
    callApi.mockRejectedValueOnce(new ApiError(422));
    await expect(createTrade("tok", payload())).rejects.toMatchObject({ status: 422 });
  });
});
