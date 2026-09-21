import Link from "next/link";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";
import { fetchOverview } from "@/lib/app/overview";
import { periodFromParams, periodToParams } from "@/lib/app/period";
import { OverviewSections } from "@/components/app/overview/sections";
import { AssetFilter } from "@/components/app/overview/asset-filter";

/** A bounded, display-safe label; the service still performs exact matching. */
const INSTRUMENT_LABEL = /^[^\u0000-\u001F\u007F<>]{1,128}$/u;

function scopedAsset(params: URLSearchParams): string | undefined {
  const raw = params.get("asset");
  if (raw === null) return undefined;
  const value = raw.trim();
  return INSTRUMENT_LABEL.test(value) ? value : undefined;
}

export const dynamic = "force-dynamic";

/**
 * The Overview.
 *
 * A Server Component: one server-to-server call, rendered once. The page
 * repeats the layout's authorization before fetching because Next.js may
 * render a child concurrently with its parent layout; layout control flow is
 * not a safe prerequisite for a data access.
 */
export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = new URLSearchParams(
    Object.entries(await searchParams).flatMap(([k, v]) =>
      typeof v === "string" ? [[k, v] as [string, string]] : [],
    ),
  );
  const period = periodFromParams(params);
  const token = sessionTokenFromCookieHeader((await headers()).get("cookie"));
  if (!token) redirect("/login");
  const user = await authenticateSessionToken(token);
  if (!user) redirect("/login");
  const redirectTo = appLayoutRedirect(user);
  if (redirectTo) redirect(redirectTo);

  // First run: a trader who has not yet written a playbook (or said they
  // have none) is sent to write one before their first review. Read from the
  // account row the session resolved — never from the URL, which a trader
  // could edit to skip the step.
  //
  // Only this page redirects, matching Streamlit's `strategy_gate.py`, where
  // only the dashboard does. It is deliberately NOT part of
  // `appLayoutRedirect`: that function also gates every relay, so putting it
  // there would refuse the very save and skip calls that complete first run,
  // and would redirect `/app/strategy` to itself.
  if (!user.strategyProfileCompleted) redirect("/app/strategy");

  const data = await fetchOverview(token, period, scopedAsset(params));

  // An instrument with no trades in this period is a real view of a real
  // account, not an empty account. Rendering the sections here would draw a
  // strip of zeros that reads as a flat month, so the page says what is true
  // and offers the way back out.
  const emptyScope = data.filters.asset !== null && data.kpi.trades === 0;
  const unscopedHref = (() => {
    const params = periodToParams(period);
    return `/app?${params.toString()}`;
  })();

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Overview</h1>
      <p className="mt-2 text-muted">Where the week stands, and what deserves review next.</p>
      <AssetFilter asset={data.filters.asset} availableAssets={data.filters.available_assets} />
      {emptyScope ? (
        <div className="mt-8 rounded-lg border border-line bg-surface p-6">
          <p className="font-display text-lg font-semibold text-text">
            No trades for {data.filters.asset}
          </p>
          <p className="mt-2 text-sm text-muted">
            Nothing was logged for this instrument in the selected period. The rest of the
            account is unaffected.
          </p>
          <Link
            href={unscopedHref}
            className="mt-4 inline-flex min-h-[44px] items-center rounded-md border border-line px-4 text-sm text-text transition-colors duration-150 ease-tl hover:border-line-strong"
          >
            Show all assets
          </Link>
        </div>
      ) : (
        <OverviewSections data={data} />
      )}
    </div>
  );
}
