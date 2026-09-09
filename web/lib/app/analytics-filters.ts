/**
 * The analytics view's URL state: which lens is open, and which slice of the
 * record it is measured over.
 *
 * The same discipline as `trade-filters.ts` — a positive allowlist, read from
 * a query string that is typo- and attacker-reachable, so an unrecognised
 * parameter is dropped rather than forwarded to the backend or re-serialised
 * into a shared link.
 *
 * `from`/`to` are deliberately absent: the period is the global lens
 * (`lib/app/period.ts`), which this page READS. There is no second date
 * control here, and the prior period the comparison uses is derived
 * server-side rather than chosen (design decision 5).
 *
 * `asset` and `session` are spelled exactly as the journal spells them so one
 * mental model covers both surfaces; `strategy` is added to that scheme
 * rather than a parallel one being invented (design decision 6).
 */
export type AnalyticsFilters = {
  asset?: string;
  session?: string;
  strategy?: string;
};

/** The exact set of filter parameters this page owns. Nothing else. */
export const ANALYTICS_FILTER_KEYS = ["asset", "session", "strategy"] as const;

type FilterKey = (typeof ANALYTICS_FILTER_KEYS)[number];

/**
 * Read the filters from search params.
 *
 * An empty or whitespace-only value is treated as absent, so a cleared field
 * does not round-trip into `?asset=` sitting inertly in the URL and does not
 * reach the API as a filter it would have to reject.
 */
export function parseAnalyticsFilters(params: URLSearchParams): AnalyticsFilters {
  const out: AnalyticsFilters = {};
  for (const key of ANALYTICS_FILTER_KEYS as readonly FilterKey[]) {
    const raw = params.get(key);
    if (raw === null) continue;
    const value = raw.trim();
    if (value === "") continue;
    out[key] = value;
  }
  return out;
}

/** Serialise filters back to search params. Only the known keys, ever. */
export function analyticsFiltersToParams(filters: AnalyticsFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const key of ANALYTICS_FILTER_KEYS as readonly FilterKey[]) {
    const value = filters[key];
    if (value) params.set(key, value);
  }
  return params;
}

/**
 * The four lenses, in the order they are read.
 *
 * Four questions about one filtered sample, not four pages: the labels are
 * retrospective by construction — each names a property of what was recorded,
 * never something to do next.
 */
export const ANALYTICS_LENSES = [
  { id: "performance", label: "Performance" },
  { id: "risk", label: "Risk" },
  { id: "timing", label: "Timing" },
  { id: "setups", label: "Setups" },
] as const;

export type LensId = (typeof ANALYTICS_LENSES)[number]["id"];

export const DEFAULT_LENS: LensId = "performance";

/**
 * The active lens, from the URL.
 *
 * Absent or unrecognised falls back to Performance rather than rendering
 * nothing: a mistyped or truncated link should still show the trader their
 * record, not a blank region that reads as a broken page.
 */
export function lensFromParams(params: URLSearchParams): LensId {
  const raw = params.get("lens");
  const match = ANALYTICS_LENSES.find((lens) => lens.id === raw);
  return match ? match.id : DEFAULT_LENS;
}
