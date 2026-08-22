import Link from "next/link";

import type { OverviewResponse } from "@/lib/app/overview";

/**
 * Every step the activation path can be waiting on.
 *
 * Keyed off the generated union rather than free strings: `Record<StepKey, …>`
 * makes a missing or misspelled key a compile error. It was a bare
 * `Record<string, …>` against three invented names, only one of which the
 * service emits — so two of the three states fell through to the "nothing
 * waiting" branch and a trader with one step done read "1 of 3 done. Nothing
 * waiting — the activation path is complete."
 *
 * Exported so a test can walk it. Every entry names something to re-read or
 * write down; none of them names a trade to take.
 */
export type StepKey = NonNullable<OverviewResponse["next_review_action"]["next_key"]>;

export const STEP_COPY: Record<StepKey, { title: string; body: string }> = {
  strategy: {
    title: "Write down your strategy",
    body: "Reviews are read against your own rules, so the rules have to exist in writing first.",
  },
  first_trade: {
    title: "Log your first completed trade",
    body: "The journal starts with one trade you have already closed and can describe.",
  },
  weekly_review: {
    title: "Read your first weekly review",
    body: "A few more completed trades and the weekly review has a real sample to read back to you.",
  },
};

/** What to go and re-read, not what to trade. */
export function NextReviewAction({ action }: { action: OverviewResponse["next_review_action"] }) {
  const step = action.next_key ? STEP_COPY[action.next_key] : undefined;

  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Next review action</h2>
      <p className="mt-1 text-sm text-muted">What to go and re-read, not what to trade.</p>
      <div className="mt-4 rounded-xl border border-line bg-surface p-5">
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent">
          {action.completed} of {action.total} done
        </div>
        {step ? (
          <>
            <p className="mt-2 font-medium text-text">{step.title}</p>
            <p className="mt-1 text-sm text-muted">
              {action.next_key === "weekly_review" && action.trades_until_review > 0
                ? `${action.trades_until_review} more completed trades to unlock it.`
                : step.body}
            </p>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted">
            Nothing waiting — the activation path is complete. Keep logging and the weekly review
            keeps getting more to work with.
          </p>
        )}
        <Link href="/app/reviews" className="mt-4 inline-block text-sm text-accent hover:underline">
          Open AI Reviews →
        </Link>
      </div>
    </section>
  );
}
