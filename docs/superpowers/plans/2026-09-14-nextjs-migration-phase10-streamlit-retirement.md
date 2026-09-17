# Phase 10 — Streamlit Retirement / Final Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the Streamlit surface completely — every account on the Next.js app, the `app_surface` toggle and the Streamlit handoff path removed, `src/tradelens/ui/` and its tests deleted, the Streamlit dependencies dropped, and the Streamlit Cloud deployment decommissioned — but only after the spec's eight retirement criteria are proven, and in an order where every step before the point of no return can be undone with a database update.

**Architecture:** Three stages separated by two owner sign-off gates. **Readiness (Group R)** is reversible, additive work that produces the evidence §11 asks for: a checked §8 parity ledger, a browser E2E smoke, a funnel check against the new origin, and an idempotent screenshot migration to R2. **Flip (Group F)** is one Alembic migration that moves every account and the column default to `nextjs` while leaving all routing code in place, so a rollback is a single `UPDATE`. **Removal (Group X)** runs only after the flip has held: the web stops reading `app_surface` and stops issuing handoffs, the Streamlit session/handoff machinery and the column are dropped, and `ui/`, its tests, its dependencies, its CI origin and its docs go.

**Tech Stack:** Python 3.9 floor · SQLAlchemy 2.x · Alembic · FastAPI · R2 via `api/storage.py` · Next.js 16 App Router · TypeScript · pytest · Vitest · Playwright (pending decision T3)

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md` — §3 ("`src/tradelens/ui/` … **Deleted at Phase 10**", "1,280 Streamlit-coupled test functions (54 files) | **Retired at Phase 10**", "Streamlit, Plotly, PyArrow | **Removed from `requirements.txt` at Phase 10**", "Streamlit handoff path, `STREAMLIT_DOMAIN`, `open/restore/revoke_streamlit_session` | **Removed at Phase 10**"); §7 phase 10 ("Flip default · remove toggle · delete `ui/` · retire UI tests · drop dependencies · decommission Streamlit Cloud"); §7 Cutover ("Default flips when §9 is satisfied; the flag is then removed"); §8 ("Nothing below may be dropped without an explicit, recorded decision"); §10.2 golden parity harness; §10.6 Playwright at desktop and 375px; **§11 criteria for retiring Streamlit ("All eight must hold. No partial retirement.")**; §12b ("The archived pages stay until Phase 10 … They go when `src/tradelens/ui/` goes").

## Global Constraints

- **No partial retirement** (§11). Group X does not start until all eight §11 criteria are recorded as met in the handoff, with evidence, and the owner has signed Gate 2.
- **Nothing in §8 is dropped without an explicit, recorded owner decision.** A missing item is a blocker or a recorded removal — never a silent omission.
- Owner identity only from the authenticated session row. Service-layer tenant isolation (`services/ownership.require_user_id`) unchanged.
- Next.js remains the BFF; `TL_SERVICE_SECRET` never reaches the browser; relays stay same-origin, `no-store`, fail-shut on unset `SITE_ORIGIN`.
- **The 779 service/DB tests stay green** (§10.1). Retiring a test is allowed only when it asserts Streamlit behaviour; a service assertion living in a Streamlit-coupled file is **moved**, not deleted.
- **Golden parity harness (`tests/parity/`) stays green with zero numeric drift.** Snapshots are never refreshed in this phase.
- `services/metrics.py` and `prompts/` untouched.
- Python 3.9.6 floor (`Optional[X]`, no `X | Y`). **No new Python dependency.** No new npm dependency except `@playwright/test` if and only if T3 is approved.
- **Every migration implements `downgrade()`** and CI's `upgrade head → downgrade -1 → downgrade -1 → upgrade head` must pass. A downgrade that cannot restore data says so in its docstring.
- **Deploy order is part of correctness:** the web build that no longer reads a column or table ships and is verified live **before** the migration that drops it runs.
- Destructive production actions (the flip migration, the drop migrations, decommissioning Streamlit Cloud, deleting Streamlit Cloud secrets) are **owner actions**. Agents prepare, test and document them; agents do not run them against production.
- Failures are fixed codes; driver and exception text never reach a response or a log line that could carry user data.
- AI copy: reflection only — no trade ideas, signals, predictions or advice.
- Gates: `pytest tests/ -q`; `pytest tests/parity -q`; `ruff check src/ scripts/`; `black --check src/ scripts/ tests/`; in `web/` (run from `web/`): `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build` (localhost origins, non-placeholder `SUPPORT_EMAIL`); `scripts/generate_openapi.py` from the repo root + `npm --prefix web run api:types` leave no diff; `alembic heads` prints exactly one head.

---

## Execution process

| Group | Reversible? | Review depth |
|---|---|---|
| R — readiness evidence (parity ledger, funnel/CI origin, E2E smoke, screenshot migration, demo-playbook decision) | Yes — additive | Deep for the screenshot migration (writes to R2 and rows); light otherwise |
| **Gate 1** — owner confirms §11 criteria 1–4, 7, 8 and authorises the flip | — | Owner |
| F — flip every account and the default to `nextjs` | **Yes** — one `UPDATE` reverts it | Deep: the migration, the Streamlit-side refusal, rollback drill |
| **Gate 2** — owner confirms §11 criteria 5 and 6 held after the flip and authorises removal | — | Owner |
| X — remove toggle, handoff path, Streamlit sessions, `ui/`, UI tests, dependencies, CI origin, docs | **No** | **Deepest in the phase.** Deploy ordering, migrations both directions, nothing live left importing a deleted module, no service assertion lost |
| E — verification, mutation battery, handoff | — | Final boundary |

**Mutation discipline** (binding, Phase 9 hardened harness): pristine bytes keyed by full path; sha256 restore asserted after every mutant; `PYTHONDONTWRITEBYTECODE=1`; pytest run with `--color=no` and `FORCE_COLOR` removed from the environment; CAUGHT only when the intended tests collected, ran and at least one FAILED; collection/import/transform failure or timeout is ERROR; a selector matching nothing is NOT-RUN; target not matching exactly once is NOT-APPLIED; none of those count as caught. Verdict controls (injected syntax error, import error, empty selector, unmutated run, one known kill per language) run and pass before the battery. Final battery from a **clean HEAD** with preflight/postflight `git status`; gates run in private `git archive` extractions while a battery edits the worktree; reviewers work only in private extractions.

---

## Scope

**In:** the §8 parity ledger with evidence; retargeting `scripts/verify_public_funnel.py` usage and CI's `APP_ORIGIN` at the new app; a Playwright smoke per section at desktop and 375px (T3); an idempotent, owner-scoped local-screenshot → R2 migration script (T9); resolving the Strategy demo-playbook preview (T2); the flip migration; removing `app_surface`, `/continue`'s handoff form, `POST /api/auth/handoff`, `lib/auth/handoff.ts`, `lib/security/app-origin.ts`, `components/auto-submit.tsx`, `STREAMLIT_DOMAIN`/`SURFACE_STREAMLIT`, `auth_exchange.py`, `auth_handoff.py`, the Streamlit functions of `auth_sessions.py`, the `auth_handoffs` table and Streamlit session rows (T5); deleting `src/tradelens/ui/` including `_archive/`; retiring Streamlit-coupled tests with a per-file ledger; removing Streamlit/PyArrow/Plotly, `runtime.txt` and `.streamlit/`; updating CI, `README.md`, `CLAUDE.md`, `PRODUCT.md` and the Streamlit-referencing scripts; the Streamlit Cloud decommission runbook (T10).

**Explicitly not in:** building AI Reviews (T1 — its own phase, an entry blocker); new product features; refreshing parity snapshots; production database operations performed by an agent; changing the Render API/worker topology; the `metrics_store` module (no importer today — recorded, untouched).

**Carried forward, NOT this phase's to close (hard pre-release gates, owner-confirmed after the Phase 10A merge):** real PostgreSQL concurrency — purge-versus-upload lock, summary-save-versus-delete interleaving, account deletion with non-cascading auth rows, the Phase 10A locked review saves, **and Weekly Recap uniqueness**; live Anthropic adversarial testing; authenticated desktop + true 375px Playwright testing (Group R3 builds the harness; the authenticated run is owner-executed); Docker build, startup and health; dependency/security audit; live R2 and screenshot-migration verification (Task R4). The lexical Partner and review output guards remain defense-in-depth, not semantic guarantees.

**Non-blocking hardening carried from Phase 9 (recorded, not closed here):**
1. CSV formula protection does not normalise leading whitespace or Unicode lookalikes (only `=`, `+`, `-`, `@`, tab, carriage return are neutralised).
2. The legacy local-file resolve/unlink path has a narrow local symlink-swap race. **Group X4 does not remove it** — `data_deletion` still serves accounts whose rows name legacy local paths until R4's migration has run and been verified; record whether any such rows remain.
3. R2 deletion cannot be transactionally rolled back if the later DB transaction fails; retries must remain convergent (rows remain, a retry completes; the screenshot may be unavailable in the interim).

**Known pre-existing Streamlit boot failures — recorded separately from Phase 10, not Phase 10 defects:** `tests/test_pages_boot.py::test_analytics_single_setup_readout_does_not_claim_a_ranking`, `::test_analytics_category_names_are_escaped_exactly_once`, `::test_journal_detail_view_opens_a_selected_trade`. They leave the suite when X4 retires `test_pages_boot.py`. The handoff must say **"retired with the Streamlit UI, never fixed"** — not "resolved".

**Closes on retirement (recorded by Phase 7/9, closed only by X):** the narrow in-flight Streamlit request race at cutover; the unlocked Streamlit writers (`upsert_strategy_profile`, `save_profile_and_mark_completed`, `append_insight` called without a version check).

---

## Entry blockers — Phase 10 cannot pass Gate 1 until these are resolved

1. **AI Reviews — RESOLVED by Phase 10A, merged at `65b63d2` (2026-09-17).** Patterns, Weekly Recap and Daily Debrief now ship on the FastAPI + Next.js boundary (`/v1/reviews`, `web/app/app/reviews/`), job-backed through `ai_jobs` with the `weekly_recap` and `daily_debrief` kinds, and Codex-cleared. Task R1's ledger records each §8 AI Reviews item as `implemented` with its location and test (see the Phase 10A handoff section in `docs/coordination/CLAUDE_CODEX_HANDOFF.md`). Phase 10A also added migration `h4i5j6k7l8m9` and carried forward: real PostgreSQL concurrency now includes **Weekly Recap uniqueness** (`weekly_reviews` has no unique `(user_id, week_start)`; both save paths lock and select the existing row, so duplicate rows remain possible on PostgreSQL without a data migration).
2. **No browser E2E harness exists.** No `playwright.config.*`, no `@playwright/test` in `web/package.json`. §11.3 requires Playwright E2E green across all sections at desktop and 375px. See **T3**.
3. **No screenshot migration exists.** §11.7 requires "Screenshots migrated to R2 and verified readable". No script under `scripts/` performs it. See **T9**.
4. **The funnel check and CI still point at Streamlit.** `scripts/verify_public_funnel.py`'s documented `--app` is `https://tradelenai.streamlit.app`; `.github/workflows/ci.yml` sets `APP_ORIGIN: https://tradelens-app.streamlit.app` (test job, line 90) and `https://tradelenai.streamlit.app` (web job, line 101). §11.8 requires the funnel to pass against the new app origin.
5. **Owner-only criteria.** §11.5 (owner uses the new app one full week on real trades, including at least one weekly recap and one screenshot autofill — which itself depends on blocker 1) and §11.6 (all beta accounts on the new surface two consecutive weeks with no recorded fallback) cannot be satisfied by an agent. They are Gate 2.

---

## What already exists — read before writing anything

Verified on `main` at `6c1f161`:

