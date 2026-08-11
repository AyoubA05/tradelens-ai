import Link from "next/link";
import { AuthShell } from "@/components/auth-shell";
import { ResetForm } from "./reset-form";

export default function ResetPasswordPage() {
  return (
    <AuthShell
      title="Choose a new password"
      intro="Enter the code from your email and set a new password."
      footer={<Link href="/login" className="hover:text-text">Back to sign in</Link>}
    >
      <ResetForm />
    </AuthShell>
  );
}
