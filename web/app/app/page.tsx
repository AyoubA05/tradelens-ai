import { headers } from "next/headers";

import { sessionTokenFromCookieHeader } from "@/lib/auth/session";
import { fetchOverview } from "@/lib/app/overview";
import { periodFromParams } from "@/lib/app/period";
import { OverviewSections } from "@/components/app/overview/sections";

export const dynamic = "force-dynamic";

/**
 * The Overview.
 *
 * A Server Component: one server-to-server call, rendered once. The layout has
 * already established that this request has a session and that the account is
 * opted in, so the token is read here only to forward it.
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
  const data = await fetchOverview(token ?? "", period);

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Overview</h1>
      <p className="mt-2 text-muted">Where the week stands, and what deserves review next.</p>
      <OverviewSections data={data} />
    </div>
  );
}
