import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { postPartnerTurn, type PartnerTurnRequest } from "@/lib/app/partner";
import {
  authorizePartnerRelay,
  partnerRelayFailure,
  PARTNER_NO_STORE,
} from "@/lib/app/partner-relay";

/**
 * POST — one turn of the global, journal-grounded conversation.
 *
 * The body is forwarded unchanged: FastAPI's schema is the allowlist, and
 * re-deciding it here would only create a second, drifting copy. What this
 * relay does add is the owner — from the session, never from the body.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// A partner turn is one synchronous model call: it must be allowed to
// outlive the platform's default budget, or a slow answer becomes a
// platform timeout the trader reads as a failure after paying for it.
export const maxDuration = 60;

export async function POST(request: Request) {
  const auth = await authorizePartnerRelay(request);
  if (auth instanceof NextResponse) return auth;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: PARTNER_NO_STORE });
  }

  try {
    const result = await postPartnerTurn(auth.token, body as PartnerTurnRequest);
    return NextResponse.json(result, {
      status: 200,
      headers: PARTNER_NO_STORE,
    });
  } catch (err) {
    return partnerRelayFailure(err, ApiError);
  }
}
