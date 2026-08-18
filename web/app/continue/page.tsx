import { redirect } from "next/navigation";
import { headers } from "next/headers";

import { AuthShell } from "@/components/auth-shell";
import { AutoSubmit } from "@/components/auto-submit";
import {
  authenticateSessionToken,
  continuePageRedirect,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";
import { handoffEligibility, hasEnteredAppBefore } from "@/lib/auth/handoff";

export const dynamic = "force-dynamic";

/**
 * The continuation boundary.
 *
 * **Rendering this page issues nothing.** The handoff is minted only by the
 * POST behind the form below. A GET-triggered issuer would mint credentials
 * on browser prefetch, on crawler visits, and on every accidental refresh —
 * and because only one handoff per user stays redeemable, a prefetch would
 * silently invalidate the token the user is about to use.
 *
 * Authorization happens here, server-side, before anything renders.
 *
 * **Two faces, one form.** The "You're all set" card is a first-run moment: it
 * is worth saying once, to someone who has just built an account and has never
 * seen the app. Shown on every sign-in it stops being a welcome and becomes a
 * toll gate between a returning trader and their journal. So a returning user
 * gets the same form, submitted for them on mount, and sees only a brief
 * "Opening your journal". The POST-only rule is untouched in both cases — see
 * `AutoSubmit` for why that has to be a client effect rather than a redirect.
 *
 * Without JavaScript the auto-submit never runs and the button is simply
 * there to be pressed, which is the same page the first-run user gets.
 */
export default async function ContinuePage() {
  const cookieHeader = (await headers()).get("cookie") ?? "";
  const user = await authenticateSessionToken(sessionTokenFromCookieHeader(cookieHeader));

  if (!user) redirect("/login");

  // A migrated account never mints a Streamlit handoff, but it still has to
  // clear the same email/onboarding gates as every other account first —
  // `continuePageRedirect` enforces that ordering, not this call site.
  const eligibility = handoffEligibility(user);
  const redirectTo = continuePageRedirect(user, eligibility.eligible);
  if (redirectTo) redirect(redirectTo);

  // Presentation only. Whether this account may cross was decided above; this
  // decides nothing but which words it reads on the way.
  const returning = await hasEnteredAppBefore(user);

  return (
    <AuthShell
      centered
      tilt={!returning}
      title={returning ? "Opening your journal" : "You're all set"}
      intro={
        returning
          ? "One moment — taking you through to TradeLens."
          : "Your account is ready. Open your journal to start reviewing trades."
      }
    >
      {/* A plain form POST: no client-side fetch, so it works without
          JavaScript, and the browser follows the 303 to the app itself. */}
      <form id="handoff-form" method="POST" action="/api/auth/handoff" className="space-y-4">
        <button
          type="submit"
          className="h-10 w-full rounded-lg bg-accent text-sm font-medium text-bg transition-transform duration-200 hover:scale-[1.01] active:scale-[0.99] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-accent/40"
        >
          {returning ? "Continue" : "Continue to your journal"}
        </button>
      </form>

      {returning && <AutoSubmit formId="handoff-form" />}

      <p className="mt-4 text-center text-[11.5px] leading-relaxed text-muted">
        {returning
          ? "If nothing happens, use the button above."
          : "This opens the TradeLens app in a new step. The link is single-use and valid for two minutes."}
      </p>
    </AuthShell>
  );
}
