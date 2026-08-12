# Proposed migration: `email_verifications`

**Date:** 2026-08-11
**Status:** PROPOSAL — not written to `alembic/versions/`, not applied anywhere.
**Blocks:** Phase 2 step 5 (email verification).

---

## 1. Is the s9 schema sufficient? No.

Inspected on `dev-auth-migration / neondb`. The auth structures s9 created are:

| Table | Columns | Purpose |
|---|---|---|
| `auth_handoffs` | `token_hash, user_id, created_at, expires_at, consumed_at` | 120-second site→Streamlit credential |
| `auth_sessions` | `token_hash, user_id, created_at, expires_at, last_seen_at, revoked_at` | durable revocable session |
| `auth_attempts` | `bucket, action, succeeded, created_at` | rate-limit counter |

There is no `email_verifications`, `verification_tokens`, `auth_tokens`, or
`tokens` table. Nothing in s9 fits.

### Why each existing table is insufficient

**`auth_attempts` — explicitly not repurposed.** It is a counter log. It has no
user foreign key, no token hash, no expiry, and no one-time-use state. Bending
it into token storage would mean adding four columns to a table whose entire
purpose is being cheap to insert into and sweep, and would make the rate limiter
and the token store share a lifecycle they do not share.

**`auth_handoffs` — wrong lifecycle, and conflating two credential types is the
thing the design deliberately avoids.** It lives 120 seconds; a verification link
must survive the user walking away from their inbox. It has no way to record
which email address a token was issued for, which is exactly what stops a token
surviving an address change. Reusing it would also mean one table where a
`redeem_handoff` bug could consume a verification token, or the reverse.

**`auth_sessions`** is a session store; not applicable.

### Why the originally-specified design no longer applies

Spec §8 said *"No table for email verification"* — verification would reuse the
`password_reset.py` pattern, where the code is signed with a key derived from
account state so that completing verification invalidates outstanding codes for
free, with nothing to store.

