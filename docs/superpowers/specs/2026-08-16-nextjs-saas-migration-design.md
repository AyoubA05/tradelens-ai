# TradeLens AI — Streamlit → Next.js SaaS migration

**Date:** 2026-08-16
**Status:** Design approved; spec pending owner review
**Supersedes nothing.** Extends the auth work in `2026-08-10-site-hosted-auth-design.md`.

---

## 1. Purpose

Replace the Streamlit presentation layer with a Next.js application served from
the same origin as the marketing site, so a user never crosses a visible seam
between "the website" and "the app". The TradeLens intelligence — services,
database, prompts, AI client — is preserved and exposed to the frontend through
a new FastAPI layer.

This is a presentation migration. No feature is added, removed, or redefined.
Interactions that Streamlit made impossible (deep links, URL-persisted filters,
keyboard navigation, optimistic updates, streaming) are in scope, because they
change how the product feels without changing what it does.

**Non-goals.** New product capabilities. Changes to prompts. Changes to the AI
model or routing. Schema redesign. Pricing or packaging.

---

## 2. Target architecture

```
                         ┌────────────────────────────────────────┐
   Browser  ─────────────│  Next.js on Vercel                     │
   (all application and  │  marketing · auth · authenticated app  │
    API traffic)         │  RSC pages + route handlers            │
                         └───────────────┬────────────────────────┘
                                         │  server-to-server, TLS only
                                         │  X-TL-Signature  (HMAC, timestamped)
                                         │  X-TL-Session-Handle (domain hash)
                                         ▼
                         ┌────────────────────────────────────────┐
                         │  FastAPI — public HTTPS, not browser-  │
                         │  consumed. Render/Railway/Fly.         │
                         │  ├─ deps.current_user()                │
                         │  ├─ routers/   (thin)                  │
                         │  └─ schemas/   (Pydantic)              │
                         └──────┬────────────────────┬────────────┘
                                │                    │
                  src/tradelens/services/     ai_jobs worker
                  src/tradelens/db/           (same image, separate process)
                                │                    │
                        ┌───────▼──────┐      ┌──────▼───────┐
                        │ Neon Postgres│      │ Anthropic    │
                        │              │      │ claude-opus-5│
                        └──────────────┘      └──────────────┘

   Storage exception — the only traffic that does NOT go through Next.js:
   Browser ──── presigned PUT (upload) / presigned GET (view) ────► Cloudflare R2
```

**Traffic rule.** The browser talks to the Next.js origin for all application
and API traffic. The single exception is chart-screenshot bytes, which move
directly between the browser and Cloudflare R2 using short-lived presigned URLs
issued by the backend. Presigning is requested through Next.js; only the object
transfer itself is direct.

### 2.1 The FastAPI hosting boundary

FastAPI is deployed as a **public HTTPS service** (a Render Web Service, or the
Fly/Railway equivalent), not a private service.

This is deliberate and worth stating, because the obvious instinct is wrong.
A Render Private Service is reachable only from inside that Render account's
private network. Vercel functions are not in that network, and Vercel's egress
addresses are dynamic on standard plans, so neither private networking nor IP
allowlisting can be depended on as the primary control. Designing as if the
backend were unreachable from the internet would produce a service that is in
fact reachable and defended by an assumption.

The backend is therefore treated as internet-exposed and defended accordingly.
It is *not browser-consumed*: no CORS headers are ever emitted, so no browser
can make a credentialed cross-origin call to it, and no frontend code holds its
address or secret.

Every request must satisfy **both** of the following, independently:

**Lock 1 — trusted server-to-server authentication.**
`X-TL-Signature: v1={timestamp}:{hex-hmac}` where the HMAC-SHA256 is computed
over `timestamp . method . path . canonical_query . sha256(body)` using `TL_SERVICE_SECRET`,
shared only between the Vercel environment and the backend environment.
Rejected if the timestamp is more than 60 seconds from the server clock, if the
signature is absent, or if it fails constant-time comparison. Binding the
method, path, ordered canonical query, and body prevents a captured signature
from being moved to a different request. An exact request can still be replayed
inside the 60-second freshness window; future mutating routes require an
idempotency key or a durable nonce if that replay is not intrinsically safe.

