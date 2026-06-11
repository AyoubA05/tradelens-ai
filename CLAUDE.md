# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
pip install -r requirements.txt
cp .env.example .env          # then fill in OPENAI_API_KEY

# Initialize DB (creates tables from models via SQLAlchemy metadata)
python -m src.tradelens.db.init_db

# Seed sample data (60 trades across 3 weeks, skips if trades already exist)
python scripts/seed.py

# Run the app
streamlit run src/tradelens/ui/app.py

# Lint
ruff check src/ scripts/

# Test
pytest tests/ -v --tb=short

# Run a single test file
pytest tests/test_foo.py -v

# Alembic migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

## Architecture

The app is a single-user Streamlit trading journal backed by SQLite. The database URL is hardcoded in [src/tradelens/db/session.py](src/tradelens/db/session.py) (`sqlite:///./data/tradelens.db`) — the `.env` `DATABASE_URL` variable is not yet wired in.

**Data layer** (`src/tradelens/db/`):
- `session.py` — SQLAlchemy engine, `SessionLocal` factory, and `Base` (DeclarativeBase)
- `models.py` — ORM models: `Strategy`, `Trade`, `Screenshot`
- `init_db.py` — `Base.metadata.create_all()` entrypoint; use for initial setup

**Schema discrepancy to be aware of**: `scripts/seed.py` references a richer `Trade` schema (`user_id`, `trade_date`, `day_of_week`, `session`, `asset_class`, `stop_price`, `tp_price`, `position_size`, `risk_amount`, `reward_amount`, `rr_planned`, `strategy_used`, `bias`, `emotions_during`, `emotions_after`, `notes`, `ai_grade`, `user_grade`, `created_at`, `updated_at`) that is **not yet defined** in `models.py`. The Alembic initial migration is also a no-op (`pass`). The models and migration need to be updated to match the seed before the seed script will work.

**UI layer** (`src/tradelens/ui/`):
- `app.py` — single Streamlit entry point; sidebar nav and KPI metrics are stubs
- `pages/` — empty, intended for multi-page Streamlit pages

**Services layer** (`src/tradelens/services/`): empty stub directory — AI integration (OpenAI) and business logic go here.

**Prompts** (`prompts/`): empty stub — LLM prompt templates will live here.

**Data** (`data/`):
- `tradelens.db` — SQLite database file (committed; gitignored pattern excludes `*.sqlite3` but not this path)
- `data/screenshots/` — uploaded chart images, stored by file path reference in `Screenshot` model

Alembic is configured to import `Base` from `src/tradelens/db/models` for autogenerate support (`alembic/env.py:23`).

## TradeLens AI — Week 2 rules

- Follow the TradeLens AI Blueprint (6‑week roadmap).
- CURRENT PHASE: Week 2 — Core App only.
- Do NOT add OpenAI calls, vision analysis, grading, or journal generation yet.
- Keep strict separation: no `streamlit` imports in `src/tradelens/services/` or `src/tradelens/db/`.
- All DB access goes through `src/tradelens/db/session.py`.
- Pages live in `src/tradelens/ui/pages/` and are numbered.