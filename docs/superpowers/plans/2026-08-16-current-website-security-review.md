# Current Website Security Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Independently verify and safely remediate reachable security and engineering defects in the completed Next.js marketing, authentication, protected-transition, and supporting deployment/database configuration.

**Architecture:** Treat the Next.js server as an untrusted public boundary and trace every route from request parsing through cookies, database operations, token issuance, and redirects. Preserve the marketing UI and leave the Streamlit journal and ongoing Streamlit-to-SaaS implementation untouched; only confirmed defects in the named website/auth boundary may change.

**Tech Stack:** Next.js App Router, TypeScript, Vitest, Neon PostgreSQL, Vercel, Node.js security tooling, Python/SQLAlchemy only where the website-to-protected-app handoff contract requires inspection.

**Spec:** User request dated 2026-08-16 and `docs/superpowers/specs/2026-08-10-site-hosted-auth-design.md`.

## Global Constraints

- Review only the completed customer-facing website and its authentication/supporting infrastructure.
- Do not modify the Streamlit journal or the ongoing Streamlit-to-Next.js/FastAPI migration.
- Preserve the marketing-site visual design.
- Verify every reported issue against reachable code and prefer root-cause fixes with focused regression tests.
- Leave unrelated worktree changes, including `.claude/settings.json`, untouched.
- Never expose environment values, credentials, raw cookies, or tokens in diagnostics or documentation.

---

### Task 1: Establish the review baseline

**Files:**
- Read: `AGENTS.md`
- Read: `CLAUDE.md`
- Read: `docs/coordination/CLAUDE_CODEX_HANDOFF.md`
- Read: `docs/superpowers/specs/2026-08-10-site-hosted-auth-design.md`
- Read: `web/package.json`

**Interfaces:**
- Consumes: repository instructions, git history, current tracked and untracked state.
- Produces: an exact in-scope file map and executable verification command list.

- [ ] **Step 1:** Record `git status --short`, the active branch, and relevant website/auth commits.
- [ ] **Step 2:** Enumerate `web/app/api`, `web/lib/auth`, `web/lib/security`, `web/lib/db`, Next/Vercel configuration, environment templates, and website auth tests.
- [ ] **Step 3:** Record environment variable names only and compare them with `.env.example`, `web/.env.example`, and Vercel documentation in the repository.
- [ ] **Step 4:** Run the unmodified web test, lint, typecheck, build, and package-audit commands from `web/package.json` to establish the baseline.

### Task 2: Audit public request and protected-session boundaries

**Files:**
- Read: `web/app/api/auth/**/route.ts`
- Read: `web/lib/auth/*.ts`
- Read: `web/lib/security/*.ts`
- Read: `web/lib/db/client.ts`
- Read: `web/app/{login,signup,onboarding,continue,verify-email,forgot-password,reset-password}/**/*`
- Read: `web/next.config.mjs`

**Interfaces:**
- Consumes: every public auth input, cookie, token, redirect, and database statement.
- Produces: confirmed findings with reachability, evidence, severity, and a reproducible regression case.

- [ ] **Step 1:** Trace signup, verification, login, onboarding, handoff, logout, password reset, resend, and protected-page decisions end to end.
- [ ] **Step 2:** Verify token entropy, hashing, TTL, single-use/revocation, cookie flags, session freshness, redirect allow-listing, CSRF posture, cache controls, and response/log leakage.
- [ ] **Step 3:** Verify all SQL is parameterized, user identity comes from the server session, ownership is enforced, rate limits are shared and fail safely, and no public endpoint returns private data.
- [ ] **Step 4:** Inspect client components for unsafe HTML, trust in client-supplied identity/state, browser-visible secrets, and private caching.

### Task 3: Audit deployment, environment, and dependency boundaries

**Files:**
- Read: `web/package.json`
- Read: `web/package-lock.json`
- Read: `web/.env.example`
- Read: `.env.example`
- Read: `web/next.config.mjs`
- Read: `.gitignore`
- Read: `web/.gitignore`
- Read: `.github/workflows/*`

**Interfaces:**
- Consumes: production/preview configuration, dependency graph, secret names, and build scripts.
- Produces: verified configuration and dependency findings without reading or printing secret values.

- [ ] **Step 1:** Compare environment keys used by server and client code with both templates and confirm no sensitive `NEXT_PUBLIC_*` values or browser imports.
- [ ] **Step 2:** Verify Vercel root/build behavior, host/origin validation, preview-versus-production separation, security headers, and static/private cache behavior.
- [ ] **Step 3:** Run `npm audit` for the production dependency graph and inspect each reported path for reachability before assigning severity.
- [ ] **Step 4:** Search tracked history and current files for credential-shaped assignments and accidental environment artifacts without printing matching values.

### Task 4: Remediate confirmed in-scope findings

**Files:**
- Modify only the exact website/auth/config files implicated by a confirmed finding.
- Test in the nearest existing `web/__tests__/*.test.ts` file or a focused new test file when no suitable test exists.

**Interfaces:**
- Consumes: a reproducible failing security or correctness case.
- Produces: the smallest root-cause fix that preserves the current UI and expected successful flows.

- [ ] **Step 1:** Read `superpowers:systematic-debugging` and `superpowers:test-driven-development` before the first fix.
- [ ] **Step 2:** Add a focused test that fails for the confirmed behavior and run it to capture the failure.
- [ ] **Step 3:** Implement the minimal root-cause correction without changing unrelated surfaces.
- [ ] **Step 4:** Run the focused test, adjacent auth tests, and inspect the targeted diff.
- [ ] **Step 5:** For security tests, temporarily reverse the fix or otherwise demonstrate that the test detects the original defect, then restore and rerun the correct implementation.

### Task 5: Verify, inspect, and hand off

**Files:**
- Modify: `docs/coordination/CLAUDE_CODEX_HANDOFF.md`
- Inspect: all review-created diffs.

**Interfaces:**
- Consumes: final code/tests, command output, and unresolved environmental limitations.
- Produces: durable Claude↔Codex notes and the user-facing severity-ordered review.

- [ ] **Step 1:** Run the complete web test suite, lint, typecheck, production build, dependency audit, `git diff --check`, and focused cross-language auth tests if their boundary changed.
- [ ] **Step 2:** Inspect `git diff --stat`, `git diff`, and `git status --short`; confirm `.claude/settings.json` and out-of-scope migration files were not altered by this review.
- [ ] **Step 3:** Update the handoff with findings, fixes, exact verification results, remaining risks, and SaaS-migration recommendations.
- [ ] **Step 4:** Re-run documentation/diff checks after the handoff update and report Critical → High → Medium → Low → Hardening, explicitly saying when an area had no meaningful finding.
