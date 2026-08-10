# Site-hosted authentication and first-run onboarding

**Date:** 2026-08-10
**Revision:** 2 — updated with confirmed production secret state
**Status:** Approved design. Implementation plan at
`docs/superpowers/plans/2026-08-10-site-hosted-auth.md`.

---

## 1. Goal

Move sign-in, sign-up, and password reset out of the Streamlit app and onto the
marketing site at `tradelensai.io`, so the login experience is fast, fully
designed, and continuous with the rest of the product. After authenticating, the
user is handed off to Streamlit already signed in.

New users additionally complete a profile at signup, verify their email, and are
routed through a first-run Strategy Profile step before reaching the dashboard.

### What this does not do

Moving login off Streamlit does not make the app faster. After the handoff the
user still lands in the same Streamlit container and still waits through the same
cold start. The login *screen* becomes fast and fully customisable; the
application behind it is unchanged. This is worth stating plainly because "the
Streamlit login feels slow and buggy" was the motivating complaint, and only part
of it is addressed here.

---

## 2. Confirmed production state

Verified by the owner in Streamlit Cloud secrets on 2026-08-10. No secret values
were shared, and none are recorded here.

| Secret | Present | Meaning for this work |
|---|---|---|
| `DATABASE_URL` | **yes — Neon/Postgres** | Production is already persistent Postgres. This is **not** a SQLite→Neon migration. |
| `TRADELENS_INVITE_CODE` | yes | Beta signup gating already configured. |
| `TRADELENS_USERNAME` | yes | Bootstrap credential — see §3. |
| `TRADELENS_PASSWORD` | yes | Bootstrap credential — see §3. |
| Anthropic API key | yes | Untouched by this work. Stays server-side. |
| `TRADELENS_SESSION_SECRET` | **no** | **Blocking.** Must be created before any handoff works. |
| `TRADELENS_SMTP_HOST/PORT/USER/PASSWORD/FROM` | **no** | **Blocking** for verification and reset. Email has never worked in production. |

Two consequences follow immediately.

**Password reset has never worked in production.** `password_reset.email_configured()`
requires `TRADELENS_SMTP_HOST` and `TRADELENS_SMTP_FROM`; neither exists. The
"Forgot your password?" control on the current login screen cannot have delivered
a single email. Email is a prerequisite for this project, not a nice-to-have.

**Every existing session token is already invalid on restart.** With
`TRADELENS_SESSION_SECRET` unset, `_session_secret()` generates a random
per-process key (`auth.py:100`), so the `?auth=` reload-persistence feature stops
working on every container restart today.

---

## 3. Existing code state

Established by inspection on 2026-08-10.

| Piece | Location | State |
|---|---|---|
| `User` model | `src/tradelens/db/models.py:7` | `id, username, password_hash, email (unique, nullable), created_at, is_active` |
| Password hashing | `services/users.py` | bcrypt; `gensalt()` default cost verified as **12** |
| Login orchestration | `ui/components/auth.py:254` | DB users take precedence; bootstrap pair reachable only while `users` is empty |
| Session persistence | `auth.py:87-167` | Self-contained HMAC-SHA256 token in `?auth=`, 24h TTL |
| Signup gate | `auth.py:244` | Requires `TRADELENS_INVITE_CODE`; disabled when unset |
| Password reset | `services/password_reset.py` | Token signed with a key derived from the account's *current* password hash — single-use with no token table |
| Strategy Profile | `services/strategy.py` | `get_active_strategy`, `upsert_strategy_profile`, 12 fields, one active row per user |
| Alembic head | `r8s9t0u1v2w3_add_user_email` | down_revision `q7r8s9t0u1v2` |
| Marketing site | `site/` | Vanilla; no `package.json` in the repo |
| Site build | `scripts/build_site.py` | stdlib Python; substitutes `__SITE_ORIGIN__` / `__APP_ORIGIN__` |
| Deployment | `vercel.json` | Vercel `tradelens-ai-site`; `APP_ORIGIN=https://tradelenai.streamlit.app` |

