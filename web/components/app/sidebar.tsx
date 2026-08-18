"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LineChart } from "lucide-react";

import {
  APP_DESTINATIONS,
  PRIMARY_ACTION,
  isActiveDestination,
} from "@/lib/app/navigation";

/**
 * The desktop rail.
 *
 * A client component only because it reads the current path to mark the active
 * destination. Everything it renders is static.
 *
 * The active state is an edge bar plus a surface change, and `aria-current`
 * carries the same fact to assistive technology — a colour difference alone
 * tells a screen reader nothing.
 */
export function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="sticky top-0 flex h-dvh flex-col border-r border-line bg-surface">
      <div className="px-5 py-6">
        <Link href="/app" className="flex items-center gap-2.5">
          <LineChart className="h-5 w-5 text-accent" aria-hidden="true" />
          <span className="font-display text-base font-bold tracking-tight">TradeLens AI</span>
        </Link>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          Post-trade journal
        </p>
      </div>

      <div className="px-3 pb-4">
        <Link
          href={PRIMARY_ACTION.href}
          className="flex w-full items-center justify-center rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-bg transition-colors duration-150 ease-tl hover:bg-accent/90"
        >
          {PRIMARY_ACTION.label}
        </Link>
      </div>

      <nav aria-label="Sections" className="flex-1 px-3">
        <ul className="space-y-0.5">
          {APP_DESTINATIONS.map((destination) => {
            const active = isActiveDestination(pathname, destination.href);
            const Icon = destination.icon;
            return (
              <li key={destination.href}>
                <Link
                  href={destination.href}
                  aria-current={active ? "page" : undefined}
                  className={[
                    "relative flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors duration-150 ease-tl",
                    active
                      ? "bg-surface-2 font-medium text-text"
                      : "text-muted hover:bg-surface-2/60 hover:text-text",
                  ].join(" ")}
                >
                  {active && (
                    <span
                      aria-hidden="true"
                      className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r bg-accent"
                    />
                  )}
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  {destination.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
