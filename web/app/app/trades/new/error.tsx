"use client";

import { ErrorState } from "@/components/app/states/error-state";

/**
 * The New Trade route's error boundary.
 *
 * Same discipline as Trade Detail's: the underlying message is never shown
 * — a thrown error's string can carry hosts, queries or backend internals,
 * none of which helps a trader decide what to do next. This page makes no
 * fetch of its own, so anything reaching this boundary is a render fault,
 * not a backend response to reshape.
 */
export default function NewTradeError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-4xl pt-6">
      <ErrorState
        title="The form did not load"
        description="Something went wrong loading New Trade. Nothing was saved."
        retry={{ onRetry: reset }}
      />
    </div>
  );
}
