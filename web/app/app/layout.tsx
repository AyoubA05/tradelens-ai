import { redirect } from "next/navigation";
import { headers } from "next/headers";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app/app-shell";
import { Sidebar } from "@/components/app/sidebar";
import { TopBar } from "@/components/app/top-bar";
import { BottomNav } from "@/components/app/bottom-nav";
import { PartnerDrawer } from "@/components/app/partner-drawer";
import {
  authenticateSessionToken,
  emailGatePassed,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";

// The shell reflects one account's session, so it must never be cached.
export const dynamic = "force-dynamic";

/**
 * The authenticated frame.
 *
 * Authorisation happens here, server-side, before any child renders — the same
 * gate the continuation page applies, so a deep link into /app cannot bypass
 * what /continue enforces.
 *
 * No API call is made. Phase 1 has no data to fetch, so the FastAPI boundary is
 * not touched: identity comes from the session the website already validated.
 */
export default async function AppLayout({ children }: { children: ReactNode }) {
  const cookieHeader = (await headers()).get("cookie") ?? "";
  const user = await authenticateSessionToken(sessionTokenFromCookieHeader(cookieHeader));

  if (!user) redirect("/login");
  if (!emailGatePassed(user)) redirect("/verify-email");
  if (!user.onboardingCompleted) redirect("/onboarding");

  return (
    <AppShell
      sidebar={<Sidebar />}
      top={<TopBar />}
      drawer={<PartnerDrawer />}
      bottomNav={<BottomNav />}
    >
      {children}
    </AppShell>
  );
}
