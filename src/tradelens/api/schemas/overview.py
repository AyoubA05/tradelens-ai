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

from typing import List, Optional

from pydantic import BaseModel, Field


class _Strict(BaseModel):
    """Base for every model below: an unexpected key means the service's
    shape moved out from under this contract, not a client sending noise."""

    model_config = {"extra": "forbid"}


class Period(_Strict):
    from_: str = Field(alias="from")
    to: str

    model_config = {"extra": "forbid", "populate_by_name": True}


class SampleFlags(_Strict):
    trades: int
    dated_points: int
    show_summary: bool
    show_series: bool
    show_dominant_series: bool
    show_comparisons: bool
    show_patterns: bool


class Undefinable(_Strict):
    """A possibly-undefined number as {value, state}.

    Both fields are required (no `= None` default) even though both are
    `Optional` in type: `_pair`/`_sample_pair` on the service side always emit
    both keys together, so a payload with one missing is a shape change to
    catch here, not a plain absence to paper over with a default null.
    """

    value: Optional[float]
    state: Optional[str]


class Kpi(_Strict):
    net_pnl: float
    win_rate: Undefinable
    expectancy: Optional[float] = None
    expectancy_state: Optional[str] = None
    profit_factor: Optional[float] = None
    profit_factor_state: Optional[str] = None
    trades: int
    wins: int
    losses: int
    today_pnl: float
    week_pnl: float


class RuleAdherence(_Strict):
    rate: Optional[float] = None
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
    current_streak: Optional[int] = None
    streak_type: Optional[str] = None
    best_streak: Optional[int] = None
    worst_streak: Optional[int] = None
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
    pnl: float
    outcome: str


class Calendar(_Strict):
    year: int
    month: int
    days: List[CalendarDay]


class NextReviewAction(_Strict):
    completed: int
    total: int
    next_key: Optional[str] = None
    is_activated: bool
    trades_until_review: int


class RecentTrade(_Strict):
    id: int
    trade_date: Optional[str] = None
    asset: Optional[str] = None
    session: Optional[str] = None
    setup_type: Optional[str] = None
    result: Optional[str] = None
    pnl: Optional[float] = None
    rr_realized: Optional[float] = None


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
