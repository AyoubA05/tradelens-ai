import { describe, expect, it } from "vitest";
import {
  isSafeRelativePath,
  safeRedirect,
  isSameOriginRequest,
} from "@/lib/security/redirect";
import {
  publicMessageFor,
  GENERIC_CREDENTIALS_MESSAGE,
} from "@/lib/security/responses";

describe("redirect validation", () => {
  it("accepts ordinary in-site paths", () => {
    for (const p of ["/login", "/onboarding", "/a/b?c=d", "/x#y"]) {
      expect(isSafeRelativePath(p)).toBe(true);
    }
  });

  it("refuses every off-site form", () => {
    // Each of these has been a real open-redirect bypass somewhere.
    const hostile = [
      "//evil.com",              // protocol-relative
      "/\\evil.com",             // backslash variant browsers treat as //
      "https://evil.com",
      "http://evil.com",
      "javascript:alert(1)",
      "data:text/html,x",
      " /login",                 // leading space, then a path
      "/login\nSet-Cookie: x",   // header injection via newline
      "login",                   // unrooted, resolves relatively
      "",
    ];
    for (const value of hostile) {
      expect(isSafeRelativePath(value), value).toBe(false);
    }
  });

  it("falls back rather than following an unsafe destination", () => {
    expect(safeRedirect("https://evil.com", "/login")).toBe("/login");
    expect(safeRedirect(undefined, "/login")).toBe("/login");
    expect(safeRedirect("/onboarding", "/login")).toBe("/onboarding");
  });

  it("allows an explicitly listed origin, by origin and not by prefix", () => {
    const allowed = ["https://tradelenai.streamlit.app"];
    expect(safeRedirect("https://tradelenai.streamlit.app/x", "/login", allowed))
      .toBe("https://tradelenai.streamlit.app/x");
    // Prefix matching would accept both of these. Origin comparison does not.
    expect(safeRedirect("https://tradelenai.streamlit.app.evil.com", "/login", allowed))
      .toBe("/login");
    expect(safeRedirect("https://tradelenai.streamlit.app@evil.com", "/login", allowed))
      .toBe("/login");
  });
});

describe("same-origin check", () => {
  const headers = (h: Record<string, string>) => ({
    get: (n: string) => h[n.toLowerCase()] ?? null,
  });

  it("accepts a matching Origin", () => {
    expect(isSameOriginRequest(headers({ origin: "https://a.io" }), "https://a.io")).toBe(true);
  });

  it("rejects a foreign Origin", () => {
    expect(isSameOriginRequest(headers({ origin: "https://evil.com" }), "https://a.io")).toBe(false);
  });

  it("falls back to Referer", () => {
    expect(isSameOriginRequest(headers({ referer: "https://a.io/login" }), "https://a.io")).toBe(true);
  });

  it("rejects a request carrying neither", () => {
    // Treating absence as acceptable is what makes this check decorative.
    expect(isSameOriginRequest(headers({}), "https://a.io")).toBe(false);
  });
});

describe("generic auth responses", () => {
  it("cannot distinguish an unknown account from a wrong password", () => {
    expect(publicMessageFor("unknown_identifier")).toBe(GENERIC_CREDENTIALS_MESSAGE);
    expect(publicMessageFor("wrong_password")).toBe(GENERIC_CREDENTIALS_MESSAGE);
    expect(publicMessageFor("inactive_account")).toBe(GENERIC_CREDENTIALS_MESSAGE);
  });

  it("cannot distinguish invalid, expired and already-used tokens", () => {
    const messages = new Set(
      (["invalid_token", "expired_token", "consumed_token"] as const).map(publicMessageFor),
    );
    expect(messages.size).toBe(1);
  });

  it("never claims an email was sent when it was not", () => {
    for (const reason of ["email_unconfigured", "email_send_failed"] as const) {
      const message = publicMessageFor(reason).toLowerCase();
      expect(message).toContain("could not send");
      expect(message).not.toMatch(/\bsent\b|on its way/);
    }
  });
});
