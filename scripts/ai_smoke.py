"""
AI Smoke Test — manual end-to-end real-API test.

Usage:
    python scripts/ai_smoke.py

What it does:
  1. Picks the first trade in the DB that has an existing screenshot file on disk.
  2. Fetches the active strategy profile (may be None).
  3. Calls analyze_screenshot() and prints key outputs + cost.
  4. Calls generate_journal() and prints section headings found + first 200 chars.
  5. Calls grade_trade() and prints grade, score, verdict + cost.
  6. Prints a summary cost table.

This script is READ-ONLY — it does NOT persist anything to the DB.
It is intended for manual verification only and is excluded from CI.

Requirements:
  - OPENAI_API_KEY must be set in .env or environment
  - At least one trade with a screenshot that exists on disk
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script
_root = str(Path(__file__).resolve().parents[1])
if _root not in sys.path:
    sys.path.insert(0, _root)

import os

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(_root) / ".env")
except ImportError:
    pass

from src.tradelens.config import settings
from src.tradelens.db.session import SessionLocal
from src.tradelens.db.models import Trade, Screenshot
from src.tradelens.services.strategy import get_active_strategy
from src.tradelens.services.vision import analyze_screenshot, ScreenshotAnalysisError
from src.tradelens.services.journal import generate_journal, build_journal_context
from src.tradelens.services.grading import grade_trade, build_grading_context
from src.tradelens.db.models import AIAnalysis


def _find_eligible_trade():
    """Return (Trade, screenshot_path) for the first trade with an on-disk screenshot."""
    db = SessionLocal()
    try:
        trades = db.query(Trade).order_by(Trade.id).all()
        for t in trades:
            for s in (t.screenshots or []):
                if Path(s.file_path).exists():
                    return dict(
                        id=t.id, asset=t.asset, direction=t.direction,
                        result=t.result, pnl=t.pnl, session=t.session,
                        setup_type=t.setup_type, bias=t.bias, notes=t.notes,
                    ), s.file_path
    finally:
        db.close()
    return None, None


def _print_banner(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def main():
    # Guard: API key
    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY is not set. Add it to your .env file.")
        sys.exit(1)

    _print_banner("TradeLens AI Smoke Test")

    # Find eligible trade
    trade_ctx, screenshot_path = _find_eligible_trade()
    if trade_ctx is None:
        print("ERROR: No trade found with an existing screenshot on disk.")
        print("Seed the DB and upload at least one screenshot, then retry.")
        sys.exit(1)

    print(f"\nTrade #{trade_ctx['id']}  {trade_ctx['asset']}  {trade_ctx['direction'] or '?'}  {trade_ctx['result'] or '?'}")
    print(f"Screenshot: {screenshot_path}")

    active_strategy = get_active_strategy()
    if active_strategy:
        print(f"Strategy: {active_strategy.get('name', '—')}")
    else:
        print("Strategy: (none — using generic framework)")

    usages = []

    # ── Step 1: Vision analysis ──────────────────────────────────────
    _print_banner("Step 1: Screenshot Analysis")
    try:
        vision_result, v_usage = analyze_screenshot(
            screenshot_path, trade_ctx, strategy_profile=active_strategy
        )
        usages.append(("Vision (gpt-4o)", v_usage))
        print(f"  Bias:          {vision_result.get('bias')} ({vision_result.get('bias_confidence')})")
        print(f"  Setup:         {vision_result.get('detected_timeframe')} / {vision_result.get('detected_asset')}")
        print(f"  Trade Quality: {vision_result.get('trade_quality')}/10")
        print(f"  Mistakes:      {vision_result.get('possible_mistakes', [])}")
        print(f"  Notes:         {str(vision_result.get('notes_to_user', ''))[:120]}")
        print(f"  Cost: ${v_usage.estimated_cost_usd:.5f}  Tokens: {v_usage.tokens_in}↑ {v_usage.tokens_out}↓  Latency: {v_usage.latency_s:.1f}s")
    except ScreenshotAnalysisError as exc:
        print(f"  FAILED: {exc}")
        sys.exit(1)

    # Build a minimal AIAnalysis-like dict for downstream calls
    # (we don't persist — use a plain dict matching build_journal_context expectations)
    db = SessionLocal()
    try:
        # Try to find an existing persisted analysis for richer context
        analysis_orm = db.query(AIAnalysis).filter(AIAnalysis.trade_id == trade_ctx["id"]).first()
    finally:
        db.close()

    if analysis_orm is None:
        print("\n  NOTE: No persisted AIAnalysis found for this trade.")
        print("  Journal + grading will use fresh vision output only.")
        # Stub a minimal object for build_journal_context
        class _FakeAnalysis:
            bias = vision_result.get("bias")
            detected_setup = vision_result.get("matched_strategy")
            trade_quality = vision_result.get("trade_quality")
            journal_entry_md = None
            grading_json = None
            zones_json = None
            mistakes_json = None
            missed_opps_json = None
            matched_strategy = vision_result.get("matched_strategy")
            matched_strategy_reason = vision_result.get("matched_strategy_reason")

        analysis_orm = _FakeAnalysis()

    # ── Step 2: Journal generation ───────────────────────────────────
    _print_banner("Step 2: Journal Generation")

    # We need ORM Trade object for build_journal_context
    db = SessionLocal()
    try:
        trade_orm = db.query(Trade).filter(Trade.id == trade_ctx["id"]).first()
        trade_dict, ai_dict = build_journal_context(trade_orm, analysis_orm)
    finally:
        db.close()

    from src.tradelens.services.journal import generate_journal, JournalStructureError
    try:
        markdown, j_usage = generate_journal(trade_dict, ai_dict, strategy_profile=active_strategy)
        usages.append(("Journal (gpt-4o-mini)", j_usage))
        # Print section headings found
        headings = [line for line in markdown.splitlines() if line.startswith("### ")]
        print(f"  Sections found ({len(headings)}):")
        for h in headings:
            print(f"    {h}")
        print(f"  Preview: {markdown[:200].replace(chr(10), ' ')}…")
        print(f"  Cost: ${j_usage.estimated_cost_usd:.5f}  Tokens: {j_usage.tokens_in}↑ {j_usage.tokens_out}↓  Latency: {j_usage.latency_s:.1f}s")
    except JournalStructureError as exc:
        print(f"  FAILED (structure): {exc}")
    except Exception as exc:
        print(f"  FAILED: {exc}")

    # ── Step 3: Grading ──────────────────────────────────────────────
    _print_banner("Step 3: Trade Grading")

    db = SessionLocal()
    try:
        trade_orm2 = db.query(Trade).filter(Trade.id == trade_ctx["id"]).first()
        grade_trade_dict, vision_dict = build_grading_context(trade_orm2, analysis_orm)
    finally:
        db.close()

    from src.tradelens.services.grading import grade_trade, GradingError
    try:
        grading_result, g_usage = grade_trade(grade_trade_dict, active_strategy, vision_dict)
        usages.append(("Grading (gpt-4o-mini)", g_usage))
        print(f"  Grade:   {grading_result.get('grade')}  Score: {grading_result.get('score')}/10")
        print(f"  Verdict: {grading_result.get('one_line_verdict')}")
        rubric = grading_result.get("rubric", {})
        for dim, data in rubric.items():
            print(f"    {dim.replace('_',' ').title()}: {data.get('score')}/10 — {data.get('note','')[:60]}")
        print(f"  Cost: ${g_usage.estimated_cost_usd:.5f}  Tokens: {g_usage.tokens_in}↑ {g_usage.tokens_out}↓  Latency: {g_usage.latency_s:.1f}s")
    except GradingError as exc:
        print(f"  FAILED (grading): {exc}")
    except Exception as exc:
        print(f"  FAILED: {exc}")

    # ── Summary ──────────────────────────────────────────────────────
    _print_banner("Cost Summary")
    total_cost = 0.0
    print(f"  {'Step':<28} {'Model':<15} {'In':>6} {'Out':>6} {'Cost':>10} {'Latency':>8}")
    print(f"  {'-'*75}")
    for label, u in usages:
        print(f"  {label:<28} {u.model:<15} {u.tokens_in:>6} {u.tokens_out:>6} ${u.estimated_cost_usd:>8.5f} {u.latency_s:>6.1f}s")
        total_cost += u.estimated_cost_usd
    print(f"  {'-'*75}")
    print(f"  {'TOTAL':<50} ${total_cost:>8.5f}")

    print(f"\nSmoke test complete. No changes written to DB.\n")


if __name__ == "__main__":
    main()
