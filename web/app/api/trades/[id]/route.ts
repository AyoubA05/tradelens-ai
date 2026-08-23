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

// Matches the nine `app/api/auth/*` routes exactly. The referrer policy is
// negligible on a JSON response, but this file already diverges from that
// family once on purpose (the fail-shut CSRF check below), and an
// undocumented second divergence reads as one more deliberate decision to
// work out.
const NO_STORE = {
  "Cache-Control": "no-store, private",
  "Referrer-Policy": "no-referrer",
};

/**
 * A trade id, or null.
 *
 * A strict digit test, not bare `Number()`: `Number` also accepts the other
 * JavaScript numeric literal forms — `"1e3"` → 1000, `"0x10"` → 16,
 * `"0b11"` → 3, `" 1"` → 1 — so several different URLs would alias one row.
 * Worse, `"999999999999999999999"` parses to `1e21`, which satisfies
 * `Number.isInteger`, and `String(1e21)` then puts the literal `"1e+21"`
 * into both the upstream request path and the HMAC-signed canonical path.
 * Ownership is enforced backend-side either way, so neither is exploitable
 * — they are simply wrong. 16 digits keeps every accepted value inside the
 * range where a JS number represents an integer exactly.
 */
function parseTradeId(raw: string): number | null {
  if (!/^[1-9]\d{0,15}$/.test(raw)) return null;
  return Number(raw);
}

/**
 * True when the backend's 503 says at least one screenshot can never be
 * cleaned up by this owner.
 *
 * The backend reports `remaining` (an object-store fault a retry clears)
 * separately from `unresolvable` (a screenshot row naming a path this owner
 * is not entitled to delete) precisely so a caller does not tell a trader to
 * keep retrying something that cannot succeed. Collapsing the two back into
 * one opaque signal here would throw away the reason that split exists.
 *
 * An unreadable body is treated as retryable — the weaker of the two claims.
 * Nothing was deleted in either case, and neither branch may imply otherwise.
 */
function cleanupIsUnresolvable(body: unknown): boolean {
  const detail = (body as { detail?: { unresolvable?: unknown } } | null | undefined)?.detail;
  return typeof detail?.unresolvable === "number" && detail.unresolvable > 0;
}

async function authorize(request: Request): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  // Fail shut, deliberately diverging from the nine `app/api/auth/*` routes.
  // Those guard with `if (siteOrigin && ...)`, so an unset SITE_ORIGIN skips
  // their CSRF check entirely. This relay is the first of that family to
  // guard trade data rather than an auth flow, so a missing origin refuses
  // the request instead of waving it through. The auth routes are tracked as
  // a separate hardening pass — do not "restore consistency" by loosening
  // this one to match them.
  if (!siteOrigin || !isSameOriginRequest(request.headers, siteOrigin)) {
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
      // could read as "partly done." `unresolvable` rides along so the
      // dialog can tell a trader whether trying again can ever work; without
      // it, the backend's deliberate split would die at this boundary.
      const payload =
        err.status === 503
          ? {
              error: "screenshot_cleanup_failed" as const,
              unresolvable: cleanupIsUnresolvable(err.body),
            }
          : { ok: false as const };
      return NextResponse.json(payload, { status: err.status, headers: NO_STORE });
    }
    return NextResponse.json({ ok: false }, { status: 502, headers: NO_STORE });
  }
}
