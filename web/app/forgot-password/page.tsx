import Link from "next/link";
import { AuthShell } from "@/components/auth-shell";
import { ForgotForm } from "./forgot-form";

export default function ForgotPasswordPage() {
  return (
    <AuthShell
      title="Reset your password"
      intro="Enter the email on your account and we will send a reset code."
      footer={<Link href="/login" className="hover:text-text">Back to sign in</Link>}
    >
      <ForgotForm />
    </AuthShell>
  );
}
