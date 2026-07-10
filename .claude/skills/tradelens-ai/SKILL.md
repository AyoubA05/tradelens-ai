---
name: tradelens-ai
description: Project guardrails and stack rules for TradeLens AI. Use this skill for ANY work in the tradelens-ai repo — UI changes, page edits, CSS/design work, AI prompt or service changes, copy/text edits, chart styling, database queries, or tests. Always consult it before writing code, UI copy, or AI-facing text in this project, even for small tweaks, because it encodes hard safety-language and design-token rules that all changes must pass.
---

# TradeLens AI — Project Rules

## What TradeLens is (and is not)

TradeLens AI is a **post-trade journal and analytics tool only**. Traders log
completed trades and reflect on them. It is never a signal app, never live
trade advice, never prediction. The AI analyzes past trades only; all AI
output is read-only, reflection-only, never auto-applied.

Why this matters: predictive or signal-like language creates regulatory and
user-harm risk, and the repo's tests lint-gate it. One stray word in UI copy
can fail CI and misrepresent the product.

### Blocked language

Never use these in code, UI copy, prompts, or AI output:
"entry signal", "live trade", "buy now", "go long", "go short",
"trade this", "signal", "alert".

Prefer reflective phrasing: "observation", "pattern", "review",
"what the chart showed", "post-trade note".

## Stack (fixed)

Python + Streamlit + SQLAlchemy + SQLite + Pandas + Plotly.
- No React. No FastAPI migration.
- No new dependencies without asking the owner first.
- Repo pins: streamlit==1.50.0, plotly==6.7.0 — use APIs valid at these versions.

## Database

DB schema is **read-only** for UI/polish work. No ALTER TABLE. No schema
changes. Query existing tables only.

## Design tokens

Design tokens live in `src/tradelens/ui/design_system.py`. These tokens are
the source of truth. Never override them inline, never re-type hex values in
pages or components. If a color/spacing/radius isn't a token, add it as a
token first (or ask), then reference it.

## Screenshot AI provenance & confidence rules

For the screenshot-analysis feature, every extracted field carries a
provenance badge with exactly one of:
- "Read from label"
- "Estimated from markup"
- "Not visible"

Confidence rules:
- confidence >= 0.70 → field auto-checked
- confidence < 0.70 → field unchecked, needs user confirmation

Color rule: **red is for errors only — never for checkbox states.** Checked
field indicators use the primary (teal) badge style.

## Related contracts

- `PRODUCT.md` (repo root) — design/tone contract and anti-pattern list
- `CLAUDE.md` — commands, test/lint requirements, architecture rules
- `.claude/MEMORY.md` — session decision log; append significant decisions