- **Streamlit UI:** `src/tradelens/ui/app.py`, `design_system.py`, `components/`, `assets/`, pages `1_NewTrade.py`, `2_Trades.py`, `4_Analytics.py`, `5_Strategy.py`, `6_Insights.py`, `7_Partner.py`, `9_Settings.py`, and `pages/_archive/` (`0_Home.py`, `3_TradeDetail.py`, `6_Calendar.py`, `7_Weekly_Review.py`, `8_AI_Partner.py`).
- **Next.js pages:** `/app`, `/app/journal`, `/app/trades/new`, `/app/trades/[id]`, `/app/analytics`, `/app/strategy`, `/app/settings`, `/app/reviews` (stub), plus `/login`, `/signup`, `/verify-email`, `/onboarding`, `/forgot-password`, `/reset-password`, `/continue`, `/account-deleted`.
- **The toggle.** `db/models.py:85-92` — `User.app_surface`, `String`, `nullable=False`, `server_default=text("'streamlit'")`, comment "Removed once Streamlit is retired (Phase 10)". Added by `alembic/versions/y5z6a7b8c9d0_add_user_app_surface.py`. Alembic head is `h4i5j6k7l8m9` (`h4i5j6k7l8m9_add_daily_debriefs.py`, Phase 10A), which supersedes the Phase 9 head `g3h4i5j6k7l8_add_ai_analysis_job_guards.py` (Phase 10A merged at `65b63d2`).
- **Web routing on the toggle** (`web/lib/auth/session.ts`): `nextDestinationFor` (`/verify-email` → `/onboarding` → `/app` if `appSurface === "nextjs"` else `/continue`); `continuePageRedirect(user, eligible)`; `appLayoutRedirect` (sends any non-`nextjs` account to `/continue`). Session query selects `u.app_surface` (line 108). Login answers `next: "/continue"` after onboarding (`app/api/auth/login/route.ts:84`); onboarding answers `next: "/continue"` (`app/api/auth/onboarding/route.ts:95`; `onboarding-form.tsx:94` falls back to `/continue`). Tests: `web/__tests__/app-surface-routing.test.ts`, which also asserts **no write to `app_surface` anywhere under `web/`**.
- **Web handoff path:** `app/continue/page.tsx` (85 lines, POST form + `AutoSubmit`), `app/api/auth/handoff/route.ts` (84), `lib/auth/handoff.ts` (167; `handoffEligibility`, `issueHandoff`, `hasEnteredAppBefore`), `lib/security/app-origin.ts` (105; `handoffRedirectUrl`, reads `APP_ORIGIN`), `components/auto-submit.tsx` (39). `lib/auth/domains.ts` exports `STREAMLIT_DOMAIN = "tl.streamlit.v1|"` and `SURFACE_STREAMLIT` alongside the website constants still used by `lib/api/client.ts`, `lib/auth/login.ts`, `lib/auth/session.ts`. `lib/env.ts:38` lists `APP_ORIGIN` as public-safe. **Password reset writes to the handoff table:** `lib/auth/password-reset.ts:262-277` runs `UPDATE auth_handoffs SET consumed_at` inside the reset transaction and returns `handoffsVoided`; `app/api/auth/reset-password/route.ts:87` logs `handoffs_voided`; `web/__tests__/password-reset.test.ts:338,350` pin it. Comments naming the Streamlit surface, `APP_ORIGIN` or `auth_handoffs` also live in `lib/mail/messages.ts:11-19`, `lib/auth/verification.ts:10-18`, `lib/auth/login.ts:73`, `app/login/login-form.tsx:39`; `lib/security/responses.ts:101` lists a `"handoff"` auth-log event. `scripts/build-marketing.mjs` substitutes `__APP_ORIGIN__`; `site/main.js` documents that CTA. `scripts/probe-credential-domains.mjs` and `scripts/integration-handoff.mjs` exercise the Streamlit domain.
- **Python handoff path:** `services/auth_exchange.py` (173; `exchange_handoff_for_streamlit_session`, filters `app_surface = 'streamlit'`), `services/auth_handoff.py` (133; no importer under `src/`), `services/auth_sessions.py` (378; `STREAMLIT_DOMAIN`, `SURFACE_STREAMLIT`, `open_streamlit_session`, `restore_streamlit_session`, `revoke_streamlit_session` alongside the website functions). `db/models.py`: `AuthHandoff` (`auth_handoffs`), `AuthSession` with `CheckConstraint("surface IN ('website', 'streamlit')", name="ck_auth_sessions_surface")`. `services/account._OWNED_BY_USER` deletes `AuthSession` and `AuthHandoff` rows; `tests/test_account_deletion_references.py` sweeps every `user_id` table.
- **Services imported only by `ui/` under `src/`** (survey, 2026-09-14): `ai_screenshot_service`, `auth_exchange`, `debrief`. **No importer under `src/`:** `auth_handoff`, `metrics_store`.
- **Streamlit-coupled tests:** 65 files under `tests/` reference Streamlit or `ui/` (7 `*_check.py` runner scripts plus 58 test files). Of those, 16 are **MIXED** (service and UI assertions in one file) and most others import `ui/` at module level while only some functions touch it — for example `test_data_state.py` (0 of 21 functions), `test_phase4_motion.py` (0/23), `test_ai_autofill_review.py` (0/44). The spec's "1,280 functions / 54 files" is an estimate; X4 records the real count.
- **Dependencies:** `requirements.txt` = `-r requirements-base.txt` + `streamlit==1.50.0`, `pyarrow==21.0.0`, `plotly==6.7.0`, `pillow==11.3.0`. `requirements-api.txt` is the FastAPI image's set and already excludes the three. `requirements-dev.txt` includes `-r requirements.txt`. `tests/test_requirements.py` pins the split (Streamlit present in runtime, absent from API; `pyarrow==21.0.0`; the pillow split). `runtime.txt` = `python-3.11` (Streamlit Community Cloud). `.streamlit/config.toml`, `secrets.toml.example`, `secrets.toml.template`.
- **Deployment:** `render.yaml` runs `tradelens-api` and `tradelens-worker` from `Dockerfile.api` — no Streamlit service. Streamlit runs on Streamlit Community Cloud, configured outside the repository.
- **Parity harness:** `tests/parity/test_metrics_parity.py`, `dataset.py`, `snapshots/metrics.json`. Refresh only with `TL_UPDATE_SNAPSHOTS=1` — **forbidden in this phase**.
- **Docs mentioning Streamlit:** `README.md` (10), `PRODUCT.md` (6), `CLAUDE.md` (3). Scripts: `capture_app_screenshots.py`, `env_audit.py`, `integration_step10.py`, `integration_step11.py`, `build_site.py`, `verify_public_funnel.py`.

---

## Decisions — approved by the owner (2026-09-14)

All ten are **approved**, with these clarifications binding on the implementation:

- **T1** — AI Reviews is its own phase, **Phase 10A (Phase 9.5)**: Patterns, Weekly Recap and Daily Debrief migrated with normal implementation, review and Codex clearance, and **completed before Gate 1**. Phase 10 resumes with Group R only after Phase 10A's review boundary is cleared.
- **T2** — the Strategy demo-playbook preview is a **deliberate removal**, recorded explicitly in the parity ledger (Task R5).
- **T3** — `@playwright/test` is the **only** new Phase 10 dependency (dev-only).
- **T4** — flip first, hold, then remove Streamlit **in a later release**.
- **T5** — `auth_handoffs` and Streamlit session rows are dropped **only after the hold** and **only after the new web build no longer writes them** (X1 live, including the password-reset change).
- **T6** — `users.app_surface` is dropped in its own migration **only after rollback to Streamlit is no longer supported** — recorded at Gate 2 as the end of the rollback window.
- **T7** — Streamlit-only services are removed; **`debrief` is kept** because AI Reviews needs it.
- **T8** — every parity item needs evidence or an explicit removal decision before Gate 1. **Unknown items, such as "trade of the week", block Gate 1 until resolved.**
- **T9** — the screenshot migration is an **owner-scoped, dry-run-first** script. A stored reference is changed **only after the R2 object is verified**; a failed migration **never destroys the legacy reference**.
- **T10** — Streamlit Cloud decommissioning remains a **manual runbook action** by the owner.

**Not yet authorised:** any irreversible Streamlit removal (Group X). The order is Phase 10A → Phase 10 Group R → Gate 1 → Group F → hold → Gate 2 → Group X.

The original decision text follows, unchanged, for reference.

