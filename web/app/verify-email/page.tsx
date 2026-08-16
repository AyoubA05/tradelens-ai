import Link from "next/link";
import { AuthShell } from "@/components/auth-shell";
import { VerifyStates } from "./verify-states";

/**
 * Reached from the link in the verification email, which carries `?token=`.
 *
 * The token is read here and handed to the client component as a prop rather
 * than being pulled from `window.location`, so the server-rendered page and the
 * interactive one always agree on which credential is in play.
 *
 * Never cached and never prerendered: the page reflects one-time state, and a
 * cached copy on a shared proxy would show one person's outcome to another.
 */
export const dynamic = "force-dynamic";

export default async function VerifyEmailPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string | string[] }>;
}) {
  const params = await searchParams;
  const raw = params.token;
  // A repeated parameter is a malformed link, not a choice to make on the
  // user's behalf about which of two tokens they meant.
  const token = typeof raw === "string" ? raw : null;

  return (
    <AuthShell
      title="Verify your email"
      // Without a token there is no "this address" to confirm and nothing to
      // click, so the promise of one click belongs only on the page that
      // actually has a link to act on.
      intro={
        token
          ? "One click confirms this address and opens your journal."
          : "Confirming your address is the last step before your journal opens."
      }
      footer={<Link href="/login" className="hover:text-text">Back to sign in</Link>}
    >
      <VerifyStates token={token} />
    </AuthShell>
  );
}
