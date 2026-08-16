import "server-only";
import bcrypt from "bcryptjs";
import { createHash, randomBytes } from "node:crypto";

import { query } from "@/lib/db/client";
import { normalizeEmail } from "@/lib/auth/contract";
import { SURFACE_WEBSITE, WEBSITE_DOMAIN } from "@/lib/auth/domains";

/**
 * Credential verification and the website session.
 *
 * Two things here are worth reading before changing anything.
 *
 * **Identity resolution has no fallthrough.** An identifier containing `@`
 * resolves by email *only*; anything else resolves by username *only*, exactly
 * and case-sensitively. `ayoub` and `Ayoub` are two real, separate accounts in
 * production, and case-folding would silently merge two people's journals. The
 * rule is total because usernames are constrained to `[a-zA-Z0-9_]` and can
 * never contain `@`.
 *
 * **The website session is a real cookie session**, unlike the Streamlit one.
 * Streamlit Community Cloud offers no server-side cookie write, which is why
 * its session credential rides in a URL. Next.js has no such limitation, so
 * here the token is `HttpOnly`, `Secure`, `SameSite=Lax` and never appears in
 * an address bar. It reuses the `auth_sessions` table — same concept, same
 * revocability, same 8h idle / 12h absolute bounds — rather than introducing a
 * second session store that would need its own expiry and revocation logic.
 *
 * Consequence, stated deliberately: each browser surface has its own session
 * row. A normal sign-out revokes the credential used on that surface; password
 * reset and the explicit all-sessions operation revoke every surface. Do not
 * describe website sign-out as ending a separate Streamlit session unless the
 * implementation is changed to revoke all rows for the user.
 */

const IDLE_TIMEOUT_S = 8 * 3600;
const ABSOLUTE_TIMEOUT_S = 12 * 3600;

export const SESSION_COOKIE = "tl_session";

/**
 * A real bcrypt hash of a value nobody knows, compared against when no account
 * matches. Without it, an unknown identifier returns in microseconds while a
 * known one takes the ~250ms bcrypt costs, and the difference is a reliable
 * account-existence oracle regardless of how careful the response body is.
 */
const TIMING_DECOY_HASH =
  "$2b$12$C6UzMDM.H6dfI/f/IKcEe.6PtGDR8CVQrJyGnQqYRHXrCBvJKvVfC";

type UserRow = {
  id: number;
  username: string;
  email: string | null;
  password_hash: string;
  is_active: number;
  email_verified_at: Date | null;
  email_verification_required: boolean;
  onboarding_completed: boolean;
  strategy_profile_completed: boolean;
};

export type LoginFailure =
  | "bad_credentials"
  | "inactive"
  | "email_unverified";

export type LoginResult =
  | {
      ok: true;
      userId: number;
      /** Drives state-based routing after login. */
      onboardingCompleted: boolean;
      /** Drives where Streamlit sends them after the handoff, in a later step. */
      strategyProfileCompleted: boolean;
    }
  | { ok: false; reason: LoginFailure };

async function findByIdentifier(identifier: string): Promise<UserRow | null> {
  const trimmed = identifier.trim();
  if (trimmed.length === 0) return null;

  if (trimmed.includes("@")) {
    const email = normalizeEmail(trimmed);
    if (email === null) return null;
    const rows = await query<UserRow>(
      `SELECT id, username, email, password_hash, is_active, email_verified_at,
              email_verification_required, onboarding_completed,
              strategy_profile_completed
         FROM users WHERE email = $1`,
      [email],
    );
    // No fallthrough to a username lookup. A failed email lookup fails.
    return rows[0] ?? null;
  }

  // Exact and case-sensitive. `=` in Postgres on a text column is exactly that.
  const rows = await query<UserRow>(
    `SELECT id, username, email, password_hash, is_active, email_verified_at,
            email_verification_required, onboarding_completed,
            strategy_profile_completed
       FROM users WHERE username = $1`,
    [trimmed],
  );
  return rows[0] ?? null;
}

/**
 * Verify credentials.
 *
 * bcrypt runs on every path, including the unknown-account path, so the
 * response time carries no information about whether an account exists.
 */
