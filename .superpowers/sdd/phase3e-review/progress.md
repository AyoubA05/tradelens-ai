# Phase 3E independent review — controller ledger

Branch codex/phase3e-ai-summary @ 86b36a8, from main @ cdee4fa.

## Deep review: cleared-with-findings. 8 mutations run; 6 killed, 2 SURVIVED.
Tenant isolation verified independently doubly-enforced (mutating EITHER owner predicate is
caught by its own named test). No browser-supplied owner: all six spellings 422 via extra=forbid.
Delimiter escaping holds — </trade_data_json> is unspellable, and a mutation removing the escape
is caught. Nothing reaches the prompt outside the JSON block (period_label is regex-pinned dates).

## Live smoke (disposable Neon br-proud-bread-auirrn83, real Postgres)
VERIFIED: filter scoping (A all=6 / NQ=4 / ES=2, each snapshot single-asset); cross-user
isolation (A's snapshot has zero of B's rows and none of B's private note); B polling A's job ->
404 with no prose; B naming user_id/owner/accountId -> 422; low-sample 0 and 1 both refused;
idempotency keys distinct per filter AND per owner, stable on recompute; panel renders all five
sections with a scope badge matching the filter; changing the filter re-scopes the button
(4 -> 2 trades) and the stale summary is NOT displayed.
VERIFIED WITH A REAL PROVIDER ERROR: the Anthropic key in .streamlit/secrets.toml is REVOKED
(direct API call returns 401), so live model output could NOT be exercised. The 401 was used
instead to drive the failure path end to end: job -> failed, attempts=1, result_ref=None, a
generic user-facing message leaking no provider internals, and re-enqueueing the same key
returned the SAME job which the worker refused to pick up again. The no-duplicate-spend property
is therefore confirmed against a real provider failure, not a stub.
NOT VERIFIED: live model output against the seeded prompt-injection payload (no working key),
and 375px rendering (the browser tab collapsed to its shell after every mobile resize; the
measurements I took were of an empty page and are worthless, so I am not claiming them).

## Rulings
Ruling: fix the two surviving mutations. The relay's fail-shut-when-SITE_ORIGIN-is-unset and the
panel's stale-selection gate are both correct in code and protected by nothing. These are the two
properties the handoff states most confidently, which is exactly the Phase 3 pattern: the
property is real, the test does not reach it.

Ruling: fix the usage-logging order. log_ai_usage runs after generation AND after save, but
generate_trade_summary raises on validation failure and discards the Usage it already holds — so
a truncated Opus response is billed and never appears in cost tracking. Cost tracking that is
silent precisely when something went wrong is worse than none.

Ruling: fix the stranded button. Aborting leaves loading=true, so switching filters mid-generation
and back leaves a permanently disabled "Reviewing trades…" with no in-app recovery. The job may
have succeeded and been paid for.

Ruling: bound every free-text field that reaches the prompt. notes/process notes/mistake tags are
bounded to 500 chars but emotions_before, setup_type, htf_bias and others pass through raw and are
browser-reachable through the PATCH allowlist with no max_length. A 200k-char field was shown to
produce a 201k-char prompt; at 40 trades that is a real cost and context-overflow lever.

Ruling: ADD a content-level no-advice gate. The reviewer is right that nothing currently catches a
model that writes a trade idea inside a structurally valid section — the five-heading check is
shape only. "No forward-looking recommendations" is not a nice-to-have here; it is the product's
identity, and the owner named it as a review focus. A rejection check at the same point as
_validate_markdown costs nothing at runtime and fails terminally without re-billing.

Deferred, recorded not fixed: no rate limit or quota on a paid endpoint (an authenticated user can
walk the date range and mint unbounded billable jobs) — pre-deployment item, not a 3E regression;
a transient provider outage being permanently terminal for that exact snapshot; and `owner` in the
idempotency canonical string being untested defence-in-depth.
