import "server-only";
import { createHash, randomBytes } from "node:crypto";

import { query, transaction } from "@/lib/db/client";

/**
 * Email-verification tokens.
 *
 * Opaque 256-bit handles, stored only as SHA-256 — the same representation
 * `auth_handoffs` and `auth_sessions` already use. The token carries no user
 * id, email, username, expiry or database id: it is a lookup key, worthless
 * without its row.
 *
 * The raw value exists only long enough to build a link and hand it to the mail
 * transport. It is never logged, never persisted, and never returned by an API.
 */

/** 24 hours. Deliberately not the handoff's 120s or the reset code's 30 minutes:
 *  a verification link is routinely opened hours later on a different device. */
export const VERIFICATION_TTL_SECONDS = Number(
  process.env.TRADELENS_VERIFICATION_TTL_SECONDS ?? 24 * 3600,
);

const SWEEP_AFTER_DAYS = 30;

function hashToken(token: string): string {
  return createHash("sha256").update(token, "utf8").digest("hex");
}

/** Build a verification URL. The only place a raw token is allowed to appear. */
export function verificationUrl(siteOrigin: string, token: string): string {
  return `${siteOrigin.replace(/\/+$/, "")}/verify-email?token=${encodeURIComponent(token)}`;
}

export type IssuedVerification = {
  /** Raw token — pass straight to the mail transport, then discard. */
  token: string;
  expiresAt: Date;
};

/**
 * Issue a token, superseding any the account already has.
 *
 * Supersession and insert happen in one transaction, so two racing resends
 * cannot both leave a live token: whichever commits second supersedes the
 * first, and the database ends with exactly one active row for the account.
 */
export async function issueVerification(
  userId: number,
  normalizedEmail: string,
  now: Date = new Date(),
): Promise<IssuedVerification> {
  const token = randomBytes(32).toString("base64url");
  const expiresAt = new Date(now.getTime() + VERIFICATION_TTL_SECONDS * 1000);

  await transaction(async (run) => {
    await run(
      `UPDATE email_verifications SET superseded_at = $2
        WHERE user_id = $1 AND consumed_at IS NULL AND superseded_at IS NULL`,
      [userId, now],
    );
    await run(
      `INSERT INTO email_verifications
         (token_hash, user_id, email, created_at, expires_at)
       VALUES ($1, $2, $3, $4, $5)`,
      [hashToken(token), userId, normalizedEmail, now, expiresAt],
    );
    return null;
  });

  // Opportunistic sweep on created_at — the reason no expires_at index exists.
  await query(
    `DELETE FROM email_verifications WHERE created_at < $1`,
    [new Date(now.getTime() - SWEEP_AFTER_DAYS * 86400_000)],
  );

  return { token, expiresAt };
}

/** Invalidate every outstanding token for an account, without issuing a new one. */
export async function supersedeAllForUser(
  userId: number,
  now: Date = new Date(),
): Promise<number> {
  const rows = await query<{ id: number }>(
    `UPDATE email_verifications SET superseded_at = $2
      WHERE user_id = $1 AND consumed_at IS NULL AND superseded_at IS NULL
      RETURNING id`,
    [userId, now],
  );
  return rows.length;
}

export type InspectionResult =
  | { status: "valid" }
  | { status: "rejected" };

/**
 * Read-only check, for rendering the confirmation page.
 *
 * **Mutates nothing.** This is what makes the flow safe against the email
 * security scanners that fetch every link in a message before the recipient
 * sees it: a scanner's GET renders a page and changes no state, so the user's
 * link still works when they actually click it.
 *
 * Invalid, expired, consumed, superseded and mismatched-email all collapse to
 * `rejected` — distinguishing them would let someone probe which tokens had
 * once existed.
 */
export async function inspectVerification(
  token: unknown,
  now: Date = new Date(),
): Promise<InspectionResult> {
  if (typeof token !== "string" || token.length === 0) {
    return { status: "rejected" };
  }
  const rows = await query<{ ok: boolean }>(
    `SELECT true AS ok
       FROM email_verifications v
       JOIN users u ON u.id = v.user_id
      WHERE v.token_hash = $1
        AND v.consumed_at IS NULL
        AND v.superseded_at IS NULL
        AND v.expires_at > $2
        AND v.email = u.email
        AND u.email_verification_required = true
        AND u.email_verified_at IS NULL`,
    [hashToken(token), now],
  );
  return rows.length === 1 ? { status: "valid" } : { status: "rejected" };
}

export type ConsumeResult =
  | { status: "verified"; userId: number }
  | { status: "rejected" };

/**
 * Consume a token and mark the address verified, atomically.
 *
 * The decision is a single conditional UPDATE. Reading the row and then marking
 * it consumed would let two concurrent confirmations both observe an unused
 * token and both proceed; `rowcount = 1` is the sole winner.
 *
 * The `v.email = u.email` condition is what stops a token outliving an address
 * change: a token issued for the old address finds no matching row once the
 * account moves to a new one, even if supersession somehow missed it. That
 * belt-and-braces is deliberate — supersession is a write that can be skipped
 * by a bug, this comparison is a condition that cannot.
 *
 * The user update runs in the same transaction, so a token is never burned
 * without the account actually becoming verified.
 */
export async function consumeVerification(
  token: unknown,
  now: Date = new Date(),
): Promise<ConsumeResult> {
  if (typeof token !== "string" || token.length === 0) {
    return { status: "rejected" };
  }
  const tokenHash = hashToken(token);

  return transaction(async (run) => {
    const claimed = await run<{ user_id: number }>(
      `UPDATE email_verifications v
          SET consumed_at = $2
         FROM users u
        WHERE v.user_id = u.id
          AND v.token_hash = $1
          AND v.consumed_at IS NULL
          AND v.superseded_at IS NULL
          AND v.expires_at > $2
          AND v.email = u.email
        RETURNING v.user_id`,
      [tokenHash, now],
    );
    if (claimed.length !== 1) return { status: "rejected" as const };

    const userId = claimed[0]!.user_id;
    await run(
      `UPDATE users
          SET email_verified_at = $2,
              email_verification_required = false
        WHERE id = $1`,
      [userId, now],
    );
    // onboarding_completed and strategy_profile_completed are deliberately
    // untouched: verifying an address is not completing onboarding, and the
    // first-run Strategy Profile step still has to happen inside Streamlit.
    return { status: "verified" as const, userId };
  });
}
