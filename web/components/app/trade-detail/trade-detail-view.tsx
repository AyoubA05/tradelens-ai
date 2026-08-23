"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft } from "lucide-react";

import { EditTradeForm } from "@/components/app/trade-detail/edit-trade-form";
import { DeleteTradeDialog } from "@/components/app/trade-detail/delete-trade-dialog";
import { TradeReadView } from "@/components/app/trade-detail/trade-read-view";
import { ScreenshotGallery } from "@/components/app/trade-detail/screenshot-gallery";
import type { TradeDetail } from "@/lib/app/trades";

/**
 * The Trade Detail page's Client Component shell.
 *
 * `trade` is the Server Component's fetch — the source of truth. This
 * component holds only UI state (is the edit form open, is the delete
 * dialog open); it never keeps its own copy of the trade that could drift
 * from what the server last returned. After a save or a conflict reload,
 * `router.refresh()` re-runs the page's Server Component and this component
 * receives the fresh `trade` as a prop, the same way the URL-is-state-of-
 * record pages in this app (Journal's filters, its pagination) already
 * re-fetch through Next rather than patching local state by hand.
 */
export function TradeDetailView({ trade }: { trade: TradeDetail }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <Link
          href="/app/journal"
          className="inline-flex items-center gap-1.5 text-sm text-muted transition-colors duration-150 ease-tl hover:text-text"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Back to journal
        </Link>
        {!editing && (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded-lg border border-line-strong px-3 py-1.5 text-sm text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
            >
              Edit
            </button>
            <button
              type="button"
              onClick={() => setDeleteOpen(true)}
              className="rounded-lg border border-negative/30 px-3 py-1.5 text-sm text-negative transition-colors duration-150 ease-tl hover:bg-negative/5"
            >
              Delete
            </button>
          </div>
        )}
      </div>

      <div className="mt-4">
        {editing ? (
          <EditTradeForm
            trade={trade}
            onCancel={() => setEditing(false)}
            onSaved={() => {
              setEditing(false);
              router.refresh();
            }}
            onConflictReload={() => {
              setEditing(false);
              router.refresh();
            }}
          />
        ) : (
          <>
            <TradeReadView trade={trade} />
            <ScreenshotGallery screenshots={trade.screenshots} asset={trade.asset} />
          </>
        )}
      </div>

      <DeleteTradeDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onDeleted={() => router.push("/app/journal")}
        deleteTrade={async () => {
          const response = await fetch(`/api/trades/${trade.id}`, { method: "DELETE" });
          // Only the 503 body says anything the status cannot: whether the
          // cleanup failure is one a retry can ever clear. An unreadable
          // body falls back to retryable — the weaker claim — and nothing
          // here ever reports a failure as a deletion.
          if (response.status !== 503) return { status: response.status };
          const body = (await response.json().catch(() => null)) as {
            unresolvable?: boolean;
          } | null;
          return { status: 503, unresolvable: Boolean(body?.unresolvable) };
        }}
      />
    </div>
  );
}