That was a good design, and **step 5's own requirements rule it out.** The
instruction states tokens must not contain *"user ID, email, username, expiry
timestamp, database ID"*. The derived-key pattern puts `{"i": user_id, "e":
expiry}` **inside the token payload** (`password_reset.py:132`). It is
structurally a signed claim, not an opaque handle.

Three further step-5 requirements it cannot meet:

- **`consumed_at` or equivalent one-time-use state** — invalidation is implicit
  in a hash change, so there is no record that a token was used, when, or whether
  a rejection was a replay or a forgery.
- **explicit invalidation of previous outstanding tokens** — implicit only.
- **auditability** — nothing to inspect when a user says a link did not work.

So spec §8 needs amending, and this proposal is that amendment. Flagging it
rather than quietly diverging.

---

## 2. Proposed table

```
users.id  ──1:N──>  email_verifications.user_id   (FK, ON DELETE CASCADE)
```

| Column | Type | Null | Purpose |
|---|---|---|---|
| `id` | `Integer` PK | no | |
| `token_hash` | `String(64)` | no | SHA-256 hex of the raw token. **Unique.** The raw token is never stored. |
| `user_id` | `Integer` FK → `users.id` | no | owner; `ON DELETE CASCADE` so deleting an account cannot orphan a live token |
| `email` | `String` | no | the **normalised address this token was issued for** — see §4 |
| `created_at` | `TIMESTAMPTZ` | no | |
| `expires_at` | `TIMESTAMPTZ` | no | written once, never extended |
| `consumed_at` | `TIMESTAMPTZ` | yes | set by the atomic consume; NULL means unused |
| `superseded_at` | `TIMESTAMPTZ` | yes | set when a newer token is issued for the same user |

`consumed_at` and `superseded_at` are kept **separate** deliberately. They are
different events — "the user clicked this link" versus "the user asked for a new
one" — and collapsing them into a single `invalidated_at` would make it
impossible to tell a genuine replay attempt from a click on a superseded link,
which is the difference between an attack signal and an ordinary support case.

### Indexes

| Index | Columns | Unique | Why |
|---|---|---|---|
| `ix_email_verifications_token_hash` | `token_hash` | **yes** | lookup path; uniqueness is the collision guarantee |
| `ix_email_verifications_user_id` | `user_id` | no | supersede-all-for-user, and per-user lookups |
| `ix_email_verifications_expires_at` | `expires_at` | no | the sweep |

A token is **usable** iff:

```sql
consumed_at IS NULL AND superseded_at IS NULL AND expires_at > now()
AND email = (SELECT email FROM users WHERE id = user_id)
```

---

## 3. Token lifecycle

1. **Issue** — 32 random bytes (`secrets.token_urlsafe(32)`, 256 bits), opaque,
   carrying no user id, email, username, expiry, or database id. Only
   `sha256(token)` is stored. The raw value exists just long enough to build the
   link and hand it to the mail transport.
2. **Supersede** — issuing sets `superseded_at = now()` on every prior row for
   that user where `consumed_at IS NULL AND superseded_at IS NULL`, in the same
   transaction as the insert. At most one live token per account.
3. **Consume** — a single conditional UPDATE, the same compare-and-swap the
   handoff uses:
   ```sql
   UPDATE email_verifications SET consumed_at = now()
    WHERE token_hash = :h AND consumed_at IS NULL
      AND superseded_at IS NULL AND expires_at > now()
   ```
   `rowcount = 1` is the sole winner; two concurrent requests give exactly one
   success and one rejection.
4. **Apply** — in the *same* transaction, set `users.email_verified_at = now()`
   and `email_verification_required = false`. Consume and state change commit
   together or not at all.
5. **Expire / sweep** — TTL **24 hours**, longer than the 30-minute reset code
   because a verification link is often opened on another device hours later.
   Rows older than 30 days are swept opportunistically on issue.

---

## 4. Binding to the address being verified

`email` on the row is what prevents a token outliving an address change, and it
is why this cannot be solved with `user_id` alone.

Without it: a user signs up as `old@x.com`, is issued a token, changes their
address to `new@y.com`, then clicks the original link — and an address nobody
proved control of becomes verified. With it, consume compares the row's `email`
against the user's current `email` and rejects on mismatch.

This composes with the already-implemented rule in `users.set_email()`, which
clears `email_verified_at` and re-arms `email_verification_required` on any
change. The row check is the second half: the first stops old verification state
carrying over, this stops an old *token* carrying over.

---

## 5. Migration source

Revision `u1v2w3x4y5z6`, on top of the current head `s9t0u1v2w3x4`.

```python
"""Add email_verifications.

Verification needs durable, auditable, one-time tokens. Spec §8 originally
avoided a table by reusing the password-reset pattern, where the code is signed
with a key derived from account state. That pattern puts the user id and expiry
inside the token payload, which the step-5 token requirements forbid, and it has
no consumed_at, so a replay is indistinguishable from a forgery.

Nothing in s9 fits: auth_attempts is a counter with no user FK or expiry, and
auth_handoffs lives 120 seconds and cannot record which address a token belongs
to — the field that stops a token surviving an email change.

Revision ID: u1v2w3x4y5z6
Revises: s9t0u1v2w3x4
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, Sequence[str], None] = "s9t0u1v2w3x4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The normalised address this token was issued for. Deleting an account
        # cascades; changing the address invalidates by mismatch at consume.
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_email_verifications_token_hash",
        "email_verifications",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_email_verifications_user_id", "email_verifications", ["user_id"]
    )
    op.create_index(
        "ix_email_verifications_expires_at", "email_verifications", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_verifications_expires_at", table_name="email_verifications"
    )
    op.drop_index("ix_email_verifications_user_id", table_name="email_verifications")
    op.drop_index("ix_email_verifications_token_hash", table_name="email_verifications")
    op.drop_table("email_verifications")
```

**Purely additive.** One new table, no change to `users` or any existing table,
no data migration, no backfill. Row counts elsewhere cannot move. `downgrade()`
drops only what `upgrade()` created.

---

## 6. Risk

| | |
|---|---|
| Affects existing data | No — nothing outside the new table is touched |
| Lock / downtime | `CREATE TABLE` takes no lock on existing tables; instant |
| Rollback | `alembic downgrade -1`, tested on the dev branch first |
| Row-count impact | zero |

---

## 7. What I need from you

1. **Approve the table** as specified, or tell me what to change.
2. Confirm the **24-hour TTL** (reset codes are 30 minutes; a verification link
   is usually opened later, often on a different device).
3. Confirm `consumed_at` and `superseded_at` stay separate rather than merging
   into one `invalidated_at`.

On approval I will write the revision, rehearse it on `dev-auth-migration` with
a downgrade/upgrade round trip, and only then continue with the rest of step 5.

Production is not touched by any of this. Production stays at `s9t0u1v2w3x4`
until a separate, explicitly approved cutover.
