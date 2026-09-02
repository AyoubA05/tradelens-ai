import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFrom,
} from "@/lib/auth/session";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { ApiError } from "@/lib/api/client";
import { getDraft, saveDraft, type TradeDraftWritePayload } from "@/lib/app/trade-draft";

/**
 * The one bridge the New Trade draft-autosave hook has to
 * `GET`/`PUT /v1/trades/draft` (Task D3).
 *
 * Same shape as every other trade-mutating relay in this app (see
 * `app/api/trades/[id]/route.ts` and `app/api/trades/create/route.ts`):
 * fail-shut same-origin CSRF, the session resolved from the cookie only,
 * the app-eligibility gate enforced here because this route can be called
 * directly, `no-store`, and the backend's status forwarded rather than
 * reshaped.
 *
 * This relay does not decide when to save, how often, or whether the form
 * is "empty enough" to skip — all of that lives client-side in
 * `lib/app/draft-autosave.ts`. A relay that added its own debounce or
 * empty-form guard would be a second, weaker copy of a rule the caller
 * already enforces, the same mistake the CSRF check next to this comment
 * exists to not repeat.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = {
  "Cache-Control": "no-store, private",
  "Referrer-Policy": "no-referrer",
};

async function authorize(request: Request): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  // Fail shut, matching the trade-detail, create and screenshot relays'
  // deliberate divergence from the `app/api/auth/*` family. Do not loosen
  // this to match those — see the trade-detail route's comment for why.
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

export async function GET(request: Request) {
  const auth = await authorize(request);
  if (auth instanceof NextResponse) return auth;

  try {
    const draft = await getDraft(auth.token);
    return NextResponse.json(draft, { status: 200, headers: NO_STORE });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ ok: false }, { status: err.status, headers: NO_STORE });
    }
    return NextResponse.json({ ok: false }, { status: 502, headers: NO_STORE });
  }
}

export async function PUT(request: Request) {
  const auth = await authorize(request);
  if (auth instanceof NextResponse) return auth;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: NO_STORE });
  }

  try {
    const saved = await saveDraft(auth.token, body as TradeDraftWritePayload);
    return NextResponse.json(saved, { status: 200, headers: NO_STORE });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ ok: false }, { status: err.status, headers: NO_STORE });
    }
    return NextResponse.json({ ok: false }, { status: 502, headers: NO_STORE });
  }
}