### The bootstrap credentials, precisely

`TRADELENS_USERNAME` / `TRADELENS_PASSWORD` are **not a user account**. Traced
through every call site:

- Read only by `expected_credentials()` (`auth.py:196`).
- Checked only by `verify_credentials()`, which is called from exactly one place:
  `authenticate_login()` at `auth.py:298`.
- That line sits in the **`else` branch of `if has_db_users:`**. It is reached
  only when the `users` table was queried successfully and is **empty**.
- A successful bootstrap login returns `user_id = None` (`auth.py:299`).

So this is an emergency/first-run credential for an empty database. Its sessions
own no `Strategy` and no `Trade` rows — `strategy._require_concrete_user_id`
raises on a null id — and `9_Settings.py:207` already tells such a user their
password cannot be changed in-app.

**Therefore: if the production `users` table has one or more rows, this path is
already unreachable in production.** Phase 1 confirms that with a row count.
Either way the credentials are left in place and untouched until Phase 9, and
they are never used as the basis for public user authentication.

### Pre-existing defects

Not caused by this work; two are load-bearing for it.

**D1 — `sign_out()` does not invalidate the session token.** `auth.py:389`
clears `session_state` and pops the URL parameter, but the HMAC token stays
cryptographically valid until expiry. Anyone holding a copy — browser history, a
shared link — can sign back in after "logging out". Self-contained tokens cannot
be revoked; fixed by §7.

**D2 — `password_reset.py` cannot read secrets on Streamlit Cloud.**
`password_reset._read_env` (line 78) uses `os.getenv` only, while
`auth._read_secret` (line 169) falls back to `st.secrets`. Cloud exposes secrets
through `st.secrets`, not the environment. So the two modules would derive
**different** base secrets from the same nominal setting. Fixed by §12.

**D3 — the stored note for the app URL was stale.** It recorded
`tradelens-app.streamlit.app`; the live value is `tradelenai.streamlit.app`. No
hostname is hardcoded anywhere in this design; everything reads `APP_ORIGIN`.

---

## 4. Deployment shape

**One** Vercel project, one domain. A Next.js + TypeScript + Tailwind app with
shadcn structure in `web/`, project Root Directory set to `web/`.

```
tradelensai.io
  /                    → public/index.html      (existing site, byte-identical)
  /login               → 21.dev sign-in card
  /signup              → profile + password, strength meter
  /verify-email        → code entry
  /forgot-password     → request a reset code
  /reset-password      → code + new password, strength meter
  /api/auth/{login,signup,verify,resend,forgot,reset}
        ↓ on success
  302 → {APP_ORIGIN}/?ht=<one-time handoff token>
```

The marketing site is **preserved, not redesigned**. A Next `prebuild` script
ports the substitution logic from `scripts/build_site.py` — including its
`validate_origin` checks, which are security-relevant — writing `site/` into
`web/public/`. `next.config.js` rewrites `/` to `/index.html`. A byte-comparison
test guards against drift.

Root Directory `web/` also avoids a known trap: with a blank root, Vercel
auto-detects the repo's `requirements.txt` and runs `uv pip install`, which fails
building `psycopg2`. Scoped to `web/`, Vercel sees only `web/package.json`.

A second Vercel project is **not** created unless a blocker is found.

---

## 5. Visual design

Both 21.dev components are used as **real React components** in `web/components/ui/`.
Neither is recreated in vanilla HTML.

**`sign-in-card-2.tsx`** keeps every visual behaviour: the 3D mouse-tracked tilt,
the four travelling border light beams with their staggered delays, corner glow
spots, glass card, animated radial background, input focus transitions, loading
states, and responsive layout.

Three changes only:

1. **Branding** — "StyleMe" → "TradeLens AI"; the placeholder `S` glyph → the
   TradeLens candle mark from `site/assets/`.
