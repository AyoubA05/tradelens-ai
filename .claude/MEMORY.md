# TradeLens AI — Session Memory

## Project
AI-powered POST-TRADE day trading journal for SMC/ICT traders. NOT a signal app.
Stack: Python, Streamlit, SQLite (Alembic), OpenAI/Anthropic API, Plotly, Pandas.
Repo: /Users/ayoub/tradelens-ai

## Architecture
- All business logic: src/tradelens/services/*.py
- Streamlit pages only render — never contain logic
- AI calls only through services/ai_client.py
- DB changes via Alembic migrations only (reversible)
- Prompts: prompts/*_v2.txt — extend only, never rewrite contracts

## Current State (Week 5)
Building: SMC/ICT schema, killzone engine, pattern detection, weekly AI review,
correction memory, AI partner chat, consistency score, cost dashboard.
85+ tests target. Commit format: week5-d<N>: <summary>

## Key Rules
- DEMO_MODE=true in CI, false locally
- No live signals, predictions, or broker sync ever
- pytest -q must pass after every phase before committing
- ruff + black must pass before final commit
