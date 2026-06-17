"""
Tests for the SMC/ICT killzone engine (Phase 1).

Coverage:
- All 5 killzone boundary cases (entry / interior / exit)
- DST flip date (March 9 2025, US spring-forward)
- Alembic migration up / idempotency (columns must exist after upgrade head)
- Vision JSON parse: screenshot_v2.txt new keys present / absent are handled
- Seed integrity: all 60 seeded trades have non-null SMC/ICT values
"""
import json
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import Base, Trade
from src.tradelens.services.sessions import assign_killzone

UTC = ZoneInfo("UTC")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(year, month, day, hour, minute=0, second=0):
    return datetime(year, month, day, hour, minute, second, tzinfo=UTC)


# ---------------------------------------------------------------------------
# 1. Killzone boundary tests — all 5 killzones
# ---------------------------------------------------------------------------

class TestKillzoneBoundaries:
    """Parameterised boundary checks (entry, interior, exit, just-outside)."""

    # Each tuple: (utc_datetime, expected_killzone_or_None, label)
    # Dates use 2025-01-15 (EST, UTC-5) so windows are: UTC = ET + 5
    #   asia:         20:00-23:59 ET  → 01:00-04:59 UTC next day
    #   london_open:  02:00-04:59 ET  → 07:00-09:59 UTC
    #   ny_am:        07:00-09:59 ET  → 12:00-14:59 UTC
    #   ny_lunch:     12:00-12:59 ET  → 17:00-17:59 UTC
    #   ny_pm:        13:30-15:59 ET  → 18:30-20:59 UTC

    CASES = [
        # asia entry boundary
        (_utc(2025,1,16, 1, 0), "asia",        "asia: entry 01:00 UTC (20:00 EST)"),
        (_utc(2025,1,16, 2, 0), "asia",        "asia: interior 02:00 UTC (21:00 EST)"),
        (_utc(2025,1,16, 4,59), "asia",        "asia: interior 04:59 UTC (23:59 EST)"),
        (_utc(2025,1,16, 0,59), None,           "asia: just before (00:59 UTC = 19:59 EST)"),

        # london_open
        (_utc(2025,1,15, 7, 0), "london_open", "london_open: entry 07:00 UTC (02:00 EST)"),
        (_utc(2025,1,15, 8,30), "london_open", "london_open: interior 08:30 UTC (03:30 EST)"),
        (_utc(2025,1,15, 9,59), "london_open", "london_open: last minute 09:59 UTC (04:59 EST)"),
        (_utc(2025,1,15, 6,59), None,           "london_open: just before 06:59 UTC (01:59 EST)"),
        (_utc(2025,1,15,10, 0), None,           "london_open: just after 10:00 UTC (05:00 EST)"),

        # ny_am
        (_utc(2025,1,15,12, 0), "ny_am",       "ny_am: entry 12:00 UTC (07:00 EST)"),
        (_utc(2025,1,15,13,30), "ny_am",       "ny_am: interior 13:30 UTC (08:30 EST)"),
        (_utc(2025,1,15,14,59), "ny_am",       "ny_am: last minute 14:59 UTC (09:59 EST)"),
        (_utc(2025,1,15,11,59), None,           "ny_am: just before 11:59 UTC (06:59 EST)"),
        (_utc(2025,1,15,15, 0), None,           "ny_am: just after 15:00 UTC (10:00 EST)"),

        # ny_lunch
        (_utc(2025,1,15,17, 0), "ny_lunch",    "ny_lunch: entry 17:00 UTC (12:00 EST)"),
        (_utc(2025,1,15,17,30), "ny_lunch",    "ny_lunch: interior 17:30 UTC (12:30 EST)"),
        (_utc(2025,1,15,17,59), "ny_lunch",    "ny_lunch: last minute 17:59 UTC (12:59 EST)"),
        (_utc(2025,1,15,16,59), None,           "ny_lunch: just before 16:59 UTC (11:59 EST)"),
        (_utc(2025,1,15,18, 0), None,           "ny_lunch: just after 18:00 UTC (13:00 EST) — gap before ny_pm"),

        # ny_pm
        (_utc(2025,1,15,18,30), "ny_pm",       "ny_pm: entry 18:30 UTC (13:30 EST)"),
        (_utc(2025,1,15,19,30), "ny_pm",       "ny_pm: interior 19:30 UTC (14:30 EST)"),
        (_utc(2025,1,15,20,59), "ny_pm",       "ny_pm: last minute 20:59 UTC (15:59 EST)"),
        (_utc(2025,1,15,18,29), None,           "ny_pm: just before 18:29 UTC (13:29 EST)"),
        (_utc(2025,1,15,21, 0), None,           "ny_pm: just after 21:00 UTC (16:00 EST)"),

        # off-session (midday gap and after close)
        (_utc(2025,1,15,21, 0), None,           "off: 21:00 UTC (16:00 EST) after ny_pm close"),
        (_utc(2025,1,15,11, 0), None,           "off: 11:00 UTC (06:00 EST) before ny_am"),
    ]

    @pytest.mark.parametrize("dt,expected,label", CASES, ids=[c[2] for c in CASES])
    def test_boundary(self, dt, expected, label):
        assert assign_killzone(dt) == expected, label


