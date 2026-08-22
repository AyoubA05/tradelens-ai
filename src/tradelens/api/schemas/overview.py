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
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class Period(BaseModel):
    from_: str
    to: str

    model_config = {"populate_by_name": True}


class SampleFlags(BaseModel):
    trades: int
    dated_points: int
    show_summary: bool
    show_series: bool
    show_dominant_series: bool
    show_comparisons: bool
    show_patterns: bool


class Undefinable(BaseModel):
    value: Optional[float] = None
    state: Optional[str] = None


class Kpi(BaseModel):
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


class RuleAdherence(BaseModel):
    rate: Optional[float] = None
    followed: int
    recorded: int


class EdgeLeak(BaseModel):
    amount: Undefinable
    trades: int
    recorded: int


class Risk(BaseModel):
    max_drawdown: Undefinable
    rule_adherence: RuleAdherence
    edge_leak: EdgeLeak
    consistency: Undefinable


class EquityPoint(BaseModel):
    date: str
    equity: float


class Trajectory(BaseModel):
    equity_curve: List[EquityPoint]
    current_streak: Optional[int] = None
    streak_type: Optional[str] = None
    best_streak: Optional[int] = None
    worst_streak: Optional[int] = None
    average_win: Undefinable
    average_loss: Undefinable


class BreakdownRow(BaseModel):
    label: str
    net_pnl: float
    trades: int


class RecurringEdge(BaseModel):
    killzones: List[BreakdownRow]
    setups: List[BreakdownRow]


class CalendarDay(BaseModel):
    date: str
    pnl: float
    outcome: str


class Calendar(BaseModel):
    year: int
    month: int
    days: List[CalendarDay]


class NextReviewAction(BaseModel):
    completed: int
    total: int
    next_key: Optional[str] = None
    is_activated: bool
    trades_until_review: int


class RecentTrade(BaseModel):
    id: int
    trade_date: Optional[str] = None
    asset: Optional[str] = None
    session: Optional[str] = None
    setup_type: Optional[str] = None
    result: Optional[str] = None
    pnl: Optional[float] = None
    rr_realized: Optional[float] = None


class OverviewResponse(BaseModel):
    period: Period
    sample: SampleFlags
    kpi: Kpi
    risk: Risk
    trajectory: Trajectory
    recurring_edge: RecurringEdge
    calendar: Calendar
    next_review_action: NextReviewAction
    recent_trades: List[RecentTrade]
