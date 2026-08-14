# Deploying site-hosted authentication

Written at the end of Step 11, before anything has been deployed. Nothing in
here has been executed against production.

**No secret value appears in this file, and none should ever be added to it.**
Every entry names a variable and says where it lives.

---

## 0. What is already true

| Thing | State |
|---|---|
| Alembic head, production | `w3x4y5z6a7b8` |
| Alembic head, dev | `w3x4y5z6a7b8` |
| Schema migrations still needed for this feature | none |
| Production data changed by Steps 2–11 | none |
| Legacy Streamlit username/password login | untouched and still required |
| Vercel Root Directory | still the marketing site — **not** `web/` |

The database work is finished. Everything below is configuration and cutover.

---

## A. Vercel — the website

**Root Directory changes to `web/`.** That is the single switch that turns the
marketing-only project into the auth-serving one. `web/scripts/build-marketing.mjs`
copies `../site` into `public/` during `prebuild`, so the existing vanilla
marketing site is still served at `/` afterwards — it is not rewritten, and it
does not move.

### The root `vercel.json` stops being read

Today the repository root carries a `vercel.json` that drives the *current*
marketing deployment: it sets `buildCommand` to `python3 scripts/build_site.py`,
`outputDirectory` to `dist/site`, and — importantly — supplies `SITE_ORIGIN`
and `APP_ORIGIN` through `build.env`.

With Root Directory set to `web/`, Vercel reads `web/vercel.json`, which does
not exist. The Next.js defaults then apply, which is what we want for the build
commands — but **the two origins currently provided by `build.env` disappear
with it**. They must be added as project environment variables before the
switch, or `prebuild` fails validation and the deploy stops. (It failing is
correct; it failing unexpectedly during a cutover is not.)

### BLOCKER: Framework Preset must be Next.js, not "Other"

Root Directory alone is not enough, and the failure mode is quiet enough to be
mistaken for success.

