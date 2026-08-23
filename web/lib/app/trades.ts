import "server-only";

import { callApi } from "@/lib/api/client";
import { periodToParams, type Period } from "@/lib/app/period";
import { filtersToParams, type TradeFilters } from "@/lib/app/trade-filters";
import type { components } from "@/lib/api/schema";

/**
 * The Trades list page, typed from the generated OpenAPI schema so the shape
 * cannot drift from what `GET /v1/trades` actually returns.
 *
 * `TradeSummary` — the row shape — deliberately does not carry `ai_grade`,
 * `user_grade`, or a screenshot count; `TradeDetail` is the only contract
 * that does. A list-page grade or screenshot column would have to be
 * fabricated client-side or fetched per row, which is exactly the kind of
 * fixture-encodes-the-plan's-wording mistake Phase 2 shipped once already —
 * so the table renders only the fields this response actually carries.
 */
export type TradeListResponse = components["schemas"]["TradeListResponse"];
export type TradeSummary = components["schemas"]["TradeSummary"];

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
