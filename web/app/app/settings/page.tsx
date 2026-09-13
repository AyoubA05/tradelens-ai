import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  appLayoutRedirect,
  authenticateSessionToken,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";
import { fetchSettings, type SettingsResponse } from "@/lib/app/settings";
import { DangerZone } from "@/components/app/settings/danger-zone";
import { DataSection } from "@/components/app/settings/data-section";
import { PreferencesSection } from "@/components/app/settings/preferences-section";
import { ProfileSection } from "@/components/app/settings/profile-section";
import { ErrorState } from "@/components/app/states/error-state";

export const dynamic = "force-dynamic";

/**
 * Settings — the quietest page in the product.
 *
 * A Server Component with client islands for the parts that write. It repeats
 * the layout's authorization before fetching, like every page here.
 *
 * A failed load renders an error and NO controls: the Danger Zone and the data
 * tools must never be offered over a picture of the account that did not load.
 */
export default async function SettingsPage() {
  const token = sessionTokenFromCookieHeader((await headers()).get("cookie"));
  if (!token) redirect("/login");
  const user = await authenticateSessionToken(token);
  if (!user) redirect("/login");
  const redirectTo = appLayoutRedirect(user);
  if (redirectTo) redirect(redirectTo);

  let data: SettingsResponse | null = null;
  try {
    data = await fetchSettings(token);
  } catch {
    // Not surfaced: an upstream message can carry internal detail, and none of
    // it is actionable to a trader.
    data = null;
  }

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="font-display text-3xl font-bold">Settings</h1>
      <p className="mt-2 text-muted">
        Preferences, your data, and your account. Nothing here changes how your trades are analysed.
      </p>

      {data === null ? (
        <div className="mt-8">
          <ErrorState
            title="Settings did not load"
            description="This is a loading failure. Nothing about your account or your data has changed."
          />
        </div>
      ) : (
        <>
          <ProfileSection account={data.account} resetEmailConfigured={data.reset_email_configured} />
          <PreferencesSection timezone={data.timezone} ai={data.ai} demoMode={data.demo_mode} />
          <DataSection
            key={`${data.data.trade_count}:${data.data.sample_count}`}
            data={data.data}
            cost={data.cost}
          />
          <DangerZone />
        </>
      )}
    </div>
  );
}
