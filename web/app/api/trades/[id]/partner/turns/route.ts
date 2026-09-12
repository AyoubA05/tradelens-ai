import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { postTradePartnerTurn, type TradePartnerTurnRequest } from "@/lib/app/partner";
import {
  authorizePartnerRelay,
  partnerRelayFailure,
  PARTNER_NO_STORE,
} from "@/lib/app/partner-relay";
import { parseRelayId } from "@/lib/app/trade-analysis-relay";

/**
 * POST — one turn about ONE completed trade.
 *
 * The trade comes from the path and is re-checked against the session owner
 * by FastAPI; an unparseable id is a 404 here, byte-identical to the 404 a
 * foreign trade gets, so this route cannot be used to probe which ids exist.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// One synchronous model call, and with a screenshot attached it is the
// slowest one this app makes. See the global route.
export const maxDuration = 60;

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorizePartnerRelay(request);
  if (auth instanceof NextResponse) return auth;

  const tradeId = parseRelayId((await params).id);
  if (tradeId === null) {
    return NextResponse.json({ ok: false }, { status: 404, headers: PARTNER_NO_STORE });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: PARTNER_NO_STORE });
  }

  try {
    const result = await postTradePartnerTurn(auth.token, tradeId, body as TradePartnerTurnRequest);
    return NextResponse.json(result, {
      status: 200,
      headers: PARTNER_NO_STORE,
    });
  } catch (err) {
    return partnerRelayFailure(err, ApiError);
  }
}
