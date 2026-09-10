"""The Strategy Profile wire contract.

Every model is `_Strict` (`extra="forbid"`, `strict=True`): a renamed or
added field is a loud failure on both sides, never a silently dropped rule.

The write model is a positive allowlist with every field REQUIRED. The save
is a full replacement, so an omitted field must be refused, not read as
"clear this rule". There is no id, owner or active flag anywhere in a
request: the profile is an owner-singleton and the owner is the session.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import Field

from src.tradelens.api.schemas.trades import _Strict

SectionId = Literal["identity", "entry", "exit", "risk", "setups", "self_awareness"]


class StrategyFields(_Strict):
    name: Optional[str]
    trading_style: Optional[str]
    markets: Optional[str]
    timeframes: Optional[str]
    entry_rules: Optional[str]
    stop_rules: Optional[str]
    take_profit_rules: Optional[str]
    risk_rules: Optional[str]
    setups_traded: Optional[str]
    setups_avoided: Optional[str]
    news_session_rules: Optional[str]
    common_mistakes: Optional[str]


class StrategyWrite(StrategyFields):
    """The whole playbook, plus the version it was edited from.

    `expected_revision` is compared, never adopted: the server derives the
    next version itself.
    """

    expected_revision: Optional[str] = Field(max_length=64)


class StrategyInsightRequest(_Strict):
    """Names one repeated-correction group. A lookup key, never rule text.

    There is deliberately no target-field key: the column is fixed server-side.
    """

    field: str = Field(min_length=1, max_length=200)
    user_value: str = Field(min_length=1, max_length=2000)
    expected_revision: Optional[str] = Field(max_length=64)


class StrategySection(_Strict):
    id: SectionId
    label: str
    written: bool


class StrategyFacets(_Strict):
    markets: List[str]
    entry_timeframe: Optional[str]
    htf_timeframe: Optional[str]
    setups: List[str]


class StrategySuggestion(_Strict):
    field: str
    user_value: str
    count: int
    rule: str


class StrategyLimits(_Strict):
    """Maximum characters per field — the one source the editor's counters read."""

    name: int
    trading_style: int
    markets: int
    timeframes: int
    entry_rules: int
    stop_rules: int
    take_profit_rules: int
    risk_rules: int
    setups_traded: int
    setups_avoided: int
    news_session_rules: int
    common_mistakes: int


class StrategyResponse(_Strict):
    profile: Optional[StrategyFields]
    revision: Optional[str]
    updated_at: Optional[str]
    sections: List[StrategySection]
    written: int
    total: int
    facets: StrategyFacets
    over_limit: List[str]
    limits: StrategyLimits
    starter: StrategyFields
    suggestions: List[StrategySuggestion]
    first_run: bool
