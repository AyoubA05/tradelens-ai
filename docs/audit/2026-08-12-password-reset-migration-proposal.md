# Proposed migration: `password_resets`

**Date:** 2026-08-12
**Status:** PROPOSAL — nothing written to `alembic/versions/`, nothing applied.
**Blocks:** Phase 2 step 7 (forgot / reset password).

---

## 1. Schema sufficiency finding: insufficient

The current design is **signed claim-bearing reset codes**, not durable opaque
tokens. `services/password_reset.py`:

- builds the payload `{"i": user_id, "e": expiry}` and base64-encodes it into
  the token (line 132) — the user id and expiry are *inside* the token;
- signs it with a key derived from the account's **current password hash**
  (line 105), so completing a reset changes the hash and every outstanding code
  stops verifying;
- stores nothing. Its own docstring says so: *"Single-use without a token
  table."*

That was a genuinely clever design, and it is the same one already rejected for
email verification in `u1v2w3x4y5z6`. It fails the step-7 requirements on four
counts:

| Requirement | Status |
|---|---|
| `token_hash` at rest | ✗ nothing stored |
| `consumed_at` | ✗ invalidation is implicit in a hash change |
| `superseded_at` or equivalent | ✗ no way to invalidate prior tokens explicitly |
| no claims in the token | ✗ carries user id and expiry |

Inspected on dev after `u1v2w3x4y5z6` (15 tables). No `password_resets`,
`reset_tokens`, `password_reset_tokens`, or `auth_reset`.

### The four tables I am forbidden to reuse — and why each is genuinely wrong

- **`email_verifications`** — proves *"this address reaches this person"*.
  A reset token proves *"this person may replace the password"*. Sharing one
  table means one bug in one consume path can burn or redeem the other kind of
  credential, and the two have different eligibility rules.
- **`auth_handoffs`** — 120-second lifetime, no email binding.
- **`auth_sessions`** — a session store; a reset token is not a session.
- **`auth_attempts`** — a counter with no user FK, no token hash, no expiry.

---

## 2. Proposed table

```
users.id  ──1:N──>  password_resets.user_id   (FK, ON DELETE CASCADE)
```

| Column | Type | Null | Purpose |
|---|---|---|---|
| `id` | `Integer` PK | no | |
| `token_hash` | `String(64)` | no | SHA-256 hex, **unique**. Raw token never stored. |
| `user_id` | `Integer` FK → `users.id` `ON DELETE CASCADE` | no | |
| `email` | `String` | no | normalised address the reset was sent to — see §4 |
| `password_hash_fingerprint` | `String(64)` | no | SHA-256 of the password hash at issue — see §4, **optional, your call** |
| `created_at` | `TIMESTAMPTZ` | no | |
| `expires_at` | `TIMESTAMPTZ` | no | written once, never extended |
| `consumed_at` | `TIMESTAMPTZ` | yes | the reset was completed |
| `superseded_at` | `TIMESTAMPTZ` | yes | a newer request replaced it |

Plus `CHECK (expires_at > created_at)`.

Same shape as `email_verifications` deliberately: two token tables with the same
columns and the same consume semantics are far easier to reason about than two
that each invented their own.

### Indexes — two, each justified by a query

| Index | Query that needs it |
|---|---|
| `ix_password_resets_token_hash` **UNIQUE** | the whole consume path is `WHERE token_hash = $1`; uniqueness is also the collision guarantee |
| `ix_password_resets_user_id` | supersession runs `UPDATE … WHERE user_id = $1` on every request; session revocation looks up by account |

**No `expires_at` index.** The sweep deletes on `created_at`, so nothing would
use it — the same call made for `email_verifications`, where I initially
proposed one and dropped it.

---

## 3. TTL

**30 minutes**, retained from the current canonical value (`TOKEN_TTL_S = 30 * 60`,
`password_reset.py:54`). Deliberately *not* the verification token's 24 hours: a
verification link is opened at leisure, whereas a reset link is an active key to
an account and should be short-lived. Configurable as a server-side constant;
30 minutes is canonical.

---

## 4. Two binding columns

**`email` — same reasoning as verification.** Consume requires
`r.email = u.email`, so a reset link mailed to an old address dies the moment
the account moves to a new one. Supersession is a *write* a bug can skip; a
condition in the `WHERE` clause cannot be.

