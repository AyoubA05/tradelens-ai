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
import {
  bucketFor,
  clientIp,
  isRateLimited,
  recordAttempt,
} from "@/lib/auth/rate-limit";
import { isSameOriginRequest } from "@/lib/security/redirect";
import { logAuthEvent, publicMessageFor } from "@/lib/security/responses";

export const runtime = "nodejs";

/** Generous for this payload, small enough that a huge body is rejected before parsing. */
const MAX_BODY_BYTES = 8 * 1024;

const MAX_LENGTHS = {
  email: 254, // RFC maximum
  password: 200, // bcrypt truncates at 72 bytes; this is only a sanity bound
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
    await recordAttempt(ipBucket, "signup", false);
    return fail("csrf_failed", 400);
  }
  const email = normalizeEmail(emailRaw);
  if (email === null || !isValidEmail(email)) {
    await recordAttempt(ipBucket, "signup", false);
    return fail("csrf_failed", 400);
  }

  const emailBucket = await bucketFor("id", email);
  if (await isRateLimited(emailBucket, "signup", "signup:id")) {
    logAuthEvent("signup", "rate_limited");
    return fail("rate_limited", 429);
  }

  const password = body.password;
  if (typeof password !== "string" || password.length > MAX_LENGTHS.password) {
    await recordAttempt(ipBucket, "signup", false);
    return fail("csrf_failed", 400);
  }
  // Same policy the strength meter shows. The meter is UX; this is the control.
  if (!isAcceptablePassword(password)) {
    await recordAttempt(ipBucket, "signup", false);
    await recordAttempt(emailBucket, "signup", false);
    return fail("weak_password", 400);
  }

  const fullName = typeof body.fullName === "string" ? body.fullName.trim() : "";
  if (fullName.length < 1 || fullName.length > MAX_LENGTHS.fullName) {
    await recordAttempt(ipBucket, "signup", false);
    return fail("csrf_failed", 400);
  }

  const birthday = body.birthday;
  if (!isValidBirthday(birthday)) {
    await recordAttempt(ipBucket, "signup", false);
    return fail("csrf_failed", 400);
  }

  const referralSource = body.referralSource;
  if (!isValidReferral(referralSource)) {
    await recordAttempt(ipBucket, "signup", false);
    return fail("csrf_failed", 400);
  }

  const referralOther = body.referralOther ?? null;
  if (!isValidReferralOther(referralSource, referralOther)) {
    await recordAttempt(ipBucket, "signup", false);
    return fail("csrf_failed", 400);
  }

  // --- invite gating ------------------------------------------------------
  if (mode === "invite") {
    const configured = requireEnv("TRADELENS_INVITE_CODE");
    const supplied = typeof body.invite === "string" ? body.invite : "";
    if (
      supplied.length > MAX_LENGTHS.invite ||
      !inviteMatches(supplied, configured)
    ) {
      await recordAttempt(ipBucket, "invite", false);
      logAuthEvent("signup", "invalid_invite", { ip_bucket: ipBucket });
      return fail("invalid_invite", 403);
    }
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
    await recordAttempt(ipBucket, "signup", false);
    await recordAttempt(emailBucket, "signup", false);
    // Says an account exists, but nothing about whether it is legacy, verified,
    // or unverified — those distinctions are what an attacker would want.
    logAuthEvent("signup", "duplicate_email");
    return fail("duplicate_email", 409);
  }

  await recordAttempt(ipBucket, "signup", true);
  // No user id, username, or email in the log line.
  logAuthEvent("signup", "success");

  // DEFERRED TO STEP 5: no verification email is sent, and none is claimed.
  // SMTP is unconfigured, so saying "check your inbox" would be false.
  return NextResponse.json(
    {
      ok: true,
      verificationRequired: true,
      emailDelivery: "pending_configuration",
      message:
        "Account created. Email verification is required before you can sign in.",
    },
    { status: 201 },
  );
}
