/**
 * The period lens: the window every figure in the product is measured over.
 *
 * This exists as chrome rather than as a per-page filter because no number in a
 * post-trade journal means anything without its window and its sample size. A
 * win rate over four days and a win rate over four months are different claims,
 * and the old app let a page show one while the reader assumed the other.
 *
 * It lives in the URL so a period is linkable, back-button-able, and shared
 * between pages without a client store. Later phases READ this; no page may
 * introduce a second date control.
 */
export type Period = {
  /** Inclusive ISO date, YYYY-MM-DD. */
  from: string;
  /** Inclusive ISO date, YYYY-MM-DD. */
  to: string;
  /** The preset this range corresponds to, or "custom". */
  presetId: string;
};

export const PERIOD_PRESETS = [
  { id: "7d", label: "Last 7 days", days: 7 },
  { id: "30d", label: "Last 30 days", days: 30 },
  { id: "90d", label: "Last 90 days", days: 90 },
  { id: "ytd", label: "Year to date", days: 0 },
] as const;

const DEFAULT_PRESET = "30d";
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function toIso(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function parseIso(value: string | null): Date | null {
  if (!value || !ISO_DATE.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return null;
  // `new Date` silently rolls a calendar-invalid value like 2026-02-30 over to
  // 2026-03-02 rather than rejecting it. A round-trip through the same ISO
  // format is the cheapest way to catch that: a valid date always comes back
  // unchanged, and a rolled-over one never does.
  if (toIso(parsed) !== value) return null;
  return parsed;
}

function shiftDays(from: Date, days: number): Date {
  const out = new Date(from);
  out.setUTCDate(out.getUTCDate() - days);
  return out;
}

/**
 * The date range a preset resolves to, as of `today`.
 *
 * Exported so the control that renders the preset list can build the exact
 * search params the contract expects instead of reimplementing this — the
 * year-to-date special case and the `PERIOD_PRESETS[1]` fallback only exist
 * here, once.
 */
export function rangeForPreset(presetId: string, today: Date): { from: string; to: string } {
  if (presetId === "ytd") {
    return { from: `${today.getUTCFullYear()}-01-01`, to: toIso(today) };
  }
  const preset = PERIOD_PRESETS.find((p) => p.id === presetId) ?? PERIOD_PRESETS[1];
  // Inclusive of both ends: "last 7 days" is today plus the six before it.
  return { from: toIso(shiftDays(today, preset.days - 1)), to: toIso(today) };
}

function presetMatching(from: string, to: string, today: Date): string {
  for (const preset of PERIOD_PRESETS) {
    const candidate = rangeForPreset(preset.id, today);
    if (candidate.from === from && candidate.to === to) return preset.id;
  }
  return "custom";
}

/**
 * Read a period from search params, falling back to the default window.
 *
 * Bad input fails to the default rather than raising: this comes from a URL, so
 * it is attacker- and typo-reachable, and a window nothing can render is worse
 * than a window the reader did not ask for. A reversed range is swapped rather
 * than rejected, because the intent is unambiguous.
 */
export function periodFromParams(params: URLSearchParams, today: Date = new Date()): Period {
  const fromDate = parseIso(params.get("from"));
  const toDate = parseIso(params.get("to"));

  if (!fromDate || !toDate) {
    const fallback = rangeForPreset(DEFAULT_PRESET, today);
    return { ...fallback, presetId: DEFAULT_PRESET };
  }

  const [start, end] = fromDate <= toDate ? [fromDate, toDate] : [toDate, fromDate];
  const from = toIso(start);
  const to = toIso(end);
  return { from, to, presetId: presetMatching(from, to, today) };
}

/** Serialise a period back to search params. Both bounds, always. */
export function periodToParams(period: Period): URLSearchParams {
  const params = new URLSearchParams();
  params.set("from", period.from);
  params.set("to", period.to);
  return params;
}

/** The top-bar reading. ISO order, because the mono column has to align. */
export function formatPeriod(period: Period): string {
  return `${period.from} → ${period.to}`;
}

/**
 * The routes the global analysis range governs.
 *
 * Exact matches, and an allowlist rather than a denylist. A new sub-route has to
 * opt in on purpose instead of inheriting a control nobody decided it should
 * have, and forgetting to add a route costs a missing lens — visible and easily
 * fixed — where forgetting to exclude one costs a lens that appears to govern a
 * page it does not, which a reader has no way to detect.
 */
export const PERIOD_SCOPED_ROUTES = [
  "/app", // Overview
  "/app/journal", // Trades
  "/app/analytics",
  "/app/reviews", // Patterns; the weekly and daily views keep their own controls
];

/**
 * Whether this route is governed by the global analysis range.
 *
 * Routes whose temporal semantics differ are absent by design: a trade detail
 * page describes one trade, New Trade describes the trade being logged, Weekly
 * Recap keeps its week selector, Daily Debrief its day selector, and Strategy
 * Profile and Settings are not time-scoped at all.
 *
 * The lens is hidden where this returns false rather than shown inertly. A
 * control that appears to govern a page but does not is worse than no control:
 * the reader cannot tell that the numbers in front of them ignore it.
 */
export function routeUsesPeriod(pathname: string): boolean {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  return PERIOD_SCOPED_ROUTES.includes(path);
}
