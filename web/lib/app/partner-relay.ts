import "server-only";

import { NextResponse } from "next/server";

import type { ApiError } from "@/lib/api/client";
import { optionalEnv } from "@/lib/env";
import { appLayoutRedirect, authenticateSessionToken, sessionTokenFrom } from "@/lib/auth/session";
import { isSameOriginRequest } from "@/lib/security/redirect";

/**
 * Authorization and failure mapping for the AI Partner relays.
 *
 * The same fail-shut CSRF/session/eligibility check the Strategy and
 * Analytics relays use. These routes spend money per call, so a
 * misconfigured `SITE_ORIGIN` refuses BEFORE the session lookup: whether a
 * deployment can be driven from another origin must not depend on whether
 * the caller happens to hold a valid cookie.
 *
 * Deliberately NOT checked: `strategyProfileCompleted`. The partner reads a
 * profile when one exists and does without one when it does not; first-run
 * routing lives on the Overview page.
 */

export const PARTNER_NO_STORE = {
  "Cache-Control": "no-store, private",
  "Referrer-Policy": "no-referrer",
};

export async function authorizePartnerRelay(
  request: Request,
): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (!siteOrigin || !isSameOriginRequest(request.headers, siteOrigin)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: PARTNER_NO_STORE });
  }
  const token = sessionTokenFrom(request);
  const user = token ? await authenticateSessionToken(token) : null;
  if (!token || !user) {
    return NextResponse.json({ ok: false }, { status: 401, headers: PARTNER_NO_STORE });
  }
  // Authorization, not navigation: an ineligible account can call these
  // routes directly without ever opening the drawer.
  if (appLayoutRedirect(user)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: PARTNER_NO_STORE });
  }
  return { token };
}

/**
 * Turn a failed Partner API call into the relay's response.
 *
 * The backend's status is forwarded unchanged — the conversation branches on
 * it. Its body is NOT: only the fixed codes this feature defines cross to
 * the browser, so neither an unexpected upstream message nor anything the
 * model said can reach a trader through an error path.
 *
 *   409  {detail: "transcript_invalid" | "conversation_full" | "no_trades"
 *                 | "duplicate_turn"}
 *   422  {detail: [{field, problem}, ...]}  — field names and codes only
 *   429  {detail: "rate_limited"}
 *   503  {detail: "partner_unavailable"}
 *
 * A 404 keeps its status and says nothing at all: whether that trade is
 * missing or someone else's is exactly what it must not reveal.
 */
const CONFLICT_CODES = new Set([
  "transcript_invalid",
  "conversation_full",
  "no_trades",
  "duplicate_turn",
]);

const FIXED_CODES: Record<number, string> = {
  429: "rate_limited",
  503: "partner_unavailable",
};

function safeDetail(status: number, body: unknown): unknown {
  const detail = (body as { detail?: unknown } | null | undefined)?.detail;
  if (status === 409 && typeof detail === "string" && CONFLICT_CODES.has(detail)) {
    return detail;
  }
  if (status === 422 && Array.isArray(detail)) {
    const problems = detail.flatMap((item) => {
      const field = (item as { field?: unknown })?.field;
      const problem = (item as { problem?: unknown })?.problem;
      return typeof field === "string" && typeof problem === "string" ? [{ field, problem }] : [];
    });
    return problems.length ? problems : undefined;
  }
  // Not read from the body: the code is a property of the status, so a
  // surprising upstream body cannot rename it or smuggle text through it.
  return FIXED_CODES[status];
}

export function partnerRelayFailure(err: unknown, apiError: typeof ApiError): NextResponse {
  if (err instanceof apiError) {
    const detail = safeDetail(err.status, err.body);
    return NextResponse.json(detail === undefined ? { ok: false } : { ok: false, detail }, {
      status: err.status,
      headers: PARTNER_NO_STORE,
    });
  }
  return NextResponse.json({ ok: false }, { status: 502, headers: PARTNER_NO_STORE });
}
