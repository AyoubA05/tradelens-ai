# Task 1 Review-Test Amendment — Fix Report

## Status

Implemented the Task 1 review findings as test-only behavioral protections.
No production defect was found, production code remains unchanged, and Task 2
was not started.

**Test-amendment commit:** `05dc3b0c90d682161568bc9115b25c2a68cd87ca`
(`test(demo): pin task one regression contracts`).

## Changed files

- `tests/test_demo.py`
  - Pins the no-argument `get_demo_df()` time boundary to today.
  - Pins the ordered, complete 32-field legacy demo row schema.
  - Pins the deterministic result distribution to 33 Wins, 21 Losses, and 6
    Breakevens.
- `tests/test_page_polish.py`
  - Exhaustively checks all 512 subsets of the nine persisted completion
    fields against an independently expressed six-section reference, with
    whitespace-only blank values.
  - Adds explicit Risk and Self-Awareness single-count assertions and covers
    the remaining non-completing Identity metadata fields.
- `docs/coordination/CLAUDE_CODEX_HANDOFF.md`
  - Records this review-test amendment and its verification evidence.
- `.superpowers/sdd/2026-08-09-dark-workspace-priority-remediation/task-1-fix-report.md`
  - This report.

No production, capture, dependency, database-schema, authentication,
AI-routing/prompt, tenant, secret, or marketing-site file changed. The
coordinator-owned SDD ledger was not edited.

## Passing evidence

Before mutation testing, the new focused assertions passed against the reviewed
implementation:

```text
pytest test_demo schema/distribution/default-date tests + completion matrix
7 passed in 0.76s

pytest completion matrix + targeted Risk/Self-Awareness + Identity metadata
5 passed in 0.31s
```

Final focused verification:

```text
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest \
  tests/test_demo.py tests/test_page_polish.py \
  tests/test_premium_page_contracts.py -q
239 passed in 15.71s

/Users/ayoub/tradelens-ai/.venv/bin/python -m ruff check \
  src/tradelens/services/demo.py \
  src/tradelens/ui/components/strategy_profile.py \
  src/tradelens/ui/pages/5_Strategy.py \
  scripts/capture_app_screenshots.py tests/test_demo.py \
  tests/test_page_polish.py tests/test_premium_page_contracts.py
All checks passed!

/Users/ayoub/tradelens-ai/.venv/bin/python -m black --check \
  src/tradelens/services/demo.py \
  src/tradelens/ui/components/strategy_profile.py \
  src/tradelens/ui/pages/5_Strategy.py \
  scripts/capture_app_screenshots.py tests/test_demo.py \
  tests/test_page_polish.py tests/test_premium_page_contracts.py
All done! 7 files would be left unchanged.

git diff --check
clean
```

Black initially identified one formatting-only issue in the new completion
test. Running Black on that test file resolved it; the final Black gate above
is clean.

## Mutation evidence

The production files were deliberately and temporarily mutated, then restored
unchanged before final verification.

1. The exact demo regression from the review was applied: no-argument calls
   anchored to `2026-08-24`, the seven omitted metadata fields
   (`day_of_week`, `asset_class`, `session`, `timeframe`, `strategy_used`,
   `setup_type`, and `updated_at`) were removed, and outcomes were collapsed to
   59 Wins / 1 Loss. The three corresponding new tests returned `FFF`:
   schema mismatch, result-count mismatch, and a maximum date later than
   `2026-08-09`.
2. The exact completion regression was applied: `risk_rules` was omitted and
   `common_mistakes` was counted twice. The exhaustive matrix and targeted
   Risk/Self-Awareness test returned `FF`: the matrix observed Self-Awareness
   as two sections, and the targeted assertion observed Risk as zero sections.

These failures prove the added tests reject the specific regressions identified
by independent review.

## Deviations

The amendment intentionally changes tests and required handoff/report records
only. It does not modify the specification-compliant implementation. The
test-amendment commit is separate from this documentation commit so this report
can record its immutable hash accurately.

## Concerns

No Task 1 implementation concern remains. The full repository suite and
browser verification were not repeated because this amendment is test-only and
does not change rendered behavior; the coordinator's fresh pre-amendment full
baseline was `2129 passed, 7 skipped`.
