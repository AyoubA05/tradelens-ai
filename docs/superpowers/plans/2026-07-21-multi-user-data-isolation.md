# Multi-User Data Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status 2026-07-26 — implemented by the owner before this session.**
> The steps below are left unticked because they were not executed here;
> this note records what was verified instead of ticking them second-hand.
>
> The audit's two named failures are both closed: `get_active_strategy` and
> `upsert_strategy_profile` take a concrete `user_id`, and timezone moved
> from a global JSON file to the user-scoped `user_settings` table
> (`get_timezone(user_id)` / `set_timezone(user_id, tz)`). Weekly reviews,
> trades, corrections, and AI usage are all owner-scoped.
>
> Verified by `tests/test_user_isolation.py`, `test_strategy.py`,
> `test_app_settings.py`, and `test_weekly_review.py` (51 passing), plus
> `tests/test_account_deletion.py`, which walks every `user_id`-bearing
> table and asserts one account's deletion leaves another's data intact.

**Goal:** Ensure every authenticated trader can access only their own trades, strategy profile, timezone setting, reviews, corrections, screenshots, and AI usage before the beta accepts multiple real users.

**Architecture:** Add ownership to Strategy and a small keyed UserSetting table, then require `user_id` at every user-facing service boundary. Migrate legacy NULL-owned data through a dry-run/apply script after a database backup. Keep relationship-based screenshot and AI-analysis ownership through their parent trade; add defense-in-depth checks on direct ID reads, updates, and deletes.

**Tech Stack:** Python 3.11, SQLAlchemy, Alembic, SQLite/Postgres-compatible migrations, pytest.

## Global Constraints

- This is a security/data-integrity plan, not UI polish; schema changes are limited to ownership and settings isolation.
- No AI service or `services/ai_client.py` changes.
- No new dependencies.
- `user_id` is required for every user-facing read/update/delete. Service functions may retain an explicit unscoped internal path only for administrative scripts and tests.
- Registered users must never receive rows with `user_id IS NULL` as a compatibility fallback.
- Legacy data is assigned only after a backup and a dry run. The assignment command targets the existing owner account `ayoub` unless the owner deliberately supplies a different username at execution time.
- The migration must run on SQLite and Postgres.
- Do not expose account IDs or usernames in screenshots, analytics events, or AI prompts beyond the existing ownership field needed for database scoping.
- Use a dedicated schema worktree/session. Do not run it concurrently with another migration session.
- Preserve unrelated dirty work and stage exact paths only.

---

## File structure

- `alembic/versions/q7r8s9t0u1v2_add_user_owned_strategy_settings.py` - ownership schema.
- `src/tradelens/db/models.py` - `Strategy.user_id` and `UserSetting` ORM mappings.
- `src/tradelens/services/strategy.py` - user-scoped strategy APIs.
- `src/tradelens/services/app_settings.py` - user-scoped DB-backed preferences.
- `src/tradelens/services/trade_service.py` - exact ownership filters on direct trade operations.
- `scripts/assign_legacy_data.py` - safe, auditable legacy assignment.
- `tests/test_user_isolation.py` - cross-user denial contracts.
- `tests/test_strategy.py`, `tests/test_app_settings.py`, `tests/test_trade_service.py` - updated service contracts.

---

### Task 1: Add strategy ownership and user settings schema

**Files:**
- Create: `alembic/versions/q7r8s9t0u1v2_add_user_owned_strategy_settings.py`
- Modify: `src/tradelens/db/models.py:19-40,208-230`
- Modify: `tests/test_migrations.py`

**Interfaces:**
- Produces: nullable `strategies.user_id` foreign key/index for migration compatibility and `user_settings(id, user_id, key, value, updated_at)` with unique `(user_id, key)`.

- [ ] **Step 1: Write failing model/migration tests**

Add:

```python
from src.tradelens.db.models import Strategy, UserSetting


def test_strategy_has_user_owner_column():
    assert "user_id" in Strategy.__table__.columns
    assert Strategy.__table__.columns["user_id"].index


def test_user_setting_has_unique_user_key_pair():
    names = {c.name for c in UserSetting.__table__.constraints}
    assert "uq_user_settings_user_key" in names
```

