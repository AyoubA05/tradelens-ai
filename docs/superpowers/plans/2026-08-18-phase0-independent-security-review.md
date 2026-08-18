# Phase 0 Independent Security & Engineering Review Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this audit inline. The repository's active instructions prohibit subagent delegation for this review.

**Goal:** Independently verify the security and engineering properties of Phase 0 at commit `7eedb52`, fix only reproduced Phase 0 defects, and decide whether Phase 0 is safe to release into Phase 1 planning.

**Architecture:** Treat the Next.js signer/client, public FastAPI service, shared Neon/Postgres database, R2 adapter, image normalizer, and AI-job worker as separate trust zones. Trace every credential and owner identifier across those zones, then use adversarial differential, concurrency, and boundary tests rather than relying on Claude's existing green suite.

**Tech Stack:** Next.js 16 · TypeScript · FastAPI · Pydantic v2 · SQLAlchemy 2 · PostgreSQL/SQLite · Alembic · boto3/R2 · Pillow · pytest · Vitest

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md`

## Global Constraints

- Review worktree: `/Users/ayoub/tradelens-ai/.claude/worktrees/phase0-foundations`, branch `worktree-phase0-foundations`, starting commit `7eedb52`.
- Do not begin or modify Phase 1 UI work.
- Preserve prompts, AI routing/model selection, Streamlit product behavior, and unrelated user changes.
- Never restore nullable-owner or shared/legacy tenant behavior.
- For each defect: reproduce first, write a regression test and observe RED, implement the root-cause fix, observe GREEN, then run proportionate full gates.
- Do not expose or print secret values while inspecting configuration.
- Update `docs/coordination/CLAUDE_CODEX_HANDOFF.md` with evidence, fixes, limitations, and the Phase 1 clearance decision.

---

### Task 1: Establish the exact Phase 0 implementation and baseline

**Files:** Phase 0 diff `c69d84b..7eedb52`, required docs, dependency manifests, CI and deployment manifests.

- [ ] Confirm the Phase 0 worktree is clean and the commit chain is based on `c69d84b`.
- [ ] Read the implementation, tests, migrations, generated contracts, and deployment files rather than relying on the handoff summary.
- [ ] Run focused Phase 0 tests once to establish an independent starting baseline.

### Task 2: Audit raw-session forwarding and the HMAC protocol

**Files:** `web/lib/api/sign.ts`, `web/lib/api/client.ts`, `src/tradelens/api/security.py`, `src/tradelens/api/deps.py`, signature vectors/generators/tests.

- [ ] Trace where the raw `tl_session` credential exists, can be logged, and can be replayed; compare its compromise blast radius and revocation behavior with a 60-second audience-bound internal credential.
- [ ] Independently enumerate canonical-query cases: duplicates, order, empty values, Unicode, percent-encoding case, malformed escapes, `+`/space, literal `?`, empty query, separators, path/query confusion, and noncanonical UTF-8.
- [ ] Build/run an independent cross-language differential probe and test current/previous secret rotation, time boundaries, method/path/body/query binding, and constant-time comparison structure.
- [ ] If a mismatch is found, add a minimal regression case, observe failure, fix both sides or the canonical contract at the root, and rerun the differential corpus.

### Task 3: Audit tenant isolation and website-session restoration

**Files:** all `src/tradelens/services/*.py`, `src/tradelens/api/**/*.py`, models/migrations, scripts reachable from production workflows, and ownership/session tests.

- [ ] Inventory every function that reads/writes user-owned trades, reviews, screenshots, jobs, corrections, CSV/sample data, costs, settings, strategies, and generated analyses.
- [ ] Search for nullable owners, missing ownership predicates, ID-only lookups, global/sentinel fallbacks, cross-owner duplicate checks, and API-reachable maintenance helpers.
- [ ] Trace `restore_website_session` as one database operation and adversarially test domain separation, revocation, expiry boundaries, inactivity, and a concurrent revoke-vs-restore race.
- [ ] Reproduce and fix any ownership/session defect with a targeted test before implementation.

### Task 4: Audit request-scoped correction context

**Files:** `src/tradelens/services/corrections.py`, `src/tradelens/api/deps.py`, `src/tradelens/services/ai_client.py`, context tests.

- [ ] Verify normal, exceptional, nested, explicit-owner, unset, async-task, and threadpool behavior.
- [ ] Confirm background work receives an explicit scope and an unset scope degrades to no corrections rather than a legacy/shared tenant.
- [ ] Add a real concurrent request/thread probe if existing tests only exercise one execution context.

### Task 5: Audit R2 and image normalization

**Files:** `src/tradelens/api/storage.py`, `src/tradelens/api/imaging.py`, screenshot models/services, R2 and image tests.

- [ ] Verify private-bucket assumptions are deployment requirements, keys are server-generated/owner-scoped, presign TTL/type controls match actual boto3 calls, and non-owner reads/deletes cannot be signed.
- [ ] Determine whether upload-size enforcement is complete between presigned PUT and normalization; trace whether unnormalized originals can reach display or AI.
- [ ] Adversarially test magic/type mismatches, corrupt containers, appended data/polyglots, EXIF, animated/multiframe files, extreme dimensions, decompression warnings/errors, and format-specific edge cases.
- [ ] Reproduce and fix any storage/image defect test-first.

### Task 6: Audit AI-job concurrency, idempotency, retry, and ownership

**Files:** `src/tradelens/api/jobs.py`, `worker.py`, `AIJob` model/migration, job tests.

- [ ] Trace enqueue, claim, complete, fail, and result-read boundaries.
- [ ] Run true concurrent enqueue/claim probes against PostgreSQL when an isolated test database is safely available; otherwise run the strongest local concurrent test and leave Postgres behavior explicitly unresolved.
- [ ] Verify duplicate requests cannot create duplicate rows/spend, a losing claimant retries another queued job rather than reporting an empty queue incorrectly, terminal jobs cannot be overwritten accidentally, and every read/result is owner-scoped.
- [ ] Reproduce and fix any job defect test-first.

### Task 7: Audit serialization, OpenAPI, migrations, and runtime boundary

**Files:** serializer/tests, generated OpenAPI/types/scripts/CI, both migrations/models, Dockerfile, Render manifest, requirements and environment docs.

- [ ] Test strict serialization of all finite/nonfinite numpy, pandas, Decimal, date/time/timezone, mapping-key, dataframe, and unknown-type cases; verify undefined financial values retain an explicit state where required by schemas.
- [ ] Regenerate OpenAPI and TypeScript types, diff them, and verify CI would fail on either schema or generated-client drift.
- [ ] Inspect upgrade/downgrade order, defaults, constraints, indexes, foreign keys, status values, and rollback hazards; confirm one Alembic head and exercise up/down/up locally.
- [ ] Inspect secret boundaries, production schema/docs/CORS/cache behavior, requirements split, non-root container execution, health exposure, and runtime commands.
- [ ] If Docker exists, build and smoke-test the API image; otherwise record this as an unresolved gate.

### Task 8: Final verification, diff inspection, and handoff

- [ ] Run all focused regressions plus the full Python, web, typecheck, lint, formatting, audit, Alembic, codegen, and build gates warranted by changed files.
- [ ] Inspect the complete diff from `7eedb52`, run `git diff --check`, and confirm no Phase 1 or unrelated files changed.
- [ ] Update the Claude↔Codex handoff with severity-ordered findings, the raw-session verdict, exact verification output, remaining limitations, and the Phase 1 clearance decision.
- [ ] Stop. Do not begin Phase 1.

