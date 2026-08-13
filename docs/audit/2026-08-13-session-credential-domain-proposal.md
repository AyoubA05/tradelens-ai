# Credential-domain confusion between website and Streamlit sessions

**Date:** 2026-08-13
**Status:** STOP — Step 10 blocked pending a decision. Nothing written to
`alembic/versions/`, nothing applied, no Step 10 code written.

---

## 1. The problem

Step 10 requires a second, independent session credential for Streamlit. The
existing `auth_sessions` design **cannot safely carry it**, and the reason is
not the table shape — it is that both credentials would be validated by the
same lookup with nothing distinguishing them.

Both sides hash identically and query identically:

| | hashing | lookup |
|---|---|---|
| Website (`web/lib/auth/session.ts:71`) | `sha256(token)` hex | `WHERE token_hash = $1` |
| Streamlit (`services/auth_sessions.py:60`) | `sha256(token)` hex | `WHERE token_hash = :h` |

`auth_sessions` columns: `id, token_hash, user_id, created_at, expires_at,
last_seen_at, revoked_at`. **No surface, audience, or domain marker.**

So any `auth_sessions` token validates on either surface.

### Demonstrated, not assumed

Run against `dev-auth-migration` on 2026-08-13 with a disposable account,
cleaned up immediately (dev back to 2 users):

```
created a Streamlit-side session (Python auth_sessions.open_session)
WEBSITE validator accepts the Streamlit-side token: true (resolved as user 28)
```

### Why this matters more than it first looks

The two credentials have deliberately different exposure:

| | transport | exposure |
|---|---|---|
| Website session | `HttpOnly; Secure; SameSite=Lax` cookie | not readable by script, never in a URL |
| Streamlit session | **query parameter in the URL** | browser history, copied links, proxy logs, referrers — the documented beta limitation |

Interchangeability turns that asymmetry into a **privilege bridge**: anyone who
obtains the Streamlit URL — which we have already documented as a bearer that
leaks through ordinary link-sharing — can paste that value into a `tl_session`
cookie on `tradelensai.io` and hold a full website session. From there they can
issue fresh handoffs, complete onboarding, and act as the user on the surface
whose whole point was that its credential *cannot* leak this way.

We accepted a weak credential on the Streamlit side on the understanding that it
was scoped to Streamlit. Without domain separation it is not scoped to anything.

---

## 2. Two ways to fix it

### Option A — domain-separated hashing (no migration)

Each surface hashes with its own prefix before storing or looking up:

```
website:    sha256("tl.website.v1|"  + token)
streamlit:  sha256("tl.streamlit.v1|" + token)
```

* **No schema change at all.** The smallest possible fix.
* **Fails closed by construction.** A Streamlit token does not hash to anything
  the website lookup can find. There is no filter to forget: the hash function
  each module uses *is* the domain.
* Downside: invisible in the row. "How many Streamlit sessions are live?"
  becomes unanswerable, and an operator reading `auth_sessions` cannot tell the
  two apart.

### Option B — a `surface` column (one migration)

`auth_sessions.surface TEXT NOT NULL DEFAULT 'website'`, values
`'website' | 'streamlit'`, with `AND surface = $n` on every lookup.

* Explicit, greppable, auditable, and queryable.
* Downside: **it is a filter, and filters get forgotten.** A future query that
  omits `AND surface = ...` silently reintroduces exactly this bug, and the
  omission looks like ordinary code.

### Recommendation — both, in one migration

They fail differently, and the combination costs one extra column on a migration
we would be running anyway:

* the **hash prefix** makes confusion impossible even if someone writes a
  careless query;
* the **column** makes the sessions auditable and the intent legible.

If you want the genuinely minimal change, **Option A alone is correct and needs
no migration**. I recommend the pair because the audit question ("is anything
still validating cross-surface?") cannot be answered without the column.

---

## 3. Proposed migration, if you approve the pair

Revision `w3x4y5z6a7b8`, on `v2w3x4y5z6a7`. Additive.

```python
def upgrade() -> None:
    op.add_column(
        "auth_sessions",
        sa.Column("surface", sa.String(16), nullable=False,
                  server_default="website"),
    )
    # Every row that exists now was created by the website login, so the
    # default is already correct for all of them and no backfill is needed.
    op.create_index(
        "ix_auth_sessions_user_surface", "auth_sessions", ["user_id", "surface"]
    )


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_user_surface", table_name="auth_sessions")
    op.drop_column("auth_sessions", "surface")
```

Index justified by a real query: revoke-all-for-user and "list this user's
Streamlit sessions" both filter on `(user_id, surface)`.

**Row-count impact: zero.** Production currently has 0 `auth_sessions` rows, so
even the default touches nothing.

### Existing behaviour that must not change

* Password reset revokes **all** sessions for the user regardless of surface —
  that is correct and stays. A reset must kill the Streamlit session too.
* `sign_out` on the website revokes the website session. Whether it should also
  end the Streamlit session is a product question, called out separately in
  Step 10's logout requirements; this migration does not decide it.

---

## 4. Work this unblocks

Once decided, Step 10 proceeds as specified: atomic
`exchange_handoff_for_streamlit_session`, the `?s=` parameter already named in
spec §7.4, `ht` cleanup, durable validation, Strategy Profile routing, legacy
coexistence, and the full test matrix.

Nothing from Step 10 has been written. The only artifacts from this increment
are this document and the throwaway probe, which has been deleted.

---

## 5. Decisions needed

1. **Option A, Option B, or both?** I recommend both.
2. If A or both: confirm the prefixes `tl.website.v1|` and `tl.streamlit.v1|`
   (versioned so a future rotation is possible without ambiguity).
3. If B or both: approve revision `w3x4y5z6a7b8` for **dev rehearsal only** —
   production stays at `v2w3x4y5z6a7` until a separate approval, as with every
   prior migration.

Production untouched. Dev untouched. Nothing deployed.
