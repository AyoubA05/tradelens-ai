"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";

/**
 * The way out of a verification screen with no usable token.
 *
 * It asks for the address rather than inheriting one. Arriving here from a
 * refused sign-in carries no identity — and the alternative, passing the
 * address through the redirect, would put someone's email in a URL, in browser
 * history, and in any log along the way, to save one field.
 *
 * The success state is shown for every submission, because the endpoint answers
 * identically whether the address is unknown, already verified, rate limited or
 * genuinely resent. Branching the UI on the outcome would rebuild, in the
 * browser, the account-enumeration oracle the API is careful not to be.
 */
export function ResendForm({ label }: { label: string }) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "submitting" | "done" | "error">("idle");
  const [message, setMessage] = useState("");
  const [mailConfigured, setMailConfigured] = useState<boolean | null>(null);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (state === "submitting") return;
    setState("submitting");
    try {
      const response = await fetch("/api/auth/resend-verification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const payload = (await response.json()) as {
        ok?: boolean;
        message?: string;
        mailConfigured?: boolean;
      };
      setMessage(payload.message ?? "");
      setMailConfigured(payload.mailConfigured ?? null);
      setState(payload.ok ? "done" : "error");
    } catch {
      setMessage("We could not reach the server. Check your connection and try again.");
      setState("error");
    }
  }

  if (state === "done") {
    return (
      <div className="space-y-3">
        <p className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-text">
          {message}
        </p>
        {/* Environment-wide, so saying it discloses nothing about the address
            that was submitted — and without it this page would claim a delivery
            that never happened. */}
        {mailConfigured === false && (
          <p className="text-[11.5px] leading-relaxed text-muted">
            Email delivery is not configured in this environment, so no message
            has actually been sent.
          </p>
        )}
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
        <label htmlFor="resend-email" className="block text-[13px] font-medium text-text">
          {label}
        </label>
        <Input
          id="resend-email" name="email" type="email" autoComplete="email" required
          value={email} onChange={(e) => setEmail(e.target.value)}
          className="mt-1.5 h-10" placeholder="you@example.com"
        />
      </div>
      <button
        type="submit"
        disabled={state === "submitting"}
        aria-busy={state === "submitting"}
        className="h-10 w-full rounded-lg bg-accent text-sm font-medium text-bg disabled:opacity-60"
      >
        {state === "submitting" ? "Sending…" : "Send a new link"}
      </button>
    </form>
  );
}
