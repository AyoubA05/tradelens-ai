import "server-only";
import bcrypt from "bcryptjs";
import { createHash, randomBytes } from "node:crypto";

import { query, transaction } from "@/lib/db/client";

/**
 * Password-reset tokens.
 *
 * Opaque 256-bit handles, SHA-256 at rest, 30-minute TTL. Deliberately not the
 * verification token's 24 hours: a verification link is opened at leisure, a
 * reset link is an active key to an account.
 *
 * Consume requires **eight** live conditions, not just a matching hash. Each one
 * closes a way an old link could otherwise still work:
 *
 *   token_hash matches            the token is real
 *   expires_at > now              not stale
 *   consumed_at IS NULL           not already used
 *   superseded_at IS NULL         not replaced by a newer request
 *   user still exists             account not deleted
 *   row email = user's email      not mailed to a since-changed address
 *   email still verified          verification not revoked in the meantime
 *   fingerprint still matches     password unchanged since issuance
 *
 * The last is the one worth explaining. The design this replaces signed each
 * code with a key derived from the current password hash, so *any* password
 * change invalidated every outstanding code for free. A token table loses that
 * unless something replaces it — otherwise a user who requests a reset, then
 * remembers their password and changes it elsewhere, leaves a live link behind.
 * Comparing the fingerprint makes it a condition nobody can forget, rather than
 * a supersede-write every future password-change path must remember to perform.
 */

export const RESET_TTL_SECONDS = 30 * 60;
const SWEEP_AFTER_DAYS = 30;

