# Task 3 Implementer Report

## Status and commit

- Status: implemented, verified, and released for independent review.
- Starting HEAD: `11c1c32407ba77792dbdd0aa41be65ef6727416a`.
- Commit: this Task 3 commit, `fix(partner): make preview availability truthful`.
- Task 4 was not started. Nothing was pushed, merged, or deployed.

## Files

- `src/tradelens/ui/components/partner_turn.py`
- `src/tradelens/ui/components/partner_panel.py`
- `tests/test_partner_turn.py`
- `tests/test_partner_panel.py`
- `tests/test_pages_boot.py`
- `docs/coordination/CLAUDE_CODEX_HANDOFF.md`
- This report.

No authentication, AI service/routing/prompt, database/schema, tenant-isolation,
secret, dependency, marketing-site, or coordinator-owned SDD ledger file was
modified.

## Implementation

- Added `OWNERLESS_PREVIEW` with the truthful copy: `AI Partner is unavailable
  in this preview account.`
- Added `PartnerAvailability.show_launcher`, defaulting to `True` so owned
  states preserve their existing availability semantics.
- Ownerless, non-positive, string, and boolean user identifiers now return the
  preview state with `can_send=False` and `show_launcher=False` before context
  is inspected.
- `render_partner_launcher` resolves availability before creating the keyed
  launcher container. Ownerless preview sessions render nothing on desktop.
- Owned but unavailable states render one status and no redundant disabled
  launcher. Ready owned states retain the real actionable button.
- The dedicated Partner body renders `OWNERLESS_PREVIEW` exactly once and no
  composer.

## Red and green evidence

The first required red run was:

```text
pytest tests/test_partner_turn.py::test_ownerless_preview_never_reads_context_or_offers_a_launcher \
       tests/test_partner_panel.py::test_ownerless_preview_renders_no_dead_desktop_launcher -q
→ 2 failed
```

The failures were the intended ones: `PartnerAvailability` had no
`show_launcher`, and the ownerless launcher still emitted `Ask about a trade`.

The dedicated-page, status-only unavailable, and boot red run produced three
intended failures: missing `OWNERLESS_PREVIEW`, a still-rendered unavailable
button, and the old boot copy.

After implementation, the five new/changed behaviors passed together:

```text
5 passed in 1.75s
```

## Safety invariants

- `send_turn` still rejects every invalid owner before opening context and
  still stores/returns `NO_USER_ERROR`; its direct defense was not modified.
- Ownerless rendering does not call `build_global_partner_context`.
- Ownerless rendering exposes no composer, launcher button, model call, usage
  log, queue claim, or route action.
- Ready-owner, AI-unavailable, no-trade, no-profile, history, queue-expiry,
  cross-user isolation, sign-out cleanup, and account-deletion cleanup tests
  remain green.
- Service, prompt, model routing, cost logging, authentication, tenant query,
  and database boundaries were not edited.

## Mutation evidence

The production ownerless return was temporarily restored to its former state:

```python
return PartnerAvailability(can_send=False, reason=NO_USER_ERROR)
```

The three direct ownerless tests then failed independently:

- availability exposed `show_launcher=True`;
- desktop rendering exposed the old sign-in status;
- the dedicated page omitted `OWNERLESS_PREVIEW`.

Result: `3 failed`. The correct implementation was restored, and the same
tests returned `3 passed`.

## Commands and results

```text
python -m pytest tests/test_partner_turn.py tests/test_partner_panel.py tests/test_pages_boot.py -q
→ 190 passed in 62.73s

python -m pytest tests/test_partner.py tests/test_partner_context.py tests/test_auth.py tests/test_account_deletion.py -q
→ 88 passed in 1.71s

python -m ruff check <Task 3 source and test files>
→ All checks passed

python -m black --check <Task 3 source and test files>
→ 5 files would be left unchanged

git diff --check
→ clean
```

The final fresh verification is recorded in the handoff and commit boundary.

## Deviations

The brief's sample pure test monkeypatches context construction in
`partner_turn`, but the current architecture constructs context in
`partner_panel._availability`; `partner_turn.partner_availability` is purposely
Streamlit-free and consumes an already-built context. The pure test therefore
uses a context object that raises if read, while a rendered panel spy proves
the adapter receives zero calls. No duplicate or alternate context path was
introduced.

The existing ready-state `reason=None` contract was preserved rather than
changing it to an empty string; Task 3 only adds `show_launcher` and the preview
state.

## Concerns

No Task 3 code concern remains. The pre-existing owner-only deployment-secret
check remains open and unchanged; it does not block local remediation review.