**Lock 2 — database-backed session validation.**
`X-TL-Session-Handle` carries the existing `WEBSITE_DOMAIN`-separated SHA-256
database lookup handle. The raw HttpOnly browser credential never crosses into
FastAPI, its tracing, or its hosting infrastructure. FastAPI resolves the row
itself, applying the same five conditions Next.js applies:
hash matches, `revoked_at IS NULL`, `expires_at > now`, within the 8h idle
window, and `users.is_active = 1`.

This preserves the independent database-backed second lock without making
FastAPI trust an upstream `sub` claim. A short-lived audience-bound assertion
would reduce exposure relative to forwarding the raw cookie, but by itself it
would also move the identity trust decision to Next.js. Wrapping the same
database handle in a second token adds expiry machinery without improving the
existing HMAC freshness boundary.

**The user id is never taken from a header, a body field, or a query
parameter.** It is derived from the session row. This is the same rule
`web/lib/auth/session.ts` states, enforced a second time in Python, so a bug or
compromise in the Next.js layer cannot by itself cause the backend to act on
the wrong account.

Additional hardening, all required:

- `/docs`, `/redoc`, and `/openapi.json` are disabled when `TL_ENV=production`.
  The OpenAPI document is generated in CI for type codegen, never served.
- No CORS middleware. The absence is asserted by a test.
- Request body cap (1 MB; uploads do not pass through the API).
- Per-user and per-IP rate limits on AI-invoking endpoints.
- HSTS, `no-store` on every authenticated response.
- Health endpoint is unauthenticated but reveals nothing beyond liveness.
- Structured logs never contain the session token, the service secret, the
  database URL, or presigned URLs.

A later hardening pass may add static-egress allowlisting if the Vercel plan
supports it. It is defense in depth, never the primary control.

### 2.2 Request lifecycle

1. Browser requests an app route or posts to a Next.js route handler.
2. Next.js validates the `tl_session` cookie (`authenticateWebsiteRequest`).
3. Next.js signs and forwards the call to FastAPI with both headers.
4. FastAPI verifies the signature, resolves the session to a `user_id`, opens a
   DB session, sets request-scoped context, and dispatches to a router.
5. The router calls one or more services with an explicit `user_id`.
6. The response is serialized through the strict encoder and returned.
7. Request-scoped context is reset in a `finally` block, always.

---

## 3. What stays, what is replaced

| Component | Fate |
|---|---|
| `src/tradelens/services/` (36 modules) | **Kept.** Signature hardening only (§4); no rewrites |
| `src/tradelens/db/` (models, session, Alembic) | **Kept unchanged.** One database serves both surfaces |
| `prompts/` | **Kept unchanged** — locked by project rule |
| 779 service/DB test functions (70 files) | **Kept unchanged.** Must stay green throughout |
| `src/tradelens/ui/pages/_archive/` (5 dead pages) | **Kept until Phase 10** — see the execution correction below |
| `src/tradelens/ui/` — `app.py`, 7 live pages, 25 components, `design_system.py` | **Deleted at Phase 10** |
| 1,280 Streamlit-coupled test functions (54 files) | **Retired at Phase 10** |
| Streamlit, Plotly, PyArrow | **Removed from `requirements.txt` at Phase 10** |
| `screenshot_service.py` local-disk writes | **Replaced** by the R2 adapter |
| Streamlit handoff path, `STREAMLIT_DOMAIN`, `open/restore/revoke_streamlit_session` | **Removed at Phase 10** |

**On preserving tests.** "Preserve the existing tests" can only mean the 779
service/DB tests. The other 1,280 encode Streamlit's own behaviour — `AppTest`
reruns, widget keys, CSS selector assertions — and have no meaning without
Streamlit. The golden parity harness (§8.2) replaces the confidence they
provided about metric correctness on real screens.

---

## 4. Tenant isolation hardening in the service layer

