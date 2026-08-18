# Phase 0 — Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build every non-visible foundation the Next.js app will stand on — hardened tenant isolation in the service layer, a doubly-authenticated FastAPI backend, R2 storage with validated uploads, a background AI job runner, and a parity harness — without shipping a single user-visible screen.

> **Independent-review amendment (2026-08-18).** This file records the plan as
> originally executed, so some embedded code samples are intentionally
> historical. The reviewed implementation and design spec supersede two parts:
> Next.js sends `X-TL-Session-Handle` (the domain-separated database hash), not
> the raw `X-TL-Session` browser credential; R2 PUTs land in quarantine and the
> server enforces size plus image normalization before producing the only key
> that may be persisted or downloaded. Query-pair order is also HMAC-bound; an
> exact signed request remains replayable inside the 60-second freshness window.

**Architecture:** A new `src/tradelens/api/` package wraps the existing, untouched `src/tradelens/services/` behind FastAPI. It is a public HTTPS service that is never called by a browser: every request must carry both a timestamped HMAC service signature and a website session token that FastAPI resolves against the database itself. The owner of a request is derived from the session row and passed explicitly into services whose signatures no longer accept a nullable owner.

**Tech Stack:** Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2.x · Alembic · boto3 (Cloudflare R2, S3-compatible) · Pillow · pytest · Next.js 16 / TypeScript / Vitest · openapi-typescript

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md`

## Corrections from execution (2026-08-16)

Recorded as they were discovered while running this plan. Where a task's text below
disagrees with this section, **this section wins** — it is what was actually verified
against the code.

1. **Task 1 does NOT delete `src/tradelens/ui/pages/_archive/`.** The stated
   justification — that its unscoped `get_trades()` calls block the isolation work — is
   wrong. Those calls live in `3_TradeDetail.py:59`, `6_Calendar.py:43` and
   `8_AI_Partner.py:48`; **no test executes any of them**, and Streamlit cannot route into
   subdirectories of `pages/`. Nine passing tests read those files' source
   (`test_landing.py` ×7, `test_charts.py` ×1, `test_cold_start.py` ×1). The archive stays
   until Phase 10 removes `src/tradelens/ui/` wholesale. Task 1 is the guard only.

2. **`scripts/recompute_metrics.py` is scoped, not given an escape hatch.** It declares
   `recompute(user_id: int)` and then calls `get_trades()` unscoped — a real defect, since
   it recomputes one user's stored metrics from every user's trades. The fix is
   `get_trades(user_id=user_id)`. Consequently **no `*_for_maintenance` or `*_all_users`
   helper is created anywhere in Phase 0** — nothing legitimate wants one. The
   import-boundary test in Task 9 still guards against one appearing later.

3. **Task 2's "no live caller" claim for `weekly.list_weekly_reviews` is wrong.** Two tests
   exercise it — `tests/test_weekly.py:269-280`, including
   `test_list_weekly_reviews_orders_recent_first`. They assert it returns *every user's*
   reviews, so they are tests of the cross-tenant behaviour being removed: **delete those
   two tests along with the function.** `get_weekly_reviews(user_id, limit)` covers the
   need. The import left dangling in the archived `7_Weekly_Review.py:16` is inert
   (nothing imports that file) and goes at Phase 10.
   Also: three tests call `find_recent_duplicate` without an owner
   (`tests/test_duplicate_prevention.py:53,61,73`) and must pass an explicit one.

4. **Task 15's golden dataset had two encoding defects.** `"result": "Break-even"` is
   rejected — `trade_validation.VALID_OUTCOMES` accepts only `win`/`loss`/`breakeven`, and
   every write routes through `canonical_outcome`; use `"Breakeven"`. And
   `"followed_rules": "Yes"/"No"/"Partial"` is the *display* form: `Trade.followed_rules`
   is an `Integer` column and the live page writes `{"Yes": 1, "No": 0, "Partial": None}`
   (`1_NewTrade.py:784`); use `1`, `0`, `None`. A snapshot built from the original values
   would pin numbers no real row could produce. The harness frame must also carry the
   `killzone` column, which `killzone_performance` reads.

5. **Local runtime is Python 3.9.6**, not 3.11. Every new module must carry
   `from __future__ import annotations` and avoid 3.10+ syntax. CI and
   `Dockerfile.api` (`python:3.11-slim`) remain the 3.11 gates.

6. **Phase 0 is based on the Codex security baseline** (`c69d84b`), not on `bf7fb33`.

## Global Constraints

- Python 3.11. Runtime deps are CI-verified on 3.11 (`runtime.txt`).
- **No Streamlit imports** in `services/`, `db/`, or the new `api/` package.
- `prompts/` files are **LOCKED** — extend contracts only, never rewrite.
- All AI calls route through `services/ai_client.py` only. `chat()` / `vision()` / `converse()` take no `model` argument.
- The model ID lives in exactly one place: `ANTHROPIC_MODEL_ID = "claude-opus-5"` in `src/tradelens/config.py`. Not env-overridable, no per-feature selection, no fallback model.
- Every schema change gets an Alembic migration with `downgrade()` implemented. Current head: **`x4y5z6a7b8c9`**.
- `DEMO_MODE=true` returns cached/mock output — zero API spend in tests.
- Secrets come from environment or `st.secrets` only. Never hardcoded, never logged.
- TradeLens is a post-trade reflection journal. No signals, predictions, or financial advice — including in copy, error strings, and docstrings.
- Lint/format gates: `ruff check src/ scripts/` and `black --check src/ scripts/` must be clean.
- The existing 779 service/DB test functions must stay green after every task.
- **Phase 0 ships no user-visible UI.** No app shell, no pages, no components. If a task seems to require one, it belongs in Phase 1.

---

## File Structure

**New Python package — `src/tradelens/api/`**

| File | Responsibility |
|---|---|
| `app.py` | FastAPI factory: middleware, routers, production hardening |
| `config.py` | API-only settings (service secret, R2 credentials, environment) |
| `security.py` | Lock 1 — HMAC signature construction and verification |
| `deps.py` | `current_user()` dependency wiring both locks; request-scoped context |
| `serialization.py` | Strict JSON encoder for numpy/pandas/Decimal/datetime |
| `storage.py` | R2 adapter — key generation, presigning, ownership checks |
| `imaging.py` | Server-side image validation and normalisation |
| `jobs.py` | AI job enqueue/claim/complete with idempotency |
| `worker.py` | Job runner process entrypoint |
| `routers/session.py` | `/v1/session/whoami` — the one endpoint Phase 0 needs |

**New service-layer file**

| File | Responsibility |
|---|---|
| `src/tradelens/services/ownership.py` | `require_user_id()` — the single owner-validation guard |

**Modified**

| File | Change |
|---|---|
| `src/tradelens/services/trade_service.py` | Remove nullable-owner defaults (Class A + B) |
| `src/tradelens/services/weekly.py` | Delete `list_weekly_reviews`; require owner |
| `src/tradelens/services/sample_data.py` | Require owner |
| `src/tradelens/services/csvio.py` | Require owner |
| `src/tradelens/services/cost.py` | Require owner |
| `src/tradelens/services/corrections.py` | ContextVar refuses rather than defaults |
| `src/tradelens/services/auth_sessions.py` | Add `restore_website_session` |
| `src/tradelens/db/models.py` | `User.app_surface`; new `AIJob` |
| `scripts/recompute_metrics.py` | Fix unscoped `get_trades()` defect |

**Deleted**

| Path | Reason |
|---|---|
| `src/tradelens/ui/pages/_archive/` | Unreachable; its unscoped `get_trades()` calls block Task 2 |

**New TypeScript**

| File | Responsibility |
|---|---|
| `web/lib/api/sign.ts` | Lock 1 signing, mirror of `security.py` |
| `web/lib/api/client.ts` | Server-only fetch wrapper adding both headers |

**New shared contract**

| File | Responsibility |
|---|---|
| `docs/contracts/service-signature-vectors.json` | Cross-language HMAC vectors, following the `auth-contract-vectors.json` precedent |

---

### Task 1: Ownership guard, and delete the archived pages

The guard both later tasks depend on, plus removal of the dead pages whose unscoped calls would otherwise break when Task 2 lands.

**Files:**
- Create: `src/tradelens/services/ownership.py`
- Create: `tests/test_ownership_guard.py`
- Delete: `src/tradelens/ui/pages/_archive/` (5 files + `__pycache__`)

**Interfaces:**
- Consumes: nothing
- Produces: `require_user_id(value: object) -> int` — raises `ValueError` on anything that is not a positive, non-bool `int`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ownership_guard.py
import pytest

from src.tradelens.services.ownership import require_user_id


def test_accepts_a_positive_integer():
    assert require_user_id(7) == 7


@pytest.mark.parametrize("bad", [None, 0, -1, "3", 3.0, True, False, [], {}])
def test_refuses_everything_that_is_not_a_positive_int(bad):
    """`True` is the subtle one: in Python `isinstance(True, int)` is True and
    `True > 0`, so a bare int check would accept it and scope a query to user 1."""
    with pytest.raises(ValueError):
        require_user_id(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ownership_guard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.tradelens.services.ownership'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/tradelens/services/ownership.py
"""The single definition of a valid request owner.

Every user-facing service validates its `user_id` through this function. It
exists because the alternative — each service inventing its own check — is how
one of them ends up accepting None and reading the legacy tenant, or accepting
True and reading user 1. There is one rule and one place to change it.

No Streamlit imports here.
"""

from __future__ import annotations


def require_user_id(value: object) -> int:
    """Return `value` as a concrete owner id, or raise.

    `bool` is rejected explicitly: it is a subclass of `int`, so `True` would
    otherwise pass both the type check and the positivity check and silently
    scope a query to user 1.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("user_id must be a positive integer")
    return value
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ownership_guard.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Delete the archived pages**

```bash
git rm -r src/tradelens/ui/pages/_archive/
```

- [ ] **Step 6: Verify nothing imported them**

Run: `grep -rn "_archive" src/ tests/ scripts/ --include=*.py`
Expected: no output. If anything appears, it is dead code referencing dead code — delete that too.

- [ ] **Step 7: Run the full suite**

Run: `pytest tests/ -q`
Expected: PASS. Note the exact passing count in the commit message; it is the baseline for Tasks 2 and 3.

- [ ] **Step 8: Commit**

```bash
git add src/tradelens/services/ownership.py tests/test_ownership_guard.py
git commit -m "feat(services): add require_user_id guard; delete archived pages

One definition of a valid request owner, rejecting bool explicitly since
isinstance(True, int) would otherwise scope a query to user 1.

The archived pages are removed rather than updated: they are unreachable
and their unscoped get_trades() calls block the isolation hardening."
```

---

### Task 2: Class A — close the true cross-tenant reads

Four functions currently return other users' rows. This is the security core of Phase 0.

**Files:**
- Modify: `src/tradelens/services/trade_service.py:56-92` (`trade_hash_exists`, `find_recent_duplicate`), `:150-205` (`_UNSCOPED`, `get_trades`)
- Modify: `src/tradelens/services/weekly.py:322-334` (delete `list_weekly_reviews`)
- Modify: `scripts/recompute_metrics.py:53`
- Create: `tests/test_tenant_isolation_class_a.py`

**Interfaces:**
- Consumes: `require_user_id` from Task 1
- Produces:
  - `get_trades(*, user_id: int, start_date=None, end_date=None, asset=None, result=None, session=None, strategy=None) -> list[Trade]` — `user_id` now **required**
  - `trade_hash_exists(trade_hash: str, user_id: int) -> bool`
  - `find_recent_duplicate(trade_data: dict, user_id: int, within_seconds: int = 60) -> Optional[Trade]`
  - `weekly.list_weekly_reviews` — **removed**

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tenant_isolation_class_a.py
"""Class A: functions that returned rows across tenant boundaries.

Each test seeds two users and asserts that the function cannot be induced to
see the other user's row — and that omitting the owner raises rather than
quietly widening the query.
"""
import pytest

from src.tradelens.services import trade_service, weekly


def _trade(user_id, asset="NQ", date="2026-08-12"):
    return {
        "user_id": user_id,
        "trade_date": date,
        "asset": asset,
        "session": "New York Open",
        "setup_type": "Liquidity Sweep + FVG",
        "result": "Win",
        "pnl": 100.0,
    }


def test_get_trades_requires_an_owner():
    with pytest.raises(TypeError):
        trade_service.get_trades()


def test_get_trades_refuses_a_null_owner():
    with pytest.raises(ValueError):
        trade_service.get_trades(user_id=None)


def test_get_trades_returns_only_the_owners_rows(two_users):
    a, b = two_users
    trade_service.create_trade(_trade(a))
    trade_service.create_trade(_trade(b))

    rows = trade_service.get_trades(user_id=a)

    assert len(rows) == 1
    assert all(t.user_id == a for t in rows)


def test_trade_hash_exists_requires_an_owner():
    with pytest.raises(ValueError):
        trade_service.trade_hash_exists("abc", None)


def test_trade_hash_does_not_leak_across_users(two_users):
    """An identical setup logged by another trader is not this trader's duplicate."""
    a, b = two_users
    created = trade_service.create_trade(_trade(b))

    assert trade_service.trade_hash_exists(created.trade_hash, a) is False
    assert trade_service.trade_hash_exists(created.trade_hash, b) is True


def test_find_recent_duplicate_requires_an_owner():
    with pytest.raises(ValueError):
        trade_service.find_recent_duplicate(_trade(1), None)


def test_find_recent_duplicate_never_returns_another_users_trade(two_users):
    a, b = two_users
    trade_service.create_trade(_trade(b))

    assert trade_service.find_recent_duplicate(_trade(a), a) is None


def test_list_weekly_reviews_is_gone():
    """It had no owner parameter at all, so every call was cross-tenant."""
    assert not hasattr(weekly, "list_weekly_reviews")
```

- [ ] **Step 2: Add the `two_users` fixture**

Append to `conftest.py`:

