import { NextResponse } from "next/server";

import { emailConfigured, optionalEnv, requireEnv } from "@/lib/env";
import { normalizeEmail } from "@/lib/auth/contract";
import { issueReset, resetEligibility, resetUrl } from "@/lib/auth/password-reset";
import { passwordResetMessage } from "@/lib/mail/messages";
import { mailTransport } from "@/lib/mail/transport";
import { bucketFor, clientIp, isRateLimited } from "@/lib/auth/rate-limit";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { logAuthEvent } from "@/lib/security/responses";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer" };

/**
 * One response for every outcome.
 *
 * Nonexistent address, unverified address, verified address, legacy account
 * with no address, malformed input, and rate-limited all return exactly this,
 * with the same 200 status. Any variation turns the form into an oracle for
 * "does this person have a TradeLens account, and is their email confirmed?"
 */
const NEUTRAL =
  "If an eligible account exists, password reset instructions will be sent. The link expires in 30 minutes.";

/**
 * `mailConfigured` is a property of the deployment, not of the address that was
 * submitted — it is identical for every input, so it discloses nothing about
 * whether an account exists. It is here so the page can stop asserting that
 * nothing was sent in an environment where mail works perfectly well.
 */
function neutral() {
  return NextResponse.json(
    { ok: true, message: NEUTRAL, mailConfigured: emailConfigured() },
    { status: 200, headers: NO_STORE },
  );
}

export async function POST(request: Request) {
  if (!(request.headers.get("content-type") ?? "").toLowerCase().includes("application/json")) {
    return neutral();
  }
  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (siteOrigin && !isSameOriginRequest(request.headers, siteOrigin)) {
    logAuthEvent("forgot", "csrf_failed");
    return NextResponse.json({ ok: false, error: NEUTRAL }, { status: 403, headers: NO_STORE });
  }

  const raw = await request.text();
  if (raw.length > 4096) return neutral();

  let email: string | null = null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      email = normalizeEmail((parsed as Record<string, unknown>).email);
    }
  } catch {
    email = null;
  }

  const ipBucket = `ip:${clientIp(request.headers)}`;
  if (await isRateLimited(ipBucket, "forgot", "forgot:ip")) {
    logAuthEvent("forgot", "rate_limited");
    return neutral();
  }
  if (email === null) {
    return neutral();
  }

  const emailBucket = await bucketFor("id", email);
  if (await isRateLimited(emailBucket, "forgot", "forgot:id")) {
    logAuthEvent("forgot", "rate_limited");
    return neutral();
  }
  const eligibility = await resetEligibility(email);
  if (!eligibility.eligible) {
    // Unknown, unverified, inactive, or legacy-without-email. Same answer.
    logAuthEvent("forgot", "unknown_identifier");
    return neutral();
  }

  const issued = await issueReset(eligibility.userId, eligibility.email, eligibility.passwordHash);
  const origin = siteOrigin || requireEnv("SITE_ORIGIN");
  const outcome = await mailTransport().send(
    passwordResetMessage(eligibility.email, resetUrl(origin, issued.token)),
  );

  // Delivery state is recorded internally and never disclosed; the response is
  // identical whether mail was sent, unavailable, or failed.
  logAuthEvent(
    "forgot",
    outcome.status === "sent" ? "success"
      : outcome.status === "failed" ? "email_send_failed" : "email_unconfigured",
  );
  return neutral();
}
