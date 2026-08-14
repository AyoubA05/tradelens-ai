"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { PasswordStrength } from "@/components/ui/password-strength";
import { cn } from "@/lib/utils";

/**
 * Signup fields from the approved onboarding design.
 *
 * No username field: the internal username is generated opaquely server-side
 * and never shown. Deriving it from the email — the earlier design — would leak
 * the local part of the address wherever the username surfaces.
 *
 * Client validation here mirrors the server rules so the form is pleasant to
 * use. It is not a control: the same policy is enforced independently in the
 * endpoint, and a submission that bypasses the browser is rejected there.
 */

const REFERRAL_OPTIONS = [
  "TikTok",
  "Instagram",
  "YouTube",
  "Google/Search",
  "Friend",
  "Reddit",
  "X/Twitter",
  "Other",
] as const;

const LABEL = "block text-[13px] font-medium text-text";
const FIELD = "mt-1.5 h-10";

export function SignupForm({ inviteRequired }: { inviteRequired: boolean }) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [birthday, setBirthday] = useState("");
  const [referral, setReferral] = useState("");
  const [referralOther, setReferralOther] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [invite, setInvite] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [delivery, setDelivery] = useState<
    "sent" | "unavailable" | "failed"
  >("failed");
  const [state, setState] = useState<
    "idle" | "validating" | "submitting" | "success"
  >("idle");

  const mismatch = confirm.length > 0 && confirm !== password;
  const busy = state === "submitting" || state === "validating";

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    // Double-submit guard. The button is disabled while busy, but a keyboard
    // Enter or a double click can still fire before React re-renders, and a
    // duplicated signup POST is not something to leave to the DOM.
    if (busy || state === "success") return;

    setError(null);
    setState("validating");
    if (password !== confirm) {
      setError("Those passwords do not match.");
      setState("idle");
      return;
    }

    setState("submitting");
    try {
      const response = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password,
          fullName,
          birthday,
          referralSource: referral,
          referralOther: referral === "Other" ? referralOther : null,
          ...(inviteRequired ? { invite } : {}),
        }),
      });
      const payload = (await response.json()) as {
        ok?: boolean;
        error?: string;
        emailDelivery?: "sent" | "unavailable" | "failed";
      };
      if (!response.ok || !payload.ok) {
        setError(payload.error ?? "Something went wrong. Please try again.");
        setState("idle");
        return;
      }
      // Anything unrecognised is treated as "not delivered". The failure that
      // matters is telling someone to check an inbox that has nothing in it.
      setDelivery(payload.emailDelivery === "sent" ? "sent"
        : payload.emailDelivery === "unavailable" ? "unavailable" : "failed");
      setState("success");
    } catch {
      setError("We could not reach the server. Check your connection and try again.");
      setState("idle");
    }
  }

  if (state === "success") {
    return (
      <div className="space-y-3">
        <p className="rounded-lg border border-accent/30 bg-accent-dim px-3 py-2 text-sm text-accent">
          Account created. Verify your email address to open your journal.
        </p>
        {/*
          Reads the delivery state the server reported rather than asserting
          one. Hardcoded copy here said no message had been sent long after
          SMTP started working — the account was fine and the verification mail
          was in the user's inbox, and the page told them to expect neither.
        */}
        <p className="text-[11.5px] leading-relaxed text-muted">
          {delivery === "sent"
            ? "Check your email for the verification link. It expires in 24 hours."
            : delivery === "unavailable"
              ? "Email delivery is not configured in this environment, so no verification message has been sent."
              : "We could not send the verification email just now. You can ask for a new one from the sign-in page."}
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {error && (
        <p
          role="alert"
          className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300"
        >
          {error}
        </p>
      )}

      <div>
        <label htmlFor="fullName" className={LABEL}>Full name</label>
        <Input
          id="fullName" name="fullName" autoComplete="name" required
          value={fullName} onChange={(e) => setFullName(e.target.value)}
          className={FIELD} placeholder="Ayoub Abouelfaid"
        />
      </div>

      <div>
        <label htmlFor="email" className={LABEL}>Email</label>
        <Input
          id="email" name="email" type="email" autoComplete="email" required
          value={email} onChange={(e) => setEmail(e.target.value)}
          className={FIELD} placeholder="you@example.com"
        />
        <p className="mt-1 text-[11.5px] text-muted">
          You will verify this before your journal opens.
        </p>
      </div>

      <div>
        <label htmlFor="birthday" className={LABEL}>Birthday</label>
        <Input
          id="birthday" name="birthday" type="date" required
          value={birthday} onChange={(e) => setBirthday(e.target.value)}
          className={cn(FIELD, "[color-scheme:dark]")}
        />
      </div>

      <div>
        <label htmlFor="referral" className={LABEL}>
          How did you hear about TradeLens?
        </label>
        <select
          id="referral" name="referral" required
          value={referral} onChange={(e) => setReferral(e.target.value)}
          className={cn(
            FIELD,
            "w-full rounded-md border border-border bg-transparent px-3 text-sm text-text",
            "outline-none focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/40",
          )}
        >
          <option value="" disabled className="bg-surface">Select one</option>
          {REFERRAL_OPTIONS.map((option) => (
            <option key={option} value={option} className="bg-surface">{option}</option>
          ))}
        </select>
      </div>

      {/* Rendered only when "Other" is chosen, not hidden with CSS. */}
      {referral === "Other" && (
        <div>
          <label htmlFor="referralOther" className={LABEL}>
            Where, specifically? <span className="font-normal text-muted">(optional)</span>
          </label>
          <Input
            id="referralOther" name="referralOther"
            value={referralOther} onChange={(e) => setReferralOther(e.target.value)}
            className={FIELD} placeholder="A podcast, a Discord, somewhere else"
          />
        </div>
      )}

      <div>
        <label htmlFor="password" className={LABEL}>Password</label>
        <Input
          id="password" name="password" type="password"
          autoComplete="new-password" spellCheck={false} required
          value={password} onChange={(e) => setPassword(e.target.value)}
          className={FIELD} placeholder="Choose a strong password"
        />
        <PasswordStrength value={password} className="mt-3" />
      </div>

      <div>
        <label htmlFor="confirm" className={LABEL}>Confirm password</label>
        <Input
          id="confirm" name="confirm" type="password"
          autoComplete="new-password" spellCheck={false} required
          value={confirm} onChange={(e) => setConfirm(e.target.value)}
          aria-invalid={mismatch || undefined}
          aria-describedby={mismatch ? "confirm-error" : undefined}
          className={FIELD}
        />
        {mismatch && (
          <p id="confirm-error" className="mt-1.5 text-[11.5px] text-red-400">
            Those passwords do not match.
          </p>
        )}
      </div>

      {inviteRequired && (
        <div>
          <label htmlFor="invite" className={LABEL}>Invite code</label>
          <Input
            id="invite" name="invite" required
            value={invite} onChange={(e) => setInvite(e.target.value)}
            className={FIELD} placeholder="TradeLens is in private beta"
          />
        </div>
      )}

      <button
        type="submit"
        disabled={busy}
        aria-busy={busy}
        className={cn(
          "mt-2 h-10 w-full rounded-lg bg-accent text-sm font-medium text-bg",
          "transition-transform duration-200 hover:scale-[1.01] active:scale-[0.99]",
          "focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-accent/40",
          "disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:scale-100",
        )}
      >
        {busy ? "Creating account…" : "Create account"}
      </button>
    </form>
  );
}