2. **Theme** — the purple palette is retargeted to the tokens already shared by
   the marketing site and the Streamlit app: bg `#0d1117`, surface `#161b22`,
   border `#252a32`, text `#e8eaed`, muted `#9aa4b2`, accent `#00e5cc`. Gradient
   geometry, opacity curves, and animation timings are unchanged — only hue moves.
   This resolves the one conflict in the brief: "keep the design" and "match
   TradeLens colours" cannot both hold for the purple, so structure is preserved
   and hue is swapped.
3. **Wiring** — the field is labelled **"Email or username"**; the button posts to
   `/api/auth/login`; `next/link` targets point at real routes.

**`password-strength.tsx`** is used unmodified except for mapping its
`emerald`/`amber`/`red` tones onto TradeLens status colours. Rules kept as
provided: 12+ characters, mixed case, a digit, a symbol, plus common-password and
repeated/sequential-run detection. It appears on **`/signup`** and
**`/reset-password`**.

**The meter is UX only.** The identical policy is enforced independently
server-side in `/api/auth/{signup,reset}`, and a test asserts a request that
bypasses the browser is rejected.

Tailwind carries the TradeLens tokens as theme extensions. Fonts match the site:
Schibsted Grotesk display, Satoshi body, JetBrains Mono labels.

---

## 6. Signup access modes

`SIGNUP_MODE` is read **server-side only** and never reaches the browser bundle.

| Value | Behaviour |
|---|---|
| `invite` | Requires a code matching `TRADELENS_INVITE_CODE`. The invite field renders **only** in this mode. |
| `open` | Anyone may create an account. No invite field in the DOM. |
| `closed` | `/signup` renders a closed state; the API rejects all requests. |

Unset defaults to `invite`. **An unrecognised value is treated as `closed` and
logged** — an unparseable access-control setting must fail shut.

The invite field is absent from the DOM in `open` mode rather than CSS-hidden, so
the page is never carrying a dead control, and switching to public launch is one
environment variable with no frontend change.

Invite validation is rate-limited (§11) so the code cannot be brute-forced.

---

## 7. The Streamlit handoff and durable session

### 7.1 Handoff — one-time credential

1. On successful login or verified signup, the Vercel function generates 32
   cryptographically random bytes, base64url-encoded.
2. It stores **only the SHA-256 hash** in `auth_handoffs`, with the user id, a
   **120-second** expiry, and a null `consumed_at`.
3. It redirects to `{APP_ORIGIN}/?ht=<token>`.
4. Streamlit hashes the parameter and redeems it with a single atomic
   compare-and-swap:
   `UPDATE auth_handoffs SET consumed_at = now() WHERE token_hash = :h AND consumed_at IS NULL AND expires_at > now()`.
   Redemption succeeds only if exactly one row is affected. This is not a
   read-then-write: Streamlit reruns scripts concurrently and two tabs can race.
5. It opens a session (§7.2) and immediately strips `ht` from the URL.

### 7.2 Durable session — the highest-risk decision

Streamlit wipes `session_state` on every full page reload. That is the entire
reason the 24h URL token exists. A one-time handoff with nothing behind it means
every browser refresh logs the user out — the exact bug `_try_restore` was built
to prevent. So the redeemed handoff must establish something durable, and *that*
choice is where the real security lives.

Three options were evaluated, as requested.

**Option A — redeem into the existing 24h HMAC token. Rejected.**
Streamlit would immediately place the same long-lived bearer back in the same
URL. The net gain over today is approximately zero and D1 still stands. This is
the "silent fallback to another long-lived URL bearer" that must not happen.

**Option B — Streamlit native OIDC. The correct end-state, deferred.**
Verified by inspecting the installed Streamlit 1.50.0 source:
`streamlit/web/server/oauth_authlib_routes.py:88` sets a **signed, HttpOnly**
auth cookie. So native `st.login()` genuinely gives a proper cookie-backed
session — no credential in the URL, survives refresh, and `st.logout()` clears
it. No third-party component is involved.

