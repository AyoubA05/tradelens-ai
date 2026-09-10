"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/**
 * The first-run step, shown when the ACCOUNT says so (the page passes the
 * server's `first_run`; nothing here reads the URL).
 *
 * The second exit is not a courtesy. Plenty of traders start journaling
 * because they have no written rules yet, and a first step they cannot
 * honestly complete is a wall in front of the product. It completes the step
 * without inventing a playbook.
 */
export function FirstRunBanner() {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  async function skip() {
    setPending(true);
    setFailed(false);
    try {
      const response = await fetch("/api/strategy/skip", { method: "POST" });
      if (!response.ok) throw new Error(String(response.status));
      router.push("/app");
    } catch {
      setFailed(true);
      setPending(false);
    }
  }

  return (
    <section
      data-testid="first-run-banner"
      aria-label="Before your first review"
      className="mt-6 rounded-xl border border-accent/40 bg-accent/5 p-5"
    >
      <p className="text-sm text-text">
        Write down how you trade before your first review. Every AI review reads these rules —
        you can change them whenever they change.
      </p>
      <button
        type="button"
        onClick={skip}
        disabled={pending}
        className="mt-4 min-h-[44px] rounded-lg border border-line-strong px-4 py-2 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2 disabled:opacity-60"
      >
        I don&apos;t have a defined strategy yet
      </button>
      {failed ? (
        <p role="alert" className="mt-2 text-sm text-negative">
          Could not record that. Try again.
        </p>
      ) : null}
    </section>
  );
}
