import "server-only";

import { callApi } from "@/lib/api/client";
import { periodToParams, type Period } from "@/lib/app/period";
import { filtersToParams, type TradeFilters } from "@/lib/app/trade-filters";
import type { components } from "@/lib/api/schema";

/**
 * The Trades list page, typed from the generated OpenAPI schema so the shape
 * cannot drift from what `GET /v1/trades` actually returns.
 *
 * `TradeSummary` — the row shape — carries `ai_grade`, `user_grade` and
 * `screenshot_count` alongside the trade's own fields, because spec §8 asks
 * the list for a grade and a screenshot indicator and the response was
 * widened to supply them. That widening is the point: the alternative was a
 * column fabricated client-side or fetched per row, which is exactly the
 * fixture-encodes-the-plan's-wording mistake Phase 2 shipped once already.
 * Anything the list renders must be a field this response actually returns.
 */
export type TradeListResponse = components["schemas"]["TradeListResponse"];
export type TradeSummary = components["schemas"]["TradeSummary"];

/**
 * `TradeDetail` is the wider contract `GET /v1/trades/{id}` returns: every
 * recorded field plus screenshots, each already carrying a short-lived
 * presigned URL (design decision #6 — screenshots are presigned directly to
 * R2, never proxied through this app).
 */
export type TradeDetail = components["schemas"]["TradeDetail"];
export type ScreenshotDescriptor = components["schemas"]["ScreenshotDescriptor"];

/**
 * The PATCH body. `expected_updated_at` is required, not optional — the
 * allowlist and the conflict guard are enforced service-side, but the type
 * still names exactly what a caller may send, so a stray field is a compile
 * error here rather than a 422 discovered at runtime.
 */
export type TradeUpdate = components["schemas"]["TradeUpdate"];

/** The page size the Trades list requests when the URL does not say otherwise. */
export const DEFAULT_TRADES_LIMIT = 25;

/**
 * Fetch one page of the Trades list for the authenticated owner.
 *
 * Server-only, same boundary as `fetchOverview`: the session token is
 * forwarded to `callApi`, which hashes it into the domain-separated handle,
 * and the owner is resolved API-side from that handle — never from anything
 * passed here. Errors are not caught, for the same reason as `fetchOverview`:
 * an empty page is indistinguishable from a trader with no trades in the
 * window, so a failed fetch must reach the route's error boundary.
 */
export async function fetchTrades(
  sessionToken: string,
  args: { period: Period; filters: TradeFilters; limit?: number; offset?: number },
): Promise<TradeListResponse> {
  const params = periodToParams(args.period);
  for (const [key, value] of filtersToParams(args.filters)) params.set(key, value);
  params.set("limit", String(args.limit ?? DEFAULT_TRADES_LIMIT));
  params.set("offset", String(args.offset ?? 0));

  return callApi<TradeListResponse>("/v1/trades", sessionToken, {
    query: params.toString(),
  });
}

/**
 * Fetch one trade for the authenticated owner.
 *
 * Same boundary as `fetchTrades`. Errors are not caught: `GET
 * /v1/trades/{id}` returns 404 byte-identical for "not yours" and "does not
 * exist" (Task A3), and the caller — the route's Server Component — is what
 * turns that 404 into `notFound()`. Catching and reshaping it here would be
 * the one place that could leak the distinction back out.
 */
export async function fetchTradeDetail(
  sessionToken: string,
  tradeId: number,
): Promise<TradeDetail> {
  return callApi<TradeDetail>(`/v1/trades/${tradeId}`, sessionToken);
}

/**
 * Edit a trade's user-editable fields.
 *
 * `update.expected_updated_at` is what the caller last saw; a stale value
 * throws `ApiError(409)` rather than silently overwriting a concurrent edit
 * (design decision #5). The 409 is not caught here — the caller decides how
 * to show a trader that their edit lost a race, and swallowing it at this
 * layer would take that choice away.
 */
export async function patchTrade(
  sessionToken: string,
  tradeId: number,
  update: TradeUpdate,
): Promise<TradeDetail> {
  return callApi<TradeDetail>(`/v1/trades/${tradeId}`, sessionToken, {
    method: "PATCH",
    body: update,
  });
}

/**
 * Delete a trade and its screenshots.
 *
 * A failed screenshot cleanup returns `ApiError(503)` with the trade row
 * left intact — the deliberately less-tidy outcome design decision #6 and
 * the "Risks" section both call out: telling a trader their images are gone
 * while they remain in the bucket is a false privacy assurance. This
 * function does not catch that, or any other status; the caller renders it
 * as "nothing was deleted, try again," never as partial success.
 */
export async function deleteTrade(sessionToken: string, tradeId: number): Promise<void> {
  await callApi<undefined>(`/v1/trades/${tradeId}`, sessionToken, { method: "DELETE" });
}
