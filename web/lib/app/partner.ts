import "server-only";

import { callApi } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

/**
 * The AI Partner's server-only bridge to `/v1/partner`.
 *
 * There is no `fetchConversation`: the server stores no transcript. The
 * browser holds every turn and hands them back signed, so a "conversation"
 * exists only for as long as one tab keeps it. Nothing here mints, edits or
 * re-signs a turn — the `mac` on each turn is the server's, and a turn that
 * arrives altered is refused rather than repaired.
 */
export type PartnerTurnRequest = components["schemas"]["PartnerTurnRequest"];
export type TradePartnerTurnRequest = components["schemas"]["TradePartnerTurnRequest"];
export type PartnerTurnResponse = components["schemas"]["PartnerTurnResponse"];
export type PartnerTranscriptTurn = components["schemas"]["PartnerTranscriptTurn"];
export type PartnerEvidence = components["schemas"]["PartnerEvidence"];

export async function postPartnerTurn(
  sessionToken: string,
  body: PartnerTurnRequest,
): Promise<PartnerTurnResponse> {
  return callApi<PartnerTurnResponse>("/v1/partner/turns", sessionToken, {
    method: "POST",
    body,
  });
}

/**
 * One turn about one trade. The trade is named by the PATH, never by the
 * body, and the body never names a screenshot: `include_screenshot` asks for
 * that trade's own, and the server chooses which object that is.
 */
export async function postTradePartnerTurn(
  sessionToken: string,
  tradeId: number,
  body: TradePartnerTurnRequest,
): Promise<PartnerTurnResponse> {
  return callApi<PartnerTurnResponse>(`/v1/trades/${tradeId}/partner/turns`, sessionToken, {
    method: "POST",
    body,
  });
}
