import Link from "next/link";
import { signupMode } from "@/lib/env";
import { AuthShell } from "@/components/auth-shell";
import { SignupForm } from "./signup-form";

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
