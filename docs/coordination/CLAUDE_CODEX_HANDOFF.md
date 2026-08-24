# Claude Code ↔ Codex Handoff

This file is the shared source of truth for the full-dark Streamlit redesign.
Both tools must read it before starting a phase and update the handoff section
before changing ownership.

It is a coordination contract, not automatic inter-process communication and
not a substitute for Git. Claude Code and Codex must not edit this worktree at
the same time.

---

# ⚠️ OPEN PRE-DEPLOYMENT GATES — NOT COMPLETED

**Owner-approved Phase 0 checkpoint, 2026-08-18.** CI run `32170167686` on `8672c36` is
green and Codex's review fixes at `44f4bb5` are accepted. Green CI does **not** clear the
three gates below. They are pre-deployment gates, not Phase 1 planning items, and none has
been run. **Do not describe any of them as done until it has actually been executed and its
real output recorded here.**

| # | Gate | Status | Why it cannot be closed yet |
|---|---|---|---|
| 1 | `Dockerfile.api` build + FastAPI startup/health smoke test (`/health` and an authenticated `whoami`) | **NOT RUN** | Docker is unavailable in the development environment. The image has never been built or booted anywhere. |
| 2 | Disposable PostgreSQL migration upgrade/downgrade verification | **NOT RUN** | Only SQLite has been exercised. `TRADELENS_PG_TEST_URL` is absent, so the Postgres suite skips. |
| 3 | Real PostgreSQL concurrent AI-job enqueue/claim verification | **NOT RUN** | Two true thread races pass against SQLite; exclusivity under Postgres connection pooling is unproven. |

Deployment configuration that also remains unproven from Git: use Neon's direct/unpooled URL
for Alembic and the pooled endpoint at runtime; keep Production and Preview on separate Neon
branches, API origins and service secrets; configure exact-origin R2 bucket CORS, never `*`.

---

## Current website security review — 2026-08-16 (Codex)

**Workspace:** `/Users/ayoub/tradelens-ai`, branch `main`, starting HEAD
`bf7fb33`. These changes are uncommitted. The pre-existing modification to
`.claude/settings.json` is unrelated and was not touched by this review.

**Scope:** independent second-lens review of the completed Next.js marketing,
authentication, protected transition, Vercel, and Neon auth integration only.
The Streamlit journal and the in-progress Streamlit → Next.js/FastAPI migration
were deliberately not reviewed or modified.

### Confirmed findings and fixes

- **High — rate-limit enforcement could be bypassed.**
  `web/lib/auth/rate-limit.ts` performed a separate count and later insert, so
  concurrent requests could all pass below the threshold. Signup recorded bad
  invite attempts under `invite` but never checked the `invite:ip` rule, making
  invite guessing effectively unlimited. Attempt admission is now one
  transaction protected by a per-bucket/action Postgres advisory lock, with the
  attempt reserved before work proceeds. Signup checks the invite-specific
  bucket. All auth routes were changed to avoid double-recording and to clear
  failures-only reservations only after success. Targeted tests first failed
  against the old implementation and now pin lock → count → insert order and
  invite rejection at 429.
- **Medium — bcrypt password aliases above 72 UTF-8 bytes.**
  Signup/reset accepted passwords longer than bcrypt's effective input, so two
  different strings sharing the first 72 bytes authenticated as the same
  password. `web/lib/auth/contract.ts` now rejects values above 72 UTF-8 bytes
  while retaining the 12-character strength rules, and both signup and reset
  share that contract. Existing long legacy passwords remain usable at login.
- **Medium — concurrent verification/reset issuance could leave two live
  tokens.** A transaction did not serialize two update-then-insert issuers that
  both initially saw no live token. `web/lib/auth/verification.ts` and
  `web/lib/auth/password-reset.ts` now lock the owning `users` row before
  superseding and inserting. Regression tests require the row lock.
- **Low — database connection failures escaped the sanitizer.**
  `pool().connect()` occurred before `transaction()`'s catch boundary; raw
  driver errors can include hosts, statements, or credentials. Connection,
  statement, commit, and rollback failures now leave `web/lib/db/client.ts` as
  sanitized `DatabaseOperationError`s. Only the non-secret Postgres error code
  is retained, which also fixes `web/lib/auth/signup.ts` incorrectly mapping
  every transaction failure to `duplicate_email`.
- **Low — `/login` froze runtime signup configuration.** The page read
  `SIGNUP_MODE` while being statically prerendered. The live deployment returned
  `x-nextjs-prerender: 1` / `x-vercel-cache: PRERENDER`; changing the environment
  could therefore leave the wrong signup link until a redeploy. The page is now
  `force-dynamic`; the verified production build classifies it dynamic and a
  local production response returns `Cache-Control: private, no-cache,
  no-store`.
- **Low — malformed cookie encoding produced a 500.** Protected pages and
  logout called `decodeURIComponent` directly on attacker-controlled cookie
  text. All website-session parsing now uses one fail-closed helper and returns
  logged-out state for malformed encodings.
- **Low — the web quality gate was nonfunctional.** Next.js 16 removed
  `next lint`, but `web/package.json` still invoked it; the repository CI ran
  only Python checks. ESLint 9 flat configuration and the Next core-web-vitals /
  TypeScript rules are installed, and `.github/workflows/ci.yml` now tests,
  lints, typechecks, builds, and audits the deployed web application on Node 22.
- **Low — published privacy/account statements contradicted the shipped
  product.** The policy said email was optional, claimed no name or DOB was
  collected, said the site used no cookies, and described signed sessions. The
  copy now accurately describes required verified email, collected signup
  fields, opaque hashed sessions, the HttpOnly website cookie, and the beta
  journal URL credential. Visual structure and styling were not changed.
- **Hardening — Vercel/Neon pool lifecycle.** `web/lib/db/client.ts` now calls
  Vercel's `attachDatabasePool` so Fluid Compute drains idle `pg` connections
  before suspension. Production and full dependency audits report zero known
  vulnerabilities.

No authentication/session bypass, cross-user ownership path, open redirect,
SQL interpolation, client-exposed secret/unsafe `NEXT_PUBLIC_*`, token replay
gap, or private-response caching issue was confirmed in the reviewed website
code. Website tokens are 256-bit random opaque credentials, stored only as
domain-separated hashes, and protected by HttpOnly/Secure/SameSite=Lax cookies;
the central lookup rechecks surface, revocation, absolute expiry, idle expiry,
and active-user state. Reset consumes atomically and revokes all sessions and
handoffs. Handoffs are server-destination-only, 120-second, one-time tokens.

### Verification

- Web: `388 passed` across 19 Vitest files; ESLint clean; `tsc --noEmit` clean.
- Production build: Next.js 16.3.0 compiled and typechecked successfully; all
  auth APIs plus `/login`, `/signup`, `/verify-email`, `/reset-password`,
  `/onboarding`, and `/continue` are dynamic. Only the public forgot-password
  shell and 404 are static.
- Cross-runtime/site checks: `167 passed, 4 skipped` across policy, funnel,
  auth-contract, handoff, and session suites.
- `npm audit` and `npm audit --omit=dev`: zero vulnerabilities.
- Client chunk scan: no database/invite/SMTP secret names or private test
  credential fixtures. Tracked-history secret-shape scan found placeholders and
  test fixtures only; no committed live secret was identified.
- Live read-only checks before the fix: homepage and login responded 200 with
  HSTS, frame denial, no-sniff, no-referrer, and Permissions-Policy; auth GET
  endpoints refused unsupported methods. The live `/login` cache defect remains
  until these changes are deployed.
- `git diff --check` clean. No deploy, database write, migration, commit, push,
  or modification to Streamlit migration-owned files was performed.

### Remaining risks and instructions for the SaaS migration

- Vercel project/dashboard state is not fully represented in Git. Before any
  deploy, manually confirm Framework=Next.js, Root Directory=`web`, Production
  `SITE_ORIGIN`/`APP_ORIGIN`/SMTP/invite settings, and that Preview uses an
  isolated Neon branch rather than production credentials. Environment changes
  cannot be inferred from source review alone.
- Add a nonce/hash-based Content-Security-Policy after inventorying Next inline
  scripts and the externally hosted fonts. Existing clickjacking, MIME, HSTS,
  referrer, and permission headers are present; CSP remains the main browser
  hardening gap.
- Normal sign-out revokes only the credential for the current surface. Password
  reset and the explicit all-session operation revoke website and Streamlit
  sessions together. Preserve that distinction in UI copy and migration APIs,
  or deliberately change it with tests.
- Do not carry the beta Streamlit URL-session pattern into the Next.js/FastAPI
  SaaS architecture. Keep browser sessions in Secure HttpOnly cookies and make
  any cross-service exchange single-use, audience-bound, short-lived, and
  server-redeemed. Avoid tokens in URLs, logs, analytics, or client-visible
  error objects.
- Preserve the central authorization invariant: identity comes only from the
  validated session; every user-owned query must derive `user_id` from that
  server context. Do not accept browser-supplied user IDs as ownership proof.
- Reuse the shared password contract, atomic attempt reservation, user-row
  serialization for one-live-token issuance, domain-separated credential
  hashes, and reset-time global revocation. Do not reimplement weaker FastAPI
  variants beside them.

## Canonical workspace

- Worktree: `/Users/ayoub/tradelens-ai/.claude/worktrees/codex+full-dark-streamlit-redesign`
- Branch: `codex/full-dark-streamlit-redesign`
- Current base: `origin/main` at `cfdb775`
- Marketing site: out of scope except for the separately approved Higgsfield
  playback correction during the motion phase.
- Push, merge, and deployment: prohibited until the user explicitly approves.

## Current handoff state

- **Active writer:** `NONE`
- **Phase:** `FINAL EVIDENCE CORRECTED — AWAITING OWNER REVIEW`
- **Phase 2:** APPROVED at `7ffd9a1`.
- **Phase 3:** APPROVED at `2c29a20`.
- **Phase 4:** APPROVED at `6b3d33c`; independently re-reviewed through
  `ad8a8ce`, with the review-contract correction committed at `6f08590`.
- **Authentication bypass:** CLOSED at `950bc8f`.
- **DATABASE_URL disclosure:** CLOSED at `7c046fc`.
- Verification: fresh final full suite `2176 passed, 7 skipped`; Ruff, Black
  (221 files), `git diff --check`, and the protected-boundary diff are clean.
  The 40-row browser matrix passed at 1440, 1024, genuine coarse 768, genuine
  coarse 375, and reduced-motion 1440: zero exceptions, overflow, undersized
  visible targets, opaque stale-light surfaces, contrast flags, demo/date/copy/
  label/icon defects, or hidden AI usage. The ready-owner Partner presentation
  was exclusive at every applicable responsive configuration; availability
  states are covered separately by tracked tests. All 13 destination/
  presentation artifacts were re-inspected.
- Final evidence correction: `107 passed` across capture, cleanup,
  contradiction, and marketing-site tests; Ruff clean; Black clean (221
  files); 80 audit links parsed, with all 78 local targets tracked and no
  ignored `.superpowers` reference; the live read-only contradiction audit
  found no contradictory record; `git diff --check` and the protected-boundary
  diff are empty.
- **STILL REQUIRED FROM THE OWNER — deployment secret check.** Not doable from
  this worktree. share.streamlit.io → the TradeLens app → **Settings →
  Secrets** → confirm whether `TRADELENS_USERNAME` and `TRADELENS_PASSWORD`
  are present and non-blank. Either answer is safe now; if they were UNSET
  before `950bc8f`, the previously committed demo pair was live on the public
  deploy and must be treated as a disclosed credential and rotated wherever it
  was reused.
- **Next owner:** **`OWNER`**.
  Not pushed, not merged, not deployed. The password-strength feature is not
  started and the branch is not finished.
- **Next action:** Review
  `docs/superpowers/audits/2026-08-09-priority-remediation-review.md` and decide
  whether to finish, push, or deploy the branch.

## Final evidence correction — 2026-08-09

**Commit:** this commit, `docs(audit): make final evidence durable`. The writer
lock is released to `NONE`; the owner decides whether to finish, push, or deploy
the branch.

The committed audit now embeds the browser matrix, keyboard accounting,
ready-owner responsive Partner exclusivity and `0 → 0` usage observation,
artifact inspection, and probe qualifications that previously depended on an
ignored local report. Every committed audit link now resolves to a tracked
test, asset, or document. Ownerless, AI-unavailable, no-trades, and no-profile
Partner states are cited as tracked behavioral-test evidence rather than
misreported as live matrix states.

The audit now distinguishes the 13 retained destination/presentation images
from key-state coverage. It states that 1024, coarse 768, and reduced-motion
results have no retained pixels; the 375 image is Partner only; the AI Reviews
Evidence Rail is below the retained crop; and alternate Journal, Analytics, AI
Reviews, Strategy, and Partner states are behavioral-test rather than retained
visual evidence. Mobile claims are qualified as Chrome-emulated geometry and
behavior rather than a physical-device, assistive-technology, or complete
mobile screenshot pass.

The Overview marketing `alt` now names the pixels actually retained: masthead,
KPI/risk bands, and the opening equity trajectory. The imagery score remains
7.5 only because the four refreshed marketing stills are relevant, legible,
coherently seeded, production-only, clean of capture chrome, and accurately
described after this correction. It is capped there because they remain
repeated full-shell views, the Overview trajectory is only partly in frame,
and none is a distinct editorial composition. The exact subtotal is
`8.5 + 8.5 + 9.0 + 8.5 + 7.5 + 7.5 + 8.0 + 7.5 = 65.0/80`.

**Verification:** focused capture, cleanup, audit-contradiction, and marketing
site suites passed `107/107`; Ruff reported all checks passed; Black reported
221 files unchanged. The audit link checker parsed 80 Markdown links, verified
all 78 local targets exist and are tracked, and found no ignored
`.superpowers` reference. The read-only contradiction command reported `No
contradictory records. Stored outcomes all match their P&L.` `git diff --check`
and the exact protected diff from `63421f7` across AI routing, Partner safety,
database, authentication, migrations, and Streamlit config were empty.

Only `docs/superpowers/audits/2026-08-09-priority-remediation-review.md`,
`site/index.html`, and this handoff changed. No image pixels, product code,
service, auth, schema, database, marketing layout, push, merge, deployment, or
branch-finish action changed. No new browser matrix was needed because this is
an evidence-text and accessible-description correction; the retained Overview
asset was re-opened at original detail to confirm the amended description.

## Priority-remediation execution checkpoint — 2026-08-09

- Plan: `docs/superpowers/plans/2026-08-09-dark-workspace-priority-remediation.md`.
- Starting product HEAD: `63421f7`.
- Scope: repair demo data coherence, Journal presentation, ownerless Partner
  truthfulness, Strategy onboarding, AI Review date selection, terminology and
  structural-icon residue, then capture clean product screenshots and re-score
  the 10K checklist.
- Workflow: Superpowers subagent-driven development. Each numbered task gets a
  fresh implementer, a separate spec-and-quality reviewer, focused tests, a
  commit boundary, and a ledger entry before the next task starts.
- Boundaries remain unchanged: no push, merge, deployment, authentication or
  database-schema changes, AI routing/prompt changes, tenant-scope changes,
  secret changes, JavaScript injection, React surface, or new dependency.
- The owner's deployment-secret check remains required before deployment; it
  does not block local remediation work.

### 2026-08-09 — Priority remediation Task 1 implementation (Codex)

**Commit:** `a59839ac85a92b039e7a2fad3c0040dc3211f1de`,
`fix(demo): bound sample data to one coherent account`.
Task 1 only; Task 2 not started.

`get_demo_df(*, as_of=None)` now generates exactly 60 weekdays ending no later
than its anchor. Its row contents and schema retain the existing index-driven
distribution, while the dates are deterministic for a supplied anchor and the
default anchor is the current local date.

The complete ICT/SMC starter profile and six-section completion rule now live
in the pure `components/strategy_profile.py`. The Strategy page imports the
immutable mapping and completion function; the screenshot capture imports a
fresh dict fixture directly instead of parsing an executable Streamlit page's
AST. Completion matches the page's actual grouping: Identity is the required
name, Exit accepts either stop or take-profit rules, and Setups includes the
stored news/session rule.

**TDD evidence:** the two time-anchor tests first failed with `TypeError:
get_demo_df() got an unexpected keyword argument 'as_of'`; the shared-profile
tests first failed because the component did not exist; the screenshot-reader
contract then failed while AST extraction remained. Each passed after its
minimal implementation.

**Verification:** focused Task 1 suites `231 passed`; capture lifecycle
`23 passed`; Ruff clean; Black clean; `git diff --check` clean. The fresh full
baseline before Task 1 was `2129 passed, 7 skipped`; it was not repeated for
this bounded task. No browser run was required because no rendered composition,
copy, or styling changed. No auth, schema, AI routing/prompt, tenant, secret,
marketing-site, or dependency file changed.

**Deviation from the illustrative plan:** `SECTION_FIELDS` preserves the
page's real six-section semantics instead of the sketch's looser Identity and
Setups groups. Dedicated tests pin `trading_style` alone as incomplete Identity
and `news_session_rules` as completing Setups.

### 2026-08-09 — Priority remediation Task 1 review-test amendment (Codex)

**Code commit:** `05dc3b0c90d682161568bc9115b25c2a68cd87ca`,
`test(demo): pin task one regression contracts`. Task 2 remains unstarted.

The amendment adds behavioral protections the independent review found
missing: the no-argument demo call cannot return dates later than today; the
ordered 32-field legacy row schema is exact; and the deterministic result split
is exactly 33 Wins, 21 Losses, and 6 Breakevens. It also compares every subset
of the nine persisted completion fields to an independently expressed six-group
reference, uses blank values for unset fields, and specifically requires Risk
and Self-Awareness to count once each.

**Mutation evidence:** the exact demo mutation (future default anchor, seven
metadata fields removed, and 59/1 collapsed Win/Loss results) made all three
new demo tests fail. The exact completion mutation (Risk omitted and
Self-Awareness duplicated) made both the exhaustive matrix and the targeted
Risk/Self-Awareness test fail. Production files were restored unchanged after
each temporary mutation.

**Verification:** `pytest tests/test_demo.py tests/test_page_polish.py
tests/test_premium_page_contracts.py -q` → `239 passed`; Ruff clean; Black
clean; `git diff --check` clean. The test-only amendment changed no production,
auth, schema, AI-routing/prompt, tenant, secret, dependency, capture, or
marketing-site file. No browser run was needed because no rendered behavior
changed. See the complete fix report at
`.superpowers/sdd/2026-08-09-dark-workspace-priority-remediation/task-1-fix-report.md`.

### 2026-08-09 — Priority remediation Task 2 implementation (Codex)

**Commit:** this commit, `fix(journal): present demo trades as a real ledger`.
Task 2 only; Task 3 not started.

The pure `components/ledger.py` now owns the result-mark vocabulary and money
formatter used by the real Journal, plus `demo_ledger_frame`, which presents
the coherent Task 1 sample account with human labels, signed currency, R-unit
suffixes, result glyphs, and deliberate missing-value placeholders. The empty
demo Journal routes those transformed rows through the same neutral row styler
as the real ledger and identifies them as the shared sample account.

The real row builder changed only at its shared mark and money references.
`ids`, `labels`, `journal_table`, single-row selection, `_open_trade`, the
pending-view intent, and the Trade Detail transition are unchanged. The demo
branch's local `_DEMO_COLUMNS` schema rename is removed.

**TDD evidence:** the two behavioral presentation tests first failed with
`ImportError: cannot import name 'demo_ledger_frame'`; the other 136 premium
contracts passed in that red run. After the pure transformation and page
wiring were added, the focused Task 2 suites passed `290/290`. The tests read
the transformed DataFrame directly and pin raw `ny_am` → `New York AM`,
`1234.5` → `$1,234.50`, R suffixes, result glyphs, missing values, and exact
column order; the source check supplements that behavior by guarding only the
demo-branch routing and removal of `_DEMO_COLUMNS`.

**Verification:** `pytest tests/test_premium_page_contracts.py
tests/test_page_polish.py tests/test_pages_boot.py -q` → `290 passed`; Ruff
clean; Black clean; `git diff --check` clean. No browser run was required by
the bounded Task 2 brief; the real Journal selection/detail subprocess flows
and all page-boot states are included in the focused suites. No authentication,
database-schema, AI service/routing/prompt, tenant, secret, dependency,
marketing-site, or coordinator-owned SDD ledger file changed.

### 2026-08-09 — Priority remediation Task 3 implementation (Codex)

**Commit:** this commit, `fix(partner): make preview availability truthful`.
Task 3 only; Task 4 not started.

Ownerless authenticated preview sessions now resolve to the explicit
`OWNERLESS_PREVIEW` presentation state before any context is read, with
`show_launcher=False`. The desktop launcher returns before creating its keyed
container, while the dedicated Partner page renders the truthful preview status
once and exposes no composer. Owned accounts that are temporarily unavailable
retain one status but no longer receive a redundant disabled button plus the
same caption; ready accounts retain the real launcher button.

The direct `send_turn` owner validation and `NO_USER_ERROR` defense are
unchanged. The panel still refuses to build ownerless context, and the existing
history, queue-expiry, no-trade, missing-profile, usage, owner-scoping, and
sign-out cleanup paths remain intact.

**TDD evidence:** the two required ownerless tests first failed because
`PartnerAvailability` had no `show_launcher` and the desktop surface rendered
`Ask about a trade`. The dedicated-page, status-only unavailable, and boot
contracts also failed against the old copy/state. After the minimal
presentation change, all five passed.

**Mutation evidence:** temporarily restoring the former ownerless return
(`NO_USER_ERROR` with the default visible launcher) made all three direct
ownerless behavior tests fail: state suppression, desktop rendering, and the
dedicated-page status. The correct implementation was restored and those three
tests passed again.

**Verification:** `pytest tests/test_partner_turn.py tests/test_partner_panel.py
tests/test_pages_boot.py -q` → `190 passed`; adjacent `test_partner.py`,
`test_partner_context.py`, `test_auth.py`, and `test_account_deletion.py` →
`88 passed`; Ruff clean; Black clean; `git diff --check` clean. The bounded
brief required direct rendering and subprocess boot evidence rather than a
browser run. No authentication, database/schema, AI service/routing/prompt,
tenant, secret, dependency, marketing-site, or coordinator-owned SDD ledger
file changed.

**Deviation from the illustrative test:** context construction lives in
`partner_panel._availability`, not `partner_turn.partner_availability`. The pure
test therefore supplies a context object that raises on any read, while the
rendered panel spy proves the adapter is never called. This exercises the real
boundary without adding a duplicate context path to the Streamlit-free turn
module.

### 2026-08-09 — Priority remediation Task 3 review amendment (Codex)

**Commit:** this amendment commit, `fix(partner): keep responsive availability
truthful`. Task 3 review findings only; Task 4 not started.

Owned-unavailable shell status now renders inside the existing
`tl_partner_launcher` keyed container. The phone breakpoint already removes
that complete presentation, so `/Partner` shows only its dedicated-page status
on a phone and other phone destinations receive no leaking Partner status. At
rail widths the keyed status retains the launcher's fixed lower-right
presentation.

The `/Partner` page now reuses the exact `PartnerAvailability` returned by its
body when it renders the desktop-route note. Ready owners keep the real
launcher instruction; owned-unavailable accounts get only the keyed launcher
status; ownerless preview accounts get `OWNERLESS_PREVIEW` in the desktop note
instead of an instruction to use a launcher their state suppresses. The
complementary CSS still provides one Partner presentation per width.

**TDD evidence:** five focused behavioral, AppTest, and AST contract tests
failed against `30c5932`: the unavailable status had no keyed scope or AppTest
launcher block, its status call sat outside the keyed container, and the
ownerless page still carried static launcher copy with no shared-availability
integration. The minimal amendment made all five pass.

**Mutation evidence:** moving the status back outside the keyed container made
all three placement protections fail. Restoring the static desktop instruction
made the ownerless AppTest fail on the missing truthful state. Both mutations
were removed and the five protections passed again.

**Verification:** amended Task 3 suites (`test_partner_turn.py`,
`test_partner_panel.py`, `test_pages_boot.py`) → `195 passed`; adjacent
Partner/auth/account-deletion suites → `88 passed`; Ruff clean; Black clean;
`git diff --check` clean. The real Partner page AppTests cover owned-no-trades
and ownerless states; responsive CSS/source contracts tie their rendered
elements to the complementary keyed presentations. No AI service, prompt,
routing, cost, auth, database/schema, tenant, secret, dependency, marketing,
or coordinator-owned ledger file changed.

### 2026-08-09 — Priority remediation Task 4 implementation (Codex)

**Commit:** this commit, `fix(strategy): align demo truth and simplify
onboarding`. Task 4 only; Task 5 not started.

The Strategy page and global sidebar now select the same shared Task 1 sample
profile whenever demo mode has no stored profile. The page presents the
complete `ICT/SMC Day Trading` playbook as a read-only preview, reports `6 of
6 sections written`, and offers no starter, form, Save control, or persistence
path. The sidebar labels that same fixture as `Sample strategy` rather than
claiming the preview has no active context.

Real empty accounts retain the starter save as their single primary action,
with explicit persistence copy, while manual construction sits behind one
collapsed `Build a playbook manually` expander. Stored profiles render the
same keyed form directly. All field keys, validation state, protected `_write`
path, starter failure handling, toast timing, persistence semantics, and
Strategy-scoped motion/44px/reduced-motion contracts remain intact.

**TDD evidence:** the shared-fixture wiring, ownerless-demo behavior, and
real-empty onboarding guards first failed against the old page; the stored
maintenance baseline passed. The intended failures were the missing demo
branch/sample sidebar and the old starter help/unwrapped manual form. All four
guards passed after the state split.

**Mutation evidence:** forcing demo selection false made the ownerless AppTest
fail on the missing complete profile; reversing the empty/stored form-shell
condition made both onboarding and maintenance AppTests fail; suppressing the
sidebar sample treatment made the coherence AppTest fail. Each mutation was
removed before final verification.

**Verification:** `pytest tests/test_page_polish.py
tests/test_premium_page_contracts.py tests/test_pages_boot.py
tests/test_strategy.py tests/test_strategy_parsing.py -q` → `322 passed`;
adjacent `test_premium_shell.py` → `45 passed`; Ruff clean; Black clean;
`git diff --check` clean. Browser testing was intentionally omitted for this
bounded task because AppTest directly proves rendered text, control absence,
primary-button type, collapsed expander state, direct stored fields, sidebar
markup, and database persistence. No authentication, AI service/routing/prompt,
database/schema, tenant, secret, dependency, marketing-site, or
coordinator-owned SDD ledger file changed.

### 2026-08-09 — Priority remediation Task 5 implementation (Codex)

**Commit:** this commit, `fix(reviews): offer only populated review periods`.
Task 5 only; Task 6 not started.

The pure `components/review_dates.py` adapter now returns unique completed
trading days and containing Mondays newest-first, tolerates a truly empty or
missing-column frame, and converts one selected demo day into the complete row
objects the debrief consumes. Daily Debrief and Weekly Recap use selectboxes
whose options come only from that adapter. Daily uses the selected in-memory
demo rows rather than the empty database, and the demo-only Weekly path uses
the existing public weekly fixture plus the selected demo frame's public
period statistics. It makes no model call and persists no sample review.

The shared Task 1 `ICT/SMC Day Trading` profile is supplied only when demo mode
has no stored profile. True-empty Daily and Weekly states render their exact
recovery copy and `Open Journal →`, then return before generator, usage, or
persistence calls. Live saved-note reuse, the sample-size gate, regeneration
containment, failed-regeneration note preservation, and safe Markdown rendering
remain unchanged. Week labels handle same-month, cross-month, and cross-year
ranges accurately.

**TDD and review evidence:** pure adapter tests first failed on the missing
module. The rendered AppTest next failed because Daily queried the database;
the unpatched demo Weekly check failed on the old empty caption. Independent
task review then reproduced a true zero-column crash and found runtime proof
gaps. Fix-round tests failed on the real `AttributeError`, missing-column row
access, and the cross-year label before the minimal guards and formatter branch
were added. Mutations that reversed option order, restored the Daily database
query, removed the demo Weekly adapter, and ignored a selected non-default day
were all killed. Scoped re-review approved every finding with no new breakage.

**Verification:** the required Task 5 suites and adjacent Weekly, Daily,
demo-data, review-reader, and Strategy suites passed `201/201`. Ruff and Black
were clean on all five changed code/test files; `git diff --check` and the diff
against services, prompts, auth, database/schema, tenant/config/secret, and
marketing paths were clean. AppTest subprocesses provide the required rendered
and runtime evidence, so no browser run was added for this bounded task. No
service, prompt, auth, schema, tenant, secret, dependency, marketing, or Task 6
file changed.

### 2026-08-09 — Priority remediation Task 6 implementation (Codex)

**Commit:** this commit, `fix(ui): finish icon and killzone vocabulary`.
Task 6 only; Task 7 not started.

Every live toast reachable from the routed application now uses Streamlit's
supported Material shortcode syntax. Successful saves and completed analysis
use `:material/check_circle:`, correction guidance uses
`:material/lightbulb:`, and the repeated-correction add action passes
`:material/add:` through the button's `icon=` parameter. Decorative brain,
search, note, and add glyphs were removed from labels and captions as plain
copy. Archived pages and unreferenced components remain deliberately outside
the live-surface contract.

Overview now names the ranked dimension `Killzone performance` and tells an
empty account to tag a killzone on completed trades to compare recurring
windows. Its `killzone` breakdown, ranking, and service calls are unchanged.
The approved `Edge leak` label and positive rule-break P&L warning remain
unchanged: a positive amount is still explained as luck, not repeatable, and a
warning rather than a result.

**TDD evidence:** the routed-source tests first failed on emoji toast literals
in the imported AI Review component, structural glyphs across four live files,
and the old `Session performance` heading. The minimal presentation change made
all three contracts pass. Temporarily restoring one `✅` toast and the old
heading made both icon guards and the terminology guard fail (`3 failed`);
restoring the implementation made those three tests pass again.

**Verification:** the required Task 6 suites (`test_toast_icons.py`,
`test_premium_page_contracts.py`, `test_overview_bands.py`, and
`test_page_polish.py`) passed `252/252`; adjacent AI Review, dashboard/positive
edge-leak, and dark-workspace suites passed `145/145`. Ruff, Black,
`git diff --check`, and the forbidden-scope diff were clean. No browser run was
required by this bounded copy/icon task. No service, AI routing/prompt, auth,
database/schema, tenant, secret, dependency, marketing-site, or Task 7 file
changed.

### 2026-08-09 — Priority remediation Task 7 implementation (Codex)

**Commit:** this commit, `docs(evidence): recapture the dark workspace`.
Task 7 only; Task 8 not started. Independently reviewed and approved with no
open findings.

The capture harness now owns frozen typed manifests for the four existing
marketing stills and nine audit views: every routed destination plus the
desktop Partner drawer and dedicated coarse-pointer phone Partner page. The
explicit `--marketing`, `--audit`, and `--all` modes use the existing owned
scratch SQLite/Chrome-profile lifecycle, restamp only that isolated database to
the fixed `2026-08-09` anchor, and capture the page viewport through CDP. The
four marketing asset paths and site-declared dimensions are unchanged; no
marketing layout changed.

Every shutter now requires zero overflow, zero rendered exceptions, the
manifest's expected pointer media, reduced motion, top scroll position, no
visible Streamlit expander chrome, no signed-out Partner clutter, no rendered
credential, and no date beyond the fixed anchor. Diagnostic URLs redact every
query value. The Partner drawer is opened with a measured, trusted CDP
move/press/release sequence; no DOM `.click()` is used. Partner evidence
requires exactly one visible presentation, and the pointer is parked outside
the viewport before capture.

**Capture inventory:** four WebPs — Overview `1600x1000`; New Trade, Analytics,
and Strategy `1400x933`. Nine PNGs — Overview, New Trade, Journal, Analytics,
AI Reviews, Strategy, Settings, and Partner drawer at `1440x1000`; dedicated
Partner page at `375x812`. All thirteen were inspected at original detail and
contain only the TradeLens page: no browser chrome, Codex overlay/composer,
Streamlit Manage-app surface, cursor, tooltip, transient focus, or auth token.
Journal shows human labels, formatted currency, and R units; Strategy and the
rail agree on `ICT/SMC Day Trading`; dates end at the anchor; both Partner
presentations are exclusive and legible.

**Browser evidence:** the final coarse 375 probe returned bottom navigation
present with five targets, `chevron=false`, `partner_presentations=1`, and zero
overflow, clipping, or undersized targets. At coarse 768 the bottom navigation
was absent, the intended sidebar expander remained at `44x44`, the launcher was
present, and overflow was zero. At desktop 1440 the rail was open, bottom
navigation and expander were absent, the launcher was present, and overflow
was zero. Physical AI Reviews input selected populated defaults: Weekly
`Aug 3–9, 2026` and Daily `Aug 7, 2026`. Each probe used a fresh owned scratch
SQLite/CDP run and cleaned its app, Chrome profile, and database afterward.

**Authorized deviation:** the first 375 capture exposed a persistent Streamlit
sidebar expander above the product bottom navigation. Pointer parking could not
remove it. The initially authorized `stSidebarCollapsedControl` selector did
not exist in the live Streamlit 1.50 DOM; the measured 44px control was
`button[data-testid="stExpandSidebarButton"]`. After escalation and corrected
authorization, one rule hides that exact selector only in the existing
`max-width: 767px` product-bottom-nav breakpoint. The 768 and 1440 navigation
behaviors remain intact. No JavaScript, crop, or broader product change was
used to hide the defect.

**TDD and review evidence:** the initial manifest tests failed because both
typed manifests were absent. Tests now pin manifest uniqueness and geometry,
artifact scope and format, explicit CLI modes, capture contaminants, fixed-date
handling, auth/query redaction, exact phone selector placement, trusted
pointer geometry and move/press/release ordering, and pointer parking. Mutations
of overflow rejection, date comparison, query redaction, the phone selector,
year-first slash dates, compact Weekly ranges, mouse release, and synthetic DOM
click were all killed and restored.

Independent review found that the first date parser missed actual
`YYYY/MM/DD` input text and compact Weekly ranges such as `Aug 10–16, 2026`.
Failing tests reproduced both; the parser now covers them plus mixed-month
ranges. Re-review then requested direct protection for `click_center()`; its
fake-CDP regression killed omitted-release and DOM-click mutations. Final
re-review approved the implementation and all thirteen images.

**Verification:** capture/cleanup/design/page suites `198 passed`; artifact
re-read confirmed every exact format and dimension and no auth query in image
metadata; Ruff clean; Black clean; `git diff --check` clean; forbidden-scope
diff empty. No service, prompt, authentication, database-schema, tenant,
security, dependency, marketing-layout, or Task 8 file changed.

### 2026-08-09 — Priority remediation Task 8 final verification (Codex)

**Commit:** this commit, `docs(audit): re-score the remediated workspace`.
Priority remediation Tasks 1–8 are complete locally. The writer lock is
released to `NONE`; the owner decides whether the branch is finished, pushed,
or deployed.

**Task commit ledger from `63421f7`:** execution checkpoint `efe73ee`; Task 1
`a59839a`, `05dc3b0`, `3a2665d`; Task 2 `891c496`, `11c1c32`; Task 3
`30c5932`, `5f51ea7`; Task 4 `fd9e2f6`; Task 5 `fa7cd73`; Task 6 `324b5d8`;
Task 7 `6ac9c69`; Task 8 is this docs-only commit. The audited product/evidence
HEAD before the Task 8 docs commit is
`6ac9c6981eab297165fa0515cc39ebd9f36dcdeb`.

**Fresh final gate:** after the capture-only Streamlit process owned by this
worktree was stopped, the complete suite passed `2176 passed, 7 skipped in
124.19s`; Ruff reported all checks passed; Black reported 221 files unchanged;
`git diff --check` was empty. The exact protected diff from `63421f7` across
AI routing, Partner safety, database, authentication, migrations, and
Streamlit config was empty.

**Browser matrix:** 40 isolated rows — seven authenticated destinations plus
the applicable Partner drawer/page at 1440, 1024, genuine coarse 768, genuine
coarse 375, and reduced-motion 1440. Pointer and reduced-motion state were
read inside every page. Every row had zero rendered exceptions, horizontal
overflow, visible hit targets below 44px, opaque stale-light surfaces,
automated contrast flags, contradictory sample states, dates after the fixed
anchor, obsolete ownerless Partner copy, raw underscore Journal labels, and
structural emoji in live controls/toasts. Drawer/page presentations were
exclusive. `ai_usage_log` stayed `0 → 0`, so the presentation and keyboard
walks caused no hidden model call.

**Keyboard:** Overview, Journal, AI Reviews, and Strategy were walked at all
five configurations; the Partner drawer was walked at its four applicable
configurations. The probe used real CDP Tab/Shift+Tab dispatch, never
`element.focus()`: 24 walks, 384 transitions, 380 control states matching
`:focus-visible`, and four document-body wrap states.

**Evidence inventory:** four marketing WebPs — Overview `1600x1000`; New
Trade, Analytics, Strategy `1400x933`. Nine audit PNGs — all seven destinations
and Partner drawer `1440x1000`; dedicated Partner page `375x812`. All 13 were
re-opened at original detail for this review and contain product-only,
coherent, readable captures with no browser/Codex/platform chrome, cursor,
tooltip, transient focus, or auth query.

**Final 10K app score:** `81/100` (`65/80`): point of view 8.5, typography
8.5, colour 9.0, hierarchy 8.5, imagery 7.5, motion 7.5, mobile 8.0, invisible
quality 7.5. Imagery is held to 7.5 because the four marketing stills remain
full-page product views with a repeated shell rather than four distinct
editorial compositions. Full evidence and score rationale:
`docs/superpowers/audits/2026-08-09-priority-remediation-review.md`.

**Exact remaining limitations:** Streamlit dataframe headers still omit
`aria-sort`; the canvas-backed ledger still limits authored tabular-numeral
control; coarse pointer is Chrome emulation rather than a physical device;
the contrast scan is automated computed-style evidence, not a formal
assistive-technology audit; no screen-reader, voice-control, or forced-colours
pass was run. The previously reported dataframe-toolbar name limitation did
not reproduce: the four controls exposed Show/hide columns, Download as CSV,
Search, and Fullscreen. The owner-only Streamlit Cloud secrets check remains
required before deployment exactly as recorded at the top of this handoff.

No product code changed in Task 8. Nothing was pushed, merged, deployed, or
used to finish the branch.

## Superseded state snapshots (historical; not current)

The bullets below preserve earlier session boundaries for audit history. They
are not the active handoff state; the authoritative state is the block above.

- **Phase 4 review outcome: no blocking findings.** The diff `2c29a20..6b3d33c`
  is presentation-only and its boundary claims re-verified empty. It is NOT
  marked approved here, because approval was withheld pending the
  authentication blocker, which is now fixed in a separate commit —
  the owner takes the approval decision.
- **Security blocker: CLOSED** at `950bc8f`. Details in the log entry below.
- Verification: `2107 passed, 7 skipped` (Phase 4 left it at `2087/7`; +20).
  Ruff clean · Black clean · `git diff --check` clean.
- **Open, NOT fixed, needs an owner ruling** — a misconfigured `DATABASE_URL`
  renders a Python traceback containing the DSN into the browser. Found while
  building the login browser evidence. Out of the scope of this correction
  (it is a boot-time import failure, not the login path) and recorded below.
- Next owner: **`OWNER`**, then Codex.
- Phase 3 is APPROVED by Codex at `2c29a20`. Phase 4 begins there and is one
  commit on top of it. Review it with `git diff 2c29a20 HEAD`.
- Next owner: **`CODEX`**.
- Next action: **Codex review of the Phase 4 diff.** Presentation-only:
  `git diff 2c29a20 -- src/tradelens/services/ src/tradelens/db/
  src/tradelens/prompts/ alembic/ src/tradelens/config.py` is empty, `auth.py`
  and `auth_screen.py` are untouched, and no marketing-site file was opened.
- Verification: `2087 passed, 7 skipped` (Phase 3 approved at `2069/7`; +18,
  all of them the new Phase 4 guards). Ruff clean · Black clean ·
  `git diff --check` clean. No database file was modified.
- **Deferred to a Codex-owned phase: the password-strength meter.** The audit
  that decided this is recorded in the Phase 4 log entry below. Two real
  new-password forms exist, but both sit inside `st.form`, and the enforced
  policy is a single rule. Neither is Claude's to change.
- **Phase 2 is APPROVED.** Codex approved Phase 2 at `7ffd9a1` — the Partner
  amendments round 4 commit and, with it, Tasks 1–17 and every amendment round
  that preceded them. The final focused Codex re-review named in the previous
  state block has been performed and passed. Phase 3 begins from `7ffd9a1` as
  its base; the approved visual direction and functionality are frozen and this
  phase must not redesign them.
- Last completed work: **Claude's Partner amendments round 4** (`7ffd9a1`) —
  Codex's P1 privacy blocker: `_partner_queue` and `_partner_run` survived
  sign-out, carrying the previous trader's unsent question in plain text. The
  cleanup prefix now covers the whole `_partner_` namespace, with a structural
  guard so the next key cannot be forgotten. Before it: **round 3**
  (`8d39e02`) —
  Codex's hidden-surface spending blocker: a queued question now expires with
  the run that made it, so a CSS-hidden presentation can never call the model.
  Before it: **round 2** (`5805968`) —
  the four findings from Codex's review of `ebdba27`: a safe context-failure
  state, no auto-send after an interrupted queue, the profile notice with
  history, and the full-page Partner restricted to bottom-navigation widths.
  Before it: **round 1** (`ebdba27`) — ownerless and AI-unavailable availability, the no-trades and
  no-profile states, immediate clearing, the two-pass sending state, and
  route-level Partner exclusivity. Before it: the **Codex
  comprehensive-review remediation** (`c78b2a0`) — Partner output enforcement,
  zero-trade model/cost gating, and Partner session cleanup on sign-out, all
  preserved unchanged. Before it: **Task 17** — the 10K re-score, which
  completes **Tasks 1–17**. Before it: Task 16 (`ac8f20e`), Task 15
  (`3de1f43`), Task 14 (`db6be6d`), and Tasks 12 and 13, the AI Reviews reading shell
  (`cd1273c`) and the Strategy/Settings/auth surface (`c8952dd`). Before
  them: Tasks 10 and 11 — Analytics on one instrument shape
  (`eaeca32`) and the pure review document model (`df07a11`). Before them:
  Tasks 8 and 9 — New Trade on the dark workspace
  (`f2eb1df`) and the dark Journal (`9d571d3`). Before them: Tasks 5–7, the
  Overview's five bands — `243d0c9`, `25616f9`, `00d2359`. Task 4 is
  `3aa9e36`; Task 3 is `5a03834` + `16a81ee`.
- Plan path: `docs/superpowers/plans/2026-08-04-phase2-dark-workspace-implementation.md`
  (4900 lines, 17 tasks, 145 steps). It supersedes
  `docs/superpowers/plans/2026-07-31-streamlit-dark-workspace-ai-review.md`.
- Verification at Partner amendments round 4: `2064 passed, 7 skipped` · Ruff clean · Black clean
  · `git diff --check` clean · all four Analytics lenses verified at 1440,
  1024, coarse 768 and coarse 375 plus reduced motion, with the pointer state
  and the reduced-motion state asserted from the page at every applicable row
  — zero overflow, zero undersized targets, zero exceptions, chart heights
  only ever 360 or 240, calendar 7-across with 47x44 cells at coarse 375, rail
  and bottom bar never both on screen. The Journal calendar was re-verified
  after the shared key rename.
- Next owner: **`CODEX`**.
- **Exact diff state:** review the whole of Phase 3 with
  `git diff 7ffd9a1 HEAD`. It is three commits on the approved `7ffd9a1`:
  `548acc5` (the four defects), `542a7f3` (recording that SHA here), and
  `0371604` (this amendment). Files touched across all
  three: `design_system.py`, `components/theme.py`,
  `components/trade_calendar.py`, `pages/1_NewTrade.py`,
  `tests/test_premium_page_contracts.py`, `tests/test_dashboard.py`,
  `.gitignore`, and this handoff. Nothing is pushed; the branch is local.
- Next action: **Codex review of the Phase 3 diff.** Phase 3 is complete. It
  was a presentation-only pass; `git diff 7ffd9a1 -- src/tradelens/services/
  src/tradelens/db/ src/tradelens/prompts/` is empty, `auth.py` is untouched,
  and no schema, secret, tenant-scoping, or marketing-site file was opened.
  Motion work remains deferred to Phase 4 and was not started.
- **Verification after the amendment:** `2069 passed, 7 skipped` (Phase 2
  approved at `2064/7`; +1 selector guard, +4 calendar guards). The calendar
  guards are mutation-tested — reverting the shape channel to colour-only
  fails them on both surfaces. Browser: both calendars and the legend at 1440,
  1024, coarse 768, coarse 375 and reduced motion, 10 runs, every one with
  zero overflow, zero sub-44px targets, zero contrast failures, zero stale
  light surfaces, and every mark surface fully distinct without colour.
  - Limitation, stated rather than papered over: the Journal grid's rendered
    evidence shows two of the three outcomes, because the month on screen has
    no breakeven day. The **legend** renders all three at all five
    configurations, and the structural test proves the Journal grid's own
    three selectors produce three distinct greyscale signatures.
  - This required real trades, so the sweep ran against a **throwaway seeded
    SQLite file in the scratchpad**, never the project database. In DEMO_MODE
    the Journal takes a demo-data branch that renders a plain table and never
    mounts the calendar at all — which is why the first Phase 3 sweep found no
    day marks to measure.
- **Phase 3 verification (pre-amendment):** `2065 passed, 7 skipped`.
  Ruff clean · Black clean ·
  `git diff --check` clean. Browser evidence: 8 destinations x 4 viewports
  (1440, 1024, coarse 768, coarse 375) plus a reduced-motion pass over all 8
  at 1440 — 40 measured runs before the fixes and 40 after. The coarse-pointer
  and reduced-motion states were asserted from inside the page on every
  applicable run rather than assumed. Confirmation pass: **zero horizontal
  overflow, zero sub-44px targets, zero composited-contrast failures, zero
  stale light surfaces** on every page at every viewport.
- **Four defects found and fixed** (all shipped in Phase 2, none cosmetic):
  1. `.tl-flank*` — the four figures beside the Overview trajectory had been
     emitted since the band was built with **no CSS anywhere**, so all three
     spans per row ran together: `Average win$293.1833 winning trades`. Two
     numbers presented as one, on the landing page, at every width.
  2. Streamlit's `primaryColor` painted Strategy's "Apply the ICT/SMC starter
     playbook" teal with a **white** label at **1.61:1**, because the colour
     rule used `.stButton > button` and a `help=` button sits inside a tooltip
     div. The 44px floor had already learned this exact lesson; the colour
     rule never had it carried back.
  3. Both calendars dimmed non-trading days with `opacity` (0.35 Overview,
     0.45 Journal), measuring **3.0:1 on 12px text**. Real dates, dimmed to
     look forbidden — the substitution the design system already warns against
     where it separates disabled from read-only inputs.
  4. The New Trade review ticket set a hand-rolled `ui-monospace` stack, so the
     last screen before a save rendered its numerals in a different face from
     every other numeral in the product.
- Colour-only meaning is **also** now spelled out for assistive technology in
  the Overview calendar (visually-hidden outcome text per day, zero visual
  change). See the unresolved finding below for the part that needs a ruling.
- A structural guard, `test_the_button_label_colour_reaches_tooltip_wrapped
  _buttons`, asserts the colour-declaring rule never regains a `>`, so the
  next control passing `help=` inherits the fix instead of rediscovering the
  bug.
- **RESOLVED by the amendment — colour-only calendar meaning.** Outcome is now
  carried by shape first: **filled circle** net-positive, **filled diamond**
  net-negative, **hollow ring** breakeven. One `.tl-cal-dot` definition serves
  the Overview grid and the legend, and the Journal grid's `::before` marks use
  the same three shapes, so the key cannot drift from the marks it explains.
  The visually-hidden outcome text stays. Calendar geometry is unchanged: the
  marks are still 7-8px inside the same cells.
  - The diamond is a **`clip-path` polygon, not `transform: rotate(45deg)`**.
    The rotation was the first implementation and measurement rejected it:
    Chrome reported the day marks' computed transform as `none` at coarse 375
    while returning the rotation matrix at 1440, so the mark silently stayed a
    rounded square on a phone. clip-path holds at all five configurations.
  - **A regression this phase itself introduced was caught here and fixed.**
    Widening the button colour rule to the descendant combinator (Phase 3
    defect 2) also made it reach the calendar's day buttons, which pass
    `help=` — so every traded day became a filled teal action button, exactly
    the treatment Analytics retired when it dropped its own calendar. The day
    rule now declares its own surface (panel, hairline border, mono figure)
    instead of depending on whether the global rule reaches it.
- **Amendment 2 — the `.impeccable/` ignore rule is narrowed.** The previous
  blanket `.impeccable/` would have hidden durable shared artifacts. Only the
  machine-local cache is ignored now, via `.impeccable/hook.cache.json` and
  `**/.impeccable/hook.cache.json` (the second catches nested project copies
  such as `src/tradelens/ui/.impeccable/`). Verified with `git check-ignore`
  against real probe files: both cache copies ignored; `live/config.json`,
  `design.json`, `critiques/`, `briefs/`, `mocks/` and `approvals/` all remain
  visible to Git at both the root and the nested path. Nothing from
  `.impeccable/` is staged in any commit.
- Three cosmetic orphan classes remain emitted with no rule and no visual
  effect — `.tl-evidence-sample`, `.tl-note-thesis-label`, `.tl-partner-head`;
  each is a dead styling hook whose siblings or children carry the styling.
  Left alone deliberately: removing them is churn, not polish.
- The comprehensive Codex review has been performed and the final focused
  re-review of the Partner presentation amendments has passed.
- Tasks 1–17 are implemented and approved.
- Task 4 interfaces are present exactly as planned and verified green
  (`tests/test_metrics.py` + `tests/test_partner_context.py`, 129 passed).
  Claude must consume them, never reproduce their calculations or open a
  second data-access path in UI code.
- Deviations already approved by the user and in force for the remaining
  tasks: use `compute_breakdown` for P&L-ranked breakdowns because
  `by_setup_type` carries no P&L; use `killzone` as the session dimension with
  labels from `KILLZONE_LABELS`, because the Overview frame has no `session`
  column.
- Band logic lives in the pure `components/overview_bands.py`, not `app.py`:
  `app.py` runs its whole Streamlit script at module scope, so importing it in
  a unit test boots a page and needs a database.
- Spec/plan agreement: resolved. `TL_LINE_STRONG` is `#5C6E77` in both, and the
  spec now carries the measured all-six-surface contract (§4.4, amendment C6 in
  §15.3).
- Blocker: cleared. The `nt_shot` Back-navigation exception is fixed and proved
  fixed in a real browser both ways (see the handoff-log entries below).

## Ownership boundaries

### Claude Code owns

- Creative direction and page composition.
- Streamlit page/component presentation.
- Design tokens and scoped UI CSS.
- Responsive behavior and accessibility presentation.
- Dashboard layout and visual treatment of approved metrics.
- AI Partner launcher, drawer/sheet, conversation presentation, and loading
  states, using only an already-approved backend interface.
- Motion and interaction polish.
- UI-focused and browser-interaction tests.

### Codex owns

- Authentication and password-recovery security behavior.
- Tenant isolation and user-scoped data access.
- AI scope/safety, prompt boundaries, model routing, and cost logging.
- Secrets, exception containment, and model-output safety.
- Service-layer calculations and APIs.
- Database and destructive-operation safety.
- Debugging, CI failures, security tests, and final engineering review.

### Files requiring Codex ownership or explicit review

- `src/tradelens/services/ai_client.py`: Codex only. Never edit concurrently.
- `src/tradelens/services/partner.py`: Codex-owned AI boundary.
- `src/tradelens/services/metrics.py`: Codex-owned calculation boundary.
- Authentication, database, cost, tenant-scoping, and secret-handling modules:
  Codex-owned.
- Claude must stop and hand off instead of adding service logic inside a page.

## One-writer protocol

1. Read this file and run `git status --short` before every phase.
2. Do not begin if `Active writer` names the other tool.
3. The incoming owner changes `Active writer` to its name before editing code.
4. Work only in the canonical worktree named above.
5. Do not run `git add -A`; stage only explicitly reviewed paths.
6. Do not reformat, restore, stage, or commit unrelated changes.
7. At a checkpoint, update `Current handoff state` with:
   - owner;
   - phase and task;
   - files changed;
   - tests and browser checks;
   - unresolved risks;
   - exact commit/diff state;
   - next owner and next action.
8. Set `Active writer` back to `NONE` before asking the user or the other tool
   for review.
9. The next owner must review the diff before continuing; it must not trust only
   the prose report.
10. No concurrent edits, cherry-picks, rebases, merges, pushes, or deployment
    while another tool is the active writer.

## Codex rulings on the preflight questions

### 1. Floating AI Partner: approved with boundaries

Claude may build the global bottom-right Partner UI by reusing the existing
`partner_reply(...)` service in its general reflective mode
(`per_trade_qa=False`). This is not approval for a new endpoint, a new direct
Anthropic call, or a new system prompt.

Required boundaries:

- Context must be assembled only from the authenticated user's journal,
  completed trades, and active Strategy Profile.
- Every service query must receive the authenticated `user_id`; no global or
  unscoped trade lookup is allowed.
- Reuse `src/tradelens/services/partner.py`; never import the Anthropic SDK from
  a page or component.
- Log usage exactly once per completed response with the authenticated user,
  using the existing `log_ai_usage("AI Partner", usage, user_id=uid)` pattern.
- Keep the existing post-trade scope guard. Never provide live signals,
  predictions, entries, position instructions, or financial advice.
- Model output must use Streamlit's safe Markdown path with unsafe HTML off.
  Any surrounding custom HTML must escape its values.
- The UI may expose evidence, sample size, confidence, and limitations, but may
  not invent them when the service did not return or support them.
- Claude owns the surface. Codex must author or approve any new context adapter,
  service signature, prompt, cost behavior, or safety behavior.

### 2. Public rule-adherence metric: approved, Codex-owned

Add one small pure public function in `services/metrics.py`, provisionally named
`rule_adherence_rate(df)`. It must reuse the existing `_is_followed` semantics,
return a fraction from `0.0` to `1.0`, and define honest behavior for empty or
unknown samples. Tests must cover all-followed, none-followed, mixed, empty, and
missing-column inputs. The UI must show the numerator/denominator or sample size
beside the percentage so a small sample is not presented as certainty.

Claude must not duplicate this calculation in Streamlit page code.

### 3. Scope amendment: approved

The user's newer approved direction overrides the older plan wherever the plan
says no chat interface or forbids the expanded Overview metrics.

The redesign now includes:

- A global bottom-right, post-trade AI Partner using the existing safe partner
  service.
- A curated fixed Overview using the existing headline metrics plus drawdown,
  streaks, average win/loss, rule adherence, edge leak, session performance,
  setup performance, consistency score, and a calendar heatmap.

This does not authorize a customizable widget builder, a generic card wall, a
new AI endpoint, a database migration, or changes to model routing.

### 4. Browser preflight: approved after foundation sync

Run the complete browser baseline only after:

1. the Opus 5 migration has its own reviewed commit;
2. that commit is brought into this redesign branch;
3. the UTC-sensitive cost test is fixed and the full suite is green.

Then capture and verify all seven destinations at 1440, 1024, real
coarse-pointer 768, real coarse-pointer 375, and reduced motion. Preserve the
New Trade wizard, Journal routes, Analytics lenses, AI caches, Strategy
persistence, Settings tenant isolation, and authentication/recovery flows.

## Required sequence from here

1. Finish and commit the staged Opus 5 migration separately from the redesign.
2. Codex reviews that commit and brings it into this branch without importing
   unrelated dirty-tree changes.
3. Codex fixes the time-dependent cost test using the current UTC month (or an
   injected/frozen timestamp in the test). Do not change production UTC
   timestamping to satisfy a hard-coded month.
4. Run the full test, Ruff, Black, and diff checks until the baseline is green.
5. Run the approved browser preflight and record baseline evidence.
6. Set `Active writer: CLAUDE` and run UI/UX Pro Max as a specification-only
   phase.
7. Set `Active writer: NONE`; Codex reviews the specification and scope.
8. Repeat the handoff for Frontend Design, Impeccable, and Emil, one phase at a
   time, with Codex reviewing the actual diff between phases.
9. Codex runs the final security, tenant-isolation, AI-safety, full-test, CI,
   and browser gates before any commit/push/PR decision.

## RESOLVED — auth fail-open, fixed at `950bc8f`

The finding recorded below was confirmed in full and is now closed. The
original text is kept underneath because it states the defect as it stood.

**Phase 4 review, performed first and separately: no blocking findings.**
`git diff 2c29a20 6b3d33c` touches five files and its boundary claims
re-verified empty — services, db, prompts, alembic, config, `auth.py`,
`auth_screen.py`, `partner_panel.py` and `site/` are all untouched by it, no
`unsafe_allow_html` was added, and no script/JS was introduced. Two review
notes, neither blocking:
- `test_every_duration_stays_under_the_300ms_ceiling` matches `\d+ms` only, so
  a second-denominated duration would pass unseen. The one that exists (the
  1.4s skeleton pulse) is the documented intended exception.
- The lens container's "replays only on lens change" property is argued from
  Streamlit's keyed-element reconciliation and is covered by a source test,
  but was not driven in a browser with an unrelated widget interaction.

**What changed in the fix.**

| | Before | After |
|---|---|---|
| Secrets unset | `("demo", "tradelens2025")` accepted | `("", "")`, legacy login unavailable |
| Blank / whitespace config | authenticated | unavailable |
| One half configured | the set half plus a default | unavailable |
| `users_exist()` raises | `has_db_users = False` → legacy branch | `AuthUnavailableError`, no decision |
| DB user wrong password | rejected | rejected (unchanged) |
| DB-backed + legacy pair | rejected | rejected, and now guarded by a test |
| Outage message | "Incorrect username or password." | "Sign-in is temporarily unavailable." |
| Outage log | none | exception TYPE NAME only |
| Configured legacy + empty DB | signs in, `user_id=None` | unchanged — compatibility preserved |

**No new environment flag.** `TRADELENS_USERNAME` / `TRADELENS_PASSWORD`
already express every supported mode: both set means legacy login exists,
anything else means it does not. A third flag would have added a way to
misconfigure the system without adding a capability.

**Deployment state — presence only, values never read.**

| Location | `TRADELENS_USERNAME` | `TRADELENS_PASSWORD` |
|---|---|---|
| `.env.example` (template) | defined | defined |
| `/Users/ayoub/tradelens-ai/.streamlit/secrets.toml` (local dev) | defined, non-blank | defined, non-blank |
| this worktree `.streamlit/secrets.toml` | absent | absent |
| process environment | not set | not set |
| tracked in Git | none — no `.env` or `secrets.toml` is tracked | — |

**LIMITATION: the live Streamlit Community Cloud secrets are not readable from
this worktree**, so whether the deployed app configures the legacy pair is
UNKNOWN here. The owner must check it directly:

> share.streamlit.io → the TradeLens app → **Settings → Secrets**, and confirm
> whether `TRADELENS_USERNAME` and `TRADELENS_PASSWORD` are present and
> non-blank.

Either answer is now safe, which is the point of the fix — unset means legacy
login is closed rather than open on a published default. But the answer
changes what the deploy did *before* this commit: if they were unset, the
published pair was live on the internet, and **the owner should treat that as
a disclosed credential** and rotate anything that reused it.

## RESOLVED — DSN disclosure and two Phase 4 gaps, at `7c046fc`

### 1. DATABASE_URL disclosure — closed, defence in depth

Reproduced first with a sentinel DSN
(`nosuchdriver+nodbapi://SENTINELUSER:SENTINELPASSWORD@sentinel-host.invalid
:5432/sentineldb`) so a leak would be unambiguous.

| | Before | After |
|---|---|---|
| Engine build fails | raises at module import | contained; `engine = None` |
| Fallback | — | none: no SQLite, no empty DB, no other tenant |
| `SessionLocal()` | session bound to nothing | `DatabaseUnavailableError` |
| `init_db()` | SQLAlchemy's own error | `DatabaseUnavailableError` |
| App boot | Streamlit's error view | one generic line, then `st.stop()` |
| Rendered page | `Traceback` **and the DSN** | calm copy, zero sentinels |
| Widgets rendered | 5 text inputs, 3 buttons | **0 and 0** |
| Log | nothing of ours | exception **type name only** |
| `showErrorDetails` | default `full` | `"none"` |

`showErrorDetails = "none"` and not `false`: verified against the pinned
streamlit **1.50.0** that the option is a STRING whose enum is
`full | stacktrace | type | none` (`config.ShowErrorDetailsConfigOptions`),
and that `false` survives only as a legacy variation the loader special-cases.
"none" is canonical and does not depend on that shim. Config alone would be
one setting away from a disclosure; containment alone would leave every other
uncaught exception free to print a traceback — hence both.

**`st.stop()` is load bearing, and a mutation proved it.** Without it the
script runs on into `require_auth()` and paints a full login form on a
deployment with no data store. The first version of the test missed this: it
asserted a sentinel `print` was not reached, and passed with the stop deleted
because the script died a few lines later anyway. It was measuring the crash,
not the stop. It now asserts the rendered widget count.

**Browser cold-start evidence** (real server, sentinel DSN, CDP): rendered
text was exactly `TradeLens is temporarily unavailable. Please try again
shortly.`; zero sentinels in the full `outerHTML`; no `Traceback`; 0 inputs,
0 buttons, 0 `stException`; and zero sentinel occurrences in the server log.

**17 subprocess tests** in `tests/test_database_url_containment.py` — cold
start is the point, and `importlib.reload(session)` would rebind `engine` and
`SessionLocal` while every service still held the old references, poisoning
the suite to test an import. Five mutations, all caught after the stop-test
was repaired: containment removed, SQLite fallback, `str(exc)` logged,
`st.stop()` removed, `showErrorDetails` back to `full`.

### 2. Duration guard — was unit-blind

Matched `(\d+)ms` only, so `0.4s` was invisible and the ceiling could be
evaded by changing units; and it never read `--tl-dur-*`, where the numbers
actually live. Now normalises ms and integer/decimal seconds across
`transition`, `animation`, both `-duration` longhands, the tokens, and
multi-value declarations. The 1.4s skeleton pulse remains a **named**
exemption, keyed to its animation name and pinned to its value. Mutations
caught: an unauthorised `0.4s` transition, a `1s` animation, and a token
raised to `420ms`.

### 3. Lens replay — the browser found a real defect, now fixed

**The Phase 4 claim was wrong.** Measured with real `animationstart` events
and a `MutationObserver` confirming a rerun actually occurred:

| Event | Before the fix | After |
|---|---|---|
| Unrelated rerun that remounts the page | **replayed** | replays (fresh mount — correct) |
| **Lens change** | **did NOT fire** | **fires exactly once** |
| Reduced motion, lens change | — | `animation-name: none`, `transform: none` |

Cause: one rule on `[class*="st-key-tl_lens_"]` matched every lens, so when
Streamlit reused the container node and swapped only its class,
`animation-name` never changed — and a CSS animation restarts only on
insertion or a name change. The keyed-reconciliation argument was wrong about
the mechanism.

Fix: one animation name per lens, generated from a single template so the four
keyframe sets cannot drift. No JavaScript, no dependency.

**Not verified, stated plainly:** a rerun caused by an unrelated *widget* on
the Analytics page. The only candidate is the Partner launcher, and a
synthetic `.click()` does not drive a Streamlit button — the observer recorded
`muts: 0`, i.e. no rerun happened, so that run proves nothing either way. The
structural argument is now stronger than before (the name changes only when
the lens changes) but it is an argument, not a measurement.

## Superseded — DSN in a rendered traceback (now fixed at `7c046fc`)

Found while building the login browser evidence, and reported rather than
silently fixed because it is outside this correction's path.

With `DATABASE_URL` pointing somewhere unusable, `src/tradelens/db/session.py`
raises at **module import**, before any page renders. The browser then shows
Streamlit's default error view containing a full traceback **including the
connection string** — measured: the rendered page contained both `Traceback`
and `sqlite:///`.

This is not the login path and the fail-closed change does not address it: the
app never reaches `authenticate_login`. Two candidate remedies, both an owner
call: set `client.showErrorDetails = false` in `.streamlit/config.toml` for
deployed environments, and/or catch the engine-construction failure and render
a generic unavailable page. Recorded, not chosen.

## Original finding (now resolved) — auth fail-open (raised during Phase 4)

Raised by an automated security review while Phase 4 was being reported.
**Not touched, and not Claude's to touch:** `auth.py` is Codex-owned, the
Phase 4 brief forbids modifying authentication, and the writer lock is
`NONE`. Recorded here so it is not lost with the session.

**The chain, read from the current source:**

1. `expected_credentials()` (`auth.py:155`) falls back to
   `_DEFAULT_USERNAME = "demo"` / `_DEFAULT_PASSWORD = "tradelens2025"`
   (`auth.py:34-35`) when `TRADELENS_USERNAME` / `TRADELENS_PASSWORD` are
   unset. There is no empty-value guard.
2. `verify_credentials()` compares against that pair with no check that it
   was actually configured.
3. `authenticate_login()` (`auth.py:196`) catches every exception from
   `users.users_exist()` and sets `has_db_users = False`, which routes to
   `verify_credentials()`.

So on a deployment where real accounts exist, **a database outage downgrades
login to the single-user secrets path** — and if those secrets are unset, to a
credential pair committed in the repository. The session it grants carries
`user_id = None`, the legacy tenant.

**One correction to the review's framing, because it changes triage.** The
review describes this as a regression and suggests restoring a
`TRADELENS_ALLOW_DEMO_LOGIN` opt-in that "the removed code did". That flag has
**never existed in this repository** — `git log -S TRADELENS_ALLOW_DEMO_LOGIN
--all` is empty. The defaults date from `a0ef59b` and the fail-open from
`7bdf825`, both long before the redesign. This is long-standing behaviour, not
something a recent commit broke, and nothing in Phases 2-4 touched it:
`git diff 7ffd9a1 HEAD -- src/tradelens/ui/components/auth.py` is empty apart
from the Phase 2 Partner-key prefix fix already recorded above.

**Not assessed by Claude:** whether the deployed Streamlit Cloud instance sets
those two secrets. That determines whether the fallback lands on published
defaults or merely on a legacy-tenant bypass, and it is a deployment question,
not a code one.

## Handoff log

### 2026-08-08 — Independent final review (Codex)

**Outcome: approved.** The Phase 4 motion diff, fail-closed authentication,
and database-bootstrap containment were reviewed against the implementation,
focused subprocess tests, a live Streamlit browser session, and the full
project gates. No product-code blocker remains.

| Before | After | Why |
|---|---|---|
| A named long-duration animation exempted its entire comma-separated declaration | The exemption is evaluated per top-level animation item | An unrelated 1.4s animation could previously borrow the skeleton pulse's exemption and pass the 300ms ceiling guard. |
| The traceback test accepted legacy `false` spellings | The project contract pins canonical `showErrorDetails = "none"` | The deployed config deliberately chose the stable Streamlit 1.50 enum rather than a compatibility shim. |

**Live motion evidence.** Chrome CDP drove the actual Analytics page in demo
mode. Performance → Risk emitted exactly one `tl-lens-in-risk` event. Selecting
the NQ Asset filter caused a confirmed Streamlit rerun (3,436 observed DOM
mutations) with zero lens-animation events and zero rendered exceptions.
Under emulated `prefers-reduced-motion: reduce`, Risk → Timing rendered with
`animation-name: none`, `transform: none`, zero overflow, and zero exceptions.
The `agent-browser` executable was unavailable, so the fallback used a fresh
headless Chrome target and direct CDP rather than claiming an agent-browser or
physical-device run.

**Security evidence.** The authentication and database paths fail closed:
unconfigured or partial legacy credentials cannot authenticate; a user-store
failure cannot fall through to legacy mode; engine construction cannot fall
back to another database; and the browser receives generic copy rather than a
DSN or traceback. The final review changed no product, auth, database, service,
schema, prompt, or marketing-site code.

**Verification:** `81 passed` in the focused motion/auth/DSN gate, then `2129
passed, 7 skipped` in the full suite. Ruff clean; Black clean (217 files);
`git diff --check` clean.

**Still owner-only:** inspect the deployed Streamlit secrets. If the legacy
username/password were absent before `950bc8f`, treat the old published pair
as disclosed and rotate it anywhere it was reused. Nothing was pushed, merged,
or deployed, and the separate password-strength feature remains deferred.

### 2026-08-08 — Phase 4: motion and interaction refinement (Claude)

Presentation only. Four motions added, one brittle locator repaired, and two
opportunities rejected outright. Phase 2 had already applied the decision
framework carefully — the rail, the tabs, the wizard step, the Journal detail
and the More sheet all carry reasoned motion with frequency arguments in their
comments — so this phase is refinement, not construction. The motion token
system (`--tl-ease-out/-in-out/-drawer`, `--tl-dur-press/-state/-panel/
-drawer`) already existed and was reused; no new timing or easing literal was
introduced.

**The four that earned their place.**

1. **The Partner drawer had no motion at all**, and `--tl-ease-drawer` /
   `--tl-dur-drawer` had been defined in Phase 2 and applied *nowhere*. A
   420px panel appeared over the work with no account of where it came from.
   It now enters on its own curve from the launcher's corner
   (`transform-origin: 100% 100%`, 8px rise, scale 0.98 — never 0).
   **Enter only, and structurally so:** `render_partner_drawer` returns before
   rendering anything when `partner_open` is false, so on close the server
   removes the element and there is no node left to animate. Keeping it
   mounted to buy an exit would put its Close button, composer and chips back
   in the tab order while invisible — reversing Phase 2's deliberate
   `display: none` decision. Rapid open/close is safe by construction rather
   than by damping: the element is present or absent, never half-transitioned.
2. **Press feedback was inconsistent.** The rail's filled action and the
   mobile tabs scaled on press; every other button changed colour only, so the
   same gesture answered differently depending on which control was hit.
   Now `scale(0.97)` at `--tl-dur-press`.
3. **The rail's dock-inspired refinement** — icon `scale(1.06)` on fine-pointer
   hover, inside the approved 1.05-1.08 band. Magnification and neighbour
   displacement were rejected: both need pointer x-position fed to a width,
   which needs JavaScript, and displacement would move a destination while a
   trader is aiming at it. Nothing animates width, so no row can push another.
4. **The Analytics lens change** reveals at 170ms — the same rhythm as the AI
   Reviews section index, because it is the same gesture. The container key
   carries the lens name, so it replays on a lens change and on nothing else.

**Rejected, with reasons.** Page transitions (Streamlit reruns the whole
script; large page-entry choreography was forbidden and would fire on every
navigation). Widening the expander reveal beyond the playbook form (Phase 2
scoped it deliberately; widening puts motion on five pages that asked for
none). Dashboard widget stagger, ambient motion, and any AI-content
replacement animation — the existing skeleton already preserves the note's
geometry and, per the Phase 3 audit, regeneration does not hide the note.
Rail press *movement* was also rejected: Phase 2's comment that these rows are
"visited dozens of times a session" still governs, so they keep colour only.

**One correctness fix inside my own work, worth recording.** The rail icon
rule sits ~150 lines AFTER the global reduced-motion kill switch with
identical specificity (0,5,0). Listing `transform: none` in that switch loses
on source order and does nothing — the icon would have kept scaling under
reduced motion. The guard is now on the declaration's own media query, and
`test_the_rail_icon_scale_is_guarded_where_it_is_declared` fails if it is
moved back. The kill switch carries a comment telling the next author why the
rule is deliberately absent from it.

**`:active` fires on the keyboard, and the brief forbids that.** A bare
`:active` scale would animate a Space-held activation. The movement is
therefore split onto `:active:not(:focus-visible)`; colour still changes on
both paths. **Measured, not reasoned:** with real `Input.dispatchKeyEvent` Tab
traversal (never `element.focus()`, which `:focus-visible` does not match) the
keyboard-focused button reports `active: true`, `focusVisible: true`,
`outline: 2px solid` and **`transform: none`**. 8 tab stops reached forward,
Shift+Tab reverse traversal confirmed.

**Browser evidence — 7 configurations, pointer and reduced-motion state read
back from the page on every row.**

| Config | pointer | reduced | rail icon | lens | drawer |
|---|---|---|---|---|---|
| 1440 fine | fine | no | `transform .16s` ease-out | — | `tl-drawer-in .24s` drawer curve |
| 1024 fine | fine | no | `transform .16s` | — | — |
| coarse 768 | **coarse** | no | **not applied** | — | — |
| coarse 375 | **coarse** | no | **not applied** | — | `display: none` (phone rule intact) |
| 1440 reduced | fine | **yes** | **not applied** | — | **`animation-name: none`** |
| 1440 Analytics | fine | no | applied | `tl-lens-in .17s` | — |
| coarse 375 Analytics | **coarse** | **yes** | not applied | **`none`** | — |

Zero horizontal overflow, zero rendered exceptions, at all seven. The drawer
keyframes read out of the live stylesheet animate opacity and transform only.

**Three probe defects found and corrected before any claim was made** —
recorded because each produced or would have produced false evidence:

1. **CDP emulation is session-scoped.** The first probe set device metrics on
   one websocket connection, closed it, then measured on a new one — so the
   overrides were reverted and `(pointer: coarse)` never flipped. The "coarse
   768/375" rows of that run were fine-pointer runs wearing a phone width. The
   probe's own pointer assertion is what caught it. Everything now happens on
   one connection.
2. **`rule.style.animationName` is empty when the shorthand contains
   `var()`.** A shorthand with a variable is stored as a pending-substitution
   value, so the CSSOM read reported the drawer and lens rules as absent when
   both were present and valid. Computed style resolves variables; the CSSOM
   declaration does not.
3. **`button.click()` does not open the Partner drawer.** Streamlit needs a
   trusted event and a server round trip. The drawer's cascade was therefore
   measured on a synthetic element carrying its class — which proves the rule
   reaches that class in each configuration, and is **not** a claim that the
   drawer was opened in a browser.

**Guards: 18 new tests in `tests/test_phase4_motion.py`, mutation-checked.**
Five mutations, each caught by the right test: the rail guard moved back to
the kill switch; the press scale losing `:not(:focus-visible)`; the drawer
swapping its curve for the generic ease-out; the icon scale pushed past the
band; the drawer losing its `transform-origin`. File-wide rules are pinned
too: no `transition: all`, nothing entering from `scale(0)`, no bare
`ease-in`, no duration above 300ms.

**One existing test was repaired, not weakened.**
`test_the_more_reveal_is_withdrawn_under_reduced_motion` located its subject
as *the first* `no-preference` block in the file. Phase 4 added earlier ones,
so that locator stopped naming the block the test is about. Both assertions
are unchanged in strength — the reveal must sit inside an opt-in block and
must never be declared outside one; only the locator learned to find its own
subject, via a helper that walks back from the declaration to its own guard.

**A process failure, recorded because it cost real work.** A mutation-testing
loop used `git checkout --` to revert a mutation and instead reverted every
Phase 4 edit in `design_system.py`, because the file was not yet committed.
All six edits were reapplied and re-verified. Mutations after that point
restore from a scratchpad copy, never from Git.

**NOT verified, stated rather than implied.** No physical device was used;
coarse pointer is Chrome emulation (`setDeviceMetricsOverride` with
`mobile: true` plus touch emulation), asserted from the page but still
emulation. Slow-motion and frame-by-frame inspection were not performed —
durations, easings, delays and animated properties were read as computed
values instead. Rapid repeated activation and mid-transition reversal were
reasoned about structurally for the drawer (present-or-absent, so no
half-state exists) but not driven in a browser, because `button.click()` does
not open it.

**The password-strength meter is specified, not implemented, and the audit is
the reason.**

- Two real new-password forms exist: signup (`auth_screen.py`, key
  `signup_password`) and reset (key `reset_new_password`). Login is
  `current-password` and was correctly excluded from scope.
- **The enforced policy is one rule: `MIN_PASSWORD_LEN = 8`** in
  `services/users.py`, applied by `validate_signup` and by
  `complete_reset`. There is no uppercase, digit, or symbol requirement.
  The 21.dev component presents four rules including a 12-character minimum —
  presenting any of them would show a trader requirements authentication does
  not enforce, which the brief forbids.
- **Both fields sit inside `st.form`, which batches widget state.** No rerun
  fires on keystroke, so a live meter cannot update until submit. Making it
  live means moving the password field out of the form — a change to
  authentication form structure, error handling and submit semantics.

Either fixing the rule set to match policy, or raising the policy to match the
rules, or restructuring the form, is Codex-owned. Recommended next phase:
Codex rules on the policy, then the meter is built natively (segmented bars on
existing tokens, textual label, requirements checklist, common-pattern
warning, `aria-live` announcement, reduced-motion safe) against whatever
policy it rules for. No TSX was copied and no React dependency was added.

**Also rejected on the same grounds: the animated dock as given.** It requires
`motion/react`, `next/link`, `clsx` and `tailwind-merge`, and the repo has no
`package.json`, `tsconfig`, Tailwind config or a single `.tsx` file. The
approved CSS-only adaptation shipped instead; see item 3 above.

**Marketing hero: reviewed, proposal only, nothing changed.** `site/` is
untouched. The findings are in the Phase 4 report to the user and are not
implemented, per the brief.

### 2026-08-08 — Phase 3 amendment: shape before colour, and a narrower ignore (Claude)

Two amendments Codex asked for before approval, plus one regression the first
of them uncovered.

**Colour is no longer the only channel.** Circle, diamond, ring — net-positive,
net-negative, breakeven — on the Overview grid, the Journal grid and the legend
that explains them. The legend is built from the same `.tl-cal-dot` class as
the Overview marks, so it cannot fall out of step with them; the Journal's
`::before` marks repeat the three shapes deliberately rather than inventing a
second vocabulary. Geometry is untouched: the marks are 7-8px in the same cells
they always occupied, and the visually-hidden outcome text stays for assistive
technology, which shape does not serve.

**The diamond is clipped, not rotated, and measurement is why.** The first
implementation used `transform: rotate(45deg)`. At coarse 375 the probe read
the day marks' computed transform as `none` while 1440 returned the rotation
matrix, so on a phone the negative mark was a rounded square — still distinct
from a circle, but not the mark the legend was promising, and different from
what every other width showed. `clip-path` is a paint-level property with no
such caveat and no interaction with any `transform: none` rule in the
reduced-motion block. Verified as the polygon at all five configurations.

**A regression from Phase 3's own defect-2 fix, caught here.** Widening the
button colour rule to the descendant combinator fixed the white-on-teal label,
and also reached the calendar's day buttons, which pass `help=`. Every traded
day became a filled teal action button — a month of primary actions, and
precisely the treatment Analytics had already retired for being the colour
reserved for actions. It was invisible in the first sweep because DEMO_MODE
sends the Journal down a demo-data branch that renders a table and never mounts
the calendar. The day rule now states its own surface instead of inheriting
whatever the global rule happens to reach, which makes it immune in both
directions. Finding it required a throwaway seeded database; the project
database was never touched.

**The ignore rule was too broad and is now exact.** `.impeccable/` holds
durable shared context as well as a machine-local cache, so the blanket
directory ignore would have hidden config, design records, briefs, critiques,
mocks and approvals from review and from every other machine. Only
`hook.cache.json` is ignored now, at the root and in nested project copies,
and that was checked with `git check-ignore` against real probe files of each
durable shape rather than reasoned about.

**Guards.** Four new tests, mutation-tested: reverting the shape channel to
colour-only fails them on both calendar surfaces. They compare a greyscale
signature — geometry plus filled-vs-hollow, colour discarded — so a future
change that keeps three colours but collapses two shapes fails rather than
passes.

### 2026-08-08 — Phase 3: the Impeccable forensic audit and polish (Claude)

Phase 2 is approved at `7ffd9a1`; this phase starts there and changes no
approved visual decision. It is a presentation-only pass, and the four things
it fixed were all defects rather than preferences — each one shipped inside
Phase 2 and each was reproduced in a browser before it was touched.

**Method.** One bounded inspection pass, then the fixes together, then exactly
one confirmation pass, as instructed. Evidence came from headless Chrome over
CDP: a fresh browser per viewport, device metrics re-applied *after* navigation
(Chrome recomputes the mobile viewport from the loaded page, which silently
turns a "coarse 375" run into a desktop layout), and a DOM probe that composites
every text node's effective background through its ancestors — folding in
`opacity` — rather than trusting the declared pair. The 44px probe keeps the
three exclusions this app genuinely needs: off-canvas rail items, `clip`ped
visually-hidden inputs, and BaseWeb's inner 2px caret input.

That compositing is what found defect 3. A declared-pair check would have read
the calendar's day numbers as content-primary on canvas — about 15:1, a pass —
and never seen the `opacity: 0.35` sitting between them, which is the whole
defect.

**Why the two selector fixes are one fix.** `.stButton > button` misses any
button that passes `help=`, because Streamlit wraps those in a tooltip div.
The 44px floor had already been corrected for exactly this and carries a
comment saying so; the colour rule sitting 1800 lines earlier never was. So one
control in the product — Strategy's starter-playbook button — kept Streamlit's
own white label on the teal `primaryColor` fill at 1.61:1, while every other
primary button was correctly dark-on-teal. Fixing the rest state then left the
reduced-motion kill switch narrower than the rule it cancels, so `help=` buttons
would have kept animating under reduced motion; that selector is widened in the
same commit. `theme.py`'s redundant duplicate is widened too, so the two
stylesheets cannot disagree about which buttons they cover, and its comment —
which described white-on-teal on a light surface, the abandoned hybrid
direction, and the reverse of what the rule does — is corrected.

Specificity is unchanged by all of this: `.stButton button` and
`.stButton > button` are both (0,1,1), so the sidebar's outlined-button
override still wins.

**What was checked and found clean**, so the next reviewer does not re-derive
it: Partner exclusivity is airtight at the CSS level — the full-page Partner is
`display: none` from 768 up and the launcher/drawer are `display: none` to 767,
complementary with no gap and no overlap, and `display` rather than
`visibility` keeps the hidden one out of the tab order. Model output takes the
safe Markdown path with `unsafe_allow_html` off and `$` escaped so paired money
is not parsed as LaTeX. The AI Reviews skeleton preserves the note's geometry
and animates only under `prefers-reduced-motion: no-preference`, so there is no
loading-state shift and no motion to suppress. The one `outline: none` in the
tree is deliberate and replaced by a ring on the wrapper. `.tl-insight-card`
resolves its variants with tinted backgrounds and accent icons, not the 3px
coloured left borders the Phase 1C spec proposed — so PRODUCT.md's "owner
decision pending" footnote describes a conflict that implementation already
resolved correctly.

**Limitations.** DEMO_MODE data was used, so these are the seeded states, not
every real one. Contrast was measured on rendered defaults; hover, focus and
active colours were read from CSS, not photographed. The colour-only encoding
in both calendars is reported unresolved rather than fixed, because every
remedy changes approved pixels.

### 2026-08-07 — Partner amendment round 4: the sign-out key leak (Claude)

**Commit:** see `fix(partner): a queued question dies with its author's
session`. Codex's P1 privacy blocker is closed. Services, schema and the AI
boundary are untouched — the diff against `c78b2a0` for `src/tradelens/
services/` and `alembic/` is empty.

**The defect was mine, and reproduced before anything changed.** Round 3
introduced `_partner_queue` and `_partner_run`. Codex's cleanup sweeps the
prefixes `("partner_", "_partner_pending_", "secondary_partner_")` — and
neither new key matches `_partner_pending_`. Run directly against the shipped
cleanup:

```
after sign-out: {'_partner_queue': {'surface': 'page',
                 'text': 'alice private question', 'run': 1},
                 '_partner_run': 1}
LEAK: True
```

So Alice's unsent question survived her sign-out **in plain text**, together
with the counter that makes it claimable. Bob signing in to the same browser
session could have had it sent as him.

**The fix is the prefix, widened to the namespace.**
`_partner_pending_` → `_partner_`. It covers the queue, the run counter, the
retired busy/pending keys and anything added later. Enumerating the two new
names would have closed this instance and left the next one open — being
forgotten is precisely what happened.

**A structural guard so it cannot happen again.**
`test_every_partner_session_key_is_covered_by_the_cleanup` reads the prefixes
out of the cleanup's own source and checks every name the Partner writes
(`QUEUE_KEY`, `RUN_KEY`, `HISTORY_PREFIX`, `ERROR_PREFIX`, `partner_open`, the
composer keys, the chip keys) against them. A new key that no prefix covers
fails the suite rather than reaching a trader.

**Three regression tests, in Codex's order.** The exact scenario — Alice
queues, signs out, Bob signs in, the Partner advances a run — asserts that
neither surface can claim the question, on two consecutive runs in case
adjacency lined up by coincidence, and that the private text is absent from
`repr(state)` rather than merely its key being gone. A queue nested inside
some other surviving value would still be a leak.

**One cleanup, both exits.** `sign_out()` is the only caller, and account
deletion in Settings goes through it. A test now pins that: no
`session_state.clear()` anywhere in the UI, and no second `clear_session*`
function outside `auth.py`. A second cleanup path is a second place to forget
a key.

**Mutation checks, all caught:** reverting to the narrow `_partner_pending_`
prefix (the exact defect); removing the partner sweep entirely; narrowing it
to `partner_history_` only.

**Verification:** `2064 passed, 7 skipped` (was `2060/7`; +4); Ruff clean;
Black clean; `git diff --check` clean. Dev database byte-identical
(`md5 dffdb781…`). Focused Partner and auth suites — `test_auth.py`,
`test_partner_panel.py`, `test_partner_turn.py`, `test_account_deletion.py` —
147 passed. No browser run: this is session-state lifetime, which a browser
cannot show and AppTest-level state can.

**The round 3 queue/run mechanism is preserved exactly.** The only production
change is one prefix in `auth.py`, nine lines including the comment explaining
why the narrow one was wrong.



### 2026-08-07 — Partner amendment round 3: no invisible spending (Claude)

**Commit:** see `fix(partner): a queued question expires with the run that
made it`. Codex's blocker was real and is closed. Services and `auth.py` are
untouched — the diff against `c78b2a0` for both is empty.

**The defect, reproduced.** Both presentations execute server-side on every
run; CSS decides which a width *shows*, and Streamlit cannot read the
viewport. So `_partner_busy_page` / `_partner_pending_page` left behind by a
run that never finished — the trader navigated away, the socket dropped, the
tab closed — would be picked up later by the page body executing **hidden** at
a rail width, and sent. Same for the drawer at phone widths, where
`partner_open` keeps its body executing while CSS hides it. Model usage and a
bill with no visible cause.

**The fix: a queued question expires with the run that made it.**

- **One queue, not one per presentation.** `_partner_queue` replaces
  `_partner_pending_{surface}` and `_partner_busy_{surface}`. Two queues meant
  the hidden presentation had its own turn to fire.
- **The queue carries its surface**, so on `/Partner` — where both bodies
  render in one run — the hidden one cannot claim what the visible one queued.
- **The queue carries its run.** `begin_partner_run` stamps once per script
  run in the shell, before either body renders. A queue is claimable only on
  the run *immediately* after the one that made it, which is exactly the
  single rerun the two-pass pattern needs and nothing more.
- **A stale queue is discarded, not skipped** — on the healthy path too. Left
  in place it would be claimed by whichever run next landed adjacent to it.

No viewport knowledge, no JavaScript, no change to services, auth, schema or
tenant scoping. One shared conversation and the 768 breakpoint behaviour are
unchanged.

**Mutation checks — and two that did not catch on the first attempt.**

| Mutation | Caught |
|---|---|
| run-adjacency check removed | yes |
| stale queue skipped instead of discarded | yes |
| **surface check removed** | **no, first time** |
| **shell stops stamping the run** | **no, first time** |

The surface-check mutation **never applied**: my replacement string did not
match because a comment sits between the two lines. Re-applied through an
index-guided edit, the test failed correctly. The shell-stamp mutation was a
genuine **test gap** — every test drove `begin_partner_run` itself, so nothing
asserted the shell does. Two tests were added: one pins that the shell stamps
exactly once and before both bodies, the other that an unstamped session can
never claim a queue, so the failure direction is "stops sending" rather than
"sends invisibly". Both now fail under their mutations.

Recording this because it is the fourth time in this phase a mutation check
has passed for the wrong reason. A mutation that does not apply looks
identical to a guard that works.

**Browser evidence — 8 combinations, all clean.**

| Route | Width | Presentations | Page visible | **Focusables in page** | Launcher |
|---|---|---|---|---|---|
| /Partner | 1440, 1024, coarse 768 | 1 | no | **0** | yes |
| /Partner | coarse 375 | 1 | yes | 5 | no |
| /Partner reduced motion | 1440, coarse 375 | 1 | as above | 0 / 5 | as above |
| Analytics | 1440 / coarse 375 | 1 / 0 | never | 0 | yes / no |

Zero exceptions, overflow and undersized targets throughout; pointer and
reduced-motion state read back from the page. **Sending still works end to
end**: driven at coarse 375, 0 turns → chip → 2 turns, with the profile notice
preserved and Clear appearing.

**Verification:** `2060 passed, 7 skipped` (was `2052/7`; +8); Ruff clean;
Black clean; `git diff --check` clean. Dev database byte-identical
(`md5 dffdb781…`).

**The UX tradeoff, stated.** Streamlit has no server-side viewport knowledge,
so the hidden presentation still *executes* — it builds one context (a read,
never a model call) and renders into markup CSS hides. Preventing invisible
model usage took priority, as instructed, and that is now structural: a hidden
surface cannot initiate `send_turn`, cannot consume usage, and cannot mutate
the queue except to discard a stale entry it owns. The remaining cost is one
redundant database read per hidden render. Removing it would need client
viewport knowledge, which means JavaScript.



### 2026-08-07 — Partner amendments round 2 (Claude)

**Commit:** see `fix(partner): safe context failure, no auto-send, bottom-nav
page`. Starting point `ebdba27`. Codex's remediation is untouched —
`git diff c78b2a0 -- src/tradelens/services/ src/tradelens/ui/components/auth.py`
is empty and the zero-trade send gate still stands.

All four findings from Codex's review of `ebdba27` were real. Test-first: 20
tests were written and failing before any implementation.

**1. A failed context became the no-trades state.** `_availability` caught the
adapter's exception and left `context = None`, which the availability rules
read as zero trades — so a database failure told a trader with a full journal
to go and log one, under a **New Trade route that fixes nothing**. The failure
now travels as `context_failed=True` rather than being inferred from a `None`
context, because `None` is also what an ownerless session produces and those
two need different answers. New `CONTEXT_UNAVAILABLE` state, no route, and the
ordering is stated: no owner, no model, no context, no trade.

**2. An interrupted two-pass send could auto-send later.** If availability
changed between queueing and sending, the not-can-send branch returned before
the busy block — leaving `_partner_pending_*` and `_partner_busy_*` set. A
later pass that found availability restored would send the question the trader
had long since walked away from, at their cost. The queue is now discarded on
that branch and the discard is reported rather than silent.

**The regression test needed a better fake, and Codex was right to ask.** The
round-1 fake returned from `rerun()` and **copied** session state. Both are
wrong: a pass that reruns is over, and session state persists across reruns.
Copying meant a two-pass test was really running two first passes, which is
exactly how the defect survived. `_RealisticSt` raises from `rerun()` and
shares the caller's dict; the test now drives pass A (unavailable) and pass B
(healthy) over one session and asserts the model was never called.

**3. The Strategy Profile notice was inside the empty-state branch**, so the
reason a trader's answers were thin vanished the moment they asked anything.
Moved out. Proved in a real browser: after clicking a suggestion at coarse 375
the conversation shows 2 turns and the notice **and** its route are still
there, alongside the new Clear control.

**4. The full-page Partner rendered on desktop.** Round 1 suppressed the
shell's Partner on `/Partner`, which guaranteed non-coexistence but left the
phone presentation on a rail width — as Codex said, that is not what the
specification asks for, and I should not have called it satisfied.

**The approved behaviour is implemented, without JavaScript and without hidden
tabbable widgets.** Two complementary media queries:

- `@media (min-width: 768px)` hides `.st-key-tl_partner_page`
- the existing phone breakpoint hides the launcher and drawer

`display: none` is what does the hiding, and it removes an element from the tab
order and the accessibility tree — not `visibility`, not a transform. The
round-1 `with_partner` flag is deleted with the approach that needed it; a
parameter no caller passes is one that rots.

**Measured, not asserted** — the claim that mattered most:

| Width | Page visible | **Focusables inside the page** | Launcher | Presentations on screen |
|---|---|---|---|---|
| 1440 fine | no | **0** | yes | **1** |
| 1024 fine | no | **0** | yes | **1** |
| coarse 768 | no | **0** | yes | **1** |
| coarse 375 | **yes** | 5 | no | **1** |

Zero focusables inside the hidden page at every rail width is the evidence that
`display: none` is not merely visual. Reduced motion re-checked at 375 and
1440: same result, `prefers-reduced-motion` read back from the page. Zero
exceptions, overflow and undersized targets throughout. Analytics still carries
its launcher and never renders the page container.

**Six mutation checks, all caught:** the failed context falling through to the
trade count; the panel dropping the failure signal; the interrupted question
left queued; the notice moved back inside the empty state; the full page shown
at rail widths; the page body losing its key.

**One self-inflicted defect worth recording.** The first version of the
desktop-note rule created a **second, early** `@media (max-width: 767px)`
block. `test_the_44px_floor_is_not_hidden_behind_the_phone_breakpoint` locates
the phone breakpoint as the *first* such occurrence, so every global 44px rule
suddenly looked phone-only. The rule now lives in the one phone breakpoint the
file has, beside the launcher rule it is the counterpart of — better structure,
and the test was right.

**Two Strategy tests failed once under load** (`test_strategy_empty_profile_
reports_zero_completion`, `test_correcting_the_name_saves_and_clears_the_
error`) while a Streamlit server and Chrome instances were running alongside
the suite. Both pass in isolation and in a quiet full run. Recorded as
subprocess timing under load, not as a product defect — and not silently
dropped.

**Verification:** `2052 passed, 7 skipped` (was `2033/7`; +19); Ruff clean;
Black clean (88 files); `git diff --check` clean. Dev database byte-identical
(`md5 dffdb781…`). App and Chrome stopped. `.impeccable/` untouched.

**Limitations, unchanged and stated.**

1. Streamlit has no server-side knowledge of the viewport, so at a rail width
   the page body is still **built** (including one context read) and then
   hidden by CSS. Avoiding that needs JavaScript, which this phase forbids.
2. The `aria-live` sending status is verified under AppTest, not in the
   browser: DEMO_MODE returns canned output instantly, so the in-flight window
   closes before a probe can sample it.
3. The context-failure state is proved by a panel test driving a real raising
   adapter, not in a live browser — forcing a database failure against the
   running app was out of scope.



### 2026-08-07 — Partner presentation amendments (Claude)

**Commit:** see `feat(partner): honest availability, clearing, and one Partner
per width`. Starting point `c78b2a0`. **Codex's safety remediation is preserved
exactly** — `services/partner.py`, `components/auth.py` and the zero-trade
send-path gate are byte-unchanged; `git diff c78b2a0 -- src/tradelens/services/`
is empty, and `NO_TRADES_ERROR` still refuses a turn before the model is
called.

Test-first throughout: 13 availability/clearing tests were written and failing
before the implementation existed.

**The decisions are pure, so they can be proved without a browser.**
`partner_availability(*, user_id, ai_ready, context)` and
`clear_conversation(...)` live in `partner_turn.py`, which holds no Streamlit.
The panel renders what they decide.

| Requirement | Behaviour | How it is proved |
|---|---|---|
| Ownerless legacy account | No composer, no actionable launcher; states `Sign in to use the AI Partner` | Rendered output, plus a boot test |
| **Tenant isolation not weakened** | `build_global_partner_context` is **never called** without a positive integer owner | A spy asserts zero calls |
| AI unavailable | Launcher renders **disabled** with the reason; composer withheld | Rendered output, and in the browser with no key |
| No completed trades | State plus a **New Trade** route; no composer | Rendered output; route asserted |
| No Strategy Profile | A `role="status"` notice plus a **Strategy Profile** route; composer stays enabled | Rendered output; browser at four widths |
| Clear conversation | Immediate; drops history, error, pending suggestion, busy flag and composer state, **on every surface** | Pure test, scoped to one owner |
| Two-pass sending | Composer and chips disabled on the second pass; turns stay; polite `aria-live` status | Rendered output on the busy pass |

**One data path.** Availability reads the context once per render through the
one approved adapter and reuses it for every decision on the surface. It is
deliberately **not** reused for the send — `send_turn` builds its own, because
what was true when the page painted is not necessarily true when the question
is asked.

**A missing model outranks a missing trade.** Both are true on a fresh install,
and only one of them is something a trader can fix by logging a trade. The
unavailable copy names no secret: `AI_UNAVAILABLE` is
`"The AI Partner is unavailable right now."`, and a test fails if `ANTHROPIC`
or the word "key" appears in it.

**Turns render before anything that can refuse**, so whatever else a pass is
doing — refusing, sending, or reporting a failure — the conversation does not
move. `Clear conversation` is offered even when the Partner can no longer send,
so a trader whose key was removed can still dismiss what they are looking at.

**Responsive exclusivity is decided server-side, from the route.**
`render_sidebar(with_partner=False)` on `7_Partner.py`. A CSS rule would have
to guess the width, and hiding a rendered drawer leaves its widgets in the tab
order. **Measured, not assumed:** on `/Partner` the launcher and drawer are
**not in the DOM at all** at 1440, 1024, coarse 768 and coarse 375 — so the
full page and the global Partner can never both be present. No JavaScript was
needed and no forbidden fallback was required.

**Six mutation checks, all caught:** building a context for an ownerless
session; offering a composer when the Partner cannot send; leaving the composer
live while sending; naming the secret in the unavailable copy; clearing only
one surface; and letting the shell render its Partner on the Partner route.

**Browser evidence.** Pointer and reduced-motion state read back from the page.

| Case | Widths | Result |
|---|---|---|
| `/Partner` exclusivity | 1440, 1024, coarse 768, coarse 375 | launcher and drawer absent from the DOM; `h1` "AI Partner"; 1 composer |
| Missing-profile notice | same four | `role="status"` notice renders; composer enabled |
| Launcher, AI available | 1440 | 159×44, enabled, focusable |
| Launcher, **no key, demo off** | 1440 | **disabled**, note reads "The AI Partner is unavailable right now." |
| Reduced motion | 1440 | `prefers-reduced-motion` asserted true; clean |

Zero exceptions, zero horizontal overflow, zero undersized targets in every
run.

**Two contract changes, both because behaviour changed rather than to make a
test pass.** The boot test expecting the empty-state scope copy now expects the
ownerless message, because the harness boots authenticated with no user id —
which is precisely the ownerless case; a second boot test presets an owner and
asserts the no-trades state. And
`test_the_authenticated_user_id_is_what_reaches_the_send_path` scanned
`render_partner_body` for `current_user_id`, which moved into the availability
helper; it now asserts, by sending, which owner the send path is given.

**Limitations, stated rather than smoothed over.**

1. The `aria-live` sending status is verified under AppTest, not in the
   browser: DEMO_MODE returns canned output instantly, so the in-flight window
   is closed before a probe can sample it. Same instrument split as Task 12.
2. The browser probe reports a disabled launcher as focusable because it does
   not filter `:disabled`. The browser removes disabled buttons from the tab
   order; that field is **not** evidence. The reason is rendered as text
   precisely because a disabled control's tooltip reaches nobody on a keyboard.
3. The ownerless state is proved by boot test and rendered output, not in a
   live browser — the signed session always has an owner.

**Verification:** `2033 passed, 7 skipped` (was `1997/7`; +36); Ruff clean;
Black clean (88 files); `git diff --check` clean. Dev database byte-identical
(`md5 dffdb781…`). App and Chrome stopped. `.impeccable/` untouched.



### 2026-08-07 — Comprehensive Codex review remediation

**Scope:** Codex-owned AI safety, grounding, authentication/session lifecycle,
and CI-format remediation only. No schema, model routing, prompt, tenant query,
or design-direction change.

**Verified defects corrected:**

- The Partner post-check accepted explicit position instructions that avoided
  its original exact marker list. Instruction-shaped patterns now redirect to
  the existing retrospective response; three reproduced outputs are pinned.
- The global Partner ignored `completed_trade_count` and called/logged the model
  with no completed records. `send_turn` now stops before model and usage calls
  when the approved context adapter reports zero completed trades.
- Sign-out copy promised the conversation ended, but authentication cleanup left
  history, errors, pending suggestions, composer state, and drawer-open state in
  `session_state`. One pure cleanup boundary now removes all ephemeral Partner
  keys before ending authentication.
- The comprehensive gate found two committed tests that Black would reformat;
  both were formatted without changing their assertions.

**TDD evidence:** the five new cases failed on the reviewed branch for the
expected reasons, then passed after the minimal changes. Focused Partner/auth
verification: `205 passed`. Complete suite: `2002 passed, 7 skipped`.

**Claude-owned presentation work still required before Phase 2 approval:**

1. Do not render an actionable launcher/composer for an ownerless legacy account;
   show accurate account-required availability without weakening user scoping.
2. Gate the surface with the existing AI-availability helper instead of opening
   a dead end.
3. Render the specified no-trades and no-Strategy-Profile states using only the
   approved context adapter; no second data-access path.
4. Add immediate Clear conversation and the two-pass sending state (disabled
   composer, stable prior turns, polite live status).
5. Make the full-page Partner presentation bottom-nav-only. A desktop direct
   `/Partner` route must not coexist with the global launcher/drawer.

Claude must not alter `services/partner.py`, AI prompts/routing, authentication
semantics, tenant scoping, database schema, or cost logging. Return to Codex for
the final Phase 2 gate before Impeccable.

### 2026-08-06 — Phase 2 COMPLETE: Task 17 and the final handoff (Claude)

**Commit:** see `docs(audit): re-score the 10K checklist against the dark
workspace`. **Tasks 1–17 are done. Phase 2 is ready for the comprehensive
Codex review.**

**Phase 2 commits, in order:**

| Commit | Task |
|---|---|
| `eaeca32` | 10 — Analytics, one instrument shape |
| `df07a11` | 11 — the pure review document model |
| `cd1273c` | 12 — the AI Reviews reading shell |
| `c8952dd` | 13 — Strategy, Settings, auth surface |
| `db6be6d` | 14 — the AI Partner desktop drawer |
| `3de1f43` | 15 — the AI Partner phone destination |
| `ac8f20e` | 16 — the cross-page audit |
| this one | 17 — the 10K re-score |

(Tasks 1–9 landed in earlier sessions; `db54c56` and `85ee83a` are the two
session-boundary handoffs.)

**Final verification:** `1997 passed, 7 skipped` (Phase 2 start: `1833/7`;
**+164 tests**). Ruff clean. Black clean (88 files). `git diff --check` clean.
Dev database byte-identical throughout (`md5 dffdb781…`, `Jul 31`) — every
browser run used a scratchpad **copy** pointed at by `DATABASE_URL`.

**The re-score: seven of eight targets met.**
Full working in `docs/superpowers/audits/2026-08-06-phase2-dark-rescore.md`;
summary appended to `docs/audits/2026-07-21-10k-checklist-business-audit.md`.

| # | Item | Baseline | Target | Result |
|---|---|---:|---:|---:|
| 01 | Point of view | 7.5 | 8.5 | 8.5 |
| 02 | Typography | 8.0 | 8.5 | 8.5 |
| 03 | Restrained colour | 8.5 | 9.0 | 9.0 |
| 04 | Hierarchy that breathes | 6.5 | 8.5 | 8.5 |
| 05 | Imagery with intent | 6.5 | 7.5 | **6.5 — NOT ATTEMPTED** |
| 06 | Motion that whispers | 6.0 | 7.5 | 7.5 |
| 07 | Mobile, designed not shrunk | 5.5 | 7.5 | 8.0 |
| 08 | The invisible expensive stuff | 4.5 | 7.0 | 7.0 |

Streamlit product polish 64/100 → 80/100. Business scores untouched — this
phase did not touch the funnel, policies or activation.

**Item 05 was in scope and was not done.** Task 17 Step 2 asks for re-captured
product screenshots from coherent seeded data; that was not performed, so the
item keeps its baseline rather than inheriting credit from the product
improvements around it. The capture harness exists and is proven; what remains
is listed in the re-score.

**Open items for the Codex review**, in the order they matter:

1. **`aria-sort` is `null`** on Streamlit's dataframe column headers, and its
   **four toolbar controls carry no accessible names**. Spec §6.3 and §12
   require both. Fixing either needs JavaScript injection — forbidden this
   phase — or replacing the ledger with an authored table. Carried unchanged
   through Tasks 9, 10, 12, 13 and 16, and **no task was expanded into a ledger
   replacement**. This is Codex's call.
2. **Focus visibility is not verified.** The sweep used programmatic
   `element.focus()` and `:focus-visible` does not match it, so its counts
   measure the probe, not the product. Needs real `Tab` dispatch.
3. **Tab order is not verified** by key dispatch. The Partner drawer's "Close
   is the first tab stop" rests on DOM order.
4. **The scoping audit matches call sites by name**, so
   `build_context=build_global_partner_context` — a reference, not a call — is
   invisible to it. Scoping is enforced and separately tested; flagged so Codex
   can decide whether the audit should follow references.
5. **The Partner drawer is non-modal** by necessity: a focus trap needs
   JavaScript, so it claims no `aria-modal` and draws no scrim.
6. **Per-finding confidence badges** are no longer rendered beside each finding
   — the consequence of §7.2's one-rail-per-note rule. The note's stated
   confidence is the **floor** across its findings, never the peak.
7. One adjacent target pair under 8 px on Journal at 768 and Strategy at all
   widths, both halves of one field group.
8. `TL_RULE = #AFBEC0` is still a light-surface value; `theme.py` compatibility
   names still lie; the note-surface CSS comment still says "light workspace".

**What Phase 2 found that the plan did not.** Recorded because the pattern
recurred: **the plan's own tests passed against unchanged code in four of the
eight tasks**, and two supplied implementations carried defects their own
suites could not see — the review parser's colliding ids and length-blind
fences, and the Partner's abandoned-question retry, which would have sent the
model two questions and billed the trader for both. Three contracts in this
phase were broken by a **comment about the thing they guard**. Six CDP
measurement corrections are recorded across the log; the fifth and sixth
produced false negatives, and every earlier claim they touched was re-measured
rather than assumed to still hold.

**State:** app and Chrome processes stopped. `.impeccable/` untouched and
unstaged. Nothing pushed, merged, or deployed. Impeccable and Emil motion work
not started.



### 2026-08-06 — Phase 2 Task 16: the cross-page audit (Claude)

**Commit:** see `fix(a11y): close the defects the cross-page dark audit
reproduced`. Task 16 only; Task 17 not started.

`tests/test_dark_accessibility.py` was written **before** anything was fixed,
transcribed from the plan, and it passes 25/25. The plan recorded `16 passed,
5 skipped` on 2026-08-04; the five composited-contrast cases now activate
because Task 1 landed, and the page-handler check gained `7_Partner.py`.

**An audit that passes everything on its first run proves nothing, so it was
mutation-checked itself.** All three defect classes are genuinely detected:

| Injected defect | Result |
|---|---|
| a broad handler rendering the exception it caught | fails on that page |
| `get_trades(...)` with the owner removed | fails, naming file and line |
| a dead entry in the payload-scoped allowlist | fails |

**Browser sweep: 8 destinations × 4 widths = 32 runs.** Coarse-pointer state
read back from the page on every coarse row.

**Zero rendered exceptions, zero document-level horizontal overflow, and zero
undersized targets — on all 31 runs that completed.** One run (Partner at
coarse 375) failed to parse on the first pass; re-run in isolation it is clean,
so it was a transient Chrome failure rather than a finding.

**Two real defects, both reproduced at all four widths, both fixed:**

1. **Overview skipped `h2 → h4`.** `overview_bands.render_ranked_list` emitted
   `<h4 class="tl-ranked-title">` inside a band whose own heading is an `<h2>`.
   Every style comes from the class, so the level was free to be correct.
2. **Strategy skipped `h1 → h5`.** The playbook form's first section heading
   was `#####`. **The first correction was wrong and the browser caught it:**
   `###` still skipped `h1 → h3`, because nothing sits between them. It is
   `##`. Both pages now measure a clean sequence — Overview
   `[1,2,2,2,3,3,2,2]`, Strategy `[1,2]`, zero skips.

That second fix is the reason the guard for it asserts the *sequence has no
gap* rather than `max(level) <= 3`. The number was easier to satisfy than the
property, and satisfying it left the defect in place.

**A third comment-brittleness case, for the record.** The guard's first form
asserted `"#####" not in source` — and the comment explaining why the marker
was wrong contained the marker. It now reads heading levels out of the
markdown calls through the AST. This is the third contract in this phase
broken by a comment about the thing it guards.

**Two probe limitations, reported rather than dressed up as findings.**

1. **Focus-ring counts are not evidence.** The sweep calls `element.focus()`,
   and `:focus-visible` does not match programmatic focus — so the non-zero
   "controls without a focus ring" counts (Journal 5, Strategy 8, Settings 5)
   measure the probe, not the product. Confirming focus visibility needs real
   `Tab` key dispatch. **Not claimed as verified.**
2. **Target separation** flagged 1 adjacent pair under 8 px on Journal at 768
   and on Strategy at all widths. Both are adjacent form controls inside one
   Streamlit row; whether the 8 px rule is intended to apply between two halves
   of a single field group is a judgement the audit cannot make. Recorded, not
   silently fixed.

**Tab order was not verified by key dispatch** and is therefore not claimed.
The Partner drawer's "Close is the first tab stop" is asserted from DOM order
and from `render_partner_drawer` rendering Close before the conversation, which
is weaker than walking focus. Left for Codex.

**Nested-route `_stcore` 404s:** not re-checked this session. They were
recorded in the preflight as baseline infrastructure noise and are not a target
of this phase.

**Scope discipline.** `git status --short` at commit time showed exactly the
audit file plus the two files a reproduced defect required. Nothing else.

**Verification:** `1997 passed, 7 skipped` (was `1972/7`; +25); Ruff clean;
Black clean; `git diff --check` clean. Dev database byte-identical
(`md5 dffdb781…`).

**One note for the security gate.** The scoping check matches call sites *by
name*, so `build_context=build_global_partner_context` in `partner_panel.py`
— a reference, not a call — is invisible to it. The scoping is enforced
elsewhere and tested: `send_turn` always passes `user_id=`, the adapter
rejects a non-positive owner before opening a session, and
`test_the_authenticated_user_id_reaches_the_context_adapter` pins it. Flagged
so Codex can judge whether the audit should also follow references.



### 2026-08-06 — Phase 2 Task 15: the AI Partner phone destination (Claude)

**Commit:** see `feat(partner): full-page destination at bottom-navigation
widths`. Task 15 only; Task 16 not started.

New route `pages/7_Partner.py`, and `/Partner` added to `MOBILE_MORE` between
Strategy Profile and Settings — work, then reflective work, then the quiet
utility. The page renders the masthead and `render_partner_body(st,
surface="page")` and does nothing else: it names no service, no adapter and no
logger, which is asserted rather than assumed.

**One conversation, two surfaces.** History is keyed by user, never by
surface, so a question asked in the drawer is on the phone page and back
again. `history_key` takes no surface argument, and that is a test — keying by
surface would give a trader two conversations with no way to tell which one
they were in.

**Mutual exclusivity is structural, not a CSS trick.** The launcher is
`display: none` below 768 and the bottom bar appears only below 768, so there
is no width at which a floating overlay could collide with the `More` sheet.
Asserted by walking the phone media query's actual extent: splitting the CSS
on `}` puts the `@media` opener *inside* the chunk that carries the launcher
rule, so asking what encloses that chunk answers about the text before the
query. Measured both ways in the browser — at coarse 768 the launcher is
visible and focusable and the bar is absent; at coarse 375 the reverse.

**`7_Partner.py` was added to `ALL_PAGES`, which is not bookkeeping** — that
list drives the parametrised boot test, so a page absent from it is a page
nothing proves boots.

**One existing contract updated, not weakened.**
`test_the_fifth_mobile_slot_is_more_not_a_renamed_settings_link` enumerates the
`More` list exactly; Task 15 adds an entry to it. The property it protects —
Settings is not the fifth tab, and everything else is reachable under More — is
unchanged, and Settings still sits last.

**Browser evidence at coarse 375 and coarse 768.** Pointer state read back
from the page.

| Check | Result |
|---|---|
| `More` closed on arrival | yes, on both `/Partner` and `/Analytics` |
| `/Partner` marked current while on it | `aria-current="true"`; not marked from `/Analytics` |
| Open `More` sheet targets | four links at 190×44, **zero under 44** |
| Bottom bar | 51 px tall, reserves its own inset (`navBottomGap` 0) |
| Floating launcher at 375 | not visible **and not focusable** |
| Launcher at coarse 768 | visible and focusable, bottom bar absent |
| Horizontal overflow | none — `scrollWidth` 375 = `innerWidth` 375 |
| Overflow / undersized / exceptions | 0 / 0 / 0 at every combination |

The page renders its masthead, one chat field and the three retrospective
chips, with `h1` reading "AI Partner".

**Persistence** is proved through the same subprocess boot harness, with the
history preset before the first run — exactly the state a multipage navigation
leaves behind. Mutation-checked: a page that resets the history instead of
reading it fails.

**Mutation checks:** history reset on arrival (1 failure), `/Partner` removed
from `MOBILE_MORE` (2), the phone launcher un-hidden (2).

**Verification:** `1972 passed, 7 skipped` (was `1961/7`); Ruff clean; Black
clean; `git diff --check` clean. Dev database byte-identical
(`md5 dffdb781…`).

**Unresolved concerns.** Unchanged from Task 14: the drawer is non-modal by
necessity. Carried forward: dataframe `aria-sort` is `null` and its four
toolbar controls have no accessible names; the ledger was not replaced.

### 2026-08-06 — Phase 2 Task 14: the AI Partner desktop drawer (Claude)

**Commit:** see `feat(partner): a global desktop drawer on the approved
service`. Task 14 only; Task 15 not started.

Two new modules: `components/partner_turn.py` (the send path, Streamlit-free)
and `components/partner_panel.py` (rendering). The Partner rides
`render_sidebar`, which every page already calls and which already renders the
mobile bar outside the rail — one wiring, so a new page cannot forget it and an
old one cannot get a second copy.

**Boundaries held, and each is a test rather than a promise.** No SDK import,
no endpoint, no query of its own; context only from
`build_global_partner_context`; `partner_reply(..., per_trade_qa=False)`; usage
logged from exactly one place; the authenticated `user_id` on every call.
`partner.py`, `partner_context.py`, `cost.py` and every prompt are untouched.

**Six send-path guarantees, all mutation-checked** by reverting each and
confirming the suite fails: context assembly inside the containment (2
failures), usage logging contained and *after* the reply is stored (1),
history projected to role/content before the model sees it (1), labels stored
per turn (1), the ownerless-send refusal (5), and the retry rule (2). Five
panel guards likewise: unescaped labels, a claimed `aria-modal`, Close moved
after the conversation, `visibility` instead of `display` on the phone, and a
page rendering its own launcher.

**One real defect the plan's design would have shipped.** A failed turn leaves
the question in history so the trader does not retype it — correct, and the
plan says so. But nothing removed it when they *did* retype, so the next call
sent **both** questions: the model would answer a two-question prompt and the
trader would be billed for the abandoned one. `_drop_abandoned_question` drops
a trailing turn only when it is a user turn, so a completed exchange is never
touched. Three consecutive failures now leave exactly one question, not three.

**A second: an ownerless send.** `build_global_partner_context` rejects a
missing owner by raising, which the containment would report as "temporarily
unavailable" — sending a signed-out trader to retry something that cannot
succeed. It is refused by name now, before any session opens.

**Two of the plan's tests could not pass as written, for the same reason.**
`test_usage_is_logged_exactly_once_per_completed_response` counts the substring
`log_ai_usage(`, which also matches a definition, a wrapper and a comment; it
reports 2 for a module with one call site. `test_partner_reply_is_called_in_
general_reflective_mode` looks for `per_trade_qa=False` in the panel, but the
call lives in the send path — which is the whole point of the split. Both are
asserted where the behaviour is.

**Three of my own tests were brittle in the way this phase keeps finding.** A
source scan for `aria-modal` failed on the docstring explaining why the
attribute is absent — the third time a contract has been broken by a comment
about the thing it guards. Those now assert **rendered output** through a small
fake `st`, which is stronger and cannot be broken by prose.

**Three design-system guards caught the new CSS and were right every time:**
unproven testids (`stChatInput`, `stChatInputSubmitButton` — now in the proven
set with the measurement that justified them), a semantic coloured side border
(replaced with the dot `.tl-error-box` already established), and raw `rgba()`
outside the token block (now `--tl-shadow-float` / `--tl-shadow-overlay`).

**A real 44px defect, found by measuring.** The chat control is not a
`.stButton`, so the drawer's own floor never reached it: measured at 1440 the
field was **378×40** and its submit button **40×40**. Fixed at every width
rather than scoped to the drawer, because Task 15's phone destination renders
the same control. Now 378×44 / 44×44.

**A sixth CDP correction.** `offsetParent` is **always null for a
position:fixed element**, so the visibility check reported the launcher and
drawer as hidden at every width. Fixed elements are now measured by computed
style plus layout box. The probe also flagged a "scrim": it is a 0×0
non-interactive SVG `<g>` whose class contains "overlay" — a false positive,
and **there is no blocking scrim**, as the non-modal design requires.

**Browser evidence — 8 combinations, all clean.** Pointer and reduced-motion
state read back from the page.

| Route | Width | Launcher in DOM | Visible | Focusable | Drawer opens | Close first | aria-modal | ovf/und/exc |
|---|---|---|---|---|---|---|---|---|
| Analytics | 1440 | yes | yes | yes | yes | yes | 0 | 0/0/0 |
| Analytics | 1024 | yes | yes | yes | yes | yes | 0 | 0/0/0 |
| Analytics | coarse 768 | yes | yes | yes | yes | yes | 0 | 0/0/0 |
| Analytics | coarse 375 | yes | **no** | **no** | hidden | — | 0 | 0/0/0 |
| Journal | 1440 / coarse 375 | as above | | | | | 0 | 0/0/0 |
| Analytics, reduced motion | 1440 / coarse 375 | as above | | | | | 0 | 0/0/0 |

At coarse 375 the launcher is in the DOM but neither visible nor **focusable** —
`display: none`, deliberately, because `visibility: hidden` or an offscreen
transform would leave a keyboard user able to reach a control they cannot see.
The phone destination is Task 15.

Open/close was driven end to end: launcher → drawer renders with Close first,
three retrospective chips and one chat field → Close → drawer leaves the DOM
entirely and the launcher returns. Closed means *not rendered*, so its widgets
are not in the tab order at all.

**Verification:** `1961 passed, 7 skipped` (was `1907/7`; +54); Ruff clean;
Black clean; `git diff --check` clean. Dev database byte-identical
(`md5 dffdb781…`) — the browser ran against a scratchpad **copy**.

**Unresolved concerns.** The drawer is non-modal by necessity: a focus trap
needs JavaScript, so it claims no `aria-modal` and draws no scrim. Recorded as
a deliberate reading of §8.2 rather than an omission. Carried forward
unchanged: dataframe `aria-sort` is `null` and its four toolbar controls have
no accessible names; the ledger was not replaced.

### 2026-08-06 — Session boundary: Tasks 12–13 done, resume at Task 14 (Claude)

Tasks 12 (`cd1273c`) and 13 (`c8952dd`) are committed with full evidence.
Tasks 14–17 are not started. This is a **context boundary, not a review
gate** — no interim Codex review is requested, and the comprehensive review
stays scheduled after Task 17. The lock is `NONE` only so a fresh session can
claim it cleanly.

**Resume at Task 14 (the AI Partner desktop drawer).** It is the largest task
in the plan — 915 lines, two new modules from scratch, a service-backed AI
surface with non-negotiable safety boundaries — which is why it was not begun
on a partial context budget rather than left half-built.

**Task 14 pre-audit, so the next session does not repeat it. Everything it
consumes already exists and is green:**

| Interface | Location | State |
|---|---|---|
| `build_global_partner_context(*, user_id)`, `PartnerContext`, `PartnerEvidenceSource` | `services/partner_context.py:132`, `:45`, `:34` | present (Task 4) |
| `partner_reply(messages, *, trade_context, strategy_profile, image_b64, per_trade_qa)` | `services/partner.py:272` | present, signature matches the plan exactly |
| `PartnerError` | `services/partner.py:135` | present |
| `TL_Z_PARTNER = 20` | `design_system.py:130`, exported as `--tl-z-partner` | present |
| `log_ai_usage(feature, usage, user_id=None)` | `services/cost.py:41` | present |

`tests/test_partner.py` + `tests/test_partner_context.py` — **57 passed** —
are the contract Task 14 must not break.

**No Partner UI exists yet.** `ui/components/` has no partner module and
`app.py` never mentions one, so Task 14 is a genuine from-scratch build of
`partner_panel.py` (rendering) and `partner_turn.py` (Streamlit-free send
path) plus their two test files and the launcher/drawer CSS. Nothing needs
retargeting first.

**Boundaries to carry in, from handoff §1 — these are scope, not style.**
Reuse `partner_reply(..., per_trade_qa=False)`; no new endpoint, no new system
prompt, no direct Anthropic import from a page or component; every service
query takes the authenticated `user_id`; usage logged exactly once per
completed response; the post-trade scope guard stays, so never signals,
predictions, entries or advice; model output goes through Streamlit's safe
Markdown path with HTML off, and any surrounding authored HTML escapes its
values. The drawer applies at **every sidebar-navigation width (≥768)** — there
is no mobile launcher and no bottom sheet; the phone destination is Task 15.

**What a fresh session needs for the browser.** The CDP driver lives in the
session scratchpad, not the worktree, and now carries **five** measured
corrections — the four in the Task 8/9 entries plus the clip-path false
negative recorded in the Task 13 entry below, which is the first one to have
hidden a real defect. Rebuild it from those notes. Also: this worktree's
database has no trades owned by user 1, so seed a scratchpad **copy** and set
`user_id = 1` there to reach the Journal and AI Reviews with data; Analytics
falls back to `get_demo_df()` and does not need it.

**Verification at this boundary:** `1907 passed, 7 skipped`; Ruff clean; Black
clean; `git diff --check` clean. Dev database byte-identical
(`md5 dffdb781…`, `Jul 31`). App and Chrome processes stopped. `.impeccable/`
untouched and unstaged.

### 2026-08-06 — Phase 2 Task 13: Strategy, Settings, auth surface (Claude)

**Commit:** see `feat(ui): a neutral Danger Zone perimeter and fillable auth
fields`. Task 13 only; Task 14 not started.

**Step 1 first, as the plan asks.** `tests/test_strategy.py`,
`tests/test_app_settings.py` and `tests/test_account_deletion.py` — 41 tests
covering starter persistence, blank-name refusal, corrected save,
untouched-field preservation and contained write failure with no DSN leak —
were green before anything changed and are green after.

**One of the plan's two tests failed for the wrong reason; the other was
vacuous.**

- `test_the_danger_zone_is_one_contained_perimeter` searched CSS blocks
  containing the string `tl-danger-zone` for `--tl-line-strong`. The perimeter
  is not on that class — it is on the **keyed container**,
  `.st-key-tl_danger_zone`, spelled with underscores, because only the
  container encloses the two expanders and their buttons. So the test failed
  while a perimeter was present, and would have kept failing after any correct
  fix.
- `test_warnings_outside_the_danger_zone_are_not_red` asserted
  `"TL_DANGER" not in outside(source, "danger_zone")`. There is no function
  named `danger_zone`, so `outside()` returns the whole file — measured, 16187
  of 16187 characters — and the page never names `TL_DANGER` at all, because
  its colour comes from CSS classes. It passed with the assertion doing
  nothing. Replaced with a check of the CSS, where the colour actually lives.

**Real finding 1 — the perimeter was spending the danger hue.** The rule read
`border: 1px solid var(--tl-danger)` while the comment directly above it
claimed "the hue stays on the heading and the buttons". Code and comment
disagreed, and spec §6.7 names `TL_LINE_STRONG` for the perimeter. A trader
opening Settings to change a timezone met a red-framed slab, so the colour
meant to mark "this one is irreversible" was already spent by the time they
reached the button that is. Now `--tl-line-strong`, measured in the browser as
`rgb(92, 110, 119)`, with the title still `rgb(245, 101, 101)`.

**Real finding 2 — no credential field on the auth screen declared an
autocomplete purpose.** Zero occurrences across sign in, create account and
reset. Worth separating from framework limitations like `aria-sort`:
`st.text_input` on the pinned streamlit==1.50.0 **does** take `autocomplete`,
checked against the installed signature before writing anything. Without it a
password manager cannot reliably offer a saved credential, and the browser may
offer to save a new password over an existing one on the sign-in form. Seven
fields now declare the purpose the HTML spec defines — `current-password` on
sign in, `new-password` where a password is being set — and the invite code
deliberately declares none. Verified in the DOM, not just in source.

**Real finding 3 — every auth input was 42px, and the probe was hiding it.**
`.st-key-tl_auth_card [data-testid="stTextInputRootElement"] input` set
`min-height: 42px`, which carries both the card key and the root-element
testid and so outranked the app-wide 44px floor. Two pixels under the §12
minimum on the first surface a user ever meets, on all five inputs.

**A fifth CDP measurement correction, and this one had produced a false
negative.** The undersized probe's exclusion read
`(clip !== 'auto' && clip !== '') || clipPath !== 'none'`. The second arm
excluded **any** element carrying a clip-path, which is how five 42px inputs
were reported as zero undersized targets. Both arms must now indicate a
deliberately hidden element. **Every surface was re-measured with the
corrected probe** — Analytics, AI Reviews, Strategy, Settings, Journal and New
Trade at 1440 and coarse 375 — and all twelve are still `0` overflow, `0`
undersized, `0` exceptions, so the Task 10 and Task 12 evidence stands. The
auth screen was the only place the false negative was hiding a real defect.

**Two pre-existing contracts failed and were handled differently, on their
merits.**

1. `test_the_danger_zone_border_encloses_the_whole_container` required
   `border: 1px solid var(--tl-danger)`. That is the state Task 13
   supersedes, and spec §6.7 says otherwise. Updated to the neutral line; the
   containment property it was written to protect is untouched.
2. `test_native_widgets_are_restyled_for_the_dark_card` failed on **my own
   comment**: it scans raw CSS lines for `data-testid="st`, and a comment
   explaining which app-wide rule the scoped one overrides was read as an
   unscoped rule leaking into the app. A contract that can be broken by
   writing a comment is guarding the wrong input, so it strips comments first
   — the same treatment the danger-zone test already uses. The property is
   unchanged.

**Already correct, verified rather than changed.** Settings carries no chart,
no promotional banner and no `type="primary"` CTA. Strategy keeps its five
accordions. The auth screen already has a real segmented control for the
sign-in/create-account switch and a 44×44 show/hide password button — my first
probe reported `modeControl: 0` because it queried for a radio; the page was
right and the probe's selector was wrong.

**Browser evidence.** Coarse-pointer and reduced-motion states read back from
the page at every applicable row.

| Surface | Widths | Overflow | Undersized | Exceptions | Notes |
|---|---|---|---|---|---|
| Strategy | 1440, 1024, coarse 768, coarse 375 | 0 | 0 | 0 | 5 accordions, inputs 44px |
| Settings | same four | 0 | 0 | 0 | perimeter `rgb(92,110,119)` at every width, 0 charts |
| Settings, reduced motion | coarse 375 | 0 | 0 | 0 | — |
| Strategy, reduced motion | 1440 | 0 | 0 | 0 | — |
| Auth (signed out) | 1440, coarse 375 | 0 | 0 | 0 | no rail, no bottom nav, no Partner; inputs 44px; autocomplete live in the DOM |

Both destructive gates were confirmed to render — `Type DELETE to confirm` and
`Type DELETE MY ACCOUNT to confirm`, two expanders inside the perimeter — and
**neither was executed**.

Strategy Name persistence was proved under AppTest rather than CDP: the name
was changed, saved, and then read back from a **fresh script run with a fresh
session**, so only the database could have carried it, and
`get_active_strategy` was checked to agree with the page. A CDP click on a
Streamlit widget drove one transition and silently failed the next in Task 9,
which is why the browser is used for geometry and AppTest for behaviour.

**Mutation checks.** Perimeter reverted to the danger hue → fails; perimeter
removed entirely → fails; sign-in password given `new-password` → fails;
`autocomplete` dropped from `login_username` → fails.

**Files changed:** `components/auth_screen.py`, `design_system.py`,
`tests/test_app_settings.py`, `tests/test_auth_screen.py`,
`tests/test_premium_page_contracts.py`, and this handoff. `git add -A` not
used; untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

**Unresolved concerns.** Carried forward unchanged: `aria-sort` is `null` on
Streamlit's dataframe headers and its four toolbar controls have no accessible
names — both need JavaScript injection (forbidden) or an authored table, and
Task 13 was not expanded into a ledger replacement. The note-surface CSS
comment still describes "the light workspace"; left for the Task 16 sweep.

### 2026-08-06 — Phase 2 Task 12: one reading shell, safe regeneration (Claude)

**Commit:** see `feat(ai-reviews): one reading shell and non-destructive
regeneration`. Task 12 only; Task 13 not started.

**All four of the plan's Task 12 tests failed against the unchanged page** —
the first task in this phase where that is true. Transcribed verbatim and run
before anything changed, so the pre-audit findings carried in from the last
session are confirmed by execution rather than by reading.

**D5 was data loss, and it is now proved by doing it.** `_render_daily_lens`
popped the cached note before calling the generator, and `_run_daily_debrief`
writes its replacement only on success — so a `DebriefError` left the trader
with no review at all. Weekly never did this and said so in a comment.

The plan proposed comparing the source offsets of `.pop(` and
`_run_daily_debrief(` inside one function. That passes for a page that pops the
key one line later, in a helper, or under another name, and it says nothing
about what is on screen. `tests/insights_regen_check.py` clicks the real
control under AppTest with the real generator raising and reads the rendered
page. **Mutation-checked:** restoring the pop fails with `FAILED REGENERATION
DESTROYED THE PRIOR NOTE`.

**D8 needed the two-pass pattern, and the in-flight pass had to be made
observable.** A Streamlit button cannot become disabled inside its own handler
— the script run is blocking — so `disabled=` alone is not a fix. The click now
records intent and reruns; the next pass renders the control disabled, says
`Updating review…` politely, and only then makes the call.

Proving that needed a third measurement correction, recorded with the others:
**AppTest resolves `st.rerun()` inside the same `run()`**, so a click passes
straight through the busy pass and the disabled control is never visible to it.
The check enters the busy pass directly and halts the script with `st.stop()`
exactly where the blocking call sits, which leaves that pass as AppTest's final
state. Mutation-checked both ways — removing `disabled=busy` fails with "still
live during the call", removing the progress line fails with "no polite inline
progress". In a browser this window is closed instantly because DEMO_MODE
returns canned output with zero spend, which is precisely why it is asserted
under AppTest instead of claimed from a screenshot.

**D7 was real:** `_note_stats(` appeared in Weekly and Daily and not once in
Patterns, so one page answered "how big is this sample" two different ways.
Patterns now opens with the same five-cell strip, fed by a new pure
`review_reader.period_stats`, which **assembles** what the metrics service
returns and calculates nothing.

**A spec violation the plan did not name.** Patterns rendered
`render_research_note`, which embeds an Evidence Rail inside *every* numbered
finding — four findings put four stacked rails on one note, against §7.2's
"once per note, not under every paragraph". Measured in the browser at 1440
before and after: **4 rails → 1**. The note's stated confidence is the **floor**
across its findings, never the peak; quoting the strongest would describe the
weakest claim on the page as high confidence. The trade-off is disclosed: the
shell shows one section at a time, so per-finding confidence badges are no
longer rendered beside each finding. Recorded for Codex as a deliberate reading
of §7.2 rather than an oversight.

**Contracts that moved rather than weakened.** Five existing tests asserted
page-source strings for behaviour that Task 12 moved into the shell
(`render_evidence_rail`, `render_evidence_disclosure`, `tl_note_sheet`,
`st.markdown(_md_safe(review["content_md"]))`, `render_research_note`). Each
now asserts the same property where the rendering actually happens, and the
safety one is asserted through the AST instead of `near()`: a fixed character
radius reports on whatever happens to sit nearby, so it would pass a file that
renders the thesis unsafely just outside the window.

**Files changed:** new `components/review_reader.py`, new
`tests/test_review_reader.py`, new `tests/insights_regen_check.py`,
`6_Insights.py`, `design_system.py`, `tests/test_insights_page.py`,
`tests/test_premium_page_contracts.py`, and this handoff. `_md_safe` moved off
the page into the shell so all three lenses get it rather than the two that
remembered. `git add -A` not used; untracked `src/tradelens/ui/.impeccable/`
deliberately not staged. `black tests/` reformatted two unrelated files
(`test_page_polish.py`, `test_trade_wizard.py`, both already non-black-clean
before this session); **both were reverted** under handoff rule 6.

**Browser evidence — 14 combinations, all clean.** Coarse-pointer emulation
asserted at every coarse row (`pointer: coarse` true **and** `pointer: fine`
false); reduced motion read back from the page.

| Lens | Widths | Overflow | Undersized | Exceptions | Sheets | Rails | Strips | Prose width |
|---|---|---|---|---|---|---|---|---|
| Patterns | 1440, 1024, coarse 768, coarse 375 | 0 | 0 | 0 | 1 | 1 | 1 | 573 / 560 / 480 / 295 |
| Weekly Recap | same four | 0 | 0 | 0 | 1 | 1 | 1 | same |
| Daily Debrief | same four | 0 | 0 | 0 | pre-generation state | — | — | — |
| Patterns, reduced motion | coarse 375 | 0 | 0 | 0 | 1 | 1 | 1 | 295 |
| Weekly, reduced motion | 1440 | 0 | 0 | 0 | 1 | 1 | 1 | 573 |

573 px of 16 px prose is ≈71 characters — inside §7.4's 68–72 ch measure, and
it never stretches into the unused right side. The section index carries 44 px
options at every width. Rail and bottom bar are never both on screen.

Daily Debrief was additionally driven end to end in the browser at 1440:
lens switch → `Generate debrief` → note appears (1 sheet, 1 rail, 1 strip,
"Day in review") → `Regenerate debrief` → the note is still there, no error, no
exception.

**Verification:** `1901 passed, 7 skipped` (was `1867/7`; +34); Ruff clean;
Black clean (85 files); `git diff --check` clean. Dev database byte-identical
(`md5 dffdb781…`) — the browser ran against a scratchpad **copy** pointed at by
`DATABASE_URL`, seeded and re-owned there only.

**Unresolved concerns.**

1. Per-finding confidence is no longer rendered beside each finding (above).
2. The note-surface CSS comment still describes "a focused DARK reading surface
   inside the light workspace"; the workspace has been fully dark since Task 1.
   Left for the Task 16 stale-comment sweep rather than widened into here.
3. Carried forward unchanged: `aria-sort` is `null` on Streamlit's dataframe
   headers and its four toolbar controls have no accessible names. Both need
   JavaScript injection (forbidden) or an authored table. **Task 12 was not
   expanded into a ledger replacement.**

### 2026-08-06 — Session boundary: Tasks 10 and 11 done, resume at Task 12 (Claude)

Tasks 10 (`eaeca32`) and 11 (`df07a11`) are committed with full evidence.
Tasks 12–17 are not started. This is a **context boundary, not a review
gate** — no interim Codex review is requested, and the comprehensive review
stays scheduled after Task 17. The lock is `NONE` only so a fresh session can
claim it cleanly.

**Resume at Task 12 (AI Reviews).** Its audit is done and recorded below, so
the next session should not repeat it.

**What a fresh session needs.** The CDP driver was rebuilt again this session
from the four corrections in the Task 8/9 entries; all four held, and a
**fifth** is now recorded in the Task 10 entry (Streamlit retains a copy of a
swapped container inside a `display:none` parent, so every calendar day button
appears twice — filter on `offsetParent !== null`). The driver lives in the
session scratchpad, not the worktree. Also worth knowing: the dev database in
this worktree has **no trades owned by user 1**, so the Journal stops at its
demo branch before the view selector ever renders; seed a scratchpad copy and
set `user_id = 1` there to reach the Journal calendar. Analytics does not need
this because it falls back to `get_demo_df()`.

**Task 12 reconnaissance — all three claimed defects are real, verified in the
source, not assumed from the plan:**

1. **D5 is real and is data loss.** `_render_daily_lens` (`6_Insights.py:576`)
   pops `cache_key` *before* calling `_run_daily_debrief`. `_run_daily_debrief`
   only writes `st.session_state[cache_key]` on success, so a `DebriefError`
   leaves the note gone and only `_err` set — the next rerun takes the error
   branch and the debrief the trader already had is destroyed. Weekly does the
   opposite deliberately, and says so in a comment: "The existing note stays on
   screen until a replacement succeeds." Daily must match Weekly.
2. **D7 is real.** `_note_stats(` appears in `_render_weekly_lens` (476) and
   `_render_daily_lens` (563) and **not once** in `_render_patterns_lens`
   (319–394).
3. **D8 is real.** There is no `disabled=` anywhere in `6_Insights.py`. Note
   for whoever implements it: a Streamlit button cannot be disabled *during*
   its own click handler, because the script run is blocking. This needs the
   two-pass flag/rerun/render-disabled/run pattern, not a `disabled=` argument
   bolted onto the existing call — budget for that.

**One plan claim that is already satisfied, so do not "fix" it.** Step 5 says
to demote the lens radio below the section header. `6_Insights.py` already
renders the radio and then `render_section_header(lens, …)`, the same shape
Task 10 measured on Analytics (question 36px/700, option 16px/400). Verify by
measurement before changing it; the plan's Analytics version of this test
passed for the wrong reason.

**Verification at this boundary:** `1867 passed, 7 skipped`; Ruff clean; Black
clean; `git diff --check` clean. Dev database byte-identical
(`md5 dffdb781…`, `Jul 31`) — browser runs used a scratchpad **copy** pointed
at by `DATABASE_URL`, and the app process's cwd was read to confirm the
worktree it served. App and Chrome processes stopped. `.impeccable/` untouched
and unstaged.

### 2026-08-06 — Phase 2 Task 11: the pure review document model (Claude)

**Commit:** see `feat(ai-reviews): pure Markdown document model for generated
notes`. Task 11 only; Task 12 not started.

New `components/review_document.py`: `ReviewSection`, `ReviewDocument`,
`parse_review_markdown` — the exact names Task 12 consumes. Standard library
only; no Streamlit, no service, no model call, no database. Guarded.

**The plan supplied a full implementation and said it was verified: "this exact
source passes all 13 tests above plus 3 extra edge cases — 16 passed". That is
true and it is not the same as correct.** Three real defects survive its own
suite, each confirmed by reverting to the plan's source and watching the new
tests fail:

| Defect | Plan's behaviour | Why it matters |
|---|---|---|
| **Colliding ids** | `_slug` counts per base, so "Risk 2" takes `risk-2`, and a later second "Risk" — numbered on its own counter — takes `risk-2` as well | Task 12 selects a section by id. Two sections with one id means the reader opens the wrong one. The plan's uniqueness test compares two *identical* headings and never reaches this |
| **Length-blind fences** | a fence closes on any equal marker, and an info string closes one too | A model quoting Markdown emits a ```` block containing ``` blocks. The parser toggles out on the inner fence and reads the rest of the quoted code as headings |
| **ATX closing hashes** | `## Findings ##` is titled `Findings ##` | The hashes render in the section title and ride into its id |

Fixed by checking uniqueness against the ids actually issued rather than a
per-base count, by capturing the fence's marker run and requiring a closing run
of the same character, at least as long, with no info string, and by stripping
the ATX closing sequence.

The plan's `test_no_section_content_is_ever_dropped` checks that three tokens
appear somewhere in the rebuilt text. The replacement asserts the property it
names: every non-heading line survives the round trip.

**Verification:** `1867 passed, 7 skipped` (was `1842/7`; +25); Ruff clean;
Black clean; `git diff --check` clean. No browser work — this task renders
nothing. Dev database untouched (`md5 dffdb781…`).

**Files changed:** new `components/review_document.py`, new
`tests/test_review_document.py`, and this handoff.

### 2026-08-06 — Phase 2 Task 10: Analytics, one instrument shape (Claude)

**Commit:** see `feat(ui): one dark instrument shape across the four Analytics
lenses`. Task 10 only; Task 11 not started.

**Three of the plan's four tests passed against the unchanged page**, as the
Task 9 recon predicted. Transcribed verbatim and run before anything changed:

| Plan test | Result | Why |
|---|---|---|
| every figure staged | passed | true, and the string count would also pass a page with zero charts |
| exactly two heights | **failed** | the one real finding: `height=320` and `height=380` |
| selector secondary to the question | passed **for the wrong reason** | `source.index("render_section_header")` finds the `_section` helper 600 lines above the selector. The header that states the question is rendered *after* the radio, so the assertion would have held whichever way round the page ran |
| sparse data compact | passed | genuinely already true |

**The heights were both real, and the more interesting one was already dead.**
`session_dow_heatmap` set `height=320` while measuring **360** in the browser,
because `apply_chart_stage` overrides it — source and screen disagreeing, which
is worse than a wrong number because nothing can catch it by looking. The new
contract asserts the mechanism through the AST (no builder sets a height at
all) rather than accepting any file whose literals happen to read 360 or 240.
`calendar_heatmap_chart`'s `height=380` has one call site and it is the
archived, unrouted `_archive/6_Calendar.py`; its literal is gone and the call
is now staged, so un-archiving it cannot land on Plotly's default 450.

**The real finding of this task was a second calendar.** Analytics did not
mount the calendar the Journal mounts — it had its own `calendar_view.py`,
which predated the dark retarget and never received it:

- a money-positive day was tinted with **the brand teal**, the colour §4.1
  reserves for actions and focus, while the KPI strip and the ledger use green
  for exactly that meaning;
- the rest of its colours were literal pre-redesign hexes (`#8E9196`,
  `#B4B8BD`, `rgba(168,75,47,0.18)`), not role tokens;
- **no textual legend**, which §6.3 requires. Measured: `.tl-cal-legend` count
  **0** on the Timing lens at 1440 and at coarse 375;
- five raw `st.metric` cards — a second, undesigned KPI system inside a lens
  that already opens with the ruled strip. Measured: **5 `stMetric` nodes** on
  screen.

Those five cards are the sharpest lesson here. `test_analytics_has_no_giant_
one_off_metric_cards` asserts `"st.metric(" not in src` and was green the whole
time, because the cards were not in the page — they were in what the page
imported. That contract now follows the page's component imports.

Analytics mounts `render_trade_calendar` and `calendar_view.py` is deleted. The
month figures are preserved rather than dropped, through the designed strip and
a new pure `month_summary()` on the calendar component — not in page code,
because the calendar owns which month is open. It is opt-in and **off for the
Journal**, so Task 9's surface is unchanged (measured: `kpiStrips` 0 there).
`winning_days` is named in days, not "win rate", because `daily_outcomes`
carries no per-trade outcome and the old label was a different measure wearing
the same word.

**The 375px calendar measurement, taken before anything was changed**, as
directed. The legacy grid measured **49×62 at coarse 375, 7 per row** — already
compliant, so nothing was forced smaller to match a number. After the swap the
day cells measure **47×44** at coarse 375, still 7 across in one row.

**One rule, not a Journal rule.** The container key is renamed
`tl_journal_calendar` → `tl_full_calendar` (page, four CSS selectors, four test
assertions). The 7-column and 44px rules were never Journal-specific; Analytics
mounted the same form and would otherwise have wrapped into a 31-row list at
375. Re-verified in the browser on **both** pages.

**Charts had no text alternative at all.** Spec §12 asks every chart for a text
summary of its key insight; Plotly gives a screen reader a canvas and unlabelled
SVG paths, and its tooltips need a pointer. `_chart` now takes a **required**
keyword-only `summary` — a keyword that can be forgotten is one that will be —
rendered as `.tl-visually-hidden` text inside the stage. Eight call sites carry
data-derived sentences.

**Every new guard was mutation-checked.** One mutation (removing a single
`summary=`) reported green on the first attempt; the mutation had not applied,
not the test. Re-run with an AST-guided edit it failed correctly. Recorded
because a mutation check that silently no-ops is the same false-confidence
shape this file exists to catch. Six guards, six confirmed failures:
reintroducing `height=320`; removing one `summary=`; giving `summary` a
default; restoring `calendar_view.py`; a component sneaking in `st.metric`;
removing the radio's collapsed label.

**Not changed, because measurement said so.** The lens selector is already
secondary to its question — measured at 1440, the question is **36px/700** and
a lens option **16px/400**. The plan's source-order proxy was replaced with the
runtime order plus the collapsed-label assertion.

**Browser evidence — 12 combinations, all clean.** Coarse-pointer emulation was
asserted at every coarse row (`pointer: coarse` true **and** `pointer: fine`
false); a width-only viewport was never accepted as coarse. Lens switches were
asserted to have taken effect by reading back the rendered question.

| Lens | Widths | Overflow | Undersized | Exceptions | Rail/bottom | Plot heights |
|---|---|---|---|---|---|---|
| Timing | 1440, 1024, coarse 768, coarse 375 | 0 | 0 | 0 | never both | 360/240/240 |
| Performance | 1440, coarse 375 | 0 | 0 | 0 | never both | 360 |
| Risk | 1440, coarse 375 | 0 | 0 | 0 | never both | 360/240 |
| Setups | 1440, coarse 375 | 0 | 0 | 0 | never both | 240 |
| Timing, reduced motion | coarse 375 | 0 | 0 | 0 | never both | 360/240/240 |
| Performance, reduced motion | 1440 | 0 | 0 | 0 | never both | 360 |

Reduced motion was asserted from the page (`prefers-reduced-motion` matched),
not assumed from the Chrome flag.

**A fourth measurement correction, recorded with the other three.** The
undersized probe found 26 calendar day buttons of which 13 measured 0×0.
Streamlit retains a copy of a swapped container inside a `display:none` parent,
so every day button appears twice. `offsetParent === null` separates the
rendered calendar from the retained one; the rendered cells measure 133×44 at
1440 and 47×44 at coarse 375. The existing 0×0 skip already excluded them, so
no false positive reached a report — but the probe now says *why*.

**Files changed:** `4_Analytics.py`, `components/charts.py`,
`components/trade_calendar.py`, `design_system.py`, `2_Trades.py` (key rename
only), `_archive/6_Calendar.py`, deleted `components/calendar_view.py`,
`tests/test_charts.py`, `tests/test_premium_page_contracts.py`, and this
handoff. `git add -A` not used; untracked `src/tradelens/ui/.impeccable/`
deliberately not staged.

**Verification:** `1842 passed, 7 skipped` (was `1833/7`); Ruff clean; Black
clean (83 files in `src/`+`scripts/`, plus the two touched test files);
`git diff --check` clean. The dev database is byte-identical
(`md5 dffdb781…`, `Jul 31`) — the browser ran against a scratchpad **copy**
pointed at by `DATABASE_URL`, seeded and re-owned there only, and the app
process's cwd was read to confirm which worktree it served.

**Deviations from the plan, all recorded above:** the plan's Task 10 file list
named only `4_Analytics.py` and `charts.py`. Deleting the duplicate calendar,
sharing its responsive rule, and adding the pure `month_summary` reach three
more UI files. No service, prompt, model-routing, auth, tenant-scoping, schema
or secret path was touched, and no second data path was opened —
`month_summary` reads the same `daily_outcomes` map the grid already draws
from.

**Carried forward for the Codex Phase 2 review (from Task 9, unchanged):**

1. `aria-sort` is `null` on Streamlit's dataframe column headers. §6.3 requires
   it. The markup is Streamlit's; setting it needs JavaScript injection, which
   the spec forbids, or replacing the ledger with an authored table. Task 10
   did **not** expand to replace the ledger. No in-scope, non-JavaScript fix
   exists.
2. The dataframe toolbar's four controls have no accessible name — `aria-label`
   and `title` both absent, tooltip only. §12 requires names on icon-only
   controls. Same ownership question.
3. Tabular numerals cannot reach the ledger; it is canvas-rendered.
4. `TL_RULE = #AFBEC0` is still a light-surface value (Task 12); `theme.py`
   compatibility names still lie; emoji remain on AI Reviews and Strategy
   surfaces (Tasks 12, 13).

### 2026-08-06 — Session boundary: Tasks 8 and 9 done, resume at Task 10 (Claude)

Tasks 8 (`f2eb1df`) and 9 are committed with full evidence. Tasks 10–17 are
not started. This is a **context boundary, not a review gate** — no interim
Codex review is requested and the comprehensive review stays scheduled after
Task 17. The lock is `NONE` only so a fresh session can claim it cleanly.

**Resume at Task 10 (Analytics).** Its audit is already done and recorded in
the Task 9 entry below under "Task 10 reconnaissance", including the one real
finding: two chart heights bypass the stage.

**What a fresh session needs.** A reusable CDP driver had to be rebuilt this
session and its four measured corrections are the expensive part to
rediscover; they are recorded in the Task 8 and Task 9 entries. The driver
lives in the session scratchpad, not the worktree, so a new session should
recreate it from those notes:

1. `PUT /json/new`, not POST — Chrome answers 405 otherwise.
2. Re-apply device metrics **after** navigation; metrics set on `about:blank`
   report `innerWidth` 981 under mobile emulation whatever width was asked
   for, which silently turns a "coarse 375" pass into a desktop layout.
3. A fresh Chrome process per viewport; reusing one across four widths closes
   the websocket after the first tab.
4. The undersized-target probe must exclude three false-positive classes —
   off-canvas, `clip`ped visually-hidden inputs, and BaseWeb's inner 2px caret
   input — and must measure the `[data-baseweb]` wrapper, which is what a
   trader actually hits.

**Verification at this boundary:** `1833 passed, 7 skipped`; Ruff clean; Black
clean (84 files); `git diff --check` clean. Dev database byte-identical
(`md5 5c33284d…`, `Jul 28`) — browser runs used a scratchpad **copy**, never
the dev database. App and browser processes stopped. `.impeccable/` untouched.

### 2026-08-06 — Phase 2 Task 9: dark Journal, real ledger contracts (Claude)

**Commit:** see `feat(ui): dark Journal, ledger rule extracted, honest icon
guards`. Task 9 only; Task 10 not started.

**All four of the plan's Task 9 tests passed against the unchanged page** —
the third task running where this is true, so each was transcribed, run, and
recorded before anything changed:

| Plan test | Why it passed as written |
|---|---|
| toolbar ≥44px | Task 3 took this fix early and said so; confirmed still in place |
| ledger neutral by row | **Its loop body never runs** — there is no `tl-ledger` class anywhere. The ledger is `st.dataframe` over a pandas Styler, so no CSS scan can see its row styling |
| tabular numerals | Matches the string anywhere in 2858 lines of CSS; says nothing about the ledger, which is canvas-rendered and unreachable by `font-variant-numeric` |
| Clear filters subordinate | Genuinely already true (`secondary_jf_clear`) |

**The ledger rule moved out of the page so it can be tested for real.**
`_ledger_styles` lived in `2_Trades.py`, which runs its whole script at module
scope, so the existing contracts reached it by parsing the page's AST and
exec'ing the extracted nodes **against invented token values** — `#167A47`
and `#B53A43`, light-workspace colours deleted in Task 1. Those tests could
never have caught the ledger pointing at a retired or wrong token; they only
ever compared the fixture against itself. Proof: repointing them at the real
tokens immediately failed on `assert '#B53A43' in 'color: #f56565'`.

The rule is now `components/ledger.py` — pure, no Streamlit import, the same
reasoning that put band logic in `overview_bands.py`. Six contracts migrated
onto it and now assert `ds.TL_SUCCESS` / `ds.TL_DANGER` rather than literals.
`_LEDGER_MARKS` and `_fmt_money` still live in the page, so the AST extraction
stays for them.

**A guard that could be evaded, found by evading it.** `test_all_toast_icons_
are_valid` matches `st.toast(... icon="…")` by regex. Routing the Journal's
three toasts through a module constant left that regex matching nothing on the
page while the suite still reported green — the same shape of false pass that
put an invalid `✓` icon into production and caused this file to exist. The
icons are inlined, and a new test requires every toast icon to be an inline
literal so the validator actually runs on it. Mutation-checked by reintroducing
the indirection.

`:material/check_circle:` was verified against Streamlit's real
`validate_icon_or_emoji` before use — it validates, and a fabricated material
name is rejected, so the validator genuinely checks the icon set. This is the
opposite of Task 2's case: `:material/…:` is correct for Streamlit's own
`icon=` parameter and wrong inside authored HTML, where it would be escaped.

**One defect found in the browser.** The demo/empty-journal ledger — the first
table a trader with no trades ever sees — listed raw database columns
(`trade_date`, `setup_type`, `killzone`, `pnl`), visibly and through the data
grid's ARIA table, while the real ledger beside it reads Date / Asset / Setup /
Session / Result / P&L. Renamed to match.

**Already correct, verified rather than changed:** the ledger is neutral by row
with colour only on signed money and breakeven left uncoloured; the trade
detail is a panel container with edit and delete behind separate disclosures
and delete gated on an explicit confirmation; the calendar carries a textual
legend; `Clear filters` is subordinate.

**Interaction paths.** The plan says "in a browser". All three are covered by
`tests/journal_flow_check.py`, which really clicks under AppTest in a
subprocess and asserts the view, the selected trade's identity, and that Back
does not bounce. That is the right instrument for a state transition — a CDP
click on a Streamlit radio drove one transition and silently failed the next,
which would have produced false evidence. The browser was used for what
AppTest cannot see.

**Browser evidence — 8 combinations, all clean:**

| View | Width | innerW | Rail | Bottom | Both | Overflow | Undersized | Toolbar | Exceptions |
|---|---|---|---|---|---|---|---|---|---|
| Ledger | 1440 | 1440 | yes | no | never | 0 | 0 | 4×44×44 | 0 |
| Ledger | 1024 | 1024 | yes | no | never | 0 | 0 | 4×44×44 | 0 |
| Ledger | coarse 768 | 768 | no | no | never | 0 | 0 | 4×44×44 | 0 |
| Ledger | coarse 375 | 375 | no | yes | never | 0 | 0 | 4×44×44 | 0 |
| Calendar | all four | — | as above | — | never | 0 | 0 | — | 0 |

The calendar's textual legend renders with all three keys at every width,
including 375. **The preflight's 22.4×22.4 toolbar defect is closed** and
measured at 44×44 at all four widths.

**A third measurement correction, recorded because it nearly became a false
report.** The undersized probe flagged five 2px inputs on the Journal. They are
BaseWeb's inner caret input inside `[data-baseweb="select"]`; the wrapper a
trader actually hits measures 501×44, 319×44 and 1024×44 — Task 3's floor
working exactly as intended. The probe now measures the wrapper. Together with
Task 8's two driver corrections that is three classes of false positive found
by looking rather than assuming.

**Verification:** `1833 passed, 7 skipped` (was `1820/7`); Ruff clean; Black
clean (84 files); `git diff --check` clean. Dev database byte-identical
(`md5 5c33284d…`) — the browser ran against a scratchpad **copy** pointed at by
`DATABASE_URL`, and the app's serving directory was confirmed by reading the
process's cwd.

**Task 10 reconnaissance, so the next session does not repeat it.** Three of
the plan's four Task 10 tests already pass: `st.plotly_chart` and
`apply_chart_stage` are both 1 (all Analytics figures route through one
`_chart()` helper), the section header precedes the radio, and
`equity_curve_chart` on an empty frame already returns `xaxis.visible = False`.
**The one that fails is real:** `charts.py` carries `height=320` in
`session_dow_heatmap` and `height=380` in `calendar_heatmap_chart`, against the
stage's `_STAGE_HEIGHT = 360` / `_STAGE_HEIGHT_COMPACT = 240`. Both are
heatmaps setting their own height in `update_layout(**_BASE_LAYOUT, …)`. Note
before changing them: `apply_chart_stage` overrides `height`, so on any staged
path those literals are already dead — but the calendar's cell geometry and the
44px day-cell rule in spec §5.5 must be **measured** at 375 before the month
grid is forced to 360, not assumed.

**Files changed:** `2_Trades.py` (toast icons, demo column labels, rule
extracted), new `components/ledger.py`, `tests/test_page_polish.py`,
`tests/test_premium_page_contracts.py`, `tests/test_toast_icons.py`, and this
handoff. `git add -A` not used; untracked `src/tradelens/ui/.impeccable/`
deliberately not staged.

**Unresolved concerns.**

1. **`aria-sort` is not achievable for the ledger.** Spec §6.3 requires it.
   Streamlit's dataframe renders an ARIA table beside its canvases, and its
   `th[role="columnheader"]` elements carry `aria-sort: null`; the markup is
   Streamlit's, and adding the attribute needs JavaScript injection, which the
   spec forbids outright. Recorded rather than silently skipped. Options for
   Codex: accept as a framework limitation, or replace the ledger with an
   authored table — a much larger change than Task 9's scope.
2. **Tabular numerals cannot reach the ledger.** It is canvas-rendered, so
   `font-variant-numeric` does not apply. The rule holds on every authored
   surface; the plan's test only ever proved the string exists.
3. **The dataframe toolbar's four controls have no accessible name** —
   `aria-label` and `title` are both absent; they carry a tooltip only. Same
   ownership question as (1). Spec §12 requires names on icon-only controls.
4. `TL_RULE = #AFBEC0` still a light-surface value (Task 12); `theme.py`
   compatibility names still lie; emoji remain on AI Reviews and Strategy
   surfaces (Tasks 12, 13).

### 2026-08-06 — Phase 2 Task 8: New Trade on the dark workspace (Claude)

**Commit:** see `feat(ui): New Trade on the dark workspace with one progress
system`. Task 8 only; Task 9 not started.

**Two of the plan's three Step-2 tests passed against the unchanged wizard.**
Transcribed verbatim and run before anything was edited: the progress-system
test names `render_stepper`, and this page has always called
`render_step_indicator`, so both its assertions were vacuous; the review-step
test passed because `_ticket_section` already drops blank rows and `"complete"`
already matched the heading `Completeness`. Only the waiting-state test failed,
and it names the wrong file. On their own the three would have licensed a no-op
task, so each is now paired with a test asserting what the plan's prose
actually requires.

**The real finding: the wizard was five bright pills.** `.tl-step-circle.done`
and `.active` both filled solid `--tl-accent-action`, and `.tl-step-connector.done`
was accent too — so a trader on step 5 saw five identical teal circles and four
teal connectors beside the teal `Continue` button. Teal is action and focus
(spec §4.1); a step already left is neither, and this is exactly the
unrestrained teal coverage 10K item 03 targets. Done now recedes to the
elevated surface behind a `TL_LINE_STRONG` edge, keeping its check glyph;
future keeps its number with no edge, so done and future differ by glyph and
edge rather than by tone. Exactly one circle carries the accent, and it is
always the active one. Contrast holds: secondary on elevated 6.13:1, strong
line on elevated 3.03:1.

**The waiting state now holds its height.** The screenshot analysis, its
spinner, and its scanning video all live in `ai_autofill_review.py`, not in
`1_NewTrade.py` where the plan looked. Both call sites — auto-trigger and
manual re-run — render inside one keyed container whose rule reserves 320px, so
the detection panel lands where the pending block stood instead of shoving the
page down. Two corrections to the plan's literal are recorded in the test's own
docstring: the file, and `tl_analysis_pending` rather than `tl-analysis-pending`
— authored HTML cannot wrap Streamlit widgets, so the height is reserved by
keying a real container, which is the mechanism `tl_wizard_bar` and `tl_step_N`
already use, and Streamlit builds `.st-key-<key>` from that key.

**The review step now offers the route it was only describing.** It counted
blank optional fields and then gave the trader no way to reach them.
`_ticket_html` returns `(html, blanks)` and the step renders one subordinate
`Complete N optional fields` action — not one per empty group, and not styled
to compete with Save, because none of those fields block saving. This moved
`_jump_to_context` above the step bodies: callbacks are bound while
`_STEP_BODIES[STEP]()` runs, which is before the action bar defines its own.

**One emoji retired**, the share Task 2's amendment assigned to this task: the
autofill success message carried a literal `✅` beside the icon `st.success`
already draws.

**Three guards mutation-checked**, each reverted in turn: the done circle back
to accent fails the pill test; dropping `min-height` fails the geometry test;
removing the action fails the completion test.

**Browser evidence — real coarse-pointer emulation with the pointer state
asserted at each coarse width:**

| Check | 1440 | 1024 | coarse 768 | coarse 375 |
|---|---|---|---|---|
| `innerWidth` | 1440 | 1024 | 768 | 375 |
| Rail on screen | yes | yes | no | no |
| Bottom nav on screen | no | no | no | yes |
| Both at once | **never** | never | never | never |
| Horizontal overflow | 0 | 0 | 0 | 0 |
| Undersized on-screen targets | 0 | 0 | 0 | 0 |
| Exceptions | 0 | 0 | 0 | 0 |

Round trip with a real 1200×700 PNG through `DOM.setFileInputFiles`, then
Continue → Back → Continue, at 1440 and coarse 375: **the draft count held at
`6 of 15` at every step**, matching the figure `8b35a6e` recorded, with zero
exceptions and an identical retained-chart `src` after Back. The stepper was
measured on step 4: **1 accent-filled circle, 0 accent connectors**, done
circles `rgb(21,35,41)` behind `rgb(92,110,119)`.

**Two driver corrections, both of which would have produced false evidence:**

1. **`innerWidth` must be re-read after navigation.** Metrics applied while
   `about:blank` is loaded describe `about:blank`, which has no viewport meta,
   so mobile emulation reports 981 whatever width was requested. The first
   coarse-375 pass reported 981 — it was measuring a desktop layout with a
   touch pointer. Re-applying metrics after load gives a true 375, and the
   driver now does this rather than leaving it to the caller.
2. **The undersized-target probe must exclude clipped elements.** It reported
   `stFileUploaderDropzoneInput` at 1×1 under `clip: rect(0,0,0,0)` at every
   width. That is the visually-hidden pattern — the styled dropzone carries the
   real target and the input stays keyboard-reachable. Excluding off-canvas,
   clipped, and transparent elements takes every width to 0.

**Verification:** `1820 passed, 7 skipped` (was `1813/7`); Ruff clean; Black
clean (83 files); `git diff --check` clean. The +7 is this task's tests. App
served from the canonical worktree, confirmed by reading the process's cwd
rather than assuming it — Task 2 measured the old palette by not checking.

**Files changed:** `design_system.py` (stepper tones, pending-state rule),
`ai_autofill_review.py` (pending container, emoji), `1_NewTrade.py`
(`_ticket_html` returns blanks, the complete action, `_jump_to_context` moved),
`tests/test_trade_wizard.py`, and this handoff. `git add -A` not used;
untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

**Unresolved concerns.**

1. **`TL_RULE = #AFBEC0` is still a light-surface value** — carried from Tasks
   1–3, still Task 12's.
2. **`theme.py`'s compatibility names still lie** (`PAPER` is a dark panel).
3. **Emoji remain on Journal, AI Reviews, and Strategy surfaces**, recorded by
   the Task 2 amendment against Tasks 9, 12 and 13. This task took only its own.

Ownership remains `CLAUDE`; continuing to Task 9 under the master directive.

### 2026-08-05 — Session boundary: paused at Task 8, lock released (Claude)

Documentation only. No product code changed in this entry — the last code
commit is `00d2359` (Task 7) and the tree is clean apart from the untracked
`src/tradelens/ui/.impeccable/`.

**Why the pause.** Tasks 5–7 each turned up a contract the plan had wrong, and
each was resolved and recorded rather than escalated. Tasks 8–17 are roughly
ten times the remaining work — New Trade, Journal, Analytics, the document
model, AI Reviews, Strategy and Settings, both Partner surfaces, the audit and
the re-score — and every one needs the same treatment: read the task,
test-first, discover the real runtime contracts, implement, browser-verify at
four widths, full suite, commit, log. Continuing in one stretch would have
produced exactly the thin commits the directive rules out.

**This is a session boundary, not a review gate.** No interim Codex review is
requested; the comprehensive review stays scheduled after Task 17. The lock is
`NONE` only so a fresh Claude session can claim it cleanly.

**What the next session needs, all recorded above rather than in context:**
the three Task 5–7 commits, the verified-green Task 4 interfaces, the two
user-approved deviations still in force (`compute_breakdown` for P&L-ranked
breakdowns; `killzone` as the session dimension with `KILLZONE_LABELS`), and
the architectural note that band logic belongs in the pure
`overview_bands.py` because `app.py` boots a page at import.

**Resume at Task 8.** Claim `Active writer: CLAUDE`, then follow the master
directive through Task 17.

### 2026-08-05 — Phase 2 Tasks 5–7: the Overview recomposed (Claude)

**Commits:** `243d0c9` (Task 5), `25616f9` (Task 6), `00d2359` (Task 7).
Tasks 8–17 not started.

Task 4's interfaces were verified against the plan before anything consumed
them — `RuleAdherenceSummary(followed, recorded, rate)`,
`EdgeLeakSummary(net_pnl, qualifying_trades, recorded_trades)`,
`PartnerContext`, `PartnerEvidenceSource`,
`build_global_partner_context(*, user_id)`, no Streamlit or Anthropic import —
and `tests/test_metrics.py` + `tests/test_partner_context.py` run green at
129 passed.

**The Overview is now five bands in five distinct forms**, in the spec's
reading order: a ruled KPI strip, a discipline panel, a dominant chart with
flanking figures, two ranked lists plus the calendar, and one editorial
readout. The anti-grid rule is enforced by a test asserting no two bands share
a builder, and by a second asserting the five appear in order.

**Honest-zero handling is the through-line.** Every band-2 measure has a way of
being unknown that is not zero: "Not recorded" adherence is distinct from a
real 0%; edge leak separates unknown, a clean sample, and rule-breaking that
netted exactly zero; consistency states how many more trades unlock it. Band 3
reads "No wins yet" rather than $0.00 when there are none. A positive edge leak
carries an explicit warning — verified in the browser on seeded data where
rule-breaking netted +$92,047.66.

**Four plan deviations, all forced by observed runtime behaviour**, all using
existing public services and all approved or recorded:

1. **`by_setup_type` cannot rank by P&L.** It is documented "No PnL or
   R-multiple metrics" and powers a stacked bar. Both ranked lists use
   `compute_breakdown`, which returns `total_pnl` already sorted. *(Approved.)*
2. **There is no `session` column** on the Overview frame. The product records
   `killzone`, which the spec names as the alternative; labels come from the
   same `KILLZONE_LABELS` map the ledger uses. *(Approved.)*
3. **`ActivationStatus` differs from the plan's sketch** — `is_activated` /
   `next_key` / `completed` / `total`, not a nested step object with
   `is_complete`. The plan says to adapt the caller, so the caller adapted.
4. **Max drawdown is signed in presentation.** `compute_max_drawdown` returns a
   positive magnitude by documented contract, which sat unsigned beside a
   positive edge leak and read as money made. The Codex-owned service is
   untouched; the sign is applied in the UI and pinned by its own test.

**A real gap found and closed:** the 0-trade welcome runs *before* the asset
filter, so a filter matching nothing rendered band 1 as a strip of zeros —
figures that read as a flat account rather than an empty scope. The bands are
now suppressed with the scope named and one control back.

**Three activation contracts were migrated, not weakened.** The
tenant-isolation guard still requires every activation input to be user-scoped
and now additionally asserts the whole computation is gated on an
authenticated user. The card-hiding test moved from grepping `app.py` for a
literal to exercising `next_review_action`, which is where the decision now
lives.

**Architecture note.** All band logic lives in the pure
`components/overview_bands.py`, not in `app.py`. `app.py` runs its entire
Streamlit script at module scope, so a unit test importing it boots a page and
needs a database — which is exactly what happened on the first attempt.

**Browser evidence, per task, at 1440 / 1024 / coarse 768 / coarse 375 with the
pointer state asserted at each coarse width:**

| Task | Result |
|---|---|
| 5 | Band 2 renders 4 untoned rows on the panel surface; 0 overflow, 0 exceptions |
| 6 | Bands 1–4 in order; two ranked lists with human-readable killzone labels, leader marked, chart present |
| 7 | All five bands in strict reading order |

**Verification:** `1813 passed, 7 skipped` (was `1711/7` after Task 3); Ruff
clean; Black clean (181 files); `git diff --check` clean; page boot checks 64
passed. Dev database untouched (`Jul 31`); all app and browser processes
stopped; no capture artifact entered the worktree; `.impeccable/` untouched.

**Remaining: Tasks 8–17.** New Trade, Journal, Analytics, the pure review
document model, AI Reviews, Strategy/Settings, both AI Partner surfaces, the
cross-page audit, and the 10K re-score. None started. The plan's Task 4
interfaces they depend on are verified present and green.

Ownership remains `CLAUDE`.

### 2026-08-05 — Phase 2 Task 4: service additions (Codex)

**Commit:** `3aa9e36`. Task 4 only. No UI, AI routing, authentication,
database-schema, secret, or model-service file changed.

**Produced interfaces:**

- `RuleAdherenceSummary(followed, recorded, rate)` and
  `rule_adherence_rate(trades)`;
- `EdgeLeakSummary(net_pnl, qualifying_trades, recorded_trades)` and
  `edge_leak_summary(trades)`;
- `PartnerEvidenceSource`, `PartnerContext`, and
  `build_global_partner_context(*, user_id)`;
- `MAX_CONTEXT_CHARS = 12000`, `MAX_EVIDENCE_SOURCES = 40`,
  `JOURNAL_HEADING`, `TRADES_HEADING`, and `STRATEGY_HEADING`.

The metrics distinguish unknown samples from known zero values without
changing `total_edge_leak()` for existing callers. The context adapter rejects
invalid owners before opening a session, repeats the owner predicate at every
trade hydration, reads the active profile through `get_active_strategy`, and
never calls the model or logs usage.

Prompt lines and evidence descriptors are admitted atomically under both
budgets. Oversized records are skipped rather than allowed to starve later
sections. Journal counts use the same stripped fallback logic as admitted
journal text, so whitespace-only process notes cannot hide a meaningful
fallback note or inflate the count.

**Plan hardening:** the plan did not cover embedded newlines in user-authored
notes, asset names, or Strategy Profile names. Those values are collapsed to
one line before prompt or evidence-label admission. A regression test proves
they cannot forge headings or extra evidence-looking bullet lines.

**Mutation checks:** removing the hydration owner predicate exposes the foreign
row and fails its dedicated test; restoring the truthiness note chain loses
fallback notes; counting SQL-prefiltered rows includes exotic whitespace. Each
mutation failed before the correct implementation was restored.

**Verification:** `38 passed` in `test_partner_context.py`; `91 passed` in
`test_metrics.py`; combined Task 4 `129 passed`; full suite `1757 passed, 7
skipped`; Ruff clean; Black clean (82 source/script files); `git diff --check`
clean. The development database was not used or modified; database tests used
an isolated in-memory SQLite database with `StaticPool`.

Ownership returned to `NONE`. Tasks 5, 14, and 15 are unblocked. Per the
user-approved master directive, Claude may now execute Tasks 5–17 continuously
and stop only for a genuine blocker or Codex-owned change.

### 2026-08-05 — Task 3 accuracy amendment; blocked on Task 4 (Claude)

**Commit:** `16a81ee`. Test naming and comments only — `design_system.py` is
byte-identical to Task 3's `5a03834`, verified with `git diff --quiet`.

**Two corrections, both requested at the Task 3 gate.**

1. **The 1.08:1 focus-ring claim is gone.** The allowlist note said
   `stBaseButton-secondary`'s default ring measured 1.08:1. That was disproven:
   `el.focus()` does not activate `:focus-visible` in Chrome, so the figure
   described `:focus`. Tabbing through 26 controls with our rule removed showed
   the default already clears 3:1. The note now gives the real rationale — the
   explicit rule pins focus to `TL_ACCENT_ACTION` rather than a framework
   default that can change between releases (spec §4.6).

2. **`test_each_alert_carries_primary_copy_on_a_semantic_tint` is renamed**
   `test_each_alert_kind_stays_readable_on_the_shared_quiet_ground`. There are
   no semantic tints: the implementation deliberately uses one shared elevated
   ground, because the container exposes its kind only through hashed `st-*`
   classes and differentiating it would need `:has()`. The docstring now
   describes what was built and why kind is carried by Streamlit's per-kind
   icon and by the sentence.

   **Its assertions are stronger, not weaker.** It still requires
   content-primary copy, and now also asserts that no kind recolours its own
   copy to a semantic hue and that the shared ground is the elevated surface.
   Mutation-checked by tinting the error alert's copy, which fails it.

**Verification:** `1711 passed, 7 skipped` — unchanged, which is the expected
result for a naming and comment amendment. Ruff clean; Black clean (177 files);
`git diff --check` clean.

**Blocked here, deliberately.** The master directive authorises Tasks 5–17
continuously and its closing line says to resume from Task 5, but the same
directive states: *"Do not start Task 5 until the handoff records Task 4 as
implemented, verified, committed, and released by Codex."* Checked in the tree:

| Task 4 artefact | Present? |
|---|---|
| `src/tradelens/services/partner_context.py` | **no** |
| `RuleAdherenceSummary` / `rule_adherence_rate` in `metrics.py` | **no** (0 occurrences) |
| `EdgeLeakSummary` / `edge_leak_summary` in `metrics.py` | **no** (0 occurrences) |
| `tests/test_partner_context.py` | **no** |

Task 5's band 2 consumes `rule_adherence_rate` and `edge_leak_summary`
directly, and the directive forbids both a UI-side substitute and duplicating
the calculation in page code. Starting Task 5 first would require one of them,
so the gate is honoured rather than worked around.

**For Codex.** The plan's Task 4 carries complete implementations and test
suites, executed against the real `metrics.py` while the plan was written:
34 `partner_context` tests and 15 metrics checks, with `_journal_text`,
`journal_entry_count`, atomic admission, and the tenant-scoped hydration guard
all mutation-checked. Ownership decisions are already settled there — the owner
validator is mirrored (matching `strategy.py`, `cost.py`, `app_settings.py`)
and the strategy profile is read through the public `get_active_strategy`, so
no other service file changes.

Ownership returned to `NONE`. **Next owner is CODEX for Task 4.** When the
handoff records Task 4 as released, the master directive authorises Claude to
claim the lock, verify the interfaces exist exactly as specified, run Task 4's
tests, and then execute Tasks 5–17 continuously with a separate commit per
task.

### 2026-08-05 — Phase 2 Task 3: controls and the eight interaction states (Claude)

**Commit:** `5a03834`. Task 4 not started, and it is Codex's.

**The plan's four given tests passed as written, before any change.** They are
regression guards, not drivers — the plan expected them to fail and they did
not. Rather than treat that as done, I audited what Task 3 actually had left:
eleven control families with no dark rule at all, and no focus or disabled
state on most of the styled ones. That audit produced 23 genuinely failing
tests, which is what the implementation was written against.

**Every selector was observed in the live DOM before a rule was written for
it**, by rendering a throwaway page containing each control the product uses.
That is this repo's standing rule for testids and it earned its keep: the
alert container turned out to expose its kind only through hashed `st-*`
classes, which changed the design.

**Newly styled, all previously bare:** text area, number input, checkbox,
slider, spinner, alerts, toasts. Fields now share one system — field surface
and hairline at rest, a border shift on hover, teal only on focus.

**Disabled and read-only are now distinguishable**, which they were not.
Disabled recedes to the canvas and takes the cursor with it; read-only keeps
content-primary text on the normal field surface, because its value is
information the trader is meant to read.

**Alerts use one quiet ground with content-primary copy.** Differentiating the
ground needs `:has()` to reach the container from the kind class inside it, and
the container's own kind is only in hashed classes. The kind is carried by
Streamlit's per-kind icon and by the sentence, so colour is not the sole
carrier either way — and a uniform ground is quieter.

**The 44px floor was driven by measurement, not assumption.** Measured under it
and corrected: `[data-baseweb="select"]` 40, `stNumberInputContainer` 40, its
steppers 38, `stFormSubmitButton` 40, and the dataframe toolbar at 22×22.
Re-measured after: **no undersized targets at 1440, 1024, 768 or 375.**

**Controls the product never renders — tabs, toggles, time inputs, data
editors, progress bars — are deliberately unstyled.** The plan's Step 3 lists
tabs and Step 4 says "every interactive control class"; CSS for a widget that
never appears is dead weight whose selector cannot be proven, and a blanket
`min-width` would have inflated small marks the spec says to leave alone.

**A correction to Task 2's evidence, which Codex approved partly on my word.**
Task 2 reported "real coarse-pointer" verification using
`Emulation.setEmulatedMedia` with pointer/hover features. **That call is
silently ignored by this Chrome** — I verified it directly: it leaves
`matchMedia('(pointer: coarse)')` false. Only `setTouchEmulationEnabled` plus
mobile device metrics flips the pointer media type.

Task 2's *conclusions* stand — its findings were width-driven — and I re-ran
the full 28-combination sweep under genuine coarse emulation, with an assertion
that the emulation took: **28/28 pass**, same nav pattern, same canvas, same
rail edge. But the claim "real media emulation, not desktop viewport resizing"
was not true when I made it. The drivers now assert the pointer state instead
of assuming it.

**A defect I reported to myself and then disproved.** A first focus probe
measured `stBaseButton-secondary` at 1.08:1 and I wrote a fix citing that
number. `el.focus()` does not trigger `:focus-visible` in Chrome — it was
measuring `:focus`. Re-measured by pressing Tab through 29 controls: every one
already showed a ring ≥3:1, and removing my rule left 26 controls still
passing. The rule is kept because spec §4.6 requires `TL_ACCENT_ACTION`
specifically and a framework default can change between releases — but its
comment now says that, not the false measurement.

**One existing contract needed refining, not weakening.**
`test_disabled_controls_keep_streamlits_dimming` forbids raising disabled copy
to primary, which is right. It fired on the read-only rule because
`:not(:disabled)` contains the substring. The guard now strips the negation
before deciding whether a rule targets disabled controls; mutation-checked by
raising a real disabled rule to primary, which still fails it.

**Browser verification:**

| Check | Result |
|---|---|
| 28 route/viewport combinations | pass, pointer emulation asserted |
| Undersized targets, 1440/1024/768/375 | **none** |
| Keyboard focus, 29 controls tabbed | all ≥3:1 |
| Coarse 375 | `pointer:coarse=true`, `hover:hover=false`, 0 overflow, 0 exceptions |
| Reduced motion | honoured, 0 elements still animating, 0 exceptions |

**Verification:** `1711 passed, 7 skipped` (was `1676/7`); Ruff clean; Black
clean (177 files); `git diff --check` clean. Dev database untouched (`Jul 31`);
all app and browser processes stopped; no capture artifact entered the
worktree.

**Files changed:** `design_system.py`, `tests/test_dark_workspace.py`,
`tests/test_design_system.py` (proven-testid allowlist),
`tests/test_premium_page_contracts.py`, and this handoff. `git add -A` not
used; untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

**A process note worth recording.** A `cat >>` ran with the shell's cwd reset
to the main checkout and created a stray `tests/test_dark_workspace.py` there.
The worktree file was untouched; the stray was deleted and the main checkout's
own modifications were left alone. Absolute paths for every write after that.

**Unresolved concerns.**

1. **`TL_RULE = #AFBEC0` is still a light-surface value** — carried from Task 1
   and Task 2. Belongs to Task 12, which restyles the Evidence Rail.
2. **`theme.py`'s compatibility names still lie** (`PAPER` is a dark panel).
3. **The dataframe toolbar fix was taken early from Task 9.** Its rule and
   allowlist entry are in place; Task 9's own step should find it already done.
4. **Checkbox, radio, slider and expander have no focus rule of ours.** The Tab
   probe shows the framework ring is adequate at ≥3:1, so nothing is broken,
   but they are not pinned to our token the way buttons and fields now are.

Ownership returned to `NONE`. **Task 4 is Codex-owned and must not be started
by Claude.**

### 2026-08-05 — Task 2 accuracy amendment (Claude)

**Commit:** `e21b9ba`, on top of `8919771`. Documentation and test naming only;
the source edits are comments. No UI behaviour changed. Task 3 not started.

**The guard's name claimed more than the guard checked.**
`test_no_structural_icon_is_an_emoji` reads as a statement about the product. It
checks three renderers: `render_empty_state`, `render_data_state`, and
Analytics' local `_empty` adapter. Renamed `test_no_empty_state_icon_is_an_emoji`,
with a docstring and a failure message that name the scope and name what it does
**not** cover.

**The handoff said "every emoji structural icon is a Material ligature".** That
was false. It now says every Phase 1 D9 **empty-state call site** was migrated,
which is what happened, and records the emoji-bearing controls that remain
against the tasks that own their surfaces:

| Surface | Remaining emoji | Owner |
|---|---|---|
| New Trade — autofill success, screenshot analyzer button and toasts | `✅`, `🔍` | Task 8 |
| Journal/trade detail toasts; corrections sidebar | `✅`, `🧠`, `💡`, `➕` | Task 9 |
| AI Reviews toasts and the `📝 AI Review` subheader | `✅`, `📝` | Task 12 |
| Strategy save toasts | `✅` | Task 13 |

They were not changed here on purpose: a toast icon or a button label is a
behaviour change, each sits on a surface a later task rebuilds, and Task 2 has
no browser evidence for any of them.

**Stale prose describing the opposite architecture, corrected.** The token change
falsified comments that were written for a light workspace and left describing it
as current:

- the Plotly template header ("Charts are DARK INSTRUMENTS inside the light
  workspace") — the reason a figure paints its own stage still holds, but not
  for that reason;
- the shared-component repaint note ("they carry the light workspace's ink by
  default");
- the hero note ("not reinstated on the light workspace");
- an Insights comment about `st.expander` on the light workspace;
- `test_app_and_marketing_site_share_one_brand_accent`'s docstring ("restated for
  the hybrid theme… the app is now a LIGHT workspace");
- `test_css_declares_the_hybrid_surface_variables` →
  `test_css_declares_the_role_surface_variables`;
- `test_navigation_rail_is_dark_and_workspace_is_light` →
  `test_the_rail_is_the_deepest_surface_and_the_canvas_sits_above_it` — both are
  dark now, so the assertion's premise moved: the separation is carried by the
  strong line, not by one being light;
- two `test_premium_page_contracts` docstrings.

Comments in `design_system.py` lines 54–57 were **kept**: they describe the
hybrid as something this commit *replaced*, which is accurate history rather
than a stale claim.

**Verification:** `1676 passed, 7 skipped` — unchanged, which is the expected
result for a naming and comment amendment. Ruff clean; Black clean (177 files);
`git diff --check` clean. Affected suites run directly: 328 passed across
`test_dark_workspace`, `test_design_system`, `test_premium_page_contracts`,
`test_premium_shell`, `test_insights_page`, `test_charts`.

**Files changed:** `design_system.py` and `6_Insights.py` (comments only),
`test_dark_workspace.py`, `test_design_system.py`,
`test_premium_page_contracts.py`, and this handoff. `git add -A` not used;
untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

Ownership returned to `NONE`. **Task 3 must not begin until Codex approves.**

### 2026-08-05 — Phase 2 Task 2: the shell retarget (Claude)

**Commit:** `8919771`. Task 2 only; Task 3 not started.

**The bridge is gone.** Task 1's compatibility aliases are deleted and every
rule now names a role token — **274 references**, not the 265 the first sweep
found. `design_system.py` is not the only file emitting `var(--tl-*)`:
`1_NewTrade.py` and `2_Trades.py` build inline styles for money colours and
captions, and those nine pointed at variables that no longer existed. An
undefined `var()` resolves to nothing and silently inherits, so this was
invisible until a test looked for it. A new guard scans every UI module and was
mutation-checked.

**The rail draws its edge with `TL_LINE_STRONG`.** Rail and canvas separate at
1.02:1, which no eye resolves. The one structural division present on every
screen has to be drawn rather than toned, and drawn at the weight that says
navigation is not work — the hairline is for things that belong together.

**Emoji in the D9 empty-state renderers (scope, stated precisely).** Every
Phase 1 D9 **empty-state call site** was migrated — the plan listed six, there
were nineteen. The first guard I wrote matched only `render_empty_state("x"` on
the following line and missed thirteen, including a whole page routing through a
local `_empty()` helper.

**This is not "every emoji in the product", and the guard no longer claims it
is.** `test_no_empty_state_icon_is_an_emoji` covers exactly three renderers —
`render_empty_state`, `render_data_state`, and Analytics' local `_empty`
adapter — and its docstring and failure message say so. Emoji-bearing controls
survive elsewhere and are left for the tasks that own those surfaces:

| Surface | Remaining emoji | Owner |
|---|---|---|
| New Trade — autofill success, screenshot analyzer button and toasts | `✅`, `🔍` | **Task 8** |
| Journal/trade detail toasts; corrections sidebar | `✅`, `🧠`, `💡`, `➕` | **Task 9** |
| AI Reviews toasts and the `📝 AI Review` subheader | `✅`, `📝` | **Task 12** |
| Strategy save toasts | `✅` | **Task 13** |

They were deliberately not modified here: each belongs to a surface a later task
rebuilds, and changing a control's label or a toast icon is a behaviour change
Task 2 has no browser evidence for.

Icons in scope are Material **ligature names** — plain escaped text styled by the
font the mobile nav already relies on. `:material/…:` cannot work here because
the icon is escaped into authored HTML, where it would render literally. All 13
names were verified in the browser to form real glyphs: 32px advance at 32px
font-size, against 167px for the same string as literal text. That matters
because Streamlit could have loaded a font subset; it has not. An absent icon now
emits no element rather than an empty 32px box.

Typographic **values** are deliberately untouched — `∞` for an undefined profit
factor, `▲▼■` deltas and ledger result marks, the stepper `✓`, `→` in link copy,
and `—` placeholders all carry meaning as text and are not icons.

**Browser verification — 28 route/viewport combinations, all pass:**

| Width | Canvas | Exceptions | Overflow | Rail | Bottom nav |
|---|---|---|---|---|---|
| 1440 | `rgb(9,18,22)` | 0 | 0 | visible | absent |
| 1024 | `rgb(9,18,22)` | 0 | 0 | visible | absent |
| coarse 768 | `rgb(9,18,22)` | 0 | 0 | absent | absent |
| coarse 375 | `rgb(9,18,22)` | 0 | 0 | absent | visible |

Rail edge computes to `rgb(92,110,119)` = `#5C6E77` at every width. The
navigation pattern matches the preflight's corrected mapping exactly, and rail
and bottom bar are never both visible — which required measuring **on-screen
geometry**, not `display`: at 375 Streamlit keeps the sidebar in the DOM,
translated `-256px` off-canvas.

**The auth widget overrides were measured and KEPT.** The instruction was to
remove them only if browser evidence proved them redundant. It proved them
*partly* redundant: card, inputs, labels and expander summary render identically
without them — same `rgb(236,245,244)` on `rgb(16,27,32)`, 15.78:1, zero
exceptions. But two rules still do work:

| | with | without |
|---|---|---|
| button text | `rgb(145,163,167)` | `rgb(236,245,244)` |
| placeholder | `rgb(145,163,167)` | `rgba(236,245,244,0.6)` |

The button one is load-bearing. Sign-in has one filled primary action and the
secondary control must stay quieter; without the override Streamlit paints both
at full content weight and the card reads as two primaries. Deleting 171 lines
on a partial result would have been a regression, so the evidence is recorded in
the source and the narrowing handed to **Task 13**, which owns the auth surface.

**Three measurement errors I made and corrected before drawing conclusions**,
recorded because each nearly became a false report:

1. Measured a block-level `<div>`'s width (690px) and read it as a broken
   ligature. It was the container; a Range around the text gives 32px.
2. Restarted the app from the main checkout instead of the worktree — the shell
   cwd resets between commands — and briefly measured the *old* palette.
3. Tested rail visibility with `display !== none`, which an off-canvas drawer
   passes. Only on-screen geometry answers that question.

**Test contract migrations.** Seven suites asserted the retired names. Two had
premises that no longer hold and were rewritten rather than repointed:
`test_no_semantic_hue_is_used_as_text_on_a_wash_or_mist` (the quiet grounds are
`*_DIM` now) and `test_trade_detail_uses_light_surface_tokens` → `..._dark_...`
(the card is a dark panel, so the reasoning inverts). `TL_LINE_STRONG` was added
to the neutral side-border set — "strong" is a weight, not a hue.

**Verification:** `1676 passed, 7 skipped` (was `1669/7`); Ruff clean; Black
clean (177 files); `git diff --check` clean. Dev database untouched (`Jul 31`);
all browser and app processes stopped; no capture artifact entered the worktree.

**Files changed:** `design_system.py`, `auth_screen.py`, `data_state.py`,
`app.py`, `1_NewTrade.py`, `2_Trades.py`, `4_Analytics.py`, `6_Insights.py`, and
four test modules. `git add -A` not used; untracked
`src/tradelens/ui/.impeccable/` deliberately not staged.

**Unresolved concerns.**

1. **`TL_RULE = #AFBEC0` is still a light-surface value.** Not in the deletion
   list or any contract test, so touching it stayed out of Task 1 and Task 2.
   It will read too bright on the Evidence Rail and belongs to Task 12.
2. **`theme.py`'s compatibility names still lie** — `PAPER` is a dark panel,
   `INK` is light text. Commented as such; they want retiring.
3. **Analytics was edited beyond Task 2's stated scope** — 19 empty-state icon
   replacements, 13 of them in `4_Analytics.py`, which Task 10 owns. The D9
   empty-state finding is one defect across files, and a guard covering the
   `_empty` adapter while thirteen of its call sites still passed emoji would
   have been false. Flagged so Task 10 knows the file moved.
5. **Emoji remain outside the empty-state renderers** — toasts, the screenshot
   analyzer button, the AI Reviews subheader, and the corrections sidebar. They
   are recorded above against Tasks 8, 9, 12 and 13 rather than changed here,
   because each is a control label or a toast on a surface a later task
   rebuilds.
4. **Empty states were not seen rendered.** The seeded database has 60 trades,
   so no empty state appeared in the sweep; the ligature mechanism was proved by
   injecting a real `.tl-empty-card` and measuring. Task 10 should confirm the
   real ones on a sparse database.

Ownership returned to `NONE`. **Task 3 must not begin until Codex approves.**

### 2026-08-04 — Task 1 amendment: chart template and auth z-scale (Claude)

**Commit:** `0b40b2e`, on top of Task 1's `dbae906`. Scope limited to the two
gate findings. Task 2 not started.

**1. Charts no longer resolve through `pio.templates.default`.**

That default is process-wide mutable state: import order decides it, any test
can swap it, and Streamlit sets its own. A figure that resolved correctly
through it was right by accident. `PLOTLY_TEMPLATE` is now pinned on
`_BASE_LAYOUT` and in `apply_chart_stage`, so the template travels with the
figure.

The old regression test proved nothing — it asserted against the global default,
which is exactly why it passed inside the suite and failed when run alone. The
rewrite sets the default to `plotly_white` first, builds a real figure, requires
the **embedded** template to still be the TradeLens stage, and restores the
global in a `finally` block with a post-condition assert so it cannot leak into
another test.

**2. `auth_screen.py` had the last raw z-index in the product.**

The card's bare `z-index: 1` is now `TL_Z_RAISED`, and the background photograph
and its scrim are `TL_Z_BASE` — the same ordering, stated in the one scale
everything else is measured against. The contract test now inspects `auth_css()`
as well as `build_css()`; a scale only one file is measured against is a
convention, not a contract. A second test pins bg < scrim < card explicitly, so
tokenising the layering cannot silently reorder it.

**Both mutation-checked.** Removing the explicit template fails the template
test; restoring `z-index: 1` fails both z-scale tests.

**3. Two stale comments the token change had falsified.** The
`apply_chart_stage` docstring still said "on the light workspace" — Codex named
this one. Reviewing it surfaced a second: `auth_screen.py` justified its
Streamlit widget overrides with "the workspace base is light", which is now the
opposite of true, and implies most of that block may be redundant now that
`base = "dark"`.

**The overrides were left in place.** Removing widget styling is a visual change
that needs a browser to confirm, and Task 1 has no browser evidence. The comment
now states that plainly and hands the deletion to Task 2.

**4. One assertion tightened rather than deleted.**
`test_charts_pin_the_stage_explicitly_so_streamlit_cannot_repaint_it` scanned
`repr(_BASE_LAYOUT)` for a transparent literal. Embedding the template object
put `rgba(0,0,0,0)` into that repr legitimately — from the template's own
internals, not from the stage. The repr scan was a proxy for "the stage keys are
not transparent", so it now checks those keys directly and additionally asserts
the template identity. The property is unchanged; the proxy was replaced.

**Verification.** Focused tests run individually and together, then the full
suite against the exact final state:

| Check | Result |
|---|---|
| 4 focused tests, one at a time | each 1 passed |
| theme + dark_workspace + charts + auth_screen + design_system | 169 passed |
| Full suite | **1669 passed, 7 skipped** |
| Ruff · Black · `git diff --check` | clean |

**Files changed:** `charts.py`, `auth_screen.py`, `tests/test_theme.py`,
`tests/test_dark_workspace.py`, and this handoff. `git add -A` not used;
untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

**Unresolved concerns carried forward from Task 1**, unchanged: no browser
evidence yet; `TL_RULE = #AFBEC0` still a light-surface value awaiting Task 2;
`theme.py`'s compatibility names still describe light surfaces. Added by this
amendment: the auth widget-override block is probably now redundant and should
be deleted in Task 2 once a browser confirms it.

Ownership returned to `NONE`. **Task 2 must not begin until Codex approves.**

### 2026-08-04 — Phase 2 Task 1: the dark token contract (Claude)

**Commit:** `dbae906`. Task 1 only; Task 2 not started.

**What shipped.** One role namespace (`TL_SURFACE_*`, `TL_CONTENT_*`,
`TL_LINE_*`, `TL_ACCENT_ACTION`) replaces the light workspace and the duplicate
legacy dark set. Superseded names are **deleted, not aliased** — an alias is how
two live systems came to coexist, and a deleted name raises ImportError at the
call site instead of silently changing meaning. 241 references across 5 source
and 6 test files were repointed. The `--tl-z-*` scale is defined and the three
arbitrary literals (1000, 20, 100) are migrated onto it.

**`TL_LINE_STRONG` is `#5C6E77`**, not the spec's original `#3A4E56`, which
measures 1.84–2.20:1 against a required ≥3:1. That was corrected in the
specification as amendment C6 before this task ran, so spec and code agree. The
contract test covers all six surfaces because `TL_SURFACE_ELEVATED` is the
binding case at 3.03:1.

**Three deviations from the plan's letter, all deliberate.**

1. **The skip link went to `--tl-z-overlay`, not `--tl-z-nav`.** The plan mapped
   the `1000` literal to the nav tier. Reading the selector, that literal is the
   keyboard skip link, which was above everything; putting it level with the
   rail lets DOM order decide whether it is reachable. Spec §12 requires full
   keyboard operation, and the spec outranks a line-level mapping in the plan.
2. **`.tl-mobile-nav` went to `--tl-z-nav`, not `--tl-z-sheet`.** Same cause: the
   plan's mapping was made from line numbers, and that selector is the bottom
   navigation itself, not the `More` sheet inside it.
3. **A CSS compatibility bridge was added.** The plan's Step 4 said *add* the
   role properties; my first pass also removed the old ones, which would have
   left every existing rule referencing undefined variables. The old CSS
   variable names now resolve to the new roles, clearly labelled, so the product
   renders between Task 1 and Task 2. **Task 2 must delete that block.** The
   Python names are still gone, so nothing can quietly keep importing them.

**Two defects found by executing, both fixed.**

- The skip link set `color: var(--tl-rail-ink)` — a variable defined nowhere,
  so it inherited onto a near-black background. Pre-existing, and invisible
  until the tokens were audited. A new test fails on **any** `var()` reference
  with no definition, and was mutation-checked by restoring the dangling name.
- `charts.py` carried two greys, muted and faint, one step apart. The role
  system has one secondary content colour and both now resolve to it. Recorded
  as an intended collapse: two greys differing by a hair carried no information
  a reader could use.

**Streamlit's own theme is now dark.** `.streamlit/config.toml` goes
`base = "dark"` with its four values pinned to the role tokens. Streamlit paints
its chrome from these, so leaving them light would have put two palettes on one
screen. Parity is tested.

**Grade chips** moved from the deleted light `PAPER` onto the dark panel, so the
A–F ramp re-points at the dark semantic family with brighter lime and orange
intermediates. All five clear 4.5:1 on the panel.

**Verification:** `1668 passed, 7 skipped` (was `1618/7`); Ruff clean; Black
clean (177 files); `git diff --check` clean. The +50 is 16 source-probe tests
and 37 dark-workspace contract tests, minus 3 hybrid tests deleted as
superseded.

**Files changed:** `.streamlit/config.toml`, `design_system.py`, `theme.py`,
`charts.py`, `auth_screen.py`, `2_Trades.py`; added `tests/source_probe.py`,
`tests/test_source_probe.py`, `tests/test_dark_workspace.py`; migrated
`test_design_system.py`, `test_theme.py`, `test_charts.py`,
`test_auth_screen.py`, `test_premium_page_contracts.py`. `git add -A` not used;
untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

**Unresolved concerns for the gate.**

1. **No browser evidence yet.** Task 1 is a token change and the suite is green,
   but nothing has rendered in a real browser on this commit. Task 2's step 6 is
   the first browser check and will be the first proof the app looks right.
2. **`TL_RULE = #AFBEC0` was left alone.** It is a light-surface Evidence Rail
   colour, not in the spec's deletion list or the contract test, so touching it
   would have widened Task 1. On dark it will read too bright and belongs to
   Task 2, which restyles that component.
3. **`theme.py`'s public names now lie.** `PAPER` is a dark panel and `INK` is
   light text. They are compatibility re-exports with a comment saying so; Task
   2 retires them.
4. **`test_rendered_figures_resolve_to_the_dark_stage` is order-dependent.** It
   fails when run alone and passes in the full suite. Verified pre-existing by
   stashing this task's changes and reproducing it on the original code — not
   introduced here, but worth its own fix.

Ownership returned to `NONE`. **Task 2 must not begin until Codex approves.**

### 2026-08-04 — Journal hydration explicitly tenant-scoped (Claude)

Codex's last plan-gate blocker. Scope was Task 4 only.

**The finding was right, and so was the reason it needed its own guard.** The
journal hydration query filtered on `Trade.id.in_(wanted)` alone. Because
`wanted` is derived from an owner-scoped query, the output was correct — which
is precisely what made the gap invisible: `test_context_is_scoped_to_the_
authenticated_user` passes with or without the predicate.

**Fix.** The hydration is extracted into `_hydrate_journal_rows(db, owner,
wanted)` and filters on `Trade.user_id == owner` as well as the id set.
Extracting it is what creates a seam a test can reach; inline, there was no way
to hand the query a foreign id.

**Guard.** `test_hydration_refuses_a_trade_id_belonging_to_another_user` calls
the helper directly with another user's trade id — the thing the predicate
exists to refuse — and also checks a mixed list returns only the owner's row.
Two supporting tests cover requested-order preservation and the empty-selection
short circuit, which must not open a query at all.

**Mutation check, run both ways as Codex asked:**

| With `Trade.user_id == owner` removed | Result |
|---|---|
| Whole file | 1 failed, 36 passed |
| `test_context_is_scoped_to_the_authenticated_user` alone | **passed** — confirming it was insufficient |
| `test_hydration_refuses_a_trade_id_belonging_to_another_user` alone | **failed** — the only test that catches it |

**Verification, executed from the canonical worktree:**

| Artifact | Result |
|---|---|
| `tests/test_partner_context.py` | 37 passed |
| `tests/test_partner_turn.py` | 31 passed |
| Both together | 68 passed |
| Ruff / Black on all four files | clean |
| Plan code blocks parsing standalone | 40 of 41 |

Product code was copied into the worktree only to run and removed afterwards;
the tree is documentation-only and the `1618 passed, 7 skipped` baseline is
untouched. **No implementation has begun.**

**Files changed:** the plan and this handoff.

Ownership returned to `NONE`.

### 2026-08-04 — Task 4 and Task 14 amended for the final gate (Claude)

Scope was Task 4 and Task 14 only. The token, specification, layout, and Task 16
decisions were not reopened, and everything else in `f546922` is untouched.

**Task 14 — three containment boundaries, not one.**

`build_context(user_id=…)` now sits *inside* the containment. It opens a
database session, so it can fail with a driver error carrying a DSN, and that
failure was previously outside the `try` — it would have escaped as a raw
exception onto the page. A test raises a `psycopg2.OperationalError` carrying
`postgresql://tl:hunter2@…` and an `sk-ant-` key and asserts the question
survives, fixed copy is stored, the exception is logged exactly once, nothing
was billed, and no fragment of the DSN or key appears anywhere in state.

`log_ai_usage` is contained separately, **after** the reply is stored. Cost
logging is bookkeeping; a failed write must not discard an answer the trader has
already been given. The turn stays `ok=True`, `usage_logged` goes `False`, the
failure is logged, and no error slot is set — a rendered error would tell the
trader their answer failed when it did not.

**Task 14 — "Context used" is now per turn and persistent.**

Each assistant turn stores the labels it was answered from, so a rerun
re-renders the right records under the right answer instead of putting the
newest context under every one. Tests cover two successful turns with different
contexts plus a rerun, and an empty context storing no labels so no heading
renders.

`to_api_messages` then projects stored turns down to `role` and `content` before
the service sees them. Presentation metadata is ours; sending it would put
unrequested fields in the API payload and feed the model a list of record labels
as though it were conversation.

**Task 4 — one definition of a journal entry.**

`_journal_text` now strips each candidate *before* judging it. The previous
version tested truthiness first, so a `trade_process_notes` of `"   "` won the
`or` chain — a non-empty string is truthy — and a real `notes` value behind it
was silently lost. Process notes still take precedence when they say something.

`journal_entry_count` is computed with that same function rather than a SQL
count, so the number the trader is shown and the notes the prompt carries cannot
answer different questions. The SQL clause only narrows and is documented as
such: `TRIM` strips spaces but not tabs or newlines, so it cannot be the
authority.

**Six behaviours mutation-checked**, each reverted in turn to confirm the suite
fails: context assembly outside containment (3 failures), uncontained usage
logging (1), unprojected history (1), labels not stored per turn (2),
`_journal_text` back to the truthiness chain (4), and counting rows instead of
meaningful notes (1).

**One defect the verification caught.** The send-path test file imported
`partner_turn` by bare module name, which works in a scratch directory and
fails collection in the worktree. Corrected to the real path and re-run there.

**Verification, executed from the canonical worktree:**

| Artifact | Result |
|---|---|
| `tests/test_partner_context.py` | 34 passed |
| `tests/test_partner_turn.py` | 31 passed |
| Both together | 65 passed |
| Ruff / Black on all four files | clean |
| Plan code blocks parsing standalone | 40 of 41 |

Product code was copied into the worktree only to run and removed afterwards;
the tree is documentation-only and the `1618 passed, 7 skipped` baseline is
untouched.

**Files changed:** the plan and this handoff. The specification was not touched.

Ownership returned to `NONE`.

### 2026-08-04 — Four remaining blockers closed; spec amended too (Claude)

Codex's second review confirmed the original seven were addressed and found four
more. All four were real, and one of them was a defect in the *specification*,
not the plan.

**1. Spec and plan no longer disagree — the spec was wrong.** Previously the plan
carried `#5C6E77` while spec §4.1 still said `#3A4E56`. Rather than leaving the
plan deviating from its own source of truth, the specification is amended:
§4.1's token block now reads `#5C6E77`, §4.4 carries the measured table for both
values and states the contract as **all six surfaces**, and §15.3 records it as
amendment C6. `TL_SURFACE_ELEVATED` is named as the binding case — it is the
lightest surface and it is where the Partner drawer's edge sits, so a
canvas/rail/panel check would have passed a value still failing on the drawer.
`TL_LINE_HAIRLINE` is explicitly exempt from the 3:1 floor with a required test
that it stays quieter than the strong line.

**2. `build_global_partner_context` now admits atomically.** The previous draft
built the text and the evidence list in lockstep and then trimmed them
*independently* — text by character budget, sources by count. That produces
exactly the two lies this surface cannot tell: an evidence link to a record the
model never saw, and a claim drawn from a record the trader cannot open.

`_admit` now takes a line and its source together or neither, and **skips** a
candidate that does not fit rather than stopping, so one oversized journal note
cannot suppress the completed-trade and strategy sections behind it. Headings are
emitted only when their first candidate is admitted, so no header stands over
nothing. Row budgets sum to `MAX_EVIDENCE_SOURCES`, making the evidence cap a
backstop rather than a limit that silently starves later sections.

21 tests, including the five Codex named — oversized first note, character
truncation, evidence truncation, blank notes, and continued inclusion of the
trade and strategy sections — plus a shared `_assert_invariant` helper that
re-checks source-iff-contribution on every scenario.

**3. Task 4 is standalone; both open decisions are closed.**

- **Owner validator: mirrored, not promoted.** `_require_concrete_user_id`
  already exists as a private copy in `strategy.py:121`, `cost.py:34`, and
  `app_settings.py:16`. Three service modules carrying their own copy *is* this
  codebase's convention, so a fourth follows it rather than adding a
  cross-service import for six lines.
- **Strategy serializer: the public API, not the private one.** The adapter calls
  `get_active_strategy(user_id)` instead of importing `strategy._to_dict`. It is
  public, already owner-validated, already tested, and its dict already carries
  `id`, which is what the evidence descriptor needs.

Both decisions mean **no other service file changes**, so Task 4's file list is
unchanged. Exact imports are now listed.

**4. Task 14's send path is implemented and pinned.** It lives in a new
Streamlit-free `partner_turn.py`, following the `trade_wizard.py` precedent, so
the orderings are provable without a browser. 20 tests pin: the exact
`partner_reply(list(history), trade_context=…, strategy_profile=…,
per_trade_qa=False)` arguments; the user turn appended **before** the call so a
failure never costs the trader their question; usage logged **only** on success
and exactly once with the authenticated user; the assistant turn appended only
on success; prior turns surviving both error classes; and an unexpected error
rendering fixed copy while the raised DSN and `sk-ant-` key stay out of state.

**On evidence, Codex was right and the previous draft overclaimed.**
`partner_reply` returns `(reply_text, usage)` and nothing else, so it cannot
report which records a given sentence drew on. Presenting the adapter's records
as per-answer citations would assert a relationship the service never
established. The contract is now `CONTEXT_USED_LABEL = "Context used"`, with the
list omitted entirely when empty. Two tests hold the line, asserted on the API
surface rather than on prose — a text scan cannot tell an explanation of why
citations are not claimed from a claim, which is a mistake the first attempt
actually made.

**5. Task 16 tests rendered output.** The unused import is gone — replaced by a
test that makes `error_box` earn its import by proving it escapes what it is
handed. Containment is now asserted on the elements AppTest actually emits, via
`rendered_text(at)`, driving three representative leaky exceptions (a Postgres
DSN, an `sk-ant-` key, an SMTP password) through the real `error_box`. Two probe
tests prove the check can detect a leak and an uncontained raise, so the negative
tests cannot silently pass forever.

Running it against the current codebase produced three corrections worth
recording:

- **`pages/_archive/` must be excluded.** Sweeping it reported four "unscoped"
  calls in superseded files nothing imports.
- **Only broad handlers may be flagged.** `2_Trades.py:855` deliberately renders
  `OutcomeMismatch` — a domain error with trader-safe copy — beside the two
  fields that disagree. That is correct, and a rule that flagged it would have
  been either rejected or, worse, obeyed.
- **Scoping must be AST-based.** A regex window read `create_trade(data)` in
  `1_NewTrade.py` as unscoped because the owner is set into `data` twenty lines
  earlier. That call site is now an explicit allowlist entry with its own
  dead-entry test, rather than a silent hole in a pattern.

**One rule was written and then withdrawn.** A draft asserted every broad handler
must log or surface what it swallowed. It failed on five existing files. It
encoded a preference this codebase has not adopted, was not requested, and would
have blocked Task 16 on pre-existing code — so it is not in the plan. If it is
wanted it is its own change with its own review.

**6. No `...` stubs remain.** The last one, `_next_review_action`, is now a prose
signature whose complete implementation sits in its task's Step 3.

**7. Everything was executed, not parsed.** Every file above was written to disk
and run:

| Artifact | Result |
|---|---|
| `source_probe` + `review_document` | 32 passed |
| `partner_turn` (Task 14) | 20 passed |
| metrics vs. the real `metrics.py` | 15/15 |
| `partner_context` + `dark_accessibility` | 37 passed, 5 skipped |
| Ruff / Black, all files | clean |
| Plan code blocks parsing standalone | 40 of 41 |

The five skips are the composited-contrast cases, gated on Task 1 introducing
the role tokens; injecting those tokens confirmed the gate opens and they pass,
so they are not skipped forever. The 41st block is a labelled f-string fragment.

Product code was copied into the worktree only to run, and removed after; the
tree is documentation-only and the `1618 passed, 7 skipped` baseline is
untouched.

**Files changed:** the plan, the specification, and this handoff.

Ownership returned to `NONE`.

### 2026-08-04 — Plan amended after Codex found execution defects (Claude)

Codex reviewed `2363ea2` and found seven blocking defects. All seven were real.
The through-line: the first rebuild asserted that its code worked instead of
running it. This pass ran it.

**1. `TL_LINE_STRONG` did not pass its own test.** Codex measured ~1.74–2.17:1;
my computation gives 1.84–2.20:1 across the six surfaces, against a required
≥3:1. Either way the spec's `#3A4E56` fails, and Task 1's contract test would
have failed on the value the same task installs.

Replaced with `#5C6E77` — the smallest value on the same cool blue-grey ramp
clearing 3:1 everywhere. The measured table is in the plan.

**`elevated` is the binding surface, not canvas.** It is the lightest of the six
*and* it is where the Partner drawer's edge sits, so the three-surface check the
spec implies (canvas/rail/panel) would have passed a value still failing on the
drawer. The test now covers all six. **This needs a spec amendment**: §4.1's
token block and §4.4's closing sentence both still say `#3A4E56`.

**2. Every command was unrunnable.** The redesign worktree has no `.venv`; the
interpreter lives in the main checkout. All 57 `.venv/bin/…` invocations now go
through one exported `$PY`, verified from the canonical worktree.

Verifying that surfaced something the plan had wrong on its own: **the
environment is Python 3.9.6, not the 3.11 `CLAUDE.md` claims**. That is the
interpreter that produced the `1618 passed` baseline. The consequence binds
every task — new modules need `from __future__ import annotations` or PEP 604
unions are a runtime `TypeError`. `app.py:1` already carries it with a comment
saying exactly why; `metrics.py` does not, which is why Task 4 uses
`typing.Optional`. Ruff and Black are invoked as `"$PY" -m …` so a stray binary
on `PATH` cannot be used by accident.

**3. `function_source` and `outside` were both broken.** Both used
`re.search(r"^\S", rest[1:], re.M)` to find a block end. With `re.MULTILINE`,
`^` matches at offset 0, so that returned a one-character block — every
structural assertion built on them would have been a false pass. `media_context`
had a third bug: it reported the nearest preceding `@media` even when that query
had already closed.

Rewritten line-based and brace-counted, and now shipped with
`tests/test_source_probe.py` — 16 tests covering complete-body extraction,
stacked decorators, nested same-name methods, last-function-in-file, first-match
removal, and the closed-media-query case. Both files are in Task 1's commit,
which they were not before.

**4. Placeholders replaced with executed code.** `edge_leak_summary`,
`_is_recorded`, `_leak_mask`, `_has_leak_evidence`, `parse_review_markdown`,
`_next_review_action`, `PartnerContext`, `PartnerEvidenceSource`, and
`build_global_partner_context` are now complete.

The metrics implementations were run against the **real** `metrics.py` —
`_is_followed`, `_parse_mistake_tags`, `_safe_float` are the shipped functions,
not paraphrases — and pass 15/15, including agreement with `total_edge_leak`
across five frame shapes. That run caught a trap now recorded in the plan:
`mistake_tags` is a **JSON-list string**, so `_parse_mistake_tags("fomo")`
returns `[]` and test data using bare tags silently exercises nothing.

The parser passes 16 tests including three edge cases the first draft had not
considered — an unclosed fence, a backtick fence not closed by tildes, and a
heading with no alphanumerics.

For the Partner adapter I stopped at complete implementation rather than
inventing a service Codex owns: the interface, ordering, pre-session owner
rejection, whole-journal counts, and structured evidence sources are pinned by
tests, and Codex may adjust budgets and text shape. It reuses
`strategy.py:121`'s existing `_require_concrete_user_id` rather than adding a
second validator.

**5. Partner fixtures defined.** `seeded_user`, `seeded_two_users`, and
`seeded_large_user` now follow the isolation pattern already established at
`tests/test_user_isolation.py:28` — in-memory SQLite, `create_all`, the
service's `SessionLocal` monkeypatched, `drop_all` and `dispose` on teardown,
with a `StaticPool` so the seeded rows survive across connections.

**6. Task 16 rewritten against real mechanisms.** The seven sketched helpers are
gone. `composite()` and `boot_page()` are implemented; the rest are replaced by
existing machinery.

This one mattered more than it looked: my `_rendered_pages` sketch would have
rendered pages in-process, and `tests/app_boot_check.py` carries an explicit
warning against exactly that — it creates a second copy of `ai_client` and was
**measured at 34–47 spurious failures**. Task 16 now uses the documented
subprocess boot. Heading sequence and tab order moved to the browser step, where
they can actually be measured.

**7. Full sweep.** Remaining `...` are three interface signatures whose bodies
appear in their task's implementation step, plus one labelled f-string fragment.
Task 1 now stages `source_probe.py` and its tests; Task 15 stages
`tests/test_pages_boot.py`, since `ALL_PAGES` drives the parametrised boot test
and a page missing from it is a page nothing proves boots. Ruff caught an unused
`ReviewSection` import in the plan's own test file — fixed by asserting the type
rather than dropping the import.

**One correction to my own process.** While sweeping I reported finding a
Markdown fence defect, on the strength of a check that used a non-greedy regex
to extract code blocks. That regex was wrong, not the document: a ``` inside a
Python string mid-line does not close a fence. Re-checked with a correct
line-based fence parser, all 39 blocks were already well-formed. The two blocks
were still promoted to four-backtick fences, because naive extractors — mine
included — mishandle them, but the plan was not broken and I should not have
said it was.

**Validation performed:** `source_probe` 16 passed · `review_document` 16 passed
· metrics 15/15 against the real module · Ruff and Black clean on all four
scratch files · 38 of 39 plan code blocks parse standalone · `"$PY" -m pytest
tests/test_data_state.py -q` → 17 passed from the canonical worktree ·
`git diff --check` clean.

**Not run:** the full suite, because no product code changed. The `1618 passed,
7 skipped` baseline is untouched.

**Files changed:** the plan and this handoff. Documentation only. `git add -A`
not used; untracked `src/tradelens/ui/.impeccable/` again not staged. The
verification scripts stayed in scratchpad and did not enter the worktree.

Ownership returned to `NONE`.

### 2026-08-04 — Consolidated implementation plan rebuilt (Claude)

Codex approved `8b35a6e` and `3bb4a5f`, which cleared §16.5's gate. The plan was
rebuilt from the three named sources with `superpowers:writing-plans`.

**Plan:** `docs/superpowers/plans/2026-08-04-phase2-dark-workspace-implementation.md`
— 17 tasks, 143 checkbox steps, 2509 lines. Each task carries exact file paths,
an Interfaces block naming what it consumes from earlier tasks and produces for
later ones, real test code before real implementation, and a Codex review gate.

**How the three sources were used.**

- The **spec** supplies the design contract. A closing coverage table maps every
  spec section to the task that implements it, so a gap is visible rather than
  discovered late.
- The **preflight** overrode source-only reasoning in three places, recorded in
  the plan's own "What the browser preflight already changed" section: the
  Partner breakpoints (drawer at every sidebar-navigation width ≥768, full-page
  destination only at ≤767 where bottom navigation actually renders), the
  dataframe toolbar controls measured at ≈22.4×22.4 CSS px at 1440, and the
  nested-route `_stcore` 404s as pre-existing infrastructure noise rather than a
  redesign target.
- **This file's rulings** became Task 4 verbatim. `RuleAdherenceSummary`,
  `EdgeLeakSummary`, and `build_global_partner_context(*, user_id)` are written
  as fixed interfaces that implementation may not renegotiate.

**Ownership is explicit in the plan, not implied.** Task 4 is marked
Codex-owned; if Claude reaches it, it stops and hands over the lock. The plan's
global constraints repeat that Claude writes no service code and that
`ai_client.py`, `partner.py`, `metrics.py`, and the auth/database/cost/tenant/
secret modules are Codex-owned.

**Two decisions the plan makes that are worth Codex's attention.**

1. **Grade tokens are re-pointed at the dark semantic family.** `TL_GRADE_A`–`F`
   currently alias the light-workspace ramp (`TL_SUCCESS_INK`, `TL_WARNING_INK`,
   `TL_DANGER_INK`), which Task 1 deletes. The plan re-points A/C/F at
   `TL_SUCCESS`/`TL_WARNING`/`TL_DANGER` and gives B and D brighter
   lime/orange values, with a test asserting all five clear 4.5:1 on
   `TL_SURFACE_PANEL`. This was not in the spec — the spec's deletion list made
   it necessary, and it is flagged here rather than buried in a task.
2. **`MIN_DATED_POINTS` is exposed publicly rather than duplicated.** Spec §5.4a
   requires one policy for the equity curve and the calendar heatmap. The plan
   exposes the existing `_MIN_DOMINANT_POINTS` constant as
   `data_state.MIN_DATED_POINTS` with `show_dated_instrument(state)`, and pins
   the two gates together with a parametrised test across 0–8 populated days, so
   the heatmap cannot drift onto a second threshold.

**Two known gaps are carried forward unchanged**, stated in the plan's closing
section rather than silently dropped: the TradeZella reference images were never
received, and the Partner's `position: fixed` behaviour is still unverified
(Task 14 step 7 verifies it; step 8 is the reviewed docked fallback, which
remains a recorded decision and never a silent substitution).

**Files changed:** the plan (added) and this handoff. Documentation only — no
product code, no service, no test, no token file touched. `git add -A` not used;
untracked `src/tradelens/ui/.impeccable/` again deliberately not staged.

**Tests and browser checks:** none. Nothing executable changed.

Ownership returned to `NONE`.

### 2026-08-03 — New Trade fix amended after Codex review (Claude)

Codex approved the crash fix but withheld approval because an uploaded
screenshot was still lost after Back. Codex was right, and the reasoning in my
previous commit comment was wrong where it mattered.

**What I got wrong.** I wrote that the deletion branch "only runs while the
uploader is on screen, so an empty widget here means the trader removed the
file." The uploader is also on screen immediately after Back — freshly
remounted and reporting `None` without the trader touching anything. That path
deleted the mirror. The `6 of 15` Codex saw on the first returned render was
`_FIELD_VALUES` reading the mirror at module level before `_step_screenshot()`
deleted it further down the same run, which is why the loss only surfaced as
`5 of 15` on the next step.

**Corrected mechanism.** The mirror is now synchronised *only* from the
uploader's `on_change` callback, which Streamlit fires on a genuine upload or
removal and never on a remount. Two pure helpers moved into `trade_wizard.py`
so the semantics are unit-testable without a browser:

- `sync_screenshot_mirror(state)` — callback-only; stores on upload, clears on
  a real removal.
- `effective_screenshot(state)` — live widget wins, mirror answers otherwise.

The page renders the effective screenshot, so after Back the preview and the
draft count both hold. Because a remounted uploader cannot be told to show the
file it had, the retained state is now stated explicitly ("Kept from earlier in
this draft: <name>") with its own **Remove chart** control — without it a
retained chart could never be taken off, since the uploader's own ✕ is gone
with the remount.

**A second defect the real-file run exposed.** Codex's instruction to test with
an actual image was what caught it. Once a chart is uploaded, the autofill panel
renders three `st.button`s keyed `_nt_ai_apply`, `_nt_ai_cancel`, and
`_nt_ai_analyze`. Buttons are unsettable exactly like uploaders, and all three
sit under the `_nt_` prefix, so `keep_alive` swept them up and Back raised
`StreamlitValueAssignmentNotAllowedError` for `_nt_ai_analyze`. My first fix
could not have caught this: with no file uploaded, that panel never renders. All
three are now exempt. Re-asserting a button is pointless as well as illegal — a
click is an event, not a draft value.

**Guards, three of them mutation-checked:**

- `test_the_page_syncs_the_mirror_only_from_the_change_callback` — requires
  `on_change` on the uploader and allows at most one mirror deletion inside
  `_step_screenshot` (the explicit Remove control). Reintroducing the exact
  render-time deletion makes it fail.
- `test_every_unsettable_widget_key_is_exempt_from_keep_alive` — now scans
  **both** `1_NewTrade.py` and `ai_autofill_review.py` for `st.button`,
  `download_button`, `form_submit_button`, `chat_input`, and `file_uploader`
  keys under the wizard prefixes, resolving literal and constant keys alike.
- `test_the_exemption_set_has_no_dead_entries` — the exemption set may not name
  a widget that no longer exists.
- Unit coverage for store / clear-on-removal / replace / remount-is-not-a-change
  / live-wins / mirror-fallback / none, plus reset and ownership-change
  clearing.

**Real-file browser round trip** — headless Chrome over CDP at 1440, real PNG
uploaded through `DOM.setFileInputFiles`, throwaway SQLite database:

| Phase | Draft | Exceptions | Retained state |
|---|---|---|---|
| after upload | 6 of 15 | 0 | — |
| Forward to step 2 | 6 of 15 | 0 | — |
| Back to step 1 | **6 of 15** | **0** | shown |
| Forward again | **6 of 15** | 0 | — |

Chart identity was verified, not assumed: Streamlit serves uploaded media at a
content-addressed URL, and it is byte-identical before and after Back
(`/media/0617287abe4…jpg`), with the filename `test_chart.png` preserved in the
retained caption. An intermediate run of this same script — before the button
keys were exempted — reproduced the `_nt_ai_analyze` exception, so the driver
demonstrably detects the failure it is asserting against.

**Verification:** `1618 passed, 7 skipped` (was 1608/7); Ruff clean; Black clean
(174 files); `git diff --check` clean. Dev database untouched
(`data/tradelens.db`, Jul 31); no capture artifact entered the worktree; both
browser and app processes stopped.

**Files changed:** `src/tradelens/ui/components/trade_wizard.py`,
`src/tradelens/ui/pages/1_NewTrade.py`, `tests/test_trade_wizard.py`, and this
handoff. `ai_autofill_review.py` was read but **not modified** — the exemption
lives in the wizard. No services touched; `.impeccable/` left untracked.

**Stale reference corrected.** The previous entry pointed at `ce80324`, which
was the pre-amend hash — `git commit --amend` had rewritten it to `b9084ba`. A
commit cannot contain its own hash, so the pointer is now set in a follow-up
commit rather than by amending. The amendment is `8b35a6e`; the commit that
carries this pointer is the branch head.

**For Codex, two things worth a second opinion:**

1. The mirror holds an `UploadedFile` reference across reruns. Consumers only
   read in-memory `BytesIO` data and the browser run confirms the bytes survive,
   but lifetime remains the judgement call in this change.
2. The exemption set is a hand-maintained list bound to source by a scanning
   test. That is the best available given Streamlit exposes no way to ask
   whether a key is settable — but if you know of a runtime check, it would be
   strictly better than a scan.

Ownership returned to `NONE`.


### 2026-08-03 — New Trade Back-navigation regression fixed (Claude)

Scope was the single documented blocker in
`docs/superpowers/audits/2026-08-03-browser-preflight.md`. No redesign work, no
service changes, no plan rebuild, `.impeccable/` untouched.

**Root cause — not where the traceback pointed.** The audit cited the
`st.file_uploader` at `1_NewTrade.py:340`, which is where the exception
*surfaces*. The cause is `keep_alive()` in `components/trade_wizard.py`, which
re-asserted every wizard-owned key with `state[key] = state[key]` so Streamlit
would not discard off-step draft values. `nt_shot` is a `file_uploader` key, and
Streamlit forbids assigning those through session state at all — even
re-assigning the identical value marks the key user-set, and the next
instantiation of that widget raises. Hence: step 1 renders the uploader, the
step-2 run re-asserts the key, and the Back run raises when step 1 rebuilds it.
No upload is needed to reproduce it.

**Fix, in two parts.**

1. `trade_wizard.py` — added `UNSETTABLE_WIDGET_KEYS = frozenset({"nt_shot"})`
   and made `keep_alive` skip it. Popping such keys is still legal, so
   `reset_wizard_state` and `wizard_owned_keys` are unchanged and a reset still
   clears the uploader.
2. `1_NewTrade.py` — skipping the key alone would have traded a crash for a lost
   screenshot, since Streamlit then discards `nt_shot` on steps 2–5. Added
   `SCREENSHOT_DRAFT_KEY` (`_nt_shot_file`), a plain non-widget mirror written
   while the uploader is on screen and read as a fallback when it is not. The
   `_nt_` prefix is deliberate: it makes the mirror wizard-owned, so `keep_alive`
   preserves it and a reset clears it — a mirror outside that prefix would
   survive a reset and leak one trader's chart into the next draft. The mirror
   holds the `UploadedFile` object (a `BytesIO` subclass), so every consumer
   contract — `.getvalue()`, `.name`, `.size`, `.file_id`, `save_screenshot`,
   `st.image` — is unchanged.

**AppTest cannot reproduce this defect, and that is worth knowing.** It discards
`nt_shot` at the end of the step-2 run, so the user-set marking never survives
to the Back run. Verified directly: the step 1 → step 2 → Back AppTest passes
against the *unfixed* code. Those two round trips are therefore committed as
workflow smoke tests and labelled as such in the file, not presented as the
regression guard.

**What actually guards the regression** — five tests added to
`tests/test_trade_wizard.py`, two of them mutation-checked by removing the
exemption and confirming both fail:

- `test_keep_alive_skips_keys_streamlit_forbids_assigning` — the root cause.
- `test_every_uploader_key_on_the_page_is_exempt_from_keep_alive` — scans the
  page for `st.file_uploader(key=...)` and fails if any key is missing from the
  exemption set, so a second uploader cannot silently reintroduce the crash.
- `test_screenshot_draft_key_is_wizard_owned` — pins the mirror inside the
  owned prefix so a rename cannot leak a chart across a reset.
- two workflow smoke tests, labelled.

**Live browser round trip, run both ways** — headless Chrome over CDP at 1440,
against a throwaway SQLite database in scratchpad, `DEMO_MODE=true`:

| Phase | Fix disabled | Fix enabled |
|---|---|---|
| step 1 | 0 exceptions, 1 uploader | 0 exceptions, 1 uploader |
| step 2 | 0 exceptions, 0 uploaders | 0 exceptions, 0 uploaders |
| Back to step 1 | **1 exception**, 0 uploaders, buttons collapse to `Copy` | **0 exceptions**, 1 uploader, `Browse files` back |

With the exemption disabled the browser reproduced the audit's error verbatim:
`StreamlitValueAssignmentNotAllowedError: Values for the widget with key
'nt_shot' cannot be set using st.session_state`. The dev database was not
touched (`data/tradelens.db` unchanged); no capture artifact entered the
worktree; both processes were stopped.

**Verification:** `1608 passed, 7 skipped` (was 1603/7 — the five additions);
Ruff clean; Black clean (174 files); `git diff --check` clean.

**Files changed:** `src/tradelens/ui/components/trade_wizard.py`,
`src/tradelens/ui/pages/1_NewTrade.py`, `tests/test_trade_wizard.py`, and this
handoff. `git add -A` not used; `src/tradelens/ui/.impeccable/` left untracked.

**For Codex:** the mirror holds a reference to an `UploadedFile` across reruns.
Consumers only touch in-memory `BytesIO` data, so it is sound for this flow, but
it is the one part of this change worth a second opinion on lifetime.

Ownership returned to `NONE`.


### 2026-08-03 — Partner placement adopted; handed to Codex (Claude)

**Owner decision adopted (spec §8.2a, logged as C4 in §15.2).** The Partner takes two
presentations of one conversation, split by active navigation pattern rather than a raw pixel
value:

| Active navigation | Partner | Launcher |
|---|---|---|
| Rail (≥1024) | Fixed bottom-right non-modal drawer | Bottom-right FAB |
| Bottom nav + `More` (≤1023) | Full-page destination via the `More` sheet | None |

**This deleted more spec than it added.** Mutual exclusivity is now structural — at bottom-nav
widths there is no Partner overlay to conflict with the `More` sheet. Removed outright: the
`:has(details[open])` selector and its browser-support floor, the hidden-is-not-closed
ambiguity, the `display: none` tab-order verification, and the four-combination open/closed test
matrix. Amendment C2 is marked superseded rather than edited away.

**New obligations recorded:** one `MOBILE_MORE` entry in `sidebar.py` that marks itself active on
the Partner page; a deep-linkable Partner route consistent with `route_href`; `session_state`
turns surviving navigation away and back; and the Partner omitted from the desktop rail so one
conversation never has two entry points at one width. The last needs verification that
Streamlit's automatic navigation is suppressed for the new page file rather than assumed.

**Codex questions partially answered by this decision:** Q4 is resolved — the fixed-positioning
check now gates only the desktop drawer and its failure mode is a contained desktop fallback
(right-hand column), not a cross-breakpoint scope change; Claude runs it and reports. Q3 is
narrowed — one context-adapter signature serves both presentations.

**Sections touched:** §3, §4.5, §8.2, §8.2a, §8.4, §8.5, §11, §15.2. Spec is 1256 lines.

**Files changed:** the spec and this handoff. Documentation only. No product code. `git add -A`
not used; untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

**Handing to Codex now.** Claude has released the lock and is NOT proceeding into the five items
below, because the handoff contract assigns all of them to Codex: `ai_client.py` is Codex-only
and never edited concurrently, model routing and cost logging are Codex-owned, and the remaining
work is debugging, CI, and service-layer signatures. Claude will not answer Q1–Q3 or Q5 on
Codex's behalf, and will not touch the Opus 5 migration or the cost test.

**Codex scope for this handoff:**

1. Review the Phase 1 specification for scope, AI safety, tenancy, and exception-containment
   implications. Inspect the diff across `17382f9`, `2d04f37`, `c3ce33d`, and this commit — do
   not trust the prose summaries.
2. Answer spec §16 Q1 (`rule_adherence_rate` signature and empty-sample behaviour — the UI
   cannot honestly render a percentage without n), Q2 (edge-leak zero disambiguation across
   no-leak / exact-zero / absent-columns), Q3 (Partner context-adapter signature), and Q5
   (rebuild the implementation plan now, or hold until the baseline is green).
3. Review and isolate the Opus 5 migration into its own reviewed commit, then bring it into this
   branch without importing unrelated dirty-tree changes from the main checkout.
4. Fix the UTC-sensitive cost test using the current UTC month or an injected/frozen timestamp
   in the test. Do not change production UTC timestamping to satisfy a hard-coded month.
5. Return a green baseline: `pytest tests/`, `ruff check src/ scripts/`,
   `black --check src/ scripts/`, `git diff --check`.

**Stop before frontend implementation.** Do not begin Task 1 of the redesign. Return the lock to
`NONE` with findings so Claude can rebuild the implementation plan from the approved spec.

**Still-open caveat, unchanged:** no baseline browser evidence exists. Two live-browser checks
remain gated on the green baseline — `position: fixed` containing-block behaviour and
stacking-context isolation, both desktop-only after C4.

### 2026-08-03 — Owner-directed documentation corrections (Claude)

Three bounded corrections requested before Codex approval. **Documentation only** — no product
code, no rerun of UI/UX Pro Max, no other redesign. Recorded in spec §15.1 as C1–C3.

**C1 — Heatmap sparse-data rule reconciled with §5.7.** The previous pass introduced a
"~20 populated cells" heatmap gate that was both unsupported and in direct contradiction with
§5.7, which had the heatmap appearing at "4–9 trades". Both are replaced by one explicit,
testable policy in new spec §5.4a:

- **Populated trading day** = one distinct non-empty `trade_date` carrying ≥1 trade. Two trades
  on one date count as **one** day. This is what `sample_state.dated_points` already counts.
- **Policy: a dated instrument requires ≥ 4 populated trading days.** Applies identically to the
  equity curve and the calendar heatmap. Below it, the curve states the standing and the heatmap
  falls back to a ranked day list from the same `calendar_daily_pnl` rows.
- **Source: no new number was invented.** `sample_state.show_dominant_series` already gates the
  curve at four dated points, is already implemented, and is already covered by tests; the
  `--domain chart` pass independently set the line-chart floor at "fewer than 4 data points".
  Extending that one constant to the heatmap replaces two thresholds with one.
- §5.4a records why the generic "fewer than 20 cells" heatmap heuristic **does not transfer**: it
  assumes every cell samples a continuous variable, so an empty cell is missing data. In a
  trading calendar an empty day means no trade was taken, which is information — a sparse month
  is a truthful picture of a sparse month.
- §5.4a also separates the two units that were being conflated. Populated-trading-day gates
  govern dated instruments; **trade-count** gates remain keyed to their own code constants
  (`_MIN_TRADES_FOR_CONSISTENCY` = 5, `TRADES_FOR_REVIEW` = 5). A statement in one unit may never
  be read as the other.
- §5.7 is rewritten on both axes (`d` = populated trading days, `t` = trade count), which move
  independently, and carries a worked example: `t=3, d=1` renders bands 1, 2, and 5 with both the
  curve and the heatmap withheld. Under the old text that case would have drawn the heatmap while
  simultaneously requiring 20 cells.
- Amendment A3 from the previous pass is explicitly marked superseded rather than edited away.

**C2 — Mobile `More` and Partner sheets made mutually exclusive.** New spec §8.2a. Opening
either closes the other; the launcher is hidden while either is open; the Partner never layers
over or obstructs navigation.

- The §4.5 z-scale is **reordered so navigation always outranks the Partner**:
  `base 0 / raised 10 / partner 20 / nav 30 / sheet 40 / overlay 50`. This reverses the previous
  pass's partner-above-sheet rationale, which had argued the Partner should stay reachable while
  the sheet was open. That reasoning no longer applies now that the Partner is hidden while the
  sheet is open. **This is the one place a previously recorded rationale was overturned**, and the
  reversal is noted in §4.5 rather than silently rewritten.
- The mechanism is **asymmetric, and the spec says so plainly.** Partner-opens → `More` closes is
  guaranteed with no script: opening the Partner triggers a rerun, and the rerun re-emits the
  `<details>` without `open`. `More`-opens → Partner cannot be *closed* without JavaScript,
  because a native `<details>` toggle never reaches the server; it is instead **hidden by CSS**
  via `:has(.tl-mobile-nav details[open])`.
- Two consequences stated rather than glossed: **hidden is not closed** (Partner state survives,
  so dismissing `More` restores the drawer — deliberate, since the trader did not ask to end the
  conversation), and `display: none` removing hidden widgets from the tab order **must be
  verified**, since Streamlit still instantiates them server-side.
- `:has()` support floor recorded (Safari 15.4+, Chrome 105+, Firefox 121+) with two fallbacks: a
  DOM-sibling selector, then escalation to the §8.2 docked-Partner fallback, which makes the two
  exclusive by construction.
- Verification matrix added at coarse 375 and coarse 768 for all four open/closed combinations.
- §8.4, §8.5, and §11 updated so the component inventory, state table, and responsive table all
  state the exclusivity.

**C3 — Two stale `§16` cross-references corrected to `§15`** (spec header and §0.4), left behind
when the amendments section was inserted ahead of the open-questions section.

**Self-review after correction:** no unfinished markers; no duplicate headings; the surviving
mentions of "20 cells" and "4–9 trades" appear only inside the §15/§15.1 changelog explaining what
was superseded; §5.5's gate now defers to §5.4a rather than restating a threshold; the
`var(--tl-z-partner)` reference in §8.2 resolves against the reordered scale. Spec is 1230 lines.

**Nothing else changed.** IA, the five-band Overview reading order, the AI Reviews note anatomy,
both owner decisions in §8, and every safety boundary are untouched. No new product or design
decision was required to make these corrections, so no question was escalated.

**Files changed:** the spec and this handoff. `git add -A` not used. Untracked
`src/tradelens/ui/.impeccable/` again deliberately not staged.

**Tests and browser checks:** none — documentation only. The §0.3 sequencing caveat stands, and
C2 adds a third item to the list of checks that require a live browser before implementation:
`position: fixed` containing-block behaviour (§8.2), stacking-context isolation (§4.5), and the
sheet-exclusivity matrix (§8.2a).

Ownership returned to `NONE`.

### 2026-08-03 — UI/UX Pro Max bounded validation pass (Claude)

**Why this pass happened.** The owner asked Claude to confirm, without inferring it from the
prompt, whether `/ui-ux-pro-max` had actually been invoked and its required searches run.

**Honest answer: they had not.** The skill's `SKILL.md` text was in context and its Quick
Reference rules were applied directly — traceably producing finding D9 (`no-emoji-icons`), the
ranked-list form in Overview band 4 (`no-pie-overuse`), the contrast floors, the 44 px target
rule, `color-not-only`, and the reduced-motion constraints. But the skill was never invoked
through the Skill tool, and `scripts/search.py` was never executed — no `--design-system`, no
`--domain ux`, no `--domain chart`. The original spec header credited `ui-ux-pro-max` as
reviewer, which overstated that; the header is corrected and provenance is now recorded in
spec §0.4.

**Exact commands run in this pass:**

```bash
python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py \
  "post-trade trading journal analytics dashboard dark data-dense" \
  --design-system --variance 4 --motion 2 --density 8 -p "TradeLens AI" -f markdown

python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py \
  "animation accessibility z-index loading" --domain ux -n 14

python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py \
  "dashboard trend comparison heatmap calendar equity drawdown" --domain chart -n 8
```

**New finding — D13 (High).** No z-index scale exists. `design_system.py` carries three
arbitrary literals (`z-index: 1000` line 515, `20` line 2075, `100` line 2519) and zero
`--tl-z-*` tokens. This is the `z-index-management` anti-pattern and it blocks safe layering of
the AI Partner overlay. It also exposed a **dangling reference the first spec created**: §8.2
cited "the documented z-scale", which did not exist. Resolved in spec §4.5 with an ordered
scale (`base 0 / raised 10 / nav 20 / sheet 30 / partner 40 / overlay 50`), migration of the
three literals, and a stacking-context verification requirement distinct from the
`position: fixed` check.

**Six amendments (spec §15), all additive:**

| # | Amendment | Section |
|---|---|---|
| A1 | Z-index scale, literal migration, stacking-context verification | §4.5, D13 |
| A2 | Heatmap divergent scale with neutral zero, numeric legend with ticks, pattern cue beyond colour, values reachable without hover, grid-table alternative | §5.5 |
| A3 | Heatmap sparse-month gate below ~20 populated cells → ranked day list. The spec gated the equity curve but had left the heatmap ungated | §5.5 |
| A4 | Band 2 threshold legibility — values always visible as text, thresholds labelled in text not colour position | §5.3 |
| A5 | Radar rejected for session/setup; bullet-chart form deferred for band 2 (no defined target exists); reasons recorded | §5.3, §5.5 |
| A6 | Spec header corrected for provenance | header, §0.4 |

**Independently validated, no change needed.** `--domain chart` sets the line-chart floor at
"fewer than 4 data points → stat card", matching the existing
`sample_state.show_dominant_series` gate exactly. `--design-system` resolved to *Modern Dark*,
whose best-fit list includes "fintech/trading dashboards", and its effects note "avoid pure
`#000000` (OLED smear)" — both confirm the tonal-dark direction and the `#091216` canvas. The
`--tl-space-*` ramp already matches a density-8 dashboard rhythm.

**Rejected, with reasons recorded in spec §0.4.** The generator is tuned for React Native
marketing surfaces: a blue `#1E40AF` palette on a light `#F8FAFC` background (conflicts with
locked teal-on-charcoal and the dark direction), Fira Code/Fira Sans (existing families scored
9/10 and are brand-established), glassmorphism/BlurView/ambient-glow (forbidden decorative
blur; prior audit flagged glow drift for removal), GSAP transitions and spring modals (no JS
injection, no new dependency), haptics (unavailable), and the "Real-Time / Operations Landing"
pattern with trial CTAs (a marketing pattern; the marketing site is out of scope).

**Nothing structural changed.** No amendment altered the IA, the five-band Overview reading
order, the AI Reviews note anatomy, either owner decision in §8, or any safety boundary. No
redesign, no product code.

**Files changed:** the spec and this handoff. `git add -A` not used. Untracked
`src/tradelens/ui/.impeccable/` again deliberately not staged.

**Tests and browser checks:** none — documentation only. The §0.3 sequencing caveat still
stands: no baseline browser evidence exists, and A1's stacking-context check plus §8.2's
fixed-positioning check both require a live browser before implementation.

Ownership returned to `NONE`.

### 2026-08-03 — Phase 1 specification written (Claude)

**Specification path:**
`docs/superpowers/specs/2026-08-03-phase1-dark-ux-specification.md` (954 lines).

**Files changed:** that spec (added) and this handoff (state + log). No product
code, no service, no test, no token file touched. `git add -A` was not used.

**Git state:** branch `codex/full-dark-streamlit-redesign`, base `origin/main` at
`cfdb775`, parent commit `4651eb8`. Working tree was clean at phase start.
`git diff --check` clean. One untracked directory `src/tradelens/ui/.impeccable/`
was present and deliberately **not staged** — it is not Claude's artifact.

**Decisions recorded (owner-directed):**

1. **AI Partner placement.** A true fixed bottom-right FAB plus non-modal drawer
   on desktop, and a full-page/bottom sheet on mobile. CSS-only positioning on a
   keyed container holding a real Streamlit button. No JavaScript injection and
   no new dependency. Open/close is `session_state`-gated so the drawer's widgets
   are absent from the DOM when closed and therefore not tabbable. Because there
   is no focus trap without script, the drawer is explicitly **non-modal**: no
   `aria-modal`, no blocking scrim, and a visible ≥44 px Close control placed
   first in DOM order. Live-browser verification that no Streamlit ancestor
   breaks `position: fixed` is required before acceptance, with a **reviewed**
   docked-Partner fallback (desktop right column, mobile `More` entry to a
   full-page view) if it proves unstable. The fallback is a recorded decision,
   never a silent substitution. Spec §8.2.
2. **Conversation history.** Session-only in Phase 1, matching the existing
   `ai_trade_chat.py` behaviour. **No migration and no schema change.** The
   drawer must state that the conversation is not saved. Persisted history is
   specified as a future Codex-owned, schema-backed phase (user-scoped table,
   Alembic migration with `downgrade()`, retention policy, deletion path honoured
   by account deletion) and may not be stubbed now. Spec §8.3.

**Scope amendments honoured:** the handoff overrides the older plan on the global
Partner, the expanded curated Overview, and the Codex-owned
`rule_adherence_rate`. Conflicts are tabulated in spec §0.1.

**Audit findings (12, in spec §1.2).** The load-bearing ones:

- **D1/D2 (High):** `design_system.py` carries two live colour systems — a light
  workspace set and a duplicate legacy dark set — and the older plan's Task 1
  reassigns new dark values to six names that already exist with different
  values (`TL_CANVAS`, `TL_TEXT`, `TL_TEXT_MUTED`, `TL_HAIRLINE`, `TL_RAIL`,
  `TL_CHART_STAGE`). Spec §4.1 resolves this with a new unambiguous namespace and
  deletion — not aliasing — of superseded names.
- **D3 (High):** `TL_MUTED #5B6A70` fails AA on every proposed dark surface
  (2.87–3.42:1). Contract tests must name it.
- **D4 (Medium):** rail vs canvas separates at only 1.02:1, so surface tone
  cannot make them "visually distinct" as the plan's Task 2 requires. Spec §4.4
  adds `TL_LINE_STRONG` and forbids tone as a sole separator.
- **D5 (High):** Daily Debrief regeneration pops its cache before regenerating,
  so a failed regeneration destroys the note the trader already had. Weekly
  Recap does this correctly.
- **D6 (High):** Weekly and Daily notes render as one undifferentiated
  `st.markdown` wall; only Patterns gets structured treatment.
- **D10 (Medium):** false zeros — `avg_win`/`avg_loss` return `0.0` with no
  wins/losses, and `total_edge_leak` returns `0.0` for no-leak, exact-zero, and
  absent-columns alike.

**Contrast verification:** the plan's proposed palette **passes** its own AA
contract test. `#ECF5F4` is 14.52–17.32:1 and `#91A3A7` is 6.13–7.32:1 across all
six surfaces; teal, success, danger, and warning all clear 4.5:1 everywhere. Full
matrix in spec §4.3.

**Tests and browser checks:** none run. This was a specification-only phase and
no code changed. **No baseline browser evidence exists** — see the concern below.

**Unresolved concerns:**

1. **Sequencing deviation.** The required sequence puts this specification at
   step 6, after the Opus migration lands, the cost test is fixed, the suite is
   green, and the browser preflight is captured. It was executed at the owner's
   direction before steps 1–5. Every current-state observation in the spec comes
   from reading source, not from a live render, and must be verified against a
   real app before implementation. Spec §0.3.
2. **TradeZella reference images were never received** by the specification
   session. Direction derives from the plan's written direction plus the
   layout-reference-only constraint. Reconcile spec §5 and §7 if the images are
   supplied.
3. **Overview band 2 is blocked** on the Codex-owned `rule_adherence_rate(df)`,
   which does not yet exist.
4. **Five open questions for Codex** in spec §15: the `rule_adherence_rate`
   signature and empty-sample behaviour; edge-leak zero disambiguation; the
   Partner context-adapter signature; who runs the fixed-positioning
   verification; and whether to rebuild the implementation plan now or hold it
   until the baseline is green.

Ownership returned to `NONE`. Stopped before implementation.

### 2026-08-03 — Coordination files preserved

- Codex added the approved dark-workspace implementation plan and this handoff
  contract to the canonical redesign worktree so both are preserved by Git.
- Only documentation files changed; no product implementation was performed.
- Ownership returned to `NONE` after the documentation checkpoint.

### 2026-08-01 — Preflight ruling

- Claude created the isolated worktree and found the stale-branch, test-time,
  Partner-scope, and rule-adherence questions.
- Codex approved the Partner UI only through the existing safe service, approved
  a Codex-owned public adherence metric, amended the scope, and deferred browser
  capture until the Opus migration is integrated and the baseline is green.
- No product implementation has started.

---

## Phase 0 (Next.js migration foundations) — interrupted session state, 2026-08-16 (Claude)

**Status: IN PROGRESS, PAUSED.** Stopped by an API session limit, not a code
failure. Resume in a fresh session.

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md`
**Plan:** `docs/superpowers/plans/2026-08-16-nextjs-migration-phase0-foundations.md`
**Worktree:** `.claude/worktrees/phase0-foundations`, branch
`worktree-phase0-foundations`. Full working ledger (all ten rulings, verbatim)
is at `.superpowers/sdd/2026-08-16-nextjs-migration-phase0-foundations/progress.md`
inside that worktree. That path is git-ignored, which is why the load-bearing
parts are duplicated here.

### Commit state

| Commit | What |
|---|---|
| `c69d84b` | Codex website/auth security remediation, committed as its own baseline |
| `7565f6b` | Task 1 — `require_user_id` guard. Reviewed clean |
| `0873a69` | Plan + spec execution corrections |
| `a0d2359` | **WIP, SUITE RED.** Task 2 service layer, incomplete. Must be replaced before merge |

`.claude/settings.json` was deliberately left uncommitted — local tooling
config, and the Codex security plan's own constraints say to leave it alone.

### Verified state before the interruption

Combined baseline after rebasing Phase 0 onto the security work: Python
**2385 passed / 7 skipped / 0 failed**; web **388 passed / 19 files**;
`tsc --noEmit` clean. The rebase was conflict-free — the security work
(`web/`, `site/`, `docs/`, CI) and Task 1 (`src/tradelens/services/`) touch
disjoint files.

One known flake, pre-existing and NOT Phase 0's:
`tests/test_pages_boot.py::test_analytics_category_names_are_escaped_exactly_once`
— a 3s Streamlit `AppTest` timeout that only fails under full-suite load.

### Rulings that change the approved plan

1. **The archived pages stay until Phase 10.** The plan's justification for
   deleting `ui/pages/_archive/` in Phase 0 was wrong: its unscoped
   `get_trades()` calls sit in three files no test executes, and Streamlit
   cannot route into subdirectories of `pages/`. Nine passing tests read those
   files' source.
2. **No `*_for_maintenance` / `*_all_users` helper is created.**
   `scripts/recompute_metrics.py` accepted a `user_id` and then loaded every
   user's trades — a defect to scope, not a case for an escape hatch.
3. **Deleting `weekly.list_weekly_reviews` takes two tests with it**
   (`tests/test_weekly.py:269-280`). They assert it returns every user's
   reviews, so they test the behaviour being removed.
4. **Golden-dataset encodings were wrong**: `"Break-even"` is rejected by
   `trade_validation.VALID_OUTCOMES`; `Trade.followed_rules` is an `Integer`
   storing `1`/`0`/`None`, not display strings.
5. **Ruling 10 — recorded but NOT YET EXECUTED. This is the blocker.**
   `ui/components/auth.py:477 current_user_id()` returns `None` for the
   secrets-fallback legacy user, and five pages pass that into
   `get_trades(user_id=uid)`. Once a null owner raises, those pages crash —
   ~62 tests. Decision: **merge Task 2 and Task 3 into one atomic change and
   refuse ownerless sessions at the shared `require_auth()` gate**, not
   per-page. Justification: the approved spec already requires services to
   reject a null owner, so an ownerless session cannot read trades; the only
   open choice is crash vs. graceful refusal, and the Partner page already
   pins graceful refusal. Verified first: `legacy_streamlit_auth_enabled()`
   fails closed, the mode engages only when the users table is empty, it is
   documented as emergency regression access, and site-hosted auth always sets
   a real int uid — so production is unaffected. The 62 failures are largely a
   harness artifact of `conftest.py:26` force-enabling the legacy flag for
   every test.

### To resume

Execute Ruling 10 (gate + Task 3's nine signature changes + update the `_boot`
helpers at `tests/test_pages_boot.py:43`, `tests/test_data_state.py:114`,
`tests/insights_review_options_check.py:70` to supply a concrete uid; keep the
ownerless-refusal tests asserting refusal; delete
`test_user_isolation.py::test_explicit_none_scopes_to_null_owned_legacy_rows`).
Get green, then replace `a0d2359` so no red commit survives.

Then Tasks 4, 6, 9 (owner-authorized scope for that session), and stop.
Tasks 5, 7, 8, 10-17 are deferred by owner direction. **Do not start Phase 1.**

### For Codex to review independently, when Phase 0 completes

The approved architecture forwards the raw website session token from Next.js
to FastAPI as `X-TL-Session`, where it is re-validated against the database.
Assess that against a short-lived, audience-bound internal credential minted
per request. Specifically: does forwarding a long-lived credential to a second
service widen the blast radius of a backend compromise or a log leak enough to
justify the extra moving part, and what is the migration cost of changing
later? The approved architecture stands unless implementation surfaces a
concrete reason to change it.

## Phase 0 security core — 2026-08-17 (Claude)

**Branch:** `worktree-phase0-foundations`, based on the Codex security remediation
`c69d84b`. **Not merged, not pushed, not deployed.**

**Scope executed this session:** the security-critical core of Phase 0 only — Tasks 1, 2, 3,
4, 6, 9 of `docs/superpowers/plans/2026-08-16-nextjs-migration-phase0-foundations.md`.
Tasks 5, 7, 8, 10–17 (serialization, migrations, R2 storage, image validation, AI jobs,
codegen, parity harness, deployment) are deliberately deferred to a fresh session. Phase 1
has not been started.

**Verified state:** 2446 passed, 7 skipped, 0 failed. `ruff check src/ scripts/` and
`black --check src/ scripts/` clean. Verified by running them directly, not from a report.

### What changed

**Tenant isolation, enforced in the service layer rather than at the route boundary.**
A guard in a router protects only the paths someone remembered to guard; a service that
accepts a nullable owner stays a loaded weapon for every future caller. `require_user_id`
(`services/ownership.py`) is now the single definition of a valid owner — it rejects `bool`
explicitly, because `isinstance(True, int)` is True and `True > 0`, so a bare int check
would scope a query to user 1.

Closed as true cross-tenant reads: `get_trades` (its `_UNSCOPED` default applied no owner
filter at all), `trade_hash_exists` and `find_recent_duplicate` (both skipped the filter on
`None` — the latter returned another trader's `Trade` object into the duplicate prompt), and
`weekly.list_weekly_reviews` (no owner parameter whatsoever; deleted).

Closed as fail-closed legacy fallbacks: `get_trade`, `update_trade`, `delete_trade`,
`weekly.get_weekly_review`, `get_weekly_reviews`, the three `sample_data` functions,
`csvio.import_trades_csv`, `cost.log_ai_usage`.

**A defect found in `scripts/recompute_metrics.py`:** `recompute(user_id: int)` accepted an
owner and then called `get_trades()` unscoped, recomputing one user's stored metrics from
every user's trades. Scoped. Consequently no `*_for_maintenance` helper was created —
nothing legitimate wanted one — and an import-boundary test forbids one appearing under
`src/tradelens/api/` later.

**A nullable-owner WRITE path the original enumeration missed:** `weekly.save_weekly_review`
defaulted `user_id` to `None` and would then filter and stamp `WeeklyReview` rows with
`user_id IS NULL`. Found by review, not by the plan. Now requires a concrete owner, with a
signature-guard test.

**Ownerless sessions.** `current_user_id()` returns `None` for the secrets-fallback legacy
user, and five pages then called `get_trades(user_id=None)`, which now raises. Rather than
per-page guards, an authenticated-but-ownerless session is refused at the shared
`require_auth()` gate. The mode is opt-in, fails closed, engages only when the users table is
empty, and is documented as emergency regression access; site-hosted auth always sets a real
int. **Consequence worth Codex's attention: the Strategy page's read-only sample-profile
preview for ownerless sessions is no longer reachable.**

**Correction memory.** `ai_client` injects a past-corrections few-shot block with no user
argument, learning the owner from a ContextVar. Unset now RAISES rather than resolving to the
legacy NULL tenant, and `corrections_scope` resets by token in a `finally` so a handler that
raises cannot leak its owner to the next request on the same threadpool worker.
`_corrections_block` still swallows errors, so an unscoped AI call degrades to an empty block
rather than failing — deliberate, and not to be "fixed".

**The FastAPI backend, with two independent locks.** Lock 1 is an HMAC over
`{timestamp}.{METHOD}.{path}.{sha256(body)}` — binding path and body is what stops a captured
header being replayed against another endpoint; constant-time compare, 60s replay window,
dual-secret rotation. Lock 2 resolves the forwarded website session against the database in
Python rather than trusting Next.js already did. Neither is sufficient alone and both
single-lock cases are asserted. The user id comes from the session row and nowhere else. No
CORS middleware (asserted). No schema served in production.

### For Codex to review independently

1. **The `X-TL-Session` forwarding design — the item flagged at design time.** The backend
   receives the raw, long-lived website session token and re-validates it. Assess against the
   alternative of a short-lived, audience-bound internal credential minted per request (an
   internal JWT with `aud`, `sub`, ~60s expiry, signed with the service secret). Does
   forwarding a 12-hour credential to a second service widen the blast radius of a backend
   compromise or a log leak enough to justify the extra moving part? What is the migration
   cost later? The approved architecture stands unless implementation surfaced a concrete
   reason to change it, and it did not.
2. Is the HMAC scheme sound — replay window, path/body binding, dual-secret comparison
   without early exit?
3. Does any user-facing service still admit a nullable owner? The enumeration missed
   `save_weekly_review` once already.
4. Can `corrections_scope` leak across requests under FastAPI's threadpool?
5. Is the `require_auth()` ownerless gate airtight — can any page body run with a `None`
   owner? And is removing the Strategy sample-profile preview acceptable, or does it need a
   separate non-gated entry point?
6. The `two_users` test fixture mutates global module state and restores it in teardown.
   Is the restoration complete?

### Risks and open items

- **`a0d2359` is a red commit** ("WIP … INCOMPLETE, SUITE RED"), a forced checkpoint when a
  session limit killed an implementer. Squash before merge.
- **Tasks 6, 9 and `2b23572` were written by the controller**, not a separate implementer,
  after six subagent failures. A review covering them was dispatched; its result is not yet
  recorded here.
- **Two load-dependent flaky tests**, both passing in isolation and on re-runs:
  `test_pages_boot.py::test_analytics_category_names_are_escaped_exactly_once` and
  `test_account_ui.py::test_reset_is_reachable_when_signup_is_enabled_too`. Both drive
  Streamlit in a subprocess.
- **Local Python is 3.9.6** while CI and `Dockerfile.api` target 3.11. `uvicorn` and `httpx`
  are pinned below their 3.10-only releases so both run identical code.
- **`.claude/settings.json` remains uncommitted** on `main` — local tooling config, excluded
  from the security baseline commit per Codex's own constraint.
- Merge conflicts are expected in `.github/workflows/ci.yml`, `web/package.json` and
  `.env.example` if the deferred Tasks 14/16 land against other edits to those files.

## Phase 0 complete — 2026-08-18 (Claude)

**Branch:** `worktree-phase0-foundations`, based on the Codex security remediation
`c69d84b`. **Not merged, not pushed, not deployed.** Phase 1 has not been started.

### Verified gates — real numbers, each run directly

| Gate | Result |
|---|---|
| `pytest tests/ -q` | **2528 passed, 7 skipped, 0 failed** |
| Phase 0's own new tests | **146** |
| `ruff check src/ scripts/` | clean |
| `black --check src/ scripts/` | clean, 122 files |
| `alembic heads` | single head `z6a7b8c9d0e1` — no branched chain |
| `vitest run` (web) | **809 passed, 21 files** |
| `tsc --noEmit` | clean |
| `eslint .` | clean |

Two known load-dependent flaky tests, both passing in isolation and on re-runs, both driving
Streamlit in a subprocess: `test_pages_boot.py::test_analytics_category_names_are_escaped_exactly_once`
and `test_account_ui.py::test_reset_is_reachable_when_signup_is_enabled_too`. Neither appeared
in the final runs.

### What Phase 0 built

`src/tradelens/api/` — `config`, `security` (Lock 1), `deps` (`current_user`), `app`,
`routers/session`, `serialization`, `storage` (R2), `imaging`, `jobs`, `worker`.
`src/tradelens/services/ownership.py` — `require_user_id`, the single owner definition.
`tests/parity/` — the golden harness that will prove migrated screens compute what Streamlit
computed. Two migrations: `users.app_surface`, and `ai_jobs`.

### Implementation discoveries — things the plan got wrong

Every one of these was found by executing, not by planning. They are listed because the plan
document alone would mislead someone re-reading it.

1. **`weekly.save_weekly_review` accepted `user_id=None`** and would stamp `WeeklyReview` rows
   with `user_id IS NULL` — a WRITE into the legacy shared tenant. The Class B enumeration in
   the spec missed it entirely; a review caught it. Unreachable in practice (the one live
   caller always passed an owner), but nothing prevented reintroduction. Now guarded by a
   signature test.
2. **`restore_website_session` was check-then-act.** It read the session row, evaluated the
   five conditions in Python, then wrote — while the TypeScript it claims to mirror uses one
   atomic `UPDATE ... WHERE <all five>`. Between the two statements a revoked session still
   authenticated the in-flight request, so for that window signing out meant nothing. Now one
   atomic UPDATE, admission on `rowcount`.
3. **The HMAC did not bind the query string.** No endpoint read query parameters for
   authorization, so nothing was exploitable — but the contract depended on a property of the
   handlers rather than of the signature. Now bound, canonically.
4. **The two canonicalisers disagreed.** `URLSearchParams` strips a leading `?`; `parse_qsl`
   did not. Found by a 400-case differential corpus, not by inspection — all 11 hand-written
   vectors passed. The bug lived in the space between them.
5. **`scripts/recompute_metrics.py`** accepted a `user_id` and then called `get_trades()`
   unscoped, recomputing one user's stored metrics from every user's trades.
6. **The archived pages were not blocking anything.** The plan deleted
   `ui/pages/_archive/` in Phase 0 because its unscoped `get_trades()` calls supposedly blocked
   the isolation work. They do not: no test executes those files and Streamlit cannot route
   into subdirectories of `pages/`. Deleting would have cost nine passing tests for nothing.
   They stay until Phase 10.
7. **The parity harness would have crashed on its own dataset.** Its frame read
   `t.entry_time`, which is not a `Trade` column — it is hash-only input that `create_trade`
   strips. Plus two encoding errors: `"Break-even"` is rejected by `VALID_OUTCOMES`, and
   `followed_rules` is an Integer column storing 1/0/None, not display strings. As written it
   would have raised, or pinned numbers no real row could produce.
8. **The presigned PUT could not bind a maximum size.** `ContentLength` on an S3-compatible
   presigned PUT binds an EXACT size, so the planned policy would have rejected every upload
   that was not exactly 10MB. The size gate moved server-side into
   `imaging.validate_and_normalise`.
9. **Ownerless legacy sessions.** `current_user_id()` returns `None` for the secrets-fallback
   user, and five pages then called `get_trades(user_id=None)`, which now raises. Refusal
   lives at the shared `require_auth()` gate. **Consequence: the Strategy page's read-only
   sample-profile preview for ownerless sessions is no longer reachable.**
10. **Dependency pins.** The plan pinned `uvicorn==0.41.0` and `httpx==0.29.4`; both require
    Python >=3.10 and local development is 3.9.6. Pinned to `uvicorn[standard]==0.39.0` and
    `httpx==0.28.1`, which support 3.9 and 3.11, so local tests and the container run
    identical code.
11. **Local dev database drift.** `data/tradelens.db` had `alembic_version` pointing at an old
    revision while its schema already matched head. Corrected with a metadata-only
    `alembic stamp` after verifying the schema matched. Local artifact; other worktrees may
    hit it.
12. **A red commit existed and has been squashed.** `a0d2359` ("WIP … INCOMPLETE, SUITE RED")
    was a forced checkpoint when a session limit killed an implementer mid-task. History was
    rewritten so it is no longer standalone; `git diff` against the pre-rewrite backup was
    empty, proving content was preserved byte-for-byte. Backup tag:
    `phase0-backup-pre-squash`.

### Honest limits

- **The container has never been built or booted.** Docker is unavailable in the development
  environment, so `Dockerfile.api` and `render.yaml` were verified only by reading: every
  `COPY` path exists, the YAML parses, the CMD matches the modules. Treat as unverified until
  someone runs `docker build`.
- **Job-claim exclusivity is not tested under real concurrency.** The conditional UPDATE is
  correct by inspection and tested sequentially; no multi-process race test exists.
- **Several commits were written by the controller rather than an implementer subagent**,
  after repeated subagent failures — specifically Lock 2, the FastAPI app, the query binding,
  and the differential corpus. Reviews were dispatched against all of them, and the review
  caught the atomicity defect in exactly that code.
- **`.claude/settings.json` remains uncommitted** on `main` — local tooling config, excluded
  from the security baseline per Codex's own constraint.

### For Codex to review independently

1. **Raw `X-TL-Session` forwarding vs a short-lived audience-bound internal credential.**
   The backend receives the raw website session token — a 12-hour credential — and
   re-validates it against the database. Assess against minting a per-request internal
   credential (JWT with `aud`, `sub`, ~60s expiry, signed with the service secret). Does
   forwarding the long-lived credential to a second service widen the blast radius of a
   backend compromise or a log leak enough to justify the extra moving part? What is the
   migration cost once endpoints exist? The approved architecture stands unless there is a
   concrete reason to change it, and implementation surfaced none.
2. **HMAC construction, including query binding.** Message is
   `{timestamp}.{METHOD}.{path}.{canonical_query}.{sha256(body)}`. Assess the canonical form
   (RFC 3986 encode, then sort by name then value), the 60-second bidirectional replay window
   (~120s of wall clock), constant-time comparison, and dual-secret rotation without early
   exit. Is there an input class where `security.py` and `sign.ts` still disagree that the
   400-case corpus does not reach?
3. **Tenant isolation / nullable-owner audit.** Every user-facing service now requires a
   concrete owner via `require_user_id`. The enumeration missed `save_weekly_review` once —
   is anything still missing? Note `require_user_id` rejects `bool` explicitly because
   `isinstance(True, int)` is True.
4. **Atomic session revocation.** `restore_website_session` enforces all five conditions in
   one UPDATE. Is `rowcount` a sound admission signal on Postgres specifically, and is the
   post-UPDATE owner read safe under real concurrency?
5. **Correction ContextVar isolation.** `corrections_scope` resets by token in a `finally`,
   and `current_user` yields inside it. Can a value leak to the next request on a reused
   FastAPI threadpool worker?
6. **R2 ownership and presign enforcement.** Keys are `u/{user}/t/{trade}/{uuid4}.{ext}`,
   server-generated. Ownership is checked before any GET is signed and a non-owner gets an
   indistinguishable `None`. The PUT policy binds `ContentType` but deliberately not
   `ContentLength` — confirm the server-side size gate genuinely covers it.
7. **Image validation.** Magic bytes, decompression-bomb guard, dimension caps, animated-frame
   rejection, and re-encode through pixel data to defeat polyglots and strip EXIF. Is the
   re-encode complete, and is SVG refused on every path?
8. **AI-job concurrency and idempotency.** Enqueue catches the uniqueness violation rather
   than pre-checking; claim is a conditional UPDATE. Prove or disprove exclusivity under
   genuinely concurrent workers — this is the gap we could not close.
9. **Serialization correctness.** Unknown types raise rather than being stringified; `pd.NaT`
   is checked before the `datetime` branch because it IS a `datetime`; non-finite floats
   become `None` with `finite_or_state` naming the reason. Can anything still become a
   confident wrong number?
10. **The OpenAPI boundary.** Schema is generated and committed, never served in production;
    CI regenerates and diffs so drift fails the build rather than the browser. Is the boundary
    airtight, and does the committed schema leak anything it should not?
11. **Migrations and rollback safety.** `users.app_surface` and `ai_jobs`, both with real
    `downgrade()`, verified upgrade → downgrade → upgrade on SQLite only. Assess rollback
    safety against Postgres, and whether the `ai_jobs` uniqueness constraint is correctly
    per-owner rather than global.

## Phase 0 independent Codex security/engineering review — 2026-08-18

**Review target:** handoff `7eedb52`, independently compared with the website/auth baseline
`c69d84b`. **Worktree:** `worktree-phase0-foundations`. Phase 1 was not started. No commit,
push, deployment, or unrelated `.claude/settings.json` change was made.

### Clearance verdict

**Phase 0 is cleared for Phase 1 at the code-review level after the fixes below.** This is
not a deployment clearance: the container and live PostgreSQL behavior remain unverified in
this environment. Phase 1 must preserve the owner-explicit service signatures and must not
persist or display an R2 quarantine key.

### Findings, ordered by severity

#### Critical

None confirmed.

#### High

1. **Raw browser credential crossed the Next.js → FastAPI boundary.**
   `web/lib/api/client.ts` forwarded the 12-hour HttpOnly website bearer as
   `X-TL-Session`. A FastAPI/infrastructure trace or header-log compromise would therefore
   yield a credential replayable directly against the website; HMAC integrity and current
   no-log conventions do not provide confidentiality. Fixed by forwarding only the existing
   `WEBSITE_DOMAIN`-separated database hash as `X-TL-Session-Handle`. FastAPI still performs
   its own atomic database revalidation of revocation, absolute/idle expiry, surface, and
   account activity. The raw header is now rejected, and a web regression proves the raw
   value is absent from the complete fetch init.

2. **The Phase 0 service boundary still admitted cross-owner object access.**
   `trade_service.create_trade` trusted a payload `user_id` and permitted NULL; the entire
   AI-analysis persistence service read/updated rows by ID without owner predicates;
   screenshot persistence accepted arbitrary trade IDs; primary screenshot lookup was
   unscoped; correction writes trusted cross-owner trade/analysis IDs; and metrics timestamp
   lookup defaulted to user 1. These were not reachable through Phase 0's sole `whoami`
   route, but they made the promised "thin router" boundary unsafe for the first Phase 1
   caller. Fixed at the service layer: authenticated owners are mandatory, payload owners
   are overwritten, every ID fetch carries/derives an ownership predicate, and active
   Streamlit callers were updated only as needed to keep existing behavior. New adversarial
   tests cover each cross-user path.

#### Medium

1. **The HMAC canonicalizer authorized observably different queries.** Both languages
   sorted query pairs, so a signature for `sort=created&sort=name` authorized the reversed
   duplicate order. They also treated a leading `?` as a removable delimiter even though
   the verifier receives `request.url.query`, where a leading `?` is literal first-key data;
   `/path??admin=true` collided with `/path?admin=true`. Both forms were reproduced through
   the real API and then fixed by preserving pair order and treating the leading character
   literally. The regenerated 400-case differential corpus now covers malformed escapes,
   invalid/truncated UTF-8, Unicode, empty values, `+`/`%20`, duplicate order, and the
   leading-`?` case. CI now regenerates this corpus; previously it could silently go stale.

2. **R2's claimed validation boundary was not connected to storage.** Presigned PUTs wrote
   directly into the same final `u/...` namespace that downloads trusted, while
   `validate_and_normalise` was an isolated helper. A caller could persist or display the
   original polyglot/metadata-bearing bytes, the advertised 10 MB cap was advisory, a row
   pointing at another owner's key could be signed, and no R2 deletion contract existed.
   Fixed with a non-downloadable `quarantine/u/...` namespace and server-side
   `finalize_upload`: check owned trade/key prefix, enforce `ContentLength` and a capped read,
   decode/re-encode a fresh PNG, write a new owner/trade UUID key with `private, no-store`,
   and discard quarantine on success/content rejection. Download signing accepts only that
   final key shape. Owner-key-validated deletion and streaming-body closure were added.
   Cloudflare R2 does not support presigned POST, so a `content-length-range` policy is not
   available; server finalization is the actual enforcement point.

3. **The public API buffered an unlimited body before applying its 1 MB limit.**
   `verified_body` called `request.body()` and checked the size afterward, letting an
   unauthenticated client consume large per-request memory before HMAC rejection. A chunked
   ASGI regression proved the third chunk was read after the cap had already been exceeded.
   The dependency now rejects oversized declared lengths early and enforces the cap while
   streaming, caches only the verified bytes for downstream use, and stops reading at the
   first over-limit chunk.

4. **Production could boot with an ephemeral/weak security configuration.** Missing
   `TL_SERVICE_SECRET` or `DATABASE_URL` allowed the API to construct under production and
   inherit the local SQLite default; `/health` still reported OK. The API now refuses
   production startup unless every accepted service secret is at least 32 bytes and
   `DATABASE_URL` is PostgreSQL. The worker independently refuses a production non-Postgres
   database. Error text names variables only, never values.

5. **The OpenAPI drift gate protected an untyped contract.** `whoami -> dict` generated only
   `{[key:string]: unknown}` and no response component, so a green drift check did not
   describe the Pydantic boundary. `WhoAmI(user_id: int)` now produces a concrete component
   and generated TypeScript type. Regeneration was run twice with an identical artifact
   digest; CI regenerates schema, client, signature expectations, and query corpus before
   diffing.

6. **The production image dependency was behind current security fixes.** Python 3.11
   production resolved Pillow 11.3.0, which current advisories list below the patched 12.3.0
   line. Production/CI now resolve Pillow 12.3.0; Python 3.9 local compatibility remains on
   11.3.0 because Pillow 12 requires Python 3.10. CI now installs `pip-audit` and audits the
   API runtime requirements. The reviewed PNG/JPEG/WebP path does not invoke the vulnerable
   PDF/font/JPEG2000/filter APIs, but a production native dependency should not remain on a
   known-vulnerable line merely because current call paths reduce reachability.

#### Low

1. `Image.DecompressionBombError` was not among the caught Pillow exceptions, so a crafted
   oversized IHDR escaped as a 500. It now becomes the same stable `ImageRejected` refusal.
2. AI job failures used `logger.exception`, exposing provider exception messages and
   tracebacks despite storing a generic DB error. Logs now contain job ID/kind and exception
   class only.
3. R2 `StreamingBody` objects were never closed after capped reads, risking connection-pool
   exhaustion under repeated finalization. They are closed in `finally`, with a regression.

#### Hardening / accepted limitations

1. HMAC freshness is **not** nonce-based replay prevention. An exact request is accepted
   more than once inside the ±60-second clock window; a regression documents this. The only
   current authenticated route is GET. Every future mutation must be idempotent (the AI job
   enqueue already is) or add a durable nonce store. Do not claim "replayed signatures are
   rejected" without this qualification.
2. Two true thread races against the SQLite test database now prove one row under concurrent
   `(user_id, idempotency_key)` enqueue and one winner under concurrent job claim. A live
   PostgreSQL race could not run. A crash after Anthropic succeeds but before `complete()`
   leaves a job `running`; there is no automatic duplicate spend today, but any future
   reaper/retry design needs provider idempotency or result recovery before re-running paid
   work. `_finish` should also gain a claim/attempt token before retries exist.
3. `corrections_scope` passed normal, exceptional, nested, and FastAPI sync/threadpool tests.
   A plain background thread does not inherit it and fails closed; the separate AI worker
   scopes each job explicitly. Unset context raises and never selects NULL/shared data.
4. Strict serialization passed NaN, ±Infinity, numpy scalars, pandas nulls/frames/series,
   Decimal, aware datetime/date, nested containers, and unknown-type refusal. Undefined
   financial metrics retain a named state through `finite_or_state` rather than becoming 0.
5. Migrations have one head and the full SQLite chain plus Phase 0
   upgrade → downgrade-to-`x4y5z6a7b8c9` → upgrade round-trip passed. The live disposable
   PostgreSQL migration suite was skipped because `TRADELENS_PG_TEST_URL` is absent. The
   `ai_jobs.status`/`users.app_surface` value sets are application-enforced rather than CHECK
   constrained; add DB checks in a future migration before external writers exist.
6. The R2 adapter is secure only if later routes persist **only** `finalize_upload()`'s final
   key. Phase 4 must wire finalization, screenshot-row persistence, AI reads, and account/
   trade deletion as one reviewed flow. The legacy local-disk deletion helpers do not delete
   R2 objects. Configure exact-origin bucket CORS for direct PUT/GET; never `*`.
7. Docker is unavailable, so `Dockerfile.api` was not built or started. The default
   Turbopack build also cannot bind its internal sandbox port here; the webpack production
   build passed. CI/Vercel must run the normal Turbopack build before deployment.
8. Registry-backed `npm audit` could not reach the npm advisory endpoint from this sandbox.
   CI already has `npm audit --omit=dev --audit-level=high`; the new Python audit is now
   parallel protection. Current installed Next 16.3.0 and Sharp 0.35.3 are beyond the known
   affected ranges reviewed manually, but CI remains authoritative.
9. Vercel dashboard state cannot be proven from Git. Production and Preview must use
   separate Neon branches/API/service secrets. Production DB/API secrets must never be
   available to preview code or named `NEXT_PUBLIC_*`. The deployment guide now says this
   explicitly and requires Neon's direct/unpooled connection for Alembic, with the pooled
   endpoint reserved for runtime.

### Architectural verdict: `X-TL-Session`

Forwarding the raw 12-hour browser credential **materially widened the blast radius** for a
header log, trace export, or infrastructure observer: it turned downstream visibility into
direct website account takeover. HMAC and no-log controls did not compensate because neither
encrypts headers, and conventions do not constrain infrastructure instrumentation.

A simple `{sub,aud,exp}` internal credential would reduce that exposure but would also make
FastAPI trust Next.js's asserted subject, weakening the independent database-backed Lock 2.
If it carried a session identifier/handle and FastAPI still revalidated the row, the extra
token expiry would largely duplicate the per-request HMAC timestamp. The reviewed compromise
is therefore preferable: forward the domain-separated database hash under the HMAC. It is
not replayable as the website cookie, preserves independent revocation/expiry/account checks,
requires no new signing format/key/audience parser, and was cheap to change before routes
proliferated. FastAPI compromise still exposes DB session hashes and the service secret by
definition; this change is aimed at the narrower and common logging/tracing boundary.

### Verification actually run by Codex

| Gate | Independent result |
|---|---|
| Full Python suite | **2,560 passed, 7 skipped** in 200.44s; one later documentation test for exact in-window replay passed in the focused 32-test security file |
| Services coverage gate | **89.76%**, **2,560 passed, 7 skipped**, threshold 80% |
| Web Vitest | **810 passed, 22 files** |
| Focused security/ownership/storage/session/job/image/OpenAPI tests | all passed; includes 2 real thread races on SQLite |
| ESLint | clean |
| TypeScript `tsc --noEmit` | clean |
| Ruff `src/ scripts/` | clean |
| Black | all changed Python files clean; repository-wide check still identifies three pre-existing test-only formatting deviations outside this review diff |
| Generated contracts | OpenAPI/types/signature/query corpus regenerated twice; digest stable |
| Alembic | one head `z6a7b8c9d0e1`; full SQLite upgrade and Phase 0 downgrade/upgrade passed |
| Dependency integrity | `pip check` clean; npm registry audit unavailable; CI audit gates present |
| Next.js production build | webpack build passed; default Turbopack blocked by sandbox port restriction |
| Docker / live PostgreSQL | unavailable; explicitly unverified |

### Instructions for Claude before Phase 1

- Keep every service owner keyword mandatory. Never restore NULL-owner compatibility or
  accept `user_id` from a request body/query/header as authority.
- All Next.js → API calls go through `callApi`; never reintroduce raw `X-TL-Session`.
- Treat exact HMAC replay inside 60 seconds as real. Add idempotency to mutations.
- Do not create a screenshot row from a quarantine key. Finalize, persist the returned final
  key, and ensure only final bytes reach Anthropic or a download presign.
- Add a disposable Neon/Postgres CI job for migrations and concurrent job claim/enqueue
  before relying on worker throughput or retry behavior.
- Build and smoke-test `Dockerfile.api` (`/health` plus authenticated `whoami`) before the
  first Render deployment. Use the direct Neon URL only for Alembic and the pooled URL at
  runtime.
- Do not start Phase 1 until the normal Vercel/Turbopack CI build and new Python dependency
  audit pass in a network-enabled runner.

## Phase 0 CI checkpoint — 2026-08-18 (Claude)

Codex's review work was committed unaltered as `44f4bb5` and is the Phase 0 baseline.
`.claude/settings.json` was not touched. Network-enabled CI is **green** on `2ff8266`
(run 32144524731).

### Green CI — every gate, exact result

| Gate | Result |
|---|---|
| `pip-audit -r requirements-api.txt` | **No known vulnerabilities found** |
| `ruff check src/ scripts/` | All checks passed |
| `black --check src/ scripts/ tests/` | 265 files unchanged |
| Alembic apply + reverse | single head; full chain up, Phase 0 pair down twice, back up |
| `pytest tests/` | **2562 passed, 9 skipped** in 282.92s |
| Services coverage gate | **89.73%** against an 80% floor |
| OpenAPI / type / signature / query-corpus drift | no diff after regeneration |
| Marketing site build | passed |
| Web Vitest | **810 passed, 22 files** |
| ESLint | clean |
| `tsc --noEmit` | clean |
| **Next.js production build** | **Next.js 16.3.0 (Turbopack), compiled successfully in 4.8s** |
| `npm audit --omit=dev --audit-level=high` | found 0 vulnerabilities |

Two gates the workflow had been missing were added: `black --check` (now including `tests/`,
which is how three files had drifted unnoticed — the documented lint command omits that
directory) and the Alembic round-trip.

### Four CI failures fixed, root cause each time

None of these could fail on the development machine, which is why CI was the only place they
could be found.

1. **Pillow pinned in the shared base file.** The review put `pillow==12.3.0` (Python 3.10+)
   in `requirements-base.txt`, which both surfaces include. Streamlit 1.50 requires
   `pillow<12`, so on the deploy interpreter pip could not satisfy both and dependency
   installation failed outright. On local Python 3.9 the marker selects 11.3.0 and no conflict
   exists.
2. **The split alone was not enough.** `requirements-dev.txt` includes both surfaces, so
   pinning per surface simply moved the same conflict into the dev resolution. Development
   cannot take the 12.x line at all, because the suite drives Streamlit AppTest as well as
   FastAPI's TestClient. Dev now lists the API's packages individually; the container and
   `pip-audit` still get 12.3.0.
3. **Eight advisories in the API runtime.** starlette 0.49.3 (PYSEC-2026-161, -248, -249,
   -2280, -2281) and python-dotenv 1.2.1 (PYSEC-2026-2270). Clearing starlette required
   moving FastAPI too, since 0.120.x caps starlette below 0.50 and every fixed release needs
   Python 3.10+. Pinned per interpreter, with the markers mirrored into `requirements-dev.txt`
   deliberately so **CI exercises the same FastAPI and Starlette the container ships**. A
   major framework bump was not sent to CI untested: a 3.11 environment was built locally and
   the whole suite run against FastAPI 0.141.1 / Starlette 1.6.0 — 2564 passed.
4. **Two tests depended on an ambient database.** One took no fixture and reached whatever
   database existed — fully migrated locally, absent in CI. The other imported `engine` by
   value at module load, so the `two_users` fixture's reload never reached it and it inspected
   the default database; this is the same by-value capture hazard the review flagged in
   `db/init_db.py`. Verified by reproducing the CI condition exactly — pip-installed 3.11, dev
   database moved aside — rather than by assuming.

Also fixed a real fragility rather than a symptom: 76 `AppTest.run()` call sites inherited
Streamlit's 3-second default, which is comfortable locally and marginal on a shared runner.
`AppTest.run` is now wrapped once in conftest. A timeout that only holds on fast hardware
tests the hardware, not the app.

### Pre-deployment verification — still outstanding, cannot be done here

These are **not** cleared by green CI and must be done before the first deployment:

1. **`Dockerfile.api` build and startup smoke test** — `docker build`, then `/health` and an
   authenticated `whoami`. Docker is unavailable in this environment; the image has never been
   built or booted anywhere.
2. **Disposable PostgreSQL migration verification** — upgrade and downgrade against a real
   Postgres. Only SQLite has been exercised. `TRADELENS_PG_TEST_URL` is absent, so the Postgres
   suite skips.
3. **Real PostgreSQL concurrent AI-job enqueue/claim test** — two true thread races pass
   against SQLite, but exclusivity under Postgres connection pooling is unproven.

Additionally: use Neon's direct/unpooled URL for Alembic and the pooled endpoint at runtime;
keep Production and Preview on separate Neon branches, API origins and service secrets; and
configure exact-origin R2 bucket CORS, never `*`.

### Architecture preserved

The raw website cookie never crosses into FastAPI — only the `WEBSITE_DOMAIN`-separated
handle, under the HMAC. Service-layer ownership stays mandatory. R2 uploads stay quarantined
until server-side finalization. HMAC query canonicalization preserves observable parameter
order and treats a leading `?` as literal data.

**Phase 1 has not been started and no Phase 1 plan has been written.**

## Phase 1 complete — Shell & Navigation — 2026-08-18 (Claude)

**Branch:** `worktree-phase0-foundations`, on top of the Phase 0 checkpoint and Codex's review
fixes. **Not merged, not pushed, not deployed.** Phase 2 has not been started.

**The three pre-deployment gates at the top of this file remain OPEN and untouched by Phase 1.**
Nothing here builds the container, exercises PostgreSQL, or tests job concurrency.

### Verified gates — real numbers, each run directly by the controller

| Gate | Result |
|---|---|
| `npx vitest run` (web) | **931 passed, 34 files** |
| `npx tsc --noEmit` | clean |
| `npx eslint .` | clean |
| `npm run build` (Turbopack) | **succeeds**; all seven `/app` routes server-render on demand |
| `pytest tests/ -q` | **2564 passed, 7 skipped** — unchanged, Phase 1 is web-only |
| `ruff` / `black` | clean |

### What Phase 1 built

A `/app` route tree with a server-side auth gate, one unified token system, six destinations
plus a primary action, desktop and phone navigation, the AI Partner drawer shell, loading/empty/
error primitives, and a keyboard model with tests that discriminate.

**Phase 1 makes no API calls.** A shell with no data has nothing to fetch, so the Phase 0
security boundary is not touched — the cheapest possible guarantee that it was not weakened.
The domain-separated session handle, the HMAC boundary, service-layer ownership, the R2
quarantine model and the OpenAPI contract gates are all exactly as Codex left them.

### Design decisions Phase 2 inherits

1. **The period lens is the global analysis range**, carried in the URL as `?from=&to=`. It
   governs Overview, Journal, Analytics and AI Reviews. `routeUsesPeriod()` in
   `web/lib/app/period.ts` is an **exact-match allowlist**; Trade Detail, New Trade, Weekly
   Recap, Daily Debrief, Strategy Profile and Settings are excluded by design and keep their own
   temporal controls. **Phase 2 reads this contract — it must not add a second date control to
   any page the lens governs.** The invariant is that no view shows two controls claiming the
   same temporal scope.
2. **The cutover is opt-in.** `users.app_surface` routes the post-login destination per account.
   Nothing switches automatically, and a test asserts no write to that column exists anywhere
   under `web/`. A future admin opt-in path must update that test as a visible, reviewed act.
3. **Marketing tokens are canonical.** `web/tailwind.config.ts` is shared with the live site;
   the app layer extends it and a test pins every pre-existing value. Streamlit's `#091216` is
   retired.
4. **Navigation reproduces the Streamlit IA exactly** — six destinations, unchanged. Moving the
   visual system and the IA together would make any regression unattributable.

### Implementation discoveries — defects the plan contained

Each was found by executing, not by planning. Listed because the plan alone would mislead.

1. **The `app_surface` redirect bypassed the email and onboarding gates.** It was placed before
   `handoffEligibility`, so a migrated account with an unverified email would have reached
   `/app` having cleared neither. Fixed by extracting `continuePageRedirect(user, eligible)`;
   the ordering is now pinned by a test that fails against the old arrangement.
2. **The bulk-switch guard was too weak to catch what it claimed** — it missed
   `SET migrated_at = now(), app_surface = ...`, treated `valid`/`paid`/`ANY($1)` as
   single-account scoping, and scanned only `web/lib`. Replaced with a blanket no-write
   assertion over `web/lib`, `web/app` and `web/scripts`.
3. **`parseIso` accepted calendar-invalid dates.** `new Date("2026-02-30T00:00:00Z")` does not
   return Invalid Date — it rolls to March 2nd. So `?from=2026-02-30` silently substituted a
   window the reader never asked for. Now rejected via an ISO round-trip check.
4. **The drawer's module-level open state leaked between tests.** "Stays closed until asked"
   passed only because it ran first. Now reset when the last listener unmounts, which is also
   the better design: open state belongs to a mounted drawer.
5. **Two controls shared `aria-label="Close AI Partner"`**, so an AT rotor would list two
   indistinguishable buttons. The backdrop is now "Dismiss AI Partner".
6. **The focus-trap tests did not exercise the focus trap.** A reviewer mutation-tested it —
   gutted the wrap-around branching — and all three tests still passed, because the panel holds
   one focusable element and jsdom performs no native Tab traversal. The tests now inject a
   second focusable element, and both the failure under mutation and the recovery after restore
   were observed directly rather than inferred.

### Honest limits

- **`inert` is asserted at the DOM-attribute level only.** jsdom reflects the attribute but does
  not implement behavioural inertness, so real browse-mode containment is unverified.
- **Sidebar/bottom-nav mutual exclusivity is a Tailwind breakpoint pair**, correct by inspection
  but unverifiable in jsdom, which loads no CSS.
- **The zero-focusable-elements branch of the trap is unreachable today** and therefore untested.
  It is deliberate insurance against a future change that empties the panel.
- **No screen reader has been run against any of this.** Every accessibility claim is a
  markup-level claim.
- **The shell has not been looked at in a browser** at 1440px or 375px. Its visual quality is
  unassessed; only its structure is tested.

### Phase 1 final fix wave and browser smoke pass — 2026-08-18

The final whole-branch review returned **sound to merge, no Critical**. Its two Important and
five actionable Minor findings were fixed at root, and the re-review then found one **new**
defect the fix wave itself introduced, which was also fixed.

**Fixed in the wave** (`f60dd18`, `19001bc`, `f4c1d64`, `baf3c86`):

- `/app/*` was reachable by accounts never opted in — the layout gated session, email and
  onboarding but not `app_surface`. Now gated, fail-closed on unrecognised values, with tests
  pinning both directions.
- `presetRange()` duplicated `rangeForPreset()` behind a comment that misdescribed it. The
  helper is exported and the duplicate deleted.
- The shared `:focus-visible` rule set `border-radius: 6px`, which tied on specificity with
  `.rounded-lg`/`.rounded-full` and won on source order — squaring pill controls on the
  already-shipped auth pages. Removed; the ring is unchanged.
- `MoreSheet` was a full-screen modal with none of the modal contract. It now has
  `role="dialog"`, `aria-modal`, an accessible name, initial focus, a focus trap, `inert`
  background and `aria-current` on its links — via a shared `useModalTrap` hook rather than a
  fourth hand-rolled copy.
- Neither overlay restored focus to its opening control on close. Both now do.
- The period lens popup claimed `role="menu"` without the ARIA menu keyboard model. The roles
  are dropped rather than the pattern half-built.
- Overview was the one placeholder with no placeholder. It has one now.

**The defect the fix wave introduced, and why it matters.** `useModalTrap` marked
`rootRef.parentElement.children` inert. The drawer's root is a direct child of the shell root,
so that was accidentally correct. The More sheet's root sits inside `BottomNav`'s Fragment
inside a `lg:hidden` wrapper — and a Fragment produces no DOM node — so opening the sheet
inerted the phone `<nav>` and nothing else, leaving `<main>` and the sidebar reachable to browse
mode. The new test recomputed the implementation's own scope, so it passed while proving
nothing. The hook now walks up to `document.body` marking siblings at every level except the
ancestor chain, which is depth-independent, and the test asserts the property that matters —
that `<main>` is inert while either overlay is open. Verified by restoring the old narrow walk
and watching the new assertion fail for the sheet while the drawer's still passed.

**Verified gates:** web **942 passed / 34 files**; `tsc --noEmit` clean; `eslint` 0 errors
(2 intentional exhaustive-deps warnings in `modal-trap.ts`); production build compiles with all
seven `/app` routes server-rendered on demand; Python **2564 passed / 7 skipped**, unchanged.

### Browser smoke pass — what was and was not verified

Run against a dev server started from this worktree on port 3100.

**Verified in a real browser:**

| Item | Result |
|---|---|
| `/app` opt-in enforcement, reject path | `/app`, `/app/journal`, `/app/analytics`, `/app/settings` all **307 → `/login`** unauthenticated. `/login` 200. |
| Auth-page rounded-focus regression (M-3) | Real keyboard Tab focus applies the teal double-ring (`rgb(13,17,23) 0 0 0 2px, rgb(0,229,204) 0 0 0 4px`) with `border-radius` left at the element's own value. A synthetic 9999px pill stays 9999px under focus. Programmatic `.focus()` correctly does **not** trigger the ring. |

**NOT verifiable in this environment — these remain open:**

The authenticated half of the smoke pass could not be run: **the Neon dev branch does not have
the `app_surface` column**, because the Phase 0 migrations have only ever been applied to local
SQLite. That is open pre-deployment gate #2. Reaching the shell needs a session, a session needs
a user row, and a user row needs that column.

Applying migrations to the shared dev branch would partially perform gate #2 without the
disposable-database discipline that gate calls for, so it was not done. A disposable Neon branch
would be the clean way to close this, and is the owner's call.

Consequently unverified in a browser, and asserted only at the jsdom/markup level:
sidebar and mobile navigation, the period lens, the More sheet, the AI Partner drawer, and
keyboard focus order, trapping and restoration. **No screen reader has been run against any of
it, and the shell has still never been looked at visually at 1440px or 375px.**

A throwaway session-minting script written for this pass was removed afterwards, and the dev
database was confirmed to contain **zero** leftover smoke accounts. No schema was altered.

## Disposable-branch verification — 2026-08-22 (Claude)

Owner-approved. Two of the three open pre-deployment gates are now **CLOSED**, verified against
real PostgreSQL on a disposable branch and then destroyed.

**Neon branch used:** `phase1-verify-disposable`, id `br-billowing-voice-au8txf1p`, project
`round-poetry-98534743` (`tradelens-prod`), forked from `dev-auth-migration`
(`br-sweet-flower-aurudgt4`) at its current LSN, created with a 2026-08-22T18:00Z auto-expiry
as a safety net. **Deleted at the end of verification**; the project is back to its six
pre-existing branches. Neither `production` nor `dev-auth-migration` was written to — the fork
reads the parent's LSN and does not modify it. Alembic used the direct/unpooled endpoint and the
app used the pooled one, per the deployment guide.

### Gate 2 — PostgreSQL migrations: CLOSED

The branch started at `w3x4y5z6a7b8`, three migrations behind head.

| Step | Result |
|---|---|
| `alembic upgrade head` | applied `x4y5z6a7b8c9`, `y5z6a7b8c9d0`, `z6a7b8c9d0e1` cleanly |
| `users.app_surface` | `character varying`, `NOT NULL`, default `'streamlit'` |
| `ai_jobs` | all 12 columns present; `uq_ai_jobs_user_key` unique constraint present |
| Downgrade round-trip | `downgrade -1` twice to `x4y5z6a7b8c9`, then `upgrade head` — both directions clean |

**The opt-in invariant was verified against real rows, not just tests:** the two pre-existing
user rows on the forked branch came through the migration as `app_surface = 'streamlit'`. The
migration moved nobody.

### Gate 3 — PostgreSQL job concurrency: CLOSED

12 threads released simultaneously by a `threading.Barrier`, so the database decided the winner.

| Assertion | Result |
|---|---|
| Concurrent enqueue, one owner + one key | exactly **one** row; every caller got the same job id; exactly **one** caller saw `created=True` |
| Concurrent claim | exactly **one** worker won; winner marked `running` |
| Cross-user, same key | two distinct jobs, one row each — no dedupe across owners |
| Concurrent enqueue, two owners, same key | one row per owner |

No thread raised. Test users and their jobs were deleted afterwards.

### Phase 1 browser smoke pass — complete

Two accounts on the disposable branch: one `app_surface='nextjs'`, one left `'streamlit'`.

| Item | Result |
|---|---|
| `nextjs` account reaches `/app` | **200** on `/app`, `/app/journal`, `/app/analytics`, `/app/settings` |
| `streamlit` account refused | **307 → `/continue`** on `/app` and `/app/journal`; reaches `/continue` (its existing journal path) with 200 |
| Sidebar navigation | click → route change, `aria-current="page"` follows |
| Mobile navigation | phone bar click → route change, `aria-current` follows |
| Period lens | opens; selecting "Last 7 days" rewrites the URL to `?from=2026-08-16&to=2026-08-22` and the mono readout matches; popup is `role="group"`, not a menu |
| Lens route scoping | present on `/app`, `/app/journal`, `/app/analytics`, `/app/reviews`; **absent** on `/app/strategy`, `/app/settings`, `/app/trades/new` — verified against real SSR HTML |
| More sheet | `role="dialog"`, `aria-modal`, name "More"; focus moves to "Close menu"; `<main>` inside an inert subtree; holds Analytics, Strategy Profile and the primary action |
| AI Partner drawer | `role="dialog"`, `aria-modal`, name "AI Partner"; focus moves to "Close AI Partner"; four Tab presses stayed inside the panel |
| Escape and focus restoration | both overlays close on Escape, **all** `inert` released (0 elements remaining), focus restored to the exact control that opened them |
| Skip link | first tab stop, targets `#main-content` |
| Focus styling | teal double-ring on real keyboard focus with `border-radius` untouched; a synthetic 9999px pill stays 9999px |
| Empty states | render on every placeholder route |

**The `inert` fix was confirmed live.** Opening either overlay marks the `lg:grid` wrapper
(sidebar + `<main>`) and the `lg:hidden` wrapper (phone bar) inert, while the dialog itself is
not. Before the fix, opening the More sheet left `<main>` reachable.

### Observations and limitations

- **The period lens wraps to two lines at 375px.** Readable, not clipped, but the top bar is
  cramped on a phone. A polish item for a later phase, not a defect.
- **Loading and error primitives were not exercised** — they still have no production callers
  and there is no `error.tsx`/`loading.tsx` under `/app`. Only the empty state is wired up.
- **No screen reader was run.** Every accessibility claim remains a markup-level claim;
  `inert` was confirmed as attribute-and-ancestor state, not as observed browse-mode behaviour.
- The Next.js dev-tools badge overlaps the bottom-left nav item in dev. Dev-only, not shipped.

### Gate 1 — Docker build and health smoke: STILL OPEN

Docker remains unavailable in this environment. `Dockerfile.api` has never been built or
started. Per the owner, this does not block the Phase 1 merge, but it must run before the first
Render deployment.

### Final Phase 1 gates

web **942 passed / 34 files**; `tsc --noEmit` clean; `eslint` 0 errors (2 intentional
exhaustive-deps warnings); production build exit 0 with all **7** `/app` routes dynamic;
`ruff` and `black` clean; Python **2563 passed, 7 skipped, 1 failed**.

That one failure is `test_pages_boot.py::test_page_boots_seed_db[6_Insights.py]` — a third
member of the known load-dependent Streamlit `AppTest` family. It passes alone in 1.54s and its
whole file passes 70/70, and **Phase 1 changed no Python file at all**
(`git diff --name-only 74c73ea..HEAD -- src/tradelens tests alembic` is empty), so it cannot be
related to this branch.

**Phase 1 is ready to merge.**

---

# Phase 2 — Overview (2026-08-22)

Branch `worktree-phase2-overview`, from `main` @ `d63007b`. Plan:
`docs/superpowers/plans/2026-08-22-nextjs-migration-phase2-overview.md`.

`/app` is now the real Overview, served through the Phase 0 FastAPI boundary and rendered in
the Phase 1 shell. Nothing in the Phase 0 security architecture was reopened.

## What shipped

| Task | Commit | Deliverable |
|---|---|---|
| A1 | `e991c92` | Low-data policy moved to `services/sample_policy.py`, shared with Streamlit |
| A2 | `9f48539` | `services/overview.py` — composes the payload; `metrics.setup_performance()` added |
| A3 | `12fcc9e` | `GET /v1/overview`, Pydantic schemas, contract regenerated |
| B1 | `9411cf5` | `web/lib/app/overview.ts` — server-side fetch |
| C1/C2 | `e6ea11c`, `789f2dd` | Stat tile, KPI row, risk & discipline |
| D1/D3 | `1524b99`, `e50d45d` | Equity curve, trading-days calendar |
| D2 | `98dd6e4` | Trajectory, recurring edge |
| E1 | `4f37107` | Next review action, recent trades |
| E2 | `fa40d50` | `OverviewSections` composition |
| fix | `2e4a117` | Behavioural owner-leak test; calendar a11y name |
| B2 | `0b34ca9` | `/app` page wiring, route loading/error boundaries |

## Architecture decisions

**One endpoint, not per-section.** `GET /v1/overview?from=&to=` returns the whole payload.
The page is a Server Component rendering once; per-section endpoints would be N round trips
for one screen. When a later phase needs finer granularity it can add endpoints then.

**The low-data policy is now shared infrastructure.** It lived under `ui/`, which Phase 10
deletes, while its own docstring insisted one answer must hold across surfaces. Streamlit
re-exports from `services/sample_policy` so both surfaces run on the same objects.

**`metrics.setup_performance()` is new, not modified.** `by_setup_type` carries no P&L column,
so the setup breakdown could not be built from it. A new public function on the same private
engine cannot alter any output the parity harness pins.

**Charts are inline SVG.** No new npm dependency. A line and a month grid do not justify a
charting library, and choosing one now would decide a later phase's question prematurely.

## Defects caught before they shipped

**Six wrong metric field names, found in the pre-flight scan before any code was written.**
`compute_basic_metrics` returns `total_pnl` not `net_pnl`; `compute_streaks` returns
`current_streak`/`max_win_streak`/`max_loss_streak`; `EdgeLeakSummary` is
`net_pnl`/`qualifying_trades`/`recorded_trades`; `killzone_performance` returns `total_pnl`;
`calendar_daily_pnl` returns `trade_date`/`net_pnl`; `by_setup_type` has no P&L column at all.
The plan had written every read as `.get(col, 0.0)`, so five of the six would have rendered as
a confident $0.00 rather than failing. Required reads are now explicit and loud (`_need`).

**Undefined was crossing the boundary as zero.** `metrics` flattens `max_drawdown`,
`consistency_score`, `avg_win`/`avg_loss` and `win_rate` to `0.0` upstream, and
`finite_or_state` can only recover a state from NaN/±inf — so a trader with four trades would
have been shown **0 out of 100 consistency**, when the real meaning is "too little signal to
score". These now cross as `{"value": null, "state": "undefined_no_sample"}`.

**Activation and today/week P&L were period-scoped.** A trader with 40 lifetime trades who
selected a quiet month would have been told to "log your first completed trade". Both now read
lifetime trades via one additional owner-scoped query.

**The typed contract was not gating drift.** Pydantic's default `extra="ignore"` silently drops
added fields, and `None` defaults meant a removed field validated as `{"value": null,
"state": null}` — a figure vanishing with no state to explain it. Now `extra="forbid"` with
defaults dropped. The re-reviewer proved the new tests are non-vacuous by reverting the config
and confirming they fail.

**A security test that tested nothing.** B1's "never sends a user id" test stringified the
function source and regex-matched it. It would have missed an id threaded through a helper, any
other spelling (`ownerId`, `accountId`, `uid` — even `userID`, since the pattern required a
lowercase `d`), and a value sent without its name. Replaced with an assertion on the outgoing
call args, and **proved stronger**: threading `owner=1` into the query fails the new test, and
the old regex test passes that same regression.

**`as const` on a ternary (TS1355).** Invisible during the parallel component batch, because
each agent was necessarily forbidden from running `tsc` while the graph was incomplete. The
first full typecheck at E2 caught it immediately.

## Accessibility — a computed finding, not a judgement call

The outcome colour pair was validated rather than eyeballed. Against the dark chart surface:

```
CVD separation   #f56565 <-> #22c55e   dE 2.3 (deutan)   FAIL
Normal vision    #f56565 <-> #22c55e   dE 33.2           PASS
```

To a deuteranope the winning colour and the losing colour are the same colour; to everyone
else they are obviously different, which is exactly how this ships undetected. So no chart in
this phase distinguishes anything by hue alone: the calendar encodes a winning day as a filled
circle and a losing day as a square (with `role="img"` so the label is announced), stat tiles
carry the sign in text, and the recent-trades table has outcome as a word in its own column.

## Verification

- Python: **2609 passed, 7 skipped**. ruff and black clean.
- Web: **982 passed / 43 files**. `tsc --noEmit` clean. eslint 0 errors (2 pre-existing
  `modal-trap.ts` warnings).
- Production build compiled; **all seven `/app` routes are `f` (dynamic)** — a statically
  prerendered `/app` would bake one trader's data into a shared page.
- **Contract drift gate CLEAN**: regenerating `openapi.json` and `schema.d.ts` produces no diff.

## Final review, fix wave, and browser smoke pass

The final whole-branch review returned **BLOCKED** with two Critical findings. A browser smoke
pass on a disposable Neon branch (`br-royal-haze-auoijqff`, forked from dev-auth-migration, NOT
production; migrated to head; seeded one isolated account) confirmed two of them on screen and
found nothing further. All were fixed in `fd8a08d` and re-verified live.

**C1 — the activation card contradicted itself.** `STEP_COPY` was keyed on
`strategy_profile`/`first_trade`/`first_review`; `activation.py` emits
`strategy`/`first_trade`/`weekly_review`. Only the middle key matched, so two of three states
fell through to the "you are done" branch. Rendered live as **"1 OF 3 DONE"** directly above
**"Nothing waiting — the activation path is complete."** The unit test passed because its
fixture was written from the plan and shared the component's own mistaken assumption.
Fixed structurally, not cosmetically: `next_key` is now a Python `Literal` that reaches the
generated TypeScript as a union, and `STEP_COPY` is typed off it — a fourth spelling is now a
tsc error rather than a silent fallthrough.

**C2 — the Overview's consistency score diverged from Streamlit's.** `_TRADE_COLUMNS` omitted
`user_grade`/`ai_grade`, so `consistency_score`'s 25%-weighted grade-trend term silently
returned a neutral 0.5 — up to ±12.5 points of divergence between the two surfaces, which is
exactly what `overview.py`'s docstring says the module exists to prevent. Invisible to `_need()`
because pandas reports a missing column as absent rather than raising.

**I1** today/week P&L were computed but rendered nowhere (spec §8 requires them) — now rendered
above the KPI row and labelled as not period-scoped. **I2** the calendar captioned out-of-window
days as "had no trade" — confirmed on screen, now distinguished by a dashed dimmed cue with an
honest caption. **I3** max drawdown rendered unsigned and neutral-toned beside a green profit —
confirmed on screen, now signed and toned. **I4** `streak_type` was never rendered. Plus seven
duplicate `money` helpers with three different behaviours, reduced to one shared helper.

**The smoke pass is a gate for this phase, not a formality.** It found in seconds what 982 web
tests, a full typecheck, a production build and three task reviews all missed.

Also verified live: an unsigned `GET /v1/overview` against the running server returns **401**,
confirming Lock 1 outside the test suite; and the calendar's shape encoding (green circles for
winning days, red squares for losing days) renders as designed.

## Carried forward

- Docker build/startup/health remains an open pre-deployment gate (see the banner at the top).
- A row with **blank pnl** and a manual `result` label is counted in `wins`/`losses` by
  `compute_basic_metrics` (result-text fallback) but contributes nothing to
  `compute_profit_factor_raw`'s pnl sum, so the all-breakeven gate could miss that edge case and
  render `0.00x`. Pre-existing, unrelated to this branch, and unreachable through `create_trade`.
- `today_pnl`/`week_pnl` use the server's local date, not the trader's timezone. Now that they
  render, this is real rather than moot.
- The `_MIN_TRADES_FOR_CONSISTENCY = 5` constant is mirrored in `services/overview.py` from a
  private constant in `services/metrics.py`. Documented, but it can drift.
- The strict-JSON test in `tests/test_overview_service.py` is prophylactic: no live path emits
  a non-finite raw float today.

## Independent Codex review — 2026-08-22

Codex independently reviewed Phase 2 at `f993fc6` against `d63007b`, including the complete
history/diff, Phase 0 boundary, owner-scoped service graph, metric functions, Pydantic/OpenAPI
contract, generated TypeScript, RSC page, component fixtures, production build, response
headers, and dependency sets. The review did not begin Phase 3.

### Findings and fixes

No Critical or High vulnerability was found. In particular, no cross-tenant read, browser
owner override, raw-cookie forwarding, shared-cache response, or client-bundled service secret
was reproduced.

**Medium — the layout was not an authorization prerequisite for the Overview fetch.**
`web/app/app/page.tsx` assumed `web/app/app/layout.tsx` had authenticated and authorized the
request first. A production start with no cookie returned the expected 307 but logged a signed
FastAPI fetch from the child page, proving Next rendered the page concurrently with the layout.
An active but email/onboarding/app-surface-ineligible website session could therefore cause
FastAPI to retrieve its Overview before the layout redirected. The API still revalidated the
session and remained owner-scoped, so this did not become a cross-tenant bypass, but the
protected-route transition was not a valid data-access boundary. The page now validates the
session and `appLayoutRedirect()` itself before `fetchOverview()`. A three-case Vitest proves
invalid and Streamlit-surface sessions never call FastAPI and a valid Next.js session does.
Future Phase 3+ pages must repeat this pattern: a parent layout is presentation/redirect
defence, not a precondition for child data access.

**Medium — valid manual outcomes with blank P&L became confident zero-valued money data.**
`create_trade` deliberately allows `result=Win|Loss` while `pnl` is blank, but Overview and
the underlying parity-pinned metrics treated missing P&L as zero in several places. The screen
could therefore show `$0` net P&L, `$0` expectancy/average, `0.00x` profit factor, zero
drawdown, a flat calendar day, and a zero-movement equity curve for a trade whose monetary
result was unknown. The API now carries `pnl_recorded`/`pnl_complete`, emits explicit
`undefined_incomplete_sample` states for affected monetary figures, suppresses equity and
grouped monetary output until complete, and marks an affected calendar day `unknown` with
`pnl: null`. The UI names incomplete P&L in text. A separate breakeven test proves a recorded
`0.0` remains a legitimate zero. This is a deliberate Overview boundary gate over unchanged,
parity-pinned metric arithmetic.

**Medium — the response contract accepted drift and contradictory payloads.**
Several nullable fields had defaults, so removing them from the service still validated and
generated optional TypeScript properties. Enum-like values such as calendar outcome and streak
type were arbitrary strings; response scalars were coercive; `{value:null,state:null}` was
valid; calendar outcome could contradict P&L. The schema is now `strict=True` plus
`extra="forbid"`, nullable wire fields remain required, undefined states and enum-like values
are Literals, value/state pairs are exclusive, always-emitted streak fields are non-nullable,
and calendar P&L/outcome invariants validate together. OpenAPI and `schema.d.ts` were regenerated;
`next_key` remains the narrow `strategy | first_trade | weekly_review | null` union.

**Medium — Today/This Week used the server calendar instead of the owner calendar.**
`services/overview.py` defaulted to `date.today()`, so users outside the Render server timezone
could see the wrong day or ISO week near midnight. It now reads the owner-scoped persisted
timezone, converts a UTC instant through `zoneinfo`, and safely falls back to the product
default/UTC for invalid or missing tzdata. Two users on opposite sides of the date boundary
and the build-to-KPI wiring are covered.

**Low — fixture and production killzone labels disagreed.** The service emitted the internal
`ny_am` key while frontend fixtures invented `NY AM`; the established product label is
`New York AM`. Overview now maps through `services.sessions.KILLZONE_LABELS`, and both the
service test and typed frontend fixtures use the real contract.

**Low — the consistency sample threshold had two sources of truth.** Overview copied the
private metrics literal `5`. `metrics.MIN_TRADES_FOR_CONSISTENCY` is now public and used by
both the scorer and Overview gate; the old private name remains a compatibility alias for the
Streamlit band. A monkeypatched-threshold regression fails if Overview ever copies it again.

**Low — profitable rule-breaking lacked the existing trust warning.** A positive edge-leak
amount rendered as an ordinary positive dollar figure, unlike Streamlit's warning that this is
luck rather than repeatable edge. The tile now states that profitable rule-breaking is not
repeatable edge and uses warning tone; direction still remains explicit in the number/text.

**Low — a flat equity series rendered at the chart floor.** The code comment claimed it was
centred but `span = 1` placed every flat point at the bottom. Flat series are now centred and
the exact geometry is pinned.

**Hardening — server-boundary environment documentation/tests were incomplete.**
`web/.env.example` omitted `TL_API_ORIGIN` and `TL_SERVICE_SECRET`, even though local Next.js
loads env from `web/`; the server-only denylist also omitted those names and guarded only env/db
modules. The example now documents both server-only values, the denylist includes current and
previous service-secret names plus the API origin, and tests enforce `server-only` on the API
signer/client and Overview fetch module. A production build with canary values confirmed none
of the database host, API origin, or service secret appeared in `.next/static`.

### Independent verdicts

- **Tenant isolation: CLEAR.** `/v1/overview` gets its owner only from `current_user`; period
  and lifetime trades, strategy, and weekly review reads all receive that owner. A signed
  two-user request containing `user_id`, `uid`, `owner`, `accountId`, and `account_id` still
  returned only the session owner's empty journal while the other owner's seeded positive
  control contained five trades. The web outbound test inspects the actual `callApi` arguments
  and permits only `from`/`to` query keys.
- **Next.js → FastAPI boundary: CLEAR.** The page passes the raw cookie only to the server-only
  API client; that client forwards only the domain-separated SHA-256 session handle and signs
  the actual method/path/ordered query/body. No browser owner id is accepted. The page-local
  gate now runs before the call.
- **Caching/user isolation: CLEAR with one live-test limitation.** Page and layout are forced
  dynamic, use request headers, and the server fetch is `cache: "no-store"`; FastAPI responses
  are `no-store, private`. A production `next start` request to `/app` returned
  `Cache-Control: private, no-cache, no-store, max-age=0, must-revalidate` and redirected before
  any API call. No independently minted authenticated Neon session was used in this review, so
  an authenticated production-response header was not re-smoked; the API header is covered by
  TestClient and Claude's earlier disposable-Neon smoke remains the live authenticated run.
- **Metric parity: CLEAR for complete data.** A controlled five-trade dataset compares Overview
  directly to the metric services for net P&L, win rate, expectancy, profit factor, drawdown,
  adherence, edge leak, consistency, streaks, averages, and daily equity. The only deliberate
  differences are semantic boundary gates where legacy metrics flatten insufficient or missing
  evidence.
- **Undefined/low-sample semantics: CLEAR.** Zero, one, two/three, four, and five-trade policy
  boundaries are covered across the shared sample policy and Overview tests. Missing sample,
  incomplete P&L, NaN, and infinities retain distinct states; a recorded zero remains numeric
  zero. Calendar `unknown`, `flat`, positive, and negative meanings are text/shape distinguishable.
- **Period/lifetime: CLEAR.** Direct API tests cover malformed, compact, reversed, and >5-year
  ranges and HMAC-bound tampering. Selected metrics use period trades; activation and
  Today/This Week use lifetime owner data; Today/This Week use owner-local current-calendar
  semantics.

### Verification actually run after fixes

- Python: **2636 passed, 7 skipped** in 205.82s.
- Web/Vitest: **1006 passed / 44 files**.
- TypeScript: `tsc --noEmit` clean.
- ESLint: **0 errors**, two pre-existing `modal-trap.ts` hook warnings.
- Black: **252 files unchanged**.
- Ruff: CI scope `src/ scripts/` clean; all review-touched Python files clean. A supplemental
  `ruff check .` notices the pre-existing unused `json` import in `tests/test_weekly.py`; CI does
  not lint tests and this review did not modify the weekly/Streamlit-owned file.
- OpenAPI → TypeScript regeneration: byte-for-byte stable after regeneration.
- Alembic: **one head**.
- Production Next.js build: success; all seven `/app` routes dynamic.
- Production `next start` smoke: `/app` without a session returned 307 `/login`, private
  no-cache/no-store headers, and—after the fix—made no FastAPI request.
- Dependency audit: `npm audit` including dev dependencies found **0** vulnerabilities.
  `pip-audit --disable-pip --no-deps -r requirements-api.txt` found **0** known vulnerabilities
  in the direct pinned API requirements. Full transitive Python resolution could not be audited
  locally because the auditor's Python 3.13 environment tried to build the Python-3.9-compatible
  `psycopg2-binary==2.9.9` without `pg_config`; CI's Python 3.11 full audit remains authoritative.
- Canary bundle scan: service secret, Neon host, and API origin absent from `.next/static`.

### Remaining limitations and Phase 3 instructions

- Docker is still unavailable here; the carried Phase 0 container build/start/health gate
  remains open before first Render deployment.
- No new disposable Neon branch or authenticated browser account was created for this pass.
  The database-independent owner adversary, production unauthenticated smoke, and Claude's
  prior disposable-Neon authenticated smoke provide the evidence above.
- The combined local Python 3.9 development environment contains known advisories in
  Streamlit/dev-only packages; the API production requirement set selects patched Python 3.11
  versions. Do not conflate the local combined environment with the Render image, and do not
  change the Streamlit pins inside a Phase 2 review.
- Every Phase 3+ data page must authorize in the page/data-access function before fetching;
  never rely on the parent layout having executed first.
- Build frontend fixtures from the generated contract and assert critical display labels
  against real Python service output. The activation and killzone mismatches demonstrate that
  a fixture copied from a plan can agree with the same UI bug.
- Reuse `Undefinable`, `UndefinedState`, `sample.pnl_complete`, and
  `metrics.MIN_TRADES_FOR_CONSISTENCY`; do not reintroduce numeric defaults or copied thresholds.
- Keep new API callers and signers `server-only`, and extend the env-safety list for every new
  server credential.

**Phase 2 is cleared for merge after these review changes are included. Stop here; do not begin
Phase 3.**

---

# Phase 3 — Trades + Trade Detail (2026-08-23)

Branch `worktree-phase3-trades`, from `main` @ `a7a05a7`. Plan:
`docs/superpowers/plans/2026-08-22-nextjs-migration-phase3-trades.md`.

`/app/journal` is a real filterable, paginated trade log and `/app/trades/[id]` a real trade
record that can be read, edited and deleted. **This phase opened the project's first write path
across the API boundary** — every prior endpoint was a read.

## What shipped

| Endpoint / surface | Notes |
|---|---|
| `GET /v1/trades` | filtered, offset-paginated, total from one shared filter construction |
| `GET /v1/trades/{id}` | detail plus presigned screenshot descriptors |
| `PATCH /v1/trades/{id}` | positive allowlist, atomic optimistic concurrency |
| `DELETE /v1/trades/{id}` | owner-scoped, idempotent, failure-aware R2 cleanup |
| `/app/journal` | filter bar, table, calendar with open-from-day, pagination |
| `/app/trades/[id]` | read view, inline edit, delete dialog, screenshot gallery |
| `/api/trades/[id]` | Next relay so Client Components can mutate without the service secret |

## Architecture decisions

**Optimistic concurrency is one conditional UPDATE.** The predicate carries trade id, the
authenticated owner and `expected_updated_at`; the decision is the rowcount. A read-compare-write
sequence would reintroduce the exact lost-update window the field exists to close — the same
TOCTOU Phase 0 removed from `restore_website_session_handle`. A rowcount of 0 triggers one
owner-scoped re-read purely to separate 404 from 409.

**The PATCH body is a positive allowlist.** `trade_service.update_trade` accepts every column but
`id`/`user_id` — right for a trusted in-process caller, wrong at an HTTP edge.
`EDITABLE_TRADE_FIELDS | SERVER_OWNED_TRADE_COLUMNS == columns` is asserted against the live
model, so a **new column is unwritable until someone deliberately files it**.

**Deletion removes R2 objects before the row, and never overclaims.** The FK cascade drops the
screenshot row and leaves the object. `delete_trade_objects` is owner-scoped (`Screenshot` has no
`user_id`, so the trade join is its only ownership signal), idempotent, and failure-aware:
`complete` requires both `failed` and `skipped` empty, and a failure returns 503 with the row
intact and nothing deleted. The UI says exactly that.

**404 never 403, byte-identical.** On every per-id route. A 403 confirms the row exists.

**The relay fails shut.** `web/app/api/trades/[id]/route.ts` refuses when `SITE_ORIGIN` is unset,
deliberately diverging from the nine pre-existing `app/api/auth/*` routes, which skip their CSRF
check in that case. It is the first of these to guard trade data rather than an auth flow.

## The defining lesson: six tests proven dead by mutation

Six separate tests in this phase passed against deliberately broken code. Every one asserted a
value the implementation **echoed back** rather than an observable outcome:

1. The limit clamp asserted `page.limit`, not the rows returned — the query could ignore the
   clamp entirely and stay green.
2. The stable-order test asserted set-equality, which the partial-ordering bug survives because
   SQLite happens to return rowid order.
3. The cross-owner screenshot test built the other owner's trade with no screenshots, so its
   `calls == []` assertion proved nothing.
4. `callApi`'s error path: `ApiError(response.status)` → `ApiError(200)` passed **all 1184 web
   tests**, in the one file every API call shares.
5. The delete closure: hardcoding `{status: 204}` passed **all 1184** — the backend 503, the
   relay's `unresolvable` split and the dialog's "Nothing was deleted" copy were each tested, and
   the wire between them was not.
6. `presign_download`'s ownership join could be removed with 119/119 green, because the test's
   malformed key was rejected by a downstream gate rather than by ownership.

A Group B implementer found a seventh in its **own** work before review: removing the ownership
join from `_owned_object_keys` stayed green because `_is_final_key` masked it.

The pattern is one thing: **assert what crosses the boundary, never what the handler hands back.**

## Defects caught before merge

Beyond the dead tests: every sample-data trade was **permanently un-editable** (built without
`updated_at`, and `NULL = 'anything'` is never true, so the atomic predicate could never match —
no value a client could send worked); the `asset` filter was a substring match, so filtering to
NQ also returned MNQ in both rows and total, and `asset=%` matched everything; an unrecognised
killzone read fine but 422'd on write-back, so an edit form posting the whole record could not
save a legacy trade; and spec §8's grade and screenshot columns were missing while a stale test
actively asserted their absence.

## Verification

- Python **2742+ passed / 7 skipped**; ruff and black clean.
- Web **1198 passed / 61 files**; `tsc --noEmit` clean; eslint 0 errors.
- Production build compiled; `/app/journal`, `/app/trades/[id]`, `/api/trades/[id]` all dynamic.
- Contract drift gate clean. Single Alembic head `a7b8c9d0e1f2`, migration round-trips.
- **Live browser smoke pass** on a disposable Neon branch against real Postgres: cross-owner
  isolation (none of the other owner's data anywhere in the payload), the exact-match asset fix,
  pagination boundaries, the em-dash for unrecorded P&L, and every relay guard — stale stamp 409,
  cross-owner 404, forbidden field 422, missing Origin 403, no session 401. A successful PATCH
  followed by a replay of the same stamp returned 409: the lost-update guard working against a
  real database. Database state confirmed afterwards.

## Carried forward

- **Docker build/startup/health remains an open pre-deployment gate** (banner at the top).
- Deferred by owner direction: the filtered-set **AI summary → Phase 3E**, and per-trade
  screenshot **upload → Phase 4**. Both are spec §8 items and neither is silently dropped.
- The nine `app/api/auth/*` routes still skip CSRF entirely when `SITE_ORIGIN` is unset. The
  relay now diverges deliberately. Whoever takes this up should **tighten the nine, never loosen
  the relay**.
- `_is_final_key` hardcodes `.png`, so `delete_trade_objects` skips a non-PNG final object. It
  fails safe today (a blocked delete, never a false success) but is the trigger condition for the
  `presign_download` masking risk.
- Quarantine objects from an upload that was never finalized have no DB row, so a trade delete
  never reaches them. Needs a reconciler.
- `list_trades` does not filter `is_sample`, so demo trades appear alongside real ones — coherent
  with Overview, which does the same, but there is no demo-data indicator anywhere in `web/`.
- Postgres isolation: under snapshot isolation a genuine concurrent writer would raise a
  serialization error, giving a 500 rather than a 409. The safety property survives (nothing is
  written); only the message is less specific. All concurrency probes ran on SQLite.
- Screenshot rendering and the 503 cleanup-failure path have never been exercised in a browser —
  no R2 credentials in the smoke environment.
- The journal calendar shows the **unfiltered** period aggregate beside a **filtered** table.
  No number is wrong, but nothing labels the scope difference. Needs a labelling decision.