**T1 — AI Reviews becomes its own phase, executed before Gate 1 (recommended).** Patterns, Weekly Recap and Daily Debrief need an API router, relays, job-backed generation for the recap, and a page — a Phase-8-sized subsystem. The writing-plans scope rule puts an independent subsystem in its own plan. Phase 10 Group R may proceed in parallel; Gate 1 waits for AI Reviews to be merged and Codex-cleared. *Alternatives:* (a) fold AI Reviews into this plan as Group A (one very large phase, review load concentrated at the riskiest point); (b) record a deliberate removal of some or all of the three (breaks §11.5, which requires a weekly recap in the owner's week of use). Affects Entry blocker 1, Gate 1.

**T2 — Record a deliberate removal of the Strategy demo-playbook preview (recommended).** The new Strategy page already offers the ICT/SMC starter playbook and the §8 Strategy items; the preview is a Streamlit-era demo affordance that needs a demo read path in the Strategy API for no workflow a signed-in trader performs. *Alternative:* implement a read-only `GET /v1/strategy/demo-playbook` and a preview panel (adds a task R5b with API, relay and component). Affects Task R5.

**T3 — Add `@playwright/test` as a `web/` devDependency for §11.3 (recommended).** The spec names Playwright explicitly; the CDP screenshot recipe used in earlier phases is not a test runner. It is the phase's only new dependency, dev-only, excluded from `npm audit --omit=dev`. The authenticated run needs a seeded local account and is **owner-executed**; CI runs only the unauthenticated public-route smoke. *Alternative:* record a spec deviation and accept a manual, documented desktop + 375px checklist per section. Affects Task R3, Gate 1.

**T4 — Flip, hold, then remove: two releases (recommended).** Group F changes only data and the column default; all routing code stays, so any account can be returned to Streamlit with `UPDATE users SET app_surface = 'streamlit' WHERE id = :id`. Group X starts only after Gate 2 (two consecutive weeks, §11.6). *Alternative:* one release that flips and removes together — faster, but no rollback short of restoring a database backup. Affects Groups F, X.

**T5 — Drop `auth_handoffs` and Streamlit session rows; narrow the surface constraint (recommended).** After X1 no code issues or redeems a handoff and no Streamlit session can be restored. Migration X2 deletes `auth_sessions` rows with `surface = 'streamlit'`, replaces `ck_auth_sessions_surface` with `surface IN ('website')`, and drops `auth_handoffs`. Downgrade recreates the empty table and the wide constraint; deleted rows are not restored (documented). *Alternative:* keep both tables and the constraint as dead schema (no migration risk, permanent clutter, and `_OWNED_BY_USER` keeps a reference to a dead model). Affects Task X2.

**T6 — Drop `users.app_surface` in its own migration after X1 is live (recommended).** Downgrade re-adds the column `NOT NULL` with `server_default 'nextjs'` — per-account values are not restored, which is correct because every account was `nextjs` at Gate 2. Affects Task X3.

**T7 — Delete the Streamlit-only services with `ui/` (recommended):** `auth_exchange.py` and `auth_handoff.py` (handoff path, T5), and `ai_screenshot_service.py` **only if** R1 confirms nothing under `src/tradelens/api/` or `services/` reaches it after `ui/` goes. **Keep** `debrief.py` (AI Reviews needs it, T1). **Leave** `metrics_store.py` untouched (no importer today; outside this phase). Affects Task X4.

**T8 — Every §8 item without evidence in R1's ledger is a Gate 1 blocker until the owner marks it "implement" (new task or phase) or "removed" (recorded with a reason) (recommended).** The 2026-09-14 keyword sweep found no match in `web/` for "trade of the week" (§8 Analytics) or the demo-playbook preview; R1 confirms or refutes each against the running code. Affects Task R1, Gate 1.

**T9 — Screenshot migration is an owner-run script, dry-run by default, owner-scoped and idempotent (recommended).** `scripts/migrate_screenshots_to_r2.py` considers only `Screenshot.file_path` values that resolve inside `screenshot_service.SCREENSHOTS_DIR` with a file name starting `f"{trade_id}_"` and whose trade belongs to the named owner; it verifies image magic bytes, uploads to `storage.build_object_key(owner, trade_id, content_type)`, re-reads the object, then updates the row — object first, row second. Missing files are reported, not errors (§9.6 "most Streamlit Cloud files are already gone" — the designed missing state handles them). Remote `http(s)` references are reference-only and skipped. *Alternative:* no migration; record that legacy local screenshots are abandoned and verify only the missing-file state. Affects Task R4, §11.7.

**T10 — Streamlit Cloud is decommissioned by the owner from a runbook, after X lands and is live (recommended).** The runbook lists: confirm no traffic for 7 days in Streamlit Cloud analytics; delete the app; delete its secrets (`ANTHROPIC_API_KEY`, `DATABASE_URL` copies held by Streamlit Cloud); rotate any credential that existed only there; remove the old Streamlit URL from Vercel `APP_ORIGIN` if still set. Affects Task X6.

---

## File structure

**Group R**
- Create `docs/superpowers/parity/2026-09-14-phase10-parity-ledger.md` — one row per §8 item: item, Next.js location (file:line or route), verifying test, status (`implemented` / `blocker` / `removed — reason`).
- Create `tests/test_parity_ledger.py` — the ledger has exactly the §8 items, each with a status, and no `blocker` row once Gate 1 is recorded.
- Modify `scripts/verify_public_funnel.py` — docstring example `--app` is the new app origin; `EXPECTED_APP_HOSTS` (or equivalent check) rejects `*.streamlit.app` as the app destination.
- Modify `.github/workflows/ci.yml` — `APP_ORIGIN` for both jobs becomes the new app origin (owner supplies the production value; CI uses `https://app.tradelensai.io` unless the owner names another).
- Create `web/playwright.config.ts`, `web/e2e/public.spec.ts`, `web/e2e/sections.spec.ts`, `web/e2e/helpers.ts`; modify `web/package.json` (devDependency + `e2e` scripts); modify `web/tsconfig.json`/`web/vitest.config.*` only to exclude `e2e/` from Vitest (T3).
- Create `scripts/migrate_screenshots_to_r2.py`, `tests/test_migrate_screenshots_to_r2.py` (T9).
- T2 outcome recorded in the ledger (no code if the removal is approved).

**Group F**
> **Revision numbering (updated after the Phase 10A merge, `65b63d2`).** Phase 10A took `h4i5j6k7l8m9`, so this
> plan's three migrations follow the live head: flip `i5j6k7l8m9n0`, drop-Streamlit-auth `j6k7l8m9n0o1`,
> drop-column `k7l8m9n0o1p2`. Re-check `alembic heads` before writing each one.

- Create `alembic/versions/i5j6k7l8m9n0_flip_app_surface_to_nextjs.py`.
- Modify `src/tradelens/db/models.py` — `app_surface` `server_default` becomes `'nextjs'`.
- Modify `tests/test_app_surface_migration.py`; create `tests/test_flip_app_surface_migration.py`.
- Modify `web/__tests__/app-surface-routing.test.ts` — the "moves nobody by default" block is replaced by "default is nextjs"; the no-write invariant stays.
- Create `docs/superpowers/runbooks/phase10-flip-and-rollback.md`.

**Group X**
- **X1 (web):** modify `web/lib/auth/session.ts`, `web/app/api/auth/login/route.ts`, `web/app/api/auth/onboarding/route.ts`, `web/app/onboarding/onboarding-form.tsx`, `web/app/app/layout.tsx`, `web/app/continue/page.tsx` (becomes a redirect), `web/lib/auth/domains.ts`, `web/lib/env.ts`, `web/scripts/build-marketing.mjs`, `site/main.js`; delete `web/app/api/auth/handoff/route.ts`, `web/lib/auth/handoff.ts`, `web/lib/security/app-origin.ts`, `web/components/auto-submit.tsx`, `web/scripts/probe-credential-domains.mjs`, `web/scripts/integration-handoff.mjs`; tests updated or deleted with a ledger; create `web/__tests__/no-streamlit-path.test.ts`.
- **X2 (Python auth):** delete `src/tradelens/services/auth_exchange.py`, `src/tradelens/services/auth_handoff.py`, `scripts/integration_step10.py`, `scripts/integration_step11.py` (Streamlit handoff integration drivers); modify `src/tradelens/services/auth_sessions.py`, `src/tradelens/services/account.py`, `src/tradelens/db/models.py`, `scripts/db_inventory.py`, `scripts/inspect_account.py`, `scripts/cleanup_dev_test_users.py`; create `alembic/versions/j6k7l8m9n0o1_drop_streamlit_auth.py`; tests updated.
- **X3 (column):** create `alembic/versions/k7l8m9n0o1p2_drop_users_app_surface.py`; modify `src/tradelens/db/models.py`; delete `tests/test_app_surface_migration.py`, `tests/test_flip_app_surface_migration.py`; modify `web/__tests__/app-surface-routing.test.ts` → delete (its invariants move to `no-streamlit-path.test.ts`).
- **X4 (UI + tests):** delete `src/tradelens/ui/` (all of it, including `_archive/`); delete the seven `tests/*_check.py` runners; retire or migrate test files per `docs/superpowers/parity/2026-09-14-phase10-test-retirement-ledger.md`; create `tests/test_no_streamlit_imports.py`.
- **X5 (deps, CI, docs, scripts):** modify `requirements.txt`, `requirements-dev.txt`, `tests/test_requirements.py`; delete `runtime.txt`, `.streamlit/`; modify `.github/workflows/ci.yml`, `README.md`, `CLAUDE.md`, `PRODUCT.md`, `scripts/capture_app_screenshots.py`, `scripts/env_audit.py`, `scripts/build_site.py`.
- **X6:** create `docs/superpowers/runbooks/phase10-streamlit-cloud-decommission.md`.

---

## Group R — readiness evidence (reversible)

### Task R1: The §8 parity ledger

**Files:**
- Create: `docs/superpowers/parity/2026-09-14-phase10-parity-ledger.md`
- Test: `tests/test_parity_ledger.py`

**Interfaces:**
- Consumes: spec §8 (verbatim item lists).
- Produces: `LEDGER_PATH = pathlib.Path("docs/superpowers/parity/2026-09-14-phase10-parity-ledger.md")`; ledger row format `| <section> | <item> | <location> | <test> | <status> |` where status ∈ `implemented`, `blocker`, `removed — <reason>`. Gate 1 and T8 read it.

- [ ] **Step 1: Write the failing test**

```python
"""The §8 parity ledger is complete and honest.

Spec §8: "Nothing below may be dropped without an explicit, recorded decision."
Every §8 item appears exactly once with a status; `implemented` rows name a
location and a test; `removed` rows carry a reason.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/superpowers/parity/2026-09-14-phase10-parity-ledger.md"

SECTION_ITEMS = {
    "Overview": [
        "KPI row (net P&L, win rate, expectancy, profit factor, trades)", "today P&L",
        "this-week P&L", "max drawdown", "rule adherence", "edge leak", "consistency score",
        "equity curve", "current/best streak", "average win", "average loss",
        "killzone performance", "setup performance", "trading-days calendar",
        "activation next-step", "recent trades", "filter panel", "low-data states",
    ],
    "Journal / Trades": [
        "date range", "asset", "session", "setup filters",
        "trades table (date, asset, session, setup, result, P&L, R, grade, screenshot)",
        "calendar month view", "open-from-day", "trade detail", "AI summary of the filtered set",
        "edit", "delete with confirmation", "per-trade screenshot upload",
    ],
    "New Trade": [
        "upload or image URL", "quality check", "AI analysis", "autofill review per field",
        "trade date", "entry time", "session auto-detect", "asset", "timeframe", "HTF bias",
        "LTF bias", "setup model", "evidence", "confirmation text",
        "followed-rules (yes/no/partial)", "result", "P&L", "risk", "position size",
        "R multiple", "exact price levels", "reflection notes",
        "emotion log (before/during/after)", "mistake tags", "completeness warnings",
        "draft persistence", "duplicate detection", "outcome/P&L contradiction block",
    ],
    "AI Reviews": [
        "Patterns (candidates, cards, confidence, evidence, sample size, next review action)",
        "Weekly Recap (week selector, generate, retry, validated sections)",
        "Daily Debrief (day selector, five sections)", "read-full-note disclosure",
    ],
    "Analytics": [
        "date range", "asset/session/strategy filters",
        "four lenses (Performance, Risk, Timing, Setups)", "equity curve", "daily P&L",
        "drawdown series", "R-multiple distribution", "by day of week", "by session",
        "by strategy", "by timeframe", "by asset", "by setup type", "emotion vs RR",
        "by hour of day", "killzone performance", "confirmation-model performance",
        "mistake frequency", "total edge leak", "rule adherence", "consistency score",
        "trade of the week", "period deltas", "evidence narrative per lens",
    ],
    "Strategy Profile": [
        "identity (name, style)", "markets", "timeframes", "entry rules",
        "exit rules (stop, target)", "risk rules", "setups", "mistakes to avoid",
        "active strategy", "ICT/SMC starter playbook", "sections-written progress",
        "skip path", "AI insight append",
    ],
    "AI Partner": [
        "global chat", "per-trade chat", "journal-grounded context", "evidence sources",
        "history trimming", "scope guard", "image attachment",
    ],
    "Settings": [
        "recovery email", "timezone", "API-key guidance", "CSV export", "CSV import",
        "load sample trades", "clear sample trades", "delete all trades", "delete account",
        "monthly cost by feature", "demo banner",
    ],
    "Cross-cutting": [
        "onboarding gate", "strategy gate", "activation status",
        "corrections capture feeding few-shot", "AI usage and cost logging", "DEMO_MODE",
        "low-sample confidence policy",
        "reflection-only safety language (never signals, predictions, or advice)",
    ],
    "Carried decisions": ["Strategy demo-playbook preview"],
}

ROW = re.compile(r"^\|\s*(?P<section>[^|]+?)\s*\|\s*(?P<item>[^|]+?)\s*\|\s*(?P<location>[^|]*?)\s*"
                 r"\|\s*(?P<test>[^|]*?)\s*\|\s*(?P<status>[^|]+?)\s*\|$")


def _rows():
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match and match["section"] not in ("Section", "---") and not set(match["section"]) <= {"-"}:
            rows.append(match.groupdict())
    return rows


def test_every_section_8_item_appears_exactly_once():
    seen = {}
    for row in _rows():
        key = (row["section"], row["item"])
        seen[key] = seen.get(key, 0) + 1
    expected = {(s, i) for s, items in SECTION_ITEMS.items() for i in items}
    assert set(seen) == expected, {
        "missing": sorted(expected - set(seen)), "unexpected": sorted(set(seen) - expected)}
    assert all(count == 1 for count in seen.values()), {k: v for k, v in seen.items() if v > 1}


def test_every_row_has_an_allowed_status_with_its_evidence():
    for row in _rows():
        status = row["status"]
        assert status == "implemented" or status == "blocker" or status.startswith("removed — "), row
        if status == "implemented":
            assert row["location"] and row["test"], row
        if status.startswith("removed — "):
            assert len(status) > len("removed — ") + 10, row


def test_implemented_locations_exist():
    for row in _rows():
        if row["status"] != "implemented":
            continue
        path = row["location"].split(":")[0].strip("` ")
        assert (ROOT / path).exists(), row
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_parity_ledger.py -v`
Expected: FAIL — `FileNotFoundError` for the ledger.

- [ ] **Step 3: Build the ledger from the running code**

For every item, find the Next.js location by reading the page/component (not by keyword alone) and the test that pins it (`web/__tests__/…` or `tests/test_api_…`). Header and first rows, exactly this shape:

```markdown
# Phase 10 — §8 parity ledger

Source: spec §8. Status is one of `implemented`, `blocker`, `removed — <reason>`.
A `removed` row requires the owner's recorded decision (T8). Built against `<commit>`.

| Section | Item | Location | Test | Status |
|---|---|---|---|---|
| Overview | KPI row (net P&L, win rate, expectancy, profit factor, trades) | web/components/app/overview/kpi-row.tsx | web/__tests__/overview-kpi-row.test.tsx | implemented |
| AI Reviews | Weekly Recap (week selector, generate, retry, validated sections) | web/app/app/reviews/page.tsx | — | blocker |
| Carried decisions | Strategy demo-playbook preview | — | — | blocker |
```

Use the exact file names found in the tree; the two example paths in the Overview row above must be replaced by the real component and test if they differ. Mark every AI Reviews row `blocker` until T1's phase merges. Mark the demo-playbook row `blocker` until T2 is approved, then `removed — owner decision T2 (2026-09-…): the starter playbook covers the workflow; no signed-in trader flow needs a demo read path`.

- [ ] **Step 4: Run the tests**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_parity_ledger.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/parity/2026-09-14-phase10-parity-ledger.md tests/test_parity_ledger.py
git commit -m "docs(parity): Phase 10 section 8 ledger with evidence per item"
```

---

### Task R2: Funnel check and CI against the new app origin

**Files:**
- Modify: `scripts/verify_public_funnel.py`
- Modify: `.github/workflows/ci.yml:90`, `.github/workflows/ci.yml:101`
- Test: `tests/test_public_funnel.py` (extend)

**Interfaces:**
- Consumes: the owner-supplied production app origin (default placeholder in CI: `https://app.tradelensai.io`).
- Produces: `verify_public_funnel.is_retired_app_host(host: str) -> bool`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_public_funnel.py`)

```python
import pathlib

from scripts import verify_public_funnel as funnel


def test_a_streamlit_host_is_refused_as_the_app_destination():
    assert funnel.is_retired_app_host("tradelenai.streamlit.app") is True
    assert funnel.is_retired_app_host("tradelens-app.streamlit.app") is True
    assert funnel.is_retired_app_host("app.tradelensai.io") is False


def test_ci_no_longer_points_app_origin_at_streamlit():
    ci = (pathlib.Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text()
    assert "streamlit.app" not in ci
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_public_funnel.py -k "retired_app_host or streamlit" -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'is_retired_app_host'`.

- [ ] **Step 3: Implement**

In `scripts/verify_public_funnel.py`, add near the other constants and use it in the app check so a redirect or `--app` naming a retired host is a failure with the fixed message `app destination is the retired Streamlit host`:

```python
# The Streamlit surface is retired (Phase 10). A funnel that still lands a
# visitor there passes the old contract and fails the product.
RETIRED_APP_HOST_SUFFIXES = (".streamlit.app",)


def is_retired_app_host(host: str) -> bool:
    host = (host or "").strip().lower().rstrip(".")
    return any(host == s.lstrip(".") or host.endswith(s) for s in RETIRED_APP_HOST_SUFFIXES)
```

Change the docstring example to `--app https://app.tradelensai.io`. In `ci.yml` set both `APP_ORIGIN` values to `https://app.tradelensai.io` (or the owner's value).

- [ ] **Step 4: Run the tests**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_public_funnel.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/verify_public_funnel.py .github/workflows/ci.yml tests/test_public_funnel.py
git commit -m "fix(funnel): refuse the retired Streamlit host; point CI at the new app origin"
```

---

### Task R3: Playwright smoke at desktop and 375px (requires T3)

**Files:**
- Modify: `web/package.json` (devDependency `@playwright/test`, scripts `e2e`, `e2e:public`)
- Create: `web/playwright.config.ts`, `web/e2e/helpers.ts`, `web/e2e/public.spec.ts`, `web/e2e/sections.spec.ts`
- Modify: `web/vitest.config.ts` — exclude `e2e/**`

**Interfaces:**
- Consumes: `E2E_BASE_URL` (default `http://localhost:3000`), `E2E_EMAIL`, `E2E_PASSWORD` (owner-supplied, never committed; the sections spec skips itself when absent).
- Produces: `npm run e2e:public` (CI-safe), `npm run e2e` (owner-run, authenticated).

- [ ] **Step 1: Install and configure**

Run (from `web/`): `npm install --save-dev --save-exact @playwright/test@1.49.1` then `npx playwright install chromium`.

`web/playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile-375", use: { ...devices["Pixel 5"], viewport: { width: 375, height: 812 } } },
  ],
});
```

Add to `web/vitest.config.ts` `test.exclude`: `"e2e/**"` (keep the existing excludes).

- [ ] **Step 2: Write the public smoke**

`web/e2e/public.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

import { expectNoHorizontalScroll } from "./helpers";

for (const path of ["/login", "/signup", "/forgot-password"]) {
  test(`${path} renders without horizontal scroll`, async ({ page }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBeLessThan(400);
    await expect(page.locator("h1")).toBeVisible();
    await expectNoHorizontalScroll(page);
  });
}

test("an anonymous /app request is sent to sign in", async ({ page }) => {
  await page.goto("/app");
  await expect(page).toHaveURL(/\/login/);
});
```

`web/e2e/helpers.ts`:

```ts
import { expect, type Page } from "@playwright/test";

export async function expectNoHorizontalScroll(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
}

export async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL(/\/app(\/|$)/);
}
```

- [ ] **Step 3: Write the authenticated sections smoke**

`web/e2e/sections.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

import { expectNoHorizontalScroll, signIn } from "./helpers";

const email = process.env.E2E_EMAIL;
const password = process.env.E2E_PASSWORD;

test.skip(!email || !password, "E2E_EMAIL and E2E_PASSWORD are owner-supplied; never committed");

const SECTIONS: { path: string; heading: RegExp }[] = [
  { path: "/app", heading: /overview/i },
  { path: "/app/journal", heading: /journal/i },
  { path: "/app/trades/new", heading: /new trade/i },
  { path: "/app/analytics", heading: /analytics/i },
  { path: "/app/reviews", heading: /ai reviews/i },
  { path: "/app/strategy", heading: /strategy/i },
  { path: "/app/settings", heading: /settings/i },
];

test.beforeEach(async ({ page }) => {
  await signIn(page, email as string, password as string);
});

for (const section of SECTIONS) {
  test(`${section.path} renders its heading, no error state, no horizontal scroll`, async ({ page }) => {
    await page.goto(section.path);
    await expect(page.getByRole("heading", { level: 1, name: section.heading })).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expectNoHorizontalScroll(page);
  });
}
```

Add to `web/package.json` scripts: `"e2e": "playwright test"`, `"e2e:public": "playwright test e2e/public.spec.ts"`.

- [ ] **Step 4: Run**

Run (from `web/`, with `npm run dev` serving on port 3000 in a separate terminal): `npm run e2e:public`
Expected: 8 passed (4 tests × 2 projects). Then confirm `npx vitest run` still reports the same file count as before (Playwright specs excluded) and `npx tsc --noEmit` is clean.

The authenticated `npm run e2e` is **owner-run** against a seeded local or staging account; its result is recorded in the handoff with the date, base URL and commit. An agent never reports it as run unless it ran.

- [ ] **Step 5: Commit**

```bash
git add web/package.json web/package-lock.json web/playwright.config.ts web/e2e web/vitest.config.ts
git commit -m "test(e2e): Playwright smoke per section at desktop and 375px"
```

---

### Task R4: Owner-scoped, idempotent screenshot migration to R2 (requires T9)

**Files:**
- Create: `scripts/migrate_screenshots_to_r2.py`
- Test: `tests/test_migrate_screenshots_to_r2.py`

**Interfaces:**
- Consumes (verified): `storage.build_object_key(user_id, trade_id, content_type) -> str`; `storage.r2_config() -> dict` with `"bucket"`; `storage._client()` (boto3-compatible `put_object`, `head_object`); `screenshot_service.SCREENSHOTS_DIR`, `screenshot_service.PROJECT_ROOT`; `db.session.SessionLocal`; models `Screenshot(trade_id, file_path)`, `Trade(id, user_id)`.
- Produces: `migrate_owner(owner: int, *, apply: bool) -> MigrationReport` with `MigrationReport(migrated: List[int], missing: List[int], skipped: List[int], failed: List[int])` of screenshot ids; CLI `python -m scripts.migrate_screenshots_to_r2 --owner <id> [--apply]`.

- [ ] **Step 1: Write the failing tests**

```python
"""Legacy local screenshots move to R2: object first, row second, never another owner's file."""

import pathlib

import pytest

from scripts import migrate_screenshots_to_r2 as mig
from src.tradelens.api import storage
from src.tradelens.db.models import Screenshot, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import screenshot_service

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class FakeR2:
    def __init__(self, fail_put=False):
        self.objects = {}
        self.fail_put = fail_put

    def put_object(self, Bucket, Key, Body, ContentType):
        if self.fail_put:
            raise RuntimeError("store down")
        self.objects[Key] = (Body, ContentType)

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise RuntimeError("missing")
        return {"ContentLength": len(self.objects[Key][0])}


def _trade(owner):
    db = SessionLocal()
    try:
        row = Trade(user_id=owner, asset="NQ", direction="Long", result="Win")
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _shot(trade_id, path):
    db = SessionLocal()
    try:
        row = Screenshot(trade_id=trade_id, file_path=str(path))
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _path_of(shot_id):
    db = SessionLocal()
    try:
        return db.get(Screenshot, shot_id).file_path
    finally:
        db.close()


@pytest.fixture
def store(monkeypatch, tmp_path):
    root = tmp_path / "screenshots"
    root.mkdir()
    monkeypatch.setattr(screenshot_service, "SCREENSHOTS_DIR", root)
    fake = FakeR2()
    monkeypatch.setattr(storage, "_client", lambda: fake)
    monkeypatch.setattr(storage, "r2_config", lambda: {"bucket": "b"})
    return root, fake


def test_dry_run_changes_nothing(two_users, store):
    root, fake = store
    owner, _ = two_users
    trade = _trade(owner)
    file = root / ("%d_chart.png" % trade)
    file.write_bytes(PNG)
    shot = _shot(trade, file)
    report = mig.migrate_owner(owner, apply=False)
    assert report.migrated == [shot]
    assert fake.objects == {}
    assert _path_of(shot) == str(file)


def test_apply_uploads_then_rewrites_the_row(two_users, store):
    root, fake = store
    owner, _ = two_users
    trade = _trade(owner)
    file = root / ("%d_chart.png" % trade)
    file.write_bytes(PNG)
    shot = _shot(trade, file)
    report = mig.migrate_owner(owner, apply=True)
    assert report.migrated == [shot] and report.failed == []
    key = _path_of(shot)
    assert key in fake.objects and fake.objects[key] == (PNG, "image/png")
    assert mig.migrate_owner(owner, apply=True).migrated == []  # idempotent


def test_a_failed_upload_leaves_the_row_untouched(two_users, store, monkeypatch):
    root, _ = store
    owner, _ = two_users
    monkeypatch.setattr(storage, "_client", lambda: FakeR2(fail_put=True))
    trade = _trade(owner)
    file = root / ("%d_chart.png" % trade)
    file.write_bytes(PNG)
    shot = _shot(trade, file)
    report = mig.migrate_owner(owner, apply=True)
    assert report.failed == [shot] and report.migrated == []
    assert _path_of(shot) == str(file)


def test_another_owners_file_and_escapes_are_never_uploaded(two_users, store):
    root, fake = store
    owner, other = two_users
    theirs = _trade(other)
    their_file = root / ("%d_theirs.png" % theirs)
    their_file.write_bytes(PNG)
    mine = _trade(owner)
    wrong_name = _shot(mine, their_file)  # names another trade's file
    outside = _shot(mine, pathlib.Path("/etc/passwd"))
    remote = _shot(mine, "https://example.test/chart.png")
    report = mig.migrate_owner(owner, apply=True)
    assert sorted(report.skipped) == sorted([wrong_name, outside, remote])
    assert fake.objects == {}


def test_a_missing_file_is_reported_not_raised(two_users, store):
    root, _ = store
    owner, _ = two_users
    trade = _trade(owner)
    shot = _shot(trade, root / ("%d_gone.png" % trade))
    assert mig.migrate_owner(owner, apply=True).missing == [shot]


def test_a_non_image_is_skipped(two_users, store):
    root, fake = store
    owner, _ = two_users
    trade = _trade(owner)
    file = root / ("%d_chart.png" % trade)
    file.write_bytes(b"#!/bin/sh\n")
    shot = _shot(trade, file)
    assert mig.migrate_owner(owner, apply=True).skipped == [shot]
    assert fake.objects == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_migrate_screenshots_to_r2.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.migrate_screenshots_to_r2'`.

- [ ] **Step 3: Implement**

`scripts/migrate_screenshots_to_r2.py`:

```python
"""Move one owner's legacy local screenshots into R2. Owner-run; dry-run by default.

Object first, row second: the row is rewritten to the R2 key only after the
upload is read back. A failure leaves the row naming the local file, so a retry
converges. Only files inside SCREENSHOTS_DIR, named for their own trade, owned
by --owner, with image magic bytes, are considered. Remote http(s) references
and missing files are reported, never fetched or raised.

    python -m scripts.migrate_screenshots_to_r2 --owner 42          # report only
    python -m scripts.migrate_screenshots_to_r2 --owner 42 --apply  # upload + rewrite
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from src.tradelens.api import storage
from src.tradelens.db.models import Screenshot, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import screenshot_service
from src.tradelens.services.ownership import require_user_id

_log = logging.getLogger(__name__)

_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


@dataclass
class MigrationReport:
    migrated: List[int] = field(default_factory=list)
    missing: List[int] = field(default_factory=list)
    skipped: List[int] = field(default_factory=list)
    failed: List[int] = field(default_factory=list)


def _content_type(head: bytes) -> Optional[str]:
    for magic, kind in _MAGIC:
        if head.startswith(magic):
            return kind
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def _local_file(raw: str, trade_id: int) -> Optional[Path]:
    """The resolved file if `raw` is this trade's legacy file inside the root, else None."""
    if "://" in raw:
        return None
    root = Path(screenshot_service.SCREENSHOTS_DIR).resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = screenshot_service.PROJECT_ROOT / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if root not in resolved.parents:
        return None
    if not resolved.name.startswith("{}_".format(int(trade_id))):
        return None
    return resolved


def migrate_owner(owner: int, *, apply: bool) -> MigrationReport:
    owner = require_user_id(owner)
    report = MigrationReport()
    db = SessionLocal()
    try:
        rows = (
            db.query(Screenshot.id, Screenshot.trade_id, Screenshot.file_path)
            .join(Trade, Trade.id == Screenshot.trade_id)
            .filter(Trade.user_id == owner)
            .order_by(Screenshot.id)
            .all()
        )
    finally:
        db.close()

    for shot_id, trade_id, raw in rows:
        prefix = storage.build_object_key(owner, trade_id, "image/png").rsplit("/", 1)[0]
        if raw.startswith(prefix + "/"):
            continue  # already an R2 key for this owner and trade
        path = _local_file(raw, trade_id)
        if path is None:
            report.skipped.append(shot_id)
            continue
        if not path.exists():
            report.missing.append(shot_id)
            continue
        body = path.read_bytes()
        kind = _content_type(body[:16])
        if kind is None:
            report.skipped.append(shot_id)
            continue
        if not apply:
            report.migrated.append(shot_id)
            continue
        key = storage.build_object_key(owner, trade_id, kind)
        try:
            client = storage._client()
            bucket = storage.r2_config()["bucket"]
            client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=kind)
            client.head_object(Bucket=bucket, Key=key)
        except Exception:  # noqa: BLE001 — a store fault is a reported failure
            _log.warning("Screenshot %s could not be uploaded", int(shot_id))
            report.failed.append(shot_id)
            continue
        db = SessionLocal()
        try:
            updated = (
                db.query(Screenshot)
                .filter(Screenshot.id == shot_id, Screenshot.file_path == raw)
                .update({Screenshot.file_path: key}, synchronize_session=False)
            )
            db.commit()
        finally:
            db.close()
        (report.migrated if updated == 1 else report.failed).append(shot_id)
    return report


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--owner", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    report = migrate_owner(args.owner, apply=args.apply)
    print(
        "migrated=%d missing=%d skipped=%d failed=%d apply=%s"
        % (len(report.migrated), len(report.missing), len(report.skipped), len(report.failed), args.apply)
    )
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

Before relying on `build_object_key`'s prefix shape in `migrate_owner`, read `src/tradelens/api/storage.py` `build_object_key` and `_is_final_key`; if a final key is not `<prefix>/<name>`, replace the `prefix` check with `storage._is_final_key(raw, owner, trade_id)` (verified to exist, signature `(key, owner, trade_id)`).

- [ ] **Step 4: Run the tests**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_migrate_screenshots_to_r2.py -v`
Expected: 6 passed. Then `ruff check scripts/` and `black --check scripts/ tests/`.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_screenshots_to_r2.py tests/test_migrate_screenshots_to_r2.py
git commit -m "feat(scripts): owner-scoped, idempotent legacy screenshot migration to R2"
```

---

### Task R5: Resolve the Strategy demo-playbook preview (requires T2)

**Files:**
- Modify: `docs/superpowers/parity/2026-09-14-phase10-parity-ledger.md` (the `Carried decisions` row)

- [ ] **Step 1:** With T2 approved as recommended, set the row's status to `removed — owner decision T2 (<date>): the starter playbook on /app/strategy covers the workflow; no signed-in flow needs a demo read path`.
- [ ] **Step 2:** Run `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_parity_ledger.py -v` — 3 passed.
- [ ] **Step 3:** Commit: `git commit -am "docs(parity): record the demo-playbook preview decision (T2)"`.

If T2's alternative is chosen instead, stop and write Task R5b (API endpoint, relay, component, tests) before Gate 1.

---

## Gate 1 — owner authorises the flip

Recorded in the handoff with date and evidence links. All must hold:

- [ ] Phase 10A — AI Reviews (T1) merged and Codex-cleared; ledger AI Reviews rows `implemented`.
- [ ] `tests/test_parity_ledger.py` passes with **zero** `blocker` rows (§11.1). Add `test_no_blockers_remain_after_gate_1` at this point:

```python
def test_no_blockers_remain_after_gate_1():
    assert [r for r in _rows() if r["status"] == "blocker"] == []
```

- [ ] `pytest tests/parity -q` green, snapshots unchanged (§11.2).
- [ ] Owner-run `npm run e2e` green at desktop and 375px, recorded with date, base URL and commit (§11.3).
- [ ] Every Codex phase review closed with no open security finding (§11.4).
- [ ] R4 run with `--apply` for every owner with legacy local rows; the handoff records counts (migrated/missing/skipped/failed = 0) and a spot-check of migrated images opening in `/app/trades/[id]` (§11.7).
- [ ] `python scripts/verify_public_funnel.py --site <site> --app <new app origin>` exits 0 (§11.8).

---

## Group F — flip every account to Next.js (reversible)

### Task F1: Flip migration and default

**Files:**
- Create: `alembic/versions/i5j6k7l8m9n0_flip_app_surface_to_nextjs.py`
- Modify: `src/tradelens/db/models.py:85-92`
- Modify: `tests/test_app_surface_migration.py`
- Create: `tests/test_flip_app_surface_migration.py`
- Modify: `web/__tests__/app-surface-routing.test.ts:50-56`

**Interfaces:**
- Consumes: revision `h4i5j6k7l8m9`.
- Produces: revision `i5j6k7l8m9n0`; `users.app_surface` default `'nextjs'`; every existing row `'nextjs'`.

- [ ] **Step 1: Write the failing migration test**

`tests/test_flip_app_surface_migration.py`:

```python
"""The flip moves every account and the default; its downgrade restores only the default."""

import os
import pathlib
import sqlite3
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _alembic(db, *args):
    env = dict(os.environ, DATABASE_URL="sqlite:///%s" % db)
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env,
        capture_output=True, text=True, check=True,
    )


def _surfaces(db):
    with sqlite3.connect(db) as conn:
        return [r[0] for r in conn.execute("SELECT app_surface FROM users ORDER BY id")]


def _insert_user(db, username):
    with sqlite3.connect(db) as conn:
        cols = {r[1]: r for r in conn.execute("PRAGMA table_info(users)")}
        required = [name for name, r in cols.items() if r[3] == 1 and r[4] is None and r[5] == 0]
        values = {name: "x" for name in required}
        values["username"] = username
        conn.execute(
            "INSERT INTO users (%s) VALUES (%s)" % (", ".join(values), ", ".join("?" * len(values))),
            list(values.values()),
        )


def test_flip_moves_existing_accounts_and_the_default(tmp_path):
    db = tmp_path / "flip.db"
    _alembic(db, "upgrade", "h4i5j6k7l8m9")
    _insert_user(db, "before")
    assert _surfaces(db) == ["streamlit"]

    _alembic(db, "upgrade", "i5j6k7l8m9n0")
    assert _surfaces(db) == ["nextjs"]
    _insert_user(db, "after")
    assert _surfaces(db) == ["nextjs", "nextjs"]


def test_downgrade_restores_the_default_but_not_per_account_values(tmp_path):
    db = tmp_path / "flip.db"
    _alembic(db, "upgrade", "i5j6k7l8m9n0")
    _insert_user(db, "flipped")
    _alembic(db, "downgrade", "h4i5j6k7l8m9")
    _insert_user(db, "new-after-downgrade")
    assert _surfaces(db) == ["nextjs", "streamlit"]
```

Update `tests/test_app_surface_migration.py::test_users_has_app_surface_defaulting_to_streamlit` → rename to `test_users_has_app_surface_defaulting_to_nextjs` and assert `all(s == "nextjs" for s in surfaces)`.

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_flip_app_surface_migration.py tests/test_app_surface_migration.py -v`
Expected: FAIL — alembic `Can't locate revision identified by 'i5j6k7l8m9n0'`; the model default test fails on `streamlit`.

If `_insert_user` cannot satisfy a NOT NULL column without a default, read `models.User` and add that column to `values` explicitly with a valid value (e.g. `password_hash`); do not weaken the assertion.

- [ ] **Step 3: Implement**

`alembic/versions/i5j6k7l8m9n0_flip_app_surface_to_nextjs.py`:

```python
"""Flip every account, and the default, to the Next.js app (Phase 10, Group F).

Reversible by design: routing still honours app_surface, so returning one
account to Streamlit is `UPDATE users SET app_surface = 'streamlit' WHERE id = :id`.

downgrade() restores the column DEFAULT only. Per-account values are not
restored — at this point there is no record of which accounts were on which
surface, and every account was moved deliberately. Use the runbook's per-account
UPDATE to return specific accounts.

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
"""

import sqlalchemy as sa
from alembic import op

revision = "i5j6k7l8m9n0"
down_revision = "h4i5j6k7l8m9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE users SET app_surface = 'nextjs'")
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "app_surface",
            existing_type=sa.String(),
            existing_nullable=False,
            server_default=sa.text("'nextjs'"),
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "app_surface",
            existing_type=sa.String(),
            existing_nullable=False,
            server_default=sa.text("'streamlit'"),
        )
```

`src/tradelens/db/models.py` — replace the `app_surface` comment and default:

```python
    # Which application surface this account lands on after login. Every
    # account was flipped to 'nextjs' in Phase 10 Group F and new accounts
    # default to it; routing still honours the value so one account can be
    # returned to Streamlit until Group X removes the column.
    app_surface: Mapped[str] = mapped_column(
        String, nullable=False, server_default=text("'nextjs'")
    )
```

`web/__tests__/app-surface-routing.test.ts` — replace the first test of `describe("the cutover is opt-in", …)` and rename the block:

```ts
describe("the cutover default", () => {
  it("routes a nextjs account, the Phase 10 default, to the new app", () => {
    // Group F flipped every row and the column default; the fixture's
    // explicit "streamlit" below is the per-account rollback path.
    expect(nextDestinationFor(user({ appSurface: "nextjs" }))).toBe("/app");
  });
```

(the `has no write to app_surface anywhere under web/` test stays unchanged inside that block).

- [ ] **Step 4: Run**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_flip_app_surface_migration.py tests/test_app_surface_migration.py tests/test_auth_handoff_and_sessions.py tests/test_step10_handoff_exchange.py -v` then from `web/`: `npx vitest run __tests__/app-surface-routing.test.ts`. Then the CI migration drill against a scratch database:

```bash
DATABASE_URL=sqlite:///./data/phase10-drill.db alembic upgrade head
```

```bash
DATABASE_URL=sqlite:///./data/phase10-drill.db alembic downgrade -1
```

```bash
DATABASE_URL=sqlite:///./data/phase10-drill.db alembic upgrade head
```

Expected: all pass; `alembic heads` prints only `i5j6k7l8m9n0 (head)`. Delete `data/phase10-drill.db` afterwards.

Tests that create users and assert Streamlit handoff eligibility (`test_step10_handoff_exchange.py`, `test_auth_handoff_and_sessions.py`, `test_auth_fail_closed.py`) will now see `nextjs` by default. For each failure, set `app_surface='streamlit'` explicitly in that test's fixture — they test the Streamlit path, which still exists until X2 — and never change what the test asserts.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/i5j6k7l8m9n0_flip_app_surface_to_nextjs.py src/tradelens/db/models.py tests/ web/__tests__/app-surface-routing.test.ts
git commit -m "feat(cutover): flip every account and the default to the Next.js app"
```

### Task F2: Flip and rollback runbook

**Files:**
- Create: `docs/superpowers/runbooks/phase10-flip-and-rollback.md`

- [ ] **Step 1:** Write the runbook with exactly these sections: *Preconditions* (Gate 1 recorded; database backup taken and its identifier written down; Streamlit Cloud still live); *Apply* (`alembic upgrade i5j6k7l8m9n0` against production, run by the owner); *Verify* (`SELECT app_surface, COUNT(*) FROM users GROUP BY app_surface` returns only `nextjs`; sign in as a beta account lands on `/app`; opening the Streamlit URL signed in shows its "moved to the web app" refusal); *Roll back one account* (`UPDATE users SET app_surface = 'streamlit' WHERE id = :id;` then that user signs in again); *Roll back everyone* (`alembic downgrade h4i5j6k7l8m9` then `UPDATE users SET app_surface = 'streamlit';`); *Record* (date, operator, counts, any rollback and why — §11.6 requires "no recorded fallback").
- [ ] **Step 2:** Commit: `git add docs/superpowers/runbooks/phase10-flip-and-rollback.md && git commit -m "docs(runbook): Phase 10 flip and rollback"`.

---

## Gate 2 — owner authorises removal

- [ ] Flip applied in production (F2 *Record* filled in).
- [ ] Owner used the new app for one full week on real trades, including at least one weekly recap and one screenshot autofill (§11.5) — dates recorded.
- [ ] All beta accounts on `nextjs` for two consecutive weeks with **no recorded fallback** (§11.6) — the F2 record shows zero rollbacks in the window.
- [ ] Decisions T4–T7 and T10 approved (done 2026-09-14); **the end of the Streamlit rollback window is recorded with a date** (T6) — X3 may not run before it.

**Point of no return.** Everything below deletes code, tables and a column.

---

## Group X — removal (irreversible)

**Deploy order (binding):** X1 web deploy verified live → X2 migration → X3 migration → X4/X5 (code only, no schema) → X6 owner decommission. X2 and X3 must not run in production before the X1 web build is live, because the currently deployed web reads `u.app_surface`, issues handoffs, **and voids handoffs inside every password reset** — dropping `auth_handoffs` under that build makes every password reset fail its transaction.

### Task X1: The web stops reading `app_surface` and stops issuing handoffs

**Files:**
- Modify: `web/lib/auth/session.ts` (remove `appSurface` from `WebsiteUser` and the SELECT; `nextDestinationFor`, `appLayoutRedirect` without surface; delete `continuePageRedirect`)
- Modify: `web/app/api/auth/login/route.ts:84`, `web/app/api/auth/onboarding/route.ts:95`, `web/app/onboarding/onboarding-form.tsx:94`, `web/app/app/layout.tsx:34-36`
- Replace: `web/app/continue/page.tsx` (redirect only — old bookmarks and emailed links still work)
- Delete: `web/app/api/auth/handoff/route.ts`, `web/lib/auth/handoff.ts`, `web/lib/security/app-origin.ts`, `web/components/auto-submit.tsx`, `web/scripts/probe-credential-domains.mjs`, `web/scripts/integration-handoff.mjs`
- Modify: `web/lib/auth/domains.ts` (remove `STREAMLIT_DOMAIN`, `SURFACE_STREAMLIT`), `web/lib/env.ts:38` (remove `APP_ORIGIN`), `web/scripts/build-marketing.mjs` (CTA → `SITE_ORIGIN` + `/login`), `site/main.js` (comment)
- Modify: `web/lib/auth/password-reset.ts:171-278` (stop voiding handoffs; drop `handoffsVoided`), `web/app/api/auth/reset-password/route.ts:87` (drop `handoffs_voided`), `web/__tests__/password-reset.test.ts:338,350`
- Modify (comments/log names only): `web/lib/mail/messages.ts:11-19`, `web/lib/auth/verification.ts:10-18`, `web/lib/auth/login.ts:73`, `web/app/login/login-form.tsx:39`, `web/lib/security/responses.ts:101` (remove the `"handoff"` event if nothing logs it after X1)
- Delete: `web/__tests__/handoff.test.ts`; rewrite `web/__tests__/app-surface-routing.test.ts` as `web/__tests__/post-login-routing.test.ts`; update every test in the "Web tests touching handoff" list below that fails
- Create: `web/__tests__/no-streamlit-path.test.ts`

**Interfaces:**
- Consumes: `WebsiteUser` without `appSurface`.
- Produces: `nextDestinationFor(user: WebsiteUser): "/verify-email" | "/onboarding" | "/app"`; `appLayoutRedirect(user: WebsiteUser): "/verify-email" | "/onboarding" | null`. No export named `continuePageRedirect`, `handoffEligibility`, `issueHandoff`, `hasEnteredAppBefore`, `handoffRedirectUrl`, `STREAMLIT_DOMAIN`, `SURFACE_STREAMLIT`.

- [ ] **Step 1: Write the failing tests**

`web/__tests__/post-login-routing.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { appLayoutRedirect, nextDestinationFor, type WebsiteUser } from "@/lib/auth/session";

function user(overrides: Partial<WebsiteUser> = {}): WebsiteUser {
  return {
    userId: 1,
    email: "trader@example.com",
    emailVerifiedAt: new Date(),
    emailVerificationRequired: true,
    onboardingCompleted: true,
    strategyProfileCompleted: true,
    ...overrides,
  };
}

describe("post-login routing after Streamlit retirement", () => {
  it("sends a verified, onboarded account to the app", () => {
    expect(nextDestinationFor(user())).toBe("/app");
    expect(appLayoutRedirect(user())).toBeNull();
  });

  it("still gates on email and onboarding, in that order", () => {
    expect(nextDestinationFor(user({ emailVerifiedAt: null, onboardingCompleted: false }))).toBe("/verify-email");
    expect(nextDestinationFor(user({ onboardingCompleted: false }))).toBe("/onboarding");
    expect(appLayoutRedirect(user({ emailVerifiedAt: null }))).toBe("/verify-email");
    expect(appLayoutRedirect(user({ onboardingCompleted: false }))).toBe("/onboarding");
  });

  it("never names /continue as a destination", () => {
    for (const u of [user(), user({ emailVerifiedAt: null }), user({ onboardingCompleted: false })]) {
      expect(nextDestinationFor(u)).not.toBe("/continue");
      expect(appLayoutRedirect(u)).not.toBe("/continue");
    }
  });
});
```

`web/__tests__/no-streamlit-path.test.ts`:

```ts
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const WEB = path.join(__dirname, "..");
const ROOTS = ["app", "lib", "components", "scripts"].map((d) => path.join(WEB, d));
const FORBIDDEN: [RegExp, string][] = [
  [/app_surface|appSurface/, "reads or writes the retired app_surface column"],
  [/streamlit/i, "references the retired Streamlit surface"],
  [/APP_ORIGIN/, "uses the retired Streamlit app origin"],
  [/\/api\/auth\/handoff/, "calls the removed handoff endpoint"],
  [/auth_handoffs|issueHandoff|handoffEligibility/, "uses the removed handoff credential"],
];

function files(): string[] {
  const out: string[] = [];
  const walk = (d: string) => {
    if (!fs.existsSync(d)) return;
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      const full = path.join(d, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (/\.(ts|tsx|mjs|js)$/.test(entry.name)) out.push(full);
    }
  };
  ROOTS.forEach(walk);
  return out;
}

describe("no Streamlit path remains in the web app", () => {
  it.each(FORBIDDEN)("no source file matches %s", (pattern, why) => {
    const offenders = files().filter((f) => pattern.test(fs.readFileSync(f, "utf8")));
    expect(offenders, `${why}: ${offenders.join(", ")}`).toEqual([]);
  });

  it("password reset no longer touches the dropped handoff table", () => {
    const source = fs.readFileSync(path.join(WEB, "lib/auth/password-reset.ts"), "utf8");
    expect(source).not.toMatch(/auth_handoffs|handoffsVoided/);
    const route = fs.readFileSync(path.join(WEB, "app/api/auth/reset-password/route.ts"), "utf8");
    expect(route).not.toMatch(/handoffs_voided/);
  });

  it("the handoff route and its helpers are gone", () => {
    for (const rel of [
      "app/api/auth/handoff/route.ts",
      "lib/auth/handoff.ts",
      "lib/security/app-origin.ts",
      "components/auto-submit.tsx",
    ]) {
      expect(fs.existsSync(path.join(WEB, rel)), rel).toBe(false);
    }
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run (from `web/`): `npx vitest run __tests__/post-login-routing.test.ts __tests__/no-streamlit-path.test.ts`
Expected: FAIL — TypeScript error on the missing `appSurface` field is not raised by Vitest, so the routing test fails on `"/continue"` being returned only once `appSurface` is absent (`undefined !== "nextjs"`), and every FORBIDDEN pattern reports offenders.

- [ ] **Step 3: Implement**

`web/lib/auth/session.ts` — remove the `appSurface` property and its doc comment from `WebsiteUser`, remove `app_surface: string;` from the row type, remove `u.app_surface` from the SELECT (line 108) and `appSurface: row.app_surface,` (line 121). Replace the three routing functions with:

```ts
/**
 * Where an authenticated user belongs right now.
 *
 * One function so login, onboarding and the old /continue link cannot
 * disagree. Streamlit is retired (Phase 10): after the email and onboarding
 * gates there is one destination.
 */
export function nextDestinationFor(user: WebsiteUser): "/verify-email" | "/onboarding" | "/app" {
  if (!emailGatePassed(user)) return "/verify-email";
  if (!user.onboardingCompleted) return "/onboarding";
  return "/app";
}

/** Whether the /app shell's layout lets this request through, or where it goes instead. */
export function appLayoutRedirect(user: WebsiteUser): "/verify-email" | "/onboarding" | null {
  if (!emailGatePassed(user)) return "/verify-email";
  if (!user.onboardingCompleted) return "/onboarding";
  return null;
}
```

`web/app/continue/page.tsx` — replace the whole file:

```tsx
import { headers } from "next/headers";
import { redirect } from "next/navigation";

import {
  authenticateSessionToken,
  nextDestinationFor,
  sessionTokenFromCookieHeader,
} from "@/lib/auth/session";

export const dynamic = "force-dynamic";

/**
 * Kept as a redirect only. Streamlit is retired (Phase 10); bookmarks and
 * already-sent emails that name /continue land where the account belongs.
 * Rendering this page issues nothing.
 */
export default async function ContinuePage() {
  const token = sessionTokenFromCookieHeader((await headers()).get("cookie"));
  const user = token ? await authenticateSessionToken(token) : null;
  if (!user) redirect("/login");
  redirect(nextDestinationFor(user));
}
```

`web/app/api/auth/login/route.ts:84` → `const next = result.onboardingCompleted ? "/app" : "/onboarding";` (update the comment above it to say the app is the only destination). `web/app/api/auth/onboarding/route.ts:95` → `next: "/app"`. `web/app/onboarding/onboarding-form.tsx:94` → `router.push(payload.next ?? "/app");`. `web/app/app/layout.tsx:34-36` — replace the comment with `// Gates email and onboarding. Streamlit is retired, so there is no surface check.`

`web/lib/auth/password-reset.ts` — change the outcome type to `| { status: "reset"; userId: number; sessionsRevoked: number }`; delete the docstring paragraph beginning "Outstanding handoffs are voided for the same reason"; delete the `auth_handoffs` comment and `UPDATE auth_handoffs … RETURNING id` statement (lines 262-271); return `{ status: "reset" as const, userId: row.user_id, sessionsRevoked: sessions.length }`. Session revocation stays exactly as it is. `web/app/api/auth/reset-password/route.ts:87` — delete the `handoffs_voided: outcome.handoffsVoided,` line. `web/__tests__/password-reset.test.ts` — replace the `toContain("UPDATE auth_handoffs SET consumed_at")` expectation at line 338 with `expect(joined).not.toContain("auth_handoffs")` and keep the `auth_sessions` revocation assertions at line 350 unchanged. Reword the comments in `lib/mail/messages.ts`, `lib/auth/verification.ts`, `lib/auth/login.ts` and `app/login/login-form.tsx` so they no longer name Streamlit, `APP_ORIGIN` or `auth_handoffs` (meaning otherwise unchanged).

Delete the six files listed above. In `web/lib/auth/domains.ts` delete the `STREAMLIT_DOMAIN` and `SURFACE_STREAMLIT` exports and their comments. In `web/lib/env.ts` change line 38 to `const PUBLIC_SAFE_NAMES = ["SITE_ORIGIN", "SIGNUP_MODE"] as const;`. In `web/scripts/build-marketing.mjs` remove `APP_TOKEN` and the `APP_ORIGIN` validation, and make the CTA token resolve to `${SITE_ORIGIN}/login`; update `site/main.js`'s header comment to say the CTA goes to the website's `/login`.

Then run the full web suite and fix each failing test by **removing only its Streamlit/handoff assertions** (the `appSurface` fixture field, `/continue` expectations → `/app`, `APP_ORIGIN` env stubs). Web tests that referenced the retired path (2026-09-14 list): `analytics-page`, `analytics-relay`, `app-surface-routing` (deleted — superseded), `build-marketing`, `handoff` (deleted), `journal-page-auth`, `login-route`, `mail`, `new-trade-create-route`, `new-trade-page-auth`, `origin-separation`, `overview-page-auth`, `partner-relay`, `password-reset`, `screenshot-relay-route`, `security`, `settings-page-load`, `settings-relay`, `signup-skips-onboarding`, `strategy-page`, `strategy-relay`, `trade-analysis-relay`, `trade-autofill-route`, `trade-detail-page-auth`, `trade-detail-route`, `trade-draft-route`, `trade-summary-route`. Record every deleted test title in `docs/superpowers/parity/2026-09-14-phase10-test-retirement-ledger.md` under "Web".

- [ ] **Step 4: Run**

Run (from `web/`): `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build` with `SITE_ORIGIN=http://localhost:3000 SUPPORT_EMAIL=support@tradelens.dev` (no `APP_ORIGIN`).
Expected: all green; the build succeeds **without** `APP_ORIGIN` set.

- [ ] **Step 5: Commit**

```bash
git add -A web site docs/superpowers/parity/2026-09-14-phase10-test-retirement-ledger.md
git commit -m "feat(cutover): web routes every account to the app; remove the Streamlit handoff path"
```

---

### Task X2: Remove the Python Streamlit auth path, handoff table and Streamlit sessions (requires T5)

**Files:**
- Delete: `src/tradelens/services/auth_exchange.py`, `src/tradelens/services/auth_handoff.py`
- Delete: `scripts/integration_step10.py` (imports `auth_handoff`, drives `issue_handoff`), `scripts/integration_step11.py` (reads and counts `auth_handoffs` rows) — both exist only to exercise the Streamlit handoff; ledger rows under "Python — Streamlit auth"
- Modify: `scripts/db_inventory.py:47` (`SITE_AUTH_TABLES` without `auth_handoffs`), `scripts/inspect_account.py:71,100` (drop the handoff count), `scripts/cleanup_dev_test_users.py:35,104` (drop `auth_handoffs` from both table lists)
- Modify: `src/tradelens/services/auth_sessions.py` (delete `STREAMLIT_DOMAIN`, `SURFACE_STREAMLIT`, `open_streamlit_session`, `restore_streamlit_session`, `revoke_streamlit_session`)
- Modify: `src/tradelens/db/models.py` (delete `AuthHandoff`; `ck_auth_sessions_surface` → `surface IN ('website')`)
- Modify: `src/tradelens/services/account.py` (remove `AuthHandoff` from `_OWNED_BY_USER` and its import)
- Create: `alembic/versions/j6k7l8m9n0o1_drop_streamlit_auth.py`
- Test: `tests/test_drop_streamlit_auth_migration.py`; update `tests/test_account_deletion_references.py`; delete Streamlit-only functions from `tests/test_auth_handoff_and_sessions.py`, `tests/test_credential_domains.py`, delete `tests/test_step10_handoff_exchange.py` (ledger entry for each)

**Interfaces:**
- Consumes: revision `i5j6k7l8m9n0`.
- Produces: revision `j6k7l8m9n0o1`; no `auth_handoffs` table; `auth_sessions.surface` accepts only `'website'`.

- [ ] **Step 1: Write the failing migration test**

`tests/test_drop_streamlit_auth_migration.py`:

```python
"""Streamlit sessions and handoffs are gone; the downgrade restores empty structure only."""

import os
import pathlib
import sqlite3
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _alembic(db, *args):
    env = dict(os.environ, DATABASE_URL="sqlite:///%s" % db)
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env,
                   capture_output=True, text=True, check=True)


def _tables(db):
    with sqlite3.connect(db) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _session_row(conn, surface, token_hash):
    conn.execute(
        "INSERT INTO auth_sessions (surface, token_hash, user_id, created_at, expires_at, last_seen_at) "
        "VALUES (?, ?, 1, '2026-01-01', '2026-01-02', '2026-01-01')",
        (surface, token_hash),
    )


def test_upgrade_deletes_streamlit_sessions_drops_handoffs_and_narrows_surface(tmp_path):
    db = tmp_path / "drop.db"
    _alembic(db, "upgrade", "i5j6k7l8m9n0")
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        _session_row(conn, "website", "a" * 64)
        _session_row(conn, "streamlit", "b" * 64)
    _alembic(db, "upgrade", "j6k7l8m9n0o1")
    assert "auth_handoffs" not in _tables(db)
    with sqlite3.connect(db) as conn:
        assert [r[0] for r in conn.execute("SELECT surface FROM auth_sessions")] == ["website"]
        conn.execute("PRAGMA foreign_keys=OFF")
        with pytest.raises(sqlite3.IntegrityError):
            _session_row(conn, "streamlit", "c" * 64)


def test_downgrade_recreates_empty_handoffs_and_the_wide_constraint(tmp_path):
    db = tmp_path / "drop.db"
    _alembic(db, "upgrade", "j6k7l8m9n0o1")
    _alembic(db, "downgrade", "i5j6k7l8m9n0")
    assert "auth_handoffs" in _tables(db)
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        _session_row(conn, "streamlit", "d" * 64)
        assert conn.execute("SELECT COUNT(*) FROM auth_handoffs").fetchone()[0] == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_drop_streamlit_auth_migration.py -v`
Expected: FAIL — `Can't locate revision identified by 'j6k7l8m9n0o1'`.

- [ ] **Step 3: Implement**

`alembic/versions/j6k7l8m9n0o1_drop_streamlit_auth.py`:

```python
"""Remove Streamlit sessions and handoff credentials (Phase 10, Group X2).

Runs only after the X1 web build — which issues no handoffs — is live.

downgrade() recreates `auth_handoffs` EMPTY and re-widens the surface
constraint. Deleted Streamlit sessions and handoffs are not restored: they
were credentials for a retired surface.

Revision ID: j6k7l8m9n0o1
Revises: i5j6k7l8m9n0
"""

import sqlalchemy as sa
from alembic import op

revision = "j6k7l8m9n0o1"
down_revision = "i5j6k7l8m9n0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM auth_sessions WHERE surface = 'streamlit'")
    with op.batch_alter_table("auth_sessions") as batch:
        batch.drop_constraint("ck_auth_sessions_surface", type_="check")
        batch.create_check_constraint("ck_auth_sessions_surface", "surface IN ('website')")
    op.drop_table("auth_handoffs")


def downgrade() -> None:
    op.create_table(
        "auth_handoffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_auth_handoffs_token_hash", "auth_handoffs", ["token_hash"], unique=True)
    op.create_index("ix_auth_handoffs_user_id", "auth_handoffs", ["user_id"])
    with op.batch_alter_table("auth_sessions") as batch:
        batch.drop_constraint("ck_auth_sessions_surface", type_="check")
        batch.create_check_constraint(
            "ck_auth_sessions_surface", "surface IN ('website', 'streamlit')"
        )
```

The downgrade's columns and index names match the migration that created the table, `alembic/versions/s9t0u1v2w3x4_add_site_auth_and_onboarding.py:112-124` (`ix_auth_handoffs_token_hash` unique, `ix_auth_handoffs_user_id`).

`db/models.py`: delete `class AuthHandoff` entirely; change the constraint to `"surface IN ('website')"` and the `surface` comment to "Only the website issues sessions; Streamlit was retired in Phase 10." `services/account.py`: remove `AuthHandoff` from the import and from `_OWNED_BY_USER`. `services/auth_sessions.py`: delete the Streamlit constants and three functions; keep every website function byte-for-byte. `git rm scripts/integration_step10.py scripts/integration_step11.py`. In `scripts/db_inventory.py` set `SITE_AUTH_TABLES = ("auth_sessions", "auth_attempts")`; in `scripts/inspect_account.py` delete the `("auth_handoffs", "handoffs")` entry and the `(SELECT count(*) FROM auth_handoffs) h,` column (and its printed field); in `scripts/cleanup_dev_test_users.py` delete `"auth_handoffs"` from both table lists, keeping the remaining order (children before `users`).

`tests/test_account_deletion_references.py`: the sweep asserts every table with a `user_id` column has a deletion decision — it passes once `auth_handoffs` is gone from the model; remove any explicit `auth_handoffs` parametrization.

Delete `tests/test_step10_handoff_exchange.py`. From `tests/test_auth_handoff_and_sessions.py` and `tests/test_credential_domains.py` delete only the functions that call a deleted function or the Streamlit domain; keep every website-session test. Record each deleted test id in the retirement ledger under "Python — Streamlit auth".

- [ ] **Step 4: Run**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_drop_streamlit_auth_migration.py tests/test_account_deletion_references.py tests/test_account_deletion.py tests/test_auth_handoff_and_sessions.py tests/test_credential_domains.py tests/test_website_session_restore.py -v`, then `python -c "import src.tradelens.api.app"` (imports cleanly), then `python -m py_compile scripts/db_inventory.py scripts/inspect_account.py scripts/cleanup_dev_test_users.py` and `grep -rn "auth_handoffs" src scripts --include="*.py"` (expected: only `src/tradelens/ui/` and the new migration), then the upgrade/downgrade drill from F1 Step 4.
Expected: all pass; one head `j6k7l8m9n0o1`. `ui/` still imports `auth_exchange` at this point — **`streamlit run` is expected to break from here on**; X4 deletes `ui/`. The X2 commit and the X4 commit ship in the same release.

- [ ] **Step 5: Commit**

```bash
git add -A src/tradelens/services src/tradelens/db alembic/versions tests docs/superpowers/parity
git commit -m "feat(cutover): drop Streamlit sessions and handoff credentials"
```

---

### Task X3: Drop `users.app_surface` (requires T6)

**Files:**
- Create: `alembic/versions/k7l8m9n0o1p2_drop_users_app_surface.py`
- Modify: `src/tradelens/db/models.py` (delete the column)
- Delete: `tests/test_app_surface_migration.py`, `tests/test_flip_app_surface_migration.py` (their subject no longer exists — ledger entries)
- Test: `tests/test_drop_app_surface_migration.py`

**Interfaces:**
- Consumes: revision `j6k7l8m9n0o1`.
- Produces: revision `k7l8m9n0o1p2` (new single head); `users` has no `app_surface`.

- [ ] **Step 1: Write the failing test**

```python
"""users.app_surface is gone; downgrade re-adds it defaulting to nextjs."""

import os
import pathlib
import sqlite3
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _alembic(db, *args):
    env = dict(os.environ, DATABASE_URL="sqlite:///%s" % db)
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env,
                   capture_output=True, text=True, check=True)


def _columns(db):
    with sqlite3.connect(db) as conn:
        return {r[1]: r for r in conn.execute("PRAGMA table_info(users)")}


def test_upgrade_drops_the_column(tmp_path):
    db = tmp_path / "col.db"
    _alembic(db, "upgrade", "k7l8m9n0o1p2")
    assert "app_surface" not in _columns(db)


def test_downgrade_re_adds_it_not_null_defaulting_to_nextjs(tmp_path):
    db = tmp_path / "col.db"
    _alembic(db, "upgrade", "k7l8m9n0o1p2")
    _alembic(db, "downgrade", "j6k7l8m9n0o1")
    column = _columns(db)["app_surface"]
    assert column[3] == 1  # NOT NULL
    assert column[4] in ("'nextjs'", "nextjs")


def test_no_model_or_live_code_mentions_the_column():
    src = ROOT / "src" / "tradelens"
    offenders = [p for p in src.rglob("*.py") if "app_surface" in p.read_text(encoding="utf-8")]
    assert offenders == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_drop_app_surface_migration.py -v`
Expected: FAIL — unknown revision; `models.py` still mentions `app_surface`.

- [ ] **Step 3: Implement**

```python
"""Drop users.app_surface — the cutover toggle (Phase 10, Group X3).

Runs only after the X1 web build — which no longer selects the column — is live.

downgrade() re-adds the column NOT NULL with DEFAULT 'nextjs'. Per-account values
are not restored; at Gate 2 every account was 'nextjs'.

Revision ID: k7l8m9n0o1p2
Revises: j6k7l8m9n0o1
"""

import sqlalchemy as sa
from alembic import op

revision = "k7l8m9n0o1p2"
down_revision = "j6k7l8m9n0o1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("app_surface")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("app_surface", sa.String(), nullable=False, server_default=sa.text("'nextjs'"))
        )