Add a migration-chain test asserting revision `q7r8s9t0u1v2` descends from current head `p6q7r8s9t0u1`.

- [ ] **Step 2: Run and verify failure**

Run: `.venv/bin/python -m pytest tests/test_migrations.py -q`  
Expected: FAIL because the model and revision do not exist.

- [ ] **Step 3: Add ORM ownership**

In `Strategy`:

```python
user_id: Mapped[Optional[int]] = mapped_column(
    ForeignKey("users.id"), nullable=True, index=True
)
```

Add:

```python
class UserSetting(Base):
    __tablename__ = "user_settings"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_user_settings_user_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
```

- [ ] **Step 4: Write the Alembic revision**

The upgrade adds `strategies.user_id`, its index and FK, then creates `user_settings` plus its indexes/unique constraint. The downgrade drops `user_settings`, then the strategy FK/index/column in reverse order. Use `batch_alter_table("strategies")` for SQLite compatibility.

- [ ] **Step 5: Verify migration on SQLite**

Run:

```bash
DATABASE_URL=sqlite:////tmp/tradelens-isolation.db .venv/bin/alembic upgrade head
DATABASE_URL=sqlite:////tmp/tradelens-isolation.db .venv/bin/alembic downgrade p6q7r8s9t0u1
DATABASE_URL=sqlite:////tmp/tradelens-isolation.db .venv/bin/alembic upgrade head
```

Expected: all commands exit 0.

- [ ] **Step 6: Run tests and commit**

Run: `.venv/bin/python -m pytest tests/test_migrations.py tests/test_init_db_reconcile.py -q`  
Expected: PASS.

```bash
git add alembic/versions/q7r8s9t0u1v2_add_user_owned_strategy_settings.py src/tradelens/db/models.py tests/test_migrations.py
git commit -m "schema: add user-owned strategies and settings"
```

### Task 2: Scope Strategy Profile by authenticated user

**Files:**
- Modify: `src/tradelens/services/strategy.py:114-205`
- Modify: `src/tradelens/ui/app.py:151-159`
- Modify: `src/tradelens/ui/components/sidebar.py:86-115`
- Modify: `src/tradelens/ui/pages/1_NewTrade.py:130-150`
- Modify: `src/tradelens/ui/pages/2_Trades.py`
- Modify: `src/tradelens/ui/pages/4_Analytics.py:60-70`
- Modify: `src/tradelens/ui/pages/5_Strategy.py:60-275`
- Modify: `src/tradelens/ui/pages/6_Insights.py:100-125`
- Modify: `tests/test_strategy.py`

**Interfaces:**
- Produces: `get_active_strategy(user_id: int) -> Optional[dict]`, `upsert_strategy_profile(user_id: int, **fields) -> dict`, and `append_insight(user_id: int, insight: str, field: str = "risk_rules") -> dict`.

- [ ] **Step 1: Write cross-user service tests**

Create two users, upsert one strategy for each, and assert each `get_active_strategy(user_id)` returns only its owner's name. Updating user B must not deactivate user A's profile.

- [ ] **Step 2: Run and verify failure**

Run: `.venv/bin/python -m pytest tests/test_strategy.py -q -k user`  
Expected: FAIL because APIs are global.

- [ ] **Step 3: Replace global filters**

Use exact ownership in every query:

```python
def get_active_strategy(user_id: int) -> Optional[dict]:
    db = SessionLocal()
    try:
        row = (
            db.query(Strategy)
            .filter(Strategy.user_id == user_id, Strategy.is_active == 1)
            .first()
        )
        return _to_dict(row) if row else None
    finally:
        db.close()
```

In `upsert_strategy_profile`, deactivate and select only `Strategy.user_id == user_id`; set `user_id=user_id` on create. In `append_insight`, use the same exact filter and ownership on create.

- [ ] **Step 4: Pass `current_user_id()` from every UI caller**

At each call site, compute `uid = current_user_id()` once per page and pass it explicitly. Change `render_sidebar()` to call `current_user_id()` before `get_active_strategy(uid)`.

- [ ] **Step 5: Verify and commit**

Run:

