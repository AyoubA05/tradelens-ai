# SP2 Postgres Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make TradeLens run on hosted Postgres (Neon) as its durable database, ending the ephemeral-SQLite risk on Streamlit Cloud, while keeping the test suite hermetic on SQLite.

**Architecture:** SQLAlchemy is already URL-driven (`config.settings.database_url`), so the runtime DB is chosen entirely by the `DATABASE_URL` env/secret. The only code that assumes SQLite is `session.py`'s hardcoded `check_same_thread` connect-arg; this plan extracts a dialect-aware `build_engine(url)` so SQLite keeps its arg and Postgres gets `pool_pre_ping` (survives Neon's scale-to-zero). Tests stay on SQLite for speed and hermeticity; one opt-in integration test proves Postgres compatibility only when a live URL is provided.

**Tech Stack:** SQLAlchemy 2.0, psycopg2-binary (new), Neon serverless Postgres, pytest.

## Design decisions (from SP2 brainstorm)

- **Provider: Neon.** Single connection string, `?sslmode=require`, scale-to-zero free tier. Plain `postgresql://` URLs (SQLAlchemy 2.0 defaults `postgresql://` to psycopg2 — no dialect prefix needed).
- **Data: start fresh.** The deployed SQLite lived on Streamlit Cloud's ephemeral disk (gitignored demo/beta data). Postgres starts empty; `init_db()` + the existing reconcile build the schema on first boot; `scripts/seed.py` re-creates demo data. No SQLite→Postgres data copy.
- **Tests stay on SQLite.** Default `pytest` requires no live DB. Postgres is exercised by one test gated on `TRADELENS_PG_TEST_URL`.

## Global Constraints

- Python 3.11 runtime (`runtime.txt`); versions CI-verified on 3.11. Local dev venv is 3.9 — psycopg2-binary supports both.
- Never hardcode credentials. `DATABASE_URL` comes from env / `.env` / `st.secrets` only. The Neon URL contains a password — it goes in `.env` (gitignored) locally and Streamlit Cloud secrets in prod, never in a committed file.
- `.env` and `data/` are already gitignored; keep it that way.
- Default `pytest tests/ -q` must pass with **no** Postgres available (currently 870 passing) and must not require network.
- Migrations remain the create_all + reconcile pattern (SP1 fix); do not attempt to replay the Alembic chain on Postgres.
- Commit after every task; stage paths explicitly (never `git add -A`).
- Branch off `main` for this work (SP1 is merged); do not build on the old `session-e1-new-trade-polish` branch.

---

### Task 1: Dialect-aware engine builder

**Files:**
- Modify: `src/tradelens/db/session.py`
- Create: `tests/test_db_engine.py`

**Interfaces:**
- Produces: `build_engine(url: str) -> sqlalchemy.engine.Engine` and module-level `engine`, `SessionLocal`, `Base`, `get_session` (unchanged names/behaviour for every existing import).

- [ ] **Step 1: Write the failing test** — `tests/test_db_engine.py`:

```python
from src.tradelens.db.session import build_engine


def test_sqlite_engine_connects(tmp_path):
    from sqlalchemy import text

    eng = build_engine(f"sqlite:///{tmp_path / 'x.db'}")
    assert eng.dialect.name == "sqlite"
    # Proves the SQLite-only check_same_thread connect-arg didn't break creation.
    with eng.connect() as c:
        assert c.execute(text("SELECT 1")).scalar() == 1


def test_postgres_url_builds_without_sqlite_args():
    # Must NOT raise: check_same_thread is SQLite-only and psycopg2 rejects it.
    # NullPool avoids opening a real connection at build time.
    from sqlalchemy.pool import NullPool

    eng = build_engine(
        "postgresql://u:p@localhost:5432/db", poolclass=NullPool
    )
    assert eng.dialect.name == "postgresql"
    assert eng.pool.__class__.__name__ == "NullPool"


def test_postgres_enables_pre_ping():
    from sqlalchemy.pool import NullPool

    eng = build_engine(
        "postgresql://u:p@localhost:5432/db", poolclass=NullPool
    )
    assert eng.pool._pre_ping is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_db_engine.py -q`
Expected: FAIL with `ImportError: cannot import name 'build_engine'`.

