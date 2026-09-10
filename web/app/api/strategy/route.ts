import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { saveStrategy, type StrategyWrite } from "@/lib/app/strategy";
import { authorizeStrategyRelay, STRATEGY_NO_STORE } from "@/lib/app/strategy-relay";
import { relayFailure } from "@/lib/app/strategy-relay-failure";

/**
 * PUT — save the whole playbook against the version it was edited from.
 *
 * The body is forwarded as-is. The allowlist is FastAPI's (`StrategyWrite`,
 * `extra="forbid"`); a relay that added, renamed or dropped keys would be a
 * second, weaker copy of that rule. The backend's status is forwarded, so a
 * stale tab's 409 reaches the editor as a 409.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function PUT(request: Request) {
  const auth = await authorizeStrategyRelay(request);
  if (auth instanceof NextResponse) return auth;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: STRATEGY_NO_STORE });
  }

  try {
    const saved = await saveStrategy(auth.token, body as StrategyWrite);
    return NextResponse.json(saved, { status: 200, headers: STRATEGY_NO_STORE });
  } catch (err) {
    return relayFailure(err, ApiError);
  }
}
