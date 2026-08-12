"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { PasswordStrength } from "@/components/ui/password-strength";

/**
 * The GET inspection runs on mount and only renders the form; it never consumes
 * the token. Consumption happens on submit. Expired, already-used, superseded
 * and invalid all render the same rejection, so the page cannot be used to probe
 * which tokens once existed.
 */
export function ResetForm({ token }: { token: string }) {
  const router = useRouter();
  const [state, setState] = useState<"inspecting" | "ready" | "rejected" | "submitting" | "done">("inspecting");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!token) { setState("rejected"); return; }
      try {
        const r = await fetch(`/api/auth/reset-password?token=${encodeURIComponent(token)}`);
        if (!cancelled) setState(r.ok ? "ready" : "rejected");
      } catch {
        if (!cancelled) setState("rejected");
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  if (state === "inspecting") return <p className="text-sm text-muted">Checking that link…</p>;

  if (state === "rejected") {
    return (
      <div className="space-y-3">
        <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          That reset link is no longer valid. Request a new one and try again.
        </p>
        <a href="/forgot-password" className="inline-block text-xs text-accent hover:underline">
          Request a new reset link
        </a>
      </div>
    );
  }

  if (state === "done") {
    return (
      <p className="rounded-lg border border-accent/30 bg-accent-dim px-3 py-2 text-sm text-accent">
        Password changed. Sign in with your new password.
      </p>
    );
  }

  const mismatch = confirm.length > 0 && confirm !== password;
  const busy = state === "submitting";

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    if (password !== confirm) { setError("Those passwords do not match."); return; }
    setState("submitting");
    try {
      const response = await fetch("/api/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      const payload = (await response.json()) as { ok?: boolean; error?: string };
      if (!response.ok || !payload.ok) {
        setError(payload.error ?? "Something went wrong. Please try again.");
        setState("ready");
        return;
      }
      setState("done");
      // Not auto-signed-in: every session was just revoked on purpose.
      setTimeout(() => router.push("/login"), 1500);
    } catch {
      setError("We could not reach the server. Check your connection and try again.");
      setState("ready");
    }
  }

  return (
    <form className="space-y-4" onSubmit={onSubmit} noValidate>
      {error && (
        <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </p>
      )}
      <div>
        <label htmlFor="password" className="block text-[13px] font-medium text-text">New password</label>
        <Input id="password" type="password" autoComplete="new-password" spellCheck={false} required
          value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1.5 h-10" />
        <PasswordStrength value={password} className="mt-3" />
      </div>
      <div>
        <label htmlFor="confirm" className="block text-[13px] font-medium text-text">Confirm new password</label>
        <Input id="confirm" type="password" autoComplete="new-password" spellCheck={false} required
          value={confirm} onChange={(e) => setConfirm(e.target.value)}
          aria-invalid={mismatch || undefined} className="mt-1.5 h-10" />
        {mismatch && <p className="mt-1.5 text-[11.5px] text-red-400">Those passwords do not match.</p>}
      </div>
      <button type="submit" disabled={busy} aria-busy={busy}
        className="h-10 w-full rounded-lg bg-accent text-sm font-medium text-bg disabled:opacity-60">
        {busy ? "Changing password…" : "Change password"}
      </button>
    </form>
  );
}
