import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import {
  authenticateWebsiteRequest,
  emailGatePassed,
  nextDestinationFor,
} from "@/lib/auth/session";
import { completeOnboarding, validateOnboarding } from "@/lib/auth/onboarding";
import { clientIp, isRateLimited, recordAttempt } from "@/lib/auth/rate-limit";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { logAuthEvent } from "@/lib/security/responses";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer" };
const MAX_BODY_BYTES = 4 * 1024;
const GENERIC = "We could not save that. Check the details and try again.";

function fail(status: number, error = GENERIC, extra: Record<string, unknown> = {}) {
  return NextResponse.json({ ok: false, error, ...extra }, { status, headers: NO_STORE });
}

export async function POST(request: Request) {
  if (!(request.headers.get("content-type") ?? "").toLowerCase().includes("application/json")) {
    return fail(415);
  }

  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (siteOrigin && !isSameOriginRequest(request.headers, siteOrigin)) {
    logAuthEvent("onboarding", "csrf_failed");
    return fail(403);
  }

  // Identity comes from the validated session and nowhere else. Any user_id,
  // username, or email in the body is not merely rejected — it is never read,
  // so there is no code path in which a client can nominate an account.
  const user = await authenticateWebsiteRequest(request);
  if (!user) {
    logAuthEvent("onboarding", "unknown_identifier");
    return fail(401, "Sign in to continue.", { next: "/login" });
  }

  // Re-checked here rather than trusted from login: a session can outlive a
  // change to the account's verification state, and a hand-crafted request
  // must not slip past a gate that only the login form happened to apply.
  if (!emailGatePassed(user)) {
    logAuthEvent("onboarding", "email_unverified");
    return fail(403, "Verify your email address first.", { next: "/verify-email" });
  }

  if (user.onboardingCompleted) {
    // Not an error, and deliberately not an update: first-run onboarding must
    // not double as an account editor.
    return NextResponse.json(
      { ok: true, state: "already_completed", next: nextDestinationFor(user) },
      { status: 200, headers: NO_STORE },
    );
  }

  const ipBucket = `ip:${clientIp(request.headers)}`;
  if (await isRateLimited(ipBucket, "signup", "signup:ip")) {
    logAuthEvent("onboarding", "rate_limited");
    return fail(429);
  }

  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) return fail(413);

  let body: Record<string, unknown>;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return fail(400);
    body = parsed as Record<string, unknown>;
  } catch {
    return fail(400);
  }

  const validated = validateOnboarding(body);
  if (!validated.ok) {
    await recordAttempt(ipBucket, "signup", false);
    return fail(400);
  }

  const outcome = await completeOnboarding(user.userId, validated.value);
  if (outcome.status === "rejected") {
    logAuthEvent("onboarding", "inactive_account");
    return fail(403);
  }

  logAuthEvent("onboarding", "success");
  // strategy_profile_completed is untouched and stays false. That false is what
  // makes Streamlit require the first-run Strategy Profile in a later step.
  return NextResponse.json(
    { ok: true, state: outcome.status, next: "/continue" },
    { status: 200, headers: NO_STORE },
  );
}