What it would cost: Streamlit redirects to an **OIDC provider**, so keeping the
21.dev page as the login UI means `tradelensai.io` must *be* that provider —
implementing authorization-code flow with PKCE, a discovery document, and JWKS —
or delegating to a hosted IdP (Auth0/Clerk/WorkOS) with the 21.dev component as
its custom login page. Writing an identity provider is a category of work where
subtle errors are catastrophic, and it is a larger change than everything else in
this spec combined. Two caveats also apply: Streamlit deliberately omits the
`Secure` flag (a documented Safari workaround, source comment at line 85), and
`[auth]` support on Community Cloud needs verification.

Recorded as the intended destination, scoped as its own future project.

**Option C — opaque server-side sessions. Chosen for this project.**
Replace the self-contained token with a random opaque id backed by an
`auth_sessions` row. Against today:

- **Revocable** — `sign_out()` marks the row revoked, which actually fixes D1.
- **No claims in the URL** — the id is meaningless without the server record.
- **Rotatable and auditable** — `last_seen_at` supports sliding expiry.
- **Short-lived** — TTL cut from 24h to **8h idle / 12h absolute**, minimising
  exposure while staying usable for a trading session.

**Stated plainly as a temporary beta limitation:** the session id is still a
bearer credential carried in the URL, because Streamlit Community Cloud gives us
no server-side cookie write outside its own OIDC flow. A copied link still grants
access until it expires or is revoked. This is meaningfully better than today —
revocable, claimless, and a third the lifetime — but it is not a cookie, and it
is not represented as one. It is removed by Option B.

**No third-party cookie component is added.** `extra-streamlit-components` and
similar are explicitly out of scope pending owner approval.

### 7.3 Cross-language token compatibility

The legacy HMAC token stays supported until Phase 9, so Node must produce bytes
Python accepts. Two details silently break everything if missed:

- Python builds the payload with `json.dumps(..., separators=(",", ":"))` and
  insertion order `u, i, e`. `JSON.stringify({u, i, e})` matches exactly.
- Python's `base64.urlsafe_b64decode` **requires `=` padding**; Node's
  `base64url` strips it. The Node implementation must re-pad.

Dedicated bidirectional tests cover valid, expired, tampered-payload, and
tampered-signature cases. These are kept regardless of the handoff design.

---

## 8. Schema

One Alembic revision on top of `r8s9t0u1v2w3`, with a fully implemented
`downgrade()`. Postgres is production, so real types are used. `sa.Date`,
`sa.Boolean`, and `sa.DateTime(timezone=True)` all round-trip on SQLite for local
tests.

### `users` — new columns, all added by `ALTER TABLE`

| Column | Type | Null | Server default |
|---|---|---|---|
| `full_name` | `String` | yes | — |
| `birthday` | `Date` | yes | — |
| `referral_source` | `String` | yes | — |
| `referral_source_other` | `String` | yes | — |
| `onboarding_completed` | `Boolean` | no | `false` |
| `strategy_profile_completed` | `Boolean` | no | `false` |
| `email_verified_at` | `DateTime(timezone=True)` (TIMESTAMPTZ) | yes | — |
| `email_verification_required` | `Boolean` | no | `true` |

`NULL` in `email_verified_at` means not verified; a timestamp means verified.

Nullability is deliberately asymmetric: the *database* permits null profile
fields so the migration cannot break existing rows, while the *signup endpoint*
requires them for new accounts. Validation lives in the service layer, which can
distinguish a new signup from a legacy row.

`is_active` stays `Integer`. Converting it is unrelated to this work.

### Backfill — explicit legacy compatibility

Existing users must not be forced through steps that did not exist when they
signed up, and must not be locked out.

| Column | Backfill for pre-existing rows | Why |
|---|---|---|
| `onboarding_completed` | `true` | They never saw the personal-info form; do not trap them behind it. |
| `email_verification_required` | **`false`** | The explicit legacy rule. |
| `email_verified_at` | **left `NULL`** | Honest: their address genuinely was never verified. |
| `strategy_profile_completed` | `true` where an active `Strategy` row exists, else `false` | Users without a profile get the first-run step exactly once. |
| `full_name`, `birthday`, `referral_source*` | left `NULL` | Never collected. |