The API boundary is not the right place to fix this on its own. A guard in the
router protects only the paths someone remembered to guard; a service that
accepts a nullable owner remains a loaded weapon for every future caller,
including the worker and any script. The defaults are therefore removed at the
service layer, where the invariant belongs.

The current nullable-owner surface divides into three classes with different
severities and different fixes. Class A was mischaracterised during
brainstorming as covering `get_trade`/`update_trade`/`delete_trade`; it does
not. Those filter `Trade.user_id == user_id` and so fail closed. The audit
below is the accurate one.

### Class A — true cross-tenant reads (`None`/sentinel skips the filter)

| Function | Current behaviour | Fix |
|---|---|---|
| `trade_service.get_trades(user_id=_UNSCOPED)` | Default returns **every user's trades** | `user_id: int` required, keyword-only, validated positive |
| `trade_service.trade_hash_exists(trade_hash, user_id=None)` | `None` checks the hash across **all users** | `user_id: int` required |
| `trade_service.find_recent_duplicate(trade_data, user_id=None)` | `None` can return **another user's trade** | `user_id: int` required |
| `weekly.list_weekly_reviews()` | No user parameter; returns **all users' reviews** | Delete, **together with the two tests that exercise it** — see the execution correction below |

`find_recent_duplicate` is the sharpest of these: it returns a `Trade` object
belonging to whichever user happened to log an identical setup, and the New
Trade flow surfaces it to the current user.

### Class B — silent legacy-tenant fallback (`None` selects NULL-owner rows)

`get_trade`, `update_trade`, `delete_trade`, `weekly.get_weekly_review`,
`weekly.get_weekly_reviews`, `sample_data.count/clear/load_sample_trades`,
`csvio.import_trades_csv`.

These fail closed for a real user, but a `None` arriving by mistake reads or
writes the legacy NULL-owner tenant instead of raising. Fix: `user_id: int`,
required, no default, validated by the shared guard.

### Class C — attribution hole

`cost.log_ai_usage(user_id=None)` writes an unattributed `ai_usage_log` row.
Not a leak; a hole in per-user cost tracking, which the Settings cost view
depends on. Fix: require `user_id`.

### Shared guard

```python
def require_user_id(value: object) -> int:
    """The owner of a request. Never None, never a bool, always positive."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("user_id must be a positive integer")
    return value
```

Already the pattern in `delete_all_trades`, `strategy._require_concrete_user_id`,
`cost._require_concrete_user_id`, and `app_settings._require_concrete_user_id`.
This centralises it.

### Admin/global access

**None is created.** The one candidate did not survive contact with the code:
`scripts/recompute_metrics.py` declares `recompute(user_id: int)` and then calls
`get_trades()` unscoped, so it recomputes one user's stored metrics from every
user's trades. That is a defect, not a legitimate need for global access — the
fix is `get_trades(user_id=user_id)`. With it scoped, nothing anywhere wants an
`iter_all_trades_for_maintenance`, and YAGNI says do not build one.

An import-boundary test still asserts no module under `src/tradelens/api/`
imports any `*_for_maintenance` / `*_all_users` symbol, so one cannot appear
later without review.

### Sequencing constraint

This lands in **Phase 0**, before any endpoint exists, and touches code
Streamlit still runs. The full Python suite must be green afterward, and
archived pages under `ui/pages/_archive/` are deleted rather than updated.

---

## 5. Request-scoped user context

`corrections.py` scopes reads and writes through a `ContextVar` so that
`ai_client`'s few-shot injection — which has no user argument — cannot mix one
trader's corrections into another's prompt. That mechanism is kept, and made
safe for a server:

1. **Explicit passing is preferred.** Every call site inside `src/tradelens/api/`
   passes `user_id` explicitly to `record_correction`, `count_corrections`,
   `repeated_corrections`, and `get_recent_corrections`. The ContextVar exists
   only for the indirect `ai_client` path.
2. **Set and reset with the token, always.** The dependency does
   `token = _ACTIVE_USER.set(uid)` and `_ACTIVE_USER.reset(token)` in a
   `finally`. Never a bare `.set()` — under FastAPI's threadpool, a leaked value
   can be observed by a later request on the same worker.
