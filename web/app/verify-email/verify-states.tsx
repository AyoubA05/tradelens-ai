"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";

export type VerifyState =
  | "entry"
  | "verified"
  | "rejected"      // invalid, expired, and already-used collapse to this
  | "unconfigured"; // mail was never sent, and we say so

const REJECTED_MESSAGE =
  "That code is no longer valid. Request a new one and try again.";

export function VerifyStates() {
  const [state, setState] = useState<VerifyState>("entry");
  const [code, setCode] = useState("");

  if (state === "verified") {
    return (
      <p className="rounded-lg border border-accent/30 bg-accent-dim px-3 py-2 text-sm text-accent">
        Email verified. Continuing to your journal.
      </p>
    );
  }

  if (state === "unconfigured") {
    return (
      <p role="alert" className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-300">
        We could not send that email. This is a problem on our side — no message
        was delivered. Please try again shortly.
      </p>
    );
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        setState("rejected");
      }}
    >
      {state === "rejected" && (
        <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {REJECTED_MESSAGE}
        </p>
      )}
      <div>
        <label htmlFor="code" className="block text-[13px] font-medium text-text">
          Verification code
        </label>
        <Input
          id="code" name="code" inputMode="text" autoComplete="one-time-code"
          value={code} onChange={(e) => setCode(e.target.value)}
          className="mt-1.5 h-10 font-mono tracking-[0.3em]" placeholder="ABC123"
        />
      </div>
      <button type="submit" className="h-10 w-full rounded-lg bg-accent text-sm font-medium text-bg">
        Verify email
      </button>
      <p className="text-center text-[11.5px] text-muted">
        Verification is not connected yet — the endpoint ships in the next increment.
      </p>
    </form>
  );
}
