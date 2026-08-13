import { redirect } from "next/navigation";
import { headers } from "next/headers";

import { AuthShell } from "@/components/auth-shell";
import { SESSION_COOKIE } from "@/lib/auth/login";
import { authenticateSessionToken, nextDestinationFor } from "@/lib/auth/session";
import { handoffEligibility } from "@/lib/auth/handoff";

export const dynamic = "force-dynamic";

/**
 * The continuation boundary.
 *
 * **Rendering this page issues nothing.** The handoff is minted only by the
 * POST behind the button below. A GET-triggered issuer would mint credentials
 * on browser prefetch, on crawler visits, and on every accidental refresh —
 * and because only one handoff per user stays redeemable, a prefetch would
 * silently invalidate the token the user is about to use.
 *
 * Authorization happens here, server-side, before anything renders.
 */
export default async function ContinuePage() {
  const cookieHeader = (await headers()).get("cookie") ?? "";
  const match = cookieHeader.match(new RegExp(`(?:^|;\\s*)${SESSION_COOKIE}=([^;]+)`));
  const user = await authenticateSessionToken(match ? decodeURIComponent(match[1]!) : null);

  if (!user) redirect("/login");

  const eligibility = handoffEligibility(user);
  if (!eligibility.eligible) redirect(nextDestinationFor(user));

  return (
    <AuthShell
      title="You're all set"
      intro="Your account is ready. Open your journal to start reviewing trades."
    >
      {/* A plain form POST: no client-side fetch, so it works without
          JavaScript, and the browser follows the 303 to the app itself. */}
      <form method="POST" action="/api/auth/handoff" className="space-y-4">
        <button
          type="submit"
          className="h-10 w-full rounded-lg bg-accent text-sm font-medium text-bg transition-transform duration-200 hover:scale-[1.01] active:scale-[0.99] focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-accent/40"
        >
          Continue to your journal
        </button>
      </form>

      <p className="mt-4 text-[11.5px] leading-relaxed text-muted">
        This opens the TradeLens app in a new step. The link is single-use and
        valid for two minutes.
      </p>
    </AuthShell>
  );
}