3. **The default becomes a refusal, not a fallback.** After Phase 0 the
   ContextVar default is a sentinel; `_resolve_user` raises if nothing set it
   rather than silently resolving to the legacy NULL tenant.
4. Tests: the var is unset after a request completes, including when the handler
   raises; and an `ai_client` call made with no context set raises rather than
   defaulting.

---

## 6. Screenshot storage (Cloudflare R2)

The bucket is private. No public access, no bucket listing, no static website
endpoint.

**Object keys** are unguessable and owner-encoded:
`u/{user_id}/t/{trade_id}/{uuid4}.{ext}`. The client-supplied filename is never
used in the key; it is stored as a display-only column.

**Upload — presigned PUT, ≤ 5 minutes.**
- Issued only for an authenticated user, only for a `trade_id` that user owns.
- Content-Type allowlist enforced *in the presign policy*, not merely checked:
  `image/png`, `image/jpeg`, `image/webp`. No SVG.
- Uploads land under `quarantine/u/{user_id}/t/{trade_id}/{uuid4}.{ext}`. That
  namespace is never eligible for a download presign or database persistence.
- R2 presigned PUT does not support a maximum-size range condition. The client
  receives a 10 MB advisory cap; finalization reads at most 10 MB + 1 byte and
  rejects a missing, empty, or oversized object before decoding it.
- The key is generated server-side and returned with the URL; the client cannot
  choose where its bytes land.

**Download — presigned GET, ≤ 5 minutes.**
- Ownership is verified against the database before any URL is signed: the
  screenshot row's trade must belong to the requesting user.
- URLs are never logged, never cached, never embedded in a server-rendered page
  that could be shared.

**Server-side validation before any AI processing.** A presigned upload means
the object arrived without passing through application code, so it is untrusted
until proven otherwise. Before the object is read by `vision.py`:

1. Fetch server-side and verify **magic bytes** match the declared type.
   A client-declared Content-Type is a claim, not evidence.
2. Decode with Pillow under a decompression-bomb guard
   (`Image.MAX_IMAGE_PIXELS`), rejecting anything that fails to decode.
3. Enforce dimension caps and reject multi-frame/animated payloads.
4. Re-encode to a fresh normalised PNG, stripping EXIF and any trailing bytes.
   This defeats polyglot files and removes location metadata a trader did not
   intend to upload.
5. Write the result under a fresh `u/{user}/t/{trade}/{uuid}.png` key. Only that
   returned final key may be persisted or signed for display. The quarantine
   object is discarded on success and content rejection.

`ai_screenshot_service.py`'s existing URL path keeps its SSRF protections
(`_is_public_url`, no-redirect handler, extension check) and gains the same
post-fetch validation.

**Retention and deletion.** The R2 adapter exposes owner/trade-key-validated
deletion. The future API/account deletion paths must invoke it before the R2
feature ships; the legacy local-disk deletion helpers do not delete R2 objects.

**Migration.** Files under `data/screenshots/` are uploaded to R2 with rewritten
`file_path` values. Files referenced by a row but absent from disk — expected,
since Streamlit Cloud's disk is ephemeral — are marked missing, and the UI shows
a designed "chart no longer available" state rather than a broken image.

---

## 7. Migration phases

Each phase ends with: tests green, parity harness green for the surfaces it
covers, handoff document updated, Codex review requested.

