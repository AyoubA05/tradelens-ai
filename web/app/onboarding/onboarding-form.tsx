"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * Personal onboarding. **No Strategy Profile fields** — those live in Streamlit
 * and are gated separately.
 *
 * The page this renders on already authorised the request server-side, so this
 * component never decides who the user is. It sends no user id, and the
 * endpoint would ignore one if it did.
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

export function OnboardingForm() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [birthday, setBirthday] = useState("");
  const [referral, setReferral] = useState("");
  const [referralOther, setReferralOther] = useState("");
  const [state, setState] = useState<"idle" | "validating" | "submitting" | "done">("idle");
  const [error, setError] = useState<string | null>(null);

  const busy = state === "validating" || state === "submitting";

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (busy || state === "done") return; // guards a double submit
    setError(null);
    setState("validating");

    if (fullName.trim().length === 0 || !birthday || !referral) {
      setError("Fill in your name, birthday, and how you found TradeLens.");
      setState("idle");
      return;
    }

    setState("submitting");
    try {
      const response = await fetch("/api/auth/onboarding", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fullName,
          birthday,
          referralSource: referral,
          referralOther: referral === "Other" ? referralOther : null,
        }),
      });
      const payload = (await response.json()) as {
        ok?: boolean;
        error?: string;
        next?: string;
      };
      if (!response.ok || !payload.ok) {
        // 401/403 carry a destination; anything else stays on the form.
        if (payload.next) { router.push(payload.next); return; }
        setError(payload.error ?? "Something went wrong. Please try again.");
        setState("idle");
        return;
      }
      setState("done");
      router.push(payload.next ?? "/continue");
    } catch {
      setError("We could not reach the server. Check your connection and try again.");
      setState("idle");
    }
  }

  if (state === "done") {
    return (
      <p className="rounded-lg border border-accent/30 bg-accent-dim px-3 py-2 text-sm text-accent">
        All set. Taking you through…
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      {error && (
        <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </p>
      )}

      <div>
        <label htmlFor="fullName" className={LABEL}>Full name</label>
        <Input id="fullName" name="fullName" autoComplete="name" required
          value={fullName} onChange={(e) => setFullName(e.target.value)}
          className={FIELD} placeholder="Ayoub Abouelfaid" />
      </div>

      <div>
        <label htmlFor="birthday" className={LABEL}>Birthday</label>
        <Input id="birthday" name="birthday" type="date" required
          value={birthday} onChange={(e) => setBirthday(e.target.value)}
          className={cn(FIELD, "[color-scheme:dark]")} />
      </div>

      <div>
        <label htmlFor="referral" className={LABEL}>How did you hear about TradeLens?</label>
        <select id="referral" name="referral" required
          value={referral} onChange={(e) => setReferral(e.target.value)}
          className={cn(FIELD,
            "w-full rounded-md border border-border bg-transparent px-3 text-sm text-text",
            "outline-none focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/40")}>
          <option value="" disabled className="bg-surface">Select one</option>
          {REFERRAL_OPTIONS.map((o) => (
            <option key={o} value={o} className="bg-surface">{o}</option>
          ))}
        </select>
      </div>

      {/* Rendered only for "Other", not hidden with CSS — the endpoint rejects
          this field when it arrives with any other source. */}
      {referral === "Other" && (
        <div>
          <label htmlFor="referralOther" className={LABEL}>
            Where, specifically? <span className="font-normal text-muted">(optional)</span>
          </label>
          <Input id="referralOther" name="referralOther"
            value={referralOther} onChange={(e) => setReferralOther(e.target.value)}
            className={FIELD} placeholder="A podcast, a Discord, somewhere else" />
        </div>
      )}

      <button type="submit" disabled={busy} aria-busy={busy}
        className={cn(
          "mt-2 h-10 w-full rounded-lg bg-accent text-sm font-medium text-bg",
          "transition-transform duration-200 hover:scale-[1.01] active:scale-[0.99]",
          "focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-accent/40",
          "disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:scale-100",
        )}>
        {busy ? "Saving…" : "Finish setup"}
      </button>

      <p className="text-center text-[11.5px] leading-relaxed text-muted">
        You will set up your trading strategy inside TradeLens, not here.
      </p>
    </form>
  );
}
