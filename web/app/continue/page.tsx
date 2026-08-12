import Link from "next/link";
import { AuthShell } from "@/components/auth-shell";

/**
 * Temporary authenticated continuation state.
 *
 * Step 9 replaces this with the real website to Streamlit handoff. Until then
 * it says plainly that the journal is not connected, because a page implying
 * the user had entered the app would be a lie the rest of the flow then has to
 * work around.
 *
 * No session semantics are invented here: the website cookie session already
 * established at login is the only session, and this page neither reads nor
 * issues any other credential.
 */
export default function ContinuePage() {
  return (
    <AuthShell
      title="You're signed in"
      intro="Your TradeLens account is ready."
      footer={<Link href="/login" className="hover:text-text">Back to sign in</Link>}
    >
      <div className="space-y-3">
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
          The journal handoff is not connected yet. Signing in works, but this
          build cannot open the TradeLens app for you.
        </p>
        <p className="text-[12.5px] leading-relaxed text-muted">
          Until it is wired up, use the existing sign-in on the app itself.
        </p>
      </div>
    </AuthShell>
  );
}
