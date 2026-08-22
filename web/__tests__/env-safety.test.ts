import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

const WEB = path.resolve(__dirname, "..");

function sources(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (["node_modules", ".next", "public", "__tests__"].includes(entry)) continue;
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) sources(full, acc);
    else if (/\.(ts|tsx|mjs)$/.test(entry)) acc.push(full);
  }
  return acc;
}

/** Anything in here would be inlined into the browser bundle if NEXT_PUBLIC_. */
const MUST_STAY_SERVER_SIDE = [
  "DATABASE_URL",
  "TRADELENS_INVITE_CODE",
  "TRADELENS_SMTP_HOST",
  "TRADELENS_SMTP_PORT",
  "TRADELENS_SMTP_USER",
  "TRADELENS_SMTP_PASSWORD",
  "TRADELENS_SMTP_FROM",
  "TL_SERVICE_SECRET",
  "TL_SERVICE_SECRET_PREVIOUS",
  "TL_API_ORIGIN",
];

describe("secrets never reach the browser", () => {
  const files = sources(WEB);

  it("declares no NEXT_PUBLIC_ variable carrying a secret", () => {
    const offenders: string[] = [];
    for (const file of files) {
      const text = readFileSync(file, "utf8");
      for (const secret of MUST_STAY_SERVER_SIDE) {
        if (text.includes(`NEXT_PUBLIC_${secret}`)) {
          offenders.push(`${path.relative(WEB, file)}: NEXT_PUBLIC_${secret}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("keeps .env.example free of NEXT_PUBLIC_ secrets", () => {
    const example = readFileSync(path.join(WEB, ".env.example"), "utf8");
    for (const secret of MUST_STAY_SERVER_SIDE) {
      expect(example).not.toContain(`NEXT_PUBLIC_${secret}`);
    }
  });

  it("documents the server-to-server API variables where Next.js loads them", () => {
    const example = readFileSync(path.join(WEB, ".env.example"), "utf8");
    expect(example).toMatch(/^TL_API_ORIGIN=/m);
    expect(example).toMatch(/^TL_SERVICE_SECRET=$/m);
  });

  it("guards env and db access with server-only", () => {
    // The import is the enforcement: a client component importing either of
    // these fails the build instead of shipping a database URL.
    for (const file of [
      "lib/env.ts",
      "lib/db/client.ts",
      "lib/api/client.ts",
      "lib/api/sign.ts",
      "lib/app/overview.ts",
    ]) {
      const text = readFileSync(path.join(WEB, file), "utf8");
      expect(text.startsWith('import "server-only"'), file).toBe(true);
    }
  });

  it("never reads a secret directly inside a client component", () => {
    const offenders: string[] = [];
    for (const file of files) {
      const text = readFileSync(file, "utf8");
      if (!text.includes('"use client"')) continue;
      for (const secret of MUST_STAY_SERVER_SIDE) {
        if (text.includes(`process.env.${secret}`)) {
          offenders.push(`${path.relative(WEB, file)}: ${secret}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("the web app never mutates schema", () => {
  it("contains no DDL — Alembic is the only schema authority", () => {
    const ddl = /\b(CREATE TABLE|ALTER TABLE|DROP TABLE|CREATE INDEX|DROP INDEX)\b/i;
    const offenders = sources(WEB)
      .filter((f) => {
        const text = readFileSync(f, "utf8");
        // Strip comments: lib/db/client.ts explains the rule by naming it.
        const code = text
          .split("\n")
          .filter((l) => !l.trim().startsWith("*") && !l.trim().startsWith("//") && !l.trim().startsWith("/*"))
          .join("\n");
        return ddl.test(code);
      })
      .map((f) => path.relative(WEB, f));
    expect(offenders).toEqual([]);
  });
});

describe("no dead session secret", () => {
  /**
   * The original design shared one HMAC key between the site and Streamlit.
   * What shipped uses opaque random credentials with their hashes in Postgres,
   * so the key protects nothing here. A configuration variable that looks
   * required but is read by nothing is worse than absent: whoever provisions
   * production would generate one, believe it matters, and never learn that
   * rotating it does nothing.
   *
   * It survives in the logging denylist on purpose — that list is about names
   * that must never be printed, whether or not this app reads them.
   */
  const CODE = sources(WEB).filter(
    (f) => !f.endsWith(path.join("lib", "security", "responses.ts")),
  );

  it("reads TRADELENS_SESSION_SECRET nowhere", () => {
    const offenders = CODE.filter((f) =>
      readFileSync(f, "utf8").includes("TRADELENS_SESSION_SECRET"),
    ).map((f) => path.relative(WEB, f));
    expect(offenders).toEqual([]);
  });

  it("does not ask for it in .env.example", () => {
    const example = readFileSync(path.join(WEB, ".env.example"), "utf8");
    const assignments = example
      .split("\n")
      .filter((line) => /^\s*TRADELENS_SESSION_SECRET\s*=/.test(line));
    expect(assignments).toEqual([]);
  });

  it("still refuses to log the name", () => {
    const text = readFileSync(path.join(WEB, "lib/security/responses.ts"), "utf8");
    expect(text).toContain("TRADELENS_SESSION_SECRET");
  });
});