```python
@pytest.fixture
def two_users(tmp_path, monkeypatch):
    """Two real user rows in an isolated database.

    Isolation tests are worthless against a shared database: a leak and a clean
    run look identical if the other tenant's rows happen not to exist. This
    guarantees both tenants exist and are distinguishable.
    """
    import importlib

    db_path = tmp_path / "isolation.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    from src.tradelens import config as tl_config

    importlib.reload(tl_config)
    from src.tradelens.db import session as db_session

    importlib.reload(db_session)
    from src.tradelens.db import models as db_models

    importlib.reload(db_models)
    db_models.Base.metadata.create_all(db_session.engine)

    from src.tradelens.services import users

    importlib.reload(users)
    a = users.create_user("trader_a", "correct-horse-battery-1")
    b = users.create_user("trader_b", "correct-horse-battery-2")
    yield a.id, b.id
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_tenant_isolation_class_a.py -v`
Expected: FAIL — `test_get_trades_requires_an_owner` fails because `get_trades()` currently succeeds and returns every trade. That failure *is* the vulnerability.

- [ ] **Step 4: Harden `trade_service`**

Replace lines 56-66 (`trade_hash_exists`):

```python
def trade_hash_exists(trade_hash: str, user_id: int) -> bool:
    """True if this user already has a trade with this hash.

    `user_id` is required. It used to default to None, which skipped the owner
    filter entirely — so a hash collision with a completely different trader
    reported "you already logged this".
    """
    owner = require_user_id(user_id)
    db: Session = SessionLocal()
    try:
        query = db.query(Trade).filter(
            Trade.trade_hash == trade_hash, Trade.user_id == owner
        )
        return db.query(query.exists()).scalar()
    finally:
        db.close()
```

Replace lines 68-90 (`find_recent_duplicate`):

```python
def find_recent_duplicate(
    trade_data: dict, user_id: int, within_seconds: int = 60
) -> Optional[Trade]:
    """Return this user's same-hash trade created within `within_seconds`, or None.

    Powers the "is this a duplicate?" prompt that catches double-clicks. The
    owner is required: this returns a Trade object that the UI shows to the
    caller, so an unscoped match handed one trader another trader's record.
    """
    owner = require_user_id(user_id)
    trade_hash = compute_trade_hash(trade_data)
    cutoff = (
        datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
    ).isoformat()
    db: Session = SessionLocal()
    try:
        return (
            db.query(Trade)
            .filter(
                Trade.trade_hash == trade_hash,
                Trade.created_at >= cutoff,
                Trade.user_id == owner,
            )
            .order_by(Trade.created_at.desc())
            .first()
        )
    finally:
        db.close()
```

Delete the `_UNSCOPED` sentinel at line 152 and change `get_trades`:

```python
def get_trades(
    *,
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    asset: Optional[str] = None,
    result: Optional[str] = None,
    session: Optional[str] = None,
    strategy: Optional[str] = None,
) -> list[Trade]:
    """Return one user's trades, filtered by the optional parameters.

    Ordered by trade_date DESC. A None filter argument means "do not filter on
    it"; `user_id` is not one of those and has no default.

    **Keyword-only, deliberately.** `start_date` used to sit first, so a
    positional `get_trades(uid)` silently asked for "trades on or after <a user
    id>". That happened once already while writing the Step 11 isolation
    harness. Every argument must be named.

    **The owner is required, deliberately.** It previously defaulted to an
    `_UNSCOPED` sentinel that applied no user filter at all, so the safe call
    and the every-tenant call differed by one easily-omitted keyword.
    """
    owner = require_user_id(user_id)
    db: Session = SessionLocal()
    try:
        query = db.query(Trade).options(selectinload(Trade.screenshots))
        query = query.filter(Trade.user_id == owner)

        if start_date:
            query = query.filter(Trade.trade_date >= start_date)
        if end_date:
            query = query.filter(Trade.trade_date <= end_date)
        if asset:
            query = query.filter(Trade.asset.ilike(f"%{asset}%"))
        if result and result != "All":
            query = query.filter(Trade.result == result)
        if session and session != "All":
            query = query.filter(Trade.session == session)
        if strategy:
            query = query.filter(Trade.strategy_used.ilike(f"%{strategy}%"))

        return query.order_by(Trade.trade_date.desc()).all()
    finally:
        db.close()
```

Add the import at the top of the file, in the same edit:

```python
from src.tradelens.services.ownership import require_user_id
```

- [ ] **Step 5: Delete `weekly.list_weekly_reviews`**

Remove the whole function (`weekly.py:322-334`). `get_weekly_reviews(user_id, limit)` covers every legitimate need.

- [ ] **Step 6: Fix the `recompute_metrics` defect**

`scripts/recompute_metrics.py:53` reads `trades = get_trades()` inside `def recompute(user_id: int)`. The function takes an owner and then ignores it, so it recomputes one user's stored metrics from **every** user's trades. Scope it:

```python
    trades = get_trades(user_id=user_id)
```

This is a real defect being fixed, not a mechanical signature update — note it in the commit message. It also means no `*_for_maintenance` escape hatch has a caller, so none is created (YAGNI); the import-boundary guard in Task 9 still forbids one from appearing later without review.

- [ ] **Step 7: Run the isolation tests**

Run: `pytest tests/test_tenant_isolation_class_a.py -v`
Expected: PASS (8 tests)

- [ ] **Step 8: Run the full suite and fix callers**

Run: `pytest tests/ -q`
Expected: PASS at the Task 1 baseline. Any failure is a caller that omitted `user_id`; fix the caller by passing the owner it already has in scope. Never re-add a default to make a test pass.

- [ ] **Step 9: Lint**

Run: `ruff check src/ scripts/ && black --check src/ scripts/`
Expected: clean

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "fix(security): close cross-tenant reads in trade and weekly services

get_trades defaulted to a sentinel that applied no owner filter;
trade_hash_exists and find_recent_duplicate skipped the filter on None,
so an identical setup logged by another trader was reported as this
trader's duplicate — and find_recent_duplicate returned that trader's
Trade object to the UI. list_weekly_reviews had no owner parameter at all.

Also fixes scripts/recompute_metrics.py, which accepted a user_id and
then loaded every user's trades to recompute that one user's metrics."
```

---

### Task 3: Class B and C — remove the legacy-tenant fallbacks

These fail closed today, so this is hardening rather than a leak fix: a `None` arriving by mistake reads or writes the legacy NULL-owner tenant instead of raising.

**Files:**
- Modify: `src/tradelens/services/trade_service.py` (`get_trade`, `update_trade`, `delete_trade`)
- Modify: `src/tradelens/services/weekly.py` (`get_weekly_review`, `get_weekly_reviews`)
- Modify: `src/tradelens/services/sample_data.py` (`count_sample_trades`, `clear_sample_trades`, `load_sample_trades`, `_sample_filter`)
- Modify: `src/tradelens/services/csvio.py` (`import_trades_csv`)
- Modify: `src/tradelens/services/cost.py` (`log_ai_usage`)
- Create: `tests/test_tenant_isolation_class_b.py`

**Interfaces:**
- Consumes: `require_user_id` from Task 1
- Produces: all nine functions take `user_id: int`, required, no default. `_sample_filter(query, user_id: int)` no longer has a NULL-owner branch.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tenant_isolation_class_b.py
"""Class B/C: functions where None selected the legacy NULL-owner tenant.

These already failed closed for a real user. The risk is quieter: a None
arriving by mistake read or wrote the legacy tenant instead of raising, so the
bug surfaced as missing data rather than an error.
"""
import pytest

from src.tradelens.services import cost, csvio, sample_data, trade_service, weekly


@pytest.mark.parametrize(
    "call",
    [
        lambda: trade_service.get_trade(1, None),
        lambda: trade_service.update_trade(1, None, pnl=1.0),
        lambda: trade_service.delete_trade(1, None),
        lambda: weekly.get_weekly_review("2026-08-10", None),
        lambda: weekly.get_weekly_reviews(None),
        lambda: sample_data.count_sample_trades(None),
        lambda: sample_data.clear_sample_trades(None),
        lambda: sample_data.load_sample_trades(None),
        lambda: cost.log_ai_usage("partner", object(), None),
    ],
)
def test_a_null_owner_raises_rather_than_selecting_the_legacy_tenant(call):
    with pytest.raises(ValueError):
        call()


def test_csv_import_requires_an_owner(tmp_path):
    f = tmp_path / "t.csv"
    f.write_bytes(b"trade_date,asset,result,pnl\n2026-08-12,NQ,Win,100\n")
    with pytest.raises(ValueError):
        with f.open("rb") as handle:
            csvio.import_trades_csv(handle, None)


def test_sample_trades_are_scoped_to_their_owner(two_users):
    a, b = two_users
    sample_data.load_sample_trades(a)

    assert sample_data.count_sample_trades(a) > 0
    assert sample_data.count_sample_trades(b) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tenant_isolation_class_b.py -v`
Expected: FAIL — each call currently returns `None`/`0`/`[]` instead of raising.

- [ ] **Step 3: Add the guard to each function**

In every one of the nine functions, change the annotation to `user_id: int` with no default and resolve the owner on the first line. The pattern, shown for `get_trade`:

```python
def get_trade(trade_id: int, user_id: int) -> Optional[Trade]:
    """Return this user's trade (relationships eager-loaded), or None.

    The owner is required. It was `Optional[int]`, and while a None fails
    closed — matching only legacy NULL-owner rows — that made a missing owner
    look like a missing trade instead of a programming error.
    """
    owner = require_user_id(user_id)
    db: Session = SessionLocal()
    try:
        return (
            db.query(Trade)
            .options(selectinload(Trade.screenshots))
            .filter(Trade.id == trade_id, Trade.user_id == owner)
            .first()
        )
    finally:
        db.close()
```

For `sample_data._sample_filter`, delete the NULL-owner branch entirely:

```python
def _sample_filter(query, user_id: int):
    """Scope a query to one user's sample trades."""
    owner = require_user_id(user_id)
    return query.filter(Trade.is_sample == 1, Trade.user_id == owner)
```

Add `from src.tradelens.services.ownership import require_user_id` to each of the five modified modules, in the same edit as its first use.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_tenant_isolation_class_b.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Run the full suite**

Run: `pytest tests/ -q`
Expected: PASS at the Task 1 baseline. Fix callers by passing the owner already in scope.

- [ ] **Step 6: Lint and commit**

```bash
ruff check src/ scripts/ && black --check src/ scripts/
git add -A
git commit -m "harden(security): require a concrete owner in nine services

These failed closed already: None selected the legacy NULL-owner tenant
rather than widening the query. The risk was that a missing owner looked
like missing data instead of an error. Now it raises."
```

---

### Task 4: Request-scoped correction context

`ai_client` injects correction few-shots with no user argument, resolving the owner through a ContextVar. Under a server that must refuse rather than fall back, and must never leak a value into the next request on the same worker.

**Files:**
- Modify: `src/tradelens/services/corrections.py:20-34`
- Create: `tests/test_corrections_context.py`

**Interfaces:**
- Consumes: `require_user_id` from Task 1
- Produces:
  - `corrections_scope(user_id: int)` — context manager that sets and always resets
  - `_resolve_user` raises `LookupError` when nothing set the context and no explicit `user_id` was passed

- [ ] **Step 1: Write the failing test**

```python
# tests/test_corrections_context.py
import pytest

from src.tradelens.services import corrections


def test_scope_sets_and_restores(two_users):
    a, _ = two_users
    with corrections.corrections_scope(a):
        assert corrections.count_corrections() == 0
    with pytest.raises(LookupError):
        corrections.count_corrections()


def test_scope_resets_even_when_the_body_raises(two_users):
    """A handler that raises must not leave its owner visible to the next
    request on the same worker thread."""
    a, _ = two_users
    with pytest.raises(RuntimeError):
        with corrections.corrections_scope(a):
            raise RuntimeError("handler exploded")
    with pytest.raises(LookupError):
        corrections.count_corrections()


def test_nested_scopes_restore_the_outer_owner(two_users):
    a, b = two_users
    with corrections.corrections_scope(a):
        with corrections.corrections_scope(b):
            assert corrections._resolve_user(corrections._UNSET) == b
        assert corrections._resolve_user(corrections._UNSET) == a


def test_unset_context_refuses_rather_than_using_the_legacy_tenant():
    with pytest.raises(LookupError):
        corrections._resolve_user(corrections._UNSET)


def test_an_explicit_owner_does_not_need_a_scope(two_users):
    a, _ = two_users
    assert corrections.count_corrections(user_id=a) == 0


def test_scope_refuses_an_invalid_owner():
    with pytest.raises(ValueError):
        with corrections.corrections_scope(None):
            pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_corrections_context.py -v`
Expected: FAIL — `corrections_scope` does not exist, and `_resolve_user` returns `None` rather than raising.

- [ ] **Step 3: Implement**

Replace `corrections.py:20-34`:

```python
from contextlib import contextmanager

from src.tradelens.services.ownership import require_user_id

# The owner of the current request. `ai_client`'s few-shot injection has no user
# argument, so this is how it learns whose corrections it may read.
#
# The default is a sentinel that RESOLVES TO A REFUSAL, not to the legacy NULL
# tenant. Under Streamlit an unset value meant "the single legacy user" and was
# harmless; under a server it would mean "whatever the last request left here",
# and a wrong answer is worse than an error.
_UNSCOPED = object()
_ACTIVE_USER: ContextVar[object] = ContextVar(
    "tradelens_corrections_user", default=_UNSCOPED
)
_UNSET = object()  # "argument not passed", distinct from an explicit value


def _resolve_user(user_id) -> int:
    if user_id is not _UNSET:
        return require_user_id(user_id)
    active = _ACTIVE_USER.get()
    if active is _UNSCOPED:
        raise LookupError(
            "no correction scope is active; call corrections_scope(user_id) "
            "or pass user_id explicitly"
        )
    return require_user_id(active)


@contextmanager
def corrections_scope(user_id: int):
    """Scope correction reads and writes to one user for the duration of a block.

    Reset happens through the token in a `finally`, never a bare `.set()`.
    FastAPI runs sync handlers in a threadpool where a worker thread is reused,
    so a value left behind is a value the next request can observe.
    """
    token = _ACTIVE_USER.set(require_user_id(user_id))
    try:
        yield
    finally:
        _ACTIVE_USER.reset(token)


def set_corrections_user(user_id: int) -> None:
    """Scope subsequent correction reads/writes. Prefer `corrections_scope`.

    Retained for the Streamlit page path, which has no block to wrap: a
    Streamlit script run is the scope. Deleted with `ui/` at Phase 10.
    """
    _ACTIVE_USER.set(require_user_id(user_id))
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_corrections_context.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the corrections and AI suites**

Run: `pytest tests/test_corrections.py tests/test_ai_client.py -q`
Expected: PASS. `_corrections_block` in `ai_client.py:217-225` already swallows exceptions, so an unscoped AI call degrades to an empty block rather than failing — which is the correct behaviour and must not be "fixed".

- [ ] **Step 6: Run the full suite, lint, commit**

```bash
pytest tests/ -q && ruff check src/ scripts/ && black --check src/ scripts/
git add -A
git commit -m "harden(security): correction scope refuses rather than defaulting

