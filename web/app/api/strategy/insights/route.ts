import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { appendStrategyInsight, type StrategyInsightRequest } from "@/lib/app/strategy";
import { authorizeStrategyRelay, STRATEGY_NO_STORE } from "@/lib/app/strategy-relay";
import { relayFailure } from "@/lib/app/strategy-relay-failure";

/**
 * POST — add one repeated correction to risk rules.
 *
 * The body names a correction group; it never carries rule text and never
 * names a column. Both are fixed server-side, and FastAPI refuses any other
 * key. This relay forwards the body unchanged rather than re-deciding that.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const auth = await authorizeStrategyRelay(request);
  if (auth instanceof NextResponse) return auth;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: STRATEGY_NO_STORE });
  }

  try {
    const result = await appendStrategyInsight(auth.token, body as StrategyInsightRequest);
    return NextResponse.json(result, { status: 200, headers: STRATEGY_NO_STORE });
  } catch (err) {
    return relayFailure(err, ApiError);
  }
}
