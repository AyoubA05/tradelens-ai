# Phase 2 Overview Independent Review Plan

> **Scope:** Review and, where proved necessary, repair Phase 2 Overview only. Do not begin Phase 3 or modify unrelated product surfaces.

## Review standard

- Treat the implementation, fixtures, generated clients, and green gates as untrusted until traced.
- Reproduce each defect with a test that fails for the identified reason before changing production code.
- Keep identity server-derived and every data access owner-scoped.
- Preserve the Phase 0 Next.js-to-FastAPI HMAC/session-handle boundary.
- Preserve undefined financial meaning instead of converting missing evidence to a plausible zero.
- Regenerate OpenAPI and TypeScript outputs after schema changes and run the drift gate.

## Task 1: Security and isolation

**Relevant files:**

- `src/tradelens/api/routers/overview.py`
- `src/tradelens/api/deps.py`
- `src/tradelens/services/overview.py`
- `web/lib/api/client.ts`
- `web/lib/app/overview.ts`
- `web/app/app/page.tsx`
- `tests/test_api_overview.py`
- `web/tests/lib/app/overview.test.ts`

1. Trace identity from the website cookie through the domain-separated handle and FastAPI dependency.
2. Trace every first- and second-hop query for period trades, lifetime trades, strategy, and reviews.
3. Add a two-user adversarial request containing common browser-supplied owner aliases and prove they cannot change the authenticated owner.
4. Verify HMAC signing uses the exact outgoing method, path, ordered query, and body.
5. Verify private responses are dynamic and `no-store, private`; inspect production artifacts for server-only values.

## Task 2: Metric and undefined-value correctness

**Relevant files:**

- `src/tradelens/services/overview.py`
- `src/tradelens/services/metrics.py`
- `src/tradelens/services/sample_policy.py`
- `tests/test_overview_service.py`
- `tests/parity/test_metrics_parity.py`

1. Compare Overview values to the existing metric functions with controlled owner-scoped data.
2. Add threshold cases around zero, one, three, four, and five trades.
3. Reproduce missing-P&L outcomes that currently yield confident zero-valued monetary metrics.
4. Require every null metric to carry an explicit undefined reason.
5. Replace the mirrored consistency threshold with one shared source of truth and prove changes cannot drift independently.
6. Verify today/week calculations use the owner timezone while selected-period metrics remain period-scoped.

## Task 3: Contract and fixture drift

**Relevant files:**

- `src/tradelens/api/schemas/overview.py`
- `docs/openapi.json`
- `web/lib/api/generated.ts`
- `tests/test_api_overview.py`
- `web/tests/components/app/overview/*.test.tsx`

1. Reproduce accepted missing fields, invalid literals, wrong nullability, and extra fields.
2. Make nullable fields required where the field itself is contractual.
3. Narrow enum-like strings and undefined states in Pydantic so generated TypeScript remains narrow.
4. Enforce `value`/`state` consistency for undefinable values.
5. Correct fixture assumptions using assertions against real service output, including killzone labels.
6. Regenerate OpenAPI and TypeScript and run the checked-in drift test.

## Task 4: Trust-affecting presentation

**Relevant files:**

- `web/components/app/overview/risk-discipline.tsx`
- `web/components/app/overview/equity-chart.tsx`
- corresponding component tests

1. Reproduce profitable rule-breaking being shown without a warning about non-repeatable behavior.
2. Reproduce a flat equity series rendering at the bottom instead of the neutral center.
3. Fix wording/geometry without changing the visual design.
4. Verify meaning is carried by text as well as color.

## Task 5: Verification and handoff

1. Run focused Python and Vitest regressions during each fix.
2. Run the relevant full Python suite, web suite, TypeScript, ESLint, Ruff, Black, OpenAPI drift, and production Next.js build.
3. Inspect generated/client bundles and route/cache output.
4. Review the final diff for accidental or unrelated changes.
5. Record findings, fixes, exact commands/results, limitations, and merge recommendation in `docs/coordination/CLAUDE_CODEX_HANDOFF.md`.
