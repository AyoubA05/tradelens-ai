import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";
import { fetchAnalytics, type AnalyticsResponse } from "@/lib/app/analytics";
import { periodFromParams } from "@/lib/app/period";
import {
  ANALYTICS_LENSES,
  lensFromParams,
  parseAnalyticsFilters,
} from "@/lib/app/analytics-filters";
import { AnalyticsFilterBar } from "@/components/app/analytics/filter-bar";
import { MetricValueText } from "@/components/app/analytics/metric-value";
import { LensTabs } from "@/components/app/analytics/lens-tabs";
import { PerformanceLens } from "@/components/app/analytics/performance-lens";
import { RiskLens } from "@/components/app/analytics/risk-lens";
import { TimingLens } from "@/components/app/analytics/timing-lens";
import { SetupsLens } from "@/components/app/analytics/setups-lens";
import { EmptyState } from "@/components/app/states/empty-state";
import { ErrorState } from "@/components/app/states/error-state";

export const dynamic = "force-dynamic";

/**
 * Analytics: four lenses over one period, one filtered sample, one fetch.
 *
 * A Server Component, the same shape as Overview and Journal. It repeats the
 * layout's authorization before fetching rather than trusting the layout to
 * have gated it — Next.js may render a child concurrently with its parent, so
 * the parent's redirect is defence, not a precondition for this page's data
 * access.
 *
 * The page renders NO date control. `/app/analytics` is in
 * `PERIOD_SCOPED_ROUTES`, so the global period lens is already on screen as
 * chrome; a second window here would leave a reader unable to tell which
 * number belongs to which. The prior period behind the comparison is derived
 * server-side and printed with its actual dates, so it is legible without a
 * control that could change it.
 *
 * Three outcomes, deliberately distinct. A failed fetch renders an error, not
 * zeros and not an empty period: "we could not load this" and "you logged
 * nothing" are different claims and a trader would act differently on each,
 * so neither may ever be shown in place of the other.
 */
export default async function AnalyticsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const rawParams = Object.entries(await searchParams).flatMap(([k, v]) =>
    typeof v === "string" ? [[k, v] as [string, string]] : [],
  );
  const params = new URLSearchParams(rawParams);

  const token = sessionTokenFromCookieHeader((await headers()).get("cookie"));
  if (!token) redirect("/login");
  const user = await authenticateSessionToken(token);
  if (!user) redirect("/login");
  const redirectTo = appLayoutRedirect(user);
  if (redirectTo) redirect(redirectTo);

  const period = periodFromParams(params);
  const filters = parseAnalyticsFilters(params);
  const lens = lensFromParams(params);

  let analytics: AnalyticsResponse | null = null;
  let failed = false;
  try {
    analytics = await fetchAnalytics(token, {
      from: period.from,
      to: period.to,
      ...filters,
    });
  } catch {
    // The reason is deliberately not surfaced: an upstream message can carry
    // internal hostnames, and none of it is actionable to a trader.
    failed = true;
  }

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Analytics</h1>
      <p className="mt-2 text-muted">One question at a time, with the evidence behind the answer.</p>

      <AnalyticsFilterBar filters={filters} />

      {failed || !analytics ? (
        <div className="mt-8">
          <ErrorState
            title="Analytics did not load"
            description={`This is a loading failure, not a reading of your trades for ${period.from} to ${period.to}.`}
          />
        </div>
      ) : analytics.performance.total_trades === 0 ? (
        <div className="mt-8" data-testid="analytics-empty">
          <EmptyState
            title="No trades in this period"
            description={`Nothing is logged between ${period.from} and ${period.to}, so there is nothing to measure. Widen the period, or clear the filters, to read a larger slice of your record.`}
          />
        </div>
      ) : (
        <>
          <LensTabs active={lens} search={params.toString()} />

          {/*
            The dates AND the figures. Printing only the window left the
            sentence's promise unkept: four deltas were fetched, typed and
            never shown. The window is derived rather than chosen, so its
            dates have to be legible here — there is no second date control
            to read them from.
          */}
          <div data-testid="analytics-comparison" className="mt-4 text-xs text-muted">
            <p>
              {`Measured over ${analytics.period.from} → ${analytics.period.to}, compared with the equally long period before it, ${analytics.comparison.period.from} → ${analytics.comparison.period.to}.`}
            </p>
            <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1">
              {(
                [
                  ["net_pnl", "Net P&L", "money"],
                  ["win_rate", "Win rate", "percent"],
                  ["profit_factor", "Profit factor", "ratio"],
                  ["consistency", "Consistency", "number"],
                ] as const
              ).map(([field, label, kind]) => (
                <div key={field} className="flex items-baseline gap-1.5">
                  <dt>{label}</dt>
                  <dd
                    data-testid={`comparison-${field}`}
                    className="font-mono text-text"
                  >
                    {/*
                      Through MetricValueText like every other figure: an
                      empty prior window must read as a missing comparison,
                      never as a 0.00 delta claiming performance held steady
                      against a period that does not exist.
                    */}
                    <MetricValueText value={analytics.comparison[field]} kind={kind} />
                  </dd>
                </div>
              ))}
            </dl>
          </div>

          {ANALYTICS_LENSES.filter((entry) => entry.id === lens).map((entry) => (
            <section
              key={entry.id}
              data-testid={`lens-${entry.id}`}
              aria-label={`${entry.label} lens`}
              className="mt-6 rounded-xl border border-line bg-surface p-6"
            >
              <h2 className="font-display text-xl font-bold">{entry.label}</h2>
              {entry.id === "performance" ? (
                <PerformanceLens
                  performance={analytics.performance}
                  discipline={analytics.discipline}
                />
              ) : entry.id === "risk" ? (
                <RiskLens risk={analytics.risk} />
              ) : entry.id === "timing" ? (
                <TimingLens timing={analytics.timing} />
              ) : (
                <SetupsLens setups={analytics.setups} />
              )}
            </section>
          ))}

        </>
      )}
    </div>
  );
}
