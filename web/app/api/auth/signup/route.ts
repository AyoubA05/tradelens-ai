import { NextResponse } from "next/server";
import { timingSafeEqual } from "node:crypto";

import { optionalEnv, requireEnv, signupMode } from "@/lib/env";
import {
  isValidBirthday,
  isValidEmail,
  isValidReferral,
  isValidReferralOther,
  isAcceptablePassword,
  normalizeEmail,
} from "@/lib/auth/contract";
import { createAccount } from "@/lib/auth/signup";
import { issueVerification, verificationUrl } from "@/lib/auth/verification";
import { verificationMessage } from "@/lib/mail/messages";
import { mailTransport } from "@/lib/mail/transport";
import {
  bucketFor,
  clientIp,
  clearFailures,
  isRateLimited,
} from "@/lib/auth/rate-limit";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { logAuthEvent, publicMessageFor } from "@/lib/security/responses";

export const runtime = "nodejs";

/** Generous for this payload, small enough that a huge body is rejected before parsing. */
const MAX_BODY_BYTES = 8 * 1024;

const MAX_LENGTHS = {
  email: 254, // RFC maximum
  password: 200, // JSON sanity bound; the contract separately enforces bcrypt's 72-byte cap
  fullName: 120,
  referralOther: 120,
  invite: 200,
} as const;

function fail(reason: Parameters<typeof publicMessageFor>[0], status: number) {
  // One shape for every failure. A caller cannot infer anything from the
  // envelope; only the message differs, and enumerable reasons share one.
  return NextResponse.json(
    { ok: false, error: publicMessageFor(reason) },
    { status },
  );
}

/** Constant-time compare so the invite code cannot be recovered by timing. */
function inviteMatches(supplied: string, expected: string): boolean {
  const a = Buffer.from(supplied);
  const b = Buffer.from(expected);
  if (a.length !== b.length) {
    // Still burn a comparison: returning early on length alone leaks it.
    timingSafeEqual(a, a);
    return false;
  }
  return timingSafeEqual(a, b);
}

