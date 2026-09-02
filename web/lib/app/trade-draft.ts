import "server-only";

import { callApi } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

/**
 * The New Trade draft (Task D3): save/load, server-only.
 *
 * Same boundary as `new-trade-create.ts`'s functions — `callApi` carries the
 * service secret and cannot reach a bundle, so the relay route
 * (`app/api/trades/draft/route.ts`) is what a Client Component actually
 * calls, through `lib/app/draft-autosave.ts`.
 *
 * `PUT /v1/trades/draft` never touches `trades` (global rule: "Autosave
 * must never create a trade") — `services.drafts.save_draft` writes only to
 * `trade_drafts`, a table `POST /v1/trades` cannot read from. This module
 * does not add a second way to reach that table; it is the one bridge.
 */
export type TradeDraftWritePayload = components["schemas"]["TradeDraftWritePayload"];
export type TradeDraftResponse = components["schemas"]["TradeDraftResponse"];

export async function getDraft(sessionToken: string): Promise<TradeDraftResponse> {
  return callApi<TradeDraftResponse>("/v1/trades/draft", sessionToken);
}

export async function saveDraft(
  sessionToken: string,
  payload: TradeDraftWritePayload,
): Promise<TradeDraftResponse> {
  return callApi<TradeDraftResponse>("/v1/trades/draft", sessionToken, {
    method: "PUT",
    body: payload,
  });
}
