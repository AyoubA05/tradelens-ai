"use client";

import { AlertTriangle } from "lucide-react";

/**
 * Errors say what happened and how to get out of it.
 *
 * They do not apologise, and they are never vague: "Sorry, something went
 * wrong" tells a trader nothing they can act on, and spends the interface's
 * credibility on politeness.
 */
export function ErrorState({
  title = "That did not load",
  description,
  retry,
}: {
  title?: string;
  description: string;
  retry?: { onRetry: () => void; label?: string };
}) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-negative/30 bg-negative/5 px-6 py-8 text-center"
    >
      <AlertTriangle className="mx-auto h-5 w-5 text-negative" aria-hidden="true" />
      <h2 className="mt-3 font-display text-base font-semibold text-text">{title}</h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-muted">{description}</p>
      {retry && (
        <button
          type="button"
          onClick={retry.onRetry}
          className="mt-5 inline-flex items-center rounded-lg border border-line-strong px-4 py-2 text-sm font-medium text-text transition-colors duration-150 ease-tl hover:bg-surface-2"
        >
          {retry.label ?? "Try again"}
        </button>
      )}
    </div>
  );
}
