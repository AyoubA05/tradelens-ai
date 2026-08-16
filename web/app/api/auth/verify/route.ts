import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import { consumeVerification, inspectVerification } from "@/lib/auth/verification";
import { clientIp, clearFailures, isRateLimited } from "@/lib/auth/rate-limit";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { logAuthEvent } from "@/lib/security/responses";

export const runtime = "nodejs";
// Never cached: a verification page reflects one-time state, and a cached copy
// on a shared proxy would show one user's outcome to another.
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer" };

/** Invalid, expired, consumed, superseded and email-mismatch all read alike. */
const REJECTED = "That link is no longer valid. Request a new one and try again.";

/**
 * GET — inspect only. Mutates nothing.
 *
 * Corporate mail security scanners fetch every link in a message before the
 * recipient ever sees it. If GET consumed the token, the scanner would burn it
 * and the real user's click would always fail — a self-inflicted denial of
 * service that looks exactly like a bug in our token handling.
 *
 * So GET answers one question ("would this token work?") and the actual state
 * change happens on POST, from a form the human submits. That also gives the
 * consume step a same-origin check, which a GET navigation cannot have.
 */
export async function GET(request: Request) {
  const token = new URL(request.url).searchParams.get("token");
  const result = await inspectVerification(token);
  return NextResponse.json(
    result.status === "valid" ? { ok: true, state: "ready" } : { ok: false, state: "rejected", error: REJECTED },
    { status: result.status === "valid" ? 200 : 400, headers: NO_STORE },
  );
}

/** POST — the actual, atomic, one-time consume. */
export async function POST(request: Request) {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (siteOrigin && !isSameOriginRequest(request.headers, siteOrigin)) {
    logAuthEvent("verify", "csrf_failed");
    return NextResponse.json({ ok: false, error: REJECTED }, { status: 403, headers: NO_STORE });
  }

  const ipBucket = `ip:${clientIp(request.headers)}`;
  if (await isRateLimited(ipBucket, "verify", "verify:ip")) {
    logAuthEvent("verify", "rate_limited");
    return NextResponse.json(
      { ok: false, error: "Too many attempts. Wait a few minutes and try again." },
      { status: 429, headers: NO_STORE },
    );
  }

  let token: unknown = null;
  try {
    const body: unknown = await request.json();
    if (typeof body === "object" && body !== null && !Array.isArray(body)) {
      token = (body as Record<string, unknown>).token;
    }
  } catch {
    token = null;
  }

  const result = await consumeVerification(token);
  if (result.status !== "verified") {
    // No user id, no email, no token — the log says a verify failed, nothing more.
    logAuthEvent("verify", "invalid_token");
    return NextResponse.json({ ok: false, error: REJECTED }, { status: 400, headers: NO_STORE });
  }

  await clearFailures(ipBucket, "verify");
  logAuthEvent("verify", "success");
  // Not signed in here. Verification proves an address; it is not authentication,
  // and inventing a session at this point would be inventing semantics the
  // approved design does not call for.
  return NextResponse.json(
    { ok: true, state: "verified", next: "/login" },
    { status: 200, headers: NO_STORE },
  );
}