export async function POST(request: Request) {
  const mode = signupMode();
  if (mode === "closed") {
    logAuthEvent("signup", "signup_closed");
    return fail("signup_closed", 403);
  }

  // --- request shape ------------------------------------------------------
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().includes("application/json")) {
    return fail("csrf_failed", 415);
  }

  const siteOrigin = optionalEnv("SITE_ORIGIN");
  if (siteOrigin && !isSameOriginRequest(request.headers, siteOrigin)) {
    logAuthEvent("signup", "csrf_failed");
    return fail("csrf_failed", 403);
  }

  const declared = Number(request.headers.get("content-length") ?? "0");
  if (declared > MAX_BODY_BYTES) return fail("csrf_failed", 413);

  const raw = await request.text();
  // Checked again after reading: content-length is client-supplied and a
  // chunked request may not send one at all.
  if (raw.length > MAX_BODY_BYTES) return fail("csrf_failed", 413);

  let body: Record<string, unknown>;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return fail("csrf_failed", 400);
    }
    body = parsed as Record<string, unknown>;
  } catch {
    return fail("csrf_failed", 400);
  }

  // --- rate limiting ------------------------------------------------------
  const ip = clientIp(request.headers);
  const ipBucket = `ip:${ip}`;
  if (await isRateLimited(ipBucket, "signup", "signup:ip")) {
    logAuthEvent("signup", "rate_limited", { ip_bucket: ipBucket });
    return fail("rate_limited", 429);
  }

  // --- field validation ---------------------------------------------------
  const emailRaw = body.email;
  if (typeof emailRaw !== "string" || emailRaw.length > MAX_LENGTHS.email) {
    return fail("csrf_failed", 400);
  }
  const email = normalizeEmail(emailRaw);
  if (email === null || !isValidEmail(email)) {
    return fail("csrf_failed", 400);
  }

  const emailBucket = await bucketFor("id", email);
  if (await isRateLimited(emailBucket, "signup", "signup:id")) {
    logAuthEvent("signup", "rate_limited");
    return fail("rate_limited", 429);
  }

  const password = body.password;
  if (typeof password !== "string" || password.length > MAX_LENGTHS.password) {
    return fail("csrf_failed", 400);
  }
  // Same policy the strength meter shows. The meter is UX; this is the control.
  if (!isAcceptablePassword(password)) {
    return fail("weak_password", 400);
  }

  const fullName = typeof body.fullName === "string" ? body.fullName.trim() : "";
  if (fullName.length < 1 || fullName.length > MAX_LENGTHS.fullName) {
    return fail("csrf_failed", 400);
  }

  const birthday = body.birthday;
  if (!isValidBirthday(birthday)) {
    return fail("csrf_failed", 400);
  }

  const referralSource = body.referralSource;
  if (!isValidReferral(referralSource)) {
    return fail("csrf_failed", 400);
  }

  const referralOther = body.referralOther ?? null;
  if (!isValidReferralOther(referralSource, referralOther)) {
    return fail("csrf_failed", 400);
  }

  // --- invite gating ------------------------------------------------------
  if (mode === "invite") {
    if (await isRateLimited(ipBucket, "invite", "invite:ip")) {
      logAuthEvent("signup", "rate_limited");
      return fail("rate_limited", 429);
    }
    const configured = requireEnv("TRADELENS_INVITE_CODE");
    const supplied = typeof body.invite === "string" ? body.invite : "";
    if (
      supplied.length > MAX_LENGTHS.invite ||
      !inviteMatches(supplied, configured)
    ) {
      logAuthEvent("signup", "invalid_invite", { ip_bucket: ipBucket });
      return fail("invalid_invite", 403);
    }
    await clearFailures(ipBucket, "invite");
  }

  // --- create -------------------------------------------------------------
  let outcome;
  try {
    outcome = await createAccount({
      email,
      password,
      fullName,
      birthday: birthday as string,
      referralSource,
      referralOther:
        typeof referralOther === "string" && referralOther.length > 0
          ? referralOther
          : null,
    });
  } catch {
    // Nothing from the driver reaches the client: a Postgres error routinely
    // carries the DSN, the host, and the failing statement.
    logAuthEvent("signup", "invalid_token", { stage: "create" });
    return NextResponse.json(
      { ok: false, error: "Something went wrong. Please try again." },
      { status: 500 },
    );
  }

  if (outcome.status === "duplicate_email") {
    // Says an account exists, but nothing about whether it is legacy, verified,
    // or unverified — those distinctions are what an attacker would want.
    logAuthEvent("signup", "duplicate_email");
    return fail("duplicate_email", 409);
  }

  await clearFailures(emailBucket, "signup");
  // No user id, username, or email in the log line.
  logAuthEvent("signup", "success");

  // --- verification -------------------------------------------------------
  //
  // Failure model, chosen deliberately: the account is NOT rolled back if the
  // token cannot be issued or the mail cannot be delivered.
  //
  // Rolling back would destroy a valid account — correct email, correct
  // password, correct profile — because of an outage in a system that has
  // nothing to do with whether the account is valid. The user would see
  // "something went wrong", retry, and hit "an account already exists" if the
  // rollback itself half-failed. Leaving the account in its unverified state is
  // both recoverable and exactly the state it is supposed to be in: it cannot
  // sign in, and /resend-verification will mint a fresh token whenever mail
  // works again.
  let delivery: "sent" | "unavailable" | "failed" | "token_failed" = "failed";
  try {
    const issued = await issueVerification(outcome.userId, email);
    const origin = siteOrigin || optionalEnv("SITE_ORIGIN");
    const result = await mailTransport().send(
      verificationMessage(email, verificationUrl(origin, issued.token)),
    );
    delivery = result.status === "unavailable" ? "unavailable" : result.status;
  } catch {
    // Token issuance itself failed. The account still exists and is still
    // recoverable through resend; nothing is left half-written, because
    // issueVerification is transactional.
    delivery = "token_failed";
    logAuthEvent("signup", "email_send_failed", { stage: "issue_token" });
  }

  return NextResponse.json(
    {
      ok: true,
      verificationRequired: true,
      // Reported honestly, and with the three states kept apart. "sent" only
      // when a transport actually accepted the message; "unavailable" when no
      // transport is configured and nothing was attempted; "failed" when one
      // was configured and did not deliver. Collapsing the last two would tell
      // a user that a transient outage is a missing configuration — and would
      // let a broken SMTP server look like a deliberate beta limitation.
      emailDelivery:
        delivery === "sent"
          ? "sent"
          : delivery === "unavailable"
            ? "unavailable"
            : "failed",
      message:
        delivery === "sent"
          ? "Account created. Check your email for the verification link."
          : delivery === "unavailable"
            ? "Account created. Email verification is required before you can sign in, and email delivery is not configured in this environment."
            : "Account created, but we could not send the verification email. Try resending it in a moment.",
    },
    { status: 201 },
  );
}
