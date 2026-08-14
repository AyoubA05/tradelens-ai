import "server-only";
import { Pool } from "pg";

import { requireEnv } from "@/lib/env";

/**
 * PostgreSQL access for the auth endpoints.
 *
 * **This module reads and writes the s9 schema. It never creates or alters it.**
 * Alembic is the sole schema authority — production reached its current state
 * precisely because application code was allowed to reconcile schema on the
 * fly, and that is not being reintroduced from a second language. There is no
 * migration, no `CREATE TABLE`, and no `ALTER` anywhere in `web/`.
 *
 * Pooling: serverless invocations are short and numerous, so the pool is kept
 * small and cached on `globalThis` to survive hot reloads in development
 * without opening a new pool per module evaluation.
 */

declare global {
  // eslint-disable-next-line no-var
  var __tradelensPool: Pool | undefined;
}

function createPool(): Pool {
  return new Pool({
    connectionString: requireEnv("DATABASE_URL"),
    // Small on purpose. Each serverless instance gets its own pool, so a large
    // per-instance maximum multiplies into far more Postgres connections than
    // intended once several instances are warm.
    max: 3,
    idleTimeoutMillis: 10_000,
    connectionTimeoutMillis: 10_000,
  });
}

export function pool(): Pool {
  if (!global.__tradelensPool) {
    global.__tradelensPool = createPool();
  }
  return global.__tradelensPool;
}

/**
 * Run a parameterised query.
 *
 * Values are always bound, never interpolated. Every call site in `web/` uses
 * this, so there is one place to look when asking whether SQL injection is
 * possible rather than one place per endpoint.
 *
 * Errors are re-thrown with the driver message removed: a Postgres error
 * routinely carries the DSN, the host, and the failing statement, none of which
 * belongs in a log a support process might forward on.
 */
export async function query<T = unknown>(
  sql: string,
  params: readonly unknown[] = [],
): Promise<T[]> {
  try {
    const result = await pool().query(sql, params as unknown[]);
    return result.rows as T[];
  } catch (error) {
    const kind = error instanceof Error ? error.constructor.name : "Error";
    throw new Error(`Database query failed (${kind}).`);
  }
}

/** Run several statements in one transaction. Rolls back on any throw. */
export async function transaction<T>(
  fn: (run: <R = unknown>(sql: string, params?: readonly unknown[]) => Promise<R[]>) => Promise<T>,
): Promise<T> {
  const client = await pool().connect();
  try {
    await client.query("BEGIN");
    const run = async <R = unknown>(
      sql: string,
      params: readonly unknown[] = [],
    ): Promise<R[]> => {
      const result = await client.query(sql, params as unknown[]);
      return result.rows as R[];
    };
    const value = await fn(run);
    await client.query("COMMIT");
    return value;
  } catch (error) {
    await client.query("ROLLBACK");
    const kind = error instanceof Error ? error.constructor.name : "Error";
    throw new Error(`Database transaction failed (${kind}).`);
  } finally {
    client.release();
  }
}
