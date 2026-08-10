# Site-hosted authentication and first-run onboarding

**Date:** 2026-08-10
**Status:** Approved design, pending implementation plan
**Supersedes:** nothing. Extends the existing Streamlit auth rather than replacing it.

---

## 1. Goal

Move sign-in, sign-up, and password reset out of the Streamlit app and onto the
marketing site at `tradelensai.io`, so the login experience is fast, fully
designed, and continuous with the rest of the product. After authenticating, the
user is handed off to the Streamlit app already signed in.

New users additionally complete a profile at signup, verify their email, and are
routed through a first-run Strategy Profile step before reaching the dashboard.

### What this does not do

Moving login off Streamlit does not make the app faster. After the handoff the
user still lands in the same Streamlit container and still waits through the same
cold start. The login *screen* becomes fast and fully customisable; the
application behind it is unchanged. This is worth stating plainly because
"the Streamlit login feels slow and buggy" was the motivating complaint, and
only part of it is addressed here.

---

## 2. Current state

Established by inspection on 2026-08-10.

| Piece | Location | State |
|---|---|---|
| `User` model | `src/tradelens/db/models.py:7` | `id, username, password_hash, email (unique, nullable), created_at, is_active` |
| Password hashing | `src/tradelens/services/users.py` | bcrypt via `bcrypt.hashpw` / `checkpw` |
| Login orchestration | `src/tradelens/ui/components/auth.py:254` | DB users take precedence; legacy secrets pair only while `users` is empty |
| Session persistence | `auth.py:87-167` | Self-contained HMAC-SHA256 token in `?auth=`, 24h TTL, sliding rotation |
| Signup gate | `auth.py:244-251` | Requires `TRADELENS_INVITE_CODE`; disabled entirely when unset |
| Password reset | `src/tradelens/services/password_reset.py` | Email + code over stdlib SMTP; token signed with a key derived from the account's current password hash, so it is single-use with no token table |
| Strategy Profile | `src/tradelens/services/strategy.py` | `get_active_strategy(user_id)`, `upsert_strategy_profile(user_id, **fields)`, 12 fields, one active row per user |
| Marketing site | `site/` | Vanilla `index.html` + `styles.css` + `main.js`; no `package.json` anywhere in the repo |
| Site build | `scripts/build_site.py` | stdlib-only Python; substitutes `__SITE_ORIGIN__` / `__APP_ORIGIN__` into `dist/site` |
| Deployment | `vercel.json` | Vercel project `tradelens-ai-site`; `SITE_ORIGIN=https://www.tradelensai.io`, `APP_ORIGIN=https://tradelenai.streamlit.app` |

### Pre-existing defects found during inspection

These are not caused by this work. Two of them are load-bearing for it.

**D1 — `sign_out()` does not invalidate the session token.**
`auth.py:389` clears `st.session_state` and pops the URL parameter, but the HMAC
token itself stays cryptographically valid until its 24h expiry. Anyone holding a
copy — browser history, a shared link, a screenshot — can sign back in after the
user has "logged out". Self-contained tokens cannot be revoked; this is inherent
to the current design and is fixed by §6.

**D2 — `password_reset.py` cannot read secrets on Streamlit Cloud.**
`password_reset._read_env` (line 78) uses `os.getenv` only, while
`auth._read_secret` (line 169) falls back to `st.secrets`. Streamlit Cloud exposes
secrets through `st.secrets`, not the process environment. So on Cloud:
`TRADELENS_SMTP_*` appears unconfigured, and — worse —
`password_reset._base_secret()` and `auth._session_secret()` derive **different**
base secrets from the same nominal setting. Fixed by making `password_reset` use
the shared `_read_secret` helper.

**D3 — production data durability is unverified.**
`settings.database_url` defaults to `sqlite:///./data/tradelens.db`
(`config.py:41`). On Streamlit Cloud that path is inside the container's
ephemeral filesystem. Unless a persistent `DATABASE_URL` is configured, every
redeploy or container restart discards all users and trades. See §9; **no
migration step in this spec may run until this is verified.**

**D4 — the stored note for the app URL was wrong.**
It recorded `tradelens-app.streamlit.app`. The live value, confirmed by both
`vercel.json` and the browser address bar, is `tradelenai.streamlit.app`. No
hostname is hardcoded anywhere in this design; everything reads `APP_ORIGIN`.

---

## 3. Deployment shape

