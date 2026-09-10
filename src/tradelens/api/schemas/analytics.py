"""The analytics wire contract.

Every numeric field is `{value, state}`. That is not defensive style — it is
the type making a fabricated zero unrepresentable. A field typed as a bare
`float` has nowhere to put "not measurable", so it eventually puts a zero
there, and a zero on a trading dashboard is a claim about someone's money.

`UndefinedState` and `_Strict` are imported from the overview contract rather
than redefined: two definitions of "undefined" would drift apart, and then
two pages would disagree about what a missing figure looks like.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import ConfigDict, Field, model_validator

from src.tradelens.api.schemas.overview import UndefinedState, _Strict


class MetricValue(_Strict):
    """One possibly-undefined figure, with the invariant enforced.

    Exactly one of `value` or `state` is present — never both, never
    neither. Without this the type merely *describes* the undefined-never-
    zero rule while the service's discipline is the only thing enforcing it,
    and the contract layer is precisely the layer meant to catch the service
    drifting. A `0.0` riding alongside `undefined_incomplete_sample` would
    otherwise serialise happily onto a trader's screen.

    Mirrors `overview.Undefinable`, which carries the same validator. The
    class is not aliased to it because the name is the OpenAPI schema name
    and the generated TypeScript is built from it.
    """

    value: Optional[float]
    state: Optional[UndefinedState]

    @model_validator(mode="after")
    def value_and_state_are_exclusive(self) -> "MetricValue":
        if (self.value is None) == (self.state is None):
            raise ValueError("exactly one of value or state must be present")
        return self


class SeriesPoint(_Strict):
    date: str
    value: float


class HistogramBucket(_Strict):
    label: str
    count: int


class MistakeCount(_Strict):
    tag: str
    count: int


class BreakdownRow(_Strict):
    key: str
    trades: int
    total_pnl: MetricValue
    win_rate: MetricValue


class BreakdownLeader(_Strict):
    """A server-selected narrative, only after the shared pattern threshold."""

    key: str
    trades: int


class Breakdown(_Strict):
    """A category breakdown, plus whether it can honestly be compared.

    `comparable` is decided server-side by `sample_policy.enough_categories`.
    One category is not a ranking, and letting the browser decide that would
    put the rule in two places.
    """

    rows: List[BreakdownRow]
    comparable: bool
    leader: Optional[BreakdownLeader]


class StreakBlock(_Strict):
    current: MetricValue
    max_win: MetricValue
    max_loss: MetricValue


class PerformanceLens(_Strict):
    """Lens 1.

    `win_rate` and `total_pnl` are INDEPENDENTLY SOURCED — the first from
    `result`, the second from `pnl` — so a sample with no monetary data at
    all still carries a valid win rate. The contract keeps them separate
    fields with separate states for that reason; a presentation that
    degrades one because the other is undefined is misreading this shape.
    """

    total_pnl: MetricValue
    win_rate: MetricValue
    expectancy: MetricValue
    profit_factor: MetricValue
    total_trades: int
    equity_curve: List[SeriesPoint]
    daily_pnl: List[SeriesPoint]
    streaks: StreakBlock


class RiskLens(_Strict):
    max_drawdown: MetricValue
    drawdown_series: List[SeriesPoint]
    r_multiples: List[HistogramBucket]
    avg_win: MetricValue
    avg_loss: MetricValue


class TimingLens(_Strict):
    """Lens 3.

    No `by_hour`: no clock component is persisted (`entry_time` is hash-only
    and the `Trade` model has no time column), so the breakdown could never
    hold a row. An always-empty panel reads as "you have no hourly pattern"
    rather than "this was never recorded".
    """

    by_day_of_week: Breakdown
    by_session: Breakdown
    by_killzone: Breakdown


class SetupsLens(_Strict):
    by_setup: Breakdown
    by_asset: Breakdown
    by_strategy: Breakdown
    by_timeframe: Breakdown
    by_confirmation: Breakdown
    mistakes: List[MistakeCount]


class DisciplineBlock(_Strict):
    rule_adherence: MetricValue
    consistency: MetricValue
    edge_leak: MetricValue
    recorded_trades: int


class AnalyticsPeriod(_Strict):
    from_: str = Field(alias="from")
    to: str

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class ComparisonBlock(_Strict):
    """This period against the equally-long one before it.

    `period` states the window actually used, because the comparison is
    DERIVED rather than chosen — there is no second date control, so the
    dates have to be legible from the response itself.
    """

    period: AnalyticsPeriod
    net_pnl: MetricValue
    win_rate: MetricValue
    profit_factor: MetricValue
    consistency: MetricValue


class AnalyticsResponse(_Strict):
    """Everything the four lenses need, over ONE sample.

    One response rather than four: the lenses answer four questions about the
    same filtered sample, and separate requests would give four chances for
    one of them to be computed over a slightly different frame — a different
    period rounding, filters applied in a different order. A trader would
    then see a win rate that disagrees with the breakdown it is built from.
    """

    period: AnalyticsPeriod
    filters: Dict[str, str]
    comparison: ComparisonBlock
    performance: PerformanceLens
    risk: RiskLens
    timing: TimingLens
    setups: SetupsLens
    discipline: DisciplineBlock
