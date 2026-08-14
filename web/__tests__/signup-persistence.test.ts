import { beforeEach, describe, expect, it, vi } from "vitest";

const { runTransaction } = vi.hoisted(() => ({
  runTransaction: vi.fn(),
}));

vi.mock("@/lib/db/client", () => ({
  transaction: runTransaction,
}));

vi.mock("bcryptjs", () => ({
  default: { hash: vi.fn().mockResolvedValue("$2b$12$test-hash") },
}));

import { createAccount } from "@/lib/auth/signup";

beforeEach(() => {
  runTransaction.mockReset();
});

describe("site signup persistence", () => {
  it("completes personal onboarding at signup while preserving the Strategy Profile gate", async () => {
    const statements: { sql: string; params: unknown[] }[] = [];
    runTransaction.mockImplementation(async (work: never) => {
      const run = async (sql: string, params: unknown[] = []) => {
        statements.push({ sql, params });
        if (sql.includes("SELECT id FROM users")) return [];
        if (sql.includes("INSERT INTO users")) return [{ id: 42 }];
        return [];
      };
      return (work as unknown as (query: typeof run) => Promise<unknown>)(run);
    });

    await createAccount({
      email: "smoke@example.com",
      password: "Correct-Horse-Battery-9!",
      fullName: "Smoke Tester",
      birthday: "1994-02-17",
      referralSource: "Reddit",
      referralOther: null,
    });

    const insert = statements.find(({ sql }) => sql.includes("INSERT INTO users"));
    expect(insert).toBeDefined();
    expect(insert!.params.slice(4, 10)).toEqual([
      "Smoke Tester",
      "1994-02-17",
      "Reddit",
      null,
      true,
      false,
    ]);
  });
});
