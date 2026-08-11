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
  const [notice, setNotice] = useState<string | null>(null);

  const mismatch = confirm.length > 0 && confirm !== password;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    // Scaffold: no endpoint yet. Say so rather than simulate an account.
    setNotice(
      "Account creation is not connected yet — the signup endpoint ships in the next increment.",
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {notice && (
        <p
          role="status"
          className="rounded-lg border border-accent/30 bg-accent-dim px-3 py-2 text-xs text-accent"
        >
          {notice}
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
        className={cn(
          "mt-2 h-10 w-full rounded-lg bg-accent text-sm font-medium text-bg",
          "transition-transform duration-200 hover:scale-[1.01] active:scale-[0.99]",
          "focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-accent/40",
        )}
      >
        Create account
      </button>
    </form>
  );
}