One Vercel project. A Next.js + TypeScript + Tailwind app in `web/`, with the
project's **Root Directory set to `web/`**.

```
tradelensai.io
  /                       → public/index.html      (existing site, byte-identical)
  /login                  → 21.dev sign-in card
  /signup                 → profile + password, with strength meter
  /verify-email           → code entry
  /forgot-password        → request a reset code
  /reset-password         → code + new password, with strength meter
  /api/auth/{login,signup,verify,resend,forgot,reset}
                          → Node serverless functions
        ↓ on success
  302 → {APP_ORIGIN}/?ht=<one-time handoff token>
```

The existing marketing site is **not rewritten**. A Next `prebuild` script ports
the substitution logic from `scripts/build_site.py` — including its
`validate_origin` checks, which are security-relevant — and writes `site/` into
`web/public/`. `next.config.js` rewrites `/` to `/index.html`.

Setting Root Directory to `web/` also resolves a known deployment trap: with a
blank root, Vercel auto-detects the repo's `requirements.txt` and runs
`uv pip install`, which fails building `psycopg2` from source. Scoped to `web/`,
Vercel sees only `web/package.json` and never attempts a Python install.

`scripts/build_site.py` is deleted once the Node port is verified, so the
substitution logic has exactly one implementation.

### Rejected alternatives

- **Two Vercel projects joined by cross-project rewrites.** Zero risk to the
  existing site, but doubles the deploys, the env vars, and the places a secret
  can drift out of sync. The shared `TRADELENS_SESSION_SECRET` makes drift a
  silent, total auth failure.
- **Porting the 21.dev components to vanilla HTML/CSS/JS.** Smallest footprint,
  no toolchain, but it is a reimplementation rather than the components
  themselves. Explicitly rejected by the owner: the real React components must be
  used.

---

## 4. Visual design

Both 21.dev components are used as real React components, not approximations.

**`web/components/ui/sign-in-card-2.tsx`** keeps every visual behaviour: the 3D
mouse-tracked tilt, the four travelling border light beams with their staggered
delays, the corner glow spots, the glass card, the animated radial background,
the input focus transitions, the loading state, and the layout.

Three changes only:

1. **Branding.** "StyleMe" → "TradeLens AI"; the placeholder `S` glyph → the
   existing TradeLens candle mark from `site/assets/`.
2. **Theme.** The purple palette is retargeted to the tokens already shared by
   the marketing site and the Streamlit app: background `#0d1117`, surface
   `#161b22`, border `#252a32`, text `#e8eaed`, muted `#9aa4b2`, accent
   `#00e5cc`. The gradient, radial glows, and pulse spots keep their exact
   geometry, opacity curves, and animation timings — only the hue changes. This
   resolves the one conflict in the brief: "keep the design" and "match TradeLens
   colours" cannot both hold for the purple, so structure is preserved and hue is
   swapped.
3. **Fields.** The `Sign In` button submits to `/api/auth/login`; `next/link`
   destinations point at the real routes.

**`web/components/ui/password-strength.tsx`** is used unmodified except for its
tone palette, whose `emerald` / `amber` / `red` are mapped onto the TradeLens
accent and status colours. Its rules are kept as provided: 12+ characters, mixed
case, a digit, a symbol, plus the common-password and repeated/sequential-run
detection.

It appears on **`/signup`** and **`/reset-password`**. Both are Next.js pages;
neither is rebuilt inside Streamlit.

Tailwind is configured with the TradeLens tokens as theme extensions so the two
components and any future ones read from one palette. Fonts match the site:
Schibsted Grotesk display, Satoshi body, JetBrains Mono labels.

---

## 5. Signup access modes

Signup mode is environment-controlled, so it changes without a code change or a
redeploy of the frontend.

`SIGNUP_MODE` — read server-side only, never sent to the browser:

| Value | Behaviour |
|---|---|
| `invite` | Signup allowed only with a code matching `TRADELENS_INVITE_CODE`. The invite field is rendered **only in this mode**, from a server-rendered flag. |
| `open` | Anyone may create an account. No invite field. |
| `closed` | `/signup` returns a "signups are closed" state; `/api/auth/signup` rejects all requests. |

Default when unset: `invite`. An unrecognised value is treated as `closed` and
logged — an unparseable access-control setting must fail shut, not open.

The invite field is absent from the DOM in `open` mode rather than hidden with
CSS, so the polished UI is never carrying a dead control.