```bash
.venv/bin/python -m pytest tests/test_strategy.py tests/test_pages_boot.py tests/test_insights_page.py -q
.venv/bin/ruff check src/tradelens/services/strategy.py src/tradelens/ui/app.py src/tradelens/ui/components/sidebar.py src/tradelens/ui/pages/
```

Expected: PASS and ruff clean.

```bash
git add src/tradelens/services/strategy.py src/tradelens/ui/app.py src/tradelens/ui/components/sidebar.py src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/pages/2_Trades.py src/tradelens/ui/pages/4_Analytics.py src/tradelens/ui/pages/5_Strategy.py src/tradelens/ui/pages/6_Insights.py tests/test_strategy.py
git commit -m "strategy: isolate profiles by user"
```

### Task 3: Replace global JSON timezone with user-scoped settings

**Files:**
- Modify: `src/tradelens/services/app_settings.py:1-47`
- Modify: `src/tradelens/ui/pages/1_NewTrade.py:225-245`
- Modify: `src/tradelens/ui/pages/9_Settings.py:100-125`
- Modify: `tests/test_app_settings.py`

**Interfaces:**
- Produces: `get_setting(user_id: int, key: str, default=None)`, `set_setting(user_id: int, key: str, value)`, `get_timezone(user_id: int) -> str`, `set_timezone(user_id: int, tz: str) -> None`.

- [ ] **Step 1: Rewrite tests for two-user isolation**

```python
def test_timezones_are_user_scoped(in_memory_db, two_users):
    a, b = two_users
    set_timezone(a.id, "America/New_York")
    set_timezone(b.id, "Europe/London")
    assert get_timezone(a.id) == "America/New_York"
    assert get_timezone(b.id) == "Europe/London"
```

- [ ] **Step 2: Run and verify failure**

Run: `.venv/bin/python -m pytest tests/test_app_settings.py -q`  
Expected: FAIL because the service is JSON/global.

- [ ] **Step 3: Replace the service with DB-backed keys**

Implement exact `(user_id, key)` lookup. `set_setting` inserts or updates one row and records an ISO UTC `updated_at`. `get_timezone` and `set_timezone` call these APIs with key `trading_timezone`.

- [ ] **Step 4: Update UI callers**

Pass `current_user_id()` from New Trade and Settings. Do not retain a global fallback file write.

- [ ] **Step 5: Verify and commit**

Run: `.venv/bin/python -m pytest tests/test_app_settings.py tests/test_pages_boot.py -q`  
Expected: PASS.

```bash
git add src/tradelens/services/app_settings.py src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/pages/9_Settings.py tests/test_app_settings.py
git commit -m "settings: store preferences per user"
```

### Task 4: Require ownership for direct trade reads, edits, and deletes

**Files:**
- Modify: `src/tradelens/services/trade_service.py:146-253`
- Modify: `src/tradelens/ui/pages/2_Trades.py`
- Modify: `tests/test_trade_service.py`
- Create: `tests/test_user_isolation.py`

**Interfaces:**
- Produces: `get_trade(trade_id: int, user_id: int)`, `update_trade(trade_id: int, user_id: int, **fields)`, `delete_trade(trade_id: int, user_id: int)`; registered-user list queries use exact equality.

- [ ] **Step 1: Write denial tests**

```python
def test_user_cannot_read_update_or_delete_another_users_trade(two_user_trades):
    user_a, user_b, trade_a = two_user_trades
    assert get_trade(trade_a.id, user_id=user_b.id) is None
    assert update_trade(trade_a.id, user_id=user_b.id, notes="changed") is None
    assert not delete_trade(trade_a.id, user_id=user_b.id)
    assert get_trade(trade_a.id, user_id=user_a.id).notes != "changed"


def test_registered_user_does_not_receive_null_owned_legacy_rows(in_memory_db, user):
    create_trade({"asset": "NQ", "trade_date": "2026-07-01", "user_id": None})
    assert get_trades(user_id=user.id) == []
```

- [ ] **Step 2: Run and verify failure**

Run: `.venv/bin/python -m pytest tests/test_user_isolation.py -q`  
Expected: FAIL because direct operations are unscoped and list queries include NULL rows.

- [ ] **Step 3: Apply exact filters**