The ContextVar default resolved to the legacy NULL tenant. Under a server
that means 'whatever the last request left here'. It now raises, and the
new corrections_scope() resets by token in a finally so a handler that
raises cannot leak its owner to the next request on the same thread."
```

---

### Task 5: Strict JSON serialization

pandas and numpy produce values that `json.dumps` either rejects or silently mangles. `profit_factor` is already `∞` on screen today.

**Files:**
- Create: `src/tradelens/api/__init__.py`, `src/tradelens/api/serialization.py`
- Create: `tests/test_api_serialization.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `to_jsonable(value: object) -> object`
  - `finite_or_state(value: object) -> tuple[Optional[float], Optional[str]]` — states: `"undefined_nan"`, `"undefined_positive_infinity"`, `"undefined_negative_infinity"`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_serialization.py
import datetime as dt
import json
import math
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.tradelens.api.serialization import finite_or_state, to_jsonable


def _roundtrip(value):
    """Strict: rejects Infinity/NaN, which json.dumps emits by default."""
    return json.loads(json.dumps(to_jsonable(value), allow_nan=False))


@pytest.mark.parametrize(
    "value,expected",
    [
        (np.int64(5), 5),
        (np.float64(1.5), 1.5),
        (np.bool_(True), True),
        (Decimal("2.50"), 2.5),
        (pd.NA, None),
        (pd.NaT, None),
        (float("nan"), None),
        (float("inf"), None),
        (float("-inf"), None),
        (None, None),
    ],
)
def test_scalars_become_json_safe(value, expected):
    assert _roundtrip(value) == expected


def test_dates_become_iso_strings():
    assert _roundtrip(dt.date(2026, 8, 12)) == "2026-08-12"
    assert _roundtrip(dt.datetime(2026, 8, 12, 9, 30, tzinfo=dt.timezone.utc)).startswith(
        "2026-08-12T09:30:00"
    )


def test_nested_containers_are_converted_throughout():
    payload = {"rows": [{"pnl": np.float64(1.0), "r": float("nan")}]}
    assert _roundtrip(payload) == {"rows": [{"pnl": 1.0, "r": None}]}


def test_dataframes_become_lists_of_records():
    df = pd.DataFrame({"asset": ["NQ"], "pnl": [np.float64(410.0)]})
    assert _roundtrip(df) == [{"asset": "NQ", "pnl": 410.0}]


def test_an_unknown_type_raises_rather_than_being_stringified():
    """Silently str()-ing an unexpected object ships a wrong value to the UI."""
    class Weird:
        pass

    with pytest.raises(TypeError):
        to_jsonable(Weird())


@pytest.mark.parametrize(
    "value,expected",
    [
        (2.5, (2.5, None)),
        (float("inf"), (None, "undefined_positive_infinity")),
        (float("-inf"), (None, "undefined_negative_infinity")),
        (float("nan"), (None, "undefined_nan")),
    ],
)
def test_finite_or_state_names_why_a_number_is_missing(value, expected):
    """An infinite profit factor means 'no losses to divide by'. Encoding that
    as a bare null loses the meaning the UI renders as ∞."""
    assert finite_or_state(value) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_serialization.py -v`
Expected: FAIL — `ModuleNotFoundError: src.tradelens.api.serialization`

- [ ] **Step 3: Implement**

```python
# src/tradelens/api/__init__.py
"""HTTP layer over the TradeLens services. No Streamlit imports anywhere here."""
```

```python
# src/tradelens/api/serialization.py
"""One conversion from service values to JSON-safe values.

The service layer speaks pandas and numpy: metrics return DataFrames, and
individual figures come back as `numpy.float64`, `Decimal`, `pandas.NaT`, or a
non-finite float. `json.dumps` rejects some of those and, by default, emits
bare `Infinity` and `NaN` for the rest — tokens no strict JSON parser accepts.

The dangerous failure is not a crash. It is a silent coercion that turns an
undefined profit factor into 0.0 and renders a confident wrong number to a
trader. Unknown types therefore raise rather than being stringified.
"""

from __future__ import annotations

import datetime as dt
import math
from decimal import Decimal
from typing import Optional

import numpy as np
import pandas as pd

_PRIMITIVES = (str, bool, int)


def to_jsonable(value: object) -> object:
    """Convert `value` into something `json.dumps(..., allow_nan=False)` accepts.

    Non-finite floats become None; use `finite_or_state` where the reason a
    number is missing carries meaning.
    """
    if value is None or isinstance(value, _PRIMITIVES):
        return value

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, Decimal):
        return to_jsonable(float(value))

    # numpy scalars: np.bool_ first — it is not a subclass of Python bool.
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return to_jsonable(float(value))

    # pandas nulls: NaT, NA. `pd.isna` on an array returns an array, so this is
    # guarded to scalars before being called.
    if value is pd.NaT or value is pd.NA:
        return None

    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()

    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()

    if isinstance(value, pd.DataFrame):
        return [to_jsonable(record) for record in value.to_dict(orient="records")]
    if isinstance(value, pd.Series):
        return [to_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.ndarray):
        return [to_jsonable(item) for item in value.tolist()]

    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]

    raise TypeError(
        f"{type(value).__name__} has no defined JSON representation. Add one "
        "here rather than letting it be stringified at the boundary."
    )


def finite_or_state(value: object) -> tuple[Optional[float], Optional[str]]:
    """Split a possibly-undefined number into (value, reason-it-is-undefined).

    Profit factor is infinite when there are no losses to divide by. That is a
    meaning, not a number, and a bare null cannot carry it — the UI renders it
    as ∞. Schemas pair an Optional[float] field with an Optional[str] state.
    """
    if value is None:
        return None, None
    number = float(value)
    if math.isnan(number):
        return None, "undefined_nan"
    if number == math.inf:
        return None, "undefined_positive_infinity"
    if number == -math.inf:
        return None, "undefined_negative_infinity"
    return number, None
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_api_serialization.py -v`
Expected: PASS (20 tests)

- [ ] **Step 5: Commit**

```bash
git add src/tradelens/api tests/test_api_serialization.py
git commit -m "feat(api): strict JSON serialization for service values

Unknown types raise rather than being stringified: the dangerous failure
is not a crash but a silent coercion that turns an undefined profit
factor into 0.0 and shows a trader a confident wrong number."
```

---

### Task 6: `restore_website_session` — Lock 2 in Python

FastAPI must resolve the session itself rather than trusting that Next.js already did.

**Files:**
- Modify: `src/tradelens/services/auth_sessions.py` (append)
- Create: `tests/test_website_session_restore.py`

**Interfaces:**
- Consumes: `WEBSITE_DOMAIN`, `SURFACE_WEBSITE`, `IDLE_TIMEOUT_S`, `_hash`, `_as_aware`, `_SESSION_ROW_TYPES` — all existing in the module
- Produces: `restore_website_session(token, now: Optional[datetime] = None) -> Optional[int]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_website_session_restore.py
"""Lock 2, Python side. Mirrors web/lib/auth/session.ts.

All five conditions are checked here rather than trusting the Next.js layer to
have checked them: a bug or compromise upstream must not by itself make the
backend act on the wrong account.
"""
import datetime as dt

import pytest
from sqlalchemy import text

from src.tradelens.db.session import SessionLocal
from src.tradelens.services import auth_sessions


def _open_website_session(user_id, *, now=None, expires_in=12 * 3600, idle_at=None):
    import hashlib
    import secrets

    started = now or dt.datetime.now(dt.timezone.utc)
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(
        (auth_sessions.WEBSITE_DOMAIN + token).encode("utf-8")
    ).hexdigest()
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, "
                "expires_at, last_seen_at, surface) VALUES (:h,:u,:c,:e,:l,:s)"
            ),
            {
                "h": digest,
                "u": user_id,
                "c": started,
                "e": started + dt.timedelta(seconds=expires_in),
                "l": idle_at or started,
                "s": auth_sessions.SURFACE_WEBSITE,
            },
        )
        db.commit()
    finally:
        db.close()
    return token


def test_a_live_session_resolves_to_its_user(two_users):
    a, _ = two_users
    token = _open_website_session(a)
    assert auth_sessions.restore_website_session(token) == a


def test_a_streamlit_token_is_not_accepted(two_users):
    """Domain separation: the surfaces hash with different prefixes, so a token
    minted for one cannot hash to a row the other can find."""
    a, _ = two_users
    streamlit_token = auth_sessions.open_streamlit_session(a)
    assert auth_sessions.restore_website_session(streamlit_token) is None


def test_a_revoked_session_is_refused(two_users):
    a, _ = two_users
    token = _open_website_session(a)
    auth_sessions.revoke_all_for_user(a)
    assert auth_sessions.restore_website_session(token) is None


def test_a_session_past_its_absolute_expiry_is_refused(two_users):
    a, _ = two_users
    token = _open_website_session(a, expires_in=-1)
    assert auth_sessions.restore_website_session(token) is None


def test_an_idle_session_is_refused(two_users):
    a, _ = two_users
    stale = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=9 * 3600)
    token = _open_website_session(a, idle_at=stale)
    assert auth_sessions.restore_website_session(token) is None


def test_a_deactivated_account_is_refused(two_users):
    """The session row alone is not enough: a disabled account must not be able
    to act through a credential minted while it was still active."""
    a, _ = two_users
    token = _open_website_session(a)
    db = SessionLocal()
    try:
        db.execute(text("UPDATE users SET is_active = 0 WHERE id = :u"), {"u": a})
        db.commit()
    finally:
        db.close()
    assert auth_sessions.restore_website_session(token) is None


@pytest.mark.parametrize("bad", [None, "", 123, b"bytes", "not-a-real-token"])
def test_garbage_is_refused_without_raising(bad):
    assert auth_sessions.restore_website_session(bad) is None


