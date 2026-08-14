/**
 * Account rules, TypeScript side.
 *
 * These same rules exist in `src/tradelens/services/users.py` for the Streamlit
 * app. The two implementations are independent — importing one into the other
 * would mean running a Python HTTP service on the signup path purely to avoid
 * duplication, which adds a failure mode to every signup to save a little code.
 *
 * What stops them drifting into two unrelated definitions is
 * `docs/contracts/auth-contract-vectors.json`: both test suites read the same
 * vectors, so a rule changed on one side without the other fails on both.
 *
 * Pure functions only. No database, no I/O, no secrets — so this module is
 * cheap to test exhaustively.
 */

/**
 * Trim, then lowercase. Storage and lookup must agree or the same address
 * registers twice.
 *
 * The `+tag` is deliberately preserved: stripping it would merge addresses the
 * owner treats as distinct, and no mail provider guarantees they are the same
 * inbox.
 */
export function normalizeEmail(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const cleaned = value.trim().toLowerCase();
  return cleaned.length > 0 ? cleaned : null;
}

/**
 * Permissive on purpose. The only authority on whether an address works is
 * whether mail arrives; this rejects the obviously-not-an-address cases so a
 * typo is caught at entry, and nothing more.
 *
 * Mirrors `_EMAIL_RE` in users.py.
 */
const EMAIL_RE = /^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/;

export function isValidEmail(value: unknown): boolean {
  const normalized = normalizeEmail(value);
  return normalized !== null && EMAIL_RE.test(normalized);
}

/** The pre-existing constraint every legacy username already satisfies. */
export const LEGACY_USERNAME_RE = /^[a-zA-Z0-9_]{3,20}$/;

/** What an opaque internal username looks like. */
export const OPAQUE_USERNAME_RE = /^u_[0-9a-f]{16}$/;

/**
 * An opaque internal username for an account whose owner never chose one.
 *
 * Takes no arguments, which is the point: it *cannot* be derived from the
 * email, the name, or anything else the user supplied. The username is not a
 * private value — it is the legacy login identifier and appears in support and
 * admin contexts — so deriving it from the address would leak the local part
 * wherever it surfaces.
 *
 * 64 bits of randomness, 18 characters, inside the legacy constraint.
 */
export function generateInternalUsername(): string {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `u_${hex}`;
}

export type PasswordFailure =
  | "too_short"
  | "no_lower"
  | "no_upper"
  | "no_digit"
  | "no_symbol";

export const PASSWORD_MIN_LENGTH = 12;
const SYMBOL_RE = /[!-/:-@[-`{-~]/;

/**
 * The identical policy the 21.dev strength meter displays.
 *
 * The meter is UX and can be bypassed by anyone posting directly; this is the
 * enforcement. They must not diverge — a form that shows four requirements
 * while the API enforces different ones is a form that lies.
 */
export function validatePassword(value: unknown): PasswordFailure[] {
  const password = typeof value === "string" ? value : "";
  const failures: PasswordFailure[] = [];
  if (password.length < PASSWORD_MIN_LENGTH) failures.push("too_short");
  if (!/[a-z]/.test(password)) failures.push("no_lower");
  if (!/[A-Z]/.test(password)) failures.push("no_upper");
  if (!/\d/.test(password)) failures.push("no_digit");
  if (!SYMBOL_RE.test(password)) failures.push("no_symbol");
  return failures;
}

export function isAcceptablePassword(value: unknown): boolean {
  return validatePassword(value).length === 0;
}

/** State a site-created account must start in. */
export const NEW_ACCOUNT_DEFAULTS = {
  onboarding_completed: false,
  strategy_profile_completed: false,
  email_verified_at: null,
  // True, deliberately. The s9 backfill set this false for accounts that
  // predate verification; a new account inheriting that exemption would be
  // able to skip verification entirely.
  email_verification_required: true,
  is_active: 1,
} as const;

/** An ISO date that is a real calendar date and a plausible birthday. */
export function isValidBirthday(value: unknown, today = new Date()): boolean {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return false;
  // Round-trip catches dates the Date constructor silently rolls over, such as
  // 2026-02-31 becoming 2026-03-03.
  if (parsed.toISOString().slice(0, 10) !== value) return false;
  if (parsed.getTime() > today.getTime()) return false;
  const earliest = new Date(today.getTime() - 130 * 365.25 * 24 * 3600 * 1000);
  return parsed.getTime() >= earliest.getTime();
}

export const REFERRAL_SOURCES = [
  "TikTok",
  "Instagram",
  "YouTube",
  "Google/Search",
  "Friend",
  "Reddit",
  "X/Twitter",
  "Other",
] as const;

export type ReferralSource = (typeof REFERRAL_SOURCES)[number];

export function isValidReferral(value: unknown): value is ReferralSource {
  return (
    typeof value === "string" &&
    (REFERRAL_SOURCES as readonly string[]).includes(value)
  );
}

export const REFERRAL_OTHER_MAX = 120;

/**
 * `referral_source_other` is only meaningful alongside "Other", and is optional
 * even then. Supplying it with a different source is rejected rather than
 * quietly dropped, so a mismatched payload is a visible client bug.
 */
export function isValidReferralOther(
  source: unknown,
  other: unknown,
): boolean {
  if (other === undefined || other === null || other === "") return true;
  if (typeof other !== "string") return false;
  if (other.length > REFERRAL_OTHER_MAX) return false;
  return source === "Other";
}