- [ ] **Step 3: Implement** — replace the engine block in `src/tradelens/db/session.py`:

```python
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from src.tradelens.config import settings

DATABASE_URL = settings.database_url


def build_engine(url: str, **overrides):
    """Create an Engine with per-dialect connect/pool settings.

    SQLite needs check_same_thread=False for Streamlit's threads; that arg is
    SQLite-only and psycopg2 rejects it. Postgres (Neon) gets pool_pre_ping so a
    connection dropped by scale-to-zero is transparently replaced. `overrides`
    lets tests inject e.g. poolclass=NullPool to avoid real connections.
    """
    kwargs = dict(overrides)
    if url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {"check_same_thread": False})
        if ":memory:" not in url and url.startswith("sqlite:///"):
            Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
    else:
        kwargs.setdefault("pool_pre_ping", True)
    return create_engine(url, **kwargs)


engine = build_engine(DATABASE_URL)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db_engine.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Full suite still green**

Run: `DEMO_MODE=true pytest tests/ -q`
Expected: `873 passed` (870 + 3 new).

- [ ] **Step 6: Commit**

```bash
git add src/tradelens/db/session.py tests/test_db_engine.py
git commit -m "db: dialect-aware engine builder (SQLite check_same_thread vs Postgres pre-ping)"
```

### Task 2: Add the Postgres driver

**Files:**
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `psycopg2` importable so `postgresql://` engines can connect.

- [ ] **Step 1: Add the dependency.** In `requirements.txt`, after the `sqlalchemy==2.0.49` line, add:

```
psycopg2-binary==2.9.10  # PostgreSQL driver (Neon); SQLAlchemy uses it for postgresql:// URLs
```

- [ ] **Step 2: Install and verify import**

Run: `source .venv/bin/activate && pip install "psycopg2-binary==2.9.10" && python -c "import psycopg2; print(psycopg2.__version__)"`
Expected: prints a version like `2.9.10 (dt dec pq3 ext lo64)`.

- [ ] **Step 3: Verify SQLAlchemy resolves the dialect** (no live connection needed)

Run:
```bash
python -c "from sqlalchemy import create_engine; from sqlalchemy.pool import NullPool; e=create_engine('postgresql://u:p@localhost/db', poolclass=NullPool); print(e.dialect.driver)"
```
Expected: `psycopg2`.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add psycopg2-binary for Postgres (Neon)"
```

### Task 3: Opt-in Postgres integration test

**Files:**
- Create: `tests/test_postgres_integration.py`

**Interfaces:**
- Consumes: `build_engine` (Task 1); `init_db(engine=...)` and `_reconcile_columns` behaviour (existing); `Trade` model.
- Produces: proof that create_all + reconcile + a Trade round-trip work on real Postgres, run only when `TRADELENS_PG_TEST_URL` is set.

- [ ] **Step 1: Write the test** — `tests/test_postgres_integration.py`:

```python
"""Live Postgres compatibility — skipped unless TRADELENS_PG_TEST_URL is set.

Run against a scratch Neon/Postgres DB:
    TRADELENS_PG_TEST_URL="postgresql://user:pass@host/db?sslmode=require" \
        pytest tests/test_postgres_integration.py -v

Proves the SQLite-authored schema (create_all) + the reconcile path + a basic
insert/select all work on Postgres. Not part of the default hermetic suite.
"""

import os

import pytest

PG_URL = os.getenv("TRADELENS_PG_TEST_URL")
pytestmark = pytest.mark.skipif(
    not PG_URL, reason="set TRADELENS_PG_TEST_URL to run Postgres integration tests"
)


def _fresh_engine():
    from sqlalchemy import text

    from src.tradelens.db.session import build_engine

    eng = build_engine(PG_URL)
    # Clean slate: drop the app schema so reruns are deterministic.
    from src.tradelens.db.session import Base
    from src.tradelens.db import models  # noqa: F401 — register tables

    Base.metadata.drop_all(eng)
    with eng.begin() as c:
        c.execute(text("SELECT 1"))
    return eng


