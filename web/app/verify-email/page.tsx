import Link from "next/link";
import { AuthShell } from "@/components/auth-shell";
import { VerifyStates } from "./verify-states";

/**
 * All five verification outcomes are represented. Invalid, expired and
 * already-used deliberately share one message: distinguishing them would let
 * someone probe which codes had once existed.
 */
export default function VerifyEmailPage() {
  return (
    <AuthShell
      title="Verify your email"
      intro="We sent a six-character code to your address. Enter it to open your journal."
      footer={<Link href="/login" className="hover:text-text">Back to sign in</Link>}
    >
      <VerifyStates />
    </AuthShell>
  );
}
