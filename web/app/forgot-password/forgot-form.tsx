"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";

/**
 * The success state is shown for every submission, because the endpoint returns
 * one neutral answer for every outcome. Rendering anything conditional on
 * whether the address exists would reintroduce, in the UI, the enumeration
 * oracle the API is careful to avoid.
 */
export function ForgotForm() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "submitting" | "done" | "error">("idle");
  const [message, setMessage] = useState("");

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (state === "submitting") return;
    setState("submitting");
    try {
      const response = await fetch("/api/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const payload = (await response.json()) as { ok?: boolean; message?: string };
      setMessage(payload.message ?? "");
      setState(payload.ok ? "done" : "error");
    } catch {
      setMessage("We could not reach the server. Check your connection and try again.");
      setState("error");
    }
  }

  if (state === "done") {
    return (
      <div className="space-y-3">
        <p className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-text">{message}</p>
        <p className="text-[11.5px] leading-relaxed text-muted">
          Email delivery is not configured in this environment, so no message has
          actually been sent yet.
        </p>
      </div>
    );
  }

  return (
    <form className="space-y-4" onSubmit={onSubmit}>
      {state === "error" && (
        <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {message}
        </p>
      )}
      <div>
        <label htmlFor="email" className="block text-[13px] font-medium text-text">Email address</label>
        <Input id="email" name="email" type="email" autoComplete="email" required
          value={email} onChange={(e) => setEmail(e.target.value)}
          className="mt-1.5 h-10" placeholder="you@example.com" />
      </div>
      <button type="submit" disabled={state === "submitting"} aria-busy={state === "submitting"}
        className="h-10 w-full rounded-lg bg-accent text-sm font-medium text-bg disabled:opacity-60">
        {state === "submitting" ? "Sending…" : "Send reset link"}
      </button>
    </form>
  );
}