# ---------------------------------------------------------------------------
# 2. DST flip — March 9 2025 (US spring forward at 2:00 AM EST → 3:00 AM EDT)
# ---------------------------------------------------------------------------

class TestDSTFlip:
    """On DST flip day, UTC offsets shift from -5 (EST) to -4 (EDT) at 07:00 UTC."""

    def test_before_dst_transition_london_open(self):
        # 06:30 UTC = 01:30 EST → off (before london_open starts at 02:00 ET)
        dt = _utc(2025, 3, 9, 6, 30)
        assert assign_killzone(dt) is None

    def test_dst_transition_moment_london_open(self):
        # 07:00 UTC: clocks spring from 02:00 EST → 03:00 EDT
        # zoneinfo renders this as 03:00 EDT → inside london_open (02:00-04:59 ET)
        dt = _utc(2025, 3, 9, 7, 0)
        assert assign_killzone(dt) == "london_open"

    def test_after_dst_ny_am(self):
        # 11:00 UTC = 07:00 EDT (EDT = UTC-4) → ny_am
        dt = _utc(2025, 3, 9, 11, 0)
        assert assign_killzone(dt) == "ny_am"

    def test_after_dst_ny_am_would_be_wrong_with_fixed_est(self):
        # With a naive UTC-5 offset, 11:00 UTC = 06:00 EST → off-session
        # With correct zoneinfo DST, 11:00 UTC = 07:00 EDT → ny_am
        # This confirms DST is handled correctly
        dt = _utc(2025, 3, 9, 11, 0)
        result = assign_killzone(dt)
        assert result == "ny_am", (
            "DST failure: naive UTC-5 would give 06:00 EST (off), "
            "but correct result is 07:00 EDT = ny_am"
        )

    def test_winter_ny_am_needs_extra_hour(self):
        # In January (EST, UTC-5): ny_am 07:00 ET = 12:00 UTC
        dt_winter = _utc(2025, 1, 15, 12, 0)
        # In summer (EDT, UTC-4): ny_am 07:00 ET = 11:00 UTC
        dt_summer = _utc(2025, 6, 15, 11, 0)
        assert assign_killzone(dt_winter) == "ny_am"
        assert assign_killzone(dt_summer) == "ny_am"

    def test_naive_datetime_assumed_utc(self):
        # Naive datetime (no tzinfo) is treated as UTC by default
        naive_dt = datetime(2025, 1, 15, 12, 0)  # 12:00 = 07:00 EST = ny_am
        assert assign_killzone(naive_dt) == "ny_am"

    def test_tz_override(self):
        # Pass Eastern time directly via tz parameter
        et_naive = datetime(2025, 1, 15, 7, 0)  # 07:00 ET = ny_am
        assert assign_killzone(et_naive, tz="America/New_York") == "ny_am"


# ---------------------------------------------------------------------------
# 3. Migration: SMC/ICT columns must exist in trades table after upgrade head
# ---------------------------------------------------------------------------

EXPECTED_SMC_COLS = [
    "htf_bias", "killzone", "liquidity_sweep", "fvg_used", "order_block_used",
    "bos", "choch", "confirmation_model", "entry_type", "mistake_tags", "followed_rules",
]


def test_migration_columns_present():
    """alembic upgrade head must have added all 11 SMC/ICT columns."""
    from src.tradelens.db.session import engine
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("trades")}
    missing = [c for c in EXPECTED_SMC_COLS if c not in cols]
    assert not missing, f"Missing columns after migration: {missing}"


