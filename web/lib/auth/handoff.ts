import "server-only";
import { createHash, randomBytes } from "node:crypto";

import { transaction } from "@/lib/db/client";
import type { WebsiteUser } from "@/lib/auth/session";
import { emailGatePassed } from "@/lib/auth/session";

/**
 * Website → Streamlit handoff, issuer side.
 *
 * **Three credentials, three lifetimes, never interchanged:**
 *
 *   website session   HttpOnly cookie, 8h idle / 12h absolute, revocable
 *   handoff           this module — 120 seconds, one-time, travels in a URL
 *   Streamlit session created by Streamlit after redeeming — step 10
 *
 * The tempting shortcut is to put the website cookie value in the redirect,
 * since both are already `auth_sessions`-shaped credentials for the same user.
 * That would work perfectly and would place a 12-hour `HttpOnly` credential
 * into an address bar, browser history, and any proxy log on the path —
 * destroying the exact protection the cookie exists to provide. Nothing here
 * reads the cookie value; it takes an already-validated `WebsiteUser`.
 *
 * The token is 32 random bytes. It encodes no user id, username, email,
 * expiry, session id, or account flag — it is a lookup key, worthless without
 * its row. Only `sha256(token)` is stored; the raw value exists just long
 * enough to build one redirect.
 *
 * TTL and hash representation match `services/auth_handoff.py` exactly, because
 * Python is what will redeem this.
 */

/** Matches HANDOFF_TTL_S in services/auth_handoff.py. */
export const HANDOFF_TTL_SECONDS = 120;

const SWEEP_AFTER_DAYS = 30;

function hashToken(token: string): string {
  return createHash("sha256").update(token, "utf8").digest("hex");
}

export type HandoffRefusal =
  | "no_session"
  | "email_unverified"
  | "onboarding_incomplete";

export type HandoffEligibility =
  | { eligible: true }
  | { eligible: false; reason: HandoffRefusal };

/**
 * Whether this user may cross into Streamlit.
 *
 * Note what is deliberately **not** required: `strategy_profile_completed`. A
 * brand-new user is *expected* to arrive with it false — that false is the
 * signal Streamlit uses to route them into the first-run Strategy Profile.
 * Requiring it here would make it impossible to ever reach the screen that sets
 * it.
 *
 * The session helper has already enforced revoked / idle / absolute / active,
 * so a caller holding a `WebsiteUser` has cleared those four.
 */
export function handoffEligibility(user: WebsiteUser | null): HandoffEligibility {
  if (!user) return { eligible: false, reason: "no_session" };
  // Legacy accounts pass on the exemption, exactly as they do at login.
  if (!emailGatePassed(user)) return { eligible: false, reason: "email_unverified" };
  if (!user.onboardingCompleted) {
    return { eligible: false, reason: "onboarding_incomplete" };
  }
  return { eligible: true };
}

/**
 * Mint a handoff for an already-authenticated user.
 *
 * Takes a `userId`, never a cookie: this function cannot be handed a session
 * credential even by mistake.
 *
 * **One redeemable handoff per user.** Issuing invalidates any outstanding one
 * and inserts the replacement in a single transaction, serialised by a row lock
 * on the user. Without the lock, two concurrent issues would each invalidate
 * what they saw and then insert, leaving two live tokens — the invalidate/insert
 * pair being transactional is not by itself enough, because both transactions
 * read a state that the other is about to change.
 *
 * Invalidation writes `consumed_at`, which the schema also uses for genuine
 * redemption. The audit ambiguity is known and recorded; the security property
 * holds either way, since `redeem_handoff` requires `consumed_at IS NULL`.
 */
export async function issueHandoff(
  userId: number,
  now: Date = new Date(),
): Promise<{ token: string; expiresAt: Date; invalidated: number }> {
  const token = randomBytes(32).toString("base64url");
  const expiresAt = new Date(now.getTime() + HANDOFF_TTL_SECONDS * 1000);

  const invalidated = await transaction(async (run) => {
    // Serialises concurrent issuance for this user. Everything below runs
    // against a state no other issuer can be modifying.
    await run(`SELECT id FROM users WHERE id = $1 FOR UPDATE`, [userId]);

    const voided = await run<{ id: number }>(
      `UPDATE auth_handoffs SET consumed_at = $2
        WHERE user_id = $1 AND consumed_at IS NULL
        RETURNING id`,
      [userId, now],
    );

    await run(
      `INSERT INTO auth_handoffs (token_hash, user_id, created_at, expires_at)
       VALUES ($1, $2, $3, $4)`,
      [hashToken(token), userId, now, expiresAt],
    );

    // Opportunistic sweep, inside the same lock so it cannot race an insert.
    await run(`DELETE FROM auth_handoffs WHERE created_at < $1`, [
      new Date(now.getTime() - SWEEP_AFTER_DAYS * 86400_000),
    ]);

    return voided.length;
  });

  return { token, expiresAt, invalidated };
}
