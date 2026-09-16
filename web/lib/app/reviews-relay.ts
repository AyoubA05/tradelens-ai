import "server-only";

import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api/client";
import { optionalEnv } from "@/lib/env";
import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFrom,
} from "@/lib/auth/session";
import { isSameOriginRequest } from "@/lib/security/redirect";

/**
 * Authorization and failure mapping for the AI Reviews relays.
 *
 * Two of these routes start paid work, so a misconfigured `SITE_ORIGIN`
 * refuses BEFORE the session lookup, exactly like the trade-summary relay.
 */

export const REVIEWS_NO_STORE = {
  "Cache-Control": "no-store, private",
  "Referrer-Policy": "no-referrer",
};

const KNOWN_REFUSALS = new Set(["empty_period", "not_enough_trades"]);

/**
 * The backend's two fixed 429 sentences, verbatim from
 * `WEEKLY_LIMIT_MESSAGE` / `DAILY_LIMIT_MESSAGE` in
 * `src/tradelens/api/routers/reviews.py`. Any other 429 detail is dropped.
 */
export const WEEKLY_LIMIT_MESSAGE =
  "You've reached today's limit for weekly recaps. " +
  "Recaps you've already generated are still available.";
export const DAILY_LIMIT_MESSAGE =
  "You've reached today's limit for daily debriefs. " +
  "Debriefs you've already generated are still available.";
const KNOWN_LIMIT_MESSAGES: ReadonlySet<unknown> = new Set([
  WEEKLY_LIMIT_MESSAGE,
  DAILY_LIMIT_MESSAGE,
]);

export async function authorizeReviewsRelay(
  request: Request,
): Promise<{ token: string } | NextResponse> {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (!siteOrigin || !isSameOriginRequest(request.headers, siteOrigin)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: REVIEWS_NO_STORE });
  }
  const token = sessionTokenFrom(request);
  const user = token ? await authenticateSessionToken(token) : null;
  if (!token || !user) {
    return NextResponse.json({ ok: false }, { status: 401, headers: REVIEWS_NO_STORE });
  }
  if (appLayoutRedirect(user)) {
    return NextResponse.json({ ok: false }, { status: 403, headers: REVIEWS_NO_STORE });
  }
  return { token };
}

/**
 * Turn a failed reviews API call into the relay's response.
 *
 *   409  → `{ok:false, detail}` only for `empty_period` / `not_enough_trades`
 *   429  → `{ok:false, error:"rate_limited", detail}` — `detail` only when it is one
 *          of the two backend limit sentences, otherwise omitted
 *   503  → `{ok:false, detail:"review_unavailable"}` for that code only
 *   401/403/404/422 → `{ok:false}` with that status
 *   anything else   → 502 `{ok:false}`
 *
 * No other backend text crosses.
 */
export function reviewsRelayFailure(error: unknown): NextResponse {
  if (!(error instanceof ApiError)) {
    return NextResponse.json({ ok: false }, { status: 502, headers: REVIEWS_NO_STORE });
  }
  const detail = (error.body as { detail?: unknown } | null | undefined)?.detail;

  if (error.status === 409) {
    const body =
      typeof detail === "string" && KNOWN_REFUSALS.has(detail)
        ? { ok: false, detail }
        : { ok: false };
    return NextResponse.json(body, { status: 409, headers: REVIEWS_NO_STORE });
  }
  if (error.status === 429) {
    return NextResponse.json(
      { ok: false, error: "rate_limited", detail: KNOWN_LIMIT_MESSAGES.has(detail) ? detail : undefined },
      { status: 429, headers: REVIEWS_NO_STORE },
    );
  }
  if (error.status === 503 && detail === "review_unavailable") {
    return NextResponse.json(
      { ok: false, detail: "review_unavailable" },
      { status: 503, headers: REVIEWS_NO_STORE },
    );
  }
  if ([401, 403, 404, 422].includes(error.status)) {
    return NextResponse.json({ ok: false }, { status: error.status, headers: REVIEWS_NO_STORE });
  }
  return NextResponse.json({ ok: false }, { status: 502, headers: REVIEWS_NO_STORE });
}

/** A generate body is `{"week": "YYYY-MM-DD"}` — anything near this size is not one. */
export const MAX_REVIEW_REQUEST_BYTES = 1_024;

/**
 * Read a generate body, bounded, or `undefined` when it is oversized or not JSON.
 * The declared length is checked first; the read text is checked again because
 * the header is advisory.
 */
export async function readJsonBody(request: Request): Promise<{ body: unknown } | undefined> {
  const declared = Number(request.headers.get("content-length") ?? "0");
  if (!Number.isFinite(declared) || declared > MAX_REVIEW_REQUEST_BYTES) return undefined;
  try {
    const raw = await request.text();
    if (new TextEncoder().encode(raw).byteLength > MAX_REVIEW_REQUEST_BYTES) return undefined;
    return { body: JSON.parse(raw) as unknown };
  } catch {
    return undefined;
  }
}