The login gate is therefore
`if user.email_verification_required and user.email_verified_at is None: block`.
Legacy accounts pass because the flag is `false`, **not** because we pretended
their email was verified. That distinction is the point: the data stays truthful,
and if we later want to require verification of legacy accounts, flipping one
boolean per user is the whole change. New accounts are created with
`email_verification_required = true` (the column default) and are blocked until
they verify.

### New tables

**`auth_handoffs`** — `id`, `token_hash` (unique, indexed), `user_id` FK,
`created_at`, `expires_at`, `consumed_at` nullable.

**`auth_sessions`** — `id`, `token_hash` (unique, indexed), `user_id` FK,
`created_at`, `expires_at`, `last_seen_at`, `revoked_at` nullable.

**`auth_attempts`** — `id`, `bucket` (indexed), `action`, `succeeded`,
`created_at`.

**No table for email verification.** It reuses the proven `password_reset`
pattern: the code is signed with a key derived from the account's current email
and `email_verified_at`, so completing verification invalidates every outstanding
code with nothing to store or sweep. Codes are **purpose-bound** — the signing
key includes a `|verify-email|` domain separator, distinct from the existing
`|reset|`, so a code from one flow can never be replayed into the other. They
expire (30 min), carry only an account id and expiry, and die on use.

Expired rows in the three new tables are swept by an opportunistic `DELETE` of
rows older than 30 days on write, avoiding a scheduled job.

---

## 9. Flows

### 9.1 New user

```
tradelensai.io → Start your journal → /login → Sign up → /signup
  full name, email, birthday, referral source (+ other), password,
  invite code (invite mode only)
  → POST /api/auth/signup
      validate server-side, bcrypt cost 12, create user
      onboarding_completed = false, email_verified_at = NULL,
      email_verification_required = true
  → send verification email → /verify-email → POST /api/auth/verify
  → email_verified_at = now(), onboarding_completed = true
  → one-time handoff → 302 {APP_ORIGIN}/?ht=…
  → Streamlit redeems, opens session, strips ht
  → strategy_profile_completed = false → first-run Strategy Profile
  → dashboard
```

A new user **cannot reach the application before verifying**: the handoff is only
issued after `email_verified_at` is set. There is no separate `/onboarding`
route — `onboarding_completed` is set on successful verification, and a page with
nothing on it would be a step for its own sake.

### 9.2 Returning user

```
tradelensai.io → Start your journal → /login (email or username)
  → POST /api/auth/login → one-time handoff → 302 {APP_ORIGIN}/?ht=…
  → strategy_profile_completed? → first-run step if false, once
  → dashboard
```

### 9.3 Login identity resolution

Explicit precedence, no unsafe fallback:

1. Identifier contains `@` → resolve **by email only**, against
   `normalise_email()` (lowercased, trimmed). No match fails the login. It does
   **not** fall through to a username lookup.
2. Otherwise → resolve **by username only**, exact match.

The rule is total because usernames are already constrained to
`^[a-zA-Z0-9_]{3,20}$` (`users.py:22`) and cannot contain `@`, so no account is
unreachable and no identifier is ambiguous.

New users never choose a username. One is generated from the email local-part,
normalised to that charset, truncated to 20 characters, and de-duplicated with a
numeric suffix inside the same transaction as the insert, so a race cannot
produce a duplicate. Existing users keep their usernames. `Trade.user_id` and
`Strategy.user_id` foreign keys are unaffected.

Tested edge cases: `@` present with no matching email; uppercase and surrounding
whitespace; a username that is a prefix of another; an email local-part colliding
with an existing username; a local-part over 20 characters; a local-part
normalising to fewer than 3 characters; two concurrent signups whose local-parts
collide.

### 9.4 First-run Strategy Profile

Gate: authenticated, `user_id is not None`, `strategy_profile_completed` false.

The null-id guard matters — bootstrap sessions carry `user_id = None`
(`auth.py:299`) and `strategy._require_concrete_user_id` raises on one. Those
sessions skip the gate entirely.

New `src/tradelens/ui/components/strategy_onboarding.py` renders:

> **Welcome to TradeLens**
> Before we analyze your trades, tell the AI how you trade.

with the existing 12 Strategy Profile fields, and two exits:

- **Save profile** — writes through `strategy.upsert_strategy_profile()`, then
  sets the flag.
- **I don't have a defined strategy yet** — sets the flag only. **No `Strategy`
  row is created**; a fake profile would poison the AI context that profile data
  feeds.

Both set `strategy_profile_completed = true`, and the screen never returns unless
the flag is intentionally reset. This is exactly why the flag is stored rather
than derived from `get_active_strategy() is not None`: a user who skips is
*completed* but has *no* profile row, and a derived check cannot represent that.

The gate hooks into `require_auth()`, which every page already calls, so no page
can be reached around it. Logic (`get_onboarding_state`,
`mark_strategy_profile_completed`) lives in `services/users.py`; no Streamlit
import enters `services/`.

---

## 10. Database work

Production is **already Neon/Postgres**. This is an `ALTER TABLE` migration on a
live database, not an import, a recreate, or a data transfer.

**Rules.** The production database is never overwritten, recreated, or imported
over. A Neon branch snapshot is taken first and verified. The migration runs on a
development Neon branch first and is only then applied to production. Every
`downgrade()` is executed and verified, not assumed. Row counts for `users`,
`trades`, `strategies`, `corrections`, `weekly_reviews`, `screenshots`,
`ai_analyses`, and `performance_metrics` are captured before and compared after,
and must match exactly — this migration adds columns and tables and must change
no row count anywhere.

Full pre-flight procedure, including the exact statements, is in Phase 1 of the
implementation plan.

---

## 11. Security

**Rate limiting** — DB-backed in `auth_attempts`, never in-memory: serverless
instances share no state, so an in-memory counter is not a limit.

| Action | Buckets | Limit |
|---|---|---|
| login | IP + identifier | 10 / 15 min per IP; 5 / 15 min per identifier |
| signup | IP | 5 / hour |
| invite validation | IP | 10 / hour |
| verify-email / resend | user + IP | 10 / hour |
| forgot-password | IP + email | 5 / hour per IP; 3 / hour per email |
| reset-password | IP | 10 / hour |

Per-identifier limits count **failures only**, so an attacker cannot lock a known
user out by deliberately burning their quota. **A successful authentication
clears that identifier's failure counter.** Rejections return the same response
shape and comparable timing as an ordinary failure.

**Other measures.**

- Passwords travel over TLS to the serverless function and never leave it. No
  client-side hashing; no password in any URL, query string, or log.
- bcrypt cost pinned to 12 in Node, matching Python's verified `gensalt()`
  default. Cost is embedded in each hash, so existing hashes still verify.
- Same-origin `Origin`/`Referer` check on every state-changing POST.
- The reset flow's non-enumeration property is preserved: identical response
  whether or not the address is registered. Signup necessarily reveals that an
  email is taken, which is why signup is rate-limited per IP.
- `SIGNUP_MODE`, `TRADELENS_INVITE_CODE`, `TRADELENS_SESSION_SECRET`,
  `DATABASE_URL`, SMTP settings, and the Anthropic key are server-side only. A
  test asserts no `NEXT_PUBLIC_` variable carries any of them and that no secret
  appears in the client bundle.
- Handoff tokens and session ids are stored hashed; a database read yields no
  usable credential.
- No secret value is ever logged, echoed in an API response, or committed.

---

## 12. Configuration layer

D2 is fixed by giving Python **one** settings accessor. A single
`src/tradelens/settings_source.py` resolves in a fixed order — `os.environ`, then
`st.secrets` (guarded), then a default — and every module uses it:
`DATABASE_URL`, `TRADELENS_SESSION_SECRET`, `TRADELENS_INVITE_CODE`,
`SIGNUP_MODE`, the five SMTP settings, `APP_ORIGIN`, `SITE_ORIGIN`. It never
logs a value, and a test asserts no module reads `os.getenv` directly for any of
these names.

