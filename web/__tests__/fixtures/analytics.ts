import type { AnalyticsResponse, MetricValue } from "@/lib/app/analytics";

/**
 * A whole analytics payload, shaped exactly like the strict backend contract.
 *
 * `analyticsFixture` is annotated as `AnalyticsResponse` rather than cast to
 * it, and that is the point of this file: a cast would let the fixture keep
 * compiling after the backend contract gains, loses or renames a field, and a
 * stale fixture is a test suite that passes against a page nobody can render.
 * With the annotation, `tsc` fails the moment the generated schema moves.
 *
 * A test states the one figure it is about by spreading over the result, so it
 * never has to restate thirty fields it does not care about.
 */
export const value = (v: number): MetricValue => ({ value: v, state: null });

/**
 * An undefined figure. `state` is the generated union, not `string`: a typo'd
 * state is the exact drift this fixture exists to catch.
 */
export const undefinedValue = (state: NonNullable<MetricValue["state"]>): MetricValue => ({
  value: null,
  state,
});

type Breakdown = AnalyticsResponse["timing"]["by_day_of_week"];

export function breakdown(
  rows: Array<{ key: string; trades: number; pnl: number | null; win: number | null }>,
  comparable: boolean,
): Breakdown {
  return {
    comparable,
    rows: rows.map((r) => ({
      key: r.key,
      trades: r.trades,
      total_pnl: r.pnl === null ? undefinedValue("undefined_incomplete_sample") : value(r.pnl),
      win_rate: r.win === null ? undefinedValue("undefined_no_sample") : value(r.win),
    })),
  };
}

const emptyBreakdown = (): Breakdown => breakdown([], false);

export function analyticsFixture(): AnalyticsResponse {
  const payload: AnalyticsResponse = {
    period: { from: "2026-08-01", to: "2026-08-31" },
    filters: {},
    comparison: {
      period: { from: "2026-07-02", to: "2026-08-01" },
      net_pnl: value(120.5),
      win_rate: value(0.4),
      profit_factor: value(1.2),
      consistency: value(60),
    },
    performance: {
      total_pnl: value(500),
      win_rate: value(0.5),
      expectancy: value(25),
      profit_factor: value(1.8),
      total_trades: 10,
      equity_curve: [
        { date: "2026-08-01", value: 100 },
        { date: "2026-08-02", value: 250 },
      ],
      daily_pnl: [{ date: "2026-08-01", value: 100 }],
      streaks: { current: value(2), max_win: value(4), max_loss: value(2) },
    },
    risk: {
      max_drawdown: value(-80),
      drawdown_series: [{ date: "2026-08-01", value: 0 }],
      r_multiples: [{ label: "0.0 to 1.0", count: 3 }],
      avg_win: value(140),
      avg_loss: value(-60),
    },
    timing: {
      by_day_of_week: breakdown(
        [
          { key: "Monday", trades: 4, pnl: 300, win: 0.5 },
          { key: "Tuesday", trades: 6, pnl: 200, win: 0.5 },
        ],
        true,
      ),
      by_session: emptyBreakdown(),
      by_killzone: emptyBreakdown(),
    },
    setups: {
      by_setup: emptyBreakdown(),
      by_asset: emptyBreakdown(),
      by_strategy: emptyBreakdown(),
      by_timeframe: emptyBreakdown(),
      by_confirmation: emptyBreakdown(),
      mistakes: [{ tag: "Moved stop", count: 2 }],
    },
    discipline: {
      rule_adherence: value(0.8),
      consistency: value(70),
      edge_leak: value(-120),
      recorded_trades: 10,
    },
  };
  return payload;
}

/** The same contract over a period in which the trader logged nothing. */
export function emptyAnalyticsFixture(): AnalyticsResponse {
  const base = analyticsFixture();
  return {
    ...base,
    performance: {
      ...base.performance,
      total_trades: 0,
      total_pnl: undefinedValue("undefined_no_sample"),
      win_rate: undefinedValue("undefined_no_sample"),
      expectancy: undefinedValue("undefined_no_sample"),
      profit_factor: undefinedValue("undefined_no_sample"),
      equity_curve: [],
      daily_pnl: [],
    },
    timing: {
      by_day_of_week: emptyBreakdown(),
      by_session: emptyBreakdown(),
      by_killzone: emptyBreakdown(),
    },
    discipline: { ...base.discipline, recorded_trades: 0 },
  };
}