```

Delete the `app_surface` column and comment from `models.User`. `ui/components/auth.py` still references it via `getattr` — harmless and deleted in X4.

- [ ] **Step 4: Run**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_drop_app_surface_migration.py tests/test_drop_streamlit_auth_migration.py -v` (the last test in the new file will still fail on `ui/` until X4 — run it again after X4), then the F1 drill (upgrade head, downgrade -1 twice, upgrade head).
Expected: the two migration tests pass; one head `k7l8m9n0o1p2`.

- [ ] **Step 5: Commit**

```bash
git add -A alembic/versions src/tradelens/db/models.py tests docs/superpowers/parity
git commit -m "feat(cutover): drop the app_surface toggle"
```

---

### Task X4: Delete `src/tradelens/ui/` and retire the Streamlit-coupled tests (requires T7)

**Files:**
- Delete: `src/tradelens/ui/` (entire tree, including `pages/_archive/`)
- Delete: `tests/account_ui_check.py`, `tests/app_boot_check.py`, `tests/insights_regen_check.py`, `tests/insights_review_options_check.py`, `tests/journal_flow_check.py`, `tests/settings_flow_check.py`, `tests/strategy_flow_check.py`
- Delete or migrate (per ledger): the Streamlit-coupled `tests/test_*.py` files
- Delete if T7 confirms: `src/tradelens/services/ai_screenshot_service.py`
- Create: `tests/test_no_streamlit_imports.py`
- Modify: `docs/superpowers/parity/2026-09-14-phase10-test-retirement-ledger.md`

