"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { ResendForm } from "./resend-form";

/**
 * The verification screen for the link that actually gets emailed.
 *
 * This replaced a six-character-code form that predated the durable token
 * design. The form looked complete and did nothing: it never read the token
 * from the URL, and submitting it always rendered "rejected". Verification
 * worked end to end at the API and was unreachable from the browser.
 *
 * **The confirm button is the point, not a formality.** Mail security scanners
 * fetch every link in a message before the recipient sees it. A page that
 * consumed the token on load would let a scanner burn it, and the real click
 * would always fail — indistinguishable from a broken token. So arriving here
 * only inspects; the consume happens on POST, from a click a human made.
 *
 * Invalid, expired, already-used and superseded all render the same message.
 * Distinguishing them would let someone probe which tokens once existed.
 */

type Phase = "checking" | "ready" | "working" | "verified" | "rejected" | "missing";

const REJECTED_MESSAGE =
  "That link is no longer valid. Request a new one and try again.";

const NOTE = "rounded-lg border px-3 py-2 text-sm";

export function VerifyStates({ token }: { token: string | null }) {
  const [phase, setPhase] = useState<Phase>(token ? "checking" : "missing");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let live = true;
    // Inspect only. This is a GET and it mutates nothing.
    fetch(`/api/auth/verify?token=${encodeURIComponent(token)}`)
      .then((response) => response.json())
      .then((payload: { ok?: boolean }) => {
        if (live) setPhase(payload.ok ? "ready" : "rejected");
      })
      .catch(() => {
        // A network failure is not a rejected token — offer the button anyway
        // rather than telling someone their valid link is dead.
        if (live) setPhase("ready");
      });
    return () => {
      live = false;
    };
  }, [token]);

  async function confirm() {
    if (!token || phase === "working") return;
    setPhase("working");
    setError(null);
    try {
      const response = await fetch("/api/auth/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const payload = (await response.json()) as { ok?: boolean; error?: string };
      if (!response.ok || !payload.ok) {
        setError(payload.error ?? REJECTED_MESSAGE);
        setPhase("rejected");
        return;
      }
      setPhase("verified");
    } catch {
      setError("We could not reach the server. Try again in a moment.");
      setPhase("ready");
    }
  }

  if (phase === "verified") {
    return (
      <div className="space-y-3">
        <p className={`${NOTE} border-accent/30 bg-accent-dim text-accent`}>
          Email verified. You can sign in now.
        </p>
        <Link
          href="/login"
          className="flex h-10 w-full items-center justify-center rounded-lg bg-accent text-sm font-medium text-bg"
        >
          Continue to sign in
        </Link>
      </div>
    );
  }

  /**
   * No token in the URL. Overwhelmingly this is someone who just tried to sign
   * in before confirming their address and was redirected here — an expected
   * waypoint, not a failure, so it is not styled as an error. It used to render
   * a bare red box reading "This page needs the link from your verification
   * email", which stated the problem, offered nothing, and left the only way
   * forward — a new email — sitting behind an endpoint the page never called.
   */
  if (phase === "missing") {
    return (
      <div className="space-y-4">
        <p className={`${NOTE} border-border bg-surface-2 text-text`}>
          Your email address has not been confirmed yet, so your journal is not
          open. Open the link in the verification email — or send yourself a new
          one below.
        </p>
        <ResendForm label="Email address" />
      </div>
    );
  }

  /**
   * A real failure: the link was used, expired, or superseded. The message has
   * always said "request a new one" — now the page it says that on can actually
   * do it, instead of handing someone an instruction and no means.
   */
  if (phase === "rejected") {
    return (
      <div className="space-y-4">
        <p role="alert" className={`${NOTE} border-red-500/30 bg-red-500/10 text-red-300`}>
          {error ?? REJECTED_MESSAGE}
        </p>
        {/* No "Back to sign in" button here: the shell already renders that
            link directly below the card, and two identical exits stacked a few
            pixels apart read as two different destinations. */}
        <ResendForm label="Send a new link to" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <p role="alert" className={`${NOTE} border-red-500/30 bg-red-500/10 text-xs text-red-300`}>
          {error}
        </p>
      )}
      <button
        type="button"
        onClick={confirm}
        disabled={phase !== "ready"}
        className="h-10 w-full rounded-lg bg-accent text-sm font-medium text-bg disabled:opacity-60"
      >
        {phase === "working" ? "Verifying…" : "Verify my email"}
      </button>
      <p className="text-center text-[11.5px] text-muted">
        This link can be used once and expires 24 hours after it was sent.
      </p>
    </div>
  );
}