The existing Streamlit invite-code signup is left untouched until the new system
is verified end to end (§11).

---

## 6. The Streamlit handoff

### 6.1 The problem with the current design

Today the URL parameter *is* the session: a self-contained, 24-hour HMAC token
carrying `{username, user_id, expiry}`. It cannot be revoked (D1), it carries
claims in plaintext-decodable form, and it survives in browser history and
copied links for a day.

### 6.2 The requested design, and an honest accounting of it

A one-time handoff token replaces the long-lived token *in the redirect*:

1. On successful login or signup, the Vercel function generates 32 cryptographically
   random bytes, base64url-encoded.
2. It stores **only the SHA-256 hash** in `auth_handoffs`, with the user id, an
   expiry of **120 seconds**, and a null `consumed_at`.
3. It redirects to `{APP_ORIGIN}/?ht=<token>`.
4. Streamlit hashes the parameter, looks it up, and redeems it with a single
   atomic conditional update:
   `UPDATE auth_handoffs SET consumed_at = now() WHERE token_hash = :h AND consumed_at IS NULL AND expires_at > now()`.
   Redemption succeeds only if that statement reports one affected row. This is a
   compare-and-swap, not a read-then-write, because Streamlit reruns scripts
   concurrently and two tabs can race.
5. It establishes the session and immediately removes `ht` from the URL.

**This solves the handoff, but not the thing that matters most.** Streamlit wipes
`st.session_state` on any full page reload, which is precisely why the long-lived
URL token was introduced. If the handoff token is one-time and nothing replaces
it, every browser refresh logs the user out again — the exact bug
`_try_restore` exists to prevent. So the redeemed handoff must establish
*something* that survives a reload, and the security of the whole scheme depends
on what that something is.

The owner asked to be told if a simpler, equally secure architecture exists.
It does not, given the constraints — Vercel and Streamlit Cloud are separate
origins and Streamlit has no server-side cookie-write API — but the options
differ materially and the choice should be explicit:

**Option A — redeem into the existing 24h HMAC token.**
Simplest. But Streamlit then immediately issues the same long-lived bearer token
into the same URL, so the net security gain over today is close to zero. The
credential in the address bar is still a 24-hour key to the account, and D1 still
stands. **Rejected as security theatre.**

**Option B — redeem into an opaque server-side session (recommended).**
Replace the self-contained token with a random opaque session id backed by an
`auth_sessions` row. Concrete gains over today:

- **Revocable.** `sign_out()` marks the row revoked, which actually fixes D1.
  Today's logout leaves a working credential behind.
- **No claims in the URL.** The id is meaningless without the server record.
- **Rotatable and auditable.** `last_seen_at` supports sliding expiry and lets a
  user see and end active sessions later.
- **Dies with the record**, not on a fixed self-contained expiry.

Residual risk, stated plainly: the session id is still a bearer credential
carried in the URL, so a copied link still grants access until it expires or is
revoked. This is better than today but is not the same as a cookie.

**Option C — Option B plus a real browser cookie.**
`extra-streamlit-components`' `CookieManager` writes a cookie through a
bidirectional component, which would remove the credential from the URL entirely.
It cannot be `HttpOnly` (it is set from JavaScript), and it adds a third-party
runtime dependency to the auth path. Deferred to a follow-up phase rather than
taken on inside a migration that is already large.

**Decision: Option B now, Option C as a separately-scoped follow-up.**

### 6.3 Cross-language token compatibility

The existing HMAC token remains supported during migration, so Node must be able
to produce bytes Python accepts. Two details will silently break everything if
missed:

- Python builds the payload with `json.dumps(..., separators=(",", ":"))` and
  insertion order `u, i, e`. `JSON.stringify({u, i, e})` matches exactly.
- Python's `base64.urlsafe_b64decode` **requires `=` padding**. Node's
  `base64url` encoding strips it. The Node implementation must re-pad.

A dedicated cross-language test suite covers this in both directions: tokens
generated in Node verified by Python, and tokens generated by Python verified in
Node, including expiry and tamper cases. These tests are kept regardless of which
handoff design ships.

**Hard prerequisite.** `TRADELENS_SESSION_SECRET` must be set to the *same* value
in Streamlit Cloud secrets and Vercel environment variables. It is very likely
unset today, in which case `_session_secret()` falls back to a random
per-process key (`auth.py:100`) and every token Vercel issues is rejected.
Nothing in this design functions until that value is set in both places.

