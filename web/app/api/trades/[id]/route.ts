import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import { authenticateSessionToken, sessionTokenFrom } from "@/lib/auth/session";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { ApiError } from "@/lib/api/client";
import { deleteTrade, patchTrade, type TradeUpdate } from "@/lib/app/trades";

/**
 * The one bridge a Trade Detail Client Component has to the FastAPI backend.
 *
 * `callApi` (and therefore `patchTrade`/`deleteTrade`) is `server-only` and
 * carries the service secret, so a Client Component cannot call it directly
 * — this route handler is the same shape every other website mutation uses
 * (see `app/api/auth/*`): same-origin CSRF check, then the session cookie
 * resolved to a token and forwarded, never anything from the request body.
 *
 * This is a thin relay, deliberately. The allowlist, the conflict guard and
 * the delete-cleanup guarantee all live service-side (design decisions #4,
 * #5, #6) — this handler's job is to get the session token from the cookie
 * to `callApi` and the backend's status code back to the caller, not to
 * re-implement any of those guarantees.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store, private" };

function parseTradeId(raw: string): number | null {
  const id = Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}

async function authorize(request: Request): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (siteOrigin && !isSameOriginRequest(request.headers, siteOrigin)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: NO_STORE });
  }
  const token = sessionTokenFrom(request);
  const user = token ? await authenticateSessionToken(token) : null;
  if (!token || !user) {
    return NextResponse.json({ ok: false }, { status: 401, headers: NO_STORE });
  }
  return { token };
}

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize(request);
  if (auth instanceof NextResponse) return auth;

  const tradeId = parseTradeId((await params).id);
  if (tradeId === null) return NextResponse.json({ ok: false }, { status: 404, headers: NO_STORE });

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: NO_STORE });
  }

  try {
    const updated = await patchTrade(auth.token, tradeId, body as TradeUpdate);
    return NextResponse.json(updated, { status: 200, headers: NO_STORE });
  } catch (err) {
    if (err instanceof ApiError) {
      // The 409 body is intentionally generic — the client's response to a
      // conflict is to re-fetch the trade and show the trader its current
      // state, not to parse a diff out of this response.
      const payload =
        err.status === 409 ? { error: "stale_trade" as const } : { ok: false as const };
      return NextResponse.json(payload, { status: err.status, headers: NO_STORE });
    }
    return NextResponse.json({ ok: false }, { status: 502, headers: NO_STORE });
  }
}

export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const auth = await authorize(request);
  if (auth instanceof NextResponse) return auth;

  const tradeId = parseTradeId((await params).id);
  if (tradeId === null) return NextResponse.json({ ok: false }, { status: 404, headers: NO_STORE });

  try {
    await deleteTrade(auth.token, tradeId);
    return new NextResponse(null, { status: 204, headers: NO_STORE });
  } catch (err) {
    if (err instanceof ApiError) {
      // A 503 here means cleanup failed and the row is still there (design
      // decision #6 / the Risks section) — never reshaped into anything that
      // could read as "partly done."
      const payload =
        err.status === 503
          ? { error: "screenshot_cleanup_failed" as const }
          : { ok: false as const };
      return NextResponse.json(payload, { status: err.status, headers: NO_STORE });
    }
    return NextResponse.json({ ok: false }, { status: 502, headers: NO_STORE });
  }
}
