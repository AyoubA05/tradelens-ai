import Link from "next/link";

import { ANALYTICS_LENSES, type LensId } from "@/lib/app/analytics-filters";

/**
 * The four-lens selector.
 *
 * Real links, not buttons over client state: the active lens belongs in the
 * URL beside the period and the filters, so a lens is linkable, survives a
 * refresh and comes back with the back button. Links are keyboard reachable
 * and announce themselves without any roving-tabindex machinery.
 *
 * Each tab carries its label as text and the active one carries
 * `aria-current="page"` plus a weight and an underline — the colour is
 * reinforcement, never the only signal.
 *
 * There is no date control here, and there must never be one: the period is
 * chrome (`lib/app/period.ts`), and a second window on one screen leaves the
 * reader unable to tell which number belongs to which.
 */
export function LensTabs({ active, search }: { active: LensId; search: string }) {
  function hrefFor(lens: LensId): string {
    const params = new URLSearchParams(search);
    params.set("lens", lens);
    return `/app/analytics?${params.toString()}`;
  }

  return (
    <nav aria-label="Analytics lenses" className="mt-6 border-b border-line">
      <ul className="-mb-px flex flex-wrap gap-1">
        {ANALYTICS_LENSES.map((lens) => {
          const isActive = lens.id === active;
          return (
            <li key={lens.id}>
              <Link
                href={hrefFor(lens.id)}
                aria-current={isActive ? "page" : undefined}
                className={`inline-flex items-center rounded-t-lg border-b-2 px-3 py-2 text-sm transition-colors duration-150 ease-tl ${
                  isActive
                    ? "border-accent font-semibold text-text"
                    : "border-transparent font-medium text-muted hover:text-text"
                }`}
              >
                {lens.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
