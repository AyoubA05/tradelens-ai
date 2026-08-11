# Phase 1A — schema drift and reconciliation report

**Date:** 2026-08-11
**Reference:** `alembic-reference / alembic_reference`, built from zero to `r8s9t0u1v2w3`
**Target:** `dev-auth-migration / neondb` (copy of production)
**Engine:** PostgreSQL 17.10, both sides
**Production:** not touched. Nothing reconciled, nothing stamped.

No connection string appears in this file.

---

## 1. Inventory — production facts confirmed

| Fact | Expected | Observed | |
|---|---|---|---|
| `users` | 2 | 2 | ✅ |
| `trades` | 21 | 21 | ✅ |
| `strategies` | 2 | 2 | ✅ |
| `weekly_reviews` | 2 | 2 | ✅ |
| `ai_usage_log` | 2 | 2 | ✅ |
| `corrections`, `screenshots`, `aianalysis`, `performance_metrics`, `user_settings` | 0 | 0 | ✅ |
| `users_with_email` | 0 | 0 | ✅ |
| `users_with_active_strategy` | 1 | 1 | ✅ |
| Alembic revision | untracked | `UNTRACKED / alembic_version missing` | ✅ |
| Bootstrap login reachable | no | `False` | ✅ |

All eight facts match. Reference reports `alembic current = r8s9t0u1v2w3`.

---

## 2. Backup restore verification — NOT RUN

Two blockers, one of them a safety stop.

**`TRADELENS_RESTORE_CHECK_URL` points at `neondb`, not `restore_check`.** That
database holds 10 tables — it is the populated copy of production on the
`backup-restore-check` branch. Restoring into it is precisely the thing the
instruction forbids, so nothing was attempted.

**No PostgreSQL client tools are installed** (`pg_dump`, `pg_restore`, `psql`
are absent), and no `.dump` artifact exists. The logical backup has not been
created yet, so there is nothing to restore.

Neither is worked around. See §6.

---

## 3. Drift summary

18 differences. The comparator classifies conservatively — anything uncertain is
drift — so Category A came back empty and the adjudication below is mine, for
your approval.

The differences fall into a clear pattern that follows directly from how each
schema was built:

* **Columns added later by `_reconcile_columns`** arrive by bare
  `ALTER TABLE ADD COLUMN`, with **no index and no foreign key**. That is
  Group 1 — genuine gaps.
* **Tables created wholesale by `create_all`** get every index and foreign key
  the model declares. Several of those were never written into a migration, so
  **dev is stricter than the reference**. That is Group 2.

---

## Group 1 — dev is MISSING what the reference has

### B1. `users.ix_users_email` — unique index absent ⚠️ **most serious**

| | |
|---|---|
| Object | `CREATE UNIQUE INDEX ix_users_email ON users USING btree (email)` — a unique **index**, not a `UNIQUE` constraint |
| Dev has | nothing on `users.email` |
| Reference has | the unique index above |
| Proposed | `CREATE UNIQUE INDEX ix_users_email ON users USING btree (email);` |
| Affects data | No rows change. **Fails if duplicate non-NULL emails exist** — check first |
| Lock / downtime | `ShareLock` blocks writes for the build. 2 rows, 0 non-NULL emails → effectively instant. `CONCURRENTLY` is available but unnecessary at this size |
| Rollback | `DROP INDEX ix_users_email;` |

**This is a live integrity gap, not bookkeeping.** Production can currently
store two accounts with the same email. It is latent only because
`users_with_email = 0`. Phase 4 makes email a login identifier and the password-reset
route, both of which assume an address identifies exactly one account. This must
be fixed before Phase 4 regardless of what is decided about stamping.

### B2. `strategies` — foreign key absent

| | |
|---|---|
| Dev has | `user_id` column, no foreign key |
| Reference has | `fk_strategies_user_id_users FOREIGN KEY (user_id) REFERENCES users(id)` |
| Proposed | `ALTER TABLE strategies ADD CONSTRAINT fk_strategies_user_id_users FOREIGN KEY (user_id) REFERENCES users(id);` |
| Affects data | No rows change. **Fails if any `strategies.user_id` references a missing user** — check first |
| Lock / downtime | Brief `ShareRowExclusiveLock` on both tables while existing rows validate. 2 rows → instant |
| Rollback | `ALTER TABLE strategies DROP CONSTRAINT fk_strategies_user_id_users;` |

Same cause as B1: `user_id` was added to `strategies` by `_reconcile_columns`.
Orphaned strategy rows are currently possible.

### B3. `strategies.ix_strategies_user_id` — index absent

| | |
|---|---|
| Proposed | `CREATE INDEX ix_strategies_user_id ON strategies USING btree (user_id);` |
| Affects data | No |
| Lock / downtime | `ShareLock`, instant at 2 rows |
| Rollback | `DROP INDEX ix_strategies_user_id;` |

Performance only today, but every per-user strategy lookup uses this column.

### B4. Column defaults absent

| | Dev | Reference |
|---|---|---|
| `users.is_active` | no default | `1` |
| `trades.is_sample` | no default | `0` |

| | |
|---|---|
| Proposed | `ALTER TABLE users ALTER COLUMN is_active SET DEFAULT 1;`<br>`ALTER TABLE trades ALTER COLUMN is_sample SET DEFAULT 0;` |
| Affects data | No — a default applies to future inserts only |
| Lock / downtime | Catalogue-only, instant, no table rewrite |
| Rollback | `ALTER COLUMN … DROP DEFAULT;` |

Low impact in practice — the ORM supplies both values client-side — but a raw
`INSERT` omitting `users.is_active` fails today (`NOT NULL`, no default) and
succeeds against the reference.

