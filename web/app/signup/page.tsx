import Link from "next/link";
import { signupMode } from "@/lib/env";
import { AuthShell } from "@/components/auth-shell";
import { SignupForm } from "./signup-form";

/**
 * Rendered per request, not at build time.
 *
 * This page's entire shape is a function of `SIGNUP_MODE`, and by default Next
 * prerenders it: the production build baked the invite field in and served it
 * from the CDN with a one-year `s-maxage`. Flipping the mode in the hosting
 * dashboard changed nothing a visitor could see until the next deploy —
 * "signups are closed" would still render a working signup form, and the only
 * thing stopping those accounts from being created was the endpoint refusing
 * them one by one.
 *
 * Caught by reading the headers of a real production build; a dev server
 * renders everything dynamically and never shows this.
 */
export const dynamic = "force-dynamic";

export default function SignupPage() {
  const mode = signupMode();

  if (mode === "closed") {
    return (
      <AuthShell
        title="Signups are closed"
        intro="TradeLens is not accepting new accounts right now."
        footer={<Link href="/login" className="hover:text-text">Back to sign in</Link>}
      >
        <p className="text-sm text-muted">
          If you already have an account you can still sign in.
        </p>
      </AuthShell>
    );
  }

  // Only the boolean crosses to the client. In "open" mode the invite field is
  // absent from the DOM entirely rather than hidden with CSS, so the page never
  // carries a dead control and opening signups is one environment variable.
  return (
    <AuthShell
      title="Create your journal"
      intro="A few details, then you can start reviewing your trades."
      footer={<>Already have an account? <Link href="/login" className="text-text hover:text-accent">Sign in</Link></>}
    >
      <SignupForm inviteRequired={mode === "invite"} />
    </AuthShell>
  );
}
