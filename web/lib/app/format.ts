/**
 * How the app writes a figure, in one place.
 *
 * Seven copies of `money` had drifted into three different behaviours —
 * two decimals with a sign, no decimals with a sign, and no decimals with the
 * sign silently dropped. The last one put a losing day on screen as `$220`,
 * readable only because a sibling aria-label happened to supply "down"
 * separately. Formatting that decides whether a number reads as a gain or a
 * loss is not per-component styling.
 */

/**
 * A signed dollar figure.
 *
 * The minus sign is text, never colour: measured against the dark surface the
 * positive and negative tokens are ΔE 2.3 apart under deuteranopia, so a tint
 * alone conveys nothing to those readers. `sign: false` exists only for the
 * few places where an adjacent word already states the direction.
 */
export function money(
  n: number,
  { decimals = 2, sign = true }: { decimals?: number; sign?: boolean } = {},
): string {
  const magnitude = Math.abs(n).toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return `${sign && n < 0 ? "-" : ""}$${magnitude}`;
}

/**
 * Why a figure has no number, in words a trader can act on.
 *
 * One vocabulary across every panel. Risk and discipline used to answer the
 * same question with "Not yet" and "More trades needed to score it" while
 * everything else said "—" and "Not enough data", which reads as two different
 * kinds of missing when it is one.
 */
export function undefinedReason(state: string | null | undefined): string {
  if (state === "undefined_positive_infinity") return "No losses yet";
  if (state === "undefined_negative_infinity") return "No wins yet";
  if (state === "undefined_incomplete_sample") return "P&L data is incomplete";
  return "Not enough data";
}

/** What an absent figure looks like. Never a zero — undefined is not zero. */
export const NO_VALUE = "—";
