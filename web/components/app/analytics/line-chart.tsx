import { MetricValueText, type MetricKind } from "@/components/app/analytics/metric-value";
import { buildCurvePath } from "@/components/app/overview/equity-curve";

/**
 * One dated series, as a line.
 *
 * The geometry comes from `buildCurvePath` and from nowhere else. That
 * function already handles the two ways a line chart lies — a divide-by-zero
 * on a flat curve, and an inverted y axis that draws a losing month as a
 * winning one — and a second implementation here would drift away from it the
 * first time either changed. This component maps values into it, regroups the
 * coordinates it returns, and draws.
 *
 * Three rules follow from "a wrong picture of an account is worse than no
 * picture":
 *
 * - A series with nothing to plot is stated in words. An empty axis with no
 *   line reads as a flat zero, and that is a claim about the trader's record
 *   rather than an absence of one.
 * - A day with nothing recorded is a break in the stroke. Interpolating across
 *   it invents a value, and drawing it at zero invents a worse one.
 * - When the values straddle zero, zero is drawn and labelled, so a reader can
 *   see which side of it a point falls on without inferring it from a colour.
 */

export type SeriesPoint = { date: string; value: number | null };

const W = 720;
const H = 180;

/** The pixel row that the value 0 lands on, taken from `buildCurvePath` itself
 *  so the baseline and the line can never be scaled by different rules. */
function zeroRow(min: number, max: number): number {
  const anchors = [min, 0, max].map((v) => ({ date: "", equity: v }));
  const coords = coordinatesOf(buildCurvePath(anchors, W, H).line);
  return Number(coords[1].split(",")[1]);
}

/** Split a path built by `buildCurvePath` back into its "x,y" pairs, in order. */
function coordinatesOf(line: string): string[] {
  return line.split(/[ML]/).filter(Boolean);
}

export function LineChart({
  id,
  title,
  description,
  points,
  kind,
}: {
  id: string;
  title: string;
  description: string;
  points: SeriesPoint[];
  kind: MetricKind;
}) {
  const plotted = points.filter(
    (p): p is { date: string; value: number } => p.value !== null && Number.isFinite(p.value),
  );
  const missing = points.length - plotted.length;

  const frame = (body: React.ReactNode) => (
    <section
      data-testid={`chart-${id}`}
      aria-label={title}
      className="mt-6 rounded-xl border border-line bg-surface p-4"
    >
      <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{title}</h3>
      <p className="mt-1 text-xs text-muted">{description}</p>
      {body}
    </section>
  );

  if (plotted.length === 0) {
    return frame(
      <p data-testid={`chart-${id}-empty`} className="mt-3 text-sm text-muted">
        There is nothing recorded in this range to draw, so no line is shown.
      </p>,
    );
  }
  if (plotted.length === 1) {
    return frame(
      <p data-testid={`chart-${id}-empty`} className="mt-3 text-sm text-muted">
        This range holds one recorded point, which is not a path. Two or more are needed before a
        line describes anything.
      </p>,
    );
  }

  const values = plotted.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const straddlesZero = min < 0 && max > 0;

  const coords = coordinatesOf(
    buildCurvePath(
      plotted.map((p) => ({ date: p.date, equity: p.value })),
      W,
      H,
    ).line,
  );

  // Regroup the coordinates into unbroken runs: an unrecorded point ends the
  // run it interrupts rather than being bridged over.
  const runs: string[][] = [];
  let cursor = 0;
  let open: string[] | null = null;
  for (const point of points) {
    if (point.value === null || !Number.isFinite(point.value)) {
      open = null;
      continue;
    }
    if (open === null) {
      open = [];
      runs.push(open);
    }
    open.push(coords[cursor]);
    cursor += 1;
  }
  const drawn = runs.filter((run) => run.length > 0);
  const d = drawn
    .map((run) => `M${run[0]}${run.slice(1).map((c) => `L${c}`).join("")}`)
    .join("");

  // Every recorded point also gets a mark. A run of ONE produces a bare `M`
  // with no `L`, which draws nothing at all — so a sparse journal whose
  // recorded days never sit adjacent rendered an empty frame captioned "3
  // recorded points". An empty axis reads as a flat zero, and that is a
  // claim about the trader's record rather than an absence of one.
  const marks = drawn.flatMap((run) => run).map((coord) => {
    const [cx, cy] = coord.split(",");
    return { cx, cy };
  });

  const last = plotted[plotted.length - 1].value;
  const stroke = last >= 0 ? "#22c55e" : "#f56565";

  return frame(
    <>
      <svg
        role="img"
        aria-label={`${title}: ${plotted.length} recorded points`}
        viewBox={`0 0 ${W} ${H}`}
        className="mt-3 h-44 w-full"
        preserveAspectRatio="none"
      >
        {straddlesZero ? (
          <line
            data-testid={`chart-${id}-zero-line`}
            aria-hidden="true"
            x1={0}
            x2={W}
            y1={zeroRow(min, max)}
            y2={zeroRow(min, max)}
            stroke="currentColor"
            strokeWidth="1"
            strokeDasharray="3 3"
            className="text-line"
          />
        ) : null}
        <path
          data-testid={`chart-${id}-line`}
          d={d}
          fill="none"
          stroke={stroke}
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
        {marks.map((mark, index) => (
          <circle
            key={`${mark.cx},${mark.cy},${index}`}
            data-testid={`chart-${id}-point`}
            cx={mark.cx}
            cy={mark.cy}
            r="3"
            fill={stroke}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>

      <p className="mt-2 font-mono text-[11px] text-muted">
        {`n=${plotted.length} recorded ${plotted.length === 1 ? "point" : "points"}`}
        {straddlesZero ? " · the dashed rule marks zero; points under it are negative" : ""}
      </p>
      {missing > 0 ? (
        <p data-testid={`chart-${id}-gaps`} className="mt-1 text-xs text-muted">
          {`${missing} ${missing === 1 ? "point" : "points"} in this range recorded no value and ${
            missing === 1 ? "is" : "are"
          } not drawn. The line breaks there rather than crossing it.`}
        </p>
      ) : null}

      {/* The text equivalent. A chart that only exists as pixels is a chart
          half the readers of this page cannot read. */}
      <div data-testid={`chart-${id}-scroll`} className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[20rem] border-collapse text-sm">
          <caption className="sr-only">{`${title}, as a table`}</caption>
          <thead>
            <tr className="border-b border-line text-left">
              <th
                scope="col"
                className="py-2 pr-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted"
              >
                Date
              </th>
              <th
                scope="col"
                className="py-2 font-mono text-[10px] uppercase tracking-[0.14em] text-muted"
              >
                Value
              </th>
            </tr>
          </thead>
          <tbody>
            {plotted.map((p) => (
              <tr key={p.date} className="border-b border-line/60 last:border-b-0">
                <td className="py-1 pr-4 font-mono text-text">{p.date}</td>
                <td className="py-1 font-mono text-text">
                  <MetricValueText value={{ value: p.value, state: null }} kind={kind} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>,
  );
}
