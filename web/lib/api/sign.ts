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
 * Pair order is preserved because handlers can observe the order of repeated
 * keys. Blank values are preserved — `debug` is an input a handler can read.
 */
export function canonicalQuery(query: string): string {
  if (!query) return "";
  const pairs: Array<[string, string]> = [];
  // URLSearchParams treats one leading `?` as a URL delimiter. Our input is
  // already the raw query (the delimiter is absent), so encode a literal first
  // question mark before parsing to match Python/Starlette semantics.
  const parseable = query.startsWith("?") ? `%3F${query.slice(1)}` : query;
  for (const [name, value] of new URLSearchParams(parseable)) {
    pairs.push([rfc3986(name), rfc3986(value)]);
  }
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
