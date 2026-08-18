import { describe, expect, it } from "vitest";

import vectors from "../../docs/contracts/service-signature-vectors.json";
import expectations from "./fixtures/signature-expectations.json";
import { buildMessage, canonicalQuery, signRequest, signatureHeader } from "@/lib/api/sign";

const EXPECTED = expectations as Record<string, string>;

describe("service signature contract", () => {
  for (const vector of vectors.vectors) {
    it(`matches Python for: ${vector.name}`, () => {
      const actual = signRequest(
        vectors.secret,
        vector.timestamp,
        vector.method,
        vector.path,
        vector.query,
        vector.body,
      );
      expect(actual).toBe(EXPECTED[vector.name]);
    });
  }

  it("covers every vector — no expectation goes unasserted", () => {
    expect(Object.keys(EXPECTED).sort()).toEqual(
      vectors.vectors.map((v) => v.name).sort(),
    );
  });

  it("upper-cases the method before signing", () => {
    expect(buildMessage("1", "post", "/x", "", "")).toBe(
      buildMessage("1", "POST", "/x", "", ""),
    );
  });

  it("produces a v1 header carrying the timestamp", () => {
    expect(signatureHeader(vectors.secret, "GET", "/health", "", "", 1_755_300_000_000)).toBe(
      `v1=1755300000:${signRequest(vectors.secret, "1755300000", "GET", "/health", "", "")}`,
    );
  });
});

describe("canonical query", () => {
  it("is order-independent", () => {
    expect(canonicalQuery("b=2&a=1")).toBe(canonicalQuery("a=1&b=2"));
  });

  it("keeps blank values rather than dropping them", () => {
    expect(canonicalQuery("debug")).toBe("debug=");
  });

  it("treats + and %20 as the same space", () => {
    expect(canonicalQuery("s=a+b")).toBe(canonicalQuery("s=a%20b"));
  });

  it("escapes sub-delims that encodeURIComponent leaves bare", () => {
    // The exact case that would otherwise pass every ASCII-alphanumeric test
    // and diverge from Python the first time a value contained an apostrophe.
    expect(canonicalQuery("q=a'b")).toBe("q=a%27b");
  });

  it("distinguishes a different value from the same key", () => {
    expect(canonicalQuery("limit=10")).not.toBe(canonicalQuery("limit=999"));
  });
});

describe("leading question mark", () => {
  it("is not part of the query, matching Python", () => {
    // URLSearchParams already strips it; Python was taught to. Pinned by name
    // here so the corpus is not the only thing holding the behaviour.
    expect(canonicalQuery("?a=1&b=2")).toBe(canonicalQuery("a=1&b=2"));
    expect(canonicalQuery("?")).toBe("");
  });
});
