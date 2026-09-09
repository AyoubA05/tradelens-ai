import { BreakdownSection } from "@/components/app/analytics/breakdown-section";
import type { AnalyticsResponse } from "@/lib/app/analytics";

/**
 * Lens 4 — what was traded, how it was framed, and what went wrong.
 *
 * The mistake list is a count of what the trader tagged themselves. It is
 * ordered as it arrives and carries no ranking language: "you did this twice"
 * is a record; "your worst mistake" is a verdict this page has no standing to
 * deliver.
 */
export function SetupsLens({ setups }: { setups: AnalyticsResponse["setups"] }) {
  return (
    <div>
      <BreakdownSection
        id="by_setup"
        title="By setup type"
        description="What was recorded for each setup type in this period."
        breakdown={setups.by_setup}
      />
      <BreakdownSection
        id="by_asset"
        title="By asset"
        description="What was recorded for each asset in this period."
        breakdown={setups.by_asset}
      />
      <BreakdownSection
        id="by_strategy"
        title="By strategy"
        description="What was recorded for each strategy in this period."
        breakdown={setups.by_strategy}
      />
      <BreakdownSection
        id="by_timeframe"
        title="By timeframe"
        description="What was recorded on each timeframe in this period."
        breakdown={setups.by_timeframe}
      />
      <BreakdownSection
        id="by_confirmation"
        title="By confirmation model"
        description="What was recorded for each confirmation model in this period."
        breakdown={setups.by_confirmation}
      />

      <section
        data-testid="setups-mistakes"
        aria-label="Recorded mistakes"
        className="mt-6 rounded-xl border border-line bg-surface p-4"
      >
        <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          Recorded mistakes
        </h3>
        <p className="mt-1 text-xs text-muted">
          The mistake tags on trades in this period, and how often each was tagged.
        </p>
        {setups.mistakes.length === 0 ? (
          <p data-testid="setups-mistakes-empty" className="mt-3 text-sm text-muted">
            No trades in this range carry a mistake tag.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {setups.mistakes.map((mistake) => (
              <li key={mistake.tag} className="flex items-baseline justify-between gap-4 text-sm">
                <span className="min-w-0 truncate text-text">{mistake.tag}</span>
                <span className="shrink-0 font-mono text-text">{mistake.count}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
