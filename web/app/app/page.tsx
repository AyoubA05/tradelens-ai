import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";
import { fetchOverview } from "@/lib/app/overview";
import { periodFromParams } from "@/lib/app/period";
import { OverviewSections } from "@/components/app/overview/sections";

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

  const data = await fetchOverview(token, period);

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Overview</h1>
      <p className="mt-2 text-muted">Where the week stands, and what deserves review next.</p>
      <OverviewSections data={data} />
    </div>
  );
}
