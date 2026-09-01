# Phase 4E — Autofill, Draft Autosave, Image-URL Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three New Trade items deferred from Phase 4 — AI autofill with per-field review, draft autosave, and image-URL ingest — by wiring services that already exist to the Next.js surface, without reopening Phase 4's form or its security model.

**Architecture:** URL ingest becomes a server-side fetch that lands bytes in the **existing R2 quarantine** and promotes them through the **existing `finalize_upload`**, so there is exactly one trusted image path and URL images inherit the decompression-bomb guard, dimension caps and re-encode they currently bypass. Autofill runs on the **finalized** image — the model only ever sees bytes we produced — and writes suggestions into a **draft**, never into `trades`. Drafts live in their own table with their own lifecycle, so an incomplete draft cannot become a journal entry by accident: it is not a trade row at all.

**Tech Stack:** FastAPI · Pydantic v2 · SQLAlchemy 2.x · Alembic · Pillow (existing `api/imaging.py`) · boto3 / Cloudflare R2 · Anthropic vision via `services/ai_client.py` · Next.js 16 App Router · TypeScript · pytest · Vitest

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md` (§7 phase 4, §8 New Trade)

## Global Constraints

- **Owner identity comes only from the authenticated session row.** Never a header, query, path segment, or body field.
- **No browser-controlled derived fields.** `session`, `killzone`, `strategy_used`, `day_of_week`, `rr_planned`, `rr_realized` and `trade_hash` are server-derived. Autofill produces *suggestions a human reviews*; it must not be able to set a derived field, and the create path's derivations stay exactly as Phase 4 left them.
- **The existing atomic duplicate/idempotency guarantees are unchanged.** `compute_trade_hash` remains the single notion of sameness; `POST /v1/trades` still returns the existing trade with `duplicate_of` rather than writing a second row. Nothing in this phase introduces a second creation path.
- **Screenshot quarantine → finalization remains the one trusted image path.** Every image byte that reaches the model or the bucket arrives through it. No temp-file side channel.
- **URL ingest must never become an SSRF path** and must never bypass image validation or normalization.
- **Autosave must never create a trade** and must never persist an incomplete draft as a real journal entry.
- **Autofill is assistive.** The trader reviews and can correct every value before creation. Nothing is written to `trades` without an explicit submit.
- Every protected page authenticates itself before any backend side effect; a parent layout is redirect defence, never a precondition.
- Next.js is the BFF: raw browser session credentials never reach FastAPI; only `sha256("tl.website.v1|" + token)` crosses. `TL_SERVICE_SECRET` never reaches the browser.
- Relays are same-origin, `no-store`, dynamic, and **fail shut when `SITE_ORIGIN` is unset**.
- Write schemas are positive allowlists with `extra="forbid"`.
- **404, never 403**, byte-identical to a genuine not-found, on every per-id route.
- TradeLens is a post-trade reflection journal. Never a signal app, a bot, or financial advice — this binds every label, placeholder and error string, and binds what the autofill model is allowed to produce.
- `src/tradelens/services/metrics.py` is parity-pinned. `prompts/` files are LOCKED — extend contracts, never rewrite.
- Alembic for every schema change, with a working `downgrade()`. **Head is `d0e1f2g3h4i5`** — the drafts migration chains off it.
- Python 3.9.6 floor: `from __future__ import annotations`, `Optional[X]`/`List[X]`, never `X | Y`.
- **No new npm dependencies.**
- Gates: `pytest tests/ -q`; `ruff check src/ scripts/`; `black --check src/ scripts/ tests/`; in `web/`: `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build`.

---

## Execution process

Groups, not per-task gates — the model that has worked since Phase 2.

| Group | Review depth |
|---|---|
| A — URL ingest through quarantine | **Deepest in the phase.** SSRF, and the only new way bytes enter the system. |
| B — drafts | **Deep.** A new table adjacent to `trades`; the "never a real entry" guarantee lives here. |
| C — autofill on the finalized image | **Deep.** Second AI consumer: cost, rate limit, prompt-injection surface, and the assistive boundary. |
| D — the review UI | Light at the group boundary. |
| E — verification and handoff | Final phase boundary. |

**Mutation-test every guard.** Across Phases 3, 3E and 4, **eleven** tests were proven to pass against deliberately broken code. Two shapes recur: asserting a value the implementation echoes back rather than an observable outcome, and being refused by a *downstream* gate so the guard under test is never exercised. Phase 4 added two more: a **shadowed test helper** that silently disabled assertions, and a test that **pinned the defect** as correct. For every guard: break it, confirm a *named* test fails, restore. A guard with no failing mutation is not defended.

---

## Scope

**In:** image-URL ingest, draft autosave, AI autofill with per-field review.

**Explicitly not in:** any redesign of the New Trade form (Phase 4's single dense form stands), and anything from Phase 5. Do not touch the form's layout, field set or validation beyond adding the review affordances Group D needs.

**Deployment gates tracked separately and NOT addressed here:** live two-account R2/browser smoke with real CORS and a real presigned PUT; Docker build/startup/health; broader Python dependency audit; Anthropic live smoke; real PostgreSQL verification; proper 375px browser verification. These are recorded in the handoff banner and stay open.

---

## What already exists — read before writing anything

This phase is mostly **wiring**, not building. Verified in the code:

- `services/vision.py`: `analyze_screenshot_v3(image_path, ...) -> tuple[dict, Usage]` and `check_screenshot_quality(image_path) -> ScreenshotQuality{usable, warnings}`.
- `services/ai_screenshot_service.py`: `is_image_url(url)`, `_is_public_url(url)`, `_download_image(url) -> Path`. The SSRF guard rejects loopback, private, link-local, reserved, unspecified and multicast, and `_OPENER` is built with a `_NoRedirect` handler — **redirects are already blocked**, which closes the redirect-to-metadata hole.
- `ui/components/ai_autofill_review.py`: `should_autocheck(field, confidence)`, `build_form_writes(...)`, `build_review_outcome(...)` — the per-field review logic Streamlit already uses. Reuse the pure decision functions; do not reimplement the confidence policy.
- `api/storage.py`: `presign_upload`, `finalize_upload`, `abandon_upload`, `_is_scoped_key`, `record_object_screenshot`.
- `api/imaging.py`: `validate_and_normalise(data) -> (bytes, content_type, w, h)`, with `MAX_UPLOAD_BYTES`, `MAX_PIXELS`, `MAX_DIMENSION`.
- `api/jobs.py`: the `ai_jobs` queue, and `count_recent_jobs` — the rate-limit primitive Phase 3E added.

## Design decisions

**1. URL ingest lands in quarantine and promotes through `finalize_upload`. It never writes a temp file.**
Today `_download_image` writes the fetched bytes to a `tempfile` and hands the path to `vision()`. Those bytes **never pass `imaging.validate_and_normalise`** — I checked; there is no reference to it anywhere in `ai_screenshot_service.py`. So a URL image today bypasses the decompression-bomb guard, the dimension caps and the re-encode that every uploaded image gets. That is precisely the bypass the owner's constraint forbids, and it is also how a malicious image would reach the vision model unmodified.

Phase 4E routes URL bytes into the same quarantine key the browser upload uses, then calls the same `finalize_upload`. One trusted path, and URL images inherit every guard for free.

**2. The SSRF re-check must close the rebinding window, not just narrow it.**
`_is_public_url` resolves the hostname and validates the IPs; `_download_image` re-checks it and then calls `urlopen(url)`, which **resolves DNS again independently**. Between those two resolutions a hostile DNS server can return a private address — classic rebinding, and the "defense-in-depth re-check" does not close it because the connection does its own lookup.

Resolve **once**, validate the resulting IP, and connect to **that IP** with the original `Host` header (and, for TLS, the original hostname for SNI/verification) — or, equivalently, validate the socket's actual peer address after connect and abort if it is not the address that was approved. Do not simply add a third call to `_is_public_url`; that repeats the mistake.

**3. Drafts are their own table, so a draft cannot accidentally be a journal entry.**
The strongest available guarantee is structural: an incomplete draft is not in `trades` at all, so no query, filter, metric or export can pick it up regardless of any flag anyone forgets to check. A `is_draft` column on `trades` would put the guarantee at the mercy of every future `WHERE` clause. One row per `(user_id, draft_id)`, owner-scoped like everything else.

**4. Autofill runs on the finalized image, never the upload.**
`finalize_upload` promotes freshly re-encoded bytes. Running analysis on those means the model only ever sees bytes **we** produced, so a crafted container cannot reach it. It also means autofill needs no image path of its own — it reads the promoted object.

**5. Autofill writes to the draft, never to `trades`, and never to a derived field.**
Suggestions land in the draft with their confidence. The trader accepts or corrects them; creation still goes through `POST /v1/trades` unchanged, where the allowlist, the fingerprint and the server-side derivations all still apply.

**Codex's Phase 4 review already removed the derived fields from the create allowlist** — it found `session`, `killzone`, `strategy_used` and `asset_class` were being *accepted from the browser* and persisted as forged values, and moved all four into `SERVER_OWNED_ON_CREATE`. `TradeCreate` now contains none of them (`CREATABLE_TRADE_FIELDS` is 31 fields). So the subtraction is already done upstream, and the test is simpler and stronger than originally written: **the autofill allowlist must be a subset of `CREATABLE_TRADE_FIELDS` and disjoint from `SERVER_OWNED_ON_CREATE`.** Pin both directions so neither can drift.

**Also unchanged by this phase, and now stronger than when this plan was drafted:** Codex found concurrent identical creates were *not* idempotent — `find_by_fingerprint` followed by an unconstrained INSERT, with a barrier reproducing two `201`s and two rows. There is now a server-owned `trades.create_idempotency_key` with a unique `(user_id, create_idempotency_key)` constraint (migration `d0e1f2g3h4i5`). Drafts and autofill must never touch that column, never create a trade, and never introduce a second creation path.

**6. Autofill is the phase's second AI consumer and gets Phase 3E's cost discipline.**
Owner-scoped rate limit before any billable call, usage recorded the instant the provider returns (before validation, so a failed parse is still billed-and-visible), and a failed job that stays terminal rather than silently re-spending. Reuse `api/jobs.count_recent_jobs` and the `ai_jobs` queue rather than inventing a second mechanism.

**7. Trader-authored text in the autofill prompt is quoted data, and the output is shape-validated.**
The vision prompt already exists and `prompts/` is locked, so extend the contract rather than rewriting it. Whatever the model returns is a **suggestion set**, filtered through the write allowlist before it can touch a draft — a field the model invents simply has nowhere to go.

## Risks

**The rebinding fix is easy to get subtly wrong.** Connecting to a validated IP while preserving TLS verification against the original hostname is the fiddly part. Mitigation: Group A tests the property directly by resolving to a private address *after* validation and asserting the fetch aborts — not by asserting the guard function returns `False`, which proves nothing about the connection.

**Autofill could quietly become authoritative.** The failure is a trader submitting a model's guess believing they confirmed it. Mitigation: nothing is pre-accepted above the existing confidence policy, every suggested field is visibly marked as suggested until touched, and Group D tests that an unreviewed suggestion is distinguishable from a human-entered value.

**A draft that never becomes a trade is litter.** Mitigation: drafts are owner-scoped, capped per owner, and superseded rather than accumulated; the plan does not add a sweeper, and says so.

---

## File Structure

**Python — new**

| File | Responsibility |
|---|---|
| `alembic/versions/<rev>_add_trade_drafts.py` | The `trade_drafts` table, with `downgrade()`. |
| `src/tradelens/services/drafts.py` | Owner-scoped draft read/upsert/delete. Pure of HTTP. |
| `src/tradelens/services/url_ingest.py` | Rebinding-safe fetch returning **bytes**, never a path. |
| `src/tradelens/api/schemas/autofill.py` | Draft, suggestion and URL-ingest models; the autofill write allowlist. |
| `src/tradelens/api/routers/autofill.py` | Draft, URL-ingest and autofill endpoints. |

**Python — modified**

| File | Change |
|---|---|
| `src/tradelens/db/models.py` | `TradeDraft`. |
| `src/tradelens/api/worker.py` | Register the `trade_autofill` handler. |
| `src/tradelens/api/app.py` | Register the router. |

**TypeScript — new**

| File | Responsibility |
|---|---|
| `web/lib/app/drafts.ts` | Server-only draft fetches. |
| `web/app/api/trades/draft/route.ts` | Draft autosave relay. |
| `web/app/api/trades/ingest-url/route.ts` | URL-ingest relay. |
| `web/app/api/trades/autofill/route.ts` | Autofill enqueue/poll relay. |
| `web/components/app/new-trade/url-ingest.tsx` | The URL input beside the file picker. |
| `web/components/app/new-trade/autofill-review.tsx` | Per-field accept/correct. |
| `web/components/app/new-trade/draft-status.tsx` | Saved/saving indicator. |

**TypeScript — modified**

| File | Change |
|---|---|
| `web/components/app/new-trade/new-trade-form.tsx` | Wire draft, ingest and review in. **Layout and field set unchanged.** |
| `web/lib/app/new-trade-fields.ts` | Screenshot field back to `"file-or-url"` once ingest actually ships. |

---

## Task list

### GROUP A — URL ingest through quarantine *(deepest review)*

**Task A1 — a rebinding-safe fetcher returning bytes.**
`services/url_ingest.py`: `fetch_image_bytes(url: str) -> bytes`. Resolve the host **once**, validate every returned address with the existing public-IP policy, then connect to the validated address while preserving the original `Host` header and TLS hostname verification. Keep the existing no-redirect opener and the 10 MB cap and 5-second timeout. Reuse `ai_screenshot_service._is_public_url`'s policy rather than writing a second one; if it needs to be shared, lift it into `url_ingest` and have the old module import it so there is one policy, not two.
Tests: loopback, private, link-local, reserved, multicast and unspecified are each refused; a non-http(s) scheme is refused; a redirect is refused; a body over the cap is refused; and — the important one — **a host that validates as public but resolves to a private address at connect time is refused**, asserting the fetch aborts rather than asserting a helper returns `False`.
**Mutations:** remove the post-resolution address check; restore the second `_is_public_url` call in place of connecting to the validated IP. Both must fail named tests.

**Task A2 — `POST /v1/trades/{id}/screenshot/ingest-url`.**
Owner-scoped like every other screenshot route. Fetches with `fetch_image_bytes`, PUTs the bytes to the caller's quarantine key, then calls the existing `finalize_upload` — **the same promote, validate, re-encode and record path the browser upload uses**. A non-image URL, an oversized body and a rejected image each return 422 with a plain message; another owner's trade returns 404, byte-identical to a missing one.
Tests: a valid image URL produces a `screenshots` row whose `file_path` is under the owner's final prefix; the promoted bytes **differ** from the fetched bytes (proving re-encode, not passthrough); a decompression bomb served over HTTP is refused by `validate_and_normalise` exactly as an uploaded one is; a cross-owner trade issues **no fetch and no S3 call at all** (assert on stubs, not just the status).

### GROUP B — Drafts *(deep review)*

**Task B1 — the `trade_drafts` table and service.**
Columns: `id`, `user_id` (FK, indexed), `payload_json`, `created_at`, `updated_at`. Alembic revision with a real `downgrade()`. `services/drafts.py`: `get_draft(user_id)`, `save_draft(user_id, payload)`, `delete_draft(user_id)` — all `require_user_id`-guarded, one live draft per owner, superseded on save rather than appended.
Tests: an owner reads only their own draft; a second owner's draft is invisible; saving twice supersedes rather than accumulating; the migration round-trips.
**Mutation:** drop the owner predicate from the read — a named test must fail.

**Task B2 — `PUT /v1/trades/draft` and `GET /v1/trades/draft`.**
The payload is a positive allowlist over the *draft-able* fields, `extra="forbid"`. **No derived field is accepted** — a test asserts the draft allowlist is a strict subset of the create allowlist minus every server-derived column, so the two cannot drift.
Tests: a draft round-trips; every derived and server-owned field is rejected; **no `trades` row is created by any number of draft saves** (assert the row count); an unsigned or body-tampered request fails Lock 1.
**Mutation:** allow a derived field through the allowlist — a named test must fail.

### GROUP C — Autofill *(deep review)*

**Task C1 — the autofill job.**
Runs `check_screenshot_quality` then `analyze_screenshot_v3` **against the finalized object**, not an upload or a temp file. Filters the model's output through the autofill write allowlist before anything is stored, so an invented field has nowhere to go. Persists suggestions with their confidence onto the owner's draft.
Cost discipline, reusing Phase 3E's shapes: an owner-scoped rate limit checked **before** any billable call; `Usage` recorded the instant the provider returns, **before** output validation, so a failed parse is still billed-and-visible; a failed job stays terminal rather than silently re-spending.
Tests: suggestions land on the draft and never on `trades`; a field outside the allowlist is dropped; a derived field is dropped; the rate limit refuses before any provider call; usage is recorded even when validation then fails; a failed job is not re-run on resubmit.
**Mutations:** remove the allowlist filter; move the usage record after validation; remove the rate-limit check. Each must fail a named test.

**Task C2 — enqueue and poll endpoints.** `POST /v1/trades/autofill` and `GET /v1/trades/autofill/{job_id}`, owner-scoped, with a foreign job id returning 404 byte-identical to a missing one. Register the handler in the worker.

### GROUP D — The review UI *(light review)*

**Task D1 — URL input.** Beside the file picker, not replacing it. Same states as the upload island; a rejected URL reads as a plain reason, never a stack or a host.
**Task D2 — per-field review.** Every suggested value is visibly *suggested* until the trader accepts or edits it, and an unreviewed suggestion is distinguishable from a human-entered value. Reuse `should_autocheck`'s confidence policy rather than inventing a second one. Nothing is submitted without an explicit action.
**Task D3 — draft status.** A quiet saved/saving indicator. Autosave is debounced, never fires on an empty form, and its failure is non-blocking — a draft that fails to save must never block or alter a real submit.
**Task D4 — flip `new-trade-fields.ts`** back to `"file-or-url"`, now that ingest actually ships.

### GROUP E — Verification and handoff

**Task E1.** Full gates from a committed HEAD: Python suite, ruff, black, vitest, tsc, eslint, production build with every new route confirmed `ƒ` dynamic, the OpenAPI/TypeScript drift gate producing no diff, and a single Alembic head. Then update the handoff. **The six deployment gates stay open and are not addressed here** — restate them rather than quietly dropping any.

---

## Self-Review

**Spec coverage.** §8's remaining New Trade items: **upload or image URL** (A2, D1) · **quality check** (C1, via `check_screenshot_quality`) · **AI analysis** (C1) · **autofill review per field** (D2) · **draft persistence** (B1, B2, D3). That is every item Phase 4 deferred; nothing else from §8 is outstanding.

**Placeholder scan.** No TBD/TODO. Each task names its files, its interface and the specific properties its tests must prove. Component tasks carry behavioural requirements rather than invented markup, because Phases 2, 3 and 4 each shipped defects from fixtures encoding a plan's wording instead of the code's real contract — implementers must read the generated types.

**Type consistency.** `fetch_image_bytes(url) -> bytes` is produced in A1 and consumed in A2. `get_draft`/`save_draft`/`delete_draft(user_id, ...)` are produced in B1 and consumed by B2 and C1. The autofill write allowlist is defined once in `schemas/autofill.py` and consumed by C1 and B2's subset test. `analyze_screenshot_v3`, `check_screenshot_quality`, `should_autocheck`, `finalize_upload` and `count_recent_jobs` are all used with their existing signatures — none is redefined.

**Two findings this plan exists to fix, recorded plainly.** URL-fetched images currently **never** pass `imaging.validate_and_normalise`, so they bypass the bomb guard, dimension caps and re-encode that every uploaded image gets. And the SSRF guard resolves DNS, then `urlopen` resolves it **again**, leaving a rebinding window that the existing "defense-in-depth re-check" narrows but does not close. Redirects are already blocked by `_NoRedirect`, which is the one part of that surface currently sound.

**Known scope risk.** Group C is a second AI consumer with its own cost, injection and rate-limit surface — the same shape as Phase 3E, which was correctly split out. If a smaller merge is wanted, **Groups A and B are a clean cut**: URL ingest and drafts are independently useful, and autofill can follow without reopening either.
