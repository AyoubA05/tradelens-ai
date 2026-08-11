"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { PasswordStrength } from "@/components/ui/password-strength";

/** The strength meter appears here as well as on signup — any new password. */
export function ResetForm() {
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const mismatch = confirm.length > 0 && confirm !== password;

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        setNotice("Password reset is not connected yet — the endpoint ships in the next increment.");
      }}
    >
      {notice && (
        <p role="status" className="rounded-lg border border-accent/30 bg-accent-dim px-3 py-2 text-xs text-accent">
          {notice}
        </p>
      )}
      <div>
        <label htmlFor="code" className="block text-[13px] font-medium text-text">Reset code</label>
        <Input id="code" name="code" required value={code} onChange={(e) => setCode(e.target.value)}
          className="mt-1.5 h-10 font-mono tracking-[0.3em]" placeholder="ABC123" />
      </div>
      <div>
        <label htmlFor="password" className="block text-[13px] font-medium text-text">New password</label>
        <Input id="password" name="password" type="password" autoComplete="new-password"
          spellCheck={false} required value={password} onChange={(e) => setPassword(e.target.value)}
          className="mt-1.5 h-10" />
        <PasswordStrength value={password} className="mt-3" />
      </div>
      <div>
        <label htmlFor="confirm" className="block text-[13px] font-medium text-text">Confirm new password</label>
        <Input id="confirm" name="confirm" type="password" autoComplete="new-password"
          spellCheck={false} required value={confirm} onChange={(e) => setConfirm(e.target.value)}
          aria-invalid={mismatch || undefined} className="mt-1.5 h-10" />
        {mismatch && <p className="mt-1.5 text-[11.5px] text-red-400">Those passwords do not match.</p>}
      </div>
      <button type="submit" className="h-10 w-full rounded-lg bg-accent text-sm font-medium text-bg">
        Set new password
      </button>
    </form>
  );
}
