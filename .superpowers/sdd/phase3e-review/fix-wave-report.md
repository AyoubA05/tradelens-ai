# Phase 3E review — fix wave

All five findings fixed. Every fix has a regression test that was confirmed to
fail against the pre-fix code by re-introducing the exact defect (mutation
listed per finding) and observing the new test fail.

## 1a — relay fail-shut on unset SITE_ORIGIN
`web/lib/app/trade-summary-relay.ts` unchanged (it was already correct); the
property was simply undefended. Added
`__tests__/trade-summary-route.test.ts` → "both relay routes with SITE_ORIGIN
unset": deletes `SITE_ORIGIN`, asserts 403 from both `POST /api/trades/summary`
and `GET /api/trades/summary/[jobId]`, and that neither the backend client nor
`authenticateSessionToken` was reached.
Mutation: `!siteOrigin || !isSameOriginRequest(...)` → `siteOrigin && !isSameOriginRequest(...)` → test fails.

## 1b — stale-selection render gate
`summary-panel.tsx` unchanged for this one. Added panel test "does not render a
summary resolved for a selection the trader has left": clicks generate under
filters A, holds the poll open, rerenders under filters B, then resolves the
poll with A's content and asserts none of it renders.
Mutation: `currentResult = stateIsCurrent ? result : null` → `currentResult = result` → test fails.

## 2 — usage recorded before validation
`generate_trade_summary` takes an `on_usage` callback, invoked the moment
`chat()` returns and before `_validate_markdown` / the advice gate can raise.
`worker.py` passes `log_ai_usage` through it and no longer logs after the save.
Failure stays terminal and still does not re-bill.
Tests: `tests/test_trade_summary.py::test_a_call_that_fails_validation_is_still_recorded_in_cost_tracking`
and `tests/test_api_trade_summary.py::test_worker_logs_spend_for_a_paid_call_whose_response_fails_validation`
(end-to-end: job ends `failed`, one `AIUsageLog` row at $0.50).
Mutation: remove the `on_usage(usage)` call → both fail.

## 3 — panel could strand a paid summary
Two changes in `summary-panel.tsx`:
- `finally` now clears loading on controller *identity* (`active.current === controller`)
  instead of `!controller.signal.aborted`. A filter change aborts without
  starting a replacement, so the old guard left that selection loading forever;
  identity still protects a run superseded by a newer `generate()`.
- The button renders on error too, labelled "Try again". Nothing retries
  automatically; the failure message still explains that this exact selection
  will not re-run on its own.
Tests: "leaves no permanently disabled button after filters move away and back"
(the A→B→A sequence) and the updated "degrades to a plain message without
automatically retrying paid work" (asserts an enabled "Try again" and exactly
two fetches).
Mutations: restore `!controller.signal.aborted` → A→B→A test fails; restore
`!currentError &&` on the button → the degrade test fails.

## 4 — central text bounding
`_safe_scalar` now truncates any `str` to `MAX_TEXT_CHARS`. Bounding lives in
the one function every `_SNAPSHOT_FIELDS` value passes through, so a field added
later is bounded by default rather than by remembering. `notes`,
`trade_process_notes` and mistake tags keep their existing explicit bounding.
Test: `test_every_snapshot_string_field_is_bounded_not_just_the_notes_columns`
— every string column set to 200k chars; asserts every string in the snapshot is
≤ 500 and the serialized snapshot stays under 40KB.
Mutation: drop the `isinstance(value, str)` branch → test fails.

## 5 — content-level no-advice gate
`_reject_forward_looking(content)` runs immediately after `_validate_markdown`,
raising the same terminal `TradeSummaryError`. It scans sentence by sentence.

**Rejects**
- A recommendation verb directly governing a position:
  `you should|must|need to|could`, `we/i recommend`, `consider`, `look(ing) to`,
  `aim/plan/prepare/be ready/wait to` immediately followed (optionally through
  `a|an|the|to|going`) by buy/sell/long/short/enter — "consider longs",
  "you should short the next open", "look to short below 4500".
- A future marker (`next session`, `tomorrow`, `going forward`, `next week`,
  `next open`, `upcoming session`, …) within ~60 chars of a directional word, in
  either order — "Going forward, sell into the London high."
- A price level paired with a directional word — "buy above 20150",
  "short below 4500" (`above|below|near|around|at|from|into|over|under` + digits).

**Deliberately does not catch / where the line is**
- Any directional word followed by a noun that describes an already-taken trade
  (`long entries`, `short setups`, `buy executions`, `long positions`, `short bias`)
  is never treated as a position. This is what keeps "long entries were late this
  week" and "Next session, note whether your long entries repeat this pattern"
  passing.
- SMC vocabulary is excluded by lookahead: `sell-side`, `buy-side`, `long-term`.
- `next time` is a reflection marker, not a future marker — "next time I will
  size smaller" passes.
- The **price-level** rule alone is skipped for sentences containing past-tense
  reflection markers (`was/were/had/did/should have/last week/…`), because a
  genuine retrospective can say "entries above 20150 were consistently late".
  The recommendation and future-marker rules are not relaxed this way — they are
  explicit enough that a past-tense word nearby should not excuse them.
- It is a lexical gate, not a classifier. A trade idea phrased with no
  directional verb, no price, and no future marker ("the discount array remains
  attractive") would pass. The system prompt remains the first defence; this is
  the catch, not a replacement.
Tests: `test_a_structurally_valid_trade_idea_is_rejected_before_it_reaches_the_trader`
(five perfect headings, Improvement Actions = "Consider longs above 20150 next
session") and `test_ordinary_past_tense_reflection_is_not_mistaken_for_trade_guidance`
(long entries / sell-side liquidity / entries above 20150 / next time / should
have — all pass through unchanged).
Mutation: remove the `_reject_forward_looking(content)` call → the rejection test fails.

## Gates
- `pytest tests/ -q` — 2784 passed, 7 skipped
- `ruff check src/ scripts/` — All checks passed
- `black --check src/ scripts/ tests/` — 280 files unchanged
- `npx vitest run` — 64 files, 1218 passed
- `npx tsc --noEmit` — clean
- `npx eslint .` — 0 errors, 2 pre-existing `modal-trap.ts` warnings
- `npm run build` — succeeded
- No schema change, so `openapi.json` / `schema.d.ts` are untouched.
