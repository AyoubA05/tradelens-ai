import { beforeEach, describe, expect, it, vi } from "vitest";

const { connect, attachDatabasePool } = vi.hoisted(() => ({
  connect: vi.fn(),
  attachDatabasePool: vi.fn(),
}));

vi.mock("pg", () => ({
  Pool: class MockPool {
    connect = connect;
    query = vi.fn();
  },
}));

vi.mock("@vercel/functions", () => ({ attachDatabasePool }));

import { transaction } from "@/lib/db/client";

beforeEach(() => {
  connect.mockReset();
  attachDatabasePool.mockClear();
  delete global.__tradelensPool;
  process.env.DATABASE_URL = "postgresql://private-user:private-password@private-host/db";
});

describe("database error boundary", () => {
  it("sanitizes a pool connection failure before it reaches application logs", async () => {
    connect.mockRejectedValueOnce(
      new Error("connect ECONNREFUSED private-user:private-password@private-host"),
    );

    let message = "";
    try {
      await transaction(async () => null);
    } catch (error) {
      message = String(error);
    }

    expect(message).toContain("Database transaction failed (Error)");
    expect(message).not.toContain("private-user");
    expect(message).not.toContain("private-password");
    expect(message).not.toContain("private-host");
  });

  it("preserves only the database code needed for safe caller decisions", async () => {
    const failure = Object.assign(new Error("duplicate value in private_table"), {
      code: "23505",
    });
    const query = vi
      .fn()
      .mockResolvedValueOnce({ rows: [] })
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce({ rows: [] });
    connect.mockResolvedValueOnce({ query, release: vi.fn() });

    let caught: unknown;
    try {
      await transaction(async (run) => run("INSERT INTO users VALUES ($1)", ["secret"]));
    } catch (error) {
      caught = error;
    }

    expect(caught).toMatchObject({ code: "23505" });
    expect(String(caught)).not.toContain("private_table");
    expect(query).toHaveBeenLastCalledWith("ROLLBACK");
  });
});
