import "server-only";

import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFrom,
} from "@/lib/auth/session";
import { isSameOriginRequest } from "@/lib/security/redirect";

/**
 * Shared authorization for both autofill relay routes (enqueue and poll),
 * the same shape `trade-summary-relay.ts` gives the summary pair — one
 * fail-shut CSRF/session/eligibility check, not two copies that could drift.
 */

export const AUTOFILL_NO_STORE = {
  "Cache-Control": "no-store, private",
  "Referrer-Policy": "no-referrer",
};

export async function authorizeTradeAutofillRelay(
  request: Request,
): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  // Fail shut, matching every other trade-mutating relay in this app —
  // deliberately diverging from the `app/api/auth/*` family. Do not loosen
  // this to match those.
  if (!siteOrigin || !isSameOriginRequest(request.headers, siteOrigin)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: AUTOFILL_NO_STORE });
  }
  const token = sessionTokenFrom(request);
  const user = token ? await authenticateSessionToken(token) : null;
  if (!token || !user) {
    return NextResponse.json({ ok: false }, { status: 401, headers: AUTOFILL_NO_STORE });
  }
  if (appLayoutRedirect(user)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: AUTOFILL_NO_STORE });
  }
  return { token };
}
