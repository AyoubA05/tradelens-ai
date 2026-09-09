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
 * Authorization for the analytics relay (Task C1) — the same fail-shut
 * CSRF/session/eligibility check `trade-analysis-relay.ts` gives the Phase 5
 * routes, in one place rather than inlined into the route handler.
 */

export const ANALYTICS_NO_STORE = {
  "Cache-Control": "no-store, private",
  "Referrer-Policy": "no-referrer",
};

export async function authorizeAnalyticsRelay(
  request: Request,
): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  // Fail shut, matching every other app relay in this codebase —
  // deliberately diverging from the `app/api/auth/*` family, whose
  // `if (siteOrigin && ...)` skips the CSRF check entirely when the variable
  // is missing. This route reads a trader's whole performance record, so a
  // missing origin refuses. Do not loosen this to match those.
  //
  // The refusal comes BEFORE the session lookup on purpose: a misconfigured
  // deployment must not have its behaviour depend on whether the caller
  // happens to hold a valid cookie.
  if (!siteOrigin || !isSameOriginRequest(request.headers, siteOrigin)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: ANALYTICS_NO_STORE });
  }
  const token = sessionTokenFrom(request);
  const user = token ? await authenticateSessionToken(token) : null;
  if (!token || !user) {
    return NextResponse.json({ ok: false }, { status: 401, headers: ANALYTICS_NO_STORE });
  }
  // The app-surface/email/onboarding gate is authorization here, not merely
  // page navigation: an ineligible account can call this route directly
  // without ever rendering the page.
  if (appLayoutRedirect(user)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: ANALYTICS_NO_STORE });
  }
  return { token };
}
