import "server-only";

import { callApi } from "@/lib/api/client";
import type { TradeCreate, TradeCreateResponse } from "@/lib/app/new-trade";
import type {
  ScreenshotContentType,
  ScreenshotDescriptor,
  ScreenshotPresignResponse,
} from "@/lib/app/screenshot-upload";

/**
 * Create a trade for the authenticated owner.
 *
 * Same boundary as `createTrade`'s siblings in `trades.ts`: the session
 * token is forwarded, ownership is resolved API-side. A submit whose
 * fingerprint matches an existing trade returns 200 with `duplicate_of` set
 * rather than a second row (design decision #5) — that is not an error, and
 * this function does not treat it as one; the caller reads `duplicate_of`.
 * A P&L/result contradiction the client-side check missed still comes back
 * as `ApiError(422)`, which this function does not catch — the server's
 * `canonical_outcome` is the actual gate (design decision, global rule 4).
 */
export async function createTrade(
  sessionToken: string,
  payload: TradeCreate,
): Promise<TradeCreateResponse> {
  return callApi<TradeCreateResponse>("/v1/trades", sessionToken, {
    method: "POST",
    body: payload,
  });
}

/**
 * Ask the backend for permission to upload one chart image for a trade.
 *
 * The trade id is what authorises this (design decision #1) — there is no
 * trade-less draft namespace — so a trade that is not the caller's returns
 * 404 and signs nothing. The response's `max_bytes` is the server's own
 * number; nothing on this path may hardcode a size of its own.
 */
export async function presignScreenshot(
  sessionToken: string,
  tradeId: number,
  contentType: ScreenshotContentType,
): Promise<ScreenshotPresignResponse> {
  return callApi<ScreenshotPresignResponse>(
    `/v1/trades/${tradeId}/screenshot/presign`,
    sessionToken,
    { method: "POST", body: { content_type: contentType } },
  );
}

/**
 * Validate a quarantined upload, promote it, and record the screenshot row.
 *
 * The key is forwarded as the browser returned it, deliberately: it is a
 * claim, and `finalize_upload` re-derives this owner's own quarantine
 * prefix and refuses anything outside it. Re-deriving or "sanitising" it
 * here would add a second, weaker copy of a check that already exists where
 * ownership actually lives.
 */
export async function finalizeScreenshot(
  sessionToken: string,
  tradeId: number,
  key: string,
): Promise<ScreenshotDescriptor> {
  return callApi<ScreenshotDescriptor>(
    `/v1/trades/${tradeId}/screenshot/finalize`,
    sessionToken,
    { method: "POST", body: { key } },
  );
}

/**
 * Drop a quarantined upload the trader chose not to keep.
 *
 * Idempotent backend-side: an object already gone is the end state this
 * asks for, so a retry is success rather than an error a caller can never
 * clear.
 */
export async function abandonScreenshot(
  sessionToken: string,
  tradeId: number,
  key: string,
): Promise<void> {
  await callApi<void>(`/v1/trades/${tradeId}/screenshot/abandon`, sessionToken, {
    method: "POST",
    body: { key },
  });
}
