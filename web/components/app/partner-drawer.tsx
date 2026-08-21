"use client";

import { useEffect, useRef, useState } from "react";
import { MessageSquareText, X } from "lucide-react";

import { useModalTrap } from "@/lib/app/modal-trap";

/**
 * The AI partner drawer — frame only.
 *
 * Phase 1 ships the shell: how it opens, how it traps focus, how it closes, and
 * what it says it is for. The conversation itself arrives with the phase that
 * has something to talk about.
 *
 * Open state lives in a module-level store rather than a context because the
 * launcher sits in the top bar and the drawer is mounted by the layout, and
 * threading a provider between them buys nothing at this size.
 */
let listeners: Array<(open: boolean) => void> = [];
let isOpen = false;

function setOpen(next: boolean) {
  isOpen = next;
  for (const listener of listeners) listener(next);
}

function useDrawerOpen() {
  const [open, setLocal] = useState(isOpen);
  useEffect(() => {
    listeners.push(setLocal);
    return () => {
      listeners = listeners.filter((l) => l !== setLocal);
      // No mounted drawer means no open drawer. Without this the module-level
      // flag outlives the component, so an earlier test can leave the next one
      // starting from an open drawer it never opened.
      if (listeners.length === 0) isOpen = false;
    };
  }, []);
  return open;
}

export function PartnerLauncher() {
  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      className="flex items-center gap-2 rounded-md border border-line bg-surface px-3 py-1.5 text-xs text-muted transition-colors duration-150 ease-tl hover:border-line-strong hover:text-text"
    >
      <MessageSquareText className="h-3.5 w-3.5" aria-hidden="true" />
      Ask about a trade
    </button>
  );
}

export function PartnerDrawer() {
  const open = useDrawerOpen();
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useModalTrap({
    open,
    onClose: () => setOpen(false),
    rootRef,
    panelRef,
    initialFocusRef: closeRef,
  });

  if (!open) return null;

  return (
    <div ref={rootRef} className="fixed inset-0 z-40">
      <button
        type="button"
        aria-label="Dismiss AI Partner"
        onClick={() => setOpen(false)}
        className="absolute inset-0 bg-bg/70 backdrop-blur-sm"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="AI Partner"
        tabIndex={-1}
        className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-line bg-surface focus:outline-none"
      >
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <h2 className="font-display text-sm font-semibold">AI Partner</h2>
            <p className="mt-0.5 text-xs text-muted">
              Ask about trades you have already logged.
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close AI Partner"
            className="rounded-md p-1.5 text-muted transition-colors duration-150 ease-tl hover:bg-surface-2 hover:text-text"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <div className="flex flex-1 items-center justify-center px-6 text-center">
          <p className="max-w-xs text-sm text-muted">
            The partner reads your journal and answers questions about what already
            happened. It arrives with the review features.
          </p>
        </div>
      </div>
    </div>
  );
}
