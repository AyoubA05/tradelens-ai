# CLAUDE.md

This file is automatically injected into every Claude Code session.
Read it fully before touching any file.

---

## Project Identity

TradeLens AI is a **post-trade reflection journal and analytics dashboard** for SMC/ICT day traders.

- ✅ Journaling, trade review, self-analysis, performance tracking, educational reflection
- ❌ NOT a signal app. NOT a bot. NOT a financial advice tool.
- ❌ Nothing in this repo may generate trade ideas, predictions, or live trading signals — including UI copy.

---

## Commands

```bash
# Setup
pip install -r requirements.txt
cp .env.example .env  # fill in ANTHROPIC_API_KEY

# Initialize DB
python -m src.tradelens.db.init_db

# Seed sample data (60 trades across 3 weeks, skips if trades exist)
python scripts/seed.py

# Run the app
streamlit run src/tradelens/ui/app.py

# Lint
ruff check src/ scripts/
black --check src/ scripts/

# Test
pytest tests/ -v --tb=short

# Run a single test file
pytest tests/test_foo.py -v

# Alembic migrations
alembic upgrade head
alembic downgrade -1
alembic revision --autogenerate -m "description"
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| UI | Streamlit (multi-page) |
| ORM | SQLAlchemy 2.x |
| Database | SQLite (dev) → PostgreSQL (prod) |
| Migrations | Alembic (every schema change; downgrade always implemented) |
| AI | Anthropic API — `claude-opus-5` for every feature (single model, no fallback) |
| Visualization | Plotly |
| Data | Pandas, NumPy |
| Testing | pytest |
| Linting | ruff, black |
| Secrets | `st.secrets` / environment — never hardcoded |

---

## TradeLens AI — Week 5 Rules

**Project identity:** TradeLens AI is a post-trade reflection journal. NOT a signal app, NOT a bot, NOT financial advice.

**Current week goal:** Week 5 — SMC/ICT schema, killzone engine, pattern detection, weekly AI review, correction memory, AI partner mode, hardening. Target: 85+ passing tests.

**AI model — one model, no routing:**
- `claude-opus-5` for every feature: screenshot analysis, autofill, grading, journal summaries, pattern analysis, weekly recaps, daily debriefs, AI partner
- The model ID lives in ONE place: `ANTHROPIC_MODEL_ID` in src/tradelens/config.py. It is not env-overridable and there is no per-feature selection and no automatic fallback model
- All AI calls go through services/ai_client.py ONLY — never call the API directly from a page. `chat()` / `vision()` / `converse()` take no `model` argument

**Hard rules:**
- NO streamlit imports inside services/ or db/
- prompts/ files are LOCKED — extend contracts only, never rewrite them
- All business logic lives in services/ — pages only render and call services
- Use Alembic for every schema change — migrations must have downgrade() implemented
- DEMO_MODE=true returns cached/mock output — zero API spend in tests
- Read API keys from st.secrets or environment only — never hardcode

**Baseline:** 136 tests passing, 0 ruff violations as of Week 5 Day 0.