| # | Phase | Contents |
|---|---|---|
| 0 | **Foundations** | Service-layer isolation hardening (§4) · request context (§5) · FastAPI skeleton with both locks · strict serializer · OpenAPI→TS codegen · R2 adapter + validation pipeline · `ai_jobs` table, worker, idempotency · per-user `app_surface` flag · golden parity harness |
| 1 | **Shell & navigation** | Unified design tokens across marketing and app · six routes · sidebar · top bar · Partner drawer shell · loading/empty/error primitives · mobile bottom nav · focus and keyboard model |
| 2 | **Overview** | KPI row · today/week P&L · risk & discipline · performance trajectory · recurring edge · trading-days calendar · next review action · recent trades · low-sample states |
| 3 | **Trades + Trade Detail** | URL-state filter bar · table · calendar view · `/trades/[id]` as a route · inline edit · delete with confirmation · screenshot view · AI summary of a filtered set |
| 4 | **New Trade** | Single dense form · presigned upload · background autofill · per-field accept/reject · draft autosave · duplicate detection · outcome/P&L contradiction block |
| 5 | **AI analysis** | Screenshot analysis · journal generation · grading — job-backed with progress and retry |
| 6 | **Analytics** | Four lenses · visx charts · evidence narratives · confidence and sample-size language |
| 7 | **Strategy Profile** | Sections · starter playbook · completion progress · AI-appended insights |
| 8 | **AI Partner** | Streaming drawer · context scoping · evidence sources · history trim · scope guard · image attach |
| 9 | **Settings** | Recovery email · timezone · CSV import/export · sample data · delete all trades · delete account · cost by feature |
| 10 | **Retirement** | Flip default · remove toggle · delete `ui/` · retire UI tests · drop dependencies · decommission Streamlit Cloud |

**One plan per phase.** This spec is too large for a single implementation plan.
Each phase gets its own plan document written immediately before it is built, so
later phases are planned with what the earlier ones actually taught us. Phase 0
is planned first; a phase is not planned until its predecessor is complete and
reviewed.

**Cutover.** A per-account `app_surface` flag routes the post-login destination.
Both surfaces read one database, so there is no migration and no dual write.
Default flips when §9 is satisfied; the flag is then removed.

---

## 8. Feature inventory

Nothing below may be dropped without an explicit, recorded decision.

**Overview** — KPI row (net P&L, win rate, expectancy, profit factor, trades) ·
today P&L · this-week P&L · max drawdown · rule adherence · edge leak ·
consistency score · equity curve · current/best streak · average win · average
loss · killzone performance · setup performance · trading-days calendar ·
activation next-step · recent trades · filter panel · low-data states.

**Journal / Trades** — date range · asset · session · setup filters · trades
table (date, asset, session, setup, result, P&L, R, grade, screenshot) ·
calendar month view · open-from-day · trade detail · AI summary of the filtered
set · edit · delete with confirmation · per-trade screenshot upload.

**New Trade** — upload or image URL · quality check · AI analysis · autofill
review per field · trade date · entry time · session auto-detect · asset ·
timeframe · HTF bias · LTF bias · setup model · evidence · confirmation text ·
followed-rules (yes/no/partial) · result · P&L · risk · position size · R
multiple · exact price levels · reflection notes · emotion log (before/during/
after) · mistake tags · completeness warnings · draft persistence · duplicate
detection · outcome/P&L contradiction block.

**AI Reviews** — Patterns (candidates, cards, confidence, evidence, sample size,
next review action) · Weekly Recap (week selector, generate, retry, validated
sections) · Daily Debrief (day selector, five sections) · read-full-note
disclosure.

**Analytics** — date range · asset/session/strategy filters · four lenses
(Performance, Risk, Timing, Setups) · equity curve · daily P&L · drawdown
series · R-multiple distribution · by day of week · by session · by strategy ·
by timeframe · by asset · by setup type · emotion vs RR · by hour of day ·
killzone performance · confirmation-model performance · mistake frequency ·
total edge leak · rule adherence · consistency score · trade of the week ·
period deltas · evidence narrative per lens.

**Strategy Profile** — identity (name, style) · markets · timeframes · entry
rules · exit rules (stop, target) · risk rules · setups · mistakes to avoid ·
active strategy · ICT/SMC starter playbook · sections-written progress · skip
path · AI insight append.

**AI Partner** — global chat · per-trade chat · journal-grounded context ·
evidence sources · history trimming · scope guard · image attachment.

**Settings** — recovery email · timezone · API-key guidance · CSV export · CSV
import · load sample trades · clear sample trades · delete all trades · delete
account · monthly cost by feature · demo banner.