---

## 7. Schema

One Alembic revision, `s9t0u1v2w3x4_add_site_auth_and_onboarding`, with a fully
implemented `downgrade()`.

Postgres becomes the production database, so the new columns use real types
rather than the string-encoded convention used by the older `created_at` columns.
`sa.Date` and `sa.Boolean` both round-trip correctly on SQLite and Postgres under
SQLAlchemy 2.x, so local development and tests are unaffected.

### `users` — new columns

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `full_name` | `String` | yes | — | Required at signup for new users; nullable so existing rows stay valid |
| `birthday` | `Date` | yes | — | Real date type |
| `referral_source` | `String` | yes | — | One of the fixed options |
| `referral_source_other` | `String` | yes | — | Free text, only when `referral_source = 'other'` |
| `onboarding_completed` | `Boolean` | no | `false` | |
| `strategy_profile_completed` | `Boolean` | no | `false` | |
| `email_verified` | `Boolean` | no | `false` | |

Nullability is deliberately asymmetric: the *database* permits null profile
fields so the migration cannot break existing accounts, while the *signup
endpoint* requires them for new accounts. Validation lives in the service layer,
where it can distinguish a new signup from a legacy row.

`is_active` remains `Integer` for now. Converting it is unrelated to this work
and would touch code paths this change does not otherwise go near.

### Backfill

Existing accounts must not be trapped behind gates that did not exist when they
signed up:

- `onboarding_completed = true` for every pre-existing row.
- `email_verified = true` for every pre-existing row **that already has an
  email**. Rows without one keep `false` and are handled by §8.4 — an account
  created before verification existed must not be locked out for never having
  passed a step that did not exist.
- `strategy_profile_completed = true` where the user already has an active
  `Strategy` row, `false` otherwise. Users without a profile are routed through
  the first-run step exactly once, which is the intended behaviour.

### New tables

**`auth_handoffs`** — one-time Vercel → Streamlit credentials.
`id`, `token_hash` (unique, indexed), `user_id` (FK), `created_at`,
`expires_at`, `consumed_at` (nullable).

**`auth_sessions`** — opaque server-side sessions (§6.2 Option B).
`id`, `token_hash` (unique, indexed), `user_id` (FK), `created_at`,
`expires_at`, `last_seen_at`, `revoked_at` (nullable).

**`auth_attempts`** — rate limiting (§10).
`id`, `bucket` (indexed), `action`, `created_at`.

**`email_verifications`** — no table. Verification reuses the existing
`password_reset` pattern: the code is signed with a key derived from the
account's current `email` and `email_verified` state, so completing verification
invalidates every outstanding code with nothing to store or sweep. Reusing a
proven in-repo pattern is preferred to inventing a second one.

Only expired/consumed rows in `auth_handoffs`, `auth_sessions`, and
`auth_attempts` need sweeping; a single `DELETE` of rows older than 30 days runs
opportunistically on write, avoiding a scheduled job.

---

## 8. Flows

### 8.1 New user

```
tradelensai.io → Start your journal → /login → Sign up → /signup
  full name, email, birthday, referral source (+ other), password
  → POST /api/auth/signup   (validates, hashes with bcrypt cost 12, creates user,
                             onboarding_completed = true, email_verified = false)
  → /verify-email  → POST /api/auth/verify
  → email_verified = true
  → issue one-time handoff → 302 {APP_ORIGIN}/?ht=…
  → Streamlit redeems, opens session, strips ht from URL
  → strategy_profile_completed = false → first-run Strategy Profile
  → dashboard
```

`onboarding_completed` is set when the signup form completes. There is no
separate `/onboarding` route; adding one would be a page with nothing on it.

### 8.2 Returning user

```
tradelensai.io → Start your journal → /login
  → POST /api/auth/login → one-time handoff → 302 {APP_ORIGIN}/?ht=…
  → dashboard
```

If `strategy_profile_completed` is false — a pre-existing user with no profile —
they pass through the first-run step once, then never again.

### 8.3 Login identity resolution

Explicit precedence, no ambiguity:

1. If the submitted identifier contains `@`, resolve **by email only**, against
   `normalise_email()` (lowercased, trimmed). If no account matches, the login
   fails. It does not fall through to a username lookup.
2. Otherwise resolve **by username only**, exact match.

