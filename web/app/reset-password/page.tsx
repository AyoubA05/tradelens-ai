import Link from "next/link";
import { AuthShell } from "@/components/auth-shell";
import { ResetForm } from "./reset-form";

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  return (
    <AuthShell
      title="Choose a new password"
      intro="Pick something long. You will sign in again afterwards."
      footer={<Link href="/login" className="hover:text-text">Back to sign in</Link>}
    >
      <ResetForm token={token ?? ""} />
    </AuthShell>
  );
}
