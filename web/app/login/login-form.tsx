"use client";

import { useState } from "react";
import { SignInCard } from "@/components/ui/sign-in-card-2";

/**
 * Scaffold. `/api/auth/login` does not exist yet, so submitting reports that
 * plainly instead of simulating a successful sign-in — a scaffold that fakes
 * authentication is the one behaviour that would make this page dangerous to
 * demo.
 */
export function LoginForm({ signupEnabled }: { signupEnabled: boolean }) {
  const [error, setError] = useState<string | null>(null);

  async function onSubmit() {
    setError(
      "Sign-in is not connected yet — the authentication endpoint ships in the next increment.",
    );
  }

  return (
    <SignInCard onSubmit={onSubmit} error={error} signupEnabled={signupEnabled} />
  );
}
