/**
 * A bucketed distribution, as horizontal bars.
 *
 * Two rules, both about not overstating what a sample shows:
 *
 * - Bars scale from the largest recorded count, never from a fixed maximum.
 * - A distribution with a single bucket gets no bar at all. A lone bar is
 *   always full width, and full width reads as dominance over a field that
 *   does not exist.
 *
 * The bar is decoration: every count is written out beside its label, so the
 * chart carries no meaning that the text does not.
 */

export type Bucket = { label: string; count: number };

export function DistributionChart({
  id,
  title,
  description,
  buckets,
}: {
  id: string;
  title: string;
  description: string;
  buckets: Bucket[];
}) {
  const max = buckets.reduce((acc, b) => Math.max(acc, b.count), 0);
  const comparable = buckets.length > 1;

  return (
    <section
      data-testid={`chart-${id}`}
      aria-label={title}
      className="mt-6 rounded-xl border border-line bg-surface p-4"
    >
      <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{title}</h3>
      <p className="mt-1 text-xs text-muted">{description}</p>

      {buckets.length === 0 || max === 0 ? (
        <p data-testid={`chart-${id}-empty`} className="mt-3 text-sm text-muted">
          There is nothing recorded in this range to draw, so no distribution is shown.
        </p>
      ) : (
        <>
          <ul className="mt-3 space-y-2">
            {buckets.map((bucket, index) => (
              <li key={bucket.label} className="grid grid-cols-[8rem_1fr_3rem] items-center gap-3">
                <span className="font-mono text-xs text-muted">{bucket.label}</span>
                <span className="h-2 w-full rounded-full bg-line/60">
                  {comparable ? (
                    <span
                      data-testid={`chart-${id}-bar-${index}`}
                      aria-hidden="true"
                      className="block h-2 rounded-full bg-positive/70"
                      style={{ width: `${(bucket.count / max) * 100}%` }}
                    />
                  ) : null}
                </span>
                <span className="text-right font-mono text-sm text-text">{bucket.count}</span>
              </li>
            ))}
          </ul>
          {comparable ? null : (
            <p data-testid={`chart-${id}-incomparable`} className="mt-3 text-xs text-muted">
              This range records only one bucket, so there is nothing to compare it against and no
              bar is drawn.
            </p>
          )}
        </>
      )}
    </section>
  );
}
