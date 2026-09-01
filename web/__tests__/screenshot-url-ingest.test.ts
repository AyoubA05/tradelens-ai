import { describe, expect, it, vi } from "vitest";

import { attachScreenshotUrl, screenshotUrlPreflight } from "@/lib/app/screenshot-upload";

/**
 * Task D1 — image-URL ingest, the browser half.
 *
 * The load-bearing property (global rule 3 / the group brief): a rejected
 * URL reads as a plain reason, never a stack, a host, or an address. That
 * means forwarding the relay's `detail` faithfully — this is the exact
 * defect Phase 4's create relay had (dropping `detail` for generic text),
 * and this suite pins that it is not repeated here.
 */

function jsonResponse(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as unknown as Response;
}

describe("screenshotUrlPreflight", () => {
  it("rejects a blank URL", () => {
    expect(screenshotUrlPreflight("   ")).toMatch(/enter a link/i);
  });

  it("rejects a non-URL string", () => {
    expect(screenshotUrlPreflight("not a url")).toMatch(/doesn't look like/i);
  });

  it("rejects a non-http(s) scheme", () => {
    expect(screenshotUrlPreflight("file:///etc/passwd")).toMatch(/http/i);
  });

  it("accepts an http(s) URL", () => {
    expect(screenshotUrlPreflight("https://example.test/chart.png")).toBeNull();
  });
});

describe("attachScreenshotUrl", () => {
  it("attaches on 201 and returns the screenshot descriptor", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse(201, { id: 9, width: 10, height: 10, uploaded_at: null, url: "https://r2.test/get" }),
    );
    const result = await attachScreenshotUrl(42, "https://example.test/chart.png", { fetchImpl });
    expect(result).toEqual({
      status: "attached",
      screenshot: { id: 9, width: 10, height: 10, uploaded_at: null, url: "https://r2.test/get" },
    });
    expect(fetchImpl).toHaveBeenCalledWith(
      "/api/trades/42/screenshot",
      expect.objectContaining({ method: "POST" }),
    );
    const body = JSON.parse((fetchImpl.mock.calls[0][1] as RequestInit).body as string);
    expect(body).toEqual({ action: "ingest-url", url: "https://example.test/chart.png" });
  });

  it("forwards the backend's own 422 detail verbatim — never a generic message", async () => {
    const fetchImpl = vi
      .fn()
      .mockResolvedValue(jsonResponse(422, { detail: "could not read an image from that link" }));
    const result = await attachScreenshotUrl(42, "https://example.test/chart.png", { fetchImpl });
    expect(result).toEqual({
      status: "rejected",
      message: "could not read an image from that link",
    });
  });

  it("never lets a detail through that names a host or address — it only ever passes through what the backend sent", async () => {
    // The backend is trusted to keep its own phrases host/address-free
    // (`url_ingest.UrlIngestError` / design-decisions.md #2's risk note);
    // this test pins that THIS layer does not itself inject or leak one —
    // e.g. it must never fall back to interpolating the trader's URL into
    // its own message.
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(422, {}));
    const result = await attachScreenshotUrl(42, "https://example.test/chart.png", { fetchImpl });
    expect(result.status).toBe("rejected");
    if (result.status === "rejected") {
      expect(result.message).not.toContain("example.test");
    }
  });

  it("falls back to a generic message on a non-422/2xx status with no detail", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(503, {}));
    const result = await attachScreenshotUrl(42, "https://example.test/chart.png", { fetchImpl });
    expect(result.status).toBe("failed");
  });

  it("does not call the network at all for a preflight-rejected URL", async () => {
    const fetchImpl = vi.fn();
    const result = await attachScreenshotUrl(42, "not a url", { fetchImpl });
    expect(result.status).toBe("rejected");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("treats a network fault as failed, not rejected", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("network down"));
    const result = await attachScreenshotUrl(42, "https://example.test/chart.png", { fetchImpl });
    expect(result.status).toBe("failed");
  });
});
