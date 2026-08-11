# `t0u1v2w3x4y5` — canonical state for all 18 differences

**Date:** 2026-08-11
**Status:** proposal. Nothing written, reconciled, or stamped. Production untouched.
**Evidence:** `pg_index` / `pg_constraint` / `information_schema` on both databases,
plus `models.py` and the migration sources that created each object.

---

## 0. Two corrections to the previous report

**0a. "Dev is stricter, therefore keep it" was too blunt for indexes.** Applied
to foreign keys and `NOT NULL` it holds — those are integrity guarantees.
Applied to indexes it does not: an index is a performance object, and an
unnecessary one costs write throughput and storage while guaranteeing nothing.
Judged individually, **four of the extra indexes are redundant and should be
dropped, not adopted.**

**0b. The column-default direction was stated without checking `models.py`.**
The server defaults come from migrations `j0k1l2m3n4o5` (`server_default="1"`)
and `i9j0k1l2m3n4` (`server_default="0"`). `models.py` declares only *client-side*
`default=`, so `create_all` produces no server default. Dev matches the model;
the reference has something the model never asked for. The recommendation below
is still "adopt the defaults", but for a different and better reason, and it
carries a `models.py` change that the previous report omitted.

**The systemic point behind both:** every item resolved here must also be
reflected in `models.py`, or a locally `create_all`-built database drifts
straight back. Reconciling the databases without reconciling the model fixes the
symptom for one cycle.

---

## 1. Index redundancy analysis

PostgreSQL builds a unique btree for every `PRIMARY KEY`. A second, non-unique
btree on the same `id` column answers no query the primary key's index cannot,
and is written on every insert.

**All ten pre-existing tables declare `index=True` on their primary key** in
`models.py` (lines 23, 75, 104, 116, 200, 214, 242, 266, 282, 305). That single
habit is the origin of every `ix_<table>_id` in both databases. The three new
auth tables do not repeat it.

| Index | Column | Redundant with | Verdict |
|---|---|---|---|
| `ix_users_id` | `users.id` | `users_pkey` | **drop** — drift, dev-only |
| `ix_corrections_id` | `corrections.id` | `corrections_pkey` | **drop** — drift, dev-only |
| `ix_ai_usage_log_id` | `ai_usage_log.id` | `ai_usage_log_pkey` | **drop** — drift, dev-only |
| `ix_performance_metrics_id` | `performance_metrics.id` | `performance_metrics_pkey` | **drop** — drift, dev-only |
| `ix_trades_user_id` | `trades.user_id` | nothing | **keep** — FK column, every per-user query |
| `ix_trades_trade_hash` | `trades.trade_hash` | nothing | **keep** — duplicate detection looks up by hash |
| `ix_strategies_user_id` | `strategies.user_id` | nothing | **keep** — FK column |
| `ix_users_email` | `users.email` | nothing | **keep, UNIQUE** — the integrity gap |
| `ix_users_username` | `users.username` | see §3 | **keep, UNIQUE** |
| `uq_users_username` | `users.username` | `ix_users_username` | **drop** — see §3 |

`idx_scan` is `0` for every index on both branches. That is **not** evidence of
disuse — both are freshly cut Neon branches and statistics reset with them. The
verdicts above rest on structural redundancy and on the query patterns in the
code, not on these counters.

**Out of scope but worth recording:** six further redundant `ix_<table>_id`
indexes exist on **both** sides — `aianalysis`, `screenshots`, `strategies`,
`trades`, `user_settings`, `weekly_reviews`. They are not drift, so `t0` leaves
them alone. Dropping them and removing `index=True` from all ten primary keys is
a worthwhile, separate cleanup. Recommendation: defer to its own revision rather
than widen `t0`'s blast radius. **Your call.**

---

## 2. Foreign keys

Each evaluated against `models.py` and application semantics rather than adopted
wholesale.

