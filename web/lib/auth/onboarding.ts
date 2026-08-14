import "server-only";

import { query } from "@/lib/db/client";
import {
  REFERRAL_OTHER_MAX,
  isValidBirthday,
  isValidReferral,
  isValidReferralOther,
} from "@/lib/auth/contract";

/**
 * Personal onboarding — the website's half.
 *
 * Deliberately narrow: full name, birthday, referral. **No trading-strategy
 * fields.** The Strategy Profile belongs to Streamlit and is gated on
 * `strategy_profile_completed`, which this module never sets — a brand-new user
 * finishes here with `onboarding_completed = true` and
 * `strategy_profile_completed = false`, and that false is precisely what makes
 * Streamlit require the first-run Strategy Profile.
 */

export const FULL_NAME_MIN = 1;
export const FULL_NAME_MAX = 120;

// C0 and C1 control characters, plus the bidirectional overrides. Written as
// escapes rather than literals so the source stays greppable and reviewable.
const CONTROL_AND_BIDI = new RegExp(
  "[\u0000-\u001F\u007F-\u009F\u200E\u200F\u202A-\u202E\u2066-\u2069]",
  "g",
);

/**
 * Normalise a submitted name.
 *
 * Collapses whitespace and strips control characters. **Unicode is preserved** —
 * names contain accents, non-Latin scripts, and combining marks, and rejecting
 * them would be both wrong and quietly discriminatory. Only characters that
 * cannot legitimately appear in a name are removed: C0/C1 controls, and the
 * bidirectional overrides that can make a stored name render as something other
 * than what it actually is.
 */
export function normalizeFullName(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const cleaned = value.replace(CONTROL_AND_BIDI, "").replace(/\s+/g, " ").trim();
  if (cleaned.length < FULL_NAME_MIN || cleaned.length > FULL_NAME_MAX) return null;
  return cleaned;
}

export type OnboardingInput = {
  fullName: string;
  birthday: string;
  referralSource: string;
  referralOther: string | null;
};

export type ValidationResult = { ok: true; value: OnboardingInput } | { ok: false };

/**
 * Validate a submitted payload against the canonical contract.
 *
 * Returns one opaque failure rather than naming the offending field: the form
 * already enforces the same rules client-side, so a caller reaching this path
 * is either a bug or someone probing, and neither needs a field-by-field map.
 */
export function validateOnboarding(body: Record<string, unknown>): ValidationResult {
  const fullName = normalizeFullName(body.fullName);
  if (fullName === null) return { ok: false };

  const birthday = body.birthday;
  if (!isValidBirthday(birthday)) return { ok: false };

  const referralSource = body.referralSource;
  if (!isValidReferral(referralSource)) return { ok: false };

  const rawOther = body.referralOther;
  if (!isValidReferralOther(referralSource, rawOther ?? null)) return { ok: false };
  const referralOther =
    typeof rawOther === "string" && rawOther.trim().length > 0
      ? rawOther.trim().slice(0, REFERRAL_OTHER_MAX)
      : null;

  return {
    ok: true,
    value: { fullName, birthday: birthday as string, referralSource, referralOther },
  };
}

export type CompletionOutcome =
  | { status: "completed" }
  | { status: "already_completed" }
  | { status: "rejected" };

/**
 * Write the profile and mark onboarding done, in one statement.
 *
 * A single conditional UPDATE rather than a read-then-write, for two reasons.
 * It is atomic — the fields and the flag are set together, so onboarding can
 * never be marked complete over a partially saved profile. And the
 * `onboarding_completed = false` predicate makes it **first-run only**: a second
 * submission matches nothing and changes nothing, so this endpoint cannot be
 * used as an undocumented account editor. Profile editing, if it is ever
 * wanted, is a separate settings feature with its own semantics.
 *
 * The user id comes from the validated session. It is never accepted from the
 * request body.
 */
export async function completeOnboarding(
  userId: number,
  input: OnboardingInput,
): Promise<CompletionOutcome> {
  const rows = await query<{ id: number }>(
    `UPDATE users
        SET full_name = $2,
            birthday = $3,
            referral_source = $4,
            referral_source_other = $5,
            onboarding_completed = true
      WHERE id = $1
        AND onboarding_completed = false
        AND is_active = 1
        AND NOT (email_verification_required = true AND email_verified_at IS NULL)
      RETURNING id`,
    [userId, input.fullName, input.birthday, input.referralSource, input.referralOther],
  );
  if (rows.length === 1) return { status: "completed" };

  // Nothing matched. Separate a harmless double submit from an account that is
  // genuinely not eligible.
  const state = await query<{ onboarding_completed: boolean }>(
    `SELECT onboarding_completed FROM users WHERE id = $1`,
    [userId],
  );
  return state[0]?.onboarding_completed
    ? { status: "already_completed" }
    : { status: "rejected" };
}