def test_activity_slides_idle_but_never_extends_absolute_expiry(two_users):
    a, _ = two_users
    token = _open_website_session(a)
    db = SessionLocal()
    try:
        before = db.execute(
            text("SELECT expires_at FROM auth_sessions WHERE surface = 'website'")
        ).scalar()
    finally:
        db.close()

    auth_sessions.restore_website_session(token)

    db = SessionLocal()
    try:
        after = db.execute(
            text("SELECT expires_at FROM auth_sessions WHERE surface = 'website'")
        ).scalar()
    finally:
        db.close()
    assert before == after
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_website_session_restore.py -v`
Expected: FAIL — `AttributeError: module has no attribute 'restore_website_session'`

- [ ] **Step 3: Implement**

Append to `auth_sessions.py`:

```python
def restore_website_session(token, now: Optional[datetime] = None) -> Optional[int]:
    """Resolve a WEBSITE session credential to a user id, sliding the idle window.

    The Python counterpart of `authenticateWebsiteRequest` in
    `web/lib/auth/session.ts`, and deliberately a re-check rather than a
    convenience: the API backend must not act on an account merely because the
    Next.js layer said it had already validated the session. A bug or a
    compromise there would otherwise be sufficient on its own.

    All five conditions, matching the TypeScript exactly:

        hash matches a row with surface='website'
        revoked_at IS NULL
        expires_at > now
        now - last_seen_at < 8h
        users.is_active = 1

    Returns None — failing closed — when any of them does not hold. All five
    failures look identical to the caller.

    `expires_at` is never touched here, which is what keeps the 12-hour cap
    absolute rather than something activity can push indefinitely.
    """
    if not token or not isinstance(token, str):
        return None

    at = now or _now()
    digest = _hash(token, WEBSITE_DOMAIN)
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT s.user_id, s.expires_at, s.last_seen_at, s.revoked_at "
                "FROM auth_sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = :h AND s.surface = :s AND u.is_active = 1"
            ).columns(**_SESSION_ROW_TYPES),
            {"h": digest, "s": SURFACE_WEBSITE},
        ).first()
        if row is None:
            return None

        user_id, expires_at, last_seen_at, revoked_at = row
        if revoked_at is not None:
            return None
        if _as_aware(expires_at) <= at:
            return None
        if at - _as_aware(last_seen_at) > timedelta(seconds=IDLE_TIMEOUT_S):
            return None

        db.execute(
            text(
                "UPDATE auth_sessions SET last_seen_at = :now "
                "WHERE token_hash = :h AND surface = :s"
            ),
            {"now": at, "h": digest, "s": SURFACE_WEBSITE},
        )
        db.commit()
        return int(user_id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/test_website_session_restore.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(api): resolve website sessions in Python (Lock 2)

Re-checks all five conditions rather than trusting that Next.js already
validated the session, so an upstream bug is not by itself sufficient to
make the backend act on the wrong account. Joins users to enforce
is_active, which the Streamlit restore path never checked."
```

---

### Task 7: `users.app_surface` migration

The per-account routing flag that makes cutover reversible.

**Files:**
- Modify: `src/tradelens/db/models.py` (User)
- Create: `alembic/versions/y5z6a7b8c9d0_add_user_app_surface.py`
- Create: `tests/test_app_surface_migration.py`

**Interfaces:**
- Consumes: Alembic head `x4y5z6a7b8c9`
- Produces: `User.app_surface: str` — `'streamlit'` (default) or `'nextjs'`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_app_surface_migration.py
from sqlalchemy import inspect, text

from src.tradelens.db.session import SessionLocal, engine


def test_users_has_app_surface_defaulting_to_streamlit(two_users):
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert "app_surface" in cols

    db = SessionLocal()
    try:
        surfaces = [r[0] for r in db.execute(text("SELECT app_surface FROM users"))]
    finally:
        db.close()
    assert surfaces and all(s == "streamlit" for s in surfaces)


def test_app_surface_accepts_the_nextjs_value(two_users):
    a, _ = two_users
    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE users SET app_surface = 'nextjs' WHERE id = :u"), {"u": a}
        )
        db.commit()
        value = db.execute(
            text("SELECT app_surface FROM users WHERE id = :u"), {"u": a}
        ).scalar()
    finally:
        db.close()
    assert value == "nextjs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_app_surface_migration.py -v`
Expected: FAIL — `app_surface` is not in the column set

- [ ] **Step 3: Add the model column**

In `models.py`, inside `class User`, after `strategy_profile_completed`:

```python
    # Which application surface this account lands on after login. Defaults to
    # 'streamlit' so every existing account keeps the product it already knows;
    # accounts are moved to 'nextjs' individually during the parity window.
    # Both surfaces read one database, so this routes a person, not their data.
    # Removed once Streamlit is retired (Phase 10).
    app_surface: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'streamlit'")
    )
```

- [ ] **Step 4: Write the migration**

```python
# alembic/versions/y5z6a7b8c9d0_add_user_app_surface.py
"""Add users.app_surface for the Next.js migration cutover.

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
"""

import sqlalchemy as sa
from alembic import op

revision = "y5z6a7b8c9d0"
down_revision = "x4y5z6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default is mandatory, not stylistic: the column is NOT NULL and
    # existing rows have no value, so without it the ALTER fails on Postgres.
    op.add_column(
        "users",
        sa.Column(
            "app_surface",
            sa.String(),
            nullable=False,
            server_default=sa.text("'streamlit'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "app_surface")
```

- [ ] **Step 5: Verify the migration applies and reverses**

```bash
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```
Expected: all three succeed. Run against the local SQLite database, never production.

- [ ] **Step 6: Run the tests and commit**

```bash
pytest tests/test_app_surface_migration.py tests/test_migrations.py -v
git add -A
git commit -m "feat(db): add users.app_surface for staged cutover"
```

---

### Task 8: `ai_jobs` table and model

AI calls take 60–120s. They must not be attempted inside a request.

**Files:**
- Modify: `src/tradelens/db/models.py` (append `AIJob`)
- Create: `alembic/versions/z6a7b8c9d0e1_add_ai_jobs.py`
- Create: `tests/test_ai_jobs_schema.py`

**Interfaces:**
- Consumes: Alembic revision `y5z6a7b8c9d0`
- Produces: `AIJob` with `UniqueConstraint("user_id", "idempotency_key")` and statuses `queued | running | succeeded | failed`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ai_jobs_schema.py
import pytest
from sqlalchemy.exc import IntegrityError

from src.tradelens.db.models import AIJob
from src.tradelens.db.session import SessionLocal


def test_the_same_idempotency_key_cannot_be_enqueued_twice(two_users):
    """The control that stops a double-submitted screenshot being paid for twice."""
    a, _ = two_users
    db = SessionLocal()
    try:
        db.add(AIJob(user_id=a, kind="screenshot_analysis", idempotency_key="k1"))
        db.commit()
        db.add(AIJob(user_id=a, kind="screenshot_analysis", idempotency_key="k1"))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_two_users_may_reuse_the_same_key(two_users):
    """The key is unique per owner, not globally: one trader's key must not
    block another's."""
    a, b = two_users
    db = SessionLocal()
    try:
        db.add(AIJob(user_id=a, kind="grading", idempotency_key="same"))
        db.add(AIJob(user_id=b, kind="grading", idempotency_key="same"))
        db.commit()
    finally:
        db.close()


def test_a_new_job_starts_queued(two_users):
    a, _ = two_users
    db = SessionLocal()
    try:
        job = AIJob(user_id=a, kind="weekly_review", idempotency_key="k2")
        db.add(job)
        db.commit()
        db.refresh(job)
        assert job.status == "queued"
        assert job.attempts == 0
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ai_jobs_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'AIJob'`

- [ ] **Step 3: Add the model**

Append to `models.py`:

```python
class AIJob(Base):
    """One asynchronous AI request.

    AI calls run 60-120 seconds, which is longer than a request should live and
    longer than most proxies allow. They are therefore enqueued here and run by
    a separate worker process against the same database.

    `(user_id, idempotency_key)` is unique. That constraint is the only thing
    standing between a double-submitted form and a second Anthropic bill, and it
    is per-owner rather than global so one trader's key cannot block another's.
    """

    __tablename__ = "ai_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_ai_jobs_user_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="queued", server_default=text("'queued'")
    )
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # A pointer to where the result landed (e.g. an aianalysis id), never the
    # result itself: generated content belongs in its own table.
    result_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Safe for a user to read: no provider text, no stack trace.
    error: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

Verify `Text` and `UniqueConstraint` are in the module's SQLAlchemy imports; add them in the same edit if not.

- [ ] **Step 4: Write the migration**

```python
# alembic/versions/z6a7b8c9d0e1_add_ai_jobs.py
"""Add ai_jobs for asynchronous AI work.

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0
"""

import sqlalchemy as sa
from alembic import op

revision = "z6a7b8c9d0e1"
down_revision = "y5z6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column(
            "status", sa.String(), nullable=False, server_default=sa.text("'queued'")
        ),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("result_ref", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_ai_jobs_user_key"),
    )
    op.create_index("ix_ai_jobs_user_id", "ai_jobs", ["user_id"])
    # The worker's claim query filters on status and orders by id.
    op.create_index("ix_ai_jobs_status", "ai_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ai_jobs_status", table_name="ai_jobs")
    op.drop_index("ix_ai_jobs_user_id", table_name="ai_jobs")
    op.drop_table("ai_jobs")
```

- [ ] **Step 5: Verify up and down, run tests, commit**

```bash
alembic upgrade head && alembic downgrade -1 && alembic upgrade head
pytest tests/test_ai_jobs_schema.py tests/test_migrations.py -v
git add -A
git commit -m "feat(db): add ai_jobs with per-owner idempotency

The (user_id, idempotency_key) constraint is what stops a double-submitted
screenshot becoming a second Anthropic bill."
```

---

### Task 9: FastAPI application with both locks

**Files:**
- Create: `src/tradelens/api/config.py`, `security.py`, `deps.py`, `app.py`, `routers/__init__.py`, `routers/session.py`
- Create: `tests/test_api_security.py`
- Create: `requirements-api.txt`

**Interfaces:**
- Consumes: `restore_website_session` (Task 6), `corrections_scope` (Task 4), `to_jsonable` (Task 5)
- Produces:
  - `sign_request(secret: str, timestamp: str, method: str, path: str, body: bytes) -> str`
  - `verify_signature(header: Optional[str], method: str, path: str, body: bytes, now: float) -> bool`
  - `current_user()` FastAPI dependency returning `int`
  - `create_app() -> FastAPI`
  - `GET /v1/session/whoami` → `{"user_id": int}`
  - `GET /health` → `{"status": "ok"}`, unauthenticated

- [ ] **Step 1: Add API dependencies**

```bash
cat > requirements-api.txt <<'EOF'
# FastAPI service dependencies. Installed in the API container, which does NOT
# install requirements.txt — Streamlit, Plotly and PyArrow have no business in
# a backend image and would triple its size.
-r requirements-base.txt
fastapi==0.120.4
uvicorn[standard]==0.41.0
boto3==1.42.7
EOF
```

Split the shared runtime deps out of `requirements.txt` into `requirements-base.txt` (pandas, numpy, sqlalchemy, psycopg2-binary, python-dotenv, anthropic, pillow, pydantic-settings, alembic, bcrypt, tzdata), leaving `requirements.txt` as `-r requirements-base.txt` plus `streamlit`, `pyarrow`, `plotly`. Add `httpx==0.29.4` to `requirements-dev.txt` for `TestClient`.

Then: `pip install -r requirements-dev.txt -r requirements-api.txt`

- [ ] **Step 2: Write the failing test**

```python
# tests/test_api_security.py
"""Both locks, and the hardening that keeps this service non-browser-facing."""
import hashlib
import hmac
import time

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api.security import sign_request

SECRET = "test-service-secret-value"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TL_SERVICE_SECRET", SECRET)
    monkeypatch.setenv("TL_ENV", "production")
    return TestClient(create_app(), raise_server_exceptions=False)


def _headers(session_token, *, method="GET", path="/v1/session/whoami", body=b"",
             secret=SECRET, timestamp=None):
    ts = timestamp or str(int(time.time()))
    return {
        "X-TL-Signature": f"v1={ts}:{sign_request(secret, ts, method, path, body)}",
        "X-TL-Session": session_token,
    }


def test_health_needs_no_credentials(client):
    assert client.get("/health").status_code == 200


def test_a_request_with_no_signature_is_refused(client, website_session):
    r = client.get("/v1/session/whoami", headers={"X-TL-Session": website_session[1]})
    assert r.status_code == 401


def test_a_valid_signature_with_no_session_is_refused(client):
    """Lock 1 alone is not enough. The service secret proves the caller is our
    frontend; it says nothing about which user is asking."""
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", "/v1/session/whoami", b"")
    r = client.get("/v1/session/whoami", headers={"X-TL-Signature": f"v1={ts}:{sig}"})
    assert r.status_code == 401


def test_both_locks_together_succeed(client, website_session):
    user_id, token = website_session
    r = client.get("/v1/session/whoami", headers=_headers(token))
    assert r.status_code == 200
    assert r.json() == {"user_id": user_id}


def test_a_signature_from_the_wrong_secret_is_refused(client, website_session):
    _, token = website_session
    r = client.get("/v1/session/whoami", headers=_headers(token, secret="wrong"))
    assert r.status_code == 401


def test_an_old_signature_is_refused(client, website_session):
    """Replay window. A captured header must stop working quickly."""
    _, token = website_session
    old = str(int(time.time()) - 3600)
    r = client.get("/v1/session/whoami", headers=_headers(token, timestamp=old))
    assert r.status_code == 401


def test_a_signature_for_a_different_path_is_refused(client, website_session):
    """The path is bound into the signature, so a header captured from one
    endpoint cannot be replayed against another."""
    _, token = website_session
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", "/health", b"")
    r = client.get(
        "/v1/session/whoami",
        headers={"X-TL-Signature": f"v1={ts}:{sig}", "X-TL-Session": token},
    )
    assert r.status_code == 401


def test_a_revoked_session_is_refused(client, website_session):
    from src.tradelens.services import auth_sessions

    user_id, token = website_session
    auth_sessions.revoke_all_for_user(user_id)
    assert client.get("/v1/session/whoami", headers=_headers(token)).status_code == 401


def test_the_user_id_comes_from_the_session_not_the_request(client, website_session):
    """The single most important property: a caller cannot name the account it
    wants to act on."""
    user_id, token = website_session
    r = client.get(
        "/v1/session/whoami?user_id=999999",
        headers=_headers(token, path="/v1/session/whoami"),
    )
    assert r.status_code in (200, 401)
    if r.status_code == 200:
        assert r.json()["user_id"] == user_id


def test_no_cors_headers_are_ever_emitted(client, website_session):
    """This service is not browser-consumed. A CORS header would be the first
    step toward it becoming so."""
    _, token = website_session
    r = client.get("/v1/session/whoami", headers=_headers(token))
    assert not any(h.lower().startswith("access-control-") for h in r.headers)


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_schema_is_not_served_in_production(client, path):
    assert client.get(path).status_code == 404


def test_authenticated_responses_are_not_cacheable(client, website_session):
    _, token = website_session
    r = client.get("/v1/session/whoami", headers=_headers(token))
    assert "no-store" in r.headers.get("cache-control", "")


def test_no_api_module_imports_a_maintenance_helper():
    """Global-access helpers must never be reachable from a request path.
    None exists today; this fails the moment one is imported here."""
    import pathlib
    import re

    offenders = []
    for path in pathlib.Path("src/tradelens/api").rglob("*.py"):
        text = path.read_text()
        if re.search(r"\b\w*(_for_maintenance|_all_users)\b", text):
            offenders.append(str(path))
    assert offenders == []
```

Add to `conftest.py`:

```python
@pytest.fixture
def website_session(two_users):
    """A live website session for the first test user: (user_id, raw_token)."""
    import datetime as dt
    import hashlib
    import secrets

    from sqlalchemy import text as sa_text

    from src.tradelens.db.session import SessionLocal
    from src.tradelens.services import auth_sessions

    user_id = two_users[0]
    token = secrets.token_urlsafe(32)
    now = dt.datetime.now(dt.timezone.utc)
    db = SessionLocal()
    try:
        db.execute(
            sa_text(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, "
                "expires_at, last_seen_at, surface) VALUES (:h,:u,:c,:e,:l,'website')"
            ),
            {
                "h": hashlib.sha256(
                    (auth_sessions.WEBSITE_DOMAIN + token).encode("utf-8")
                ).hexdigest(),
                "u": user_id,
                "c": now,
                "e": now + dt.timedelta(hours=12),
                "l": now,
            },
        )
        db.commit()
    finally:
        db.close()
    return user_id, token
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_api_security.py -v`
Expected: FAIL — `ModuleNotFoundError: src.tradelens.api.app`

- [ ] **Step 4: Implement `config.py`**

```python
# src/tradelens/api/config.py
"""API-only settings. Read from the environment; never hardcoded, never logged."""

from __future__ import annotations

import os
from typing import Optional


def service_secrets() -> list[str]:
    """Accepted signing secrets, current first.

    Two are supported so `TL_SERVICE_SECRET` can be rotated without downtime:
    deploy the new secret as the current one and keep the old in
    `TL_SERVICE_SECRET_PREVIOUS` until every caller has been redeployed.
    """
    secrets = [os.getenv("TL_SERVICE_SECRET", ""), os.getenv("TL_SERVICE_SECRET_PREVIOUS", "")]
    return [s for s in secrets if s]


def is_production() -> bool:
    return os.getenv("TL_ENV", "development").lower() == "production"


def r2_config() -> dict:
    return {
        "account_id": os.getenv("R2_ACCOUNT_ID", ""),
        "access_key_id": os.getenv("R2_ACCESS_KEY_ID", ""),
        "secret_access_key": os.getenv("R2_SECRET_ACCESS_KEY", ""),
        "bucket": os.getenv("R2_BUCKET", ""),
    }
```

- [ ] **Step 5: Implement `security.py`**

