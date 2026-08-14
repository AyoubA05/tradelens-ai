import "server-only";

/**
 * Server-only environment access.
 *
 * The `server-only` import above is the enforcement, not a convention: if any
 * client component ever imports this module, the build fails rather than
 * shipping a bundle containing a database URL. That is deliberately a hard
 * error — a leaked `DATABASE_URL` or session secret is not something to catch
 * in review.
 *
 * Nothing here is ever exposed as `NEXT_PUBLIC_*`. Values that genuinely are
 * safe for the browser (the app and site origins) are passed down explicitly
 * from server components as props, so the decision to expose one is always
 * visible at the call site rather than implied by a variable name.
 *
 * Values are returned to callers and never logged. `describeConfig()` exists
 * for diagnostics and reports only whether each setting is present.
 */

/** Settings that must never reach a browser bundle. */
const SECRET_NAMES = [
  "DATABASE_URL",
  "TRADELENS_INVITE_CODE",
  "TRADELENS_SMTP_HOST",
  "TRADELENS_SMTP_PORT",
  "TRADELENS_SMTP_USER",
  "TRADELENS_SMTP_PASSWORD",
  "TRADELENS_SMTP_FROM",
] as const;

/** Settings that are safe to render into a page, passed explicitly as props. */
const PUBLIC_SAFE_NAMES = ["APP_ORIGIN", "SITE_ORIGIN", "SIGNUP_MODE"] as const;

export type SecretName = (typeof SECRET_NAMES)[number];
export type PublicSafeName = (typeof PUBLIC_SAFE_NAMES)[number];

export class MissingEnvError extends Error {
  constructor(name: string) {
    // Names only. A message quoting the value would put a secret in a log line
    // and, on a server error page, possibly in front of a user.
    super(`Required environment variable ${name} is not set.`);
    this.name = "MissingEnvError";
  }
}

function read(name: string): string | undefined {
  const value = process.env[name];
  return value && value.length > 0 ? value : undefined;
}

/** Read a setting, or throw. Use where the request cannot proceed without it. */
export function requireEnv(name: SecretName | PublicSafeName): string {
  const value = read(name);
  if (!value) throw new MissingEnvError(name);
  return value;
}

/** Read a setting, or fall back. Use where absence is a valid configuration. */
export function optionalEnv(
  name: SecretName | PublicSafeName,
  fallback = "",
): string {
  return read(name) ?? fallback;
}

export type SignupMode = "invite" | "open" | "closed";

/**
 * How signup is gated right now.
 *
 * Unset defaults to `invite`. **An unrecognised value is treated as `closed`**:
 * an access-control setting nobody can parse must fail shut, not open. Read
 * server-side only, so a browser cannot see which mode is active except through
 * what the page actually renders.
 */
export function signupMode(): SignupMode {
  const raw = read("SIGNUP_MODE");
  if (raw === undefined) return "invite";
  if (raw === "invite" || raw === "open" || raw === "closed") return raw;
  console.warn(
    `SIGNUP_MODE has an unrecognised value; treating signup as closed.`,
  );
  return "closed";
}

/** True when outbound mail is configured. Delivery is never assumed. */
export function emailConfigured(): boolean {
  return Boolean(read("TRADELENS_SMTP_HOST") && read("TRADELENS_SMTP_FROM"));
}

/** Presence-only report for diagnostics. Never contains a value. */
export function describeConfig(): Record<string, "set" | "unset"> {
  const out: Record<string, "set" | "unset"> = {};
  for (const name of [...SECRET_NAMES, ...PUBLIC_SAFE_NAMES]) {
    out[name] = read(name) ? "set" : "unset";
  }
  return out;
}

export const SECRET_ENV_NAMES: readonly string[] = SECRET_NAMES;
export const PUBLIC_SAFE_ENV_NAMES: readonly string[] = PUBLIC_SAFE_NAMES;
