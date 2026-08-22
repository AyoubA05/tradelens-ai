import { money } from "@/lib/app/format";
import type { OverviewResponse } from "@/lib/app/overview";

type Point = { date: string; equity: number };

/**
 * Map equity points into an SVG line and its closed area.
 *
 * Exported because the geometry is data, not decoration: an inverted y axis or
 * a divide-by-zero on a flat curve is a wrong picture, and a wrong picture of
 * an account is worse than no picture.
 */
export function buildCurvePath(points: Point[], width: number, height: number) {
  if (points.length === 0) return { line: "", area: "" };

  const values = points.map((p) => p.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  // A flat curve has no range; centre it rather than dividing by zero.
  const isFlat = max === min;
  const span = max - min || 1;
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;

  const coords = points.map((p, i) => {
    const x = points.length > 1 ? i * stepX : width / 2;
    // SVG y grows downward, so the largest value gets the smallest y.
    const y = isFlat ? height / 2 : height - ((p.equity - min) / span) * height;
    return `${Number(x.toFixed(2))},${Number(y.toFixed(2))}`;
  });

  const line = `M${coords[0]}` + coords.slice(1).map((c) => `L${c}`).join("");
  const area = `${line}L${Number((points.length > 1 ? width : width / 2).toFixed(2))},${height}L${points.length > 1 ? 0 : Number((width / 2).toFixed(2))},${height}Z`;
  return { line, area };
}

/**
 * The account's path through the period.
 *
 * One series, so no legend — the title names it and the end value is labelled.
 * The line takes a status colour rather than the brand accent: teal means
 * "act" everywhere else in this product, and an equity line is not an action.
 */
export function EquityCurve({
  points,
  sample,
}: {
  points: Point[];
  sample: Pick<
    OverviewResponse["sample"],
    "show_dominant_series" | "dated_points" | "pnl_complete"
  >;
}) {
  const MIN_POINTS = 4;
  if (!sample.pnl_complete) {
    return (
      <div className="rounded-xl border border-line bg-surface p-6">
        <p className="text-sm font-medium text-text">P&amp;L data is incomplete</p>
        <p className="mt-1 max-w-sm text-sm text-muted">
          Record P&amp;L for every trade in this period before reading its equity path.
        </p>
      </div>
    );
  }
  if (!sample.show_dominant_series) {
    const needed = MIN_POINTS - sample.dated_points;
    return (
      <div className="rounded-xl border border-line bg-surface p-6">
        <p className="text-sm font-medium text-text">Not enough dated trades for a curve</p>
        <p className="mt-1 max-w-sm text-sm text-muted">
          {needed} more trading {needed === 1 ? "day" : "days"} will unlock the equity curve. The
          figures above already reflect every trade logged.
        </p>
      </div>
    );
  }

  const W = 720;
  const H = 180;
  const { line, area } = buildCurvePath(points, W, H);
  const last = points[points.length - 1]?.equity ?? 0;
  const up = last >= 0;
  const stroke = up ? "#22c55e" : "#f56565";

  return (
    <figure className="rounded-xl border border-line bg-chart p-4">
      <figcaption className="flex items-baseline justify-between">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          Equity curve
        </span>
        <span className={`font-mono text-sm ${up ? "text-positive" : "text-negative"}`}>
          {money(last, { decimals: 0 })}
        </span>
      </figcaption>
      <svg
        role="img"
        aria-label={`Equity curve over ${points.length} trading days, ending at ${money(last, { decimals: 0 })}`}
        viewBox={`0 0 ${W} ${H}`}
        className="mt-3 h-44 w-full"
        preserveAspectRatio="none"
      >
        <path d={area} fill={stroke} fillOpacity="0.08" />
        <path d={line} fill="none" stroke={stroke} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      {/* No "5 needed" clause here: 5 is the pattern threshold in TRADES
          (services/sample_policy), and this axis counts trading DAYS — the
          two are not the same count, and the sample gate above already
          withholds the curve until it has earned one. */}
      <p className="mt-2 font-mono text-[11px] text-muted">
        n={points.length} trading {points.length === 1 ? "day" : "days"}
      </p>
    </figure>
  );
}
