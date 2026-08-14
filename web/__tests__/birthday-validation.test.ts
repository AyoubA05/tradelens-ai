import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

import {
  BIRTHDAY_MAX_AGE_YEARS,
  describeBirthdayProblem,
  isValidBirthday,
} from "@/lib/auth/contract";

/**
 * Birthday rejection has to say which field is wrong and why.
 *
 * The reported case: a date input holding `02/18/0005` submitted `0005-02-18`,
 * the server's 130-year limit correctly refused it, and the page answered "We
 * could not save that. Check the details and try again." The person had
 * checked the details. Nothing on the page connected the failure to the year.
 *
 * The server rule is unchanged and still authoritative. What is tested here is
 * that the reason is available before submission, and — the part that matters
 * for not weakening anything — that the client and server share one
 * implementation rather than two that can drift apart.
 */

const TODAY = new Date("2026-08-14T00:00:00Z");

describe("describeBirthdayProblem", () => {
  it("accepts a plausible birthday", () => {
    expect(describeBirthdayProblem("1994-02-17", TODAY)).toBeNull();
  });

  it("names an empty field rather than calling it invalid", () => {
    expect(describeBirthdayProblem("", TODAY)).toMatch(/enter your date of birth/i);
    expect(describeBirthdayProblem(undefined, TODAY)).toMatch(/enter your date of birth/i);
  });

  it("names the year on the reported case", () => {
    // 0005-02-18 — the exact value from the screenshot.
    const problem = describeBirthdayProblem("0005-02-18", TODAY);
    expect(problem).toMatch(/year/i);
    expect(problem).toContain(String(BIRTHDAY_MAX_AGE_YEARS));
  });

  it("names a future date as future, not as malformed", () => {
    expect(describeBirthdayProblem("2030-01-01", TODAY)).toMatch(/future/i);
  });

  it("rejects a date that is not on the calendar", () => {
    // The Date constructor rolls this over to 2026-03-03 rather than failing.
    expect(describeBirthdayProblem("2026-02-31", TODAY)).toMatch(/real calendar date/i);
  });

  it("rejects a partial or non-ISO value", () => {
    for (const bad of ["1994", "1994-02", "17/02/1994", "not-a-date"]) {
      expect(describeBirthdayProblem(bad, TODAY), bad).toMatch(/complete date/i);
    }
  });

  it("distinguishes its reasons instead of returning one message", () => {
    const reasons = new Set(
      ["", "1994", "2026-02-31", "2030-01-01", "0005-02-18"].map((v) =>
        describeBirthdayProblem(v, TODAY),
      ),
    );
    expect(reasons.size).toBe(5);
  });
});

describe("the server rule is not weakened", () => {
  it("isValidBirthday agrees with describeBirthdayProblem on every case", () => {
    const cases = [
      "1994-02-17", "", "1994", "2026-02-31", "2030-01-01", "0005-02-18",
      "1900-01-01", "2026-08-14", "17/02/1994", "not-a-date",
    ];
    for (const value of cases) {
      expect(isValidBirthday(value, TODAY), value).toBe(
        describeBirthdayProblem(value, TODAY) === null,
      );
    }
  });

  it("still refuses everything it refused before", () => {
    expect(isValidBirthday("0005-02-18", TODAY)).toBe(false);
    expect(isValidBirthday("2030-01-01", TODAY)).toBe(false);
    expect(isValidBirthday("2026-02-31", TODAY)).toBe(false);
    expect(isValidBirthday(null, TODAY)).toBe(false);
  });

  it("accepts today, the boundary a person born today would submit", () => {
    expect(isValidBirthday("2026-08-14", TODAY)).toBe(true);
  });

  it("is defined in terms of the reason function, so the two cannot drift", () => {
    const source = readFileSync(
      path.resolve(__dirname, "..", "lib/auth/contract.ts"),
      "utf8",
    );
    const body = source.slice(source.indexOf("export function isValidBirthday"));
    expect(body).toContain("describeBirthdayProblem(value, today) === null");
  });
});

describe("both forms validate before submitting", () => {
  /**
   * Asserted at the source rather than by rendering, because what matters is
   * that neither form can reach `fetch` with a birthday the endpoint will
   * refuse — and a render test would only cover the paths it happens to drive.
   */
  const forms = [
    "app/signup/signup-form.tsx",
    "app/onboarding/onboarding-form.tsx",
  ];

  for (const relative of forms) {
    it(`${relative} checks the birthday before fetch`, () => {
      const source = readFileSync(
        path.resolve(__dirname, "..", relative),
        "utf8",
      );
      expect(source).toContain("describeBirthdayProblem(birthday)");
      expect(source.indexOf("describeBirthdayProblem(birthday)")).toBeLessThan(
        source.indexOf("await fetch("),
      );
    });
  }

  it("the onboarding form no longer treats a bad date as a missing one", () => {
    const source = readFileSync(
      path.resolve(__dirname, "..", "app/onboarding/onboarding-form.tsx"),
      "utf8",
    );
    // The old guard bundled birthday into the "fill everything in" check.
    expect(source).not.toContain("|| !birthday ||");
  });
});