With the preset left at "Other" (the project's `framework` reads `null`), Vercel
runs the build command and then publishes a **static output directory**,
defaulting to `public/`. The Next.js build runs, reports success, prints its
whole route table — and its output is discarded. What ships is the contents of
`public/`, which is precisely the marketing site.

Observed on the first correct build (`d3322e0`), where every log line was right:

| Path | Result |
|---|---|
| `/`, `/privacy/`, `/terms/` | 200 — static marketing, tokens substituted |
| `/login`, `/signup` | **404** |
| `/api/auth/*` | **404** |
| any response | **none of the `next.config.mjs` security headers** |

That last row is the tell. `next.config.mjs` sets `X-Frame-Options`,
`Referrer-Policy`, `X-Content-Type-Options` and HSTS on `/:path*`; if a Next
runtime were serving, every response would carry them. Their absence, with the
marketing site working perfectly, means the Next application was never deployed.

Set **Settings → Build & Deployment → Framework Preset → Next.js**, then trigger
a **new Git deployment**. Do not use "Redeploy": that replays the original
deployment's resolved settings rather than reading current project
configuration, which is what produced the earlier
`python3: can't open file '/vercel/path0/web/scripts/build_site.py'`.

Build settings after the switch:

| Setting | Value |
|---|---|
| Root Directory | `web` |
| Framework preset | Next.js — **explicitly**, see above |
| Build command | default (`next build`, which runs `prebuild` first) |
| Install command | default |
| Node version | 20 or later |

### Environment variables (Production scope)

Website-only secrets:

| Variable | Notes |
|---|---|
| `DATABASE_URL` | The Neon **production** branch pooled URL, `sslmode=require`. Same database the Streamlit app uses. |
| `TRADELENS_INVITE_CODE` | Required while `SIGNUP_MODE=invite`. At least 8 characters. |
| `TRADELENS_SMTP_HOST` | |
| `TRADELENS_SMTP_PORT` | `587` for STARTTLS, `465` for implicit TLS. |
| `TRADELENS_SMTP_USER` | Omit only if the relay needs no authentication. |
| `TRADELENS_SMTP_PASSWORD` | |
| `TRADELENS_SMTP_FROM` | e.g. `TradeLens AI <no-reply@tradelensai.io>`. Must be an address the relay is allowed to send as, or messages will be rejected or filed as spam. |

Public origins — safe to render, still set server-side and passed down as props:

| Variable | Value |
|---|---|
| `SITE_ORIGIN` | `https://www.tradelensai.io` — scheme + host only, no trailing path. |
| `APP_ORIGIN` | the Streamlit app origin, e.g. `https://<app>.streamlit.app` |
| `SIGNUP_MODE` | `invite`, `open`, or `closed`. Unset defaults to `invite`; anything unrecognised fails **closed**. |

Build-time only — read by `prebuild`, not at runtime:

| Variable | Notes |
|---|---|
| `SUPPORT_EMAIL` | The contact address on `/privacy`, `/terms` and the footer. **The build fails without it**, deliberately: the current marketing deploy substitutes it via `scripts/build_site.py`, and the Next `prebuild` must too or the switch to `web/` would publish a literal `mailto:__SUPPORT_EMAIL__`. |

**`TRADELENS_SESSION_SECRET` must NOT be set here.** Nothing in `web/` reads it.
The design that needed a shared HMAC key was replaced by opaque random
credentials whose hashes live in Postgres. Setting it would create a variable
that looks load-bearing, that rotating does nothing to, and that a future
reader would reasonably assume protects something.

Two properties depend on `SITE_ORIGIN` being correct and HTTPS:

* the session cookie's `Secure` flag is derived from its scheme;
* every auth endpoint's CSRF check compares against it.

---

## B. Streamlit Community Cloud — the app

No code change is required to deploy the app; it already consults site auth
first and falls back to legacy login.

### BLOCKER: the app is currently private

As of this writing, every anonymous request to the production app is answered
with a 303 to `share.streamlit.io/-/auth/app` — Streamlit Community Cloud's own
viewer sign-in. Site-hosted auth cannot work through that gate, for three
separate reasons:

1. **The user never reaches the app.** They are sent to Streamlit's login and
   must hold a Streamlit account on the viewer list. Our handoff is never seen.
2. **The one-time credential is forwarded to a third party.** The redirect
   preserves the query string, so `?ht=<token>` is handed to
   `share.streamlit.io` as part of `redirect_uri` and lands in logs on an
   origin outside our control.
3. **The 120-second TTL cannot survive it.** Completing a Streamlit OAuth
   sign-in inside two minutes is not a reasonable expectation, so handoffs
   would routinely expire and present the generic "link is no longer valid".

**Required before cutover:** set the app's sharing to public ("anyone with the
link can view") in Manage app → Settings → Sharing. TradeLens's own
authentication — the handoff plus the legacy login — is then the only gate,
which is what the design assumes.

Verify afterwards that an anonymous request returns 200 rather than a 303 to
`share.streamlit.io`.

Streamlit-only secrets (in the Cloud secrets UI, TOML):

| Variable | Notes |
|---|---|
| `TRADELENS_SESSION_SECRET` | **Legacy login only.** Signs the old `?auth=` session token. Retires with that login and belongs nowhere else. |
| `TRADELENS_USERNAME`, `TRADELENS_PASSWORD` | Legacy fallback credentials, if still in use. |
| `ANTHROPIC_API_KEY` | Unrelated to auth; already present. |

Shared with the website:

| Variable | Notes |
|---|---|
| `DATABASE_URL` | **The same production Neon URL as Vercel.** The two runtimes must agree byte for byte, or a handoff minted on one is invisible to the other. |
| `SITE_ORIGIN` | Used for the "back to TradeLens AI" link on a failed sign-in link. Must match Vercel's. |

Streamlit does **not** need `APP_ORIGIN`, the SMTP variables, or the invite code.

### What Streamlit cannot do, stated plainly

Streamlit Community Cloud serves the app's HTML itself. The app cannot set
`Cache-Control`, `Referrer-Policy`, `X-Frame-Options`, or a CSP on those
responses, and it cannot write an HttpOnly cookie outside its own OIDC flow.
Do not record these as configured on the app side, because they are not.

The consequence is the beta limitation below.

---

## C. Neon

Nothing to change. Production is already at `w3x4y5z6a7b8` and this feature
adds no migration.

Confirm before cutover:

* the pooled connection string used by both runtimes points at the
  **production** branch, not `dev-auth-migration`;
* `sslmode=require` is present;
* connection limits are sized for two runtimes rather than one — Vercel opens
  connections per serverless instance, which is a different shape of load than
  Streamlit's single long-lived process.

---

## D. DNS and domain

`www.tradelensai.io` already points at the Vercel project. Changing the Root
Directory does not change DNS, and there is no new hostname.

Check that the apex redirects to `www` (or the reverse) consistently: the CSRF
check compares against exactly one `SITE_ORIGIN`, so a user who reaches the
site on the other hostname will have their state-changing POSTs refused.

---

## E. Order of deployment

1. **Neon** — verify only. No change.
2. **Streamlit** — add `SITE_ORIGIN`; confirm `DATABASE_URL` is production.
   Deploy. The app is unchanged from a user's point of view: legacy login still
   works, and no handoff exists yet to consume.
2b. **Streamlit sharing** — set the app public, then confirm an anonymous
   request returns 200 rather than a redirect to `share.streamlit.io`.
3. **Vercel** — add every variable above, then switch Root Directory to `web/`
   and deploy. The marketing site continues to serve at `/`; the auth routes
   appear alongside it.
4. **Verify on production without telling anyone** — see below.
5. **Only then** change the marketing CTA to point at `/signup` or `/login`.

Streamlit before Vercel, deliberately: the app must be ready to accept a
handoff before the website can mint one.

## F. Testing safely before the CTA changes

Every auth route is reachable by URL while the marketing CTA still points where
it always did, so the whole flow can be exercised in production by people who
know the URLs and nobody else:

* set `SIGNUP_MODE=invite` and keep the invite code private;
* walk `/signup → email → /verify-email → /login → /onboarding → /continue`
  and confirm the Streamlit journal opens;
* confirm a real verification email arrives from the production relay, and
  that its links point at `https://www.tradelensai.io`, never at the app host;
* confirm the session cookie comes back `Secure; HttpOnly; SameSite=lax`.

Change the CTA only after a full pass.

## G. Rollback

| Failure | Action |
|---|---|
| Anything wrong with the website | Revert Root Directory to the marketing site and redeploy. The marketing site returns exactly as before; the auth routes 404. |
| The CTA was already changed | Point it back at the Streamlit app first — that is one edit and it restores the old journey immediately. |
| A bad Vercel deploy | Promote the previous deployment. Instant, no rebuild. |
| Streamlit misbehaving | Legacy username/password login is still present and unchanged, so the app remains usable while site auth is disabled. |
| Suspected credential compromise | `SIGNUP_MODE=closed` stops new accounts immediately, and revoking rows in `auth_sessions` / `auth_handoffs` invalidates live credentials without a deploy. |

No rollback path requires a database migration, because no migration is part of
this cutover. That is the main reason the schema work was finished first.

## H. When the legacy Streamlit login can be removed

Not part of this deployment. The preconditions are:

1. site auth has run in production long enough to be trusted;
2. both legacy accounts (`ayoub`, `Ayoub`) have a verified email address and
   can sign in through the website;
3. `TRADELENS_USERNAME` / `TRADELENS_PASSWORD` are no longer needed by anyone.

Removing it also retires `TRADELENS_SESSION_SECRET`, which is the last thing
that reads it.

## I. Known beta limitation to carry into production

After the handoff, the Streamlit session travels as `?s=<token>` in the URL,
because Streamlit Community Cloud offers no server-side cookie write outside
its own OIDC flow. Anyone who obtains that URL is that session until it expires
(8h idle / 12h absolute) or is revoked.

The app replaces the query parameter after the exchange, which cleans the URL
the app currently controls. It does **not** erase entries already written to
browser history, and nothing here should be read as claiming otherwise. This is
not equivalent to the website's HttpOnly cookie. Streamlit's native OIDC is the
real fix and is out of scope for this rollout.
