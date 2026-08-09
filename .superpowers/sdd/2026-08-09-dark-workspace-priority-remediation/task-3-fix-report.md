# Task 3 Review Amendment Report

## Status and commit

- Status: both review-proven P1 defects fixed and verified.
- Starting HEAD: `30c593295ba9a68f8610d19ca003dc261f88e327`.
- Commit: this amendment commit, `fix(partner): keep responsive availability truthful`.
- Task 4 was not started. Nothing was pushed, merged, or deployed.

## Changes

- Owned-unavailable launcher status remains inside the existing keyed
  `tl_partner_launcher` presentation. The phone CSS therefore removes the
  complete shell presentation, preventing duplication on `/Partner` and leaks
  onto other phone routes while preserving the desktop fixed launcher status.
- `render_partner_body` returns the `PartnerAvailability` it rendered.
  `/Partner` reuses that exact state for its desktop-route note:
  - ready owner: retains the real `Ask about a trade` instruction;
  - owned unavailable: emits no second desktop note because the keyed launcher
    status is already the visible desktop presentation;
  - ownerless preview: shows `OWNERLESS_PREVIEW` instead of pointing to a
    launcher that availability suppresses.
- Complementary width behavior is unchanged: page presentation at `<=767px`,
  launcher/drawer presentation at `>=768px`.

## TDD and mutation evidence

Five new tests failed against the starting code before production edits:

- fake-render scope showed the unavailable status at `()` rather than inside
  `("tl_partner_launcher",)`;
- the real owned-no-trades `/Partner` AppTest had no keyed launcher block;
- the launcher AST placed `render_partner_status` outside the keyed container;
- the real ownerless `/Partner` AppTest rendered the static nonexistent-launcher
  instruction;
- the page had no shared availability assignment/desktop renderer integration.

After the minimal implementation, all five passed. Mutation checks then proved
each correction:

- moving the status back outside the keyed container produced `3 failed` across
  the fake-render, AppTest, and AST protections;
- restoring the unconditional static desktop instruction made the ownerless
  AppTest fail because `OWNERLESS_PREVIEW` was absent and the launcher copy
  returned.

Both mutations were restored to the fixed implementation; the five focused
protections returned `5 passed`.

## Verification

```text
pytest tests/test_partner_turn.py tests/test_partner_panel.py tests/test_pages_boot.py -q
→ 195 passed in 63.80s

pytest tests/test_partner.py tests/test_partner_context.py tests/test_auth.py tests/test_account_deletion.py -q
→ 88 passed in 1.60s

ruff check src/tradelens/ui/components/partner_panel.py src/tradelens/ui/pages/7_Partner.py tests/test_partner_panel.py
→ All checks passed

black --check src/tradelens/ui/components/partner_panel.py src/tradelens/ui/pages/7_Partner.py tests/test_partner_panel.py
→ 3 files would be left unchanged

git diff --check
→ clean
```

The focused suites include the Partner responsive contracts, real page AppTests,
all page boots, ownerless zero-context/no-composer behavior, ready and unavailable
states, history/profile/no-trade paths, queue run/surface/expiry protections, and
hidden-surface spending protection. Adjacent suites preserve the direct send
fail-closed rule, usage boundary, tenant scoping, sign-out cleanup, account
deletion cleanup, and cross-user privacy.

## Scope and concerns

No AI service, AI client, prompt, routing, cost, authentication, database/schema,
tenant-isolation, secret, dependency, marketing, or coordinator-owned SDD ledger
file changed. No Task 3 code concern remains. The pre-existing owner-only deployed
legacy-secret check remains open and unchanged; it does not block this local
amendment.
