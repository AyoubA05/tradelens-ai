# TradeLens AI

AI-powered trading journal and self-review dashboard for post-trade analysis, structured journaling, screenshot review, and long-term performance analytics.

## Overview
TradeLens AI is a post-trade reflection tool for traders. Users can log trades manually or upload TradingView screenshots, then use AI to help label chart context, generate a structured journal entry, and review long-term performance.

## MVP Features
- Manual trade entry form
- Screenshot upload
- Strategy Profile
- AI-assisted screenshot analysis
- Structured AI journal entry
- Trade grade based on process
- SQLite database
- Analytics dashboard
- Calendar journal view
- CSV import/export
- Corrections feedback loop
- Sample demo dataset

## Out of Scope
- Live trading signals
- Broker integrations
- Automated trading
- Fully automatic chart-pattern detection
- Multi-user auth in MVP

## Tech Stack
- Python
- Streamlit
- SQLAlchemy
- SQLite
- Pandas
- Plotly
- OpenAI API

## Week 1 Status
- Project structure initialized
- Database models created
- Seed script in progress
- GitHub repo created
- Streamlit app running locally

## Local Setup
```bash
pip install -r requirements.txt
cp .env.example .env
python -m src.tradelens.db.init_db
python scripts/seed.py
streamlit run src/tradelens/ui/app.py
```