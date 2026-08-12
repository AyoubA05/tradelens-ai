import { redirect } from "next/navigation";
import { headers } from "next/headers";

import { AuthShell } from "@/components/auth-shell";
import { authenticateSessionToken, emailGatePassed, nextDestinationFor } from "@/lib/auth/session";
import { SESSION_COOKIE } from "@/lib/auth/login";
import { OnboardingForm } from "./onboarding-form";

export const dynamic = "force-dynamic";

/**
 * Server component. Authorization happens here, before anything renders — a
 * client-side redirect would leave the page reachable by anyone who ignores it.
 */
export default async function OnboardingPage() {
  const cookieHeader = (await headers()).get("cookie") ?? "";
  const match = cookieHeader.match(new RegExp(`(?:^|;\\s*)${SESSION_COOKIE}=([^;]+)`));
  const user = await authenticateSessionToken(match ? decodeURIComponent(match[1]!) : null);

  // Logged out, expired, revoked, or inactive all land here.
  if (!user) redirect("/login");
  if (!emailGatePassed(user)) redirect("/verify-email");
  // Already done: sent onward rather than shown a form that would refuse to save.
  if (user.onboardingCompleted) redirect(nextDestinationFor(user));

  return (
    <AuthShell
      title="Tell us about you"
      intro="A few details to finish setting up your account. You can start journalling straight after."
    >
      <OnboardingForm />
    </AuthShell>
  );
}
