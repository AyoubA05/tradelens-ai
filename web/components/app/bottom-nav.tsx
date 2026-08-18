"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MoreHorizontal } from "lucide-react";

import { APP_DESTINATIONS, isActiveDestination } from "@/lib/app/navigation";
import { MoreSheet } from "@/components/app/more-sheet";

/**
 * Phone navigation.
 *
 * Four destinations and More. Five slots is the most that leaves a 44px target
 * at 375px, and a sixth would make every one of them harder to hit rather than
 * making the app feel more complete.
 */
export function BottomNav() {
  const pathname = usePathname();
  const [moreOpen, setMoreOpen] = useState(false);
  const primary = APP_DESTINATIONS.filter((d) => d.phonePriority);

  return (
    <>
      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 backdrop-blur"
      >
        <ul className="grid grid-cols-5">
          {primary.map((destination) => {
            const active = isActiveDestination(pathname, destination.href);
            const Icon = destination.icon;
            return (
              <li key={destination.href}>
                <Link
                  href={destination.href}
                  aria-current={active ? "page" : undefined}
                  className={[
                    "flex min-h-[3.25rem] flex-col items-center justify-center gap-1 px-1 py-2 text-[10px]",
                    active ? "text-accent" : "text-muted",
                  ].join(" ")}
                >
                  <Icon className="h-5 w-5" aria-hidden="true" />
                  {destination.label}
                </Link>
              </li>
            );
          })}
          <li>
            <button
              type="button"
              onClick={() => setMoreOpen(true)}
              className="flex min-h-[3.25rem] w-full flex-col items-center justify-center gap-1 px-1 py-2 text-[10px] text-muted"
            >
              <MoreHorizontal className="h-5 w-5" aria-hidden="true" />
              More
            </button>
          </li>
        </ul>
      </nav>
      <MoreSheet open={moreOpen} onClose={() => setMoreOpen(false)} />
    </>
  );
}