**Interfaces:**
- Consumes: X1–X3 merged.
- Produces: no module under `src/`, `tests/` or `scripts/` imports `streamlit`, `plotly`, `pyarrow` or `src.tradelens.ui`.

- [ ] **Step 1: Write the failing guard**

`tests/test_no_streamlit_imports.py`:

```python
"""Streamlit is retired: nothing imports it, its chart stack, or the deleted ui package."""

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
FORBIDDEN = ("streamlit", "plotly", "pyarrow", "src.tradelens.ui")


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_no_python_file_imports_a_retired_module():
    offenders = []
    for folder in ("src", "tests", "scripts"):
        for path in (ROOT / folder).rglob("*.py"):
            for name in _imports(path):
                if any(name == f or name.startswith(f + ".") for f in FORBIDDEN):
                    offenders.append("%s: %s" % (path.relative_to(ROOT), name))
    assert offenders == []


def test_the_ui_package_is_gone():
    assert not (ROOT / "src" / "tradelens" / "ui").exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_no_streamlit_imports.py -v`
Expected: FAIL — hundreds of offenders; `ui/` exists.

- [ ] **Step 3: Build the retirement ledger before deleting anything**

For every file reported by Step 2 under `tests/`, open it and classify **each test function**:
- **retire** — asserts Streamlit behaviour (AppTest reruns, widget keys, page source, CSS selectors, `ui/` rendering). Record `file::function — reason`.
- **migrate** — asserts a service/DB/API behaviour and touches `ui/` only through an import or a re-export. Rewrite the import to the service module (e.g. a `ui.components.X` re-export of `services.sample_policy` → import `services.sample_policy`) and keep the assertion byte-for-byte. Record `file::function — migrated import from <old> to <new>`.