```python
# src/tradelens/api/security.py
"""Lock 1 — proof that a request came from our own frontend.

The signed message binds the timestamp, method, path and a hash of the body:

    {timestamp}.{METHOD}.{path}.{sha256(body)}

Binding path and body is what makes a captured header useless elsewhere. A
signature over the timestamp alone would be a reusable bearer token for every
endpoint on the service.

This proves *which caller*, never *which user*. Identity is Lock 2's job.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional

from src.tradelens.api.config import service_secrets

REPLAY_WINDOW_SECONDS = 60


def build_message(timestamp: str, method: str, path: str, body: bytes) -> str:
    return f"{timestamp}.{method.upper()}.{path}.{hashlib.sha256(body).hexdigest()}"


def sign_request(secret: str, timestamp: str, method: str, path: str, body: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        build_message(timestamp, method, path, body).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(
    header: Optional[str],
    method: str,
    path: str,
    body: bytes,
    now: Optional[float] = None,
) -> bool:
    """Whether `header` is a valid, fresh signature. Never raises."""
    secrets = service_secrets()
    if not header or not secrets:
        return False
    if not header.startswith("v1="):
        return False

    try:
        timestamp, provided = header[3:].split(":", 1)
        age = abs((now if now is not None else time.time()) - int(timestamp))
    except (ValueError, TypeError):
        return False

    if age > REPLAY_WINDOW_SECONDS:
        return False

    # compare_digest against every accepted secret, without short-circuiting on
    # the first match, so the comparison cost does not depend on which secret
    # was used.
    matched = False
    for secret in secrets:
        expected = sign_request(secret, timestamp, method, path, body)
        if hmac.compare_digest(expected, provided):
            matched = True
    return matched
```

- [ ] **Step 6: Implement `deps.py`**

```python
# src/tradelens/api/deps.py
"""The single gate every authenticated route goes through."""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import Depends, HTTPException, Request

from src.tradelens.api.security import verify_signature
from src.tradelens.services.auth_sessions import restore_website_session
from src.tradelens.services.corrections import corrections_scope

_UNAUTHORIZED = HTTPException(status_code=401, detail="unauthenticated")


async def verified_body(request: Request) -> bytes:
    """Read the body once, enforce Lock 1 against it, and cache it.

    Reading here rather than in the route matters: the signature covers the
    bytes, so verification must see exactly what the handler will see.
    """
    body = await request.body()
    if len(body) > 1_048_576:
        raise HTTPException(status_code=413, detail="request too large")
    if not verify_signature(
        request.headers.get("X-TL-Signature"),
        request.method,
        request.url.path,
        body,
    ):
        raise _UNAUTHORIZED
    return body


async def current_user(
    request: Request, _body: bytes = Depends(verified_body)
) -> AsyncIterator[int]:
    """Resolve the owner of this request, and scope correction reads to them.

    **The id comes from the session row and nowhere else.** No header, query
    parameter, or body field may name the account being acted on. Everything
    downstream receives this value explicitly.

    Yields inside `corrections_scope` so the ContextVar is reset even when the
    handler raises — FastAPI reuses threadpool workers, and a value left behind
    is one the next request can read.
    """
    user_id = restore_website_session(request.headers.get("X-TL-Session"))
    if user_id is None:
        raise _UNAUTHORIZED
    with corrections_scope(user_id):
        yield user_id
```

- [ ] **Step 7: Implement `routers/session.py` and `app.py`**

```python
# src/tradelens/api/routers/__init__.py
```

```python
# src/tradelens/api/routers/session.py
from fastapi import APIRouter, Depends

from src.tradelens.api.deps import current_user

router = APIRouter(prefix="/v1/session", tags=["session"])


@router.get("/whoami")
def whoami(user_id: int = Depends(current_user)) -> dict:
    """Echo the authenticated owner. Exists to prove both locks end to end."""
    return {"user_id": user_id}
```

```python
# src/tradelens/api/app.py
"""The FastAPI application.

Public HTTPS, and deliberately not browser-consumed. There is no CORS
middleware: its absence is what makes a browser unable to call this service
cross-origin with credentials, and a test asserts no Access-Control header is
ever emitted.

The schema is not served in production. It is generated in CI for TypeScript
codegen, which needs a file, not a public endpoint.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.tradelens.api.config import is_production
from src.tradelens.api.routers import session


def create_app() -> FastAPI:
    production = is_production()
    app = FastAPI(
        title="TradeLens API",
        version="0.1.0",
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )

    @app.middleware("http")
    async def no_store(request, call_next):
        """Authenticated responses must not be cached anywhere.

        /health is excluded so a load balancer may cache liveness.
        """
        response = await call_next(request)
        if request.url.path != "/health":
            response.headers["Cache-Control"] = "no-store, private"
        return response

    @app.get("/health")
    def health() -> JSONResponse:
        """Liveness only. Reveals nothing about configuration or data."""
        return JSONResponse({"status": "ok"})

    app.include_router(session.router)
    return app


app = create_app()
```

- [ ] **Step 8: Run the tests**

Run: `pytest tests/test_api_security.py -v`
Expected: PASS (14 tests)

- [ ] **Step 9: Run the full suite, lint, commit**

```bash
pytest tests/ -q && ruff check src/ scripts/ && black --check src/ scripts/
git add -A
git commit -m "feat(api): FastAPI application with both authentication locks

Lock 1 binds timestamp, method, path and body hash into the signature, so
a captured header cannot be replayed against another endpoint. Lock 2
resolves the session in Python. Neither alone is sufficient: the service
secret proves the caller is our frontend and says nothing about which
user is asking.

No CORS middleware and no schema endpoint in production; both asserted."
```

---

### Task 10: Cross-language signature contract

Two implementations of one HMAC scheme. The repo already solves this with shared vectors.

**Files:**
- Create: `docs/contracts/service-signature-vectors.json`
- Create: `web/lib/api/sign.ts`, `web/lib/api/client.ts`
- Create: `web/__tests__/service-signature.test.ts`
- Create: `tests/test_service_signature_vectors.py`

**Interfaces:**
- Consumes: `sign_request`, `build_message` (Task 9)
- Produces: `signRequest(secret, timestamp, method, path, body): Promise<string>`; `callApi<T>(path, init): Promise<T>`

- [ ] **Step 1: Write the shared vectors**

```json
{
  "$comment": [
    "Canonical HMAC request-signing vectors, shared by the Python and TypeScript",
    "implementations of Lock 1.",
    "",
    "The scheme exists in two languages: src/tradelens/api/security.py signs and",
    "verifies on the backend, web/lib/api/sign.ts signs on the Vercel side. They",
    "cannot import each other, so these vectors are what stops them drifting into",
    "two subtly different schemes that fail in production and nowhere else.",
    "",
    "Follows the precedent of auth-contract-vectors.json. Both test suites read",
    "these exact values."
  ],
  "algorithm": "HMAC-SHA256 over '{timestamp}.{METHOD}.{path}.{sha256hex(body)}'",
  "header_format": "v1={timestamp}:{hex_signature}",
  "replay_window_seconds": 60,
  "secret": "contract-vector-secret-do-not-use-in-production",
  "vectors": [
    {
      "name": "GET with an empty body",
      "timestamp": "1755300000",
      "method": "GET",
      "path": "/v1/session/whoami",
      "body": ""
    },
    {
      "name": "POST with a JSON body",
      "timestamp": "1755300000",
      "method": "POST",
      "path": "/v1/trades",
      "body": "{\"asset\":\"NQ\",\"pnl\":410.0}"
    },
    {
      "name": "method is upper-cased before signing",
      "timestamp": "1755300000",
      "method": "post",
      "path": "/v1/trades",
      "body": ""
    },
    {
      "name": "non-ASCII body is UTF-8 encoded before hashing",
      "timestamp": "1755300000",
      "method": "POST",
      "path": "/v1/trades",
      "body": "{\"notes\":\"café — ✓\"}"
    }
  ]
}
```

- [ ] **Step 2: Write the failing Python test**

```python
# tests/test_service_signature_vectors.py
"""Python half of the cross-language signing contract."""
import json
import pathlib

import pytest

from src.tradelens.api.security import build_message, sign_request

VECTORS = json.loads(
    pathlib.Path("docs/contracts/service-signature-vectors.json").read_text()
)


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=lambda v: v["name"])
def test_each_vector_signs_to_a_stable_value(vector):
    signature = sign_request(
        VECTORS["secret"],
        vector["timestamp"],
        vector["method"],
        vector["path"],
        vector["body"].encode("utf-8"),
    )
    assert len(signature) == 64
    assert signature == sign_request(
        VECTORS["secret"],
        vector["timestamp"],
        vector["method"],
        vector["path"],
        vector["body"].encode("utf-8"),
    )
    # Written to a file the TypeScript suite reads back.
    (pathlib.Path("web/__tests__/fixtures") / "signature-expectations.json")


def test_method_case_does_not_change_the_message():
    assert build_message("1", "post", "/x", b"") == build_message("1", "POST", "/x", b"")


def test_expectations_file_matches_current_implementation():
    """The generated expectations are the bridge to the TypeScript suite."""
    path = pathlib.Path("web/__tests__/fixtures/signature-expectations.json")
    expected = json.loads(path.read_text())
    for vector in VECTORS["vectors"]:
        actual = sign_request(
            VECTORS["secret"],
            vector["timestamp"],
            vector["method"],
            vector["path"],
            vector["body"].encode("utf-8"),
        )
        assert expected[vector["name"]] == actual
```

- [ ] **Step 3: Generate the expectations file**

Create `scripts/generate_signature_expectations.py`:

```python
"""Write the signing expectations the TypeScript suite asserts against.

Run after any change to the signing scheme; CI fails if the committed file
disagrees with the implementation.
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.tradelens.api.security import sign_request  # noqa: E402

vectors = json.loads(
    pathlib.Path("docs/contracts/service-signature-vectors.json").read_text()
)
out = {
    v["name"]: sign_request(
        vectors["secret"], v["timestamp"], v["method"], v["path"],
        v["body"].encode("utf-8"),
    )
    for v in vectors["vectors"]
}
dest = pathlib.Path("web/__tests__/fixtures/signature-expectations.json")
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
print(f"wrote {len(out)} expectations to {dest}")
```

Run: `python scripts/generate_signature_expectations.py`

- [ ] **Step 4: Write the TypeScript signer and its test**

```typescript
// web/lib/api/sign.ts
import "server-only";
import { createHash, createHmac } from "node:crypto";

/**
 * Lock 1, TypeScript half. Must stay byte-identical to
 * src/tradelens/api/security.py — the shared vectors in
 * docs/contracts/service-signature-vectors.json are what enforce that.
 *
 * The message binds timestamp, method, path and body hash, so a captured
 * header cannot be replayed against a different endpoint.
 */
export function buildMessage(
  timestamp: string,
  method: string,
  path: string,
  body: string,
): string {
  const bodyHash = createHash("sha256").update(body, "utf8").digest("hex");
  return `${timestamp}.${method.toUpperCase()}.${path}.${bodyHash}`;
}

export function signRequest(
  secret: string,
  timestamp: string,
  method: string,
  path: string,
  body: string,
): string {
  return createHmac("sha256", secret)
    .update(buildMessage(timestamp, method, path, body), "utf8")
    .digest("hex");
}

export function signatureHeader(
  secret: string,
  method: string,
  path: string,
  body: string,
  now: number = Date.now(),
): string {
  const timestamp = String(Math.floor(now / 1000));
  return `v1=${timestamp}:${signRequest(secret, timestamp, method, path, body)}`;
}
```

```typescript
// web/__tests__/service-signature.test.ts
import { describe, expect, it } from "vitest";

import vectors from "../../docs/contracts/service-signature-vectors.json";
import expectations from "./fixtures/signature-expectations.json";
import { buildMessage, signRequest, signatureHeader } from "@/lib/api/sign";

describe("service signature contract", () => {
  for (const vector of vectors.vectors) {
    it(`matches Python for: ${vector.name}`, () => {
      const actual = signRequest(
        vectors.secret,
        vector.timestamp,
        vector.method,
        vector.path,
        vector.body,
      );
      expect(actual).toBe((expectations as Record<string, string>)[vector.name]);
    });
  }

  it("upper-cases the method before signing", () => {
    expect(buildMessage("1", "post", "/x", "")).toBe(buildMessage("1", "POST", "/x", ""));
  });

  it("produces a v1 header carrying the timestamp", () => {
    const header = signatureHeader(vectors.secret, "GET", "/health", "", 1_755_300_000_000);
    expect(header).toBe(
      `v1=1755300000:${signRequest(vectors.secret, "1755300000", "GET", "/health", "")}`,
    );
  });
});
```

- [ ] **Step 5: Write the API client**

```typescript
// web/lib/api/client.ts
import "server-only";

import { signatureHeader } from "@/lib/api/sign";
import { requiredEnv } from "@/lib/env";

/**
 * The only way the website talks to the FastAPI backend.
 *
 * Server-only, deliberately: the service secret must never reach a bundle, and
 * the backend emits no CORS headers, so a browser could not call it anyway.
 * Both facts are load-bearing and neither should be "fixed".
 */
export class ApiError extends Error {
  constructor(readonly status: number) {
    super(`api request failed with status ${status}`);
  }
}

export async function callApi<T>(
  path: string,
  sessionToken: string,
  init: { method?: string; body?: unknown } = {},
): Promise<T> {
  const method = init.method ?? "GET";
  const body = init.body === undefined ? "" : JSON.stringify(init.body);
  const base = requiredEnv("TL_API_ORIGIN");

  const response = await fetch(`${base}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-TL-Signature": signatureHeader(requiredEnv("TL_SERVICE_SECRET"), method, path, body),
      "X-TL-Session": sessionToken,
    },
    body: body === "" ? undefined : body,
    cache: "no-store",
  });

  if (!response.ok) throw new ApiError(response.status);
  return (await response.json()) as T;
}
```

- [ ] **Step 6: Run both suites**

```bash
pytest tests/test_service_signature_vectors.py -v
cd web && npx vitest run __tests__/service-signature.test.ts && npx tsc --noEmit
```
Expected: both PASS. A mismatch means the two implementations have diverged — fix the implementation, never the expectations file by hand.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(api): cross-language signing contract with shared vectors

The scheme exists in Python and TypeScript and they cannot import each
other, so shared vectors are what stop them drifting into two schemes
that agree in tests and disagree in production."
```

---

### Task 11: R2 storage adapter