| FK | In model? | Semantics | Verdict |
|---|---|---|---|
| `trades.user_id → users.id` | yes | a trade belongs to one trader | keep |
| `corrections.user_id → users.id` | yes | correction memory is per-trader; mixing them across users was a real prior bug | keep |
| `weekly_reviews.user_id → users.id` | yes | reviews are per-trader | keep |
| `ai_usage_log.user_id → users.id` | yes | cost telemetry attributed per trader | keep |
| `strategies.user_id → users.id` | yes | one active profile per trader | keep — **dev must gain it** |

All five are intentional and declared. Every one is retained in canonical state.
Only `strategies` requires an orphan pre-check, because it is the one being added
to a populated table; the other four already exist in dev and were validated when
created.

---

## 3. Username uniqueness — canonical is a single UNIQUE index

Not chosen because production has it. Chosen on three findings:

1. **The reference shape is internally redundant.** It carries *two* btree
   indexes on `users(username)`: `uq_users_username` (unique, backing the
   constraint) and `ix_users_username` (non-unique). Any query the second serves,
   the first already serves. One column, two indexes, one guarantee.
2. **It matches current model generation.** `models.py:24` declares
   `unique=True, index=True`, which SQLAlchemy renders as exactly one unique
   index named `ix_users_username`. The single-index shape is what a fresh
   `create_all` produces today.
3. **Nothing depends on the constraint name.** No `naming_convention` is
   configured on the metadata, so `uq_users_username` is a hand-written name from
   `j0k1l2m3n4o5`, not a convention-derived one. No `ON CONFLICT ON CONSTRAINT`
   references it, and no foreign key points at `users.username` — PostgreSQL
   accepts a unique *index* as an FK target anyway, so nothing is foreclosed.

The one thing given up: `ON CONFLICT ON CONSTRAINT uq_users_username`.
`ON CONFLICT (username)` infers from a unique index and is what the codebase
would use. Accepted.

This also makes email and username **consistent** — both unique indexes.

---

## 4. Canonical-state table — all 18 items

Legend for *impact*: **I** integrity · **P** performance · **M** metadata only.

### Items where DEV changes (adoption acts on the untracked lineage)

| # | Object | Dev now | r8 reference | Canonical `t0` | Why correct | Impact | Redundant? | Adoption action (untracked) | `t0` Alembic action (tracked) | Rollback | Pre-check |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 14 | `users.email` uniqueness | none | `UNIQUE INDEX ix_users_email` | `UNIQUE INDEX ix_users_email` | Phase 4 makes email a login identifier and the reset route; both assume one account per address. Gap is live today | **I** | no | `CREATE UNIQUE INDEX ix_users_email ON users USING btree (email);` | already present at r8 — `t0` no-op via existence guard | `DROP INDEX ix_users_email;` | **duplicate non-NULL normalised emails must be 0** |
| 7 | `strategies.user_id` FK | absent | `fk_strategies_user_id_users` | present | declared in the model; orphan strategies possible today | **I** | no | `ALTER TABLE strategies ADD CONSTRAINT fk_strategies_user_id_users FOREIGN KEY (user_id) REFERENCES users(id);` | no-op via guard | `ALTER TABLE strategies DROP CONSTRAINT fk_strategies_user_id_users;` | **orphan `strategies.user_id` must be 0** |
| 8 | `ix_strategies_user_id` | absent | present | present | FK column; every per-user profile lookup | **P** | no | `CREATE INDEX ix_strategies_user_id ON strategies USING btree (user_id);` | no-op via guard | `DROP INDEX ix_strategies_user_id;` | none |
| 13 | `users.is_active` server default | none | `1` | `1` | column is `NOT NULL` with no default in dev, so a raw `INSERT` omitting it fails. Costless safety | **M** | no | `ALTER TABLE users ALTER COLUMN is_active SET DEFAULT 1;` | no-op via guard | `ALTER COLUMN is_active DROP DEFAULT;` | none |
| 9 | `trades.is_sample` server default | none | `0` | `0` | same reasoning; keeps sample/real partition well-defined for non-ORM writes | **M** | no | `ALTER TABLE trades ALTER COLUMN is_sample SET DEFAULT 0;` | no-op via guard | `ALTER COLUMN is_sample DROP DEFAULT;` | none |
| 16 | `ix_users_id` | present | absent | **absent** | redundant with `users_pkey`; pure write cost | **P** | **yes** | `DROP INDEX ix_users_id;` | no-op (never existed at r8) | `CREATE INDEX ix_users_id ON users USING btree (id);` | none |
| 4 | `ix_corrections_id` | present | absent | **absent** | redundant with `corrections_pkey` | **P** | **yes** | `DROP INDEX ix_corrections_id;` | no-op | recreate | none |
| 2 | `ix_ai_usage_log_id` | present | absent | **absent** | redundant with `ai_usage_log_pkey` | **P** | **yes** | `DROP INDEX ix_ai_usage_log_id;` | no-op | recreate | none |
| 5 | `ix_performance_metrics_id` | present | absent | **absent** | redundant with `performance_metrics_pkey` | **P** | **yes** | `DROP INDEX ix_performance_metrics_id;` | no-op | recreate | none |

