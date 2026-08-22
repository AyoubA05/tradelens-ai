"use client";

import { ErrorState } from "@/components/app/states/error-state";

/**
 * The route's error boundary.
 *
 * The underlying message is deliberately not shown: a backend failure string
 * can carry hosts, queries, or internals, and none of it helps a trader decide
 * what to do next.
 */
export default function OverviewError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-6xl pt-6">
      <ErrorState
        title="Your overview did not load"
        description="The figures could not be fetched just now. Nothing in your journal has changed."
        retry={{ onRetry: reset }}
      />
    </div>
  );
}