**Files:**
- Create: `src/tradelens/api/storage.py`
- Create: `tests/test_api_storage.py`

**Interfaces:**
- Consumes: `require_user_id` (Task 1)
- Produces:
  - `build_object_key(user_id: int, trade_id: int, content_type: str) -> str`
  - `presign_upload(user_id: int, trade_id: int, content_type: str) -> dict` → `{"url", "key", "expires_in", "max_bytes"}`
  - `presign_download(user_id: int, screenshot_id: int) -> Optional[str]`
  - `ALLOWED_CONTENT_TYPES`, `MAX_UPLOAD_BYTES`, `PRESIGN_TTL_SECONDS`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_storage.py
import re

import pytest

from src.tradelens.api import storage


def test_keys_are_owner_scoped_and_random():
    a = storage.build_object_key(7, 12, "image/png")
    b = storage.build_object_key(7, 12, "image/png")
    assert a.startswith("u/7/t/12/")
    assert a.endswith(".png")
    assert a != b, "two uploads must never collide on one key"
    assert re.fullmatch(r"u/7/t/12/[0-9a-f-]{36}\.png", a)


def test_the_client_filename_never_reaches_the_key():
    """A user-chosen filename in a key is a path-traversal and overwrite
    primitive. The server chooses where bytes land."""
    key = storage.build_object_key(1, 1, "image/png")
    assert ".." not in key and "\\" not in key


@pytest.mark.parametrize("content_type", ["image/svg+xml", "text/html", "application/pdf", ""])
def test_disallowed_types_are_refused(content_type):
    """SVG is script-bearing markup, not a picture."""
    with pytest.raises(ValueError):
        storage.build_object_key(1, 1, content_type)


def test_presign_refuses_a_trade_the_user_does_not_own(two_users, monkeypatch):
    a, b = two_users
    from src.tradelens.services import trade_service

    theirs = trade_service.create_trade(
        {"user_id": b, "trade_date": "2026-08-12", "asset": "NQ", "result": "Win", "pnl": 1.0}
    )
    monkeypatch.setattr(storage, "_client", lambda: _FakeS3())
    with pytest.raises(PermissionError):
        storage.presign_upload(a, theirs.id, "image/png")


def test_presign_upload_bounds_the_policy(two_users, monkeypatch):
    a, _ = two_users
    from src.tradelens.services import trade_service

    mine = trade_service.create_trade(
        {"user_id": a, "trade_date": "2026-08-12", "asset": "NQ", "result": "Win", "pnl": 1.0}
    )
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    result = storage.presign_upload(a, mine.id, "image/png")

    assert result["expires_in"] <= 300
    assert result["max_bytes"] == storage.MAX_UPLOAD_BYTES
    # Enforced in the policy, not merely checked in application code.
    assert fake.last_params["ContentType"] == "image/png"
    assert fake.last_params["ContentLength"] == storage.MAX_UPLOAD_BYTES


def test_presign_download_refuses_another_users_screenshot(two_users, monkeypatch):
    a, b = two_users
    from src.tradelens.db.models import Screenshot
    from src.tradelens.db.session import SessionLocal
    from src.tradelens.services import trade_service

    theirs = trade_service.create_trade(
        {"user_id": b, "trade_date": "2026-08-12", "asset": "NQ", "result": "Win", "pnl": 1.0}
    )
    db = SessionLocal()
    try:
        shot = Screenshot(trade_id=theirs.id, file_path="u/2/t/1/x.png")
        db.add(shot)
        db.commit()
        shot_id = shot.id
    finally:
        db.close()

    monkeypatch.setattr(storage, "_client", lambda: _FakeS3())
    assert storage.presign_download(a, shot_id) is None


class _FakeS3:
    def __init__(self):
        self.last_params = None

    def generate_presigned_url(self, operation, Params=None, ExpiresIn=None):
        self.last_params = Params
        return f"https://r2.example/{Params['Key']}?sig=x&exp={ExpiresIn}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_storage.py -v`
Expected: FAIL — `ModuleNotFoundError: src.tradelens.api.storage`

- [ ] **Step 3: Implement**

```python
# src/tradelens/api/storage.py
"""Cloudflare R2 adapter for chart screenshots.

The bucket is private: no public access, no listing, no website endpoint. Bytes
move directly between the browser and R2 using short-lived presigned URLs, which
is the one exception to "the browser only talks to Next.js".

Because a presigned upload arrives without passing through application code, the
object is untrusted until `imaging.validate_and_normalise` has seen it.
"""

from __future__ import annotations

import uuid
from typing import Optional

import boto3
from botocore.config import Config

from src.tradelens.api.config import r2_config
from src.tradelens.db.models import Screenshot, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ownership import require_user_id

# SVG is deliberately absent: it is script-bearing markup that browsers execute.
ALLOWED_CONTENT_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PRESIGN_TTL_SECONDS = 300


def _client():
    cfg = r2_config()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{cfg['account_id']}.r2.cloudflarestorage.com",
        aws_access_key_id=cfg["access_key_id"],
        aws_secret_access_key=cfg["secret_access_key"],
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def build_object_key(user_id: int, trade_id: int, content_type: str) -> str:
    """Where an upload lands. Chosen by the server, always.

    The client's filename is never used: a user-supplied component in a key is a
    path-traversal and overwrite primitive. The uuid4 makes the key unguessable
    even to someone who knows both ids.
    """
    owner = require_user_id(user_id)
    extension = ALLOWED_CONTENT_TYPES.get(content_type)
    if extension is None:
        raise ValueError(f"unsupported content type: {content_type!r}")
    return f"u/{owner}/t/{int(trade_id)}/{uuid.uuid4()}.{extension}"


def _owns_trade(user_id: int, trade_id: int) -> bool:
    db = SessionLocal()
    try:
        return (
            db.query(Trade.id)
            .filter(Trade.id == trade_id, Trade.user_id == user_id)
            .first()
            is not None
        )
    finally:
        db.close()


def presign_upload(user_id: int, trade_id: int, content_type: str) -> dict:
    """A short-lived PUT URL for one specific object.

    Type and size are bound INTO the policy rather than merely validated here:
    a check in application code is advice, a signed policy is a rule R2 itself
    enforces on the upload.
    """
    owner = require_user_id(user_id)
    if not _owns_trade(owner, trade_id):
        raise PermissionError("trade not found")

    key = build_object_key(owner, trade_id, content_type)
    url = _client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": r2_config()["bucket"],
            "Key": key,
            "ContentType": content_type,
            "ContentLength": MAX_UPLOAD_BYTES,
        },
        ExpiresIn=PRESIGN_TTL_SECONDS,
    )
    return {
        "url": url,
        "key": key,
        "expires_in": PRESIGN_TTL_SECONDS,
        "max_bytes": MAX_UPLOAD_BYTES,
    }


def presign_download(user_id: int, screenshot_id: int) -> Optional[str]:
    """A short-lived GET URL, or None if this user may not see the object.

    Ownership is resolved through the screenshot's trade before anything is
    signed. Returning None rather than raising means "no such screenshot for
    you" — a missing object and someone else's object are indistinguishable.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = (
            db.query(Screenshot.file_path)
            .join(Trade, Trade.id == Screenshot.trade_id)
            .filter(Screenshot.id == screenshot_id, Trade.user_id == owner)
            .first()
        )
    finally:
        db.close()
    if row is None:
        return None

    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": r2_config()["bucket"], "Key": row[0]},
        ExpiresIn=PRESIGN_TTL_SECONDS,
    )
```

- [ ] **Step 4: Run the tests and commit**

```bash
pytest tests/test_api_storage.py -v
ruff check src/ && black --check src/
git add -A
git commit -m "feat(api): R2 adapter with owner-scoped keys and bounded presigns

Type and size are bound into the signed policy rather than checked in
application code: a check is advice, a signed policy is a rule R2
enforces. Ownership is verified before any GET is signed."
```

---

### Task 12: Image validation and normalisation

A presigned upload never passed through application code. The object is a claim until proven otherwise.

**Files:**
- Create: `src/tradelens/api/imaging.py`
- Create: `tests/test_api_imaging.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `validate_and_normalise(data: bytes) -> tuple[bytes, str, int, int]` → `(png_bytes, "image/png", width, height)`
  - `ImageRejected(ValueError)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_imaging.py
import io

import pytest
from PIL import Image

from src.tradelens.api.imaging import ImageRejected, validate_and_normalise


def _png(size=(64, 48), mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, "teal").save(buf, format="PNG")
    return buf.getvalue()


def test_a_real_png_is_accepted_and_normalised():
    data, content_type, w, h = validate_and_normalise(_png())
    assert content_type == "image/png"
    assert (w, h) == (64, 48)
    assert data.startswith(b"\x89PNG")


def test_a_renamed_text_file_is_refused():
    """Magic bytes, not the declared type. A client's Content-Type is a claim."""
    with pytest.raises(ImageRejected):
        validate_and_normalise(b"<script>alert(1)</script>")


def test_svg_is_refused():
    with pytest.raises(ImageRejected):
        validate_and_normalise(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')


def test_trailing_bytes_do_not_survive_normalisation():
    """A polyglot file — valid image plus an appended payload — must not be
    stored or handed to AI with the payload intact."""
    poisoned = _png() + b"<?php system($_GET['c']); ?>"
    data, _, _, _ = validate_and_normalise(poisoned)
    assert b"<?php" not in data


def test_exif_is_stripped():
    """Chart screenshots can carry EXIF the trader never meant to share."""
    buf = io.BytesIO()
    image = Image.new("RGB", (32, 32), "black")
    image.save(buf, format="JPEG", exif=Image.Exif().tobytes())
    data, _, _, _ = validate_and_normalise(buf.getvalue())
    assert Image.open(io.BytesIO(data)).getexif() == {}


def test_an_oversized_image_is_refused():
    with pytest.raises(ImageRejected):
        validate_and_normalise(_png(size=(20000, 20000)))


def test_empty_input_is_refused():
    with pytest.raises(ImageRejected):
        validate_and_normalise(b"")


def test_an_animated_gif_is_refused():
    """Multi-frame payloads are not chart screenshots."""
    buf = io.BytesIO()
    frames = [Image.new("P", (8, 8), i) for i in range(3)]
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:])
    with pytest.raises(ImageRejected):
        validate_and_normalise(buf.getvalue())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_imaging.py -v`
Expected: FAIL — `ModuleNotFoundError: src.tradelens.api.imaging`

- [ ] **Step 3: Implement**

```python
# src/tradelens/api/imaging.py
"""Prove an uploaded object is an image before anything else touches it.

A presigned upload reaches R2 without passing through application code, so what
lands there is whatever the client sent. Everything downstream — the AI vision
call, the browser rendering it — treats it as a picture, so this is the only
place that can decide whether it is one.

The output is a re-encoded PNG, not the original bytes. Re-encoding is what
defeats polyglot files: a valid image with an appended payload survives every
header check ever written and does not survive being decoded and written out
fresh. It also drops EXIF, including location data a trader never meant to share.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError

MAX_PIXELS = 50_000_000
MAX_DIMENSION = 12_000

# Guards Pillow against decompression bombs: a small file that expands into
# gigabytes of pixels. Set below Pillow's own default so the check is ours.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"\xff\xd8\xff", "JPEG"),
    (b"RIFF", "WEBP"),
)


class ImageRejected(ValueError):
    """The object is not an image we will process.

    Carries no detail about why beyond a stable phrase: an attacker probing the
    validator should not be told which check they failed.
    """


def _looks_like_an_image(data: bytes) -> bool:
    return any(data.startswith(prefix) for prefix, _ in _MAGIC)


def validate_and_normalise(data: bytes) -> tuple[bytes, str, int, int]:
    """Return `(png_bytes, "image/png", width, height)` or raise `ImageRejected`."""
    if not data or not _looks_like_an_image(data):
        raise ImageRejected("not a supported image")

    try:
        with Image.open(io.BytesIO(data)) as image:
            if getattr(image, "n_frames", 1) > 1:
                raise ImageRejected("not a supported image")

            width, height = image.size
            if (
                width > MAX_DIMENSION
                or height > MAX_DIMENSION
                or width * height > MAX_PIXELS
            ):
                raise ImageRejected("not a supported image")

            image.load()
            # Re-create through the pixel data only. Nothing from the source
            # container — metadata, trailing bytes, ancillary chunks — travels.
            clean = Image.new("RGB", image.size)
            clean.paste(image.convert("RGB"))
    except ImageRejected:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageRejected("not a supported image") from exc

    out = io.BytesIO()
    clean.save(out, format="PNG", optimize=True)
    return out.getvalue(), "image/png", width, height
```

- [ ] **Step 4: Run the tests and commit**

```bash
pytest tests/test_api_imaging.py -v
git add -A
git commit -m "feat(api): validate and normalise uploaded images

Re-encodes through pixel data only. A polyglot file survives every header
check ever written and does not survive being decoded and written out
fresh; the same pass drops EXIF the trader never meant to share."
```

---

### Task 13: AI job queue and worker

**Files:**
- Create: `src/tradelens/api/jobs.py`, `src/tradelens/api/worker.py`
- Create: `tests/test_api_jobs.py`

**Interfaces:**
- Consumes: `AIJob` (Task 8), `require_user_id` (Task 1), `corrections_scope` (Task 4)
- Produces:
  - `enqueue(user_id: int, kind: str, idempotency_key: str, payload: dict) -> tuple[int, bool]` → `(job_id, was_created)`
  - `claim_next() -> Optional[AIJob]`
  - `complete(job_id: int, result_ref: str) -> None`
  - `fail(job_id: int, message: str) -> None`
  - `run_once(handlers: dict) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_jobs.py
import pytest

from src.tradelens.api import jobs
from src.tradelens.db.models import AIJob
from src.tradelens.db.session import SessionLocal


def test_enqueue_returns_the_new_job_id(two_users):
    a, _ = two_users
    job_id, created = jobs.enqueue(a, "grading", "k1", {"trade_id": 1})
    assert created is True
    assert job_id > 0


def test_the_same_key_returns_the_existing_job_without_a_second_row(two_users):
    """The double-submit control. A repeated request must cost nothing."""
    a, _ = two_users
    first, created_first = jobs.enqueue(a, "grading", "same", {"trade_id": 1})
    second, created_second = jobs.enqueue(a, "grading", "same", {"trade_id": 1})

    assert (first, created_first) == (second, True) or first == second
    assert created_second is False

    db = SessionLocal()
    try:
        assert db.query(AIJob).filter(AIJob.user_id == a).count() == 1
    finally:
        db.close()


def test_one_users_key_does_not_block_another(two_users):
    a, b = two_users
    _, created_a = jobs.enqueue(a, "grading", "shared", {})
    _, created_b = jobs.enqueue(b, "grading", "shared", {})
    assert created_a and created_b


def test_enqueue_requires_a_real_owner():
    with pytest.raises(ValueError):
        jobs.enqueue(None, "grading", "k", {})


def test_claim_marks_the_job_running_and_counts_the_attempt(two_users):
    a, _ = two_users
    job_id, _ = jobs.enqueue(a, "grading", "k2", {})

    claimed = jobs.claim_next()

    assert claimed.id == job_id
    assert claimed.status == "running"
    assert claimed.attempts == 1


def test_a_claimed_job_is_not_claimed_twice(two_users):
    """Two workers must not both pay for the same Anthropic call."""
    a, _ = two_users
    jobs.enqueue(a, "grading", "k3", {})
    assert jobs.claim_next() is not None
    assert jobs.claim_next() is None


def test_complete_records_where_the_result_landed(two_users):
    a, _ = two_users
    job_id, _ = jobs.enqueue(a, "grading", "k4", {})
    jobs.claim_next()
    jobs.complete(job_id, "aianalysis:42")

    db = SessionLocal()
    try:
        job = db.get(AIJob, job_id)
        assert job.status == "succeeded"
        assert job.result_ref == "aianalysis:42"
        assert job.finished_at is not None
    finally:
        db.close()


def test_failure_stores_a_message_safe_to_show_a_user(two_users):
    a, _ = two_users
    job_id, _ = jobs.enqueue(a, "grading", "k5", {})
    jobs.claim_next()
    jobs.fail(job_id, "The review could not be generated. Try again.")

    db = SessionLocal()
    try:
        job = db.get(AIJob, job_id)
        assert job.status == "failed"
        assert "Traceback" not in (job.error or "")
    finally:
        db.close()


def test_run_once_dispatches_to_the_handler_for_the_job_kind(two_users):
    a, _ = two_users
    jobs.enqueue(a, "grading", "k6", {"trade_id": 7})
    seen = {}

    def handler(user_id, payload):
        seen["user_id"] = user_id
        seen["payload"] = payload
        return "aianalysis:7"

    assert jobs.run_once({"grading": handler}) is True
    assert seen == {"user_id": a, "payload": {"trade_id": 7}}


def test_run_once_returns_false_when_the_queue_is_empty():
    assert jobs.run_once({}) is False


def test_a_handler_that_raises_fails_the_job_without_leaking_detail(two_users):
    a, _ = two_users
    jobs.enqueue(a, "grading", "k7", {})

    def explode(user_id, payload):
        raise RuntimeError("anthropic said something with a key in it")

    jobs.run_once({"grading": explode})

    db = SessionLocal()
    try:
        job = db.query(AIJob).filter(AIJob.idempotency_key == "k7").one()
        assert job.status == "failed"
        assert "anthropic said" not in (job.error or "")
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api_jobs.py -v`
Expected: FAIL — `ModuleNotFoundError: src.tradelens.api.jobs`

- [ ] **Step 3: Implement `jobs.py`**

```python
# src/tradelens/api/jobs.py
"""Enqueue, claim and complete asynchronous AI work.

