"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";

/**
 * The response is identical whether or not the address is registered, so this
 * form cannot be used to discover who has an account. That is why the success
 * state is shown for every submission rather than only for real ones.
 */
const NEUTRAL =
  "If that address has a TradeLens account, a reset code is on its way. The code expires in 30 minutes.";

export function ForgotForm() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  if (submitted) {
    return (
      <div className="space-y-3">
        <p className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-sm text-text">
          {NEUTRAL}
        </p>
        <p className="text-[11.5px] text-muted">
          Not connected yet — no email was actually sent. The endpoint ships in
          the next increment.
        </p>
      </div>
    );
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => { e.preventDefault(); setSubmitted(true); }}
    >
      <div>
        <label htmlFor="email" className="block text-[13px] font-medium text-text">
          Email address
        </label>
        <Input
          id="email" name="email" type="email" autoComplete="email" required
          value={email} onChange={(e) => setEmail(e.target.value)}
          className="mt-1.5 h-10" placeholder="you@example.com"
        />
      </div>
      <button type="submit" className="h-10 w-full rounded-lg bg-accent text-sm font-medium text-bg">
        Send reset code
      </button>
    </form>
  );
}
