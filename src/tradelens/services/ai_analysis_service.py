"""
Persistence layer for AI screenshot analysis results.

Keeps all DB logic out of the Streamlit UI layer. No Streamlit imports here.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from src.tradelens.db.models import AIAnalysis, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ai_client import Usage
from src.tradelens.services.ownership import require_user_id


def _owned_trade(db, trade_id: int, user_id: int) -> Optional[Trade]:
    owner = require_user_id(user_id)
    return db.query(Trade).filter(Trade.id == trade_id, Trade.user_id == owner).first()


def _owned_analysis(db, analysis_id: int, user_id: int) -> Optional[AIAnalysis]:
    owner = require_user_id(user_id)
    return (
        db.query(AIAnalysis)
        .join(Trade, Trade.id == AIAnalysis.trade_id)
        .filter(AIAnalysis.id == analysis_id, Trade.user_id == owner)
        .first()
    )


def get_analysis_for_trade(trade_id: int, *, user_id: int) -> Optional[AIAnalysis]:
    """Return the saved AIAnalysis row for a trade, or None if not yet run."""
    db = SessionLocal()
    try:
        owner = require_user_id(user_id)
        return (
            db.query(AIAnalysis)
            .join(Trade, Trade.id == AIAnalysis.trade_id)
            .filter(AIAnalysis.trade_id == trade_id, Trade.user_id == owner)
            .first()
        )
    finally:
        db.close()


def create_or_update_analysis(
    trade_id: int,
    vision_result: dict,
    usage: Usage,
    prompt_version: str = "screenshot_v2",
    *,
    user_id: int,
) -> AIAnalysis:
    """
    Persist an AI screenshot analysis result.

    Inserts a new row if none exists for this trade; updates in-place on re-run.
    detected_setup is left null — Day 2 vision output has no clean setup field;
    the user fills it via the editable chip on the Trade Detail page.
    """
    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        if _owned_trade(db, trade_id, user_id) is None:
            raise ValueError("trade not found")
        row = db.query(AIAnalysis).filter(AIAnalysis.trade_id == trade_id).first()
        if row is None:
            row = AIAnalysis(trade_id=trade_id, created_at=now)
            db.add(row)

        row.model = usage.model
        row.prompt_version = prompt_version
        row.bias = vision_result.get("bias")
        row.detected_setup = None  # not available from Day 2 vision; user edits this
        row.zones_json = json.dumps(vision_result.get("key_zones", []))
        row.matched_strategy = vision_result.get("matched_strategy")
        row.mistakes_json = json.dumps(vision_result.get("possible_mistakes", []))
        row.missed_opps_json = json.dumps(vision_result.get("missed_opportunities", []))
        row.trade_quality = vision_result.get("trade_quality")
        row.raw_response_json = json.dumps(vision_result)
        row.tokens_input = usage.tokens_in
        row.tokens_output = usage.tokens_out
        row.cost_usd = usage.estimated_cost_usd
        row.updated_at = now

        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


def update_analysis_fields(analysis_id: int, *, user_id: int, **fields) -> AIAnalysis:
    """
    Partial update for user-confirmed labels (bias, detected_setup, trade_quality, zones_json).

    Also denormalizes bias → trades.bias and detected_setup → trades.setup_type so
    the Trades list and Home dashboard reflect user-confirmed values.
    """
    allowed = {
        "bias",
        "detected_setup",
        "trade_quality",
        "zones_json",
        "matched_strategy",
        "mistakes_json",
        "missed_opps_json",
    }
    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        row = _owned_analysis(db, analysis_id, user_id)
        if row is None:
            raise ValueError(f"AIAnalysis row {analysis_id} not found")

        for key, val in fields.items():
            if key in allowed:
                setattr(row, key, val)
        row.updated_at = now

        # denormalize confirmed labels back to the trade row
        trade = _owned_trade(db, row.trade_id, user_id)
        if trade:
            if "bias" in fields:
                trade.bias = fields["bias"]
            if "detected_setup" in fields and fields["detected_setup"]:
                trade.setup_type = fields["detected_setup"]

        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


def save_grade(analysis_id: int, grading_result: dict, *, user_id: int) -> AIAnalysis:
    """
    Persist grading JSON to aianalysis.grading_json and letter grade to trades.ai_grade.

    Does NOT overwrite trades.user_grade.
    """
    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        row = _owned_analysis(db, analysis_id, user_id)
        if row is None:
            raise ValueError(f"AIAnalysis row {analysis_id} not found")
        row.grading_json = json.dumps(grading_result)
        row.updated_at = now

        trade = _owned_trade(db, row.trade_id, user_id)
        if trade:
            trade.ai_grade = grading_result.get("grade")

        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()


def save_user_grade(trade_id: int, grade: Optional[str], *, user_id: int) -> Trade:
    """
    Persist user-override grade to trades.user_grade.

    Pass None to clear the override back to NULL. Does NOT overwrite ai_grade.
    """
    db = SessionLocal()
    try:
        trade = _owned_trade(db, trade_id, user_id)
        if trade is None:
            raise ValueError(f"Trade {trade_id} not found")
        trade.user_grade = grade  # None clears the override
        db.commit()
        db.refresh(trade)
        return trade
    finally:
        db.close()


# ---------------------------------------------------------------------------
# SMC/ICT pre-fill (week5-d1.6)
# ---------------------------------------------------------------------------

# Bool-typed SMC trade columns (stored as 0/1); htf_bias is a free string.
_SMC_BOOL_KEYS = ("liquidity_sweep", "fvg_used", "order_block_used")
_SMC_PREFILL_KEYS = ("htf_bias",) + _SMC_BOOL_KEYS


def get_smc_prefill(trade: Trade, analysis: Optional[AIAnalysis]) -> dict:
    """Return SMC/ICT pre-fill values for the Trade Detail form.

    The user's existing trade value always takes priority; only when it is unset
    do we fall back to the AI's proposal from the stored vision analysis. This
    guarantees AI suggestions never silently overwrite values the user entered.

    Bool fields are returned as 0/1 (matching the trade columns); htf_bias as a
    string. Returns None for a field with neither a user value nor a proposal.
    """
    proposals: dict = {}
    if analysis is not None and analysis.raw_response_json:
        try:
            proposals = json.loads(analysis.raw_response_json)
        except (json.JSONDecodeError, TypeError):
            proposals = {}

    out: dict = {}
    for key in _SMC_PREFILL_KEYS:
        user_val = getattr(trade, key, None)
        if user_val is not None:
            out[key] = user_val
            continue
        ai_val = proposals.get(key)
        if key in _SMC_BOOL_KEYS:
            out[key] = None if ai_val is None else (1 if ai_val else 0)
        else:
            out[key] = ai_val
    return out


def save_trade_smc(trade_id: int, *, user_id: int, **fields) -> Trade:
    """Persist user-confirmed SMC/ICT values to the trade row.

    Only known SMC columns are written; unknown keys are ignored. Does not touch
    any AI analysis row — these are the trader's confirmed values.
    """
    allowed = set(_SMC_PREFILL_KEYS)
    db = SessionLocal()
    try:
        trade = _owned_trade(db, trade_id, user_id)
        if trade is None:
            raise ValueError(f"Trade {trade_id} not found")
        for key, val in fields.items():
            if key in allowed:
                setattr(trade, key, val)
        db.commit()
        db.refresh(trade)
        return trade
    finally:
        db.close()


def save_journal(analysis_id: int, markdown: str, *, user_id: int) -> AIAnalysis:
    """Persist a generated journal entry to aianalysis.journal_entry_md."""
    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        row = _owned_analysis(db, analysis_id, user_id)
        if row is None:
            raise ValueError(f"AIAnalysis row {analysis_id} not found")
        row.journal_entry_md = markdown
        row.updated_at = now
        db.commit()
        db.refresh(row)
        return row
    finally:
        db.close()
