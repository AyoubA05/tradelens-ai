import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";
import { fetchStrategy, type StrategyResponse } from "@/lib/app/strategy";
import { ErrorState } from "@/components/app/states/error-state";
import { FirstRunBanner } from "@/components/app/strategy/first-run-banner";
import { InsightSuggestions } from "@/components/app/strategy/insight-suggestions";
import { PlaybookEditor } from "@/components/app/strategy/playbook-editor";
import { PlaybookSummary } from "@/components/app/strategy/playbook-summary";

export const dynamic = "force-dynamic";

/**
 * Strategy Profile — the trader's playbook, and the rulebook every AI review
 * reads.
 *
 * A Server Component with client islands for the parts that write. It
 * repeats the layout's authorization before fetching, like every page here.
 * It does NOT gate on the first-run flag: this is where first run is
 * completed, and gating it would loop.
 *
 * A failed load renders an error and NO editor. The save is a full
 * replacement, so an empty editor shown in place of a playbook that failed
 * to load — and then saved — would wipe the trader's rules.
 */
export default async function StrategyPage() {
  const token = sessionTokenFromCookieHeader((await headers()).get("cookie"));
  if (!token) redirect("/login");
  const user = await authenticateSessionToken(token);
  if (!user) redirect("/login");
  const redirectTo = appLayoutRedirect(user);
  if (redirectTo) redirect(redirectTo);

  let data: StrategyResponse | null = null;
  try {
    data = await fetchStrategy(token);
  } catch {
    // Not surfaced: an upstream message can carry internal detail, and none
    // of it is actionable to a trader.
    data = null;
  }

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="font-display text-3xl font-bold">Strategy Profile</h1>
      <p className="mt-2 text-muted">Your own rules, written down.</p>

      {data === null ? (
        <div className="mt-8">
          <ErrorState
            title="The playbook did not load"
            description="This is a loading failure. Nothing about your saved rules has changed."
          />
        </div>
      ) : (
        <>
          {data.first_run ? <FirstRunBanner /> : null}
          <PlaybookSummary data={data} />
          <InsightSuggestions data={data} />
          <PlaybookEditor data={data} />
        </>
      )}
    </div>
  );
}
