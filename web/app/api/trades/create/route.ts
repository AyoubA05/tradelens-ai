import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFrom,
} from "@/lib/auth/session";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { ApiError } from "@/lib/api/client";
import { createTrade } from "@/lib/app/new-trade-create";
import type { TradeCreate } from "@/lib/app/new-trade";

/**
 * The one bridge the New Trade Client Component has to FastAPI's
 * `POST /v1/trades`.
 *
 * Same shape as `app/api/trades/[id]/route.ts` (Task C3's sibling route):
 * fail-shut same-origin CSRF, session resolved from the cookie only, the
 * app-eligibility gate enforced here (not just by the page it normally
 * arrives from) because this route can be called directly. The allowlist,
 * the future-date check against the owner's own calendar, the fingerprint
 * dedup (design decision #5) and the P&L/outcome contradiction guard all
 * live service-side — this handler relays the session token and the
 * backend's status code, and does not re-implement any of them.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = {
  "Cache-Control": "no-store, private",
  "Referrer-Policy": "no-referrer",
};

/** The backend's own user-facing message, when it sent one. */
function detailFrom(body: unknown): string | undefined {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return undefined;
}

async function authorize(request: Request): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  // Fail shut, matching the trade-detail relay's deliberate divergence from
  // the `app/api/auth/*` family — see that route's comment for why.
  if (!siteOrigin || !isSameOriginRequest(request.headers, siteOrigin)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: NO_STORE });
  }
  const token = sessionTokenFrom(request);
  const user = token ? await authenticateSessionToken(token) : null;
  if (!token || !user) {
    return NextResponse.json({ ok: false }, { status: 401, headers: NO_STORE });
  }
  if (appLayoutRedirect(user)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: NO_STORE });
  }
  return { token };
}

export async function POST(request: Request) {
  const auth = await authorize(request);
  if (auth instanceof NextResponse) return auth;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: NO_STORE });
  }

  try {
    const created = await createTrade(auth.token, body as TradeCreate);
    // `callApi` does not surface the backend's own 200-vs-201 split (design
    // decision #5's "nothing created" vs "created" distinction), only the
    // parsed body — so this relay always answers 200 on success and the
    // caller branches on `created.duplicate_of` in the body, which carries
    // the same information without depending on a status code this layer
    // cannot see.
    return NextResponse.json(created, { status: 200, headers: NO_STORE });
  } catch (err) {
    if (err instanceof ApiError) {
      // 422 (a P&L/outcome contradiction the client-side check missed, or a
      // future trade_date) is the one status whose body says something the
      // trader can act on: the backend's message names the contradiction or
      // the offending date, and without it the form can only show generic
      // "this did not save" copy that tells them nothing to fix. Same shape
      // as the summary relay's 429 — forward `detail` for that status only,
      // so no other backend message leaks through. The client's job is to
      // show it, never to reshape or retry past it.
      if (err.status === 422) {
        const detail = detailFrom(err.body);
        return NextResponse.json(
          { ok: false, ...(detail ? { detail } : {}) },
          { status: 422, headers: NO_STORE },
        );
      }
      return NextResponse.json({ ok: false }, { status: err.status, headers: NO_STORE });
    }
    return NextResponse.json({ ok: false }, { status: 502, headers: NO_STORE });
  }
}
