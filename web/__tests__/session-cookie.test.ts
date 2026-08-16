import { describe, expect, it } from "vitest";

import { sessionTokenFromCookieHeader } from "@/lib/auth/session";

describe("website session cookie parsing", () => {
  it("returns null instead of throwing on malformed percent encoding", () => {
    expect(sessionTokenFromCookieHeader("other=1; tl_session=%E0%A4%A")).toBeNull();
  });

  it("decodes a valid credential without accepting a prefix collision", () => {
    expect(sessionTokenFromCookieHeader("tl_session_backup=bad; tl_session=good%2Dtoken"))
      .toBe("good-token");
  });
});
