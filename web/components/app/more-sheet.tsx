"use client";

import { useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { X } from "lucide-react";

import { APP_DESTINATIONS, PRIMARY_ACTION, isActiveDestination } from "@/lib/app/navigation";
import { useModalTrap } from "@/lib/app/modal-trap";

/**
 * Phone overflow.
 *
 * Holds the destinations a trader reaches occasionally — reading analytics or
 * editing a strategy is desk work — plus logging a trade, which has no room in
 * a five-slot bar but is the reason the app exists.
 *
 * A full-screen overlay is a modal, and this one now carries the same
 * contract the AI partner drawer does — role="dialog", trapped focus, initial
 * focus on open, focus restored on close, background siblings inert — via the
 * shared `useModalTrap` hook rather than its own copy of that logic.
 */
export function MoreSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useModalTrap({
    open,
    onClose,
    rootRef,
    panelRef,
    initialFocusRef: closeRef,
  });

  if (!open) return null;

  const overflow = APP_DESTINATIONS.filter((d) => !d.phonePriority);

  return (
    <div ref={rootRef} className="fixed inset-0 z-40 lg:hidden">
      <button
        type="button"
        aria-label="Dismiss menu"
        onClick={onClose}
        className="absolute inset-0 bg-bg/70 backdrop-blur-sm"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="More"
        tabIndex={-1}
        className="absolute inset-x-0 bottom-0 rounded-t-2xl border-t border-line bg-surface p-4 pb-8 focus:outline-none"
      >
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-display text-sm font-semibold">More</h2>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close menu"
            className="rounded-md p-1.5 text-muted transition-colors duration-150 ease-tl hover:bg-surface-2 hover:text-text"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <ul className="space-y-1">
          {overflow.map((destination) => {
            const active = isActiveDestination(pathname, destination.href);
            const Icon = destination.icon;
            return (
              <li key={destination.href}>
                <Link
                  href={destination.href}
                  onClick={onClose}
                  aria-current={active ? "page" : undefined}
                  className="flex items-center gap-3 rounded-lg px-3 py-3 text-sm text-text hover:bg-surface-2"
                >
                  <Icon className="h-4 w-4 text-muted" aria-hidden="true" />
                  {destination.label}
                </Link>
              </li>
            );
          })}
          <li className="pt-2">
            <Link
              href={PRIMARY_ACTION.href}
              onClick={onClose}
              aria-current={
                isActiveDestination(pathname, PRIMARY_ACTION.href) ? "page" : undefined
              }
              className="flex items-center justify-center rounded-lg bg-accent px-4 py-3 text-sm font-semibold text-bg"
            >
              {PRIMARY_ACTION.label}
            </Link>
          </li>
        </ul>
      </div>
    </div>
  );
}
