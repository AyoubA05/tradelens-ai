import "server-only";

import { callApi } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

/**
 * Trade autofill (Task D2): server-only bridge to
 * `POST /v1/trades/autofill` and `GET /v1/trades/autofill/{job_id}`.
 *
 * Autofill keys on a `screenshot_id` (design decision #4) — the screenshot
 * must already be finalized, so this can only ever be called for a trade
 * that already exists (Task D1/D2's `NewTradeForm` only reaches this after
 * `runUpload`/`runUrlIngest` succeeds). Nothing here writes to `trades`;
 * the job's suggestions land in the caller's draft (`trade_drafts`) and are
 * read back directly off the job status.
 */
export type TradeAutofillJobRequest = components["schemas"]["TradeAutofillJobRequest"];
export type TradeAutofillJobAccepted = components["schemas"]["TradeAutofillJobAccepted"];
export type TradeAutofillJobStatus = components["schemas"]["TradeAutofillJobStatus"];
export type AutofillSuggestion = components["schemas"]["AutofillSuggestion"];

export async function enqueueTradeAutofill(
  sessionToken: string,
  screenshotId: number,
): Promise<TradeAutofillJobAccepted> {
  const body: TradeAutofillJobRequest = { screenshot_id: screenshotId };
  return callApi<TradeAutofillJobAccepted>("/v1/trades/autofill", sessionToken, {
    method: "POST",
    body,
  });
}

export async function fetchTradeAutofillJob(
  sessionToken: string,
  jobId: number,
): Promise<TradeAutofillJobStatus> {
  return callApi<TradeAutofillJobStatus>(`/v1/trades/autofill/${jobId}`, sessionToken);
}
