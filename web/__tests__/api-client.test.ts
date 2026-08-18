import { createHash } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";

import { callApi } from "@/lib/api/client";
import { WEBSITE_DOMAIN } from "@/lib/auth/domains";

describe("FastAPI client credential boundary", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("forwards a non-browser-replayable session handle, never the raw cookie", async () => {
    vi.stubEnv("TL_API_ORIGIN", "https://api.example.test");
    vi.stubEnv("TL_SERVICE_SECRET", "service-secret");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ user_id: 7 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const raw = "raw-browser-cookie-value";
    await callApi("/v1/session/whoami", raw);

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers["X-TL-Session-Handle"]).toBe(
      createHash("sha256").update(WEBSITE_DOMAIN + raw, "utf8").digest("hex"),
    );
    expect(headers).not.toHaveProperty("X-TL-Session");
    expect(JSON.stringify(init)).not.toContain(raw);
  });
});
