/**
 * Profile — who you are signed in as.
 *
 * Decision S1: the email is shown, never edited here. On the website the email
 * is the sign-in identity and its verification gates the app, so changing it
 * needs a verify-the-new-address-before-switching flow of its own.
 */
export function ProfileSection({
  account,
  resetEmailConfigured,
}: {
  account: { username: string; email: string | null; email_verified: boolean };
  resetEmailConfigured: boolean;
}) {
  return (
    <section aria-labelledby="settings-profile" className="mt-10">
      <h2 id="settings-profile" className="font-display text-xl font-bold">
        Profile
      </h2>
      <p className="mt-1 text-sm text-muted">Your account and how you sign in.</p>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-[10rem_1fr]">
        <dt className="text-muted">Signed in as</dt>
        <dd className="text-text">{account.username || "—"}</dd>
        <dt className="text-muted">Email</dt>
        <dd className="text-text">
          {account.email ?? "No email on this account"}
          {account.email ? (
            <span className="ml-2 text-xs text-muted">
              {account.email_verified ? "Verified" : "Not verified yet"}
            </span>
          ) : null}
        </dd>
      </dl>
      {!resetEmailConfigured ? (
        <p className="mt-3 text-xs text-muted">
          Outgoing email is not configured on this deployment yet, so reset messages cannot be
          delivered.
        </p>
      ) : null}
    </section>
  );
}
