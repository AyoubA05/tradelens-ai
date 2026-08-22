# Phase 3 — Trades + Trade Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/app/journal` a real, filterable, paginated trade log and `/app/trades/[id]` a real trade record that can be read, edited, and deleted — the first write path across the FastAPI boundary.

**Architecture:** Three read endpoints and two write endpoints under the existing two-lock boundary. The list is offset-paginated and filtered entirely from URL state, so a filtered view is a shareable link. Mutations expose an explicit editable-field allowlist rather than the service's `**fields` passthrough, and carry an `expected_updated_at` so a stale tab cannot silently overwrite a newer edit. The AI summary of a filtered set runs through the Phase 0 `ai_jobs` queue — its first real consumer — because an AI call does not belong in a request cycle.

**Tech Stack:** FastAPI · Pydantic v2 · SQLAlchemy 2.x · pandas (existing metrics) · Next.js 16 App Router (RSC + client islands) · TypeScript · Tailwind · Cloudflare R2 presigned URLs · pytest · Vitest

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md` (§7 phase 3, §8 Journal/Trades inventory, §2.2 request lifecycle, §4 tenant isolation)

## Global Constraints

- **The Phase 0 security architecture is untouchable.** Domain-separated `X-TL-Session-Handle`, the HMAC boundary and its canonical-query contract, mandatory service-layer ownership, the R2 quarantine/finalization model, generated OpenAPI/TypeScript contract gates.
- **The owner comes from the session row and nowhere else.** Never a header, query parameter, path segment, or body field.
- **Every page validates its own authorization.** Established by the Codex Phase 2 review: Next renders a page concurrently with its layout, so a parent layout is redirect defence, **not** a precondition for child data access. Every new route in this phase calls `appLayoutRedirect()` itself before fetching.
- **Undefined is not zero.** Figures a sample cannot support cross as `{"value": null, "state": "..."}`. Missing P&L is `undefined_incomplete_sample`; a recorded `0.0` is a legitimate zero.
- **Nothing distinguishes outcome by colour alone.** The positive/negative tokens measure ΔE 2.3 apart under deuteranopia. Every outcome carries a word, a shape, or a sign in text.
- TradeLens is a **post-trade reflection journal**. Never a signal app, a bot, or financial advice. This binds every label, empty state, error string and tooltip.
- **No new npm dependencies.**
- Python 3.9.6 floor: `from __future__ import annotations`, `Optional[X]`/`List[X]`/`Dict[K,V]`, never `X | Y`.
- No Streamlit imports in `services/`, `db/`, or `src/tradelens/api/`.
- Alembic for every schema change, with `downgrade()` implemented.
- Gates: `pytest tests/ -q`; `ruff check src/ scripts/`; `black --check src/ scripts/ tests/`; in `web/`: `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build`.
- jest-dom is not global: new web test files need `import "@testing-library/jest-dom/vitest";` first.
- `npm run build` needs `APP_ORIGIN`, `SITE_ORIGIN`, `SUPPORT_EMAIL`.

---

## Execution process

Same shape as Phase 2, which worked: **groups**, not per-task review gates.

| Group | Review depth |
|---|---|
| A — service pagination, list and detail endpoints | **Deep.** Ownership, filter injection, pagination correctness. |
| B — mutations (PATCH, DELETE) | **Deepest in the phase.** First write path across the boundary. |
| C — trades list UI (filters, table, calendar) | Light at the group boundary. |
| D — trade detail UI (view, edit, delete, screenshot) | Light, **except** the delete-confirmation and edit-conflict interaction, which get real scrutiny. |
| E — AI summary of a filtered set | **Deep.** First `ai_jobs` consumer; prompt-injection surface. |
| F — verification, browser smoke pass, handoff | Final phase boundary. |

TDD the data contracts, the filter/pagination logic, and every mutation guard. Do not mutation-test routine presentation. **The browser smoke pass is a gate, not a formality** — in Phase 2 it caught a self-contradicting card that 982 passing tests certified.

---

## Design decisions

**1. Offset pagination, not cursor.** A trader's trade count is in the hundreds, not millions, and offset pagination makes page N a shareable URL. Cursors would buy consistency under concurrent inserts that this data does not experience. `limit` is capped server-side at 100 so a caller cannot request the whole table.

**2. The filter set is the URL, and the URL is signed.** All filters live in query parameters, which the HMAC already covers, so a filtered view is both shareable and tamper-evident. Journal stays on `PERIOD_SCOPED_ROUTES` and keeps `?from=&to=`; the additional filters (`asset`, `session`, `setup`, `result`) join them.

**3. Trade Detail ignores the period lens.** Established in Phase 1: never present two controls claiming the same temporal scope. A single trade has one date; a period selector on that page would mean nothing. `/app/trades/[id]` is not added to `PERIOD_SCOPED_ROUTES`.

**4. The PATCH body is an explicit allowlist, not the service's `**fields`.** `trade_service.update_trade` accepts every column except `id` and `user_id` — which is right for a trusted in-process caller and wrong for an HTTP boundary. Exposing it directly would let a caller write `trade_hash`, `is_sample`, `created_at`, or `strategy_id`. The Pydantic model names the editable fields, and `extra="forbid"` rejects the rest.

**5. Edits carry `expected_updated_at`.** Inline editing on a page a trader may have left open invites the lost-update problem: two tabs, both stale, last write wins silently. The PATCH requires the `updated_at` the client last saw, and returns `409` when it no longer matches. This is cheap now and impossible to retrofit once clients exist.

**6. Screenshots are presigned directly to R2, never proxied.** `presign_download(user_id, screenshot_id)` already resolves ownership through the trade and returns `None` rather than raising, so a missing object and someone else's object are indistinguishable. The URL is short-lived and the browser fetches R2 directly — proxying image bytes through Next.js would put a per-image serverless invocation on every page view.

**7. The AI summary runs asynchronously through `ai_jobs`.** Phase 0 built the queue and nothing has used it. A Claude call over a filtered trade set takes many seconds — too long for a request cycle and far too long for a serverless function budget. Phase 3 enqueues, returns a job id, and polls. This also makes the summary idempotent per filter set, so a double-click does not buy two AI calls.

**8. The summary's inputs are data, never instructions.** A trade's `notes`, `mistake_tags` and `trade_process_notes` are user-authored free text that will be embedded in a prompt. They are the trader's own words, so this is not a cross-tenant injection risk — but the prompt must still frame them as quoted data, and the summary must never be allowed to produce a trade idea or a market opinion.

## Risks

**The first write path is the largest new attack surface in the project.** Mitigation: the HMAC already covers `sha256(body)`, so body integrity is signed; ownership is enforced in the service (`update_trade`/`delete_trade` both filter on `user_id`); the allowlist bounds what can be written; and every mutation test asserts a second owner's trade is untouchable.

**Deleting a trade cascades to screenshots.** `Screenshot` has `ondelete="CASCADE"` on `trade_id` — the database row goes, but the **R2 object does not**. Mitigation: the delete endpoint removes the stored objects before the row, and the plan tests that path explicitly. An orphaned object is a privacy tail, not just tidiness.

**`Screenshot` has no `user_id`.** Ownership flows only through `trade_id → trades.user_id`. Every screenshot path must join through the trade; none may query screenshots by id alone.

**Pagination plus filtering plus a total count is where off-by-one bugs live.** Mitigation: the count and the page come from the same filter construction, and the tests pin boundaries (page 0, last page, a page beyond the end, and a filter matching nothing).

---

## File Structure

**Python — new**

| File | Responsibility |
|---|---|
| `src/tradelens/api/schemas/trades.py` | Request/response models: list query, list response, detail, patch body. |
| `src/tradelens/api/routers/trades.py` | The five endpoints. Thin: validate, call the service with the session owner, return. |
| `src/tradelens/services/trade_summary.py` | Builds the AI summary of a filtered set. Pure of HTTP; the only new AI caller. |

**Python — modified**

| File | Change |
|---|---|
| `src/tradelens/services/trade_service.py` | Add `list_trades(...)` returning a page plus a total; leave `get_trades` untouched for existing callers. |
| `src/tradelens/api/storage.py` | Add `delete_trade_objects(user_id, trade_id)` so deletion does not orphan R2 objects. |
| `src/tradelens/api/app.py` | Register the trades router. |
| `src/tradelens/api/worker.py` | Register the `trade_summary` job handler. |

**TypeScript — new**

| File | Responsibility |
|---|---|
| `web/lib/app/trades.ts` | Server-only fetches: list, detail, patch, delete, summary enqueue/poll. |
| `web/lib/app/trade-filters.ts` | The URL filter contract — parse, serialise, and the allowlist of filterable fields. |
| `web/components/app/trades/filter-bar.tsx` | URL-state filter controls. |
| `web/components/app/trades/trades-table.tsx` | The table. |
| `web/components/app/trades/trades-calendar.tsx` | Month view with open-from-day. |
| `web/components/app/trades/pagination.tsx` | Page controls. |
| `web/components/app/trades/summary-panel.tsx` | AI summary of the filtered set, with its polling state. |
| `web/components/app/trade-detail/detail-header.tsx` | Date, asset, outcome, P&L. |
| `web/components/app/trade-detail/detail-fields.tsx` | The read view of every recorded field. |
| `web/components/app/trade-detail/edit-form.tsx` | Inline edit, including conflict handling. |
| `web/components/app/trade-detail/delete-dialog.tsx` | Delete with confirmation. |
| `web/components/app/trade-detail/screenshot-view.tsx` | Presigned screenshot display. |
| `web/app/app/trades/[id]/page.tsx` | The detail route. |
| `web/app/app/trades/[id]/loading.tsx`, `error.tsx` | Route boundaries. |

**TypeScript — modified**

| File | Change |
|---|---|
| `web/app/app/journal/page.tsx` | Becomes the real trades list. |
| `web/app/app/journal/loading.tsx`, `error.tsx` | Route boundaries (new). |

---

## Task list

Each group's tasks follow the same TDD shape used in Phase 2: write the failing test, run it and confirm it fails for the stated reason, implement, confirm it passes, commit.

### GROUP A — Service pagination and read endpoints *(deep review)*

**Task A1 — `list_trades` with filtering, pagination and a total.**
`src/tradelens/services/trade_service.py` gains:
```python
@dataclass
class TradePage:
    trades: List[Trade]
    total: int
    limit: int
    offset: int

