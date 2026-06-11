# TradeLens AI

## What it is

TradeLens AI is an AI-powered post-trade journaling and performance analysis dashboard for active traders. It combines structured trade logging, GPT-4o chart analysis, strategy-aware grading, and rich analytics to help traders understand their patterns and improve their discipline over time. **It is not a live trading signal tool — all analysis is post-trade only.**

## Live Demo

[https://tradelens-app.streamlit.app/](https://tradelens-app.streamlit.app/)

Seeded with 60 sample trades. Add your `OPENAI_API_KEY` in Settings to enable AI features (analysis, journaling, grading).

## Features

- Log trades with asset, session, timeframe, direction, bias, setup type, R-multiple, emotion tags, and notes
- Upload chart screenshots analyzed by GPT-4o vision — returns bias, key zones, detected setup, and quality score
- Auto-generate strategy-aware 8-section trade journals in markdown (context, bias, entry rationale, risk, mistakes, lessons, psychology, verdict)
- Grade trades A–F by process quality with a rubric-based score and user override
- Corrections tracking — every time you change an AI label, the delta is logged for RLHF-style feedback loops
- Analytics dashboard: equity curve, drawdown, profit factor gauge, win rate by day of week, R-multiple histogram, emotion vs R, and setup breakdown — all filterable by date, asset, session, and strategy
- Import/export trades via CSV for portability and backup
- CLI script to pre-compute and cache KPIs (`python scripts/recompute_metrics.py`)

## Architecture

```
Streamlit UI  (src/tradelens/ui/pages/)
      │
Services layer  (src/tradelens/services/)  — pure Python, Streamlit-free
      │
SQLAlchemy ORM + SQLite  (src/tradelens/db/)
      │
OpenAI API  (GPT-4o vision  +  GPT-4o-mini text)
```

All business logic lives in `services/`. Pages are thin glue only — no metric math, no chart layout code, no DB queries. AI is post-trade only; no live signals.

## Tech Stack

| Layer | Tech |
|---|---|
| UI | Streamlit |
| Data | Pandas, NumPy |
| Charts | Plotly (graph_objects) |
| ORM / Migrations | SQLAlchemy 2.x + Alembic |
| DB | SQLite (local) |
| AI | OpenAI GPT-4o / GPT-4o-mini |
| Config | pydantic-settings, python-dotenv |
| Tests | pytest — 136 passing |

## Setup (local)

```bash
# 1. Clone and enter the repo
git clone https://github.com/your-handle/tradelens-ai.git
cd tradelens-ai

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

# 5. Run database migrations
alembic upgrade head

# 6. (Optional) Seed 60 sample trades
python scripts/seed.py

# 7. Start the app
streamlit run src/tradelens/ui/app.py
```

## Deploying to Streamlit Community Cloud

1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app
3. Set the entrypoint to `src/tradelens/ui/app.py`
4. In **Secrets**, add:
   ```
   OPENAI_API_KEY = "sk-..."
   ```
5. Deploy — the app auto-creates all tables on first load

See `.streamlit/secrets.toml.example` for the secrets format.

## Notes

- **SQLite is ephemeral on Streamlit Cloud** — the database resets on every redeploy. For persistent storage, swap the SQLite connection string for a PostgreSQL URL in `src/tradelens/db/session.py` (`DATABASE_URL = "postgresql://..."`) and run `alembic upgrade head` once before deploy. No other code changes are needed.
- **AI features require a valid `OPENAI_API_KEY`**. Without it, the app runs in journal-only mode — all non-AI features (trade logging, analytics, strategy profile, CSV import/export) still work.
- **Alembic** is used for local schema evolution. On a fresh Streamlit Cloud deploy, `Base.metadata.create_all()` runs at startup and creates all tables directly from the ORM models, bypassing the migration history.
