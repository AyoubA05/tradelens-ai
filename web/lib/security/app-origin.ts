import "server-only";

import { requireEnv } from "@/lib/env";

/**
 * The one place the Streamlit destination is decided.
 *
 * It comes from server configuration and nothing else. No part of it is ever
 * taken from a request: no `next`, no `redirect`, no `returnTo`. That is not
 * caution for its own sake — a handoff redirect carries a live credential, so
 * an attacker who could steer the destination would not be redirecting a
 * browser, they would be having one delivered to them.
 *
 * Because there is no client input at all, the classic open-redirect surface
 * does not exist here. What is left to guard is a *misconfigured* origin, which
 * this module refuses to build a URL from.
 */

/** Schemes that must never appear, whatever the configuration says. */
const FORBIDDEN_SCHEMES = ["javascript:", "data:", "vbscript:", "file:", "blob:"];

export class InvalidAppOriginError extends Error {
  constructor(reason: string) {
    // The reason, never the value — a bad origin can end up in a log or an
    // error page, and it may embed credentials in its userinfo.
    super(`APP_ORIGIN is not a usable destination: ${reason}`);
    this.name = "InvalidAppOriginError";
  }
}

/**
 * Whether plain HTTP is tolerated. Local development only, and explicit:
 * production must be HTTPS or the handoff refuses to build a URL at all.
 */
function httpAllowed(): boolean {
  return process.env.NODE_ENV !== "production";
}

/**
 * Parse and validate the configured origin.
 *
 * Rejects, in order of how badly each would go wrong:
 *
 *   - unparseable values, and protocol-relative `//host` forms
 *   - `javascript:`, `data:`, and friends
 *   - anything carrying userinfo — `https://app.example.com@evil.test` parses
 *     with host `evil.test`, which is the whole trick
 *   - a query string or fragment, which would collide with the `?ht=` we append
 *   - plain HTTP outside development
 */
export function validatedAppOrigin(raw?: string): URL {
  const value = (raw ?? requireEnv("APP_ORIGIN")).trim();

  if (value.startsWith("//")) {
    throw new InvalidAppOriginError("protocol-relative URLs are not accepted");
  }
  for (const scheme of FORBIDDEN_SCHEMES) {
    if (value.toLowerCase().startsWith(scheme)) {
      throw new InvalidAppOriginError("scheme is not http or https");
    }
  }

  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new InvalidAppOriginError("value is not an absolute URL");
  }

  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    throw new InvalidAppOriginError("scheme is not http or https");
  }
  if (parsed.protocol === "http:" && !httpAllowed()) {
    throw new InvalidAppOriginError("plain HTTP is only permitted outside production");
  }
  if (parsed.username || parsed.password) {
    throw new InvalidAppOriginError("userinfo is not permitted in a destination");
  }
  if (!parsed.hostname) {
    throw new InvalidAppOriginError("no host");
  }
  if (parsed.search || parsed.hash) {
    throw new InvalidAppOriginError("query strings and fragments are not permitted");
  }

  return parsed;
}

/**
 * Build the handoff destination.
 *
 * `URL` does the assembly, so the token is percent-encoded by the parser rather
 * than by string concatenation, and any path configured on `APP_ORIGIN` — some
 * deployments serve the app under a subpath — is preserved intact.
 *
 * The only query parameter is `ht`. No user id, email, username, expiry, or
 * session credential goes anywhere near this URL.
 */
export function handoffRedirectUrl(token: string, rawOrigin?: string): string {
  const origin = validatedAppOrigin(rawOrigin);
  const destination = new URL(origin.toString());
  destination.search = "";
  destination.searchParams.set("ht", token);
  return destination.toString();
}
