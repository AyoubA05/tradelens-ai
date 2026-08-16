import "server-only";
import { createHash } from "node:crypto";

import { query } from "@/lib/db/client";
import { SESSION_COOKIE } from "@/lib/auth/login";
import { WEBSITE_DOMAIN } from "@/lib/auth/domains";

/**
 * The single gate every protected website route goes through.
 *
 * It exists so route handlers cannot each invent their own idea of "logged in".
 * Four of the five conditions below are the kind that get forgotten one at a
 * time — a route that checks the cookie resolves but forgets `revoked_at`, or
 * checks expiry but not whether the account is still active — and each omission
 * is silently exploitable rather than visibly broken.
 *
 * A session is valid only when all of:
 *
 *   the SHA-256 of the cookie matches a row      the credential is real
 *   revoked_at IS NULL                           not signed out or reset-revoked
 *   expires_at > now                             inside the 12h absolute cap
 *   now - last_seen_at < 8h                      inside the idle window
 *   user is_active = 1                           account not disabled
 *
 * **The identity comes from the session row and nowhere else.** No route may
 * accept a user id, username, or email from the browser as an authority for
 * which account to act on; doing so is how one authenticated user ends up
 * editing another's account.
 */

const IDLE_TIMEOUT_S = 8 * 3600;

export type WebsiteUser = {
  userId: number;
  email: string | null;
  emailVerifiedAt: Date | null;
  emailVerificationRequired: boolean;
  onboardingCompleted: boolean;
  strategyProfileCompleted: boolean;
};

/** Parse the session credential without letting malformed percent escapes throw. */
export function sessionTokenFromCookieHeader(raw: string | null): string | null {
  if (!raw) return null;
  const match = raw.match(new RegExp(`(?:^|;\\s*)${SESSION_COOKIE}=([^;]+)`));
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]!);
  } catch {
    return null;
  }
}

/** Read the session cookie off a request. */
export function sessionTokenFrom(request: Request): string | null {
  return sessionTokenFromCookieHeader(request.headers.get("cookie"));
}

/**
 * Resolve a session credential to its user, or null.
 *
 * Slides `last_seen_at` on success. **`expires_at` is never touched** — that is
 * what keeps the 12-hour cap absolute rather than something activity can push
 * indefinitely, and it is the reason the idle and absolute bounds are two
 * separate columns instead of one.
 */
export async function authenticateWebsiteRequest(
  request: Request,
  now: Date = new Date(),
): Promise<WebsiteUser | null> {
  const token = sessionTokenFrom(request);
  if (!token) return null;
  return authenticateSessionToken(token, now);
}

export async function authenticateSessionToken(
  token: unknown,
  now: Date = new Date(),
): Promise<WebsiteUser | null> {
  if (typeof token !== "string" || token.length === 0) return null;
  // Website domain. A Streamlit token hashes to something this lookup cannot
  // find, so pasting one into the tl_session cookie fails by construction.
  const tokenHash = createHash("sha256").update(WEBSITE_DOMAIN + token, "utf8").digest("hex");

  const rows = await query<{
    user_id: number;
    email: string | null;
    email_verified_at: Date | null;
    email_verification_required: boolean;
    onboarding_completed: boolean;
    strategy_profile_completed: boolean;
  }>(
    `UPDATE auth_sessions s
        SET last_seen_at = $2
       FROM users u
      WHERE s.user_id = u.id
        AND s.token_hash = $1
        AND s.surface = 'website'
        AND s.revoked_at IS NULL
        AND s.expires_at > $2
        AND s.last_seen_at > $2 - make_interval(secs => $3)
        AND u.is_active = 1
      RETURNING u.id AS user_id, u.email, u.email_verified_at,
                u.email_verification_required, u.onboarding_completed,
                u.strategy_profile_completed`,
    [tokenHash, now, IDLE_TIMEOUT_S],
  );

  const row = rows[0];
  if (!row) return null;
  return {
    userId: row.user_id,
    email: row.email,
    emailVerifiedAt: row.email_verified_at,
    emailVerificationRequired: row.email_verification_required,
    onboardingCompleted: row.onboarding_completed,
    strategyProfileCompleted: row.strategy_profile_completed,
  };
}

/**
 * Whether the account has cleared the email gate.
 *
 * Legacy accounts carry `email_verification_required = false` and pass. New
 * accounts must have verified. This is the same rule login enforces, applied
 * again here — a session could in principle outlive a change to the account's
 * verification state, and a hand-crafted request must not slip past a gate the
 * login form happened to apply earlier.
 */
export function emailGatePassed(user: WebsiteUser): boolean {
  return !(user.emailVerificationRequired && user.emailVerifiedAt === null);
}

/**
 * Where an authenticated user belongs right now.
 *
 * One function so login, onboarding, and the continuation page cannot disagree
 * about it. `/continue` is a placeholder that says so on the page; step 9
 * replaces it with the real handoff.
 */
export function nextDestinationFor(user: WebsiteUser): string {
  if (!emailGatePassed(user)) return "/verify-email";
  if (!user.onboardingCompleted) return "/onboarding";
  return "/continue";
}
