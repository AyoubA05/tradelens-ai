import "server-only";
import { query, transaction } from "@/lib/db/client";

/**
 * Rate limiting backed by the `auth_attempts` table.
 *
 * **Not an in-memory Map.** Each serverless invocation may run in a fresh
 * instance with its own memory, so an in-process counter resets whenever the
 * platform decides to cold-start — which makes it not a limit at all, just a
 * speed bump for whoever happens to hit a warm instance.
 *
 * The table already exists: Alembic revision `s9t0u1v2w3x4` created it with
 * `(bucket, action, succeeded, created_at)`. No schema change is needed for
 * this step.
 *
 * Two properties worth stating because they are easy to get backwards:
 *
 * * **Per-identifier limits count failures only.** If every attempt counted,
 *   an attacker could lock a known account out simply by burning its quota.
 * * **A success clears that identifier's failures**, so a person who mistypes
 *   a password four times and then gets it right is not left near a threshold.
 */

export type AuthAction =
  | "login"
  | "signup"
  | "invite"
  | "verify"
  | "forgot"
  | "reset";

export type RateLimitRule = {
  /** Attempts permitted inside the window. */
  limit: number;
  /** Window length in seconds. */
  windowSeconds: number;
  /** When true, only failed attempts count toward the limit. */
  failuresOnly: boolean;
};

/** Limits from the approved design. Per-IP by default, per-identifier where noted. */
export const RULES: Record<string, RateLimitRule> = {
  "login:ip": { limit: 10, windowSeconds: 15 * 60, failuresOnly: false },
  "login:id": { limit: 5, windowSeconds: 15 * 60, failuresOnly: true },
  "signup:ip": { limit: 5, windowSeconds: 3600, failuresOnly: false },
  "signup:id": { limit: 3, windowSeconds: 3600, failuresOnly: true },
  "invite:ip": { limit: 10, windowSeconds: 3600, failuresOnly: true },
  // Keyed `:ip` because that is the bucket it is applied to. It was written as
  // `verify:id` and handed an IP bucket, which reads as a per-account limit and
  // is not one — the distinction matters, since a per-identifier limit on
  // verification would let anyone lock a known address out of confirming it.
  "verify:ip": { limit: 10, windowSeconds: 3600, failuresOnly: true },
  "forgot:ip": { limit: 5, windowSeconds: 3600, failuresOnly: false },
  "forgot:id": { limit: 3, windowSeconds: 3600, failuresOnly: false },
  "reset:ip": { limit: 10, windowSeconds: 3600, failuresOnly: true },
};

/**
 * A bucket key.
 *
 * Identifier buckets are hashed, not stored in the clear: `auth_attempts` would
 * otherwise become a slow-growing list of every email address anyone has ever
 * typed into the login form, including addresses with no account.
 */
export async function bucketFor(
  kind: "ip" | "id",
  value: string,
): Promise<string> {
  if (kind === "ip") return `ip:${value}`;
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value.toLowerCase()),
  );
  const hex = Array.from(new Uint8Array(digest), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
  return `id:${hex.slice(0, 32)}`;
}

/**
 * How often a write also triggers the retention sweep.
 *
 * The sweep used to be a function nothing ever called, under a comment saying
 * no scheduled job was needed — so `auth_attempts` had no retention at all and
 * grew for the lifetime of the deployment. Hooking it here is what makes that
 * comment true. One in two hundred writes keeps the amortised cost negligible
 * while guaranteeing it runs often on any endpoint that sees real traffic.
 */
const SWEEP_PROBABILITY = 1 / 200;

/**
 * Atomically reserve one attempt unless this bucket is already at its limit.
 *
 * The advisory transaction lock closes the count-then-insert race. Without it,
 * a burst of parallel requests can all observe the same below-limit count and
 * all proceed before any of them records an attempt. The reservation is stored
 * as a failure until a successful failures-only flow clears the bucket; if a
 * function dies mid-request, the conservative outcome is one consumed slot.
 *
 * Returns true when the caller should be refused. An unknown rule still allows
 * the request so a programming mistake is visible rather than silently mapped
 * to an arbitrary policy.
 */
export async function isRateLimited(
  bucket: string,
  action: AuthAction,
  ruleKey: string,
): Promise<boolean> {
  const rule = RULES[ruleKey];
  if (!rule) return false;

  const limited = await transaction(async (run) => {
    // Stable, database-wide lock for this exact bucket/action pair. Transaction
    // scope guarantees release on both commit and rollback.
    await run(
      "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
      [`${bucket}\u0000${action}`],
    );
    const rows = await run<{ n: string }>(
      `SELECT count(*) AS n FROM auth_attempts
        WHERE bucket = $1
          AND action = $2
          AND created_at > now() - make_interval(secs => $3)
          AND ($4 = false OR succeeded = false)`,
      [bucket, action, rule.windowSeconds, rule.failuresOnly],
    );
    if (Number(rows[0]?.n ?? 0) >= rule.limit) return true;

    await run(
      "INSERT INTO auth_attempts (bucket, action, succeeded, created_at) VALUES ($1, $2, false, now())",
      [bucket, action],
    );
    return false;
  });

  if (Math.random() < SWEEP_PROBABILITY) {
    try {
      await sweepOldAttempts();
    } catch {
      // Retention cannot change the auth result.
    }
  }
  return limited;
}

/**
 * Clear a bucket's failures after a success.
 *
 * Deletes rather than marking, because the only reason those rows exist is to
 * feed the counter and keeping them would make the window permanently dirty.
 */
export async function clearFailures(
  bucket: string,
  action: AuthAction,
): Promise<void> {
  await query(
    "DELETE FROM auth_attempts WHERE bucket = $1 AND action = $2 AND succeeded = false",
    [bucket, action],
  );
}

/** 30-day retention. Driven from attempt reservations, so no scheduled job is needed. */
export async function sweepOldAttempts(): Promise<void> {
  await query("DELETE FROM auth_attempts WHERE created_at < now() - interval '30 days'");
}

/**
 * The client IP, from the proxy headers Vercel sets.
 *
 * Falls back to a constant rather than to something attacker-controlled: if the
 * real IP cannot be determined, every such request shares one bucket, which
 * throttles conservatively instead of handing out unlimited fresh buckets.
 */
export function clientIp(headers: { get(name: string): string | null }): string {
  const forwarded = headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) return first;
  }
  return headers.get("x-real-ip")?.trim() || "unknown";
}
