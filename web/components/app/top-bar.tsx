import { Suspense } from "react";

import { PeriodLens } from "@/components/app/period-lens";
import { PartnerLauncher } from "@/components/app/partner-drawer";

/**
 * The top bar carries two things and refuses the rest: the window under review,
 * and the way into the AI partner. Page titles live in the page, where the
 * content that explains them lives.
 *
 * The lens is wrapped in Suspense because it reads search params, which opts
 * its subtree into client-side rendering; without the boundary that would opt
 * the whole route out of static rendering.
 */
export function TopBar() {
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-end gap-3 border-b border-line bg-bg/80 px-4 backdrop-blur sm:px-6 lg:px-8">
      <Suspense fallback={<div className="h-7 w-52 rounded-md bg-surface" />}>
        <PeriodLens />
      </Suspense>
      <PartnerLauncher />
    </header>
  );
}
