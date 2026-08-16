import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import { authenticateWebsiteRequest } from "@/lib/auth/session";
import { handoffEligibility, issueHandoff } from "@/lib/auth/handoff";
import { handoffRedirectUrl } from "@/lib/security/app-origin";
import { clientIp, isRateLimited } from "@/lib/auth/rate-limit";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { logAuthEvent } from "@/lib/security/responses";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// The redirect carries a live credential in its URL, so nothing on this path
// may be cached and no Referer may leak it to another origin.
const NO_STORE = { "Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer" };
const MAX_BODY_BYTES = 1024;

/**
 * POST only, deliberately.
 *
 * A GET issuer would mint credentials on browser prefetch, on a crawler visit,
 * and on every accidental refresh — each one silently invalidating the previous
 * token under the one-outstanding-handoff rule, so a user could end up racing
 * their own prefetch. State changes belong behind POST, and POST is also what
 * makes the same-origin check meaningful.
 */
export async function POST(request: Request) {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (siteOrigin && !isSameOriginRequest(request.headers, siteOrigin)) {
    logAuthEvent("handoff", "csrf_failed");
    return NextResponse.json({ ok: false }, { status: 403, headers: NO_STORE });
  }

  // Body is read only to bound it. Nothing in it is used: the user comes from
  // the session, the destination from server config. There is no field a client
  // could set that would change what this endpoint does.
  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) {
    return NextResponse.json({ ok: false }, { status: 413, headers: NO_STORE });
  }

  const user = await authenticateWebsiteRequest(request);
  const eligibility = handoffEligibility(user);
  if (!eligibility.eligible) {
    logAuthEvent("handoff", eligibility.reason === "no_session" ? "unknown_identifier"
      : eligibility.reason === "email_unverified" ? "email_unverified" : "inactive_account");
    const next = eligibility.reason === "no_session" ? "/login"
      : eligibility.reason === "email_unverified" ? "/verify-email" : "/onboarding";
    return NextResponse.json(
      { ok: false, next }, { status: eligibility.reason === "no_session" ? 401 : 403, headers: NO_STORE });
  }

  const ipBucket = `ip:${clientIp(request.headers)}`;
  // Generous on purpose: a double click or an ordinary retry must not lock a
  // real user out of their own journal.
  if (await isRateLimited(ipBucket, "login", "login:ip")) {
    logAuthEvent("handoff", "rate_limited");
    return NextResponse.json({ ok: false }, { status: 429, headers: NO_STORE });
  }

  let destination: string;
  try {
    const { token, invalidated } = await issueHandoff(user!.userId);
    // The raw token exists only across these two lines.
    destination = handoffRedirectUrl(token);
    // Counts only. No token, no user id, no destination with the token in it.
    logAuthEvent("handoff", "success", { invalidated_prior: invalidated });
  } catch {
    logAuthEvent("handoff", "invalid_token", { stage: "issue" });
    return NextResponse.json({ ok: false }, { status: 500, headers: NO_STORE });
  }

  // 303 so the browser follows with GET and the POST is not repeated on a back
  // navigation — which would mint a second token and invalidate this one.
  return NextResponse.redirect(destination, { status: 303, headers: NO_STORE });
}

/** GET must never mint a credential. */
export async function GET() {
  return NextResponse.json(
    { ok: false, error: "Use POST." }, { status: 405, headers: { ...NO_STORE, Allow: "POST" } });
}
