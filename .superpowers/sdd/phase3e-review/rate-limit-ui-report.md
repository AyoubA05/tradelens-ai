# AI Summary rate-limit UI fix — report

## Status
Done. Not committed (per instructions) — changes staged in the working tree only.

## Gates
- `npx vitest run` — PASS (64 files, 1221 tests)
- `npx tsc --noEmit` — PASS (no output)
- `npx eslint .` — PASS: 0 errors, 2 pre-existing warnings in `lib/app/modal-trap.ts` (unrelated, expected)
- `APP_ORIGIN=... SITE_ORIGIN=... SUPPORT_EMAIL=... npm run build` — PASS, compiled successfully, all routes generated including `/api/trades/summary` and `/api/trades/summary/[jobId]`

## Files changed
- `web/app/api/trades/summary/route.ts` — relay now special-cases a backend 429: reads `error.body.detail` off the `ApiError` and returns `{ ok: false, error: "rate_limited", detail: <backend message> }` at status 429. Every other status is untouched (`{ ok: false }` with the original status; 502 fallback for non-`ApiError` unchanged).
- `web/components/app/trades/summary-panel.tsx` — `generate()` now checks `queuedResponse.status === 429` before the generic `!ok` throw, parses the JSON body, and stores `payload.detail` (falling back to `RATE_LIMIT_FALLBACK_MESSAGE` if the body is missing/malformed) in new `rateLimitMessage` state, scoped to the selection the same way `error`/`result` already are. Render: while `currentRateLimitMessage` is set, the "Summarize"/"Try again" button is hidden entirely (no retry affordance that could only fail again) and a plain `role="status"` message shows the backend's own text instead of `FAILURE_MESSAGE`. Any other failure path is untouched — `currentError` still renders `FAILURE_MESSAGE` with `role="alert"` and the button still becomes "Try again".
- `web/__tests__/trade-summary-route.test.ts` — added two tests: 429 maps to the distinguishable body; every other status (tested with 500) keeps the opaque `{ ok: false }` body.
- `web/__tests__/trade-summary-panel.test.tsx` — added one test: a 429 enqueue response renders the backend's message via `role="status"`, no `role="alert"`, no "Try again"/"Summarize" button, and only one fetch call (no poll started). The pre-existing "degrades to a plain message without automatically retrying paid work" test already covers a non-429 failure keeping `FAILURE_MESSAGE` + enabled "Try again" button — unchanged and still passing, confirming no regression there.

## Exact copy a rate-limited trader now sees
Whatever the backend sent as `detail` on the 429 (per `src/tradelens/api/routers/trades.py`):

> "You've reached 20 AI summaries for today. New summaries are available again 24 hours after your earliest one. Summaries you've already generated are still available."

rendered plainly as a `role="status"` paragraph, replacing both the generic failure text and the retry button. If the backend body is ever missing/unparseable, the panel falls back to a client-side message of the same character:

> "You've reached today's limit for AI summaries. Summaries you've already generated are still available."

## Mutation confirmations
1. **Relay (route.ts)** — removed the `error.status === 429` branch (mutation reverted the 429 case back to the generic `{ ok: false }` body while keeping the 429 status). Ran `npx vitest run __tests__/trade-summary-route.test.ts`: the new "maps a backend 429..." test failed (`{ ok: false }` received vs. `{ ok: false, error: "rate_limited", detail: ... }` expected); the "keeps the opaque body for every other status" test still passed, confirming it's actually exercising the distinguishing branch. Restored the file, reran — all 7 tests in that file passed again.
2. **Panel (summary-panel.tsx)** — removed the `queuedResponse.status === 429` special-case block entirely (mutation makes a 429 fall through to the generic `!queuedResponse.ok` throw, i.e. the pre-fix behavior). Ran `npx vitest run __tests__/trade-summary-panel.test.tsx`: the new "shows the backend's rate-limit message..." test failed — `waitFor` timed out waiting for `role="status"` with the limit text; the DOM dump in the failure showed the generic `FAILURE_MESSAGE` under `role="alert"` and a "Try again" button, i.e. the old broken behavior. Restored the file, reran — all 7 tests passed again.
3. **Non-429 regression coverage** — no separate mutation needed: the existing "degrades to a plain message without automatically retrying paid work" test already asserts `FAILURE_MESSAGE` + enabled "Try again" for a non-429 (job `status: "failed"`) path, and it passed unchanged both before and after the above two mutations were applied/reverted, confirming the non-429 behavior was never touched by this fix.

## What was deliberately left alone
- Relay stays same-origin, no-store, `dynamic = "force-dynamic"`, and fails shut when `SITE_ORIGIN` is unset (untouched code paths, covered by existing tests that still pass).
- Owner scoping, `extra="forbid"`, delimiter escaping, terminal failed jobs, and the no-advice gate are backend concerns not touched by this change.
- No copy implies a market opinion or timing — the rate-limit message is purely about the trader's own summary quota and journal availability.
