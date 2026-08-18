import "server-only";
import { createHash, createHmac } from "node:crypto";

/**
 * Lock 1, TypeScript half. Must stay byte-identical to
 * src/tradelens/api/security.py — the shared vectors in
 * docs/contracts/service-signature-vectors.json are what enforce that, since
 * neither implementation can import the other.
 *
 * The message binds timestamp, method, path, canonical query and body hash, so
 * a captured header cannot be replayed against a different endpoint, a
 * different query, or a different payload.
 */

/**
 * RFC 3986 percent-encoding.
 *
 * `encodeURIComponent` leaves `!'()*` unescaped, but Python's
 * `quote(safe="-._~")` escapes them. Without this fixup the two languages
 * would agree on every ASCII-alphanumeric query anyone happened to test and
 * disagree the first time a value contained an apostrophe.
 */
function rfc3986(value: string): string {
  return encodeURIComponent(value).replace(
    /[!'()*]/g,
    (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase(),
  );
}

/**
 * Normalise a raw query string into the form that gets signed.
 *
 * Sorting after encoding is deliberate: every byte is ASCII by then, so
 * JavaScript's UTF-16 ordering and Python's code-point ordering cannot differ.
 * Blank values are preserved — `?debug` is an input a handler can read.
 */
export function canonicalQuery(query: string): string {
  if (!query) return "";
  const pairs: Array<[string, string]> = [];
  for (const [name, value] of new URLSearchParams(query)) {
    pairs.push([rfc3986(name), rfc3986(value)]);
  }
  pairs.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0));
  return pairs.map(([name, value]) => `${name}=${value}`).join("&");
}

export function buildMessage(
  timestamp: string,
  method: string,
  path: string,
  query: string,
  body: string,
): string {
  const bodyHash = createHash("sha256").update(body, "utf8").digest("hex");
  return [timestamp, method.toUpperCase(), path, canonicalQuery(query), bodyHash].join(".");
}

export function signRequest(
  secret: string,
  timestamp: string,
  method: string,
  path: string,
  query: string,
  body: string,
): string {
  return createHmac("sha256", secret)
    .update(buildMessage(timestamp, method, path, query, body), "utf8")
    .digest("hex");
}

export function signatureHeader(
  secret: string,
  method: string,
  path: string,
  query: string,
  body: string,
  now: number = Date.now(),
): string {
  const timestamp = String(Math.floor(now / 1000));
  return `v1=${timestamp}:${signRequest(secret, timestamp, method, path, query, body)}`;
}