For user-scoped `get_trades`, filter only `Trade.user_id == user_id`. For direct operations, add `Trade.user_id == user_id` to the query. Keep `_UNSCOPED` only for administrative scripts that omit the argument entirely.

- [ ] **Step 4: Update Journal callers**

Pass `current_user_id()` to get/update/delete operations. A missing row renders the existing not-found state and never reveals whether the ID exists for another user.

- [ ] **Step 5: Verify and commit**

Run:

```bash
.venv/bin/python -m pytest tests/test_user_isolation.py tests/test_trade_service.py tests/test_journal.py -q
.venv/bin/ruff check src/tradelens/services/trade_service.py src/tradelens/ui/pages/2_Trades.py
```

Expected: PASS.

```bash
git add src/tradelens/services/trade_service.py src/tradelens/ui/pages/2_Trades.py tests/test_trade_service.py tests/test_user_isolation.py
git commit -m "security: scope direct trade operations by owner"
```

### Task 5: Add a dry-run legacy ownership assignment

**Files:**
- Create: `scripts/assign_legacy_data.py`
- Create: `tests/test_assign_legacy_data.py`
- Modify: `docs/DEPLOY.md`

**Interfaces:**
- Produces: `plan_assignment(username: str) -> AssignmentPlan` and `apply_assignment(plan: AssignmentPlan) -> dict[str, int]`; default CLI is dry-run, mutation requires `--apply`.

- [ ] **Step 1: Write dry-run tests**

Seed one NULL trade and one NULL strategy. Assert dry-run reports counts without mutation; apply assigns both to the requested user's ID; unknown username exits non-zero; running apply twice changes zero rows the second time.

- [ ] **Step 2: Implement the script**

The script must:

1. Resolve an existing `User` by exact username.
2. Count NULL-owned `Trade`, `Strategy`, `WeeklyReview`, and `Correction` rows.
3. Print the target user ID and per-table counts.
4. Return without writing unless `--apply` is present.
5. In one transaction, assign NULL rows to the target and roll back on any error.
6. Never alter rows already owned by another user.

- [ ] **Step 3: Document the production procedure**

Add:

```markdown
## Legacy ownership assignment

1. Create a database backup/snapshot.
2. Dry run:
   `.venv/bin/python scripts/assign_legacy_data.py --username ayoub`
3. Review every count.
4. Apply only after approval:
   `.venv/bin/python scripts/assign_legacy_data.py --username ayoub --apply`
5. Run the dry run again; expected count for every table is 0.
```

- [ ] **Step 4: Verify and commit**

Run: `.venv/bin/python -m pytest tests/test_assign_legacy_data.py -q`  
Expected: PASS.

```bash
git add scripts/assign_legacy_data.py tests/test_assign_legacy_data.py docs/DEPLOY.md
git commit -m "migration: safely assign legacy data to an owner"
```

### Task 6: End-to-end isolation verification

**Files:**
- Modify: only the owning task when a failing assertion identifies a defect.

**Interfaces:**
- Produces: evidence that two concurrent users cannot observe or modify each other's state.

- [ ] **Step 1: Run security-focused tests**

```bash
.venv/bin/python -m pytest tests/test_user_isolation.py tests/test_strategy.py tests/test_app_settings.py tests/test_trade_service.py tests/test_auth.py tests/test_auth_signup.py -q
```

Expected: PASS.

- [ ] **Step 2: Run migration tests on SQLite**

```bash
DATABASE_URL=sqlite:////tmp/tradelens-isolation.db .venv/bin/alembic upgrade head
.venv/bin/python -m pytest tests/test_migrations.py tests/test_init_db_reconcile.py -q
```

Expected: PASS.

- [ ] **Step 3: Run the full suite**

```bash
.venv/bin/ruff check src/ scripts/
.venv/bin/black --check src/ scripts/
DEMO_MODE=true .venv/bin/python -m pytest tests/ -q
```

Expected: all clean/passing.

- [ ] **Step 4: Perform two-user manual acceptance**

Create users `isolation_a` and `isolation_b`. Give each a different timezone, strategy name, and one trade. In two private browser windows, verify Dashboard, New Trade defaults, Journal, Analytics, Insights, Strategy, Settings, edit, and delete show only the current user's values.