**Cross-cutting** — onboarding gate · strategy gate · activation status ·
corrections capture feeding few-shot · AI usage and cost logging · `DEMO_MODE` ·
low-sample confidence policy · reflection-only safety language (never signals,
predictions, or advice).

---

## 9. Risks and edge cases

**Severe**

1. **Cross-tenant leak.** Addressed at the service layer (§4), plus a
   route-walking test asserting every registered route resolves an owner from
   the session, plus Codex review on each phase.
2. **Correction context bleed.** Addressed by §5; tested for reset-on-exception.
3. **Serialization drift.** `profit_factor` renders as `∞` today. JSON has no
   `Infinity` or `NaN`; pandas produces both, plus numpy scalars and `Decimal`.
   A silent coercion to `null` becomes a wrong number on screen. One strict
   encoder, an explicit sentinel for undefined values, tested against empty,
   single-trade, all-win, and all-loss datasets.
4. **Untrusted uploads reaching AI.** Addressed by §6's validation pipeline.

**Material**

5. **Double AI spend** from strict-mode double-invocation, proxy retries, or job
   re-runs. Mitigated by a uniquely-constrained idempotency key per job.
6. **Missing screenshot history** — most Streamlit Cloud files are already gone.
   Designed missing state, not a broken image.
7. **Two surfaces during parity.** Shared database makes records consistent;
   wizard drafts do not cross over and must not be claimed to.
8. **Streaming through the proxy.** Requires explicit `maxDuration` and a
   stream-through route handler; a naive proxy buffers and destroys the effect.
9. **Neon scale-to-zero** cold start on the first request after idle.
10. **Palette seam** — marketing `#0d1117` vs app `#091216`. One token set,
    unified in Phase 1.
11. **Secrets relocation** — `ANTHROPIC_API_KEY` moves from `st.secrets` to
    container environment. `resolve_anthropic_key()` reads env first, so this
    works, but must be verified before Phase 5.
12. **Service secret rotation** — `TL_SERVICE_SECRET` must be rotatable without
    downtime; the backend accepts a current and a previous secret during a
    rotation window.

---

## 10. Testing and verification

**10.1 Existing suite.** The 779 service/DB tests stay green from Phase 0 to
Phase 10. Any failure is a migration defect, not an intended change.

**10.2 Golden parity harness** (`tests/parity/`). One seeded, fixed dataset.
Every public metric and service output is snapshotted, and each API response is
asserted equal to the service output for the same input. Numeric drift fails CI.
This is what replaces the retired UI tests.

**10.3 Tenant isolation matrix.** For every route: user A receives 404/403 on
user B's trade, analysis, weekly review, strategy, setting, screenshot, and job.
Plus a route-walking test that fails when a new route is added without an owner
dependency, and the import-boundary test from §4.

**10.4 Security tests.** Missing/expired/out-of-scope signature rejected · revoked
session rejected · idle-expired session rejected · inactive user rejected · no
CORS header emitted on any response · `/openapi.json` absent in production mode ·
presigned GET refused for a non-owner · oversized and wrong-MIME uploads
refused · a renamed non-image refused by magic-byte validation.

**10.5 Serialization edge tests.** Empty dataset · one trade · all wins · all
losses · infinite profit factor · NaN R-multiple · missing timestamps ·
timezone-naive vs aware.

**10.6 Frontend.** Vitest for `lib/` and components. Playwright E2E per section
against `DEMO_MODE=true`, at desktop and 375px.

**10.7 CI gates.** `ruff` · `black` · `pytest` · `tsc --noEmit` · `vitest` ·
`playwright` · OpenAPI codegen drift check (a regenerated client that differs
from the committed one fails the build).

---

## 11. Criteria for retiring Streamlit

All eight must hold. No partial retirement.

1. Every item in §8 is implemented in the new app and checked off.
2. Golden parity harness green — zero numeric drift.
3. Playwright E2E green across all sections, desktop and 375px.
4. Every Codex phase review closed, with no open security finding.
5. The owner has used the new app for one full week on real trades, including at
   least one weekly recap and one screenshot autofill.
6. All beta accounts on the new surface for two consecutive weeks with no
   recorded fallback to Streamlit.
