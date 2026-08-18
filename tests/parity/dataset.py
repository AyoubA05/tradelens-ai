"""One fixed dataset, used by every parity assertion.

Deliberately hand-written rather than random or seeded-from-production: the
point is that the numbers below never change, so a difference in output can only
mean a change in computation. It covers the shapes that break metrics — a
losing trade, a break-even, a missing R multiple, a rule break, a trade with no
screenshot — because an all-wins dataset proves almost nothing.

Two encodings below are deliberately NOT the display form a UI might show:

- ``result`` uses ``"Breakeven"`` (no hyphen) — the only spelling
  ``trade_validation.VALID_OUTCOMES`` accepts. ``create_trade`` routes every
  write through ``canonical_outcome``, which raises ``ValueError`` for
  anything else.
- ``followed_rules`` uses ``1`` / ``0`` / ``None`` — the STORED form.
  ``Trade.followed_rules`` is an Integer column; the live New Trade page
  writes ``{"Yes": 1, "No": 0, "Partial": None}``. A snapshot built from the
  display strings ("Yes"/"No"/"Partial") would pin numbers no real row could
  produce.

``killzone`` is computed the same way the New Trade page computes it — via
``sessions.detect_killzone(entry_time, trade_date)`` — because it is a real
``Trade`` column that ``metrics.killzone_performance`` reads, and
``create_trade`` does not derive it automatically.
"""

from __future__ import annotations

from src.tradelens.services import trade_service
from src.tradelens.services.sessions import detect_killzone

GOLDEN_TRADES = [
    {
        "trade_date": "2026-08-10",
        "entry_time": "09:35",
        "asset": "NQ",
        "session": "New York Open",
        "setup_type": "Liquidity Sweep + FVG",
        "timeframe": "15m",
        "htf_bias": "Bullish",
        "result": "Win",
        "pnl": 480.0,
        "risk_amount": 180.0,
        "rr_realized": 2.7,
        "followed_rules": 1,
        "strategy_used": "ICT/SMC Day Trading",
    },
    {
        "trade_date": "2026-08-11",
        "entry_time": "09:50",
        "asset": "ES",
        "session": "New York Open",
        "setup_type": "Liquidity Sweep + FVG",
        "timeframe": "15m",
        "htf_bias": "Bearish",
        "result": "Loss",
        "pnl": -220.0,
        "risk_amount": 200.0,
        "rr_realized": None,
        "followed_rules": 0,
        "mistake_tags": '["Counter-trend entry"]',
        "strategy_used": "ICT/SMC Day Trading",
    },
    {
        "trade_date": "2026-08-12",
        "entry_time": "10:15",
        "asset": "NQ",
        "session": "New York Open",
        "setup_type": "BOS + OB Retest",
        "timeframe": "15m",
        "htf_bias": "Bullish",
        "result": "Win",
        "pnl": 410.0,
        "risk_amount": 150.0,
        "rr_realized": 2.73,
        "followed_rules": 1,
        "strategy_used": "ICT/SMC Day Trading",
    },
    {
        "trade_date": "2026-08-13",
        "entry_time": "11:05",
        "asset": "EURUSD",
        "session": "London",
        "setup_type": "CHoCH Entry",
        "timeframe": "15m",
        "htf_bias": "Bearish",
        "result": "Breakeven",
        "pnl": 0.0,
        "risk_amount": 120.0,
        "rr_realized": 0.0,
        "followed_rules": None,
        "strategy_used": "ICT/SMC Day Trading",
    },
    {
        "trade_date": "2026-08-14",
        "entry_time": "09:31",
        "asset": "NQ",
        "session": "New York Open",
        "setup_type": "Liquidity Sweep + FVG",
        "timeframe": "5m",
        "htf_bias": "Bullish",
        "result": "Loss",
        "pnl": -95.0,
        "risk_amount": 100.0,
        "rr_realized": -0.95,
        "followed_rules": 1,
        "strategy_used": "ICT/SMC Day Trading",
    },
]


def seed_golden_dataset(user_id: int) -> None:
    """Insert the golden trades for `user_id`. Order is significant."""
    for row in GOLDEN_TRADES:
        data = dict(row)
        data["killzone"] = detect_killzone(data["entry_time"], data["trade_date"])
        trade_service.create_trade({**data, "user_id": user_id}, user_id=user_id)
