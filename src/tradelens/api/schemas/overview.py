# src/tradelens/api/schemas/overview.py
"""The Overview response contract.

Typed rather than a bare dict, deliberately: a `-> dict` handler generates
`{[key: string]: unknown}` in the TypeScript client, and the drift gate then
guards a contract that says nothing.

`Optional[float]` paired with a `*_state` string is how an undefined figure
crosses the boundary. Null plus "undefined_positive_infinity" is a profit
factor with no losses to divide by — rendering 0.0 there would be a confident
wrong number.

Shaped against the real `build_overview` payload (services/overview.py), not
the earlier draft this contract was sketched from. Two figures the draft
described as bare floats are actually `{value, state}` pairs there:
`kpi.win_rate` (undefined below any sample — `services/overview._sample_pair`)
and `risk.edge_leak.amount` (undefined without followed_rules/mistake_tags
evidence — `services/overview._pair`). Both are `Undefinable` here rather than
`Optional[float]` + a sibling `*_state` field, matching how the service nests
them.

Every model is `extra="forbid"`. Pydantic's default (`extra="ignore"`) would
let `build_overview` grow a field this contract never learns about — silently
dropped from the response, `openapi.json` never regenerated to mention it, and
the TypeScript drift gate staying green over a contract that has quietly
stopped describing reality. `Undefinable.value`/`.state` also drop their
`= None` defaults: `services/overview._pair`/`_sample_pair` always emit both
keys together, so a payload missing one of them means the service's shape
changed underneath this contract. `_need()` in services/overview.py exists to
make exactly that loud rather than degrading into a plausible-looking null;
this mirrors that here, at the boundary.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

UndefinedState = Literal[
    "undefined_nan",
    "undefined_positive_infinity",
    "undefined_negative_infinity",
    "undefined_no_sample",
    "undefined_incomplete_sample",
]


class _Strict(BaseModel):
    """Base for every model below: an unexpected key means the service's
    shape moved out from under this contract, not a client sending noise."""

    model_config = ConfigDict(extra="forbid", strict=True)


class Period(_Strict):
    from_: str = Field(alias="from")
    to: str

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class SampleFlags(_Strict):
    trades: int
    dated_points: int
    show_summary: bool
    show_series: bool
    show_dominant_series: bool
    show_comparisons: bool
    show_patterns: bool
    pnl_recorded: int
    pnl_complete: bool


class Undefinable(_Strict):
    """A possibly-undefined number as {value, state}.

    Both fields are required (no `= None` default) even though both are
    `Optional` in type: `_pair`/`_sample_pair` on the service side always emit
    both keys together, so a payload with one missing is a shape change to
    catch here, not a plain absence to paper over with a default null.
    """

    value: Optional[float]
    state: Optional[UndefinedState]

    @model_validator(mode="after")
    def value_and_state_are_exclusive(self) -> "Undefinable":
        if (self.value is None) == (self.state is None):
            raise ValueError("exactly one of value or state must be present")
        return self


class Kpi(_Strict):
    net_pnl: Undefinable
    win_rate: Undefinable
    expectancy: Optional[float]
    expectancy_state: Optional[UndefinedState]
    profit_factor: Optional[float]
    profit_factor_state: Optional[UndefinedState]
    trades: int
    wins: int
    losses: int
    today_pnl: Undefinable
    week_pnl: Undefinable

    @model_validator(mode="after")
    def undefined_kpis_have_a_reason(self) -> "Kpi":
        for value, state, name in (
            (self.expectancy, self.expectancy_state, "expectancy"),
            (self.profit_factor, self.profit_factor_state, "profit_factor"),
        ):
            if (value is None) == (state is None):
                raise ValueError(f"exactly one of {name} or {name}_state is required")
        return self


class RuleAdherence(_Strict):
    rate: Optional[float]
    followed: int
    recorded: int


class EdgeLeak(_Strict):
    amount: Undefinable
    trades: int
    recorded: int


class Risk(_Strict):
    max_drawdown: Undefinable
    rule_adherence: RuleAdherence
    edge_leak: EdgeLeak
    consistency: Undefinable


class EquityPoint(_Strict):
    date: str
    equity: float


class Trajectory(_Strict):
    equity_curve: List[EquityPoint]
    current_streak: int
    streak_type: Literal["win", "loss", "none"]
    best_streak: int
    worst_streak: int
    average_win: Undefinable
    average_loss: Undefinable


class BreakdownRow(_Strict):
    label: str
    net_pnl: float
    trades: int


class RecurringEdge(_Strict):
    killzones: List[BreakdownRow]
    setups: List[BreakdownRow]


class CalendarDay(_Strict):
    date: str
    pnl: Optional[float]
    outcome: Literal["positive", "negative", "flat", "unknown"]

    @model_validator(mode="after")
    def outcome_matches_pnl(self) -> "CalendarDay":
        if self.pnl is None:
            if self.outcome != "unknown":
                raise ValueError("missing P&L requires an unknown outcome")
            return self
        expected = (
            "positive" if self.pnl > 0 else "negative" if self.pnl < 0 else "flat"
        )
        if self.outcome != expected:
            raise ValueError("calendar outcome contradicts P&L")
        return self


class Calendar(_Strict):
    year: int
    month: int
    days: List[CalendarDay]


class NextReviewAction(_Strict):
    """The trader's position on the activation path.

    `next_key` is a closed set rather than a free string, so the generated
    TypeScript is a union the client can key its copy off exhaustively. It was
    a bare `str`, and the web card was written against three invented spellings
    — two of which no service ever emits, so the card fell through to "the
    activation path is complete" while it displayed "1 of 3 done". A union
    makes that a compile error instead of a contradiction on screen.
    `tests/test_activation.py` pins these members to `activation.STEP_KEYS`.
    """

    completed: int
    total: int
    next_key: Optional[Literal["strategy", "first_trade", "weekly_review"]]
    is_activated: bool
    trades_until_review: int


class RecentTrade(_Strict):
    id: int
    trade_date: Optional[str]
    asset: Optional[str]
    session: Optional[str]
    setup_type: Optional[str]
    result: Optional[Literal["Win", "Loss", "Breakeven"]]
    pnl: Optional[float]
    rr_realized: Optional[float]


class OverviewResponse(_Strict):
    period: Period
    sample: SampleFlags
    kpi: Kpi
    risk: Risk
    trajectory: Trajectory
    recurring_edge: RecurringEdge
    calendar: Calendar
    next_review_action: NextReviewAction
    recent_trades: List[RecentTrade]
