import "server-only";

import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFrom,
} from "@/lib/auth/session";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { ApiError } from "@/lib/api/client";

/**
 * Shared authorization for every Phase 5 relay (Task D1) — one fail-shut
 * CSRF/session/eligibility check, the same shape `trade-autofill-relay.ts`
 * gives the autofill pair, not six copies that could drift.
 */

export const ANALYSIS_NO_STORE = {
  "Cache-Control": "no-store, private",
  "Referrer-Policy": "no-referrer",
};

export async function authorizeTradeAnalysisRelay(
  request: Request,
): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  // Fail shut, matching every other trade-mutating relay in this app —
  // deliberately diverging from the `app/api/auth/*` family, whose
  // `if (siteOrigin && ...)` skips the CSRF check entirely when the variable
  // is missing. These routes spend money and write to a trader's own
  // record, so a missing origin refuses. Do not loosen this to match those.
  //
  // The refusal comes BEFORE the session lookup on purpose: a misconfigured
  // deployment must not have its behaviour depend on whether the caller
  // happens to hold a valid cookie.
  if (!siteOrigin || !isSameOriginRequest(request.headers, siteOrigin)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: ANALYSIS_NO_STORE });
  }
  const token = sessionTokenFrom(request);
  const user = token ? await authenticateSessionToken(token) : null;
  if (!token || !user) {
    return NextResponse.json({ ok: false }, { status: 401, headers: ANALYSIS_NO_STORE });
  }
  // The app-surface/email/onboarding gate is authorization here, not merely
  // page navigation: an ineligible account can call this route directly
  // without ever rendering the panel, so refuse before signing a billable
  // FastAPI mutation.
  if (appLayoutRedirect(user)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: ANALYSIS_NO_STORE });
  }
  return { token };
}

/**
 * A trade or job id, or null.
 *
 * A strict digit test rather than bare `Number()`, matching `parseTradeId`
 * in `app/api/trades/[id]/route.ts`: `Number` also accepts `"1e3"` (1000),
 * `"0x10"` (16), `"0b11"` (3) and `" 1"`, so several distinct URLs would
 * alias one row, and a 21-digit id re-serialises into the signed upstream
 * path as `"1e+21"`. 16 digits stays inside the exact-integer range.
 */
export function parseRelayId(raw: string): number | null {
  if (!/^[1-9]\d{0,15}$/.test(raw)) return null;
  return Number(raw);
}

/**
 * The three statuses whose bodies say something the status code cannot, and
 * which a trader therefore needs to read:
 *
 * - **429** carries the owner-scoped ceiling in the backend's own words.
 * - **409** says which prerequisite is missing (journal and grading both
 *   need an analysis first).
 * - **503** says the AI context could not be fingerprinted, so nothing was
 *   queued and nothing was spent.
 *
 * Every other status is `{ ok: false }` at the same code. A 404 in
 * particular is an ownership answer — its body must never leak through.
 */
const FORWARDED_DETAIL_STATUSES = new Set([409, 429, 503]);

function detailOf(body: unknown): string | undefined {
  if (typeof body !== "object" || body === null || !("detail" in body)) return undefined;
  const detail = (body as { detail: unknown }).detail;
  return typeof detail === "string" ? detail : undefined;
}

/** The one error mapping every Phase 5 relay route shares. */
export function analysisRelayError(err: unknown): NextResponse {
  if (err instanceof ApiError) {
    if (FORWARDED_DETAIL_STATUSES.has(err.status)) {
      return NextResponse.json(
        { ok: false, detail: detailOf(err.body) },
        { status: err.status, headers: ANALYSIS_NO_STORE },
      );
    }
    return NextResponse.json({ ok: false }, { status: err.status, headers: ANALYSIS_NO_STORE });
  }
  // Anything that is not an `ApiError` never reached the backend, or came
  // back unreadable. It is reported as a gateway fault and nothing about it
  // — host, address, stack — crosses to the browser.
  return NextResponse.json({ ok: false }, { status: 502, headers: ANALYSIS_NO_STORE });
}
