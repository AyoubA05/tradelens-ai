# Agent: Vision Agent

Scope: screenshot analysis only — src/tradelens/services/vision.py

## This agent's job

Analyze a trading screenshot and return structured JSON proposals for SMC/ICT fields.
Output is ALWAYS editable by the user — never silently applied.

## Model

claude-opus-4-8 with base64 image blocks (PNG/JPG/WEBP)

## Output contract (prompts/screenshot_v2.txt — LOCKED)

Returns strict JSON. Week 5 adds these keys to the existing contract:
htf_bias, liquidity_sweep, fvg_used, order_block_used, bos, choch

## Rules

- Only propose values — never write directly to the DB
- If image is unreadable or ambiguous → return partial JSON with confidence flags
- All calls go through services/ai_client.py
- Log cost to ai_analysis table

## Do NOT touch

- Any other service file
- Any page file
- prompts/ contract structure
