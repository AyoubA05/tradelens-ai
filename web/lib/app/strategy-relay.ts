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
 * Authorization for the Strategy Profile relays — the same fail-shut
 * CSRF/session/eligibility check `analytics-relay.ts` gives Analytics.
 *
 * Deliberately NOT checked here: `strategyProfileCompleted`. First-run
 * routing lives on the Overview page only. Gating these relays on it would
 * refuse the very save and skip calls that complete first run.
 */

export const STRATEGY_NO_STORE = {
  "Cache-Control": "no-store, private",
  "Referrer-Policy": "no-referrer",
};

export async function authorizeStrategyRelay(
  request: Request,
): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  // Fail shut, and BEFORE the session lookup: a misconfigured deployment
  // must not have its behaviour depend on whether the caller holds a valid
  // cookie. These routes write the rulebook every AI review reads.
  if (!siteOrigin || !isSameOriginRequest(request.headers, siteOrigin)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: STRATEGY_NO_STORE });
  }
  const token = sessionTokenFrom(request);
  const user = token ? await authenticateSessionToken(token) : null;
  if (!token || !user) {
    return NextResponse.json({ ok: false }, { status: 401, headers: STRATEGY_NO_STORE });
  }
  // Authorization, not navigation: an ineligible account can call these
  // routes directly without ever rendering the page.
  if (appLayoutRedirect(user)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: STRATEGY_NO_STORE });
  }
  return { token };
}