### Items where the REFERENCE changes (`t0` acts on the tracked lineage)

| # | Object | Dev now | r8 reference | Canonical `t0` | Why correct | Impact | Redundant? | Adoption action (untracked) | `t0` Alembic action (tracked) | Rollback | Pre-check |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 10 | `trades.user_id` FK | present | absent | present | declared in the model; a trade belongs to one trader | **I** | no | no-op via guard | `op.create_foreign_key("trades_user_id_fkey", "trades", "users", ["user_id"], ["id"])` | drop constraint | orphan check (empty at r8) |
| 3 | `corrections.user_id` FK | present | absent | present | per-trader correction memory | **I** | no | no-op | `op.create_foreign_key("corrections_user_id_fkey", …)` | drop constraint | orphan check |
| 18 | `weekly_reviews.user_id` FK | present | absent | present | per-trader reviews | **I** | no | no-op | `op.create_foreign_key("weekly_reviews_user_id_fkey", …)` | drop constraint | orphan check |
| 1 | `ai_usage_log.user_id` FK | present | absent | present | per-trader cost attribution | **I** | no | no-op | `op.create_foreign_key("ai_usage_log_user_id_fkey", …)` | drop constraint | orphan check |
| 12 | `ix_trades_user_id` | present | absent | present | FK column; per-user trade listing is the app's hottest query | **P** | no | no-op | `op.create_index("ix_trades_user_id", "trades", ["user_id"])` | drop index | none |
| 11 | `ix_trades_trade_hash` | present | absent | present | duplicate detection looks up by hash on every import | **P** | no | no-op | `op.create_index("ix_trades_trade_hash", "trades", ["trade_hash"])` | drop index | none |
| 6 | `strategies.is_active` nullability | `NOT NULL` | nullable | **`NOT NULL`** | `models.py:91` declares `nullable=False`; `get_active_strategy` filters on it and a NULL would silently vanish from both branches. The reference is the drifted side | **I** | no | no-op | `op.alter_column("strategies", "is_active", nullable=False)` | `nullable=True` | **`strategies.is_active IS NULL` must be 0** |
| 15 | `uq_users_username` constraint | absent | present | **absent** | redundant second index on one column — §3 | **I**/**P** | **yes** | no-op (never existed) | `op.drop_constraint("uq_users_username", "users", type_="unique")` | recreate constraint | none |
| 17 | `ix_users_username` uniqueness | UNIQUE | non-unique | **UNIQUE** | carries the invariant that `uq_users_username` gave up — §3 | **I** | no | no-op | drop then `op.create_index(..., unique=True)` — **after** #15, so uniqueness is never unenforced | recreate non-unique | none |

**Ordering constraint:** on the tracked lineage #15 must precede #17, and #17
must create the unique index before the transaction commits. Alembic wraps the
revision in a transaction on PostgreSQL, so username uniqueness is never
observably unenforced.

---

## 5. Accompanying `models.py` changes

Without these, a locally `create_all`-built database diverges again immediately.

| Change | Reason |
|---|---|
| `users.is_active`: add `server_default=text("1")` | item 13 |
| `trades.is_sample`: add `server_default=text("0")` | item 9 |
| Remove `index=True` from the PK on `users`, `corrections`, `ai_usage_log`, `performance_metrics` | items 16, 4, 2, 5 |
| *(deferred)* remove `index=True` from the remaining six PKs | §1 out-of-scope cleanup |

`username` and `email` need no change — `unique=True, index=True` already
produces the canonical single unique index.

---

## 6. Shared-DDL requirement

The adoption operations and the `t0` revision must not be two independently
maintained sets of DDL. One module, `src/tradelens/db/schema_adoption.py`,
exposes the operations against a live connection with existence guards, and is
called by both:

* `alembic/versions/t0u1v2w3x4y5_*.py` → `upgrade()` calls it via `op.get_bind()`
* `scripts/adopt_schema.py` → calls it directly, for the untracked lineage

Guarded on existence throughout, so it is idempotent and correct whichever
lineage it meets. A test asserts running it twice is a no-op and that both
entry points reach the same function.

---

## 7. Workflow

### Tracked lineage — build the canonical reference

```
alembic-reference / alembic_reference   (currently r8s9t0u1v2w3)
  alembic upgrade t0u1v2w3x4y5
  alembic current  ->  t0u1v2w3x4y5
```

This database now *defines* canonical post-adoption state.

### Untracked lineage — reconcile, prove, then stamp

```
dev-auth-migration / neondb   (UNTRACKED — deliberately left so)
  1. pre-checks: duplicate emails = 0
                 orphan strategies.user_id = 0
                 strategies.is_active IS NULL = 0
  2. python -m scripts.adopt_schema          # same DDL module as t0, no Alembic
  3. comparator:  REFERENCE = alembic-reference @ t0
                  TARGET    = dev-auth-migration
     MUST exit 0        <-- the gate
  4. alembic stamp t0u1v2w3x4y5              # honest: equivalence was proven
  5. alembic current -> t0u1v2w3x4y5
  6. alembic upgrade s9t0u1v2w3x4
  7. verify row counts unchanged; verify backfill
  8. alembic downgrade -1 ; verify ; alembic upgrade head ; verify
```

**No stamp at `r8` ever occurs on the untracked lineage.** The database is
stamped once, directly at `t0`, and only after a byte-level comparison against a
database built by migrations to exactly that revision. The stamp asserts
something already demonstrated.

`s9t0u1v2w3x4.down_revision` is re-pointed from `r8s9t0u1v2w3` to
`t0u1v2w3x4y5`. It has never been applied anywhere, so this costs nothing.

### Production — identical pattern, after the hard gate

```
production (UNTRACKED)
  HARD GATE: real pg_dump --format=custom  +  pg_restore into an empty database
             verified. The SQLAlchemy row-copy does NOT satisfy this.
  -> approved adoption reconciliation (same scripts/adopt_schema.py)
  -> comparator against alembic-reference @ t0  ->  exit 0
  -> alembic stamp t0u1v2w3x4y5
  -> alembic upgrade s9t0u1v2w3x4
```

---

## 8. Open decisions

1. **Drop the four redundant `ix_*_id` indexes?** Recommended yes (items 2, 4, 5, 16).
2. **Also drop the six redundant `ix_*_id` present on both sides?** Recommended
   as a *separate* later revision, not in `t0`.
3. **Server defaults on `users.is_active` / `trades.is_sample`** — adopt, plus
   the `models.py` change. Confirm.
4. **Username canonical shape** — single `UNIQUE INDEX ix_users_username`,
   dropping `uq_users_username`. Confirm.
5. **Production remains blocked** on real `pg_dump` / `pg_restore` verification.