**`password_hash_fingerprint` — recovers something the old design got for free,
and I'd like your decision on it.**

The signed-claim design derived its key from the current password hash, so *any*
password change invalidated every outstanding reset code automatically. A token
table loses that unless something replaces it.

The gap: a user requests a reset, then remembers their password and changes it
through a future settings page. The emailed link is still live, and whoever
holds it can change the password again. Fixing that by superseding inside every
password-change path means every such path must remember to; storing
`sha256(password_hash)` at issue and requiring it to still match at consume
makes it a condition nobody can forget.

It stores a hash *of* a hash — not the password hash itself — so the row leaks
nothing usable.

**Recommend including it.** It is one column and it closes a real hole, but it
is beyond your stated minimum, so say if you'd rather leave it out.

---

## 5. Migration source

Revision `v2w3x4y5z6a7`, on top of the current head `u1v2w3x4y5z6`.

```python
"""Add password_resets: durable, opaque, single-use reset tokens.

Replaces the signed claim-bearing codes in services/password_reset.py, which
carry the user id and expiry inside the token and store nothing — so a replay
cannot be distinguished from a forgery, and prior tokens cannot be explicitly
invalidated.

Deliberately the same shape as email_verifications: two token tables with
identical columns and identical consume semantics are easier to reason about
than two that each invented their own.

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v2w3x4y5z6a7"
down_revision: Union[str, Sequence[str], None] = "u1v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_resets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Normalised address the reset was sent to. Compared at consume, so a
        # link mailed to a previous address cannot reset a changed one.
        sa.Column("email", sa.String(), nullable=False),
        # SHA-256 of the password hash at issue. Recovers the property the
        # signed-claim design had for free: any password change, by any route,
        # invalidates outstanding reset tokens as a condition rather than
        # relying on every change path remembering to supersede.
        sa.Column("password_hash_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_password_resets_expiry_after_creation",
        ),
    )
    op.create_index(
        "ix_password_resets_token_hash", "password_resets", ["token_hash"], unique=True
    )
    op.create_index("ix_password_resets_user_id", "password_resets", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_password_resets_user_id", table_name="password_resets")
    op.drop_index("ix_password_resets_token_hash", table_name="password_resets")
    op.drop_table("password_resets")
```

Purely additive: one new table. No existing table altered, no backfill, no row
count anywhere can move. `downgrade()` drops only what `upgrade()` created.

---

## 6. Risk

| | |
|---|---|
| Affects existing data | No |
| Lock / downtime | `CREATE TABLE` takes no lock on existing tables; instant |
| Rollback | `alembic downgrade -1`, rehearsed on dev first |
| Row-count impact | zero |

---

## 7. Decisions needed

1. **Approve the table** as specified, or say what to change.
2. **`password_hash_fingerprint` — in or out?** Recommended in (§4).
3. Confirm **30-minute TTL** retained.

On approval: write the revision, rehearse on `dev-auth-migration` with a
downgrade/upgrade round trip and a SQLite chain check, then build the rest of
step 7. Production stays at `u1v2w3x4y5z6` until a separate explicit approval.

---

## 8. Recorded as deferred, not actioned in this step

**`ON DELETE NO ACTION` on seven foreign keys.** `auth_sessions`,
`auth_handoffs`, `trades`, `strategies`, `corrections`, `weekly_reviews`, and
`ai_usage_log` all block deleting a user; only `email_verifications` and
`user_settings` cascade. Account deletion is therefore impossible for any user
with activity, and `auth.py`'s `sign_out` docstring already assumes an account
deletion path that would fail. **Not changed here.** Password-reset session
revocation is an `UPDATE`, not a `DELETE`, so it is unaffected.

**Website session / handoff invariant, recorded now as instructed.** The website
`HttpOnly` cookie credential (`auth_sessions`, via `lib/auth/login.ts`) **must
never be exposed to, reused as, or transmitted to Streamlit.** The future
handoff stays an independent one-time credential: 120-second TTL, SHA-256 at
rest, single atomic consume. After consuming it, Streamlit creates its **own**
independent opaque session credential. The cookie value must not appear in any
redirect URL, query parameter, or response body bound for the app origin. Not
implemented in this step.
