import { NextResponse } from "next/server";

import { optionalEnv } from "@/lib/env";
import { isAcceptablePassword } from "@/lib/auth/contract";
import { completeReset, hashNewPassword, inspectReset } from "@/lib/auth/password-reset";
import { clientIp, isRateLimited, recordAttempt } from "@/lib/auth/rate-limit";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { logAuthEvent, publicMessageFor } from "@/lib/security/responses";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer" };
const REJECTED = "That reset link is no longer valid. Request a new one and try again.";

/**
 * GET — inspect only, mutates nothing.
 *
 * Mail security scanners fetch every link in a message before the recipient
 * sees it. A consuming GET would burn the token and the real click would always
 * fail — a self-inflicted outage indistinguishable from a token bug.
 */
export async function GET(request: Request) {
  const token = new URL(request.url).searchParams.get("token");
  const result = await inspectReset(token);
  return NextResponse.json(
    result.status === "valid"
      ? { ok: true, state: "ready" }
      : { ok: false, state: "rejected", error: REJECTED },
    { status: result.status === "valid" ? 200 : 400, headers: NO_STORE },
  );
}

/** POST — the atomic, one-time reset. */
export async function POST(request: Request) {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (siteOrigin && !isSameOriginRequest(request.headers, siteOrigin)) {
    logAuthEvent("reset", "csrf_failed");
    return NextResponse.json({ ok: false, error: REJECTED }, { status: 403, headers: NO_STORE });
  }

  const ipBucket = `ip:${clientIp(request.headers)}`;
  if (await isRateLimited(ipBucket, "reset", "reset:ip")) {
    logAuthEvent("reset", "rate_limited");
    return NextResponse.json(
      { ok: false, error: publicMessageFor("rate_limited") }, { status: 429, headers: NO_STORE });
  }

  const raw = await request.text();
  if (raw.length > 4096) {
    return NextResponse.json({ ok: false, error: REJECTED }, { status: 413, headers: NO_STORE });
  }

  let token: unknown = null;
  let password: unknown = null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      token = (parsed as Record<string, unknown>).token;
      password = (parsed as Record<string, unknown>).password;
    }
  } catch {
    /* handled below */
  }

  // Exactly the policy signup enforces — reset must never accept a password
  // signup would reject, or the two paths disagree about what is acceptable.
  if (!isAcceptablePassword(password)) {
    await recordAttempt(ipBucket, "reset", false);
    return NextResponse.json(
      { ok: false, error: publicMessageFor("weak_password") }, { status: 400, headers: NO_STORE });
  }

  // Hashed before the transaction: bcrypt cost 12 takes a few hundred
  // milliseconds and must not hold a database connection for that long.
  const newHash = await hashNewPassword(password as string);

  const outcome = await completeReset(token, newHash);
  if (outcome.status !== "reset") {
    await recordAttempt(ipBucket, "reset", false);
    logAuthEvent("reset", "invalid_token");
    return NextResponse.json({ ok: false, error: REJECTED }, { status: 400, headers: NO_STORE });
  }

  await recordAttempt(ipBucket, "reset", true);
  // Counts only — no user id, no token, no hash.
  logAuthEvent("reset", "success", {
    sessions_revoked: outcome.sessionsRevoked,
    handoffs_voided: outcome.handoffsVoided,
  });

  // Deliberately not signed in. Every session was just revoked because the old
  // password may be compromised; minting a new one here would undo that.
  return NextResponse.json(
    { ok: true, state: "reset", next: "/login" }, { status: 200, headers: NO_STORE });
}
