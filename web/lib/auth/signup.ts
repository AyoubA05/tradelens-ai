import "server-only";
import bcrypt from "bcryptjs";

import { transaction } from "@/lib/db/client";
import {
  NEW_ACCOUNT_DEFAULTS,
  generateInternalUsername,
} from "@/lib/auth/contract";

/**
 * Account creation.
 *
 * Two things carry most of the weight here.
 *
 * **The database is the authority on uniqueness, not the pre-check.** Looking
 * up the email first and inserting if absent is a check-then-act race: two
 * simultaneous signups for the same address both see nothing and both insert.
 * The pre-check exists only to produce a friendlier message in the common case;
 * correctness comes from the unique index on `users.email` — which production
 * was missing until the `t0u1v2w3x4y5` adoption added it, so this is a
 * guarantee that had to be created before it could be relied on.
 *
 * **The insert is the whole transaction.** Nothing partial can be left behind
 * because nothing else happens inside it. Verification-token issuance is
 * deliberately NOT here — see the note at the bottom of this file.
 */

/** bcrypt cost. Matches Python's `gensalt()` default; interop verified both ways. */
export const BCRYPT_COST = 12;

/** Postgres unique-violation. Checked by code, never by parsing the message. */
const UNIQUE_VIOLATION = "23505";

export type SignupInput = {
  email: string; // already normalized by the caller
  password: string;
  fullName: string;
  birthday: string; // ISO yyyy-mm-dd
  referralSource: string;
  referralOther: string | null;
};

export type SignupOutcome =
  | { status: "created"; userId: number }
  | { status: "duplicate_email" };

/**
 * Create an account, or report that the address is taken.
 *
 * Returns `duplicate_email` for a losing concurrent insert exactly as it does
 * for a plain duplicate, so the two are indistinguishable to the caller and
 * neither leaks timing information about which happened.
 */
export async function createAccount(
  input: SignupInput,
): Promise<SignupOutcome> {
  // Hashing is server-side and outside the transaction: bcrypt at cost 12 takes
  // a few hundred milliseconds, and holding a database transaction open for
  // that long under load is how a connection pool runs dry.
  const passwordHash = await bcrypt.hash(input.password, BCRYPT_COST);

  try {
    return await transaction(async (run) => {
      const existing = await run<{ id: number }>(
        "SELECT id FROM users WHERE email = $1",
        [input.email],
      );
      if (existing.length > 0) return { status: "duplicate_email" as const };

      // Retry only for a username collision. At 64 bits this effectively never
      // happens, but "effectively never" is not "never", and the alternative is
      // a signup that fails for a reason the user cannot act on.
      for (let attempt = 0; attempt < 5; attempt += 1) {
        const username = generateInternalUsername();
        try {
          const rows = await run<{ id: number }>(
            `INSERT INTO users (
               username, password_hash, email, created_at, is_active,
               full_name, birthday, referral_source, referral_source_other,
               onboarding_completed, strategy_profile_completed,
               email_verified_at, email_verification_required
             ) VALUES ($1, $2, $3, now(), $4, $5, $6, $7, $8, $9, $10, NULL, $11)
             RETURNING id`,
            [
              username,
              passwordHash,
              input.email,
              NEW_ACCOUNT_DEFAULTS.is_active,
              input.fullName,
              input.birthday,
              input.referralSource,
              input.referralOther,
              NEW_ACCOUNT_DEFAULTS.onboarding_completed,
              NEW_ACCOUNT_DEFAULTS.strategy_profile_completed,
              NEW_ACCOUNT_DEFAULTS.email_verification_required,
            ],
          );
          return { status: "created" as const, userId: rows[0]!.id };
        } catch (error) {
          if (isUniqueViolation(error) && !mentionsEmail(error)) continue;
          throw error;
        }
      }
      throw new Error("Could not allocate an internal username.");
    });
  } catch (error) {
    // The losing side of a concurrent insert. Reported exactly like an ordinary
    // duplicate: from outside, the two are the same event.
    if (isUniqueViolation(error)) {
      return { status: "duplicate_email" };
    }
    throw error;
  }
}

function isUniqueViolation(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    (error as { code?: string }).code === UNIQUE_VIOLATION
  );
}

function mentionsEmail(error: unknown): boolean {
  const constraint =
    typeof error === "object" && error !== null && "constraint" in error
      ? String((error as { constraint?: string }).constraint ?? "")
      : "";
  return constraint.includes("email");
}

/**
 * DEFERRED TO STEP 5 — email verification.
 *
 * No verification token is created here, and none is faked to make this step
 * look finished. `email_verified_at` is left NULL and
 * `email_verification_required` true, which is exactly the state a new account
 * should be in while waiting to verify.
 *
 * Consequence to be honest about: until step 5 ships, an account created here
 * can be created but cannot yet be verified, and therefore cannot sign in. The
 * signup response says verification is required and does NOT claim an email was
 * sent — SMTP is unconfigured, so no message exists to claim.
 */
