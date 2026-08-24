import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";
import { fetchOverview } from "@/lib/app/overview";
import { fetchTrades, DEFAULT_TRADES_LIMIT } from "@/lib/app/trades";
import { periodFromParams } from "@/lib/app/period";
import { parseFilters } from "@/lib/app/trade-filters";
import { FilterBar } from "@/components/app/trades/filter-bar";
import { JournalCalendar } from "@/components/app/trades/journal-calendar";
import { TradesTable } from "@/components/app/trades/trades-table";
import { Pagination } from "@/components/app/trades/pagination";
import { TradeSummaryPanel } from "@/components/app/trades/summary-panel";

export const dynamic = "force-dynamic";

function parseOffset(raw: string | undefined): number {
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

/**
 * The Journal: the Trades list, its filters, and the month calendar.
 *
 * A Server Component, same pattern as the Overview page. It repeats the
 * layout's authorization before fetching rather than trusting the layout to
 * have already gated it — Next.js may render a child concurrently with its
 * parent layout, so a parent's redirect is defence, not a precondition for
 * this page's own data access.
 *
 * Two server-to-server calls, not one: `fetchTrades` gets the filtered,
 * paginated rows for the table, and `fetchOverview` gets the whole-period
 * calendar aggregate `JournalCalendar` needs (see that component for why a
 * paginated page of trades cannot substitute for it). Both run from the same
 * validated session and the same period, and neither result is cached as
 * data the other could silently drift from.
 */
export default async function JournalPage({
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
  const filters = parseFilters(params);
  const offset = parseOffset(params.get("offset") ?? undefined);

  const [tradesPage, overview] = await Promise.all([
    fetchTrades(token, { period, filters, offset }),
    fetchOverview(token, period),
  ]);

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Journal</h1>
      <p className="mt-2 text-muted">Find a trade, work a month, or read one closely.</p>

      <FilterBar />

      <JournalCalendar
        calendar={overview.calendar}
        period={overview.period}
        sample={overview.sample}
        filters={filters}
      />

      <TradeSummaryPanel
        period={period}
        filters={filters}
        tradeCount={tradesPage.total}
      />

      <section className="mt-10">
        <h2 className="font-display text-xl font-bold">Trades</h2>
        <TradesTable trades={tradesPage.trades} />
        <Pagination total={tradesPage.total} limit={tradesPage.limit || DEFAULT_TRADES_LIMIT} offset={tradesPage.offset} />
      </section>
    </div>
  );
}
