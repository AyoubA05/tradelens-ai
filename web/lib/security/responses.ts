/**
 * Uniform auth responses, and the logging rules that go with them.
 *
 * Two separate concerns that are easy to get wrong in opposite directions:
 *
 * **Account enumeration.** "No such account" and "wrong password" must be
 * indistinguishable from outside, or the login form becomes a way to discover
 * who has an account. Same for password reset: the response is identical
 * whether or not the address is registered. Signup necessarily reveals that an
 * address is taken — that is unavoidable if duplicate registration is to be
 * refused — which is why signup is rate limited per IP instead.
 *
 * **Useful diagnostics.** Operators still need to know why something failed.
 * The reason is carried in a server-side `reason` field that is logged and
 * never serialised into the response body.
 */

/** What actually happened. Server-side only; never sent to a browser. */
export type AuthFailureReason =
  | "unknown_identifier"
  | "wrong_password"
  | "inactive_account"
  | "email_unverified"
  | "rate_limited"
  | "signup_closed"
  | "invalid_invite"
  | "duplicate_email"
  | "weak_password"
  | "invalid_token"
  | "expired_token"
  | "consumed_token"
  | "csrf_failed"
  | "email_unconfigured"
  | "email_send_failed";

/** What the browser is told. Deliberately coarse. */
export const GENERIC_CREDENTIALS_MESSAGE =
  "That email or username and password combination is not correct.";

export const GENERIC_RESET_MESSAGE =
  "If that address has a TradeLens account, a reset code is on its way. The code expires in 30 minutes.";

export const GENERIC_TOKEN_MESSAGE =
  "That link is no longer valid. Request a new one and try again.";

export const RATE_LIMITED_MESSAGE =
  "Too many attempts. Wait a few minutes and try again.";

/**
 * Reasons that must collapse to one message so the response cannot be used to
 * tell registered addresses from unregistered ones.
 */
const INDISTINGUISHABLE: ReadonlySet<AuthFailureReason> = new Set([
  "unknown_identifier",
  "wrong_password",
  "inactive_account",
]);

export function publicMessageFor(reason: AuthFailureReason): string {
  if (INDISTINGUISHABLE.has(reason)) return GENERIC_CREDENTIALS_MESSAGE;
  switch (reason) {
    case "rate_limited":
      return RATE_LIMITED_MESSAGE;
    case "invalid_token":
    case "expired_token":
    case "consumed_token":
      return GENERIC_TOKEN_MESSAGE;
    case "email_unverified":
      return "Verify your email address before signing in. Check your inbox for the code.";
    case "signup_closed":
      return "TradeLens is not accepting new accounts right now.";
    case "invalid_invite":
      return "That invite code is not valid.";
    case "duplicate_email":
      return "An account already exists for that email address.";
    case "weak_password":
      return "Choose a stronger password: at least 12 characters, with upper and lower case, a number, and a symbol.";
    case "csrf_failed":
      return "That request could not be verified. Reload the page and try again.";
    case "email_unconfigured":
    case "email_send_failed":
      // Never say "sent" when nothing was sent. An account whose verification
      // mail silently failed would otherwise wait forever for it.
      return "We could not send that email. This is a problem on our side — please try again shortly.";
    default:
      return "Something went wrong. Please try again.";
  }
}

/**
 * Values that must never appear in a log line, in any form.
 *
 * Listed as a constant so the logging helper and its test agree on one
 * definition rather than drifting apart.
 */
export const NEVER_LOG = [
  "password",
  "password_hash",
  "passwordHash",
  "token",
  "handoff",
  "session",
  "verification_code",
  "reset_code",
  "DATABASE_URL",
  "TRADELENS_SESSION_SECRET",
  "TRADELENS_SMTP_PASSWORD",
  "TRADELENS_INVITE_CODE",
] as const;

/**
 * Log an auth event with a reason and no secrets.
 *
 * Takes a reason and an optional bag of *non-sensitive* context. Any key whose
 * name looks sensitive is dropped rather than redacted — a redacted marker
 * still tells a log reader the field was present, and the point is that these
 * never reach the log at all.
 */
export function logAuthEvent(
  event: string,
  reason: AuthFailureReason | "success",
  context: Record<string, string | number | boolean> = {},
): void {
  const safe: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(context)) {
    const lowered = key.toLowerCase();
    if (NEVER_LOG.some((banned) => lowered.includes(banned.toLowerCase()))) {
      continue;
    }
    safe[key] = value;
  }
  console.info(JSON.stringify({ event, reason, ...safe }));
}
