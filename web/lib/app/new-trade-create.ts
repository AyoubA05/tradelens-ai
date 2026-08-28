import "server-only";

import { callApi } from "@/lib/api/client";
import type { TradeCreate, TradeCreateResponse } from "@/lib/app/new-trade";

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
