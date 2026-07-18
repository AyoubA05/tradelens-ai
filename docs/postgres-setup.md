# Postgres (Neon) Setup — SP2

TradeLens uses hosted Postgres in production for durable data. Local dev may
stay on SQLite; the runtime DB is selected entirely by `DATABASE_URL`.

## 1. Create the Neon database
1. Sign up at https://neon.tech (free tier) and create a project.
2. Copy the **pooled** connection string from the dashboard. It looks like:
   `postgresql://USER:PASSWORD@ep-xxxx-pooler.REGION.aws.neon.tech/DBNAME?sslmode=require`
3. Keep `?sslmode=require` — Neon requires TLS.

## 2. Point the app at Postgres locally (to initialise + seed)
```bash
source .venv/bin/activate
export DATABASE_URL="postgresql://USER:PASSWORD@ep-...-pooler.REGION.aws.neon.tech/DBNAME?sslmode=require"
python -m src.tradelens.db.init_db     # creates tables + reconciles columns
python scripts/seed.py                 # optional: demo trades
streamlit run src/tradelens/ui/app.py  # smoke-test against Postgres
```

## 3. Set the secret on Streamlit Cloud
In the app's **Settings → Secrets**, add:
```toml
DATABASE_URL = "postgresql://USER:PASSWORD@ep-...-pooler.REGION.aws.neon.tech/DBNAME?sslmode=require"
```
Reboot the app. `init_db()` runs on boot and builds the schema on first start.

## Notes
- The password lives only in `.env` (gitignored) and Streamlit secrets — never in git.
- Neon scales to zero; the app's `pool_pre_ping` transparently replaces a dropped
  connection, so the first request after idle just reconnects.
- To prove compatibility against a real database before cutover, run the opt-in
  integration test:
  `TRADELENS_PG_TEST_URL="postgresql://…?sslmode=require" pytest tests/test_postgres_integration.py -v`
