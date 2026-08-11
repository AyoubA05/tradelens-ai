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
  "TRADELENS_SESSION_SECRET",
  "TRADELENS_INVITE_CODE",
  "TRADELENS_SMTP_HOST",
  "TRADELENS_SMTP_PORT",
  "TRADELENS_SMTP_USER",
  "TRADELENS_SMTP_PASSWORD",
  "TRADELENS_SMTP_FROM",
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

  it("guards env and db access with server-only", () => {
    // The import is the enforcement: a client component importing either of
    // these fails the build instead of shipping a database URL.
    for (const file of ["lib/env.ts", "lib/db/client.ts"]) {
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