---

## Group 2 — dev HAS what the reference lacks (dev is stricter)

Ten items. Every one exists because `create_all` faithfully built what
`models.py` declares, while the corresponding migration never created it.

| Object | Table |
|---|---|
| `FOREIGN KEY (user_id) → users(id)` | `trades`, `corrections`, `ai_usage_log`, `weekly_reviews` |
| `ix_trades_user_id`, `ix_trades_trade_hash` | `trades` |
| `ix_users_id`, `ix_corrections_id`, `ix_ai_usage_log_id`, `ix_performance_metrics_id` | various |

| | |
|---|---|
| Proposed | **Keep all ten. Change nothing.** |
| Affects data | n/a |
| Lock / downtime | n/a |
| Rollback | n/a |

Dropping them would remove real referential integrity and real indexes in order
to match a reference that is *less* correct than the live database. The honest
description is that the migrations are missing these, not that production has
them wrongly. Recommendation: accept as permanent, intentional divergence, and
record it — a later migration can add them to the reference lineage if exact
parity ever becomes necessary.

---

## Group 3 — attribute conflicts requiring a decision

### B5. `strategies.is_active` nullability — the reference is the wrong one

| | |
|---|---|
| Dev has | `NOT NULL` |
| Reference has | nullable |
| `models.py:91` says | `nullable=False` |

| | |
|---|---|
| Proposed | **Keep dev as `NOT NULL`. Do not reconcile.** |
| Affects data | Reconciling *to* the reference would loosen the constraint |
| Lock / downtime | `DROP NOT NULL` is catalogue-only and instant — but should not be done |
| Rollback | n/a if unchanged |

Here dev matches the model and the **reference has drifted from it**: some
migration created the column nullable while `models.py` declares otherwise.
Reconciling blindly toward the reference would degrade a correct constraint to
match an incorrect one. This is the clearest illustration of why "reconcile to
the reference" needs a human decision rather than a script.

### B6. Username uniqueness — same guarantee, different object

| | |
|---|---|
| Dev has | `CREATE UNIQUE INDEX ix_users_username ON users (username)` |
| Reference has | `uq_users_username UNIQUE (username)` constraint, **plus** a separate non-unique `ix_users_username` index |
| Uniqueness enforced? | **Yes, on both sides** |

| | |
|---|---|
| Proposed (option 1, recommended) | Leave as is; record the divergence |
| Proposed (option 2, exact parity) | `DROP INDEX ix_users_username;` → `ALTER TABLE users ADD CONSTRAINT uq_users_username UNIQUE (username);` → `CREATE INDEX ix_users_username ON users (username);` |
| Affects data | No |
| Lock / downtime | Option 2 leaves username uniqueness **unenforced between the drop and the add** — brief, but real |
| Rollback | Option 2: reverse the three statements |

This is exactly the distinction you told me not to guess at, and the guess would
have been wrong. Uniqueness is not missing; it is implemented as a different
object under a different name.

**The one forward-looking hazard:** a future migration calling
`op.drop_constraint("uq_users_username")` would fail on dev, because no such
constraint exists there. That is an argument for option 2 — the only one.

---

## 4. Recommended reconciliation set

**Apply (4 statements), after the two pre-checks:**

```sql
-- Pre-check 1: must return 0
SELECT count(*) FROM (
  SELECT email FROM users WHERE email IS NOT NULL GROUP BY email HAVING count(*) > 1
) d;

-- Pre-check 2: must return 0
SELECT count(*) FROM strategies s
LEFT JOIN users u ON u.id = s.user_id
WHERE s.user_id IS NOT NULL AND u.id IS NULL;

CREATE UNIQUE INDEX ix_users_email ON users USING btree (email);
ALTER TABLE strategies ADD CONSTRAINT fk_strategies_user_id_users
  FOREIGN KEY (user_id) REFERENCES users(id);
CREATE INDEX ix_strategies_user_id ON strategies USING btree (user_id);
ALTER TABLE users ALTER COLUMN is_active SET DEFAULT 1;
ALTER TABLE trades ALTER COLUMN is_sample SET DEFAULT 0;
```

**Accept as permanent divergence, change nothing:** Group 2's ten objects,
`strategies.is_active NOT NULL` (B5), and username uniqueness shape (B6) unless
you choose option 2.

**Combined risk:** no row is modified by any statement; all are instant at these
row counts; every one has a one-line rollback.

---

## 5. Consequence for stamping

The comparator will **still exit 1** after this reconciliation, because Group 2,
B5, and B6 remain by deliberate choice. The plan's rule was "stamp only when the
comparator exits 0". That rule needs one amendment, for your approval:

> Stamp when every Category B item is either reconciled **or** explicitly
> accepted and recorded in this report, with the residual list attached to the
> stamp decision.

The alternative — forcing exit 0 — means dropping real foreign keys and
loosening a correct `NOT NULL`, which is worse than the problem. I would rather
change the rule in the open than quietly reinterpret it.

If you prefer the rule unchanged, the honest route is a small
`s8…`-prefixed "reconcile create_all divergence" migration that brings the
*reference lineage* up to what production already has, so both converge legitimately.

---

## 6. Blocked, needing your action

1. **`TRADELENS_RESTORE_CHECK_URL` points at `neondb`.** It needs to point at an
   empty `restore_check` database inside the `backup-restore-check` branch.
2. **No `pg_dump` / `pg_restore` / `psql` installed**, and no dump artifact
   exists. Either install the client tools (`brew install libpq`) and create the
   dump, or run the dump/restore yourself and share the row counts.

Restore verification is the last outstanding Phase 1A item. Everything else is
complete.