7. Screenshots migrated to R2 and verified readable; missing-file states behave
   as designed.
8. `scripts/verify_public_funnel.py` passes against the new app origin.

Then: delete `src/tradelens/ui/`, retire the 1,280 UI-coupled tests, remove
Streamlit/Plotly/PyArrow from `requirements.txt`, remove `STREAMLIT_DOMAIN` and
the Streamlit handoff path, and decommission the Streamlit Cloud deployment.

---

## 12. Design direction

Dark, dense, and instrument-like. The reference dashboard supplied by the owner
is correct about **information density and composition** and wrong about
**palette and personality**: the target is that level of structure wearing
TradeLens's teal-on-charcoal identity.

- **Palette.** One unified token set across marketing and app. Charcoal
  surfaces, a single teal accent, semantic green/red. Teal coverage reduced to
  primary action plus one active state per viewport.
- **Typography.** Schibsted Grotesk (display), Satoshi (body), JetBrains Mono
  (metrics, dates, compact metadata only — never prose).
- **Hierarchy.** The weakest item in the current app (6.5/10). Multi-column
  composition replaces the single-column stack of full-width bands.
- **Motion.** Purposeful only: state transitions, drawer, streaming text,
  optimistic feedback. No ambient drift, no card-by-card reveals.
- **Mobile.** Phone-first for the daily loop (log, overview, browse, read a
  review); desktop-first for Analytics and Strategy editing.
- **Invisible quality.** Real empty, loading, and error states everywhere.
  Keyboard navigation throughout. WCAG AA contrast, verified.

Applied during implementation via these skills, in this order of authority:

| Owner's name for it | Skill invoked | Scope |
|---|---|---|
| frontend-design | `frontend-design` | Architecture, components, layout, visual system |
| UI/UX Max Pro | `ui-ux-pro-max` | UX and dashboard decisions, alongside the above |
| Emily Design | `emil-design-eng` | Motion, transitions, animation |
| Impeccable | `impeccable` | Final premium SaaS/fintech polish, consistency, originality |

---

## 12b. Execution corrections (2026-08-16)

Verified against the code while executing Phase 0. Where §3–§11 above disagree with this
section, **this section wins.**

- **The archived pages stay until Phase 10.** §3 originally deleted
  `ui/pages/_archive/` in Phase 0 because its unscoped `get_trades()` calls were said to
  block §4. They do not: those calls sit in three files no test executes, and Streamlit
  cannot route into subdirectories of `pages/`. Nine passing tests read the archived
  files' source, so deleting them costs real coverage and buys nothing. They go when
  `src/tradelens/ui/` goes.
- **No admin/global helper exists** — see §4's rewritten *Admin/global access*.
- **`weekly.list_weekly_reviews` deletion takes two tests with it.** The claim that it had
  no live caller was wrong: `tests/test_weekly.py:269-280` exercises it and asserts it
  returns every user's reviews. Those are tests of the cross-tenant behaviour being
  removed, so they are deleted with the function rather than preserved.
- **Golden-dataset encodings were wrong** (§10.2's harness): `"Break-even"` is rejected by
  `trade_validation.VALID_OUTCOMES` (only `win`/`loss`/`breakeven`), and
  `Trade.followed_rules` is an `Integer` storing `1`/`0`/`None`, not `"Yes"`/`"No"`/
  `"Partial"`. The harness frame must also carry `killzone`.
- **Phase 0 is based on the Codex website/auth security remediation** (`c69d84b`), which
  landed as its own commit before this work. Its change to `web/lib/auth/session.ts` is
  cookie-parsing robustness only; the five session conditions §2.1's Lock 2 mirrors are
  unchanged.
- **Local development runs Python 3.9.6**; CI and `Dockerfile.api` remain the 3.11 gates.

## 13. Coordination

`docs/coordination/CLAUDE_CODEX_HANDOFF.md` is updated at every phase boundary
with: architectural decisions made, work completed, tests added and their
status, risks discovered, and the specific items Codex should independently
review — with security and tenant isolation named explicitly on every phase that
touches a service, a route, or a credential.
