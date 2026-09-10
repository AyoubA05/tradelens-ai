import type { StrategyResponse } from "@/lib/app/strategy";

/**
 * The compact header: whose playbook, how complete, what reads it, and the
 * saved values worth scanning.
 *
 * Every figure here is the SERVER's. Completion is decided by
 * `strategy_playbook.section_status` in Python; this component prints it
 * and computes nothing, so the count on screen is the count the AI context
 * was actually built from — the SAVED profile, never unsaved keystrokes.
 */
export function PlaybookSummary({ data }: { data: StrategyResponse }) {
  const name = data.profile?.name?.trim() ?? "";
  const updated = (data.updated_at ?? "").slice(0, 10);
  const complete = data.written >= data.total;
  const facets: { label: string; items: string[] }[] = [
    { label: "Markets", items: data.facets.markets },
    {
      label: "Timeframes",
      items: [
        data.facets.entry_timeframe ? `Entry ${data.facets.entry_timeframe}` : null,
        data.facets.htf_timeframe ? `HTF ${data.facets.htf_timeframe}` : null,
      ].filter((v): v is string => v !== null),
    },
    { label: "Setups", items: data.facets.setups },
  ].filter((f) => f.items.length > 0);

  return (
    <section
      data-testid="playbook-summary"
      aria-label="Playbook summary"
      className="mt-6 rounded-xl border border-line bg-surface p-5"
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="font-display text-xl font-semibold text-text">
          {name || "No playbook yet"}
        </p>
        {data.profile ? (
          <span className="rounded-full border border-positive/40 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-positive">
            Active
          </span>
        ) : null}
        {updated ? <p className="font-mono text-xs text-muted">{`Updated ${updated}`}</p> : null}
      </div>

      <div
        role="progressbar"
        aria-label="Sections written"
        aria-valuemin={0}
        aria-valuemax={data.total}
        aria-valuenow={data.written}
        className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-surface-2"
      >
        <span
          className="block h-full rounded-full bg-accent"
          style={{ width: `${data.total ? Math.round((data.written / data.total) * 100) : 0}%` }}
        />
      </div>
      <p data-testid="playbook-count" className="mt-2 text-sm text-text">
        {`${data.written} of ${data.total} sections written`}
      </p>
      <p className="mt-1 text-sm text-muted">
        {complete
          ? "Every review and grade is read against these rules."
          : "Reviews and grading fall back to generic reflection until you describe how you trade."}
      </p>

      {facets.length ? (
        <dl className="mt-4 flex flex-col gap-2">
          {facets.map((facet) => (
            <div key={facet.label} className="flex flex-wrap items-center gap-2">
              <dt className="w-24 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                {facet.label}
              </dt>
              {facet.items.map((item) => (
                <dd
                  key={item}
                  className="rounded-md border border-line px-2 py-0.5 text-xs text-text"
                >
                  {item}
                </dd>
              ))}
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  );
}
