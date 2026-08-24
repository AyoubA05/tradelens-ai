# Phase 3 Core Independent Review Plan

> **For agentic workers:** Execute this review inline. Do not delegate service files covered by `AGENTS.md`, do not start Phase 3E or Phase 4, and use test-first fix-forward commits for confirmed defects.

**Goal:** Independently verify and, where necessary, correct the security, ownership, concurrency, storage, and contract guarantees in the published Phase 3 core range `0830e5b..ccb9224`.

**Architecture:** Trace browser-visible behavior through Next.js Server Components and route handlers, the signed FastAPI boundary, owner-scoped services, SQL predicates, and R2 helpers. Every suspected defect must be reproduced against the real implementation; every correction must be protected by a regression that is also proven against the broken mutation.

**Tech Stack:** Next.js App Router, TypeScript/Vitest, FastAPI/Pydantic, SQLAlchemy, SQLite/PostgreSQL-compatible migrations, Cloudflare R2 adapter, pytest.

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md`

## Global Constraints

- Review only Phase 3 core Groups A–D; do not implement Phase 3E or Phase 4.
- Identity must come only from the authenticated website-session boundary.
- Preserve published history; fixes are new commits on `main`.
- Do not weaken ownership predicates, strict schemas, no-store behavior, or server-only boundaries.
- Do not modify files owned by unrelated agents unless a reproduced Phase 3 core defect requires it.

---

### Task 1: Map the published implementation

**Files:**
- Read: `AGENTS.md`
- Read: `docs/coordination/CLAUDE_CODEX_HANDOFF.md`
- Read: `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md`
- Read: `docs/superpowers/plans/2026-08-22-nextjs-migration-phase3-trades.md`
- Inspect: all paths changed in `0830e5b..ccb9224`

- [x] Read the complete Phase 3 history and aggregate diff.
- [x] Map each endpoint through authentication, router, schema, service query, storage operation, relay, and UI consumer.
- [x] Record existing tests for each security invariant and identify tests that assert echoes or mocks instead of observable behavior.

### Task 2: Attack ownership and HTTP write boundaries

**Files:**
- Inspect: `src/tradelens/api/routers/trades.py`
- Inspect: `src/tradelens/api/schemas/trades.py`
- Inspect: `src/tradelens/services/trade_service.py`
- Test: `tests/test_api_trades.py`
- Test: `tests/test_trade_service_list.py`

- [x] Use two owners for list, detail, PATCH, DELETE, screenshot signing, and cleanup.
- [x] Attempt direct-id substitution plus `user_id`, `uid`, `owner`, `accountId`, and screenshot key/id injection.
- [x] Mutate each service ownership predicate and confirm the relevant test fails.
- [x] Submit every server-owned/internal/unknown PATCH field and verify a 422 with no mutation.
- [x] Compare Pydantic, OpenAPI, generated TypeScript, and real service payloads for required fields and nullability.

### Task 3: Prove concurrency and timestamp integrity

**Files:**
- Inspect: `src/tradelens/api/routers/trades.py`
- Inspect: `src/tradelens/services/trade_service.py`
- Inspect: `alembic/versions/a7b8c9d0e1f2_backfill_trade_updated_at.py`
- Test: `tests/test_api_trades.py`
- Test: `tests/test_migrations.py`

- [x] Construct a deterministic stale-writer interleaving.
- [x] Mutate the conditional UPDATE into check-then-update and require the test to fail.
- [x] Remove owner scoping from the 404/409 re-read and require the test to fail.
- [x] Trace every current, imported, sample, and legacy creation path for nullable `updated_at`.
- [x] Verify migration upgrade/downgrade behavior and database-level nullability/default guarantees.

### Task 4: Prove R2 deletion and screenshot ownership

**Files:**
- Inspect: `src/tradelens/api/storage.py`
- Inspect: `src/tradelens/api/routers/trades.py`
- Inspect: `web/app/api/trades/[id]/route.ts`
- Inspect: `web/components/app/trade-detail/delete-trade-dialog.tsx`
- Test: `tests/test_api_storage.py`
- Test: `tests/test_api_trades.py`
- Test: `web/__tests__/trade-detail-route.test.ts`
- Test: `web/__tests__/delete-trade-dialog.test.tsx`

- [x] Use a syntactically valid foreign final key and prove no download URL or delete call is produced.
- [x] Mutate ownership joins and require the tests to fail.
- [x] Propagate a real storage failure through FastAPI, Next.js, and the dialog.
- [x] Mutate the relay to return a fabricated 204 and require a browser-visible test failure.
- [x] Characterize partial-delete and orphan consistency behavior.

### Task 5: Verify filters, pagination, round-trip, page auth, and relay wire behavior

**Files:**
- Inspect: `web/app/app/journal/page.tsx`
- Inspect: `web/app/app/trades/[id]/page.tsx`
- Inspect: `web/lib/app/trades.ts`
- Inspect: Phase 3 components and tests

- [x] Seed exact-match and wildcard filter adversaries; compare totals and rows.
- [x] Seed tied dates/ids and verify stable page boundaries and enforced row limits.
- [x] Test legacy lowercase results, unknown killzones, nullable fields, grades, and screenshots through read→PATCH.
- [x] Prove invalid and Streamlit-only sessions cannot trigger signed FastAPI calls from either page.
- [x] Inspect each relay test for handler-return assertions and mutate wire status/error propagation.

### Task 6: Fix confirmed defects using red-green mutation proof

- [x] Add the smallest regression that fails for the reproduced root cause.
- [x] Run it against the broken implementation and record the expected failure.
- [x] Apply the narrow production fix.
- [x] Run the focused regression and neighboring suite.
- [x] Reapply the broken mutation, prove failure, restore the fix, and prove green.
- [x] Commit each coherent correction as a new fix-forward commit on `main`.

### Task 7: Full verification and handoff

**Files:**
- Modify: `docs/coordination/CLAUDE_CODEX_HANDOFF.md`

- [x] Run the full Python suite, Phase 3 focused tests, Ruff, Black, Vitest, TypeScript, ESLint, production build, contract generation drift, and Alembic-head checks.
- [x] Inspect dynamic route output, no-store headers, dependency/security gates where available, and `git diff --check`.
- [x] Review the final diff and commit history for unrelated changes.
- [x] Classify every tracked carry-forward as safe to defer, required before Phase 3E, or required before deployment.
- [x] Update the handoff with exact evidence and stop without beginning Phase 3E.