export async function attemptLogin(
  identifier: unknown,
  password: unknown,
): Promise<LoginResult> {
  const id = typeof identifier === "string" ? identifier : "";
  const pw = typeof password === "string" ? password : "";

  const user = await findByIdentifier(id);

  if (user === null) {
    await bcrypt.compare(pw, TIMING_DECOY_HASH);
    return { ok: false, reason: "bad_credentials" };
  }

  let matches = false;
  try {
    matches = await bcrypt.compare(pw, user.password_hash);
  } catch {
    matches = false;
  }
  if (!matches) return { ok: false, reason: "bad_credentials" };

  if (!user.is_active) return { ok: false, reason: "inactive" };

  // Only reachable once the password is already correct. Telling an unverified
  // user to check their email does reveal the account exists — but whoever
  // supplied the right password knew that already, so nothing is disclosed that
  // the caller did not have. Before the password check this message would be a
  // genuine enumeration oracle; after it, it is just useful.
  //
  // Legacy accounts carry email_verification_required = false and pass
  // straight through, which is the whole point of the s9 backfill.
  if (user.email_verification_required && user.email_verified_at === null) {
    return { ok: false, reason: "email_unverified" };
  }

  return {
    ok: true,
    userId: user.id,
    onboardingCompleted: user.onboarding_completed,
    strategyProfileCompleted: user.strategy_profile_completed,
  };
}

/**
 * Open a website session. Returns the raw token for the cookie; only its hash
 * is stored. `expires_at` is written once and updated by nothing, which is what
 * makes the 12-hour cap absolute rather than nominal.
 */
/** SHA-256 hex of the website domain prefix plus the token, UTF-8. */
function websiteHash(token: string): string {
  return createHash("sha256").update(WEBSITE_DOMAIN + token, "utf8").digest("hex");
}

export async function openWebsiteSession(
  userId: number,
  now: Date = new Date(),
): Promise<{ token: string; expiresAt: Date }> {
  const token = randomBytes(32).toString("base64url");
  const expiresAt = new Date(now.getTime() + ABSOLUTE_TIMEOUT_S * 1000);
  await query(
    `INSERT INTO auth_sessions
       (token_hash, user_id, created_at, expires_at, last_seen_at, surface)
     VALUES ($1, $2, $3, $4, $3, $5)`,
    // surface is passed explicitly; the column has no default, so forgetting it
    // is a NOT NULL violation rather than a silent website-domain row.
    [websiteHash(token), userId, now, expiresAt, SURFACE_WEBSITE],
  );
  return { token, expiresAt };
}

/** Resolve a cookie to a user, sliding the idle window. Fails closed. */
export async function resolveWebsiteSession(
  token: unknown,
  now: Date = new Date(),
): Promise<number | null> {
  if (typeof token !== "string" || token.length === 0) return null;
  const tokenHash = websiteHash(token);
  const rows = await query<{ user_id: number }>(
    `UPDATE auth_sessions SET last_seen_at = $2
      WHERE token_hash = $1
        AND surface = 'website'
        AND revoked_at IS NULL
        AND expires_at > $2
        AND last_seen_at > $2 - make_interval(secs => $3)
      RETURNING user_id`,
    [tokenHash, now, IDLE_TIMEOUT_S],
  );
  return rows[0]?.user_id ?? null;
}

/** Revoke a session. This is what makes sign-out mean something. */
export async function revokeWebsiteSession(
  token: unknown,
  now: Date = new Date(),
): Promise<boolean> {
  if (typeof token !== "string" || token.length === 0) return false;
  const rows = await query<{ id: number }>(
    `UPDATE auth_sessions SET revoked_at = $2
      WHERE token_hash = $1 AND surface = 'website' AND revoked_at IS NULL
      RETURNING id`,
    [websiteHash(token), now],
  );
  return rows.length === 1;
}

/** Cookie attributes. Secure is dropped only on plain-HTTP local development. */
export function sessionCookieOptions(expiresAt: Date, secure: boolean) {
  return {
    httpOnly: true,
    secure,
    sameSite: "lax" as const,
    path: "/",
    expires: expiresAt,
  };
}
