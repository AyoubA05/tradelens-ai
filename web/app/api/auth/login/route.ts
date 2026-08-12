import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import {
  SESSION_COOKIE,
  attemptLogin,
  openWebsiteSession,
  sessionCookieOptions,
} from "@/lib/auth/login";
import { bucketFor, clientIp, isRateLimited, recordAttempt, clearFailures } from "@/lib/auth/rate-limit";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { GENERIC_CREDENTIALS_MESSAGE, logAuthEvent, publicMessageFor } from "@/lib/security/responses";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer" };
const MAX_BODY_BYTES = 4 * 1024;

export async function POST(request: Request) {
  if (!(request.headers.get("content-type") ?? "").toLowerCase().includes("application/json")) {
    return NextResponse.json({ ok: false, error: GENERIC_CREDENTIALS_MESSAGE }, { status: 415, headers: NO_STORE });
  }

  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (siteOrigin && !isSameOriginRequest(request.headers, siteOrigin)) {
    logAuthEvent("login", "csrf_failed");
    return NextResponse.json({ ok: false, error: GENERIC_CREDENTIALS_MESSAGE }, { status: 403, headers: NO_STORE });
  }

  const raw = await request.text();
  if (raw.length > MAX_BODY_BYTES) {
    return NextResponse.json({ ok: false, error: GENERIC_CREDENTIALS_MESSAGE }, { status: 413, headers: NO_STORE });
  }

  let identifier: unknown = null;
  let password: unknown = null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      identifier = (parsed as Record<string, unknown>).identifier;
      password = (parsed as Record<string, unknown>).password;
    }
  } catch {
    /* falls through to the generic failure below */
  }

  const ipBucket = `ip:${clientIp(request.headers)}`;
  const idBucket = typeof identifier === "string" && identifier.length > 0
    ? await bucketFor("id", identifier)
    : ipBucket;

  // Per-IP counts every attempt; per-identifier counts failures only, so an
  // attacker cannot lock a known account out by deliberately burning its quota.
  if ((await isRateLimited(ipBucket, "login", "login:ip")) ||
      (await isRateLimited(idBucket, "login", "login:id"))) {
    logAuthEvent("login", "rate_limited");
    return NextResponse.json({ ok: false, error: publicMessageFor("rate_limited") }, { status: 429, headers: NO_STORE });
  }

  const result = await attemptLogin(identifier, password);

  if (!result.ok) {
    await recordAttempt(ipBucket, "login", false);
    await recordAttempt(idBucket, "login", false);
    logAuthEvent("login", result.reason === "email_unverified" ? "email_unverified" : "wrong_password");

    // bad_credentials and inactive collapse to one message: whether an account
    // exists but is disabled is not something a stranger should be able to ask.
    if (result.reason === "email_unverified") {
      return NextResponse.json(
        { ok: false, error: publicMessageFor("email_unverified"), verificationRequired: true },
        { status: 403, headers: NO_STORE },
      );
    }
    return NextResponse.json({ ok: false, error: GENERIC_CREDENTIALS_MESSAGE }, { status: 401, headers: NO_STORE });
  }

  const { token, expiresAt } = await openWebsiteSession(result.userId);
  await recordAttempt(ipBucket, "login", true);
  await clearFailures(idBucket, "login");
  logAuthEvent("login", "success");

  // State-based, not hardcoded. An account that has already completed personal
  // onboarding must not be sent back through it. /continue is an explicit
  // placeholder — the Streamlit handoff is step 9 and is not faked here.
  const next = result.onboardingCompleted ? "/continue" : "/onboarding";

  const response = NextResponse.json(
    // No user id, username, or email. The handoff to Streamlit is a later step;
    // this establishes the website session and nothing more.
    { ok: true, next },
    { status: 200, headers: NO_STORE },
  );
  response.cookies.set(
    SESSION_COOKIE,
    token,
    sessionCookieOptions(expiresAt, (siteOrigin || "https://").startsWith("https://")),
  );
  return response;
}
