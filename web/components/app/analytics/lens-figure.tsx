import { MetricValueText, type MetricKind } from "@/components/app/analytics/metric-value";
import type { MetricValue } from "@/lib/app/analytics";

/**
 * One labelled figure on a lens.
 *
 * The value is always rendered by `MetricValueText` — a lens never formats a
 * number itself, because a local `toFixed` is one branch away from printing a
 * zero for a figure nobody measured.
 *
 * Every figure carries the same weight regardless of what the figures beside
 * it happen to be. Nothing here dims, disables or annotates a value because a
 * neighbour is undefined: `win_rate` comes from `result` and `total_pnl` from
 * `pnl`, so a trader who labels outcomes without recording amounts has a
 * perfectly valid win rate and the page must not imply otherwise.
 */
export function LensFigure({
  label,
  value,
  kind,
  testId,
  magnitudeAsLoss = false,
}: {
  label: string;
  value: MetricValue;
  kind: MetricKind;
  testId: string;
  magnitudeAsLoss?: boolean;
}) {
  const displayed =
    magnitudeAsLoss && value.value !== null && value.value > 0
      ? { value: -value.value, state: null }
      : value;
  return (
    <div data-testid={testId} className="border-l border-line px-4 py-3 first:border-l-0 first:pl-0">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</div>
      <MetricValueText value={displayed} kind={kind} className="mt-1 block font-mono text-xl text-text" />
    </div>
  );
}

/** A plain integer count. Counts are not `{value, state}` figures. */
export function LensCount({
  label,
  count,
  testId,
}: {
  label: string;
  count: number;
  testId: string;
}) {
  return (
    <div data-testid={testId} className="border-l border-line px-4 py-3 first:border-l-0 first:pl-0">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</div>
      <div className="mt-1 font-mono text-xl text-text">{count}</div>
    </div>
  );
}

export function FigureRow({ children }: { children: React.ReactNode }) {
  return <div className="mt-4 grid grid-cols-2 gap-y-2 sm:grid-cols-3 lg:grid-cols-4">{children}</div>;
}