An account whose *username* legitimately contains `@` is unreachable by rule 1
falling back — which is why usernames are already constrained to
`^[a-zA-Z0-9_]{3,20}$` (`users.py:22`) and cannot contain `@`. The rule is
therefore total and unambiguous.

New users never choose a username. One is generated from the email local-part,
normalised to the existing charset, truncated to 20 characters, and
de-duplicated with a numeric suffix. This keeps `Trade.user_id` and
`Strategy.user_id` foreign keys working exactly as they do now.

Edge cases with explicit tests: `@` in the identifier but no such email;
uppercase and surrounding whitespace in an email; a username that is a prefix of
another; an email local-part colliding with an existing username; a generated
username exceeding 20 characters; two signups whose local-parts collide.

### 8.4 Legacy accounts and email verification

An existing account must not become unusable because a step invented today was
never completed:

- Accounts **with** an email are backfilled `email_verified = true`. They already
  proved control of it through the existing reset flow's threat model, and
  retroactively locking them out has no security benefit.
- Accounts **without** an email keep `email_verified = false`. They can still
  sign in with username + password. They are prompted — not blocked — to attach
  and verify an address, because without one a forgotten password is
  unrecoverable. Verification is enforced only for accounts created through the
  new signup endpoint.

### 8.5 First-run Strategy Profile

Gate: authenticated, `user_id is not None`, `strategy_profile_completed` false.

The `user_id is not None` guard matters — legacy secrets-pair sessions carry a
null user id (`auth.py:299`) and `strategy._require_concrete_user_id` raises on
one. Those sessions skip the gate entirely.

New `src/tradelens/ui/components/strategy_onboarding.py` renders:

> **Welcome to TradeLens**
> Before we analyze your trades, tell the AI how you trade.

with the existing 12 Strategy Profile fields, and two exits:

- **Save profile** — writes through `strategy.upsert_strategy_profile()`, then
  sets the flag.
- **I don't have a defined strategy yet** — sets the flag only, writes no
  `Strategy` row.

Both mark `strategy_profile_completed = true`, and the screen never appears
again unless the flag is intentionally reset. This is exactly why the flag is a
stored column rather than derived from `get_active_strategy() is not None`: a
user who skips is *completed* but has *no* profile row, and a derived check
cannot represent that.

The gate hooks into `require_auth()`, which every page already calls, so no page
can be reached around it. Business logic (`get_onboarding_state`,
`mark_strategy_profile_completed`) lives in `services/users.py`; no Streamlit
import enters `services/`.

---

## 9. Database migration to Neon

**No migration step runs until D3 is resolved.** Nothing in this section may be
executed, and no claim that existing users were migrated may be made, before the
production value is verified.

### What to check in Streamlit Cloud

Open the app's **Settings → Secrets** and look for a `DATABASE_URL` entry. Report
which of these it is — the value itself is a credential and should not be pasted
anywhere it will be stored:

| What you find | What it means | What we do |
|---|---|---|
| No `DATABASE_URL` at all | The app is on the ephemeral container SQLite. All production data is being discarded on every restart. | There is nothing to migrate. Stand up Neon clean; this change *fixes* an active data-loss bug. |
| `postgresql://…` or `postgres://…` | A real external Postgres already holds production data. | Dump it, restore into Neon, run Alembic, verify row counts before cutover. |
| `sqlite:///…` pointing at a mounted persistent path | Data may be surviving restarts. | Pull the file down, inspect it, migrate its contents into Neon. |

Also confirm whether `TRADELENS_SESSION_SECRET`, `TRADELENS_INVITE_CODE`, and the
`TRADELENS_SMTP_*` values are present, since D2 means the SMTP ones may never
have been read on Cloud even if they are set.

### Migration rules

- Take a backup before touching anything, and verify the backup restores before
  it is relied on.
- The old database is **not** deleted, overwritten, or repointed during initial
  rollout. It stays intact and reachable as the rollback target.
- Cutover is a `DATABASE_URL` change, so rollback is the same change in reverse.
- Row counts for `users`, `trades`, and `strategies` are compared before and
  after and must match exactly.
- Alembic runs against Neon; every revision's `downgrade()` is tested, not
  assumed.

---

## 10. Security

**Rate limiting.** DB-backed, never in-memory — serverless instances share no
state, so an in-memory counter is not a limit. Every attempt inserts an
`auth_attempts` row keyed on a bucket; a request is rejected when the count in
the window is exceeded.

