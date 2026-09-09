import { money, NO_VALUE } from "@/lib/app/format";
import type { MetricValue } from "@/lib/app/analytics";

/**
 * One `{value, state}` figure, as text.
 *
 * This is the single place an undefined figure becomes something a trader
 * reads, and the whole undefined-never-zero rule terminates here. A `0.0`
 * that arrived as a measurement is printed as `$0.00` — a trader who broke
 * exactly even measured that, and hiding it would be its own lie. A `null`
 * prints an em-dash and nothing else numeric: there is no branch that can
 * emit `0`, `0.00`, `$0.00`, `0%` or `N/A` for an absent figure.
 *
 * The em-dash carries a `title` because "—" alone tells a trader a figure is
 * missing without telling them why, and the five reasons ask for five
 * different responses: widen the period, record the missing amounts, or read
 * the figure as genuinely unbounded. None of these sentences suggests a next
 * trade — this is a record of what happened, not a prompt to act.
 */

export type MetricKind = "money" | "percent" | "ratio" | "number";

const UNDEFINED_EXPLANATIONS: Record<string, string> = {
  undefined_no_sample: "No trades in this range to measure this.",
  undefined_incomplete_sample:
    "Not every trade in this range records this, so a total would be misleading.",
  undefined_positive_infinity:
    "No losing trades in this range, so there is no ratio to report.",
  undefined_negative_infinity:
    "No winning trades in this range, so there is no ratio to report.",
  undefined_nan: "This could not be computed from the trades in this range.",
};

/** The fallback is a sentence too: an unknown state is still not a zero. */
const UNKNOWN_EXPLANATION = "This figure is not available for the trades in this range.";

function formatted(value: number, kind: MetricKind): string {
  if (kind === "money") return money(value);
  // A rate crosses the wire as a fraction, matching the Overview KPI row.
  if (kind === "percent") return `${(value * 100).toFixed(1)}%`;
  if (kind === "ratio") return `${value.toFixed(2)}x`;
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

export function MetricValueText({
  value,
  kind,
  className,
}: {
  value: MetricValue;
  kind: MetricKind;
  className?: string;
}) {
  if (value.value === null) {
    const explanation = UNDEFINED_EXPLANATIONS[value.state ?? ""] ?? UNKNOWN_EXPLANATION;
    return (
      <span className={className} title={explanation} aria-label={explanation}>
        {NO_VALUE}
      </span>
    );
  }
  return <span className={className}>{formatted(value.value, kind)}</span>;
}
