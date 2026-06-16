# Skill: AI Service Editor

You are editing TradeLens AI services — the business logic layer.

## Absolute rules in this mode

- NEVER import Streamlit in any file under src/tradelens/services/ or src/tradelens/db/
- ALL Anthropic SDK calls go through src/tradelens/services/ai_client.py — never call the SDK directly
- Log tokens_input, tokens_output, cost_usd on EVERY AI call to the ai_analysis table
- Use effort="medium" by default; effort="high" for weekly review only
- If stop_reason == "refusal" → retry once with a fallback model; if that fails → return typed AIUnavailable
- Use prompt caching (cache_control on system block) for Strategy Profile text — it repeats across calls
- DEMO_MODE=true → return cached/mock output immediately, zero API spend

## Model routing

| Model | Use |
|---|---|
| `claude-opus-4-8` | Vision, journal, full grading, weekly review, pattern detection, AI partner chat |
| `claude-haiku-4-5` | Grading pre-pass only (cheap first-pass) |

## Before editing any service file

1. Read the existing function signatures — do not change them unless stated in the plan
2. Write the failing test first, then implement until green (TDD)
3. Run pytest -q after every change — do not proceed if any test fails

## What services/ contains

- ai_client.py — single AI wrapper (ALL calls go here)
- vision.py — screenshot analysis (claude-opus-4-8, base64 image blocks)
- journal.py — journal generation (claude-opus-4-8)
- grading.py — trade grading (haiku pre-pass + opus-4-8 full grade)
- weekly.py — weekly review (claude-opus-4-8, effort=high)
- patterns.py — pattern detection (deterministic pandas + one opus-4-8 call)
- corrections.py — few-shot correction memory builder
- sessions.py — assign_killzone() pure function, no AI
- metrics.py — pure pandas aggregations, no AI, no Streamlit
- partner.py — AI partner chat (claude-opus-4-8, scope guard enforced)