function sha256(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

/**
 * Canonical fingerprint: SHA-256 hex of the exact `password_hash` string,
 * UTF-8 encoded, lowercase hex. Defined in one place so Python and TypeScript
 * cannot disagree; pinned by the shared contract vectors.
 *
 * Stores a hash *of* a hash. Neither the password nor the bcrypt hash is ever
 * copied into `password_resets`.
 */
export function passwordHashFingerprint(passwordHash: string): string {
  return sha256(passwordHash);
}

export function resetUrl(siteOrigin: string, token: string): string {
  return `${siteOrigin.replace(/\/+$/, "")}/reset-password?token=${encodeURIComponent(token)}`;
}

export type ResetEligibility =
  | { eligible: true; userId: number; email: string; passwordHash: string }
  | { eligible: false };

/**
 * Whether this address may receive a reset link.
 *
 * Only a verified address is eligible. A legacy username-only account is a
 * perfectly valid account — it simply has no address to send to, and cannot
 * use email reset until it attaches and verifies one. The caller must return
 * the same neutral response either way.
 */
export async function resetEligibility(
  normalizedEmail: string,
): Promise<ResetEligibility> {
  const rows = await query<{ id: number; email: string; password_hash: string }>(
    `SELECT id, email, password_hash
       FROM users
      WHERE email = $1
        AND is_active = 1
        AND email_verified_at IS NOT NULL
        AND email_verification_required = false`,
    [normalizedEmail],
  );
  const row = rows[0];
  return row
    ? { eligible: true, userId: row.id, email: row.email, passwordHash: row.password_hash }
    : { eligible: false };
}

/**
 * Issue a reset token, superseding any outstanding ones.
 *
 * Supersede and insert share one transaction, so racing forgot-password
 * requests leave a deterministic state: whichever commits second supersedes the
 * first, and exactly one active token remains.
 */
export async function issueReset(
  userId: number,
  normalizedEmail: string,
  passwordHash: string,
  now: Date = new Date(),
): Promise<{ token: string; expiresAt: Date }> {
  const token = randomBytes(32).toString("base64url");
  const expiresAt = new Date(now.getTime() + RESET_TTL_SECONDS * 1000);

  await transaction(async (run) => {
    await run(
      `UPDATE password_resets SET superseded_at = $2
        WHERE user_id = $1 AND consumed_at IS NULL AND superseded_at IS NULL`,
      [userId, now],
    );
    await run(
      `INSERT INTO password_resets
         (token_hash, user_id, email, password_hash_fingerprint, created_at, expires_at)
       VALUES ($1, $2, $3, $4, $5, $6)`,
      [sha256(token), userId, normalizedEmail, passwordHashFingerprint(passwordHash), now, expiresAt],
    );
    return null;
  });

  await query(`DELETE FROM password_resets WHERE created_at < $1`, [
    new Date(now.getTime() - SWEEP_AFTER_DAYS * 86400_000),
  ]);

  return { token, expiresAt };
}

/**
 * Read-only check, for rendering the reset form.
 *
 * **Mutates nothing** — no consume, no supersede. Mail security scanners fetch
 * every link in a message before the recipient sees it; a consuming GET would
 * burn the token before the user ever clicked, producing an outage that looks
 * exactly like a token bug.
 *
 * Every rejection reason collapses to one answer so a caller cannot probe which
 * tokens once existed.
 *
 * The fingerprint comparison is done in TypeScript rather than SQL, because
 * `digest()` needs the pgcrypto extension and depending on it here would make
 * the reset flow fail on a database that has not enabled it.
 */
export async function inspectReset(
  token: unknown,
  now: Date = new Date(),
): Promise<{ status: "valid" } | { status: "rejected" }> {
  if (typeof token !== "string" || token.length === 0) return { status: "rejected" };
  const rows = await query<{ fingerprint: string; current_hash: string }>(
    `SELECT r.password_hash_fingerprint AS fingerprint, u.password_hash AS current_hash
       FROM password_resets r
       JOIN users u ON u.id = r.user_id
      WHERE r.token_hash = $1
        AND r.consumed_at IS NULL
        AND r.superseded_at IS NULL
        AND r.expires_at > $2
        AND r.email = u.email
        AND u.email_verified_at IS NOT NULL
        AND u.email_verification_required = false
        AND u.is_active = 1`,
    [sha256(token), now],
  );
  const row = rows[0];
  if (!row) return { status: "rejected" };
  return row.fingerprint === passwordHashFingerprint(row.current_hash)
    ? { status: "valid" }
    : { status: "rejected" };
}

export type ResetOutcome =
  | { status: "reset"; userId: number; sessionsRevoked: number; handoffsVoided: number }
  | { status: "rejected" };

/**
 * Complete a reset: change the password, burn the token, and end every session.
 *
 * The bcrypt hash is computed by the caller *before* this runs, so a ~250ms
 * hashing cost never holds a database transaction open.
 *
 * Everything else happens in one transaction, so the user can never end up with
 * a consumed token and an unchanged password, or a changed password and a
 * reusable token.
 *
 * Session revocation is a security boundary, not UX: a password is reset
 * precisely when the old one may be compromised, and leaving sessions opened
 * with it alive would defeat the point.
 *
 * Outstanding handoffs are voided for the same reason. A handoff issued seconds
 * before the reset would otherwise still be redeemable inside its 120-second
 * window and would mint a *fresh* Streamlit session after the password changed.
 */
export async function completeReset(
  token: unknown,
  newPasswordHash: string,
  now: Date = new Date(),
): Promise<ResetOutcome> {
  if (typeof token !== "string" || token.length === 0) return { status: "rejected" };
  const tokenHash = sha256(token);

  return transaction(async (run) => {
    // Claim first, conditionally. A read-then-write would let two concurrent
    // confirmations both observe an unused token and both proceed.
    const candidate = await run<{
      id: number;
      user_id: number;
      fingerprint: string;
      current_hash: string;
    }>(
      `SELECT r.id, r.user_id,
              r.password_hash_fingerprint AS fingerprint,
              u.password_hash AS current_hash
         FROM password_resets r
         JOIN users u ON u.id = r.user_id
        WHERE r.token_hash = $1
          AND r.consumed_at IS NULL
          AND r.superseded_at IS NULL
          AND r.expires_at > $2
          AND r.email = u.email
          AND u.email_verified_at IS NOT NULL
          AND u.email_verification_required = false
          AND u.is_active = 1
        FOR UPDATE OF r`,
      [tokenHash, now],
    );
    const row = candidate[0];
    if (!row) return { status: "rejected" as const };

    // The password must not have changed since the token was issued.
    if (row.fingerprint !== passwordHashFingerprint(row.current_hash)) {
      return { status: "rejected" as const };
    }

    const claimed = await run<{ id: number }>(
      `UPDATE password_resets SET consumed_at = $2
        WHERE id = $1 AND consumed_at IS NULL AND superseded_at IS NULL
        RETURNING id`,
      [row.id, now],
    );
    if (claimed.length !== 1) return { status: "rejected" as const };

    await run(`UPDATE users SET password_hash = $2 WHERE id = $1`, [
      row.user_id,
      newPasswordHash,
    ]);

    // Any other live reset token for this account dies with the same event.
    await run(
      `UPDATE password_resets SET superseded_at = $2
        WHERE user_id = $1 AND id <> $3
          AND consumed_at IS NULL AND superseded_at IS NULL`,
      [row.user_id, now, row.id],
    );

    const sessions = await run<{ id: number }>(
      `UPDATE auth_sessions SET revoked_at = $2
        WHERE user_id = $1 AND revoked_at IS NULL
        RETURNING id`,
      [row.user_id, now],
    );

    // auth_handoffs has no revoked_at; marking consumed_at makes them
    // unredeemable, since redeem_handoff requires consumed_at IS NULL. This
    // conflates "the user redeemed it" with "a reset voided it" — acceptable
    // for a 120-second row, and noted as a small future schema tidy-up.
    const handoffs = await run<{ id: number }>(
      `UPDATE auth_handoffs SET consumed_at = $2
        WHERE user_id = $1 AND consumed_at IS NULL
        RETURNING id`,
      [row.user_id, now],
    );

    return {
      status: "reset" as const,
      userId: row.user_id,
      sessionsRevoked: sessions.length,
      handoffsVoided: handoffs.length,
    };
  });
}

/** bcrypt cost 12, matching signup and the Python side. */
export async function hashNewPassword(password: string): Promise<string> {
  return bcrypt.hash(password, 12);
}