def test_create_all_and_reconcile_on_postgres():
    from sqlalchemy import inspect

    from src.tradelens.db.init_db import init_db
    from src.tradelens.db.session import Base

    eng = _fresh_engine()
    init_db(engine=eng)  # create_all + reconcile
    tables = set(inspect(eng).get_table_names())
    assert "trades" in tables
    cols = {c["name"] for c in inspect(eng).get_columns("trades")}
    assert "trade_process_notes" in cols  # the SP1 reconcile column
    Base.metadata.drop_all(eng)


def test_trade_round_trip_on_postgres():
    from src.tradelens.db.init_db import init_db
    from src.tradelens.db.session import Base, build_engine
    from src.tradelens.db.models import Trade
    from sqlalchemy.orm import sessionmaker

    eng = _fresh_engine()
    init_db(engine=eng)
    Session = sessionmaker(bind=eng)
    with Session() as s:
        s.add(Trade(trade_date="2026-07-16", asset="NQ", direction="Long"))
        s.commit()
    with Session() as s:
        rows = s.query(Trade).all()
        assert len(rows) == 1
        assert rows[0].asset == "NQ"
    Base.metadata.drop_all(eng)
```

- [ ] **Step 2: Verify it SKIPS cleanly with no URL**

Run: `pytest tests/test_postgres_integration.py -q`
Expected: `2 skipped` (no `TRADELENS_PG_TEST_URL`).

- [ ] **Step 3: Verify the default suite is unaffected**

Run: `DEMO_MODE=true pytest tests/ -q`
Expected: `873 passed, 2 skipped`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_postgres_integration.py
git commit -m "test: opt-in Postgres integration (create_all + reconcile + round-trip)"
```

### Task 4: Env example + deploy docs

**Files:**
- Modify: `.env.example`
- Create: `docs/postgres-setup.md`

**Interfaces:**
- Produces: copy-paste setup instructions consumed by Task 5.

- [ ] **Step 1: Update `.env.example`.** Replace the `DATABASE_URL=sqlite:///./data/tradelens.db` line with:

```
# Database — local dev defaults to SQLite. For Postgres (Neon), paste your
# connection string (keep sslmode=require). Never commit a real password.
DATABASE_URL=sqlite:///./data/tradelens.db
# DATABASE_URL=postgresql://USER:PASSWORD@ep-xxxx.REGION.aws.neon.tech/DBNAME?sslmode=require
```

- [ ] **Step 2: Create `docs/postgres-setup.md`:**

```markdown
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
```

- [ ] **Step 3: Verify** `.env.example` has no real credentials and the SQLite default is intact.

Run: `grep -c "USER:PASSWORD" .env.example && grep -c "sqlite:///./data/tradelens.db" .env.example`
Expected: `1` then `1`.

- [ ] **Step 4: Commit**

```bash
git add .env.example docs/postgres-setup.md
git commit -m "docs: Neon Postgres setup + .env.example Postgres example"
```

### Task 5: Live cutover (human-in-the-loop)

**Files:** none (operational). This task is run by Ayoub; the agent guides and verifies.

**Interfaces:**
- Consumes: Tasks 1–4. Produces: a live Postgres-backed deployment.

- [ ] **Step 1: Create the Neon DB** per `docs/postgres-setup.md` §1 (Ayoub — account creation cannot be done by the agent). Have the pooled connection string ready.

- [ ] **Step 2: Run the opt-in integration test against the real DB** to prove compatibility before cutover:

```bash
source .venv/bin/activate
TRADELENS_PG_TEST_URL="postgresql://…?sslmode=require" pytest tests/test_postgres_integration.py -v
```
Expected: `2 passed`.

- [ ] **Step 3: Initialise + smoke-test locally** per `docs/postgres-setup.md` §2 (init_db, optional seed, `streamlit run`). Confirm the dashboard loads and a trade can be logged and reappears after refresh.

- [ ] **Step 4: Set the Streamlit Cloud secret** per §3 (Ayoub — dashboard action) and reboot. Confirm the deployed app loads with the Postgres backend and no `OperationalError`.

- [ ] **Step 5: Confirm durability** — log a trade on the deployed app, trigger a reboot/redeploy, confirm the trade persists (the whole point of SP2).

- [ ] **Step 6: Commit the plan checkbox state**

```bash
git add docs/superpowers/plans/2026-07-16-sp2-postgres-foundation.md
git commit -m "SP2: Postgres foundation complete — live cutover verified"
```
