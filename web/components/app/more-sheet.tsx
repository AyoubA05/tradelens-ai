"use client";

import { useEffect } from "react";
import Link from "next/link";

import { APP_DESTINATIONS, PRIMARY_ACTION } from "@/lib/app/navigation";

/**
 * Phone overflow.
 *
 * Holds the destinations a trader reaches occasionally — reading analytics or
 * editing a strategy is desk work — plus logging a trade, which has no room in
 * a five-slot bar but is the reason the app exists.
 */
export function MoreSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const overflow = APP_DESTINATIONS.filter((d) => !d.phonePriority);

  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <button
        type="button"
        aria-label="Close menu"
        onClick={onClose}
        className="absolute inset-0 bg-bg/70 backdrop-blur-sm"
      />
      <div className="absolute inset-x-0 bottom-0 rounded-t-2xl border-t border-line bg-surface p-4 pb-8">
        <ul className="space-y-1">
          {overflow.map((destination) => {
            const Icon = destination.icon;
            return (
              <li key={destination.href}>
                <Link
                  href={destination.href}
                  onClick={onClose}
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