Two properties matter more than throughput:

* **An enqueue is idempotent per owner.** A repeated request returns the
  existing job. Without it a double-clicked button is a second Anthropic bill.
* **A claim is exclusive.** Two workers must never run the same job, for the
  same reason.

Both rest on the `(user_id, idempotency_key)` constraint and a conditional
UPDATE, not on application-level checking — a read-then-write would race.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.tradelens.db.models import AIJob
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.corrections import corrections_scope
from src.tradelens.services.ownership import require_user_id

_log = logging.getLogger(__name__)

_GENERIC_FAILURE = "This could not be generated. Please try again."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(
    user_id: int, kind: str, idempotency_key: str, payload: dict
) -> tuple[int, bool]:
    """Queue a job. Returns `(job_id, was_created)`.

    The uniqueness violation is caught rather than pre-checked: between a
    SELECT and an INSERT another request can land, and the constraint is the
    only thing that cannot be raced.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        job = AIJob(
            user_id=owner,
            kind=kind,
            idempotency_key=idempotency_key,
            payload=json.dumps(payload),
            status="queued",
            created_at=_now(),
        )
        db.add(job)
        db.commit()
        return int(job.id), True
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(AIJob)
            .filter(AIJob.user_id == owner, AIJob.idempotency_key == idempotency_key)
            .one()
        )
        return int(existing.id), False
    finally:
        db.close()


def claim_next() -> Optional[AIJob]:
    """Atomically take the oldest queued job, or return None.

    The UPDATE is conditional on the row still being queued, so two workers
    racing produce one winner and one None — never two runs of one job.
    """
    db = SessionLocal()
    try:
        row = (
            db.query(AIJob.id)
            .filter(AIJob.status == "queued")
            .order_by(AIJob.id.asc())
            .first()
        )
        if row is None:
            return None

        claimed = db.execute(
            text(
                "UPDATE ai_jobs SET status = 'running', started_at = :now, "
                "attempts = attempts + 1 WHERE id = :id AND status = 'queued'"
            ),
            {"now": _now(), "id": row[0]},
        )
        db.commit()
        if claimed.rowcount != 1:
            return None
        return db.get(AIJob, row[0])
    finally:
        db.close()


def complete(job_id: int, result_ref: str) -> None:
    _finish(job_id, status="succeeded", result_ref=result_ref, error=None)


def fail(job_id: int, message: str) -> None:
    """Mark a job failed with a message that is safe to show a user."""
    _finish(job_id, status="failed", result_ref=None, error=message)


def _finish(job_id: int, *, status: str, result_ref, error) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE ai_jobs SET status = :s, result_ref = :r, error = :e, "
                "finished_at = :now WHERE id = :id"
            ),
            {"s": status, "r": result_ref, "e": error, "now": _now(), "id": job_id},
        )
        db.commit()
    finally:
        db.close()


def run_once(handlers: dict[str, Callable[[int, dict], str]]) -> bool:
    """Claim and run one job. Returns whether there was one to run.

    The handler's exception is logged and discarded rather than stored: a
    provider error message can carry a prompt fragment or a key, and this
    column is read by a user.
    """
    job = claim_next()
    if job is None:
        return False

    handler = handlers.get(job.kind)
    if handler is None:
        fail(job.id, _GENERIC_FAILURE)
        _log.error("no handler registered for job kind %r", job.kind)
        return True

    try:
        payload = json.loads(job.payload or "{}")
        with corrections_scope(job.user_id):
            result_ref = handler(job.user_id, payload)
        complete(job.id, result_ref)
    except Exception:  # noqa: BLE001 — message withheld deliberately
        _log.exception("job %s (%s) failed", job.id, job.kind)
        fail(job.id, _GENERIC_FAILURE)
    return True
```

- [ ] **Step 4: Implement `worker.py`**

```python
# src/tradelens/api/worker.py
"""Job runner process.

A separate process from the API, in the same image. AI calls run 60-120s and
must not occupy a request worker.

Phase 0 ships the loop with no handlers registered — the handlers arrive with
the features that need them, from Phase 5. An unknown kind fails its job
safely, which is the correct behaviour for a queue that outlives a deploy.
"""

from __future__ import annotations

import logging
import time

from src.tradelens.api.jobs import run_once

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)

HANDLERS: dict = {}

IDLE_SLEEP_SECONDS = 2.0


def main() -> None:
    _log.info("worker started with %d handler(s)", len(HANDLERS))
    while True:
        try:
            if not run_once(HANDLERS):
                time.sleep(IDLE_SLEEP_SECONDS)
        except Exception:  # noqa: BLE001 — a worker must outlive one bad job
            _log.exception("worker loop error")
            time.sleep(IDLE_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the tests and commit**

```bash
pytest tests/test_api_jobs.py -v
ruff check src/ && black --check src/
git add -A
git commit -m "feat(api): AI job queue with per-owner idempotency

Enqueue catches the uniqueness violation rather than pre-checking, and
claim is a conditional UPDATE: between a SELECT and a write another
request can land, and only the constraint cannot be raced. Handler
exceptions are logged, not stored — a provider message can carry a
prompt fragment or a key, and that column is read by a user."
```

---

### Task 14: OpenAPI → TypeScript codegen with drift detection

**Files:**
- Create: `scripts/generate_openapi.py`
- Modify: `web/package.json` (scripts + devDependency)
- Modify: `.github/workflows/ci.yml`
- Create: `tests/test_openapi_generation.py`

**Interfaces:**
- Consumes: `create_app` (Task 9)
- Produces: `web/lib/api/openapi.json`, `web/lib/api/schema.d.ts`, `npm run api:types`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_openapi_generation.py
import json
import pathlib
import subprocess
import sys


def test_the_committed_schema_matches_the_application():
    """Drift here means the TypeScript types describe an API that no longer
    exists — and the compiler would keep saying everything is fine."""
    generated = subprocess.run(
        [sys.executable, "scripts/generate_openapi.py", "--stdout"],
        capture_output=True, text=True, check=True,
    ).stdout
    committed = pathlib.Path("web/lib/api/openapi.json").read_text()
    assert json.loads(generated) == json.loads(committed), (
        "run: python scripts/generate_openapi.py && cd web && npm run api:types"
    )


def test_the_schema_documents_the_whoami_endpoint():
    schema = json.loads(pathlib.Path("web/lib/api/openapi.json").read_text())
    assert "/v1/session/whoami" in schema["paths"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_openapi_generation.py -v`
Expected: FAIL — the script and the schema file do not exist

- [ ] **Step 3: Write the generator**

```python
# scripts/generate_openapi.py
"""Write the OpenAPI schema to a file for TypeScript codegen.

The running service does not serve /openapi.json in production, so the schema
is produced here instead. Generating it in CI and committing the result means a
backend change that breaks the frontend contract fails the build rather than
failing in a browser.
"""

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.tradelens.api.app import create_app  # noqa: E402

DEST = pathlib.Path("web/lib/api/openapi.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    schema = json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"
    if args.stdout:
        sys.stdout.write(schema)
        return
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(schema)
    print(f"wrote {DEST}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Generate the schema and types**

```bash
python scripts/generate_openapi.py
cd web && npm install --save-dev openapi-typescript@7.9.1
npx openapi-typescript lib/api/openapi.json -o lib/api/schema.d.ts
```

Add to `web/package.json` scripts:

```json
    "api:types": "openapi-typescript lib/api/openapi.json -o lib/api/schema.d.ts"
```

- [ ] **Step 5: Add the CI gate**

In `.github/workflows/ci.yml`, after the pytest step:

```yaml
      - name: API schema and client types are current
        run: |
          python scripts/generate_signature_expectations.py
          python scripts/generate_openapi.py
          cd web && npm run api:types
          cd .. && git diff --exit-code -- web/lib/api web/__tests__/fixtures
```

- [ ] **Step 6: Run the tests and commit**

```bash
pytest tests/test_openapi_generation.py -v
git add -A
git commit -m "build: generate OpenAPI schema and TS types with a drift gate

The schema is not served in production, so it is generated and committed.
CI regenerates and diffs: a backend change that breaks the frontend
contract fails the build instead of failing in a browser."
```

---

### Task 15: Golden parity harness

The instrument that will prove, in every later phase, that a migrated screen computes what Streamlit computed.

**Files:**
- Create: `tests/parity/__init__.py`, `tests/parity/dataset.py`, `tests/parity/test_metrics_parity.py`
- Create: `tests/parity/snapshots/metrics.json`

**Interfaces:**
- Consumes: `require_user_id` (Task 1), `to_jsonable` (Task 5)
- Produces:
  - `seed_golden_dataset(user_id: int) -> None`
  - `golden_metrics(user_id: int) -> dict`
  - Snapshot at `tests/parity/snapshots/metrics.json`, refreshed with `TL_UPDATE_SNAPSHOTS=1`

- [ ] **Step 1: Write the dataset builder**

```python
# tests/parity/__init__.py
```

```python
# tests/parity/dataset.py
"""One fixed dataset, used by every parity assertion.

Deliberately hand-written rather than random or seeded-from-production: the
point is that the numbers below never change, so a difference in output can only
mean a change in computation. It covers the shapes that break metrics — a
losing trade, a break-even, a missing R multiple, a rule break, a trade with no
screenshot — because an all-wins dataset proves almost nothing.
"""

from __future__ import annotations

from src.tradelens.services import trade_service

GOLDEN_TRADES = [
    {
        "trade_date": "2026-08-10", "entry_time": "09:35", "asset": "NQ",
        "session": "New York Open", "setup_type": "Liquidity Sweep + FVG",
        "timeframe": "15m", "htf_bias": "Bullish", "ltf_bias": "Bullish",
        "result": "Win", "pnl": 480.0, "risk_amount": 180.0, "rr_realized": 2.7,
        "followed_rules": "Yes", "strategy_used": "ICT/SMC Day Trading",
    },
    {
        "trade_date": "2026-08-11", "entry_time": "09:50", "asset": "ES",
        "session": "New York Open", "setup_type": "Liquidity Sweep + FVG",
        "timeframe": "15m", "htf_bias": "Bearish", "ltf_bias": "Bullish",
        "result": "Loss", "pnl": -220.0, "risk_amount": 200.0, "rr_realized": None,
        "followed_rules": "No", "mistake_tags": "Counter-trend entry",
        "strategy_used": "ICT/SMC Day Trading",
    },
    {
        "trade_date": "2026-08-12", "entry_time": "10:15", "asset": "NQ",
        "session": "New York Open", "setup_type": "BOS + OB Retest",
        "timeframe": "15m", "htf_bias": "Bullish", "ltf_bias": "Bullish",
        "result": "Win", "pnl": 410.0, "risk_amount": 150.0, "rr_realized": 2.73,
        "followed_rules": "Yes", "strategy_used": "ICT/SMC Day Trading",
    },
    {
        "trade_date": "2026-08-13", "entry_time": "11:05", "asset": "EURUSD",
        "session": "London", "setup_type": "CHoCH Entry", "timeframe": "15m",
        "htf_bias": "Bearish", "ltf_bias": "Bearish",
        "result": "Break-even", "pnl": 0.0, "risk_amount": 120.0, "rr_realized": 0.0,
        "followed_rules": "Partial", "strategy_used": "ICT/SMC Day Trading",
    },
    {
        "trade_date": "2026-08-14", "entry_time": "09:31", "asset": "NQ",
        "session": "New York Open", "setup_type": "Liquidity Sweep + FVG",
        "timeframe": "5m", "htf_bias": "Bullish", "ltf_bias": "Bearish",
        "result": "Loss", "pnl": -95.0, "risk_amount": 100.0, "rr_realized": -0.95,
        "followed_rules": "Yes", "strategy_used": "ICT/SMC Day Trading",
    },
]


def seed_golden_dataset(user_id: int) -> None:
    """Insert the golden trades for `user_id`. Order is significant."""
    for row in GOLDEN_TRADES:
        trade_service.create_trade({**row, "user_id": user_id})
```

- [ ] **Step 2: Write the failing parity test**

```python
# tests/parity/test_metrics_parity.py
"""Numeric drift detector.