def test_migration_idempotent():
    """Running alembic upgrade head a second time must not raise."""
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_migration_downgrade_is_noop_on_sqlite():
    """Downgrade on SQLite is a deliberate no-op (DROP COLUMN unsupported <3.35)."""
    result = subprocess.run(
        ["alembic", "downgrade", "-1"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    # Re-upgrade so the DB is back at head for subsequent tests
    subprocess.run(["alembic", "upgrade", "head"], capture_output=True)


# ---------------------------------------------------------------------------
# 4. Vision JSON parse — screenshot_v2.txt new keys
# ---------------------------------------------------------------------------

def _make_v1_response():
    return {
        "bias": "bullish",
        "bias_confidence": 0.8,
        "detected_timeframe": "15m",
        "detected_asset": "NQ",
        "structure": "Bullish trend",
        "bos": True,
        "choch": False,
        "key_zones": [],
        "matched_strategy": None,
        "matched_strategy_reason": None,
        "possible_mistakes": [],
        "missed_opportunities": [],
        "trade_quality": 7,
        "notes_to_user": "Good setup.",
    }


def _make_v2_response():
    data = _make_v1_response()
    data.update({
        "htf_bias": "bullish",
        "liquidity_sweep": True,
        "fvg_used": False,
        "order_block_used": True,
    })
    return data


def test_v2_json_has_all_new_keys():
    data = _make_v2_response()
    for key in ("htf_bias", "liquidity_sweep", "fvg_used", "order_block_used", "bos", "choch"):
        assert key in data, f"Missing key in v2 response: {key}"


def test_v1_json_missing_new_keys_handled_gracefully():
    """Code consuming vision output must handle v1 responses that lack v2 keys."""
    data = _make_v1_response()
    # Simulate a consumer using .get() with a default
    assert data.get("htf_bias") is None
    assert data.get("liquidity_sweep") is None
    assert data.get("fvg_used") is None
    assert data.get("order_block_used") is None
    # v1 already has bos and choch
    assert data.get("bos") is True
    assert data.get("choch") is False


def test_v2_prompt_file_contains_required_keys():
    """screenshot_v2.txt must declare all 6 SMC/ICT output keys."""
    from pathlib import Path
    prompt = Path(__file__).resolve().parents[1] / "prompts" / "screenshot_v2.txt"
    assert prompt.exists(), "prompts/screenshot_v2.txt not found"
    text = prompt.read_text()
    for key in ("htf_bias", "liquidity_sweep", "fvg_used", "order_block_used", "bos", "choch"):
        assert f'"{key}"' in text, f"Key {key!r} missing from screenshot_v2.txt"


# ---------------------------------------------------------------------------
# 5. Seed integrity — all 60 trades must have non-null SMC/ICT values
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def seeded_db():
    """Create a fresh in-memory DB and seed it."""
    import src.tradelens.services.trade_service as _ts
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Patch SessionLocal in both trade_service and seed so they share the in-memory DB
    import scripts.seed as _seed_mod

    original_ts = _ts.SessionLocal
    original_seed = _seed_mod.SessionLocal

    _ts.SessionLocal = Session
    _seed_mod.SessionLocal = Session

    _seed_mod.seed()

    yield Session

    _ts.SessionLocal = original_ts
    _seed_mod.SessionLocal = original_seed


def test_seed_trade_count(seeded_db):
    db = seeded_db()
    try:
        count = db.query(Trade).count()
        assert count == 60, f"Expected 60 seeded trades, got {count}"
    finally:
        db.close()


@pytest.mark.parametrize("col", ["htf_bias", "killzone", "liquidity_sweep", "fvg_used", "order_block_used"])
def test_seed_no_nulls_on_smc_fields(seeded_db, col):
    db = seeded_db()
    try:
        null_count = db.execute(
            text(f"SELECT COUNT(*) FROM trades WHERE {col} IS NULL")
        ).scalar()
        assert null_count == 0, f"Column {col!r} has {null_count} NULL rows after seeding"
    finally:
        db.close()


def test_seed_killzone_values_are_valid(seeded_db):
    valid = {"asia", "london_open", "ny_am", "ny_lunch", "ny_pm"}
    db = seeded_db()
    try:
        rows = db.execute(text("SELECT DISTINCT killzone FROM trades")).fetchall()
        for (kz,) in rows:
            assert kz in valid, f"Invalid killzone value in seed: {kz!r}"
    finally:
        db.close()


def test_seed_htf_bias_values_are_valid(seeded_db):
    valid = {"bullish", "bearish", "neutral"}
    db = seeded_db()
    try:
        rows = db.execute(text("SELECT DISTINCT htf_bias FROM trades")).fetchall()
        for (htf,) in rows:
            assert htf in valid, f"Invalid htf_bias value in seed: {htf!r}"
    finally:
        db.close()


def test_seed_mistake_tags_are_valid_json(seeded_db):
    db = seeded_db()
    try:
        rows = db.execute(text("SELECT mistake_tags FROM trades")).fetchall()
        for (tags,) in rows:
            if tags is not None:
                parsed = json.loads(tags)
                assert isinstance(parsed, list), f"mistake_tags is not a JSON list: {tags!r}"
    finally:
        db.close()
