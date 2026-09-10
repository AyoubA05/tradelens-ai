import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { skipStrategy } from "@/lib/app/strategy";
import { authorizeStrategyRelay, STRATEGY_NO_STORE } from "@/lib/app/strategy-relay";
import { relayFailure } from "@/lib/app/strategy-relay-failure";

/**
 * POST — "I don't have a defined strategy yet". Completes first run and
 * writes no profile. Takes no body: there is nothing a browser could say
 * here that the server should act on.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const auth = await authorizeStrategyRelay(request);
  if (auth instanceof NextResponse) return auth;

  try {
    const result = await skipStrategy(auth.token);
    return NextResponse.json(result, { status: 200, headers: STRATEGY_NO_STORE });
  } catch (err) {
    return relayFailure(err, ApiError);
  }
}
