"use client";

import { useState } from "react";

import { PartnerConversation } from "@/components/app/partner/conversation";

/**
 * Ask the partner about THIS trade.
 *
 * The trade is named by the relay path, never by the request body, and the
 * body never names a screenshot: the checkbox asks for "this trade's own
 * image", and the server picks which object that is from the owner's storage.
 *
 * Changing the checkbox mid-conversation starts a fresh conversation rather
 * than changing what the next turn sends. A conversation that answered one
 * question with the chart and the next without it would be citing evidence
 * the trader can no longer tell apart.
 */
export function TradePartnerPanel({
  tradeId,
  hasScreenshot,
}: {
  tradeId: number;
  hasScreenshot: boolean;
}) {
  const [withScreenshot, setWithScreenshot] = useState(false);

  return (
    <section
      data-testid="trade-partner-panel"
      aria-labelledby="trade-partner-heading"
      className="mt-10 flex flex-col rounded-xl border border-line bg-surface"
    >
      <div className="px-5 pt-5">
        <h2 id="trade-partner-heading" className="font-display text-xl font-bold">
          Ask about this trade
        </h2>
        <p className="mt-1 max-w-2xl text-sm leading-6 text-muted">
          Questions about what happened on this closed trade. The partner reads this trade, its
          review, and your playbook. It never comments on future market direction.
        </p>
        {hasScreenshot ? (
          <label className="mt-3 flex min-h-[44px] items-center gap-2 text-sm text-text">
            <input
              type="checkbox"
              checked={withScreenshot}
              onChange={(event) => setWithScreenshot(event.target.checked)}
              className="h-4 w-4 accent-current"
            />
            Let the partner look at this trade&apos;s screenshot
          </label>
        ) : null}
      </div>
      <PartnerConversation
        key={withScreenshot ? "with-screenshot" : "without-screenshot"}
        endpoint={`/api/trades/${tradeId}/partner/turns`}
        includeScreenshot={hasScreenshot && withScreenshot}
        intro="Ask about an entry, an exit, or a rule you set for yourself."
        placeholder="e.g. Did my exit follow my take-profit rules?"
      />
    </section>
  );
}
