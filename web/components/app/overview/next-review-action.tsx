import Link from "next/link";

import type { OverviewResponse } from "@/lib/app/overview";

const STEP_COPY: Record<string, { title: string; body: string }> = {
  strategy_profile: {
    title: "Write down your strategy",
    body: "Reviews are read against your own rules, so they need the rules first.",
  },
  first_trade: {
    title: "Log your first completed trade",
    body: "The journal starts with one trade you have already closed.",
  },
  first_review: {
    title: "Review your first useful sample",
    body: "A few more completed trades and the weekly review has something true to say.",
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
              {action.next_key === "first_review" && action.trades_until_review > 0
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