The ledger file gets these sections: *Summary* (files deleted, files migrated, functions retired, functions migrated, before/after `pytest --collect-only -q | tail -1`), *Known pre-existing failures retired, never fixed* (the three `test_pages_boot.py` ids from Scope, verbatim), *Web* (from X1), *Python — Streamlit auth* (from X2), *Python — UI* (this task), one row per function.

Start from the 2026-09-14 survey (verify each — it is keyword-based): MIXED files to migrate carefully: `test_activation.py`, `test_api_trades.py`, `test_app_surface_migration.py` (deleted in X3), `test_auth_handoff_and_sessions.py` (X2), `test_auth_screen.py`, `test_capture_app_screenshots.py`, `test_capture_cleanup.py`, `test_cost.py`, `test_credential_domains.py` (X2), `test_database_url_containment.py`, `test_partner_context.py`, `test_sample_policy.py`, `test_source_probe.py`, `test_strategy_first_run.py`, `test_trade_autofill.py`, `test_user_isolation.py`, `test_website_session_restore.py`. Module-level-only importers with few or no UI functions (migrate, do not delete wholesale): `test_account_ui.py` (0/7), `test_ai_autofill_review.py` (0/44), `test_ai_review.py` (0/4), `test_auth_logging_audit.py` (0/7), `test_auth_signup.py` (0/8), `test_cold_start.py` (0/2), `test_data_state.py` (0/21), `test_phase4_motion.py` (0/23), `test_policy_pages.py` (0/17), `test_site_trust_links.py` (0/6), `test_toast_icons.py` (0/2).