Node reads the same variable names from Vercel's environment, so one documented
set of names describes both runtimes.

### Environment variables to add manually

Values are never placed in the repository or pasted into chat.

**Streamlit Cloud — Settings → Secrets**

| Variable | What it is |
|---|---|
| `TRADELENS_SESSION_SECRET` | 32+ bytes of cryptographic randomness, base64 or hex. Signs session and verification tokens. **Must be byte-identical to Vercel's.** |
| `TRADELENS_SMTP_HOST` | Mail server hostname, e.g. your provider's SMTP endpoint |
| `TRADELENS_SMTP_PORT` | Usually `587` (STARTTLS) or `465` (implicit TLS) |
| `TRADELENS_SMTP_USER` | SMTP username, often an API-key identifier |
| `TRADELENS_SMTP_PASSWORD` | SMTP password or API key |
| `TRADELENS_SMTP_FROM` | Envelope/display sender, e.g. `TradeLens <no-reply@tradelensai.io>`. Must be an address the provider has authorised for the domain, or mail is silently dropped. |

**Vercel — Project → Settings → Environment Variables**

The same six, plus `DATABASE_URL` (the same Neon connection string, pooled
endpoint), `TRADELENS_INVITE_CODE`, `SIGNUP_MODE` (`invite` for beta),
`APP_ORIGIN`, and `SITE_ORIGIN`.

The Anthropic key is **not** added to Vercel. No AI call happens in the auth path.

### Email delivery

Node sends through the **same** `TRADELENS_SMTP_*` names via `nodemailer`, so one
configuration describes both runtimes and there is no second source of truth.

**Tradeoff, stated before any switch.** Some providers throttle or block SMTP
egress from serverless platforms, and each cold start pays a TLS handshake.
A transactional HTTP API (Resend, Postmark, SES) avoids both and gives delivery
logs, at the cost of a second provider account and a Python-side change so both
runtimes still agree. Recommendation: **start with SMTP**, since Python already
implements it and it keeps one mechanism; delivery is verified in Phase 4 against
a real inbox. If Vercel egress proves unreliable, swapping is contained behind a
single `sendMail()` function on each side — and that swap would be proposed, with
the provider named, before being made.

**Failing safely.** If email is unconfigured or delivery raises, signup returns a
clear "we could not send your verification email" and the account stays
unverified. `email_verified_at` is set **only** on successful code redemption,
never as a consequence of a send attempt, and never because a send failed.

---

## 13. AI integration

Unchanged. The Anthropic key stays in Streamlit Cloud secrets, every AI call
continues to route through `services/ai_client.py` on `ANTHROPIC_MODEL_ID`, and
no key or AI call is added to the Next.js app or to any browser bundle.

---

## 14. Rollout

The Streamlit login stays fully functional throughout. Nothing is removed until
the new path is verified end to end in production. Phases are in the
implementation plan; the cutover is repointing the six `[data-app-link]` CTAs in
`site/index.html` from `APP_ORIGIN` to `/login` — one commit, revertible in one
commit.

---

## 15. Testing

**Python (pytest).** The 136-test baseline must not regress. Migration upgrade
and downgrade on SQLite and on a Neon branch; each backfill rule; the legacy
compatibility rule specifically; handoff redemption including expiry, replay, and
concurrent redemption; session create/restore/slide/revoke; that `sign_out()` now
genuinely invalidates (D1); identity-resolution edge cases; the first-run gate
including the null-id skip and both exits; that the gate does not re-trigger;
rate limiting including failures-only counting and reset-on-success; that the
settings layer resolves identically under env and `st.secrets` (D2).

**Node (vitest).** Token issuance and verification; bcrypt round-trip; base64
padding; server-side password policy; all four `SIGNUP_MODE` values including an
unrecognised one failing shut; rate-limit guards; no secret in the client bundle.

**Cross-language.** Node-generated tokens verified in Python and the reverse —
valid, expired, tampered payload, tampered signature. The highest-risk seam,
covered independently of the handoff work.

**Manual.** The Phase 8 matrix in the implementation plan.
