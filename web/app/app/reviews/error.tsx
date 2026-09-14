"use client";

import { ErrorState } from "@/components/app/states/error-state";

/**
 * The AI Reviews route's error boundary. The underlying message is never
 * shown: a backend failure string can carry internals.
 */
export default function ReviewsError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-6xl pt-6">
      <ErrorState
        title="AI Reviews did not load"
        description="Your patterns and saved reviews could not be fetched just now. Nothing in your journal has changed."
        retry={{ onRetry: reset }}
      />
    </div>
  );
}
