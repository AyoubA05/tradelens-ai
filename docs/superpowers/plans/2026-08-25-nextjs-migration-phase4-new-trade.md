# Phase 4 — New Trade + Screenshot Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a trader log a completed trade from the Next.js app in one dense form, and attach a screenshot through the full quarantine → validate → normalize → promote lifecycle that Phase 0 built and nothing has yet exercised end to end.

**Architecture:** The trade row is created first and its id is what authorises the upload — so the browser never names an object key that anything trusts, and `presign_upload`'s existing `_owns_trade` gate remains the only ownership rule. Screenshots then flow browser → presigned PUT into a non-downloadable quarantine namespace → server-side finalization that decodes, validates and re-encodes the bytes → a fresh owner-scoped final key → the `screenshots` row → quarantine cleanup. Next.js stays the BFF: relays hold the session cookie, `callApi` forwards only the domain-separated handle.

**Tech Stack:** FastAPI · Pydantic v2 · SQLAlchemy 2.x · Pillow (existing `api/imaging.py`) · boto3 / Cloudflare R2 · Next.js 16 App Router (RSC + client islands) · TypeScript · Tailwind · pytest · Vitest

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md` (§7 phase 4, §8 New Trade inventory, §2.2 request lifecycle, §4 tenant isolation, §12 design direction)

## Global Constraints

- **Every protected page authenticates before any backend side effect.** Next renders a page concurrently with its layout, so a parent layout is redirect defence, **never** a precondition for child data access. Each new route calls `appLayoutRedirect()` itself before fetching. (Established by the Codex Phase 2 review; re-verified in Phase 3.)
- **Identity comes only from the authenticated session row.** Never a header, query, path segment, or body field.
- **Service-layer tenant isolation is mandatory.** Every service call passes an explicit `user_id` guarded by `require_user_id`. No nullable-owner path.
- **Next.js is the BFF.** Raw browser session credentials never reach FastAPI; `callApi` forwards only `sha256("tl.website.v1|" + token)`. `TL_SERVICE_SECRET` never reaches the browser.
- **The HMAC/session-handle boundary is unchanged.** HMAC-SHA256 over `{timestamp}.{METHOD}.{path}.{canonical_query}.{sha256(body)}`.
- **Every mutation/write schema is an explicit positive allowlist** with `extra="forbid"`. Ownership and server-owned metadata (`user_id`, `id`, `trade_hash`, `is_sample`, `created_at`, `updated_at`, `strategy_id`) are unreachable through HTTP input. A new column is not writable until deliberately filed.
- **No object key supplied by the browser is ever trusted.** A returned key is a claim to be re-derived and re-checked against the owner's expected prefix, never a location to act on.
- **404, never 403**, byte-identical to a genuine not-found, on every per-id route.
- TradeLens is a **post-trade reflection journal**. Never a signal app, a bot, or financial advice. This binds every label, placeholder, empty state and error string.
- **No new npm dependencies.**
- Python 3.9.6 floor: `from __future__ import annotations`, `Optional[X]`/`List[X]`, never `X | Y`.
- No Streamlit imports in `services/`, `db/`, or `src/tradelens/api/`.
- `src/tradelens/services/metrics.py` is parity-pinned — adding is allowed, modifying is not.
- Alembic for every schema change, with a working `downgrade()`.
- Gates: `pytest tests/ -q`; `ruff check src/ scripts/`; `black --check src/ scripts/ tests/`; in `web/`: `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build`.
- jest-dom is not global: new web test files need `import "@testing-library/jest-dom/vitest";` first.

---

## Execution process

Groups, not per-task gates — the model that worked in Phases 2 and 3.

| Group | Review depth |
|---|---|
| A — trade creation, duplicate detection, idempotency | **Deep.** First write endpoint that creates rows. |
| B — the screenshot lifecycle | **Deepest in the phase.** Untrusted bytes, untrusted keys, cross-tenant object access. |
| C — the dense form: field parity and validation | Light at the group boundary. |
| D — upload UX, partial failure, retry, mobile | Light, **except** the partial-failure and retry interaction, which get real scrutiny. |
| E — AI autofill | **Deferred — see Scope.** |
| F — verification, browser smoke pass, handoff | Final phase boundary. |

**Mutation-test every security guard.** Across Phases 3 and 3E, eight separate tests passed against deliberately broken code — each asserting a value the implementation echoed back rather than an observable outcome. For every guard in Groups A and B, break it and confirm a named test fails. A guard with no failing mutation is not defended.

**The browser smoke pass is a gate, not a formality.** In Phase 2 it found a self-contradicting card that 982 passing tests certified.

---

## Scope

**In:** trade creation with duplicate detection, the complete screenshot lifecycle, the single dense form at exact field parity, client and server validation, upload states and retry, mobile at ~375px.

**Deferred to Phase 4E, tracked not dropped:** **AI autofill** — screenshot quality check, vision analysis, per-field accept/reject review. Spec §7 lists it in the Phase 4 row and §8 names "upload or image URL · quality check · AI analysis · autofill review per field". It is deferred because it is a second AI consumer with its own prompt-injection surface, cost controls and rate limit — the same shape as Phase 3E, which was correctly split out — and because the form and the lifecycle must be trustworthy before anything writes into them automatically. **Draft autosave** is also deferred to 4E; it is only meaningful once autofill can populate a partly-filled form.

**Explicitly not in this phase:** the four open pre-deployment gates (Docker build/startup/health; broader Python dependency audit; working Anthropic key + live injection/model smoke; real 375px browser smoke of Phase 3E) stay tracked in the handoff and are **not** solved here. The flaky Streamlit AppTest harness stays recorded as technical debt — **do not mix a test-harness rewrite into this phase.**

---

## Design decisions

**1. The trade is created first, and its id is what authorises the upload.**
This is the phase's central decision. `storage.presign_upload(user_id, trade_id, content_type)` already requires `_owns_trade(owner, trade_id)`, so a screenshot can only be uploaded against a trade that exists and belongs to the caller. New Trade therefore submits the form, gets a `trade_id` back, and only then presigns.

The alternative — a trade-less draft namespace keyed by something else — would require inventing a second ownership rule for objects with no owning row, plus a sweeper for drafts that never become trades. That is a new trust boundary built to save one round trip, and this project's whole security posture rests on there being exactly one way ownership is resolved.

The cost is a real window: a trade can exist without its screenshot. That is the right direction for the failure to point. A trade saved without its screenshot is visible, editable and attachable later; a screenshot uploaded with no trade is an orphan nobody can find and nothing sweeps. **Decision 6 makes that window survivable.**

**2. The browser's returned key is a claim, never a location.**
`presign_upload` returns a quarantine key; the browser PUTs to it and hands it back to `finalize_upload`. `finalize_upload` already re-derives `_expected_prefix(owner, trade_id, quarantine=True)` and refuses anything outside it, so a forged key cannot escape the caller's own quarantine namespace. Phase 4 must not add any path that trusts a supplied key, and must test that refusal directly rather than relying on a downstream gate — Phase 3's review found exactly that mistake in `presign_download`, where a malformed key was rejected by a *later* check and the ownership join was never exercised.

**3. Validation is server-side and re-encoding is mandatory.**
Client-side checks are courtesy: they save a trader a slow upload of a 40MB file. The real gate is `imaging.validate_and_normalise`, which caps input bytes, refuses non-images, guards Pillow against decompression bombs (`MAX_PIXELS`, `MAX_DIMENSION`), and — critically — **writes fresh re-encoded bytes** rather than promoting the uploaded object. The uploaded bytes are never what a viewer later downloads, so a polyglot or a file with a malicious trailer cannot survive promotion. ContentType is bound into the presigned policy, so it is a rule R2 enforces rather than advice this code gives.

**4. Duplicate detection reuses `compute_trade_hash`, which already exists.**
`trade_service.compute_trade_hash` fingerprints date, asset, direction, entry time and the price levels; `create_trade` computes it and a lookup by `(trade_hash, user_id)` already exists. Phase 4 surfaces it rather than inventing a second notion of sameness — a submit that matches an existing fingerprint for that owner is reported as a probable duplicate with a link to the existing trade, not silently written and not silently refused.

**5. Idempotency is the trade hash, not a client token.**
A double-submit, a retried request after a dropped response, and a back-button resubmit all produce the same fingerprint. The endpoint returns the existing trade with a flag rather than creating a second row. No client-generated idempotency key is introduced: the browser cannot be trusted to generate one uniquely, and the fingerprint is already the project's answer to this question.

**6. Partial failure is explicit, and the trade is always the durable thing.**
If creation succeeds and any later step fails — presign, PUT, finalize — the trade exists and the UI says so plainly: the trade is saved, the screenshot did not attach, and here is how to retry. Retrying attaches to the *existing* trade (the fingerprint prevents a second row), so a trader can never end up with duplicate trades from a flaky upload. Abandoned quarantine objects are cleaned by an explicit abandon call and, failing that, are unreachable: quarantine is never downloadable and `delete_trade_objects` sweeps the trade's objects on deletion.

**7. One dense form, never a wizard.**
Approved in spec §12 and reaffirmed by the owner. The Streamlit page carries a `tl_wizard_bar`; the Next.js form does not replicate it. Everything is visible at once, grouped, with completeness warnings rather than gated steps. On mobile the groups stack; they do not become pages.

## Risks

**This is the first code to move untrusted bytes.** Every prior phase moved JSON. Mitigation: nothing the browser uploads is ever served — `finalize_upload` promotes only re-encoded output — and the quarantine namespace has no download path at all.

**`_is_final_key` hardcodes `.png`.** Carried from Phase 3: `delete_trade_objects` would *skip* a non-PNG final object, and Phase 3E's review noted this is the trigger condition for an untested ownership join in `presign_download`. `validate_and_normalise` only emits PNG today, so nothing is stranded — but Phase 4 is the phase that makes image handling load-bearing. **Task B4 addresses it deliberately rather than inheriting it.**

**A trade with no screenshot is a normal state, not an error.** Screenshots are optional in the existing workflow. Every state in this phase must treat "no screenshot" as ordinary, and must never render a broken image or an empty frame where a trader simply did not attach one.

**Field parity is large and easy to get subtly wrong.** Mitigation: Task C1 pins the field list against the Streamlit form's own keys in a test, so a missing field fails rather than being noticed later by a trader who lost their notes.

---

## File Structure

**Python — new**

| File | Responsibility |
|---|---|
| `src/tradelens/api/schemas/new_trade.py` | Positive allowlist for trade creation; the screenshot request/response models. |
| `src/tradelens/api/routers/new_trade.py` | `POST /v1/trades`, and the three screenshot endpoints. Thin: validate, call the service with the session owner, return. |

**Python — modified**

| File | Change |
|---|---|
| `src/tradelens/api/storage.py` | `abandon_upload(user_id, trade_id, key)`; generalise `_is_final_key` beyond `.png` (Task B4). |
| `src/tradelens/services/trade_service.py` | `find_by_fingerprint(user_id, trade_hash)` — surface the existing lookup as a named service function. |
| `src/tradelens/api/app.py` | Register the new router. |

**TypeScript — new**

| File | Responsibility |
|---|---|
| `web/lib/app/new-trade.ts` | Server-only create + screenshot fetches. |
| `web/lib/app/new-trade-fields.ts` | The field contract: names, types, options, client validation rules — one source shared by the form and its tests. |
| `web/app/api/trades/create/route.ts` | Create relay. |
| `web/app/api/trades/[id]/screenshot/route.ts` | Presign / finalize / abandon relay. |
| `web/components/app/new-trade/trade-form.tsx` | The single dense form. |
| `web/components/app/new-trade/field-group.tsx` | One titled group of fields; the unit that stacks on mobile. |
| `web/components/app/new-trade/screenshot-upload.tsx` | The upload island: states, progress, retry, remove. |
| `web/components/app/new-trade/duplicate-notice.tsx` | Probable-duplicate surface with a link to the existing trade. |
| `web/components/app/new-trade/completeness-notice.tsx` | Non-blocking warnings about thin records. |
| `web/app/app/trades/new/page.tsx` | The route (replaces the Phase 1 placeholder). |
| `web/app/app/trades/new/loading.tsx`, `error.tsx` | Route boundaries. |

---

## Task list

Each task follows the TDD shape used since Phase 2: write the failing test, run it and confirm it fails for the stated reason, implement, confirm it passes, commit.

### GROUP A — Trade creation and duplicate detection *(deep review)*

**Task A1 — `find_by_fingerprint` in `trade_service`.**
Surface the existing `(trade_hash, user_id)` lookup as `find_by_fingerprint(*, user_id: int, trade_hash: str) -> Optional[Trade]`, owner-scoped via `require_user_id`. Do not change `compute_trade_hash` or `create_trade`.
Tests: returns the owner's matching trade; returns `None` for another owner's identical fingerprint (**seed both and assert cross-owner isolation directly**); returns `None` when nothing matches.

**Task A2 — `POST /v1/trades`.**
Body is a positive allowlist over the parity field set (Task C1 names it). `extra="forbid"`; `user_id`, `id`, `trade_hash`, `is_sample`, `created_at`, `updated_at`, `strategy_id` unreachable. On submit: compute the fingerprint, call `find_by_fingerprint`; if it matches, return **200** with the existing trade and `duplicate_of` set, creating nothing; otherwise `create_trade` and return **201**. Server-side validation refuses a P&L/outcome contradiction by delegating to `canonical_outcome` (which already re-derives the label from P&L) and refuses a trade date in the future.
Tests: each allowlisted field round-trips; each server-owned field is rejected; a second identical submit creates no second row (**assert the row count**, not just the response); two owners submitting identical trades each get their own row; a future date is 422; unsigned and body-tampered requests fail Lock 1; the response is not cacheable.
**Mutations:** remove the fingerprint check (duplicate test must fail); remove `extra="forbid"` (each server-owned field test must fail).

### GROUP B — The screenshot lifecycle *(deepest review in the phase)*

**Task B1 — `POST /v1/trades/{id}/screenshot/presign`.**
Delegates to `storage.presign_upload`, which already requires `_owns_trade`. Returns `url`, `key`, `expires_in`, `max_bytes`. A trade that is not the caller's returns **404**, byte-identical to a missing trade.
Tests: an owned trade returns a URL whose key sits under the caller's quarantine prefix; another owner's trade returns 404 **and no presigned URL is generated at all** (assert on a stubbed client, not just the status); an unsupported content type is refused before any signing.
**Mutation:** remove the ownership check — the cross-owner test must fail.

**Task B2 — `POST /v1/trades/{id}/screenshot/finalize`.**
Body carries the `key` the browser received. Delegates to `storage.finalize_upload`, which re-derives the expected quarantine prefix and refuses anything outside it, decodes, validates, re-encodes, promotes to a fresh owner-scoped final key, writes the `screenshots` row, and deletes the quarantine object. Rejected images return **422** with a plain message; a key outside the caller's prefix returns **404**.
Tests: a valid PNG round-trips and produces a `screenshots` row whose `file_path` is under the owner's final prefix; **a forged key naming another owner's quarantine path is refused, and the test is built so ownership — not malformed input — is what causes the refusal** (Phase 3's review found exactly this test written the vacuous way); a non-image is 422; an oversized file is 422; a decompression bomb is 422; the promoted bytes differ from the uploaded bytes (proving re-encode, not copy); the quarantine object is gone afterwards.
**Mutations:** remove the prefix re-derivation; skip `validate_and_normalise`. Both must fail named tests.

**Task B3 — `POST /v1/trades/{id}/screenshot/abandon`.**
Deletes a quarantine object the trader chose not to keep, or that failed validation. Owner-scoped and idempotent — a missing object is success. Never touches a final key.
Tests: an owned quarantine key is removed; a key outside the caller's prefix issues **no delete call at all**; a second abandon succeeds; a final key is refused rather than deleted.

**Task B4 — generalise `_is_final_key` beyond `.png`.**
Carried from Phase 3 and now load-bearing: `_is_final_key` hardcodes `.png`, so a non-PNG final object would be *skipped* by `delete_trade_objects` — a privacy tail the moment normalization emits another format. Derive the accepted extension set from what `validate_and_normalise` can emit, in one place, so the two cannot drift.
Tests: a final key with each emittable extension is recognised; a key with an unexpected extension is not; `delete_trade_objects` reports a skipped key as **incomplete** (the Phase 3E rule that `complete` requires both `failed` and `skipped` empty must still hold).

### GROUP C — The dense form *(light review)*

**Task C1 — the field contract, pinned to parity.**
`web/lib/app/new-trade-fields.ts` names every field, its type, its options and its client validation rule. A test pins this list against the fields the Streamlit New Trade form collects — enumerated from `src/tradelens/ui/pages/1_NewTrade.py`'s form keys: asset (select + custom), trade date, entry time, timeframe, HTF bias, LTF bias, setup, confluences, confirmation text, entry / stop / take-profit / exit prices, position size, risk, R multiple, result, P&L, followed-rules, rule broken, mistake tags, emotions before / during / after, mindset, what went well, what to do better, process notes, screenshot. A field present in Streamlit and missing here **fails the test** — parity is not a thing to notice later, when a trader has already lost their notes.

**Task C2 — the form.**
One dense form, grouped, everything visible; **no wizard**. Groups stack at ~375px and never become pages. Client validation mirrors the server's rules and is explicitly courtesy: it must never be the only thing preventing a bad write. Completeness warnings are non-blocking — a thin record is allowed, and the trader is told what would make it more useful. The P&L/outcome contradiction is surfaced inline before submit, matching the server's `canonical_outcome` behaviour.

**Task C3 — the route.**
`/app/trades/new` validates its own authorization via `appLayoutRedirect()` before any fetch, plus `loading.tsx` and `error.tsx` that leak no backend message. Replaces the Phase 1 placeholder.

### GROUP D — Upload UX and partial failure *(light review, except the failure paths)*

**Task D1 — the upload island.**
Idle, selecting, uploading with progress, validating, attached, and failed. Client-side size and type checks before the PUT, framed as saving time rather than as the gate. Remove calls abandon. A trade with no screenshot is an ordinary state, never a broken frame.

**Task D2 — partial failure and retry.**
If creation succeeded and any later step failed, say plainly that the trade is saved and the screenshot did not attach, with a retry that attaches to the **existing** trade and cannot create a second one. This interaction gets real review: it is where a trader could otherwise be told nothing was saved when in fact a trade was, or be induced to resubmit and create a duplicate.

**Task D3 — mobile at ~375px.**
Groups stack, no horizontal overflow, tap targets adequate, the upload control usable one-handed. Long unbroken values must wrap rather than overflow.

### GROUP E — AI autofill — **DEFERRED TO PHASE 4E**

Not executed in this phase. Written out so the §7/§8 parity item stays tracked and cannot be silently dropped: screenshot quality check, vision analysis, per-field accept/reject review, and draft autosave. It is a second AI consumer with its own injection surface, cost tracking and rate limit — the same shape as Phase 3E — and the form and lifecycle must be trustworthy before anything writes into them automatically. **Do not begin it as part of Phase 4.**

### GROUP F — Verification and handoff

**Task F1.** Full gates from a committed HEAD: Python suite, ruff, black, vitest, tsc, eslint, production build with every new route confirmed `ƒ` dynamic, and the OpenAPI/TypeScript drift gate producing no diff. Then a **real browser smoke pass on a disposable Neon branch** (forked from dev, never production; deleted afterwards) covering: creating a trade with every field populated; a duplicate submit producing no second row; uploading a real image and seeing it render on the trade; a rejected non-image; an abandoned upload; the partial-failure path; a second account proving isolation on create and on every screenshot endpoint; and ~375px. R2 credentials are required for the upload half — **if they are unavailable, say so and record the upload lifecycle as unverified in a browser rather than implying it was tested.** Record what was seen, update the handoff, and stop.

---

## Self-Review

**Spec coverage.** §7 phase 4 and §8's New Trade inventory: single dense form (C2) · presigned upload (B1) · trade date, entry time, session auto-detect, asset, timeframe, HTF/LTF bias, setup model, evidence, confirmation text, followed-rules, result, P&L, risk, position size, R multiple, exact price levels, reflection notes, emotion log, mistake tags (C1, C2) · completeness warnings (C2) · duplicate detection (A2) · outcome/P&L contradiction block (A2 server-side, C2 inline) · upload or image URL — **the URL half is deferred with autofill to 4E**, since an image fetched from a URL is a server-side fetch of attacker-influenced input and belongs with the analysis work that motivates it · quality check, AI analysis, autofill review per field, draft persistence — **deferred to 4E, recorded above**.

**Placeholder scan.** No TBD/TODO. Each task names its files, its interface and the specific properties its tests must prove. Component tasks carry behavioural requirements rather than invented markup, because Phases 2 and 3 both shipped defects from fixtures that encoded a plan's wording instead of the code's real contract — implementers must read the generated types.

**Type consistency.** `find_by_fingerprint(*, user_id, trade_hash) -> Optional[Trade]` is produced in A1 and consumed in A2. `compute_trade_hash` and `create_trade` are used unchanged. `presign_upload(user_id, trade_id, content_type)`, `finalize_upload(user_id, trade_id, upload_key)` and `delete_trade_objects(user_id, trade_id)` are used with their existing signatures; `abandon_upload(user_id, trade_id, key)` is the one addition, named consistently in B3 and D1. The field list in C1 is the single source consumed by C2 and by A2's allowlist.

**Known scope risk.** Group B is the highest-risk work in the project so far — it is the first code to move untrusted bytes, and the first to accept a key from a browser. If a smaller merge is wanted, **Groups A and C are a clean cut**: trade creation and the form deliver a usable New Trade without any screenshot, and the lifecycle can follow. That is a worse product but a coherent one.
