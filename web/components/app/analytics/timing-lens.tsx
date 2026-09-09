import { BreakdownSection } from "@/components/app/analytics/breakdown-section";
import type { AnalyticsResponse } from "@/lib/app/analytics";

/**
 * Lens 3 — when the recorded trades happened.
 *
 * There is no hour-of-day breakdown, and that is deliberate: no clock
 * component is stored for a trade, so such a panel could only ever sit empty,
 * and an empty "by hour" panel reads as a claim about the trader's record
 * rather than as a missing data source.
 */
export function TimingLens({ timing }: { timing: AnalyticsResponse["timing"] }) {
  return (
    <div>
      <BreakdownSection
        id="by_day_of_week"
        title="By day of week"
        description="What was recorded on each weekday in this period."
        breakdown={timing.by_day_of_week}
      />
      <BreakdownSection
        id="by_session"
        title="By session"
        description="What was recorded in each trading session in this period."
        breakdown={timing.by_session}
      />
      <BreakdownSection
        id="by_killzone"
        title="By killzone"
        description="What was recorded in each killzone in this period."
        breakdown={timing.by_killzone}
      />
    </div>
  );
}
