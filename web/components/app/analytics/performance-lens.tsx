import { FigureRow, LensCount, LensFigure } from "@/components/app/analytics/lens-figure";
import type { AnalyticsResponse } from "@/lib/app/analytics";

/**
 * Lens 1 — what the record adds up to, and how consistently it was kept.
 *
 * `total_pnl` and `win_rate` sit side by side as equals. They are
 * independently sourced — one from `pnl`, one from `result` — so an undefined
 * total says nothing at all about the win rate beside it. There is
 * deliberately no shared "incomplete data" banner over this row and no
 * conditional dimming: either would tell a trader their win rate is
 * unreliable, which would not be true.
 *
 * Everything here is retrospective. Nothing on this lens says what to do next.
 */
export function PerformanceLens({
  performance,
  discipline,
}: {
  performance: AnalyticsResponse["performance"];
  discipline: AnalyticsResponse["discipline"];
}) {
  return (
    <div>
      <FigureRow>
        <LensFigure testId="figure-total-pnl" label="Net P&L" value={performance.total_pnl} kind="money" />
        <LensFigure testId="figure-win-rate" label="Win rate" value={performance.win_rate} kind="percent" />
        <LensFigure testId="figure-expectancy" label="Expectancy" value={performance.expectancy} kind="money" />
        <LensFigure
          testId="figure-profit-factor"
          label="Profit factor"
          value={performance.profit_factor}
          kind="ratio"
        />
        <LensCount testId="figure-total-trades" label="Trades" count={performance.total_trades} />
        <LensFigure testId="figure-streak-current" label="Current streak" value={performance.streaks.current} kind="number" />
        <LensFigure testId="figure-streak-max-win" label="Longest win streak" value={performance.streaks.max_win} kind="number" />
        <LensFigure testId="figure-streak-max-loss" label="Longest loss streak" value={performance.streaks.max_loss} kind="number" />
      </FigureRow>

      <section
        data-testid="performance-series-pending"
        aria-label="Equity curve and daily P&L"
        className="mt-6 rounded-xl border border-line bg-surface p-4"
      >
        <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          Equity curve and daily P&amp;L
        </h3>
        <p className="mt-1 text-xs text-muted">
          {`${performance.equity_curve.length} equity points and ${performance.daily_pnl.length} daily totals are recorded for this period. These series are not drawn yet.`}
        </p>
      </section>

      <section
        data-testid="performance-discipline"
        aria-label="Discipline"
        className="mt-6 rounded-xl border border-line bg-surface p-4"
      >
        <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Discipline</h3>
        <p className="mt-1 text-xs text-muted">
          How closely the record was kept to the rules the trader wrote down.
        </p>
        <FigureRow>
          <LensFigure
            testId="figure-rule-adherence"
            label="Rule adherence"
            value={discipline.rule_adherence}
            kind="percent"
          />
          <LensFigure
            testId="figure-consistency"
            label="Consistency"
            value={discipline.consistency}
            kind="number"
          />
          <LensFigure testId="figure-edge-leak" label="Edge leak" value={discipline.edge_leak} kind="money" />
          <LensCount
            testId="figure-recorded-trades"
            label="Trades with rules recorded"
            count={discipline.recorded_trades}
          />
        </FigureRow>
      </section>
    </div>
  );
}
