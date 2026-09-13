"""The Settings wire contract.

Every model is `_Strict` (`extra="forbid"`, `strict=True`): a renamed or added
field is a loud failure, never a silently ignored one. No request model names
an owner, a user, a trade, a path or an object key — the owner is the session.
The two destructive writes carry their typed confirmation as a `Literal`, so a
request that reaches the route body has already typed the phrase exactly.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import Field

from src.tradelens.api.schemas.trades import _Strict

# A JSON-escaped CSV must fit inside the API's 1 MiB body cap (decision S4).
MAX_IMPORT_CSV_CHARS = 900_000


class SettingsAccount(_Strict):
    username: str
    email: Optional[str]
    email_verified: bool


class SettingsTimezone(_Strict):
    current: str
    options: List[str]


class SettingsAI(_Strict):
    state: Literal["enabled", "demo", "unavailable"]


class SettingsData(_Strict):
    trade_count: int
    sample_count: int
    csv_columns: List[str]
    max_import_rows: int


class SettingsCostRow(_Strict):
    feature: str
    cost_usd: float
    calls: int


class SettingsCost(_Strict):
    month: str
    total_usd: float
    rows: List[SettingsCostRow]


class SettingsResponse(_Strict):
    account: SettingsAccount
    timezone: SettingsTimezone
    ai: SettingsAI
    data: SettingsData
    cost: SettingsCost
    reset_email_configured: bool
    demo_mode: bool


class TimezoneWrite(_Strict):
    timezone: str = Field(max_length=64)


class SampleTradesResponse(_Strict):
    count: int
    sample_count: int


class CsvExportResponse(_Strict):
    filename: Literal["trades.csv"]
    row_count: int
    csv: str


class CsvImportWrite(_Strict):
    csv: str = Field(min_length=1, max_length=MAX_IMPORT_CSV_CHARS)


class CsvImportResponse(_Strict):
    inserted: int
    skipped: int
    errors: List[str]


class DeleteTradesWrite(_Strict):
    confirm: Literal["DELETE"]


class DeleteAccountWrite(_Strict):
    confirm: Literal["DELETE MY ACCOUNT"]


class DeleteTradesResponse(_Strict):
    deleted: int
