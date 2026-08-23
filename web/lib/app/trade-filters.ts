/**
 * The Trades list filter contract: what a filtered view of the journal is
 * allowed to carry in its URL, beyond the period (`from`/`to`) that already
 * governs the route.
 *
 * This is a positive allowlist, the same shape as the PATCH allowlist in
 * `TradeUpdate` (see `schema.d.ts`): a query string is attacker- and
 * typo-reachable, so an unrecognised parameter is dropped on read rather than
 * forwarded to the backend or re-serialised into a link. That keeps a shared
 * journal URL exactly as wide as the filters this page actually understands,
 * never wider by accident (a stray `?debug=1` copied into a shared link) and
 * never narrower (a filter silently lost on a round trip).
 *
 * `from`/`to` are deliberately absent here — they are the period lens
 * (`lib/app/period.ts`), read once by the page and not re-derived per filter.
 */
export type TradeFilters = {
  asset?: string;
  session?: string;
  setup?: string;
  result?: string;
};

/** The exact set of query parameters this filter bar owns. Nothing else. */
export const TRADE_FILTER_KEYS = ["asset", "session", "setup", "result"] as const;

type FilterKey = (typeof TRADE_FILTER_KEYS)[number];

/**
 * Read the filters from search params.
 *
 * A key not in `TRADE_FILTER_KEYS` is dropped, not forwarded — the same
 * discipline `periodFromParams` applies to a malformed date. An empty or
 * whitespace-only value is treated as absent so a cleared text input does not
 * round-trip into `?asset=` sitting inertly in the URL.
 */
export function parseFilters(params: URLSearchParams): TradeFilters {
  const out: TradeFilters = {};
  for (const key of TRADE_FILTER_KEYS as readonly FilterKey[]) {
    const raw = params.get(key);
    if (raw === null) continue;
    const value = raw.trim();
    if (value === "") continue;
    out[key] = value;
  }
  return out;
}

/** Serialise filters back to search params. Only the known keys, ever. */
export function filtersToParams(filters: TradeFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of TRADE_FILTER_KEYS as readonly FilterKey[]) {
    const value = filters[key];
    if (value) params.set(key, value);
  }
  return params;
}
