# Task 4 Implementer Report

## Status and commit

- Status: implemented, verified, and released for independent review.
- Starting HEAD: `5f51ea7cd33f23da31ce4382f24f7712676ff260`.
- Commit: this Task 4 commit, `fix(strategy): align demo truth and simplify onboarding`.
- Task 5 was not started. Nothing was pushed, merged, or deployed.

## Files

- `src/tradelens/ui/components/sidebar.py`
- `src/tradelens/ui/pages/5_Strategy.py`
- `tests/strategy_flow_check.py`
- `tests/test_page_polish.py`
- `tests/test_premium_page_contracts.py`
- `tests/test_pages_boot.py`
- `docs/coordination/CLAUDE_CODEX_HANDOFF.md`
- This report.

No authentication, AI service/routing/prompt, database/schema, tenant-isolation,
secret, dependency, marketing-site, or coordinator-owned SDD ledger file was
modified.

## Implementation

- Ownerless demo mode with no stored profile now uses the shared
  `demo_strategy_profile()` fixture on the Strategy page and in the sidebar.
- The page reports the sample as complete and read-only, with no starter button,
  editable Strategy field, Save control, or reachable strategy persistence.
- The starter retains its ownerless disabled defense, and form submission still
  refuses a missing owner before `_write`.
- The sidebar renders `Sample strategy: ICT/SMC Day Trading`; stored profiles
  retain the existing `Active strategy` treatment.
- A real empty account retains the starter save as its single primary action.
  The revised help states that it saves immediately and every rule is editable
  afterward.
- Empty-account manual construction is inside one collapsed expander. Stored
  profiles render the same keyed form directly.
- `render_strategy_fields` owns the unchanged field declarations; keys,
  validation, `_write`, error slots, toast/rerun timing, and persistence fields
  are preserved.

## Red and green evidence

The first focused run produced three intended failures and one passing stored
profile baseline:

```text
test_strategy_page_and_sidebar_select_the_shared_demo_profile FAILED
test_ownerless_demo_is_complete_read_only_and_sidebar_coherent FAILED
test_real_empty_account_has_one_primary_and_collapsed_manual_route FAILED
test_stored_profile_maintenance_stays_direct_and_persistent PASSED
```

The failures named the missing demo selection/sample sidebar and the old
starter help/unwrapped onboarding form. After implementation, the four guards
passed together.

## Behavioral coverage

- The demo AppTest patches strategy persistence to raise if touched, boots with
  `user_id=None`, verifies the complete fixture and sidebar sample, and rejects
  starter/Save controls and editable Strategy fields.
- The real-empty AppTest verifies truthful zero completion, one primary starter
  action, exact save help, and one collapsed manual expander.
- The stored-profile AppTest edits one field, reads the database back, verifies
  all untouched fields, then proves the saved form is directly visible with its
  primary Save action.
- Existing starter persistence, blank-name refusal and correction, write-failure
  containment, completion, field preservation, motion, reduced-motion, 44px,
  shell, and page-boot contracts remain green.

## Mutation evidence

Three temporary production mutations were each killed:

1. Forcing `demo_preview` false failed the ownerless demo AppTest on missing
   `6 of 6 sections written`.
2. Reversing the `profile is None` form-shell condition failed both real-empty
   onboarding and stored maintenance AppTests.
3. Suppressing the sidebar demo badge branch failed the coherence AppTest on
   the missing `Sample strategy` presentation.

All mutations were restored before the final gates.

## Commands and results

```text
python -m pytest tests/test_page_polish.py tests/test_premium_page_contracts.py \
  tests/test_pages_boot.py tests/test_strategy.py tests/test_strategy_parsing.py -q
→ 322 passed in 83.90s

python -m pytest tests/test_premium_shell.py -q
→ 45 passed in 0.30s

python -m ruff check <Task 4 source, tests, and AppTest runner>
→ All checks passed

python -m black --check <Task 4 source, tests, and AppTest runner>
→ 6 files would be left unchanged

git diff --check
→ clean
```

Browser testing was intentionally omitted: for this bounded structural task,
AppTest directly proves rendered text, absent/present controls, button type,
collapsed state, direct form fields, sidebar markup, and database effects. The
existing CSS contracts preserve dark direction, responsive behavior, reduced
motion, and 44px disclosure targets.

## Concerns

No Task 4 code concern remains. The pre-existing owner-only deployment-secret
check remains open and unchanged; it does not block local remediation review.
