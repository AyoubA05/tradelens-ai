"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { SettingStatus } from "@/components/app/settings/setting-status";

/**
 * Danger Zone — the only bordered region on the page.
 *
 * Both actions are permanent and each asks for its confirmation typed in full
 * (decision S9: the phrase only, for account deletion). The request carries
 * the constant phrase, never the raw typed text, and the server compares it
 * exactly.
 *
 * A blocked screenshot cleanup deleted NOTHING, and the copy says so — and
 * says whether trying again can help. Never a success message over it.
 */

const GENERIC_FAILURE = "That did not work. Try again.";
const BLOCKED_RETRYABLE = "Some screenshots could not be removed, so nothing was deleted. Try again.";
const BLOCKED_UNRESOLVABLE =
  "Some screenshots could not be removed, so nothing was deleted. Contact support — trying again will not fix this.";

type Status = { tone: "ok" | "fail"; text: string } | null;

async function failureText(response: Response): Promise<string> {
  const body = (await response.json().catch(() => ({}))) as { detail?: unknown; unresolvable?: unknown };
  if (response.status === 503 && body.detail === "screenshot_cleanup_failed") {
    return body.unresolvable === true ? BLOCKED_UNRESOLVABLE : BLOCKED_RETRYABLE;
  }
  return GENERIC_FAILURE;
}

export function DangerZone({
  onAccountDeleted = (next: string) => window.location.assign(next),
}: {
  onAccountDeleted?: (next: string) => void;
}) {
  const [open, setOpen] = useState<"trades" | "account" | null>(null);
  const [typedTrades, setTypedTrades] = useState("");
  const [typedAccount, setTypedAccount] = useState("");
  const [tradesStatus, setTradesStatus] = useState<Status>(null);
  const [accountStatus, setAccountStatus] = useState<Status>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const router = useRouter();

  async function deleteTrades() {
    if (typedTrades !== "DELETE" || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setTradesStatus(null);
    try {
      const response = await fetch("/api/settings/delete-trades", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ confirm: "DELETE" }),
      });
      if (response.ok) {
        const body = (await response.json()) as { deleted: number };
        setTradesStatus({ tone: "ok", text: `Deleted ${body.deleted} trades.` });
        setTypedTrades("");
        // The data section's counts come from the server; re-read them, so the
        // page never keeps offering to export or clear trades that are gone.
        router.refresh();
        return;
      }
      setTradesStatus({ tone: "fail", text: await failureText(response) });
    } catch {
      setTradesStatus({ tone: "fail", text: GENERIC_FAILURE });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function deleteAccount() {
    if (typedAccount.trim() !== "DELETE MY ACCOUNT" || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setAccountStatus(null);
    try {
      const response = await fetch("/api/settings/delete-account", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ confirm: "DELETE MY ACCOUNT" }),
      });
      if (response.ok) {
        const body = (await response.json()) as { ok?: boolean; next?: string };
        if (body.ok === true && typeof body.next === "string" && body.next.startsWith("/")) {
          onAccountDeleted(body.next);
          return;
        }
      }
      setAccountStatus({ tone: "fail", text: response.ok ? GENERIC_FAILURE : await failureText(response) });
    } catch {
      setAccountStatus({ tone: "fail", text: GENERIC_FAILURE });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const toggleClass =
    "flex min-h-[44px] w-full items-center justify-between text-left text-sm font-semibold text-text";
  const inputClass =
    "mt-1 min-h-[44px] w-full rounded-lg border border-line bg-bg px-3 text-sm text-text focus:border-line-strong focus:outline-none";
  const destructiveClass =
    "mt-3 min-h-[44px] rounded-lg border border-negative/40 px-4 py-1.5 text-sm text-negative transition-colors duration-150 ease-tl hover:bg-negative/5 disabled:opacity-50";

  return (
    <section aria-labelledby="settings-danger" className="mt-12 rounded-xl border border-line-strong p-5">
      <h2 id="settings-danger" className="font-display text-xl font-bold text-negative">
        Danger Zone
      </h2>
      <p className="mt-1 text-sm text-muted">
        Both of these are permanent, take effect immediately, and have no backup. Each one asks you to
        type its confirmation in full.
      </p>

      <div className="mt-4 border-t border-line pt-3">
        <button
          type="button"
          aria-expanded={open === "trades"}
          onClick={() => setOpen(open === "trades" ? null : "trades")}
          className={toggleClass}
        >
          Delete all trades
        </button>
        {open === "trades" ? (
          <div className="mt-2">
            <p className="text-sm text-muted">
              Permanently deletes every trade you have logged, sample and real, and the AI summaries, weekly
              recaps and daily debriefs made from them. Your account, playbook and settings are kept. Export your trades first if you
              want to keep them.
            </p>
            <label htmlFor="danger-trades-confirm" className="mt-3 block text-sm text-text">
              Type DELETE to confirm
            </label>
            <input
              id="danger-trades-confirm"
              value={typedTrades}
              onChange={(event) => setTypedTrades(event.target.value)}
              autoComplete="off"
              className={inputClass}
            />
            <button
              type="button"
              onClick={() => void deleteTrades()}
              disabled={busy || typedTrades !== "DELETE"}
              className={destructiveClass}
            >
              Delete all trades permanently
            </button>
            {tradesStatus ? <SettingStatus tone={tradesStatus.tone} text={tradesStatus.text} /> : null}
          </div>
        ) : null}
      </div>

      <div className="mt-4 border-t border-line pt-3">
        <button
          type="button"
          aria-expanded={open === "account"}
          onClick={() => setOpen(open === "account" ? null : "account")}
          className={toggleClass}
        >
          Delete my account
        </button>
        {open === "account" ? (
          <div className="mt-2">
            <p className="text-sm text-muted">
              Permanently deletes your account and everything in it: every trade, note and psychology entry,
              your Strategy Profile, your saved reviews and AI analyses, your settings, and every chart image
              you uploaded. It cannot be undone and there is no backup. Export your trades first if you want
              to keep them.
            </p>
            <p className="mt-2 text-sm text-muted">
              Anonymous records of what AI features cost to run are kept for accounting, with no link to you
              or your trades.
            </p>
            <label htmlFor="danger-account-confirm" className="mt-3 block text-sm text-text">
              Type DELETE MY ACCOUNT to confirm
            </label>
            <input
              id="danger-account-confirm"
              value={typedAccount}
              onChange={(event) => setTypedAccount(event.target.value)}
              autoComplete="off"
              className={inputClass}
            />
            <button
              type="button"
              onClick={() => void deleteAccount()}
              disabled={busy || typedAccount.trim() !== "DELETE MY ACCOUNT"}
              className={destructiveClass}
            >
              Delete my account permanently
            </button>
            {accountStatus ? <SettingStatus tone={accountStatus.tone} text={accountStatus.text} /> : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
