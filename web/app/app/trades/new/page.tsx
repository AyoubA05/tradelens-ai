import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";
import { NewTradeForm } from "@/components/app/new-trade/new-trade-form";

export const dynamic = "force-dynamic";

/**
 * New Trade: one dense form, never a wizard (design decision #7).
 *
 * A Server Component, same pattern as Trade Detail and every other
 * protected page — it repeats the layout's authorization itself before
 * rendering, because Next.js may render a child concurrently with its
 * parent layout (the Codex Phase 2 finding global-constraints.md pins).
 * A parent's redirect is defence, not a precondition for this page.
 *
 * This page itself makes no backend call — the form's client-side submit
 * goes through `/api/trades/create`, which re-derives and re-checks this
 * same authorization before it will call FastAPI (see that route). The
 * check here exists so an ineligible account never sees the form at all,
 * not because the relay depends on it.
 */
export default async function NewTradePage() {
  const token = sessionTokenFromCookieHeader((await headers()).get("cookie"));
  if (!token) redirect("/login");
  const user = await authenticateSessionToken(token);
  if (!user) redirect("/login");
  const redirectTo = appLayoutRedirect(user);
  if (redirectTo) redirect(redirectTo);

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="font-display text-3xl font-bold text-text">Log completed trade</h1>
      <p className="mt-2 text-muted">
        A post-trade record for review — everything is visible at once, and every field but
        asset, date and time is optional.
      </p>
      <div className="mt-8">
        <NewTradeForm />
      </div>
    </div>
  );
}
