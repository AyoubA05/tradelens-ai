import { headers } from "next/headers";
import { notFound, redirect } from "next/navigation";

import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";
import { fetchTradeDetail } from "@/lib/app/trades";
import { ApiError } from "@/lib/api/client";
import { TradeDetailView } from "@/components/app/trade-detail/trade-detail-view";

export const dynamic = "force-dynamic";

/**
 * Trade Detail: one trade, read, edited inline, or deleted.
 *
 * A Server Component, the same pattern as the Overview and Journal pages —
 * it repeats the layout's authorization itself before fetching, because
 * Next.js may render a child concurrently with its parent layout (the
 * Codex Phase 2 finding this rule exists to guard against). A parent's
 * redirect is defence, not a precondition for this page's own data access.
 *
 * Deliberately not on `PERIOD_SCOPED_ROUTES` (design decision #3): a single
 * trade has one date, and a period selector here would be a second control
 * claiming the same temporal scope the trade's own date already answers.
 *
 * A trade that is not the caller's returns 404, byte-identical to a trade
 * that never existed (Task A3) — `notFound()` renders the route's own
 * `not-found.tsx`, never a caught-and-reshaped "you don't own this"
 * message, which would itself be the leak this property exists to prevent.
 */
export default async function TradeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  // A strict digit test rather than bare `Number()`, matching the relay's
  // `parseTradeId`: `Number` also accepts `"1e3"` (1000), `"0x10"` (16),
  // `"0b11"` (3) and `" 1"`, so several distinct URLs would resolve to one
  // trade, and a 21-digit id would be re-serialised into the upstream path
  // as `"1e+21"`. 16 digits stays inside the exact-integer range.
  const tradeId = /^[1-9]\d{0,15}$/.test(id) ? Number(id) : null;

  const token = sessionTokenFromCookieHeader((await headers()).get("cookie"));
  if (!token) redirect("/login");
  const user = await authenticateSessionToken(token);
  if (!user) redirect("/login");
  const redirectTo = appLayoutRedirect(user);
  if (redirectTo) redirect(redirectTo);

  // An id that is not a plain positive integer can never be a trade —
  // treated exactly like a 404 from the API rather than reaching the API at
  // all, and rendering the same not-found page either way.
  if (tradeId === null) notFound();

  let trade;
  try {
    trade = await fetchTradeDetail(token, tradeId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  return (
    <div className="mx-auto max-w-6xl">
      <TradeDetailView trade={trade} />
    </div>
  );
}
