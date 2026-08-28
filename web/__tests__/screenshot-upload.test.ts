import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  attachScreenshot,
  screenshotPreflight,
  type ScreenshotAttachResult,
} from "@/lib/app/screenshot-upload";

/**
 * The browser half of the upload lifecycle (design decision #1):
 * presign → PUT to R2 → finalize. Every outcome other than `attached`
 * leaves an existing trade untouched, and the 422/409 split has to survive
 * this layer — a trader whose image was refused and a trader whose upload
 * expired need different next steps.
 */

function fileOf(type: string, size: number, name = "chart.png"): File {
  // jsdom's File does not let `size` be set from a small blob, so it is
  // stubbed: nothing under test reads the bytes.
  return { name, type, size } as unknown as File;
}

function jsonResponse(status: number, body: unknown = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

const presigned = {
  url: "https://r2.test/put",
  key: "u/7/t/42/q/abc",
  max_bytes: 10 * 1024 * 1024,
  expires_in: 300,
};

let calls: Array<Record<string, unknown>>;

function relayFetch(responses: Response[]): typeof fetch {
  let i = 0;
  return vi.fn(async (_url: unknown, init: unknown) => {
    calls.push(JSON.parse((init as RequestInit).body as string));
    return responses[Math.min(i++, responses.length - 1)];
  }) as unknown as typeof fetch;
}

const okPut = async () => ({ ok: true });

beforeEach(() => {
  calls = [];
});

describe("screenshotPreflight", () => {
  it("refuses a type the presign enum does not accept", () => {
    expect(screenshotPreflight({ type: "application/pdf", size: 10 }, null)).toMatch(/PNG/);
  });

  it("uses the server's max_bytes rather than a number of its own", () => {
    const tooBig = { type: "image/png", size: 2001 };
    expect(screenshotPreflight(tooBig, 2000)).toMatch(/larger than/);
    expect(screenshotPreflight(tooBig, 4000)).toBeNull();
  });

  it("frames the size check as a wasted upload, never as the gate", () => {
    const message = screenshotPreflight({ type: "image/png", size: 99 }, 10) ?? "";
    expect(message).toMatch(/would not succeed/);
  });
});

describe("attachScreenshot", () => {
  it("presigns, uploads, finalizes, and reports the screenshot", async () => {
    const fetchImpl = relayFetch([jsonResponse(200, presigned), jsonResponse(201, { id: 5 })]);
    const result = await attachScreenshot(42, fileOf("image/png", 1000), {
      fetchImpl,
      put: okPut,
    });
    expect(result).toEqual({ status: "attached", screenshot: { id: 5 } });
    expect(calls[0]).toEqual({ action: "presign", content_type: "image/png" });
    expect(calls[1]).toEqual({ action: "finalize", key: presigned.key });
  });

  it("PUTs to the presigned URL the server chose, never a key it composed itself", async () => {
    const fetchImpl = relayFetch([jsonResponse(200, presigned), jsonResponse(201, { id: 5 })]);
    const put = vi.fn(async (url: string) => {
      expect(url).toBe("https://r2.test/put");
      return { ok: true };
    });
    await attachScreenshot(42, fileOf("image/png", 10), { fetchImpl, put });
    expect(put).toHaveBeenCalledOnce();
  });

  it("reports a finalize 422 as rejected, distinct from a generic failure", async () => {
    const fetchImpl = relayFetch([jsonResponse(200, presigned), jsonResponse(422)]);
    const result = await attachScreenshot(42, fileOf("image/png", 10), { fetchImpl, put: okPut });
    expect(result.status).toBe("rejected");
    expect((result as { message: string }).message).toMatch(/trade is unchanged/i);
    // A definitively refused upload is litter with no download path, so it
    // is abandoned rather than left in the bucket forever.
    expect(calls.at(-1)).toEqual({ action: "abandon", key: presigned.key });
  });

  it("reports a finalize 409 as stale, and does NOT abandon an object already gone", async () => {
    const fetchImpl = relayFetch([jsonResponse(200, presigned), jsonResponse(409)]);
    const result = await attachScreenshot(42, fileOf("image/png", 10), { fetchImpl, put: okPut });
    expect(result.status).toBe("stale");
    expect(calls.some((c) => c.action === "abandon")).toBe(false);
  });

  it("does not abandon after a transient finalize fault — the key may still finalize", async () => {
    const fetchImpl = relayFetch([jsonResponse(200, presigned), jsonResponse(502)]);
    const result = await attachScreenshot(42, fileOf("image/png", 10), { fetchImpl, put: okPut });
    expect(result.status).toBe("failed");
    expect(calls.some((c) => c.action === "abandon")).toBe(false);
  });

  it("abandons the quarantine object when the PUT fails", async () => {
    const fetchImpl = relayFetch([jsonResponse(200, presigned), jsonResponse(204)]);
    const result = await attachScreenshot(42, fileOf("image/png", 10), {
      fetchImpl,
      put: async () => ({ ok: false }),
    });
    expect(result.status).toBe("failed");
    expect(calls.at(-1)).toEqual({ action: "abandon", key: presigned.key });
  });

  it("never claims a trade was lost, in any outcome", async () => {
    const outcomes: ScreenshotAttachResult[] = [];
    for (const second of [jsonResponse(422), jsonResponse(409), jsonResponse(502)]) {
      calls = [];
      outcomes.push(
        await attachScreenshot(42, fileOf("image/png", 10), {
          fetchImpl: relayFetch([jsonResponse(200, presigned), second]),
          put: okPut,
        }),
      );
    }
    for (const outcome of outcomes) {
      const message = (outcome as { message: string }).message;
      expect(message).toMatch(/trade is unchanged/i);
      expect(message).not.toMatch(/nothing was saved|not saved|lost/i);
    }
  });

  it("checks the size against the server's max_bytes and skips the upload", async () => {
    const fetchImpl = relayFetch([jsonResponse(200, { ...presigned, max_bytes: 500 })]);
    const put = vi.fn(async () => ({ ok: true }) as { ok: boolean });
    const result = await attachScreenshot(42, fileOf("image/png", 5000), { fetchImpl, put });
    expect(result.status).toBe("rejected");
    expect(put).not.toHaveBeenCalled();
  });

  it("refuses a non-image before any network call", async () => {
    const fetchImpl = relayFetch([jsonResponse(200, presigned)]);
    const result = await attachScreenshot(42, fileOf("application/pdf", 10), { fetchImpl });
    expect(result.status).toBe("rejected");
    expect(calls).toHaveLength(0);
  });

  it("reports phases and upload progress", async () => {
    const phases: Array<[string, number]> = [];
    const fetchImpl = relayFetch([jsonResponse(200, presigned), jsonResponse(201, { id: 5 })]);
    await attachScreenshot(42, fileOf("image/png", 10), {
      fetchImpl,
      put: async (_u, _f, onProgress) => {
        onProgress(0.5);
        return { ok: true };
      },
      onPhase: (phase, progress) => phases.push([phase, progress]),
    });
    expect(phases).toContainEqual(["presigning", 0]);
    expect(phases).toContainEqual(["uploading", 0.5]);
    expect(phases).toContainEqual(["validating", 1]);
  });

  it("fails cleanly when the relay itself is unreachable", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError("network down");
    }) as unknown as typeof fetch;
    const result = await attachScreenshot(42, fileOf("image/png", 10), { fetchImpl });
    expect(result.status).toBe("failed");
  });
});
