import { describe, expect, it } from "vitest";

import cases from "./fixtures/canonical-query-cases.json";
import { canonicalQuery } from "@/lib/api/sign";

/**
 * Differential test against the Python canonicaliser.
 *
 * The two implementations cannot import each other, and a disagreement between
 * them is an authentication outage that shows up only in production, on
 * whichever query shape nobody thought to test. The corpus is generated from a
 * fixed seed by scripts/generate_canonical_query_cases.py, with Python as the
 * reference, and deliberately probes the places the languages differ: the
 * sub-delims encodeURIComponent leaves bare, the space/plus ambiguity, bare
 * delimiters, already-escaped percent signs, and non-ASCII including astral
 * characters.
 */
describe("canonical query differential vs Python", () => {
  const corpus = cases as Array<{ query: string; canonical: string }>;

  it("has a corpus large enough to be worth trusting", () => {
    expect(corpus.length).toBeGreaterThanOrEqual(400);
  });

  it.each(corpus.map((c, i) => [i, c.query, c.canonical] as const))(
    "case %i matches Python: %j",
    (_i, query, expected) => {
      expect(canonicalQuery(query)).toBe(expected);
    },
  );
});