def list_trades(
    *,
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    asset: Optional[str] = None,
    session: Optional[str] = None,
    setup_type: Optional[str] = None,
    result: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> TradePage:
```
`get_trades` is **not** modified — existing callers keep their contract. `require_user_id` first; every filter applied to both the count query and the page query from one shared construction, so they cannot diverge. `limit` clamped to `1..100`, `offset` clamped to `>= 0`. Ordered `trade_date desc, id desc` so the order is total and pagination is stable (the existing single-key ordering makes same-day ties non-deterministic — a real pagination bug, since a tie could appear on two pages or none).
Tests: a second owner's trades never appear; each filter narrows correctly; combined filters intersect; total counts the filtered set, not the page; page 0 / last page / beyond-the-end / a filter matching nothing; limit clamping at 0, 101 and −1; and a stable-order test that seeds three same-day trades and asserts no row appears twice across two pages.

**Task A2 — `GET /v1/trades`.**
Query: `from`, `to`, `asset`, `session`, `setup`, `result`, `limit`, `offset`. Reuse Phase 2's `_validated_period` shape (ISO regex pre-check, reversed-range and 5-year-window refusals) so the two endpoints agree about what a period is. Response `TradeListResponse` with `trades`, `total`, `limit`, `offset`, and `killzone` mapped through `services.sessions.KILLZONE_LABELS` — never the internal key, the mistake Codex caught in Phase 2. Pydantic `strict=True`, `extra="forbid"`, enum-likes as `Literal`, matching Phase 2's hardened contract.
Tests: unsigned → 401; no session → 401; tampered query → 401 (the HMAC covers it); another owner's rows never returned; invalid/reversed period → 422; `limit=1000` clamped not honoured; response not cacheable; the handler's return annotation is the typed model, asserted through the generated OpenAPI `$ref`.

**Task A3 — `GET /v1/trades/{id}`.**
Returns the full record plus screenshot descriptors, each with a short-lived presigned URL from `presign_download`. A trade belonging to someone else returns **404, not 403** — a 403 confirms the row exists.
Tests: own trade returns; another owner's id returns 404; a non-existent id returns 404 and is byte-identical to the cross-owner response; screenshots resolve only through the trade; no presigned URL is issued for a trade the caller does not own.

### GROUP B — Mutations *(deepest review in the phase)*

**Task B1 — `PATCH /v1/trades/{id}`.**
Body model names only the editable fields — `trade_date`, `asset`, `session`, `setup_type`, `timeframe`, `direction`, `result`, `pnl`, `rr_realized`, `risk_amount`, `followed_rules`, `killzone`, `htf_bias`, `notes`, `mistake_tags` — plus a required `expected_updated_at`. `extra="forbid"` rejects everything else, so `trade_hash`, `is_sample`, `created_at`, `strategy_id`, `id` and `user_id` are unreachable. On a stale `expected_updated_at`, return `409` with the current value so the client can show what changed.
Tests: each editable field round-trips; `user_id` in the body is rejected by `extra="forbid"`; `trade_hash` likewise; another owner's trade returns 404 and is not modified (assert the row afterwards); a stale `expected_updated_at` returns 409 and leaves the row untouched; editing `pnl` re-derives `result` through `canonical_outcome`; an unsigned or body-tampered request fails Lock 1 (the HMAC covers `sha256(body)`).

**Task B2 — `DELETE /v1/trades/{id}`.**
Removes stored R2 objects **before** the row, via a new `storage.delete_trade_objects(user_id, trade_id)`, then calls `delete_trade`. Deleting an already-deleted trade returns 404, not 500.
Tests: own trade is removed and returns 204; another owner's trade returns 404 and the row survives (assert it afterwards); screenshots' R2 objects are deleted, proven with a stubbed client that records calls; the DB rows cascade; a second delete returns 404; an unsigned request fails Lock 1.

### GROUP C — Trades list UI *(light review)*

**Task C1 — the URL filter contract.** `web/lib/app/trade-filters.ts`: an exact allowlist of filterable fields, `parseFilters(params)` / `filtersToParams(filters)`, and round-trip tests including unknown parameters being dropped rather than forwarded.
**Task C2 — filter bar and table.** Filters write to the URL (no client state of record); the table shows date, asset, session, setup, result, P&L, R, grade and a screenshot indicator. Outcome is a word in its own column. Missing P&L reads "not recorded", never `$0.00`. Empty state invites logging a trade.
**Task C3 — calendar month view with open-from-day.** Reuses Phase 2's shape encoding — filled circle for a winning day, square for a losing day, dash for flat, diamond for P&L not recorded — and its out-of-window treatment. A day with trades links into the filtered list for that day.
**Task C4 — pagination controls and the journal page.** The page validates auth itself per the Global Constraints, fetches once server-side, and renders. Plus `loading.tsx` and `error.tsx` that leak no backend message.

### GROUP D — Trade Detail UI *(light review, except edit-conflict and delete)*

**Task D1 — the detail route.** `/app/trades/[id]`, auth-validated in the page, 404 rendered as a real not-found rather than an error boundary. Not added to `PERIOD_SCOPED_ROUTES`.
**Task D2 — the read view.** Header plus every recorded field, with unrecorded fields shown as unrecorded rather than blank or zero.
**Task D3 — inline edit.** Sends `expected_updated_at`; on 409 shows what changed and offers to reload rather than silently discarding either version. This interaction gets real review.
**Task D4 — delete with confirmation.** A modal reusing Phase 1's `useModalTrap` (focus trap, `inert` background, focus restoration). Requires an explicit confirm; states plainly that the trade and its screenshots are removed permanently. This gets real review.
**Task D5 — screenshot view.** Presigned URL, `loading="lazy"`, meaningful `alt`, and a graceful state when the object is missing or the URL has expired.

### GROUP E — AI summary of a filtered set *(deep review)*

**Task E1 — `services/trade_summary.py`.** Builds the summary from a filtered `TradePage`, calling `ai_client.chat()`. `DEMO_MODE=true` returns cached output so tests spend nothing. The prompt frames trader-authored text as quoted data and forbids trade ideas, predictions and market opinions. Refuses to summarise a sample too small to support one.
**Task E2 — enqueue and poll endpoints.** `POST /v1/trades/summary` enqueues via `api.jobs.enqueue` with an idempotency key derived from owner plus the canonical filter set, so a double-click does not buy two AI calls; `GET /v1/trades/summary/{job_id}` returns status or result, and **404s a job belonging to another owner**. Register the handler in the worker.
**Task E3 — the summary panel.** Requests, polls with backoff, renders, and degrades to a plain message when the job fails. Never blocks the table.

### GROUP F — Verification and handoff

**Task F1.** Full gates from a committed HEAD: Python suite, ruff, black, vitest, tsc, eslint, production build with every `/app` route confirmed `ƒ` dynamic, and the OpenAPI/TypeScript drift gate producing no diff. Then a **real browser smoke pass on a disposable Neon branch** (forked from dev, never production; deleted afterwards) covering: filtering by each field and by combinations; pagination boundaries; open-from-day; opening a trade; editing a field; the 409 conflict path with two stale tabs; deleting with confirmation; a screenshot rendering; the AI summary completing; and a second account proving isolation on both the list and the detail route. Record what was seen, update the handoff, and stop.

---

## Self-Review

**Spec coverage.** §7 phase 3 and §8's Journal/Trades inventory, item by item: date-range/asset/session/setup filters (C1, C2 — plus `result`, which §8's table column list implies) · trades table with date, asset, session, setup, result, P&L, R, grade, screenshot (C2) · calendar month view (C3) · open-from-day (C3) · trade detail (D1, D2) · AI summary of the filtered set (E1–E3) · edit (D3) · delete with confirmation (D4) · per-trade screenshot **upload** — **deliberately deferred**: upload belongs with New Trade in Phase 4, which owns the quarantine→finalize flow end to end; Phase 3 implements viewing only. That is the one §8 line this plan does not close, and it is recorded here rather than dropped silently.

**Placeholder scan.** No TBD/TODO. Each task names its files, its interface, and the specific properties its tests must prove. Task-level code blocks are given where the signature is the contract (A1); component tasks carry their behavioural requirements rather than invented markup, because Phase 2 showed brief-authored fixtures drifting from the generated schema — implementers must read the real types.

**Type consistency.** `TradePage{trades,total,limit,offset}` is produced in A1 and consumed by A2. `list_trades` keyword names match the query parameters in A2 (`setup_type` maps to the `setup` query parameter — noted explicitly so the two are not confused). `expected_updated_at` is named identically in B1 and D3. `KILLZONE_LABELS` is the single label source in A2 and C2. `presign_download(user_id, screenshot_id)` is used as-is in A3 and D5.

**Known scope risk.** This is a larger phase than Phase 2 — five endpoints, two of them mutating, plus the first async AI consumer. If a smaller merge is wanted, **Group E is the clean cut**: Groups A–D deliver a complete, usable Trades and Trade Detail experience on their own, and the AI summary can follow as Phase 3b without reopening anything.
