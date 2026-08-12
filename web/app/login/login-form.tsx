"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { SignInCard } from "@/components/ui/sign-in-card-2";

/**
 * Wired to POST /api/auth/login.
 *
 * The only failure the form distinguishes is "verify your email", and only
 * because that response is reachable exclusively after the correct password —
 * so it discloses nothing the caller did not already have. Everything else,
 * including a disabled account, shows one generic message.
 */
export function LoginForm({ signupEnabled }: { signupEnabled: boolean }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(identifier: string, password: string) {
    setError(null);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identifier, password }),
      });
      const payload = (await response.json()) as {
        ok?: boolean;
        error?: string;
        next?: string;
        verificationRequired?: boolean;
      };

      if (!response.ok || !payload.ok) {
        setError(payload.error ?? "Something went wrong. Please try again.");
        if (payload.verificationRequired) router.push("/verify-email");
        return;
      }
      // The session cookie is already set by the response; the handoff into
      // Streamlit is a later step and is not invented here.
      router.push(payload.next ?? "/onboarding");
    } catch {
      setError("We could not reach the server. Check your connection and try again.");
    }
  }

  return (
    <SignInCard onSubmit={onSubmit} error={error} signupEnabled={signupEnabled} />
  );
}
