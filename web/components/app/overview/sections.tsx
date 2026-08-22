import { KpiRow } from "@/components/app/overview/kpi-row";
import { RiskDiscipline } from "@/components/app/overview/risk-discipline";
import { Trajectory } from "@/components/app/overview/trajectory";
import { RecurringEdge } from "@/components/app/overview/recurring-edge";
import { TradingCalendar } from "@/components/app/overview/trading-calendar";
import { NextReviewAction } from "@/components/app/overview/next-review-action";
import { RecentTrades } from "@/components/app/overview/recent-trades";
import type { OverviewResponse } from "@/lib/app/overview";

/**
 * The Overview, in reading order: what happened, whether it was a process,
 * how it got there, what repeats, when it happened, what to review, and the
 * trades themselves.
 */
export function OverviewSections({ data }: { data: OverviewResponse }) {
  return (
    <div className="mt-8">
      <KpiRow kpi={data.kpi} sample={data.sample} />
      <RiskDiscipline risk={data.risk} sample={data.sample} />
      <Trajectory trajectory={data.trajectory} sample={data.sample} />
      <RecurringEdge edge={data.recurring_edge} sample={data.sample} />
      <TradingCalendar calendar={data.calendar} sample={data.sample} />
      <NextReviewAction action={data.next_review_action} />
      <RecentTrades trades={data.recent_trades} />
    </div>
  );
}
