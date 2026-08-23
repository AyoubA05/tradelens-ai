"use client";

import { useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { useModalTrap } from "@/lib/app/modal-trap";

/**
 * The Trade Detail delete confirmation.
 *
 * A modal (Phase 1's `useModalTrap`: focus trap, `inert` background, focus
 * restoration), because deleting a trade is irreversible and needs an
 * explicit confirm, not a click that could land by accident.
 *
 * **The 503 branch is the reason this component exists in this shape.** The
 * backend deletes screenshot objects before the row, and a cleanup failure
 * returns 503 with the row still intact — nothing deleted (design decision
 * #6, and the Risks section: "a trader told their screenshots are gone
 * while private images remain in the bucket has been given a false privacy
 * assurance"). This dialog's job is to keep that guarantee visible: on any
 * failure the copy says plainly that nothing was deleted. It never says
 * "trade removed," never reads as partial success, and never auto-retries —
 * retrying is the trader's decision.
 *
 * The 503 has two shapes and they get different copy. A retryable cleanup
 * fault says "you can try again," because a retry genuinely can clear it.
 * An *unresolvable* one — a screenshot row naming a path this owner is not
 * entitled to delete — says the opposite: retrying will not help and this
 * trade needs attention before it can be removed. Offering "try again" for
 * a failure that can never succeed is exactly what the backend's
 * remaining/unresolvable split was written to prevent, so the confirm
 * button is disabled in that branch rather than inviting a retry the
 * copy has just said cannot work.
 *
 * Initial focus lands on Cancel, not Confirm — a destructive action should
 * not be one accidental Enter key away from firing.
 */
export function DeleteTradeDialog({
  open,
  onClose,
  onDeleted,
  deleteTrade,
}: {
  open: boolean;
  onClose: () => void;
  onDeleted: () => void;
  /**
   * Injected so tests can exercise every response without a real fetch.
   * `unresolvable` is meaningful only on a 503; absent means retryable.
   */
  deleteTrade: () => Promise<{ status: number; unresolvable?: boolean }>;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<
    null | "cleanup_failed" | "cleanup_unresolvable" | "generic"
  >(null);

  const close = () => {
    if (deleting) return;
    setError(null);
    onClose();
  };

  useModalTrap({ open, onClose: close, rootRef, panelRef, initialFocusRef: cancelRef });

  if (!open) return null;

  async function handleConfirm() {
    setDeleting(true);
    setError(null);
    try {
      const response = await deleteTrade();
      if (response.status === 204) {
        onDeleted();
        return;
      }
      if (response.status !== 503) {
        setError("generic");
        return;
      }
      setError(response.unresolvable ? "cleanup_unresolvable" : "cleanup_failed");
    } catch {
      setError("generic");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div ref={rootRef} className="fixed inset-0 z-40">
      <button
        type="button"
        aria-label="Dismiss"
        onClick={close}
        className="absolute inset-0 bg-bg/70 backdrop-blur-sm"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Delete this trade"
        tabIndex={-1}
        className="absolute left-1/2 top-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-line bg-surface p-6 focus:outline-none"
      >
        <h2 className="font-display text-base font-semibold text-text">Delete this trade?</h2>
        <p className="mt-2 text-sm text-muted">
          This permanently removes the trade and its screenshots. This cannot be undone.
        </p>

        {error && (
          <div
            role="alert"
            className="mt-4 flex gap-2 rounded-lg border border-negative/30 bg-negative/5 px-3 py-3"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-negative" aria-hidden="true" />
            <p className="text-sm text-text">
              {error === "cleanup_unresolvable"
                ? "Nothing was deleted. One of the stored screenshots cannot be removed from here, and trying again will not change that. Everything is still here, untouched — this one needs our support team to look at it before it can be cleared."
                : error === "cleanup_failed"
                  ? "Nothing was deleted. We could not finish removing the stored screenshots, so the trade and its images are still here, untouched. You can try again."
                  : "Nothing was deleted. Something went wrong. You can try again."}
            </p>
          </div>
        )}

        <div className="mt-5 flex gap-2">
          <button
            type="button"
            onClick={handleConfirm}
            // Disabled once the failure is known to be unresolvable: the copy
            // has just said a retry cannot work, and leaving the button live
            // would contradict it.
            disabled={deleting || error === "cleanup_unresolvable"}
            className="rounded-lg bg-negative px-4 py-2 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-negative/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {deleting ? "Deleting…" : "Delete trade"}
          </button>
          <button
            ref={cancelRef}
            type="button"
            onClick={close}
            disabled={deleting}
            className="rounded-lg border border-line-strong px-4 py-2 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