- [ ] **Step 4: Delete and migrate**

```bash
git rm -r src/tradelens/ui
```

```bash
git rm tests/account_ui_check.py tests/app_boot_check.py tests/insights_regen_check.py tests/insights_review_options_check.py tests/journal_flow_check.py tests/settings_flow_check.py tests/strategy_flow_check.py
```

Then apply the ledger: `git rm` each fully-retired file; edit each migrated file. For `ai_screenshot_service.py`, run `grep -rn "ai_screenshot_service" src scripts` — if only its own file matches, `git rm src/tradelens/services/ai_screenshot_service.py` and retire its tests with ledger rows; otherwise keep it and record why.

- [ ] **Step 5: Run**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_no_streamlit_imports.py tests/test_drop_app_surface_migration.py -v`, then `PYTHONDONTWRITEBYTECODE=1 pytest tests/ -q`, then `pytest tests/parity -q`, then `pytest --cov=src/tradelens/services --cov-fail-under=80 -q`.
Expected: guard tests pass; full suite has **zero failures** (the three pre-existing Streamlit boot failures are gone because their file is retired — record them as retired, never fixed); parity green with unchanged snapshots; services coverage ≥ 80%. If coverage falls below 80%, a retired file was carrying service assertions — move them back per Step 3 rather than lowering the gate.

- [ ] **Step 6: Commit**

```bash
git add -A src tests docs/superpowers/parity
git commit -m "feat(cutover): delete the Streamlit UI and retire its tests, with a per-function ledger"
```

---

### Task X5: Dependencies, runtime files, CI, docs and scripts

**Files:**
- Modify: `requirements.txt`, `requirements-dev.txt`, `tests/test_requirements.py`
- Delete: `runtime.txt`, `.streamlit/config.toml`, `.streamlit/secrets.toml.example`, `.streamlit/secrets.toml.template`
- Modify: `.github/workflows/ci.yml` (build-site step `APP_ORIGIN` removed if `build_site.py` no longer needs it), `scripts/build_site.py`, `scripts/env_audit.py`, `scripts/capture_app_screenshots.py`
- Modify: `README.md`, `PRODUCT.md`, `CLAUDE.md`

**Interfaces:**
- Produces: `requirements.txt` == the runtime set without Streamlit/PyArrow/Plotly; `tests/test_requirements.py` asserts their absence everywhere.

- [ ] **Step 1: Write the failing test** (replace the Streamlit-specific tests in `tests/test_requirements.py`)

Delete `test_pyarrow_is_pinned_to_ci_verified_version` and any assertion that Streamlit is present in `requirements.txt`; delete the pillow-split tests whose only justification is "Streamlit 1.50 requires pillow<12" (`test_dev_does_not_include_the_api_requirements_file`, `test_only_the_api_surface_takes_the_patched_pillow_line`) and record them in the ledger. Add:

```python
RETIRED = ("streamlit", "pyarrow", "plotly")