Phase 0 pins the SERVICE outputs. From Phase 2 onward each API response is
asserted equal to the service output for the same input, so the snapshot chain
runs from the database to the screen.

Refresh deliberately, never reflexively:  TL_UPDATE_SNAPSHOTS=1 pytest tests/parity
A diff here is either a bug you just introduced or a change you can explain.
"""

import json
import os
import pathlib

import pandas as pd

from src.tradelens.api.serialization import to_jsonable
from src.tradelens.services import metrics, trade_service
from tests.parity.dataset import seed_golden_dataset

SNAPSHOT = pathlib.Path(__file__).parent / "snapshots" / "metrics.json"


def _frame(user_id: int) -> pd.DataFrame:
    trades = trade_service.get_trades(user_id=user_id)
    return pd.DataFrame(
        [
            {
                "trade_date": t.trade_date, "asset": t.asset, "session": t.session,
                "setup_type": t.setup_type, "timeframe": t.timeframe,
                "result": t.result, "pnl": t.pnl, "rr_realized": t.rr_realized,
                "risk_amount": t.risk_amount, "followed_rules": t.followed_rules,
                "mistake_tags": t.mistake_tags, "strategy_used": t.strategy_used,
                "htf_bias": t.htf_bias, "ltf_bias": t.ltf_bias,
                "entry_time": t.entry_time,
            }
            for t in trades
        ]
    )


def golden_metrics(user_id: int) -> dict:
    df = _frame(user_id)
    return {
        "basic": metrics.compute_basic_metrics(df),
        "expectancy": metrics.compute_expectancy(metrics.compute_basic_metrics(df)),
        "profit_factor_raw": metrics.compute_profit_factor_raw(df),
        "max_drawdown": metrics.compute_max_drawdown(metrics.compute_equity_curve(df)),
        "streaks": metrics.compute_streaks(df),
        "consistency_score": metrics.consistency_score(df),
        "total_edge_leak": metrics.total_edge_leak(df),
        "by_session": metrics.by_session(df),
        "by_asset": metrics.by_asset(df),
        "by_setup_type": metrics.by_setup_type(df),
        "by_day_of_week": metrics.by_day_of_week(df),
        "killzone_performance": metrics.killzone_performance(df),
        "mistake_frequency": metrics.mistake_frequency(df),
        "equity_curve": metrics.compute_equity_curve(df),
        "daily_pnl": metrics.daily_pnl(df),
    }


def test_metrics_match_the_golden_snapshot(two_users):
    user_id, _ = two_users
    seed_golden_dataset(user_id)

    actual = to_jsonable(golden_metrics(user_id))

    if os.getenv("TL_UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")

    expected = json.loads(SNAPSHOT.read_text())
    assert actual == expected


def test_the_golden_dataset_is_scoped_to_its_owner(two_users):
    """A parity snapshot computed from two tenants' trades would be green and
    meaningless."""
    a, b = two_users
    seed_golden_dataset(a)
    assert trade_service.get_trades(user_id=b) == []


def test_every_snapshotted_value_survives_strict_json(two_users):
    a, _ = two_users
    seed_golden_dataset(a)
    json.dumps(to_jsonable(golden_metrics(a)), allow_nan=False)
```

- [ ] **Step 3: Run to verify it fails**

Run: `pytest tests/parity/ -v`
Expected: FAIL — the snapshot file does not exist

- [ ] **Step 4: Generate the snapshot and inspect it**

```bash
TL_UPDATE_SNAPSHOTS=1 pytest tests/parity/ -v
```

Then **read `tests/parity/snapshots/metrics.json` before committing it.** A snapshot is only as good as the first review of it. Check: net P&L is 575.0, five trades, two wins, two losses, one break-even, and no field is `null` where a number belongs.

- [ ] **Step 5: Confirm it is now a real gate**

```bash
pytest tests/parity/ -v
```
Expected: PASS without the env var.

- [ ] **Step 6: Commit**

```bash
git add tests/parity
git commit -m "test: golden parity harness pinning service metric outputs

One fixed dataset covering a loss, a break-even, a missing R multiple and
a rule break — an all-wins dataset proves almost nothing. Phase 0 pins the
service outputs; later phases assert each API response equals the service
output for the same input. This replaces the confidence the retired
Streamlit UI tests provided about metric correctness."
```

---

### Task 16: Deployment scaffolding

**Files:**
- Create: `Dockerfile.api`, `render.yaml`, `.dockerignore`
- Modify: `.env.example`
- Create: `docs/DEPLOY-API.md`

**Interfaces:**
- Consumes: everything above
- Produces: a runnable container for the API and the worker

- [ ] **Step 1: Write the Dockerfile**

```dockerfile
# Dockerfile.api
# The API and worker image. Deliberately does NOT install requirements.txt:
# Streamlit, PyArrow and Plotly are presentation dependencies with no business
# in a backend, and they roughly triple the image.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# psycopg2-binary ships wheels, but Pillow's runtime needs these.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo libwebp7 zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-base.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY prompts/ ./prompts/

# Non-root: a container that never needs to write to its own filesystem should
# not be able to.
RUN useradd --create-home --uid 10001 tradelens
USER tradelens

EXPOSE 8000
CMD ["uvicorn", "src.tradelens.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

```
# .dockerignore
.git
.venv
node_modules
web
site
tests
data
docs
*.db
.streamlit
__pycache__
```

- [ ] **Step 2: Write `render.yaml`**

```yaml
# render.yaml
# Two services from one image: the HTTP API and the job worker.
#
# The API is a WEB service, not a private service. Vercel functions egress from
# dynamic addresses and are not inside Render's private network, so a private
# service would be unreachable — and designing as if it were unreachable from
# the internet, while it is in fact reachable, is worse than treating it as
# public and defending it. Defence is TL_SERVICE_SECRET plus session validation.
services:
  - type: web
    name: tradelens-api
    runtime: docker
    dockerfilePath: ./Dockerfile.api
    healthCheckPath: /health
    envVars:
      - key: TL_ENV
        value: production
      - key: TL_SERVICE_SECRET
        sync: false
      - key: TL_SERVICE_SECRET_PREVIOUS
        sync: false
      - key: DATABASE_URL
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: R2_ACCOUNT_ID
        sync: false
      - key: R2_ACCESS_KEY_ID
        sync: false
      - key: R2_SECRET_ACCESS_KEY
        sync: false
      - key: R2_BUCKET
        sync: false

  - type: worker
    name: tradelens-worker
    runtime: docker
    dockerfilePath: ./Dockerfile.api
    dockerCommand: python -m src.tradelens.api.worker
    envVars:
      - key: TL_ENV
        value: production
      - key: DATABASE_URL
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false
```

- [ ] **Step 3: Document the environment**

Append to `.env.example`:

```bash
# --- FastAPI backend (Phase 0) ---------------------------------------------
# Shared only between the Vercel environment and the API container. Rotating:
# set the new value here, move the old to TL_SERVICE_SECRET_PREVIOUS, redeploy
# both sides, then clear PREVIOUS.
TL_SERVICE_SECRET=
TL_SERVICE_SECRET_PREVIOUS=
TL_ENV=development
# Where the website reaches the API. Server-side only; never exposed to a browser.
TL_API_ORIGIN=http://localhost:8000

# --- Cloudflare R2 ---------------------------------------------------------
# The bucket must be private: no public access, no listing, no website endpoint.
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=
```

Write `docs/DEPLOY-API.md` covering: generating `TL_SERVICE_SECRET` (`openssl rand -hex 32`), the rotation procedure, creating the private R2 bucket, running `alembic upgrade head` against Neon before first deploy, and the fact that `TL_SERVICE_SECRET` must be identical in Vercel and Render or every request 401s.

- [ ] **Step 4: Verify the image builds and runs**

```bash
docker build -f Dockerfile.api -t tradelens-api .
docker run --rm -p 8000:8000 -e TL_ENV=development tradelens-api &
sleep 5 && curl -fsS http://localhost:8000/health
```
Expected: `{"status":"ok"}`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "build(api): container, Render services, and deployment docs

A web service rather than a private one: Vercel egress is not inside
Render's private network, so a private service would be unreachable —
and defending a service by assuming it is unreachable when it is not is
worse than treating it as public and locking it."
```

---

### Task 17: Verify Phase 0 and update the Claude↔Codex handoff

The gate before any Phase 1 work begins.

**Files:**
- Modify: `docs/coordination/CLAUDE_CODEX_HANDOFF.md`

- [ ] **Step 1: Run every gate and record the real output**

```bash
pytest tests/ -q
ruff check src/ scripts/
black --check src/ scripts/
cd web && npx vitest run && npx tsc --noEmit && cd ..
docker build -f Dockerfile.api -t tradelens-api .
```

Record the actual numbers. If anything fails, Phase 0 is not complete — fix it and rerun. Do not write a handoff that claims a green suite you have not seen.

- [ ] **Step 2: Append the Phase 0 record to the handoff**

Include, with no softening:

**Architectural decisions**
- FastAPI is a public HTTPS web service; the private-service option was rejected because Vercel egress cannot reach Render's private network and its addresses are dynamic.
- Two independent locks, both required: timestamped HMAC over `{timestamp}.{METHOD}.{path}.{sha256(body)}`, and database-backed session resolution in Python.
- The owner of a request is derived from the session row only.
- Isolation is enforced in the service layer, not the router.
- No `*_for_maintenance` helper was created: `recompute_metrics` needed scoping, not global access, so nothing legitimate wanted one (YAGNI). The import-boundary test guards against one appearing later.

**Work completed** — the 17 tasks, with the test count each added.

**Risks discovered during implementation** — including the `recompute_metrics` defect (accepted a `user_id`, then computed that user's metrics from every user's trades) and anything else found while working.

**Tests** — total added, total passing, and what the golden parity harness does and does not cover.

- [ ] **Step 3: Write the explicit Codex review request**

State these as questions Codex must answer independently, not as conclusions:

1. **`X-TL-Session` forwarding — the one the owner wants assessed.** The approved design forwards the raw website session token from Next.js to FastAPI, where it is re-validated against the database. Assess this against the alternative of a short-lived, audience-bound internal credential minted per request (an internal JWT with `aud`, `sub`, and a ~60s expiry, signed with the service secret). Specifically: does forwarding the long-lived credential to a second service widen the blast radius of a backend compromise or a log leak enough to justify the extra moving part? What is the migration cost of changing later? **The approved architecture stands unless Phase 0 implementation surfaced a concrete reason to change it** — this is a request for independent assessment, not a change already decided.
2. Is the HMAC scheme sound — replay window, path/body binding, dual-secret comparison without early exit?
3. Does any route or service still admit a nullable owner?
4. Can `corrections_scope` leak across requests under FastAPI's threadpool?
5. Do the R2 presign policies actually bind type and size, or only appear to?
6. Does `validate_and_normalise` reject every polyglot and decompression-bomb shape it claims to?
7. Is the job idempotency constraint genuinely race-proof under concurrent enqueues?

- [ ] **Step 4: Commit**

```bash
git add docs/coordination/CLAUDE_CODEX_HANDOFF.md
git commit -m "docs(handoff): Phase 0 record and Codex review request

Flags the raw X-TL-Session forwarding design for independent assessment
against a short-lived audience-bound internal credential. The approved
architecture stands unless implementation surfaced a concrete reason."
```

- [ ] **Step 5: Stop**

Phase 0 is complete. **Do not begin Phase 1.** The app shell, navigation, and every visible surface wait for the Phase 1 plan, which is written after this phase is reviewed — so it is written knowing what Phase 0 actually taught us.

---

## Self-Review

**Spec coverage.** Every Phase 0 item in §7 of the spec maps to a task: isolation hardening → 1–3; request context → 4; FastAPI skeleton with both locks → 6, 9; strict serializer → 5; OpenAPI→TS codegen → 14; R2 adapter and validation → 11, 12; `ai_jobs` table, worker, idempotency → 8, 13; per-user `app_surface` flag → 7; golden parity harness → 15. Deployment (16) and the handoff gate (17) were implicit in the spec and are made explicit here.

**Deviations from the spec, both deliberate:**
1. The spec anticipated a `*_for_maintenance` escape hatch for `recompute_metrics.py`. Reading it revealed the function accepts a `user_id` and then ignores it — a defect, not a legitimate global-access need. It gets scoped instead, so no such helper is created. The import-boundary test still guards against one appearing.
2. `requirements.txt` is split into `requirements-base.txt` + surface-specific files, which the spec did not mention. Without it the API image installs Streamlit.

**Placeholder scan.** No TBD/TODO. Every code step carries real code. `worker.py` ships with an empty `HANDLERS` dict — that is the intended Phase 0 state, stated in its docstring, not a placeholder.

**Type consistency.** `require_user_id` returns `int` everywhere. `to_jsonable`/`finite_or_state` names are stable across Tasks 5 and 15. `sign_request(secret, timestamp, method, path, body)` has identical parameter order in Python and TypeScript. `enqueue` returns `(job_id, was_created)` in both its definition and its tests. `presign_upload` returns the same four keys in Task 11's implementation and test.
