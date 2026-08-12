import { NextResponse } from "next/server";

import { optionalEnv, requireEnv } from "@/lib/env";
import { normalizeEmail } from "@/lib/auth/contract";
import { issueVerification, verificationUrl } from "@/lib/auth/verification";
import { query } from "@/lib/db/client";
import { mailTransport, verificationMessage } from "@/lib/mail/transport";
import {
  bucketFor,
  clientIp,
  isRateLimited,
  recordAttempt,
} from "@/lib/auth/rate-limit";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { logAuthEvent } from "@/lib/security/responses";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer" };

/**
 * One response for every outcome.
 *
 * Address unknown, already verified, and genuinely resent all return this. Any
 * difference between them turns the resend form into an oracle for "does this
 * person have a TradeLens account, and have they confirmed their email?" —
 * which is exactly the question an attacker enumerating a breach list wants
 * answered.
 */
const NEUTRAL =
  "If that address needs verifying, a new link is on its way. It expires in 24 hours.";

export async function POST(request: Request) {
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (siteOrigin && !isSameOriginRequest(request.headers, siteOrigin)) {
    logAuthEvent("resend", "csrf_failed");
    return NextResponse.json({ ok: false, error: NEUTRAL }, { status: 403, headers: NO_STORE });
  }

  const ipBucket = `ip:${clientIp(request.headers)}`;
  if (await isRateLimited(ipBucket, "verify", "forgot:ip")) {
    logAuthEvent("resend", "rate_limited");
    // Still neutral: a distinct "rate limited" reply for a known address and a
    // generic one for an unknown address would leak the distinction anyway.
    return NextResponse.json({ ok: true, message: NEUTRAL }, { status: 200, headers: NO_STORE });
  }

  let email: string | null = null;
  try {
    const body: unknown = await request.json();
    if (typeof body === "object" && body !== null && !Array.isArray(body)) {
      email = normalizeEmail((body as Record<string, unknown>).email);
    }
  } catch {
    email = null;
  }

  // Malformed input gets the same answer as everything else.
  if (email === null) {
    await recordAttempt(ipBucket, "verify", false);
    return NextResponse.json({ ok: true, message: NEUTRAL }, { status: 200, headers: NO_STORE });
  }

  const emailBucket = await bucketFor("id", email);
  if (await isRateLimited(emailBucket, "verify", "forgot:id")) {
    logAuthEvent("resend", "rate_limited");
    return NextResponse.json({ ok: true, message: NEUTRAL }, { status: 200, headers: NO_STORE });
  }
  await recordAttempt(emailBucket, "verify", false);
  await recordAttempt(ipBucket, "verify", false);

  const rows = await query<{ id: number }>(
    `SELECT id FROM users
      WHERE email = $1
        AND email_verification_required = true
        AND email_verified_at IS NULL`,
    [email],
  );

  // Nothing to do — unknown address, or already verified. Same response.
  if (rows.length !== 1) {
    logAuthEvent("resend", "unknown_identifier");
    return NextResponse.json({ ok: true, message: NEUTRAL }, { status: 200, headers: NO_STORE });
  }

  const userId = rows[0]!.id;
  // Supersedes any outstanding token in the same transaction, so a burst of
  // resends still leaves exactly one live token.
  const issued = await issueVerification(userId, email);

  const origin = siteOrigin || requireEnv("SITE_ORIGIN");
  const outcome = await mailTransport().send(
    verificationMessage(email, verificationUrl(origin, issued.token)),
  );

  // The token was created regardless; the account stays recoverable and the
  // user can resend. Delivery state is recorded internally, never disclosed.
  logAuthEvent(
    "resend",
    outcome.status === "sent" ? "success" : outcome.status === "failed" ? "email_send_failed" : "email_unconfigured",
  );

  return NextResponse.json({ ok: true, message: NEUTRAL }, { status: 200, headers: NO_STORE });
}
