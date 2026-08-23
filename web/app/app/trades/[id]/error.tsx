"use client";

import { ErrorState } from "@/components/app/states/error-state";

/**
 * The Trade Detail route's error boundary.
 *
 * The underlying message is deliberately not shown: a backend failure string
 * can carry hosts, queries, or internals, and none of it helps a trader decide
 * what to do next. A missing/foreign trade is handled separately, by
 * `notFound()` in the page and this route's `not-found.tsx` — this boundary
 * is only for a fetch that genuinely failed.
 */
export default function TradeDetailError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-6xl pt-6">
      <ErrorState
        title="This trade did not load"
        description="The trade could not be fetched just now. Nothing about it has changed."
        retry={{ onRetry: reset }}
      />
    </div>
  );
}