def test_no_requirements_file_installs_the_retired_presentation_stack():
    for label, text in (("requirements.txt", RUNTIME), ("requirements-dev.txt", DEV),
                        ("requirements-api.txt", API)):
        names = _dep_names(text)
        for dep in RETIRED:
            assert dep not in names, "%s still installs %s" % (label, dep)


def test_streamlit_cloud_runtime_files_are_gone():
    assert not (ROOT / "runtime.txt").exists()
    assert not (ROOT / ".streamlit").exists()
```

(`_dep_names` is the existing helper at `tests/test_requirements.py:49`.)

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_requirements.py -v`
Expected: FAIL — `requirements.txt still installs streamlit`; `runtime.txt` exists.

- [ ] **Step 3: Implement**

`requirements.txt`:

```text
# Shared runtime dependencies. The Streamlit surface was retired in Phase 10;
# the deployed services install requirements-api.txt.
-r requirements-base.txt
```

Remove `pillow==11.3.0` only if nothing outside `ui/` imports PIL at runtime from this set (`grep -rn "from PIL\|import PIL" src scripts`); if something does, keep the pin and record why. Make `requirements-dev.txt` still install the API packages the tests need (unchanged logic; drop comments that justify the Streamlit pillow split). `git rm runtime.txt` and `git rm -r .streamlit`.

Scripts: remove Streamlit URLs and handoff steps from `build_site.py`, `env_audit.py`, `capture_app_screenshots.py`. CI: remove `APP_ORIGIN` from the "Build marketing site" step if `build_site.py` no longer reads it.

Docs: in `README.md` and `PRODUCT.md` replace Streamlit run/deploy instructions with the Next.js + FastAPI ones already used in earlier phase handoffs (`web/` dev server, `uvicorn`/Docker API, worker). In `CLAUDE.md`: remove `streamlit run src/tradelens/ui/app.py`, the "UI | Streamlit (multi-page)" row (→ "UI | Next.js 16 App Router (web/)"), and "`st.secrets`" references (→ environment only); keep every other rule unchanged. `CLAUDE.md` is project instructions — show the owner the diff in the handoff.

- [ ] **Step 4: Run**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_requirements.py tests/test_public_funnel.py tests/test_site_metadata.py -v`; then in a fresh virtualenv `pip install -r requirements-dev.txt && PYTHONDONTWRITEBYTECODE=1 pytest tests/ -q`; `python -m scripts.build_site` with `SITE_ORIGIN=https://www.tradelensai.io SUPPORT_EMAIL=support@example.com`.
Expected: all green in an environment where Streamlit is **not installed** (`python -c "import streamlit"` raises `ModuleNotFoundError`).

- [ ] **Step 5: Commit**

```bash
git add -A requirements.txt requirements-dev.txt tests scripts .github README.md PRODUCT.md CLAUDE.md docs/superpowers/parity
git commit -m "chore(cutover): drop Streamlit, PyArrow and Plotly; Streamlit Cloud files, CI origin and docs"
```

---

### Task X6: Streamlit Cloud decommission runbook (requires T10; owner-executed)

**Files:**
- Create: `docs/superpowers/runbooks/phase10-streamlit-cloud-decommission.md`

- [ ] **Step 1:** Write the runbook with these steps, each with a checkbox and a "recorded by / date" field: (1) X1–X5 merged and deployed; production `alembic heads` shows `k7l8m9n0o1p2`; (2) Streamlit Cloud app analytics show no sessions for 7 consecutive days; (3) delete the Streamlit Cloud app; (4) delete its secrets in Streamlit Cloud; (5) rotate any credential that existed only in Streamlit Cloud secrets (list which, never their values); (6) confirm Vercel has no `APP_ORIGIN` environment variable left, or remove it; (7) confirm the old `*.streamlit.app` URL no longer serves the app; (8) `python scripts/verify_public_funnel.py --site <site> --app <app>` exits 0; (9) record the date in the handoff.
- [ ] **Step 2:** Commit: `git add docs/superpowers/runbooks/phase10-streamlit-cloud-decommission.md && git commit -m "docs(runbook): Streamlit Cloud decommission"`.

---

## Group E — verification, mutation battery, handoff

- [ ] **E1 Gates** at the tip (record exact numbers, never "green" without them): `pytest tests/ -q` (N passed / N skipped / N failed — any failure named); `pytest tests/parity -q`; coverage gate; ruff; black; alembic single head and the upgrade/downgrade drill; `web/`: vitest, tsc, eslint, build **without `APP_ORIGIN`**; OpenAPI + client regeneration leaves no diff; `npm audit --omit=dev --audit-level=high`; `pip-audit -r requirements-api.txt`.
- [ ] **E2 Mutation battery** (hardened harness and verdict controls from Execution process), at minimum:
  - F1: migration skips the `UPDATE`; default left `'streamlit'`; downgrade restores nothing.
  - X1: `nextDestinationFor` returns `/continue`; `appLayoutRedirect` re-adds a surface check; `/continue` renders a form instead of redirecting; `APP_ORIGIN` re-added to `PUBLIC_SAFE_NAMES`; handoff route file restored.
  - X2: `DELETE FROM auth_sessions WHERE surface = 'streamlit'` removed; constraint left wide; `AuthHandoff` left in `_OWNED_BY_USER`.
  - X3: downgrade default `'streamlit'`; column left in the model.
  - X4: one migrated service assertion reverted to import from a deleted `ui` path (must be ERROR, not CAUGHT — proves the controls); `test_no_streamlit_imports` FORBIDDEN list missing `plotly`.
  - R4: row updated before upload; owner filter removed from the screenshot query; `trade_id` prefix check removed; `http(s)` reference not skipped.
  - R2: `is_retired_app_host` suffix check removed.
- [ ] **E3 Review:** independent reviewer in a private extraction; deepest on X1–X3 deploy ordering and migrations, R4, and the retirement ledger (no service assertion lost — compare `pytest --collect-only` service test ids before and after).
- [ ] **E4 Handoff** section in `docs/coordination/CLAUDE_CODEX_HANDOFF.md`: commits; decisions T1–T10 as approved; Gate 1 and Gate 2 evidence with dates; the §11 eight criteria each with evidence or "owner-recorded on <date>"; deploy order actually followed; migration drill output; retirement ledger summary with before/after collected-test counts; the three pre-existing Streamlit boot failures **retired with the Streamlit UI, never fixed**; the three Phase 9 non-blocking hardening items (still open); hard pre-release gates (still open unless an owner-run result is recorded); battery table with verdict counts; what did NOT run (authenticated Playwright unless owner-run; production migrations; Streamlit Cloud decommission unless owner-recorded).

---

## Self-review (2026-09-14)

- **Spec coverage:** §7 phase 10 — flip default (F1), remove toggle (X1, X3), delete `ui/` (X4), retire UI tests (X4 + ledger), drop dependencies (X5), decommission Streamlit Cloud (X6). §3 — `_archive/` with `ui/` (X4); `STREAMLIT_DOMAIN` and `open/restore/revoke_streamlit_session` (X1, X2). §11 — 1 (R1, Gate 1, T1, T8), 2 (Gate 1, X4 Step 5), 3 (R3, T3, Gate 1), 4 (Gate 1), 5 and 6 (Gate 2), 7 (R4, T9, Gate 1), 8 (R2, Gate 1, X6). §10.1 (X4 migrate-not-delete, coverage gate). §10.2 (parity harness in every gate, snapshots frozen). §8 "no drop without a recorded decision" (R1 ledger, T2, T8).
- **Gap the spec does not cover:** AI Reviews was never scheduled in §7; surfaced as Entry blocker 1 and T1 rather than silently absorbed.
- **Placeholder scan:** the CI app origin `https://app.tradelensai.io` is a stated default the owner may replace (R2); R1's example Overview row paths are marked for replacement with the real files; every code step carries code.
- **Type consistency:** revisions chain `h4i5j6k7l8m9 → i5j6k7l8m9n0 → j6k7l8m9n0o1 → k7l8m9n0o1p2`; `nextDestinationFor`/`appLayoutRedirect` return types match between X1's implementation and `post-login-routing.test.ts`; `MigrationReport` fields match R4's tests and CLI.