| Action | Bucket | Limit |
|---|---|---|
| login | IP, and identifier | 10 / 15 min per IP; 5 / 15 min per identifier |
| signup | IP | 5 / hour |
| forgot-password | IP, and email | 5 / hour per IP; 3 / hour per email |
| reset-password | IP | 10 / hour |
| verify-email | user | 10 / hour |

Per-identifier limits are counted on failures only, so an attacker cannot lock a
known user out by burning their quota deliberately. Rejections return the same
shape and timing as a failed attempt, and are tested directly rather than
assumed.

**Other measures.**

- Passwords are sent over TLS to the serverless function and never leave it.
  No client-side hashing, no password in any URL, query string, or log.
- bcrypt cost pinned to 12 in Node to match Python's current `gensalt()` default.
  Cost is embedded in the hash, so existing hashes at other costs still verify.
- Same-origin `Origin`/`Referer` check on every state-changing POST.
- The reset flow's existing non-enumeration property is preserved: the response
  is identical whether or not the address is registered. Signup necessarily
  reveals that an email is taken; that is accepted, and is why signup is
  rate-limited per IP.
- `SIGNUP_MODE`, `TRADELENS_INVITE_CODE`, `TRADELENS_SESSION_SECRET`, and
  `DATABASE_URL` are server-side only and never reach a client bundle. A test
  asserts no `NEXT_PUBLIC_` variable carries any of them.
- Handoff tokens and session ids are stored hashed. A database read does not
  yield a usable credential.
- D2 is fixed: `password_reset.py` moves to the shared `_read_secret` helper so
  both modules derive the same base secret on Streamlit Cloud.

**Email delivery from Vercel.** Node sends through the same `TRADELENS_SMTP_*`
settings via `nodemailer`, so there is one mail configuration for both runtimes.
Some providers throttle or block SMTP egress from serverless platforms; if that
happens, swapping to an HTTP email API is contained behind a single `sendMail()`
function and changes nothing else.

---

## 11. Rollout and rollback

The Streamlit login stays fully functional throughout. Nothing is removed until
the new path is verified end to end in production.

1. Neon stood up, Alembic applied, `DATABASE_URL` and
   `TRADELENS_SESSION_SECRET` set identically on both hosts.
2. Next.js app deployed; auth routes reachable but not yet linked from the site.
3. Verified in production with a real account: signup, verification, handoff,
   first-run Strategy Profile, dashboard, sign out, sign back in, reset password.
4. The six `[data-app-link]` CTAs in `site/index.html` are repointed from
   `APP_ORIGIN` to `/login`. This is the switch, and it is one commit to revert.
5. After a soak period, the Streamlit login screen and the legacy `?auth=` token
   path are removed in a separate change.

Rollback at any point before step 5 is reverting step 4 and, if needed,
repointing `DATABASE_URL`. The old database is untouched throughout.

---

## 12. Testing

**Python (pytest).** The 136-test baseline must not regress.
Migration upgrade and downgrade against both SQLite and Postgres; backfill
correctness for each of the three backfill rules; handoff redemption including
expiry, replay, and concurrent-redemption races; opaque session create, restore,
slide, and revoke; that `sign_out()` now genuinely invalidates (D1);
identity-resolution edge cases from §8.3; the first-run gate including the
null-`user_id` skip; both first-run exits; that the gate does not re-trigger;
rate-limit enforcement and the failures-only counting rule.

**Node (vitest).** Token issuance and verification; bcrypt round-trip;
base64 padding; signup and login validation; `SIGNUP_MODE` behaviour for all
three values plus an unrecognised one falling shut; rate-limit guards; that no
secret reaches a client bundle.

**Cross-language.** Node-generated tokens verified in Python and the reverse,
covering valid, expired, tampered-payload, and tampered-signature cases. This is
the highest-risk seam in the design and gets dedicated coverage independent of
the handoff work.

**Manual.** Full new-user and returning-user walkthroughs against staging before
step 4, at desktop and mobile widths, including reduced-motion.

---

## 13. Open items

1. **`DATABASE_URL` in Streamlit Cloud** — blocking §9. See the table there for
   exactly what to look for.
2. **`TRADELENS_SESSION_SECRET`** — must be generated and set identically on both
   hosts before anything works.
3. **SMTP reachability from Vercel** — verify during phase 2; the fallback is
   contained.
