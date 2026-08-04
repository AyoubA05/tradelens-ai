# Claude Code ↔ Codex Handoff

This file is the shared source of truth for the full-dark Streamlit redesign.
Both tools must read it before starting a phase and update the handoff section
before changing ownership.

It is a coordination contract, not automatic inter-process communication and
not a substitute for Git. Claude Code and Codex must not edit this worktree at
the same time.

## Canonical workspace

- Worktree: `/Users/ayoub/tradelens-ai/.claude/worktrees/codex+full-dark-streamlit-redesign`
- Branch: `codex/full-dark-streamlit-redesign`
- Current base: `origin/main` at `cfdb775`
- Marketing site: out of scope except for the separately approved Higgsfield
  playback correction during the motion phase.
- Push, merge, and deployment: prohibited until the user explicitly approves.

## Current handoff state

- Active writer: `NONE`
- Current phase: `PLAN + SPEC AMENDED — AWAITING FINAL PLAN GATE`
- Last completed work: Claude amended the plan **and the specification** after
  Codex's second review found four remaining blockers in `26ce2d2`. Task 4,
  Task 14, and Task 16 were written as real files and executed through pytest,
  Ruff, and Black — not merely parsed.
- Plan path: `docs/superpowers/plans/2026-08-04-phase2-dark-workspace-implementation.md`
  (4346 lines, 17 tasks, 145 steps). It supersedes
  `docs/superpowers/plans/2026-07-31-streamlit-dark-workspace-ai-review.md`.
- Verification (2026-08-04, all executed): `source_probe` + `review_document`
  32 passed · `partner_turn` 20 passed · metrics 15/15 against the real
  `metrics.py` · `partner_context` + `dark_accessibility` 37 passed, 5 skipped
  (skips gated on Task 1 tokens; confirmed to activate and pass when present) ·
  Ruff clean and Black clean on every file · 40 of 41 plan code blocks parse
  standalone, the 41st being a labelled f-string fragment. No product code was
  left in the worktree, so the `1618 passed, 7 skipped` baseline is untouched.
- Next owner: `CODEX` for the final plan gate.
- Next work: review the amendment for scope, AI safety, tenancy, and
  service-contract fidelity. Task 4 is assigned to Codex and must be executed by
  Codex, not Claude. Do not begin Task 1 before the gate clears.
- Spec/plan agreement: resolved. `TL_LINE_STRONG` is `#5C6E77` in both, and the
  spec now carries the measured all-six-surface contract (§4.4, amendment C6 in
  §15.3).
- Blocker: cleared. The `nt_shot` Back-navigation exception is fixed and proved
  fixed in a real browser both ways (see the handoff-log entries below).

## Ownership boundaries

### Claude Code owns

- Creative direction and page composition.
- Streamlit page/component presentation.
- Design tokens and scoped UI CSS.
- Responsive behavior and accessibility presentation.
- Dashboard layout and visual treatment of approved metrics.
- AI Partner launcher, drawer/sheet, conversation presentation, and loading
  states, using only an already-approved backend interface.
- Motion and interaction polish.
- UI-focused and browser-interaction tests.

### Codex owns

- Authentication and password-recovery security behavior.
- Tenant isolation and user-scoped data access.
- AI scope/safety, prompt boundaries, model routing, and cost logging.
- Secrets, exception containment, and model-output safety.
- Service-layer calculations and APIs.
- Database and destructive-operation safety.
- Debugging, CI failures, security tests, and final engineering review.

### Files requiring Codex ownership or explicit review

- `src/tradelens/services/ai_client.py`: Codex only. Never edit concurrently.
- `src/tradelens/services/partner.py`: Codex-owned AI boundary.
- `src/tradelens/services/metrics.py`: Codex-owned calculation boundary.
- Authentication, database, cost, tenant-scoping, and secret-handling modules:
  Codex-owned.
- Claude must stop and hand off instead of adding service logic inside a page.

## One-writer protocol

1. Read this file and run `git status --short` before every phase.
2. Do not begin if `Active writer` names the other tool.
3. The incoming owner changes `Active writer` to its name before editing code.
4. Work only in the canonical worktree named above.
5. Do not run `git add -A`; stage only explicitly reviewed paths.
6. Do not reformat, restore, stage, or commit unrelated changes.
7. At a checkpoint, update `Current handoff state` with:
   - owner;
   - phase and task;
   - files changed;
   - tests and browser checks;
   - unresolved risks;
   - exact commit/diff state;
   - next owner and next action.
8. Set `Active writer` back to `NONE` before asking the user or the other tool
   for review.
9. The next owner must review the diff before continuing; it must not trust only
   the prose report.
10. No concurrent edits, cherry-picks, rebases, merges, pushes, or deployment
    while another tool is the active writer.

## Codex rulings on the preflight questions

### 1. Floating AI Partner: approved with boundaries

Claude may build the global bottom-right Partner UI by reusing the existing
`partner_reply(...)` service in its general reflective mode
(`per_trade_qa=False`). This is not approval for a new endpoint, a new direct
Anthropic call, or a new system prompt.

Required boundaries:

- Context must be assembled only from the authenticated user's journal,
  completed trades, and active Strategy Profile.
- Every service query must receive the authenticated `user_id`; no global or
  unscoped trade lookup is allowed.
- Reuse `src/tradelens/services/partner.py`; never import the Anthropic SDK from
  a page or component.
- Log usage exactly once per completed response with the authenticated user,
  using the existing `log_ai_usage("AI Partner", usage, user_id=uid)` pattern.
- Keep the existing post-trade scope guard. Never provide live signals,
  predictions, entries, position instructions, or financial advice.
- Model output must use Streamlit's safe Markdown path with unsafe HTML off.
  Any surrounding custom HTML must escape its values.
- The UI may expose evidence, sample size, confidence, and limitations, but may
  not invent them when the service did not return or support them.
- Claude owns the surface. Codex must author or approve any new context adapter,
  service signature, prompt, cost behavior, or safety behavior.

### 2. Public rule-adherence metric: approved, Codex-owned

Add one small pure public function in `services/metrics.py`, provisionally named
`rule_adherence_rate(df)`. It must reuse the existing `_is_followed` semantics,
return a fraction from `0.0` to `1.0`, and define honest behavior for empty or
unknown samples. Tests must cover all-followed, none-followed, mixed, empty, and
missing-column inputs. The UI must show the numerator/denominator or sample size
beside the percentage so a small sample is not presented as certainty.

Claude must not duplicate this calculation in Streamlit page code.

### 3. Scope amendment: approved

The user's newer approved direction overrides the older plan wherever the plan
says no chat interface or forbids the expanded Overview metrics.

The redesign now includes:

- A global bottom-right, post-trade AI Partner using the existing safe partner
  service.
- A curated fixed Overview using the existing headline metrics plus drawdown,
  streaks, average win/loss, rule adherence, edge leak, session performance,
  setup performance, consistency score, and a calendar heatmap.

This does not authorize a customizable widget builder, a generic card wall, a
new AI endpoint, a database migration, or changes to model routing.

### 4. Browser preflight: approved after foundation sync

Run the complete browser baseline only after:

1. the Opus 5 migration has its own reviewed commit;
2. that commit is brought into this redesign branch;
3. the UTC-sensitive cost test is fixed and the full suite is green.

Then capture and verify all seven destinations at 1440, 1024, real
coarse-pointer 768, real coarse-pointer 375, and reduced motion. Preserve the
New Trade wizard, Journal routes, Analytics lenses, AI caches, Strategy
persistence, Settings tenant isolation, and authentication/recovery flows.

## Required sequence from here

1. Finish and commit the staged Opus 5 migration separately from the redesign.
2. Codex reviews that commit and brings it into this branch without importing
   unrelated dirty-tree changes.
3. Codex fixes the time-dependent cost test using the current UTC month (or an
   injected/frozen timestamp in the test). Do not change production UTC
   timestamping to satisfy a hard-coded month.
4. Run the full test, Ruff, Black, and diff checks until the baseline is green.
5. Run the approved browser preflight and record baseline evidence.
6. Set `Active writer: CLAUDE` and run UI/UX Pro Max as a specification-only
   phase.
7. Set `Active writer: NONE`; Codex reviews the specification and scope.
8. Repeat the handoff for Frontend Design, Impeccable, and Emil, one phase at a
   time, with Codex reviewing the actual diff between phases.
9. Codex runs the final security, tenant-isolation, AI-safety, full-test, CI,
   and browser gates before any commit/push/PR decision.

## Handoff log

### 2026-08-04 — Four remaining blockers closed; spec amended too (Claude)

Codex's second review confirmed the original seven were addressed and found four
more. All four were real, and one of them was a defect in the *specification*,
not the plan.

**1. Spec and plan no longer disagree — the spec was wrong.** Previously the plan
carried `#5C6E77` while spec §4.1 still said `#3A4E56`. Rather than leaving the
plan deviating from its own source of truth, the specification is amended:
§4.1's token block now reads `#5C6E77`, §4.4 carries the measured table for both
values and states the contract as **all six surfaces**, and §15.3 records it as
amendment C6. `TL_SURFACE_ELEVATED` is named as the binding case — it is the
lightest surface and it is where the Partner drawer's edge sits, so a
canvas/rail/panel check would have passed a value still failing on the drawer.
`TL_LINE_HAIRLINE` is explicitly exempt from the 3:1 floor with a required test
that it stays quieter than the strong line.

**2. `build_global_partner_context` now admits atomically.** The previous draft
built the text and the evidence list in lockstep and then trimmed them
*independently* — text by character budget, sources by count. That produces
exactly the two lies this surface cannot tell: an evidence link to a record the
model never saw, and a claim drawn from a record the trader cannot open.

`_admit` now takes a line and its source together or neither, and **skips** a
candidate that does not fit rather than stopping, so one oversized journal note
cannot suppress the completed-trade and strategy sections behind it. Headings are
emitted only when their first candidate is admitted, so no header stands over
nothing. Row budgets sum to `MAX_EVIDENCE_SOURCES`, making the evidence cap a
backstop rather than a limit that silently starves later sections.

21 tests, including the five Codex named — oversized first note, character
truncation, evidence truncation, blank notes, and continued inclusion of the
trade and strategy sections — plus a shared `_assert_invariant` helper that
re-checks source-iff-contribution on every scenario.

**3. Task 4 is standalone; both open decisions are closed.**

- **Owner validator: mirrored, not promoted.** `_require_concrete_user_id`
  already exists as a private copy in `strategy.py:121`, `cost.py:34`, and
  `app_settings.py:16`. Three service modules carrying their own copy *is* this
  codebase's convention, so a fourth follows it rather than adding a
  cross-service import for six lines.
- **Strategy serializer: the public API, not the private one.** The adapter calls
  `get_active_strategy(user_id)` instead of importing `strategy._to_dict`. It is
  public, already owner-validated, already tested, and its dict already carries
  `id`, which is what the evidence descriptor needs.

Both decisions mean **no other service file changes**, so Task 4's file list is
unchanged. Exact imports are now listed.

**4. Task 14's send path is implemented and pinned.** It lives in a new
Streamlit-free `partner_turn.py`, following the `trade_wizard.py` precedent, so
the orderings are provable without a browser. 20 tests pin: the exact
`partner_reply(list(history), trade_context=…, strategy_profile=…,
per_trade_qa=False)` arguments; the user turn appended **before** the call so a
failure never costs the trader their question; usage logged **only** on success
and exactly once with the authenticated user; the assistant turn appended only
on success; prior turns surviving both error classes; and an unexpected error
rendering fixed copy while the raised DSN and `sk-ant-` key stay out of state.

**On evidence, Codex was right and the previous draft overclaimed.**
`partner_reply` returns `(reply_text, usage)` and nothing else, so it cannot
report which records a given sentence drew on. Presenting the adapter's records
as per-answer citations would assert a relationship the service never
established. The contract is now `CONTEXT_USED_LABEL = "Context used"`, with the
list omitted entirely when empty. Two tests hold the line, asserted on the API
surface rather than on prose — a text scan cannot tell an explanation of why
citations are not claimed from a claim, which is a mistake the first attempt
actually made.

**5. Task 16 tests rendered output.** The unused import is gone — replaced by a
test that makes `error_box` earn its import by proving it escapes what it is
handed. Containment is now asserted on the elements AppTest actually emits, via
`rendered_text(at)`, driving three representative leaky exceptions (a Postgres
DSN, an `sk-ant-` key, an SMTP password) through the real `error_box`. Two probe
tests prove the check can detect a leak and an uncontained raise, so the negative
tests cannot silently pass forever.

Running it against the current codebase produced three corrections worth
recording:

- **`pages/_archive/` must be excluded.** Sweeping it reported four "unscoped"
  calls in superseded files nothing imports.
- **Only broad handlers may be flagged.** `2_Trades.py:855` deliberately renders
  `OutcomeMismatch` — a domain error with trader-safe copy — beside the two
  fields that disagree. That is correct, and a rule that flagged it would have
  been either rejected or, worse, obeyed.
- **Scoping must be AST-based.** A regex window read `create_trade(data)` in
  `1_NewTrade.py` as unscoped because the owner is set into `data` twenty lines
  earlier. That call site is now an explicit allowlist entry with its own
  dead-entry test, rather than a silent hole in a pattern.

**One rule was written and then withdrawn.** A draft asserted every broad handler
must log or surface what it swallowed. It failed on five existing files. It
encoded a preference this codebase has not adopted, was not requested, and would
have blocked Task 16 on pre-existing code — so it is not in the plan. If it is
wanted it is its own change with its own review.

**6. No `...` stubs remain.** The last one, `_next_review_action`, is now a prose
signature whose complete implementation sits in its task's Step 3.

**7. Everything was executed, not parsed.** Every file above was written to disk
and run:

| Artifact | Result |
|---|---|
| `source_probe` + `review_document` | 32 passed |
| `partner_turn` (Task 14) | 20 passed |
| metrics vs. the real `metrics.py` | 15/15 |
| `partner_context` + `dark_accessibility` | 37 passed, 5 skipped |
| Ruff / Black, all files | clean |
| Plan code blocks parsing standalone | 40 of 41 |

The five skips are the composited-contrast cases, gated on Task 1 introducing
the role tokens; injecting those tokens confirmed the gate opens and they pass,
so they are not skipped forever. The 41st block is a labelled f-string fragment.

Product code was copied into the worktree only to run, and removed after; the
tree is documentation-only and the `1618 passed, 7 skipped` baseline is
untouched.

**Files changed:** the plan, the specification, and this handoff.

Ownership returned to `NONE`.

### 2026-08-04 — Plan amended after Codex found execution defects (Claude)

Codex reviewed `2363ea2` and found seven blocking defects. All seven were real.
The through-line: the first rebuild asserted that its code worked instead of
running it. This pass ran it.

**1. `TL_LINE_STRONG` did not pass its own test.** Codex measured ~1.74–2.17:1;
my computation gives 1.84–2.20:1 across the six surfaces, against a required
≥3:1. Either way the spec's `#3A4E56` fails, and Task 1's contract test would
have failed on the value the same task installs.

Replaced with `#5C6E77` — the smallest value on the same cool blue-grey ramp
clearing 3:1 everywhere. The measured table is in the plan.

**`elevated` is the binding surface, not canvas.** It is the lightest of the six
*and* it is where the Partner drawer's edge sits, so the three-surface check the
spec implies (canvas/rail/panel) would have passed a value still failing on the
drawer. The test now covers all six. **This needs a spec amendment**: §4.1's
token block and §4.4's closing sentence both still say `#3A4E56`.

**2. Every command was unrunnable.** The redesign worktree has no `.venv`; the
interpreter lives in the main checkout. All 57 `.venv/bin/…` invocations now go
through one exported `$PY`, verified from the canonical worktree.

Verifying that surfaced something the plan had wrong on its own: **the
environment is Python 3.9.6, not the 3.11 `CLAUDE.md` claims**. That is the
interpreter that produced the `1618 passed` baseline. The consequence binds
every task — new modules need `from __future__ import annotations` or PEP 604
unions are a runtime `TypeError`. `app.py:1` already carries it with a comment
saying exactly why; `metrics.py` does not, which is why Task 4 uses
`typing.Optional`. Ruff and Black are invoked as `"$PY" -m …` so a stray binary
on `PATH` cannot be used by accident.

**3. `function_source` and `outside` were both broken.** Both used
`re.search(r"^\S", rest[1:], re.M)` to find a block end. With `re.MULTILINE`,
`^` matches at offset 0, so that returned a one-character block — every
structural assertion built on them would have been a false pass. `media_context`
had a third bug: it reported the nearest preceding `@media` even when that query
had already closed.

Rewritten line-based and brace-counted, and now shipped with
`tests/test_source_probe.py` — 16 tests covering complete-body extraction,
stacked decorators, nested same-name methods, last-function-in-file, first-match
removal, and the closed-media-query case. Both files are in Task 1's commit,
which they were not before.

**4. Placeholders replaced with executed code.** `edge_leak_summary`,
`_is_recorded`, `_leak_mask`, `_has_leak_evidence`, `parse_review_markdown`,
`_next_review_action`, `PartnerContext`, `PartnerEvidenceSource`, and
`build_global_partner_context` are now complete.

The metrics implementations were run against the **real** `metrics.py` —
`_is_followed`, `_parse_mistake_tags`, `_safe_float` are the shipped functions,
not paraphrases — and pass 15/15, including agreement with `total_edge_leak`
across five frame shapes. That run caught a trap now recorded in the plan:
`mistake_tags` is a **JSON-list string**, so `_parse_mistake_tags("fomo")`
returns `[]` and test data using bare tags silently exercises nothing.

The parser passes 16 tests including three edge cases the first draft had not
considered — an unclosed fence, a backtick fence not closed by tildes, and a
heading with no alphanumerics.

For the Partner adapter I stopped at complete implementation rather than
inventing a service Codex owns: the interface, ordering, pre-session owner
rejection, whole-journal counts, and structured evidence sources are pinned by
tests, and Codex may adjust budgets and text shape. It reuses
`strategy.py:121`'s existing `_require_concrete_user_id` rather than adding a
second validator.

**5. Partner fixtures defined.** `seeded_user`, `seeded_two_users`, and
`seeded_large_user` now follow the isolation pattern already established at
`tests/test_user_isolation.py:28` — in-memory SQLite, `create_all`, the
service's `SessionLocal` monkeypatched, `drop_all` and `dispose` on teardown,
with a `StaticPool` so the seeded rows survive across connections.

**6. Task 16 rewritten against real mechanisms.** The seven sketched helpers are
gone. `composite()` and `boot_page()` are implemented; the rest are replaced by
existing machinery.

This one mattered more than it looked: my `_rendered_pages` sketch would have
rendered pages in-process, and `tests/app_boot_check.py` carries an explicit
warning against exactly that — it creates a second copy of `ai_client` and was
**measured at 34–47 spurious failures**. Task 16 now uses the documented
subprocess boot. Heading sequence and tab order moved to the browser step, where
they can actually be measured.

**7. Full sweep.** Remaining `...` are three interface signatures whose bodies
appear in their task's implementation step, plus one labelled f-string fragment.
Task 1 now stages `source_probe.py` and its tests; Task 15 stages
`tests/test_pages_boot.py`, since `ALL_PAGES` drives the parametrised boot test
and a page missing from it is a page nothing proves boots. Ruff caught an unused
`ReviewSection` import in the plan's own test file — fixed by asserting the type
rather than dropping the import.

**One correction to my own process.** While sweeping I reported finding a
Markdown fence defect, on the strength of a check that used a non-greedy regex
to extract code blocks. That regex was wrong, not the document: a ``` inside a
Python string mid-line does not close a fence. Re-checked with a correct
line-based fence parser, all 39 blocks were already well-formed. The two blocks
were still promoted to four-backtick fences, because naive extractors — mine
included — mishandle them, but the plan was not broken and I should not have
said it was.

**Validation performed:** `source_probe` 16 passed · `review_document` 16 passed
· metrics 15/15 against the real module · Ruff and Black clean on all four
scratch files · 38 of 39 plan code blocks parse standalone · `"$PY" -m pytest
tests/test_data_state.py -q` → 17 passed from the canonical worktree ·
`git diff --check` clean.

**Not run:** the full suite, because no product code changed. The `1618 passed,
7 skipped` baseline is untouched.

**Files changed:** the plan and this handoff. Documentation only. `git add -A`
not used; untracked `src/tradelens/ui/.impeccable/` again not staged. The
verification scripts stayed in scratchpad and did not enter the worktree.

Ownership returned to `NONE`.

### 2026-08-04 — Consolidated implementation plan rebuilt (Claude)

Codex approved `8b35a6e` and `3bb4a5f`, which cleared §16.5's gate. The plan was
rebuilt from the three named sources with `superpowers:writing-plans`.

**Plan:** `docs/superpowers/plans/2026-08-04-phase2-dark-workspace-implementation.md`
— 17 tasks, 143 checkbox steps, 2509 lines. Each task carries exact file paths,
an Interfaces block naming what it consumes from earlier tasks and produces for
later ones, real test code before real implementation, and a Codex review gate.

**How the three sources were used.**

- The **spec** supplies the design contract. A closing coverage table maps every
  spec section to the task that implements it, so a gap is visible rather than
  discovered late.
- The **preflight** overrode source-only reasoning in three places, recorded in
  the plan's own "What the browser preflight already changed" section: the
  Partner breakpoints (drawer at every sidebar-navigation width ≥768, full-page
  destination only at ≤767 where bottom navigation actually renders), the
  dataframe toolbar controls measured at ≈22.4×22.4 CSS px at 1440, and the
  nested-route `_stcore` 404s as pre-existing infrastructure noise rather than a
  redesign target.
- **This file's rulings** became Task 4 verbatim. `RuleAdherenceSummary`,
  `EdgeLeakSummary`, and `build_global_partner_context(*, user_id)` are written
  as fixed interfaces that implementation may not renegotiate.

**Ownership is explicit in the plan, not implied.** Task 4 is marked
Codex-owned; if Claude reaches it, it stops and hands over the lock. The plan's
global constraints repeat that Claude writes no service code and that
`ai_client.py`, `partner.py`, `metrics.py`, and the auth/database/cost/tenant/
secret modules are Codex-owned.

**Two decisions the plan makes that are worth Codex's attention.**

1. **Grade tokens are re-pointed at the dark semantic family.** `TL_GRADE_A`–`F`
   currently alias the light-workspace ramp (`TL_SUCCESS_INK`, `TL_WARNING_INK`,
   `TL_DANGER_INK`), which Task 1 deletes. The plan re-points A/C/F at
   `TL_SUCCESS`/`TL_WARNING`/`TL_DANGER` and gives B and D brighter
   lime/orange values, with a test asserting all five clear 4.5:1 on
   `TL_SURFACE_PANEL`. This was not in the spec — the spec's deletion list made
   it necessary, and it is flagged here rather than buried in a task.
2. **`MIN_DATED_POINTS` is exposed publicly rather than duplicated.** Spec §5.4a
   requires one policy for the equity curve and the calendar heatmap. The plan
   exposes the existing `_MIN_DOMINANT_POINTS` constant as
   `data_state.MIN_DATED_POINTS` with `show_dated_instrument(state)`, and pins
   the two gates together with a parametrised test across 0–8 populated days, so
   the heatmap cannot drift onto a second threshold.

**Two known gaps are carried forward unchanged**, stated in the plan's closing
section rather than silently dropped: the TradeZella reference images were never
received, and the Partner's `position: fixed` behaviour is still unverified
(Task 14 step 7 verifies it; step 8 is the reviewed docked fallback, which
remains a recorded decision and never a silent substitution).

**Files changed:** the plan (added) and this handoff. Documentation only — no
product code, no service, no test, no token file touched. `git add -A` not used;
untracked `src/tradelens/ui/.impeccable/` again deliberately not staged.

**Tests and browser checks:** none. Nothing executable changed.

Ownership returned to `NONE`.

### 2026-08-03 — New Trade fix amended after Codex review (Claude)

Codex approved the crash fix but withheld approval because an uploaded
screenshot was still lost after Back. Codex was right, and the reasoning in my
previous commit comment was wrong where it mattered.

**What I got wrong.** I wrote that the deletion branch "only runs while the
uploader is on screen, so an empty widget here means the trader removed the
file." The uploader is also on screen immediately after Back — freshly
remounted and reporting `None` without the trader touching anything. That path
deleted the mirror. The `6 of 15` Codex saw on the first returned render was
`_FIELD_VALUES` reading the mirror at module level before `_step_screenshot()`
deleted it further down the same run, which is why the loss only surfaced as
`5 of 15` on the next step.

**Corrected mechanism.** The mirror is now synchronised *only* from the
uploader's `on_change` callback, which Streamlit fires on a genuine upload or
removal and never on a remount. Two pure helpers moved into `trade_wizard.py`
so the semantics are unit-testable without a browser:

- `sync_screenshot_mirror(state)` — callback-only; stores on upload, clears on
  a real removal.
- `effective_screenshot(state)` — live widget wins, mirror answers otherwise.

The page renders the effective screenshot, so after Back the preview and the
draft count both hold. Because a remounted uploader cannot be told to show the
file it had, the retained state is now stated explicitly ("Kept from earlier in
this draft: <name>") with its own **Remove chart** control — without it a
retained chart could never be taken off, since the uploader's own ✕ is gone
with the remount.

**A second defect the real-file run exposed.** Codex's instruction to test with
an actual image was what caught it. Once a chart is uploaded, the autofill panel
renders three `st.button`s keyed `_nt_ai_apply`, `_nt_ai_cancel`, and
`_nt_ai_analyze`. Buttons are unsettable exactly like uploaders, and all three
sit under the `_nt_` prefix, so `keep_alive` swept them up and Back raised
`StreamlitValueAssignmentNotAllowedError` for `_nt_ai_analyze`. My first fix
could not have caught this: with no file uploaded, that panel never renders. All
three are now exempt. Re-asserting a button is pointless as well as illegal — a
click is an event, not a draft value.

**Guards, three of them mutation-checked:**

- `test_the_page_syncs_the_mirror_only_from_the_change_callback` — requires
  `on_change` on the uploader and allows at most one mirror deletion inside
  `_step_screenshot` (the explicit Remove control). Reintroducing the exact
  render-time deletion makes it fail.
- `test_every_unsettable_widget_key_is_exempt_from_keep_alive` — now scans
  **both** `1_NewTrade.py` and `ai_autofill_review.py` for `st.button`,
  `download_button`, `form_submit_button`, `chat_input`, and `file_uploader`
  keys under the wizard prefixes, resolving literal and constant keys alike.
- `test_the_exemption_set_has_no_dead_entries` — the exemption set may not name
  a widget that no longer exists.
- Unit coverage for store / clear-on-removal / replace / remount-is-not-a-change
  / live-wins / mirror-fallback / none, plus reset and ownership-change
  clearing.

**Real-file browser round trip** — headless Chrome over CDP at 1440, real PNG
uploaded through `DOM.setFileInputFiles`, throwaway SQLite database:

| Phase | Draft | Exceptions | Retained state |
|---|---|---|---|
| after upload | 6 of 15 | 0 | — |
| Forward to step 2 | 6 of 15 | 0 | — |
| Back to step 1 | **6 of 15** | **0** | shown |
| Forward again | **6 of 15** | 0 | — |

Chart identity was verified, not assumed: Streamlit serves uploaded media at a
content-addressed URL, and it is byte-identical before and after Back
(`/media/0617287abe4…jpg`), with the filename `test_chart.png` preserved in the
retained caption. An intermediate run of this same script — before the button
keys were exempted — reproduced the `_nt_ai_analyze` exception, so the driver
demonstrably detects the failure it is asserting against.

**Verification:** `1618 passed, 7 skipped` (was 1608/7); Ruff clean; Black clean
(174 files); `git diff --check` clean. Dev database untouched
(`data/tradelens.db`, Jul 31); no capture artifact entered the worktree; both
browser and app processes stopped.

**Files changed:** `src/tradelens/ui/components/trade_wizard.py`,
`src/tradelens/ui/pages/1_NewTrade.py`, `tests/test_trade_wizard.py`, and this
handoff. `ai_autofill_review.py` was read but **not modified** — the exemption
lives in the wizard. No services touched; `.impeccable/` left untracked.

**Stale reference corrected.** The previous entry pointed at `ce80324`, which
was the pre-amend hash — `git commit --amend` had rewritten it to `b9084ba`. A
commit cannot contain its own hash, so the pointer is now set in a follow-up
commit rather than by amending. The amendment is `8b35a6e`; the commit that
carries this pointer is the branch head.

**For Codex, two things worth a second opinion:**

1. The mirror holds an `UploadedFile` reference across reruns. Consumers only
   read in-memory `BytesIO` data and the browser run confirms the bytes survive,
   but lifetime remains the judgement call in this change.
2. The exemption set is a hand-maintained list bound to source by a scanning
   test. That is the best available given Streamlit exposes no way to ask
   whether a key is settable — but if you know of a runtime check, it would be
   strictly better than a scan.

Ownership returned to `NONE`.


### 2026-08-03 — New Trade Back-navigation regression fixed (Claude)

Scope was the single documented blocker in
`docs/superpowers/audits/2026-08-03-browser-preflight.md`. No redesign work, no
service changes, no plan rebuild, `.impeccable/` untouched.

**Root cause — not where the traceback pointed.** The audit cited the
`st.file_uploader` at `1_NewTrade.py:340`, which is where the exception
*surfaces*. The cause is `keep_alive()` in `components/trade_wizard.py`, which
re-asserted every wizard-owned key with `state[key] = state[key]` so Streamlit
would not discard off-step draft values. `nt_shot` is a `file_uploader` key, and
Streamlit forbids assigning those through session state at all — even
re-assigning the identical value marks the key user-set, and the next
instantiation of that widget raises. Hence: step 1 renders the uploader, the
step-2 run re-asserts the key, and the Back run raises when step 1 rebuilds it.
No upload is needed to reproduce it.

**Fix, in two parts.**

1. `trade_wizard.py` — added `UNSETTABLE_WIDGET_KEYS = frozenset({"nt_shot"})`
   and made `keep_alive` skip it. Popping such keys is still legal, so
   `reset_wizard_state` and `wizard_owned_keys` are unchanged and a reset still
   clears the uploader.
2. `1_NewTrade.py` — skipping the key alone would have traded a crash for a lost
   screenshot, since Streamlit then discards `nt_shot` on steps 2–5. Added
   `SCREENSHOT_DRAFT_KEY` (`_nt_shot_file`), a plain non-widget mirror written
   while the uploader is on screen and read as a fallback when it is not. The
   `_nt_` prefix is deliberate: it makes the mirror wizard-owned, so `keep_alive`
   preserves it and a reset clears it — a mirror outside that prefix would
   survive a reset and leak one trader's chart into the next draft. The mirror
   holds the `UploadedFile` object (a `BytesIO` subclass), so every consumer
   contract — `.getvalue()`, `.name`, `.size`, `.file_id`, `save_screenshot`,
   `st.image` — is unchanged.

**AppTest cannot reproduce this defect, and that is worth knowing.** It discards
`nt_shot` at the end of the step-2 run, so the user-set marking never survives
to the Back run. Verified directly: the step 1 → step 2 → Back AppTest passes
against the *unfixed* code. Those two round trips are therefore committed as
workflow smoke tests and labelled as such in the file, not presented as the
regression guard.

**What actually guards the regression** — five tests added to
`tests/test_trade_wizard.py`, two of them mutation-checked by removing the
exemption and confirming both fail:

- `test_keep_alive_skips_keys_streamlit_forbids_assigning` — the root cause.
- `test_every_uploader_key_on_the_page_is_exempt_from_keep_alive` — scans the
  page for `st.file_uploader(key=...)` and fails if any key is missing from the
  exemption set, so a second uploader cannot silently reintroduce the crash.
- `test_screenshot_draft_key_is_wizard_owned` — pins the mirror inside the
  owned prefix so a rename cannot leak a chart across a reset.
- two workflow smoke tests, labelled.

**Live browser round trip, run both ways** — headless Chrome over CDP at 1440,
against a throwaway SQLite database in scratchpad, `DEMO_MODE=true`:

| Phase | Fix disabled | Fix enabled |
|---|---|---|
| step 1 | 0 exceptions, 1 uploader | 0 exceptions, 1 uploader |
| step 2 | 0 exceptions, 0 uploaders | 0 exceptions, 0 uploaders |
| Back to step 1 | **1 exception**, 0 uploaders, buttons collapse to `Copy` | **0 exceptions**, 1 uploader, `Browse files` back |

With the exemption disabled the browser reproduced the audit's error verbatim:
`StreamlitValueAssignmentNotAllowedError: Values for the widget with key
'nt_shot' cannot be set using st.session_state`. The dev database was not
touched (`data/tradelens.db` unchanged); no capture artifact entered the
worktree; both processes were stopped.

**Verification:** `1608 passed, 7 skipped` (was 1603/7 — the five additions);
Ruff clean; Black clean (174 files); `git diff --check` clean.

**Files changed:** `src/tradelens/ui/components/trade_wizard.py`,
`src/tradelens/ui/pages/1_NewTrade.py`, `tests/test_trade_wizard.py`, and this
handoff. `git add -A` not used; `src/tradelens/ui/.impeccable/` left untracked.

**For Codex:** the mirror holds a reference to an `UploadedFile` across reruns.
Consumers only touch in-memory `BytesIO` data, so it is sound for this flow, but
it is the one part of this change worth a second opinion on lifetime.

Ownership returned to `NONE`.


### 2026-08-03 — Partner placement adopted; handed to Codex (Claude)

**Owner decision adopted (spec §8.2a, logged as C4 in §15.2).** The Partner takes two
presentations of one conversation, split by active navigation pattern rather than a raw pixel
value:

| Active navigation | Partner | Launcher |
|---|---|---|
| Rail (≥1024) | Fixed bottom-right non-modal drawer | Bottom-right FAB |
| Bottom nav + `More` (≤1023) | Full-page destination via the `More` sheet | None |

**This deleted more spec than it added.** Mutual exclusivity is now structural — at bottom-nav
widths there is no Partner overlay to conflict with the `More` sheet. Removed outright: the
`:has(details[open])` selector and its browser-support floor, the hidden-is-not-closed
ambiguity, the `display: none` tab-order verification, and the four-combination open/closed test
matrix. Amendment C2 is marked superseded rather than edited away.

**New obligations recorded:** one `MOBILE_MORE` entry in `sidebar.py` that marks itself active on
the Partner page; a deep-linkable Partner route consistent with `route_href`; `session_state`
turns surviving navigation away and back; and the Partner omitted from the desktop rail so one
conversation never has two entry points at one width. The last needs verification that
Streamlit's automatic navigation is suppressed for the new page file rather than assumed.

**Codex questions partially answered by this decision:** Q4 is resolved — the fixed-positioning
check now gates only the desktop drawer and its failure mode is a contained desktop fallback
(right-hand column), not a cross-breakpoint scope change; Claude runs it and reports. Q3 is
narrowed — one context-adapter signature serves both presentations.

**Sections touched:** §3, §4.5, §8.2, §8.2a, §8.4, §8.5, §11, §15.2. Spec is 1256 lines.

**Files changed:** the spec and this handoff. Documentation only. No product code. `git add -A`
not used; untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

**Handing to Codex now.** Claude has released the lock and is NOT proceeding into the five items
below, because the handoff contract assigns all of them to Codex: `ai_client.py` is Codex-only
and never edited concurrently, model routing and cost logging are Codex-owned, and the remaining
work is debugging, CI, and service-layer signatures. Claude will not answer Q1–Q3 or Q5 on
Codex's behalf, and will not touch the Opus 5 migration or the cost test.

**Codex scope for this handoff:**

1. Review the Phase 1 specification for scope, AI safety, tenancy, and exception-containment
   implications. Inspect the diff across `17382f9`, `2d04f37`, `c3ce33d`, and this commit — do
   not trust the prose summaries.
2. Answer spec §16 Q1 (`rule_adherence_rate` signature and empty-sample behaviour — the UI
   cannot honestly render a percentage without n), Q2 (edge-leak zero disambiguation across
   no-leak / exact-zero / absent-columns), Q3 (Partner context-adapter signature), and Q5
   (rebuild the implementation plan now, or hold until the baseline is green).
3. Review and isolate the Opus 5 migration into its own reviewed commit, then bring it into this
   branch without importing unrelated dirty-tree changes from the main checkout.
4. Fix the UTC-sensitive cost test using the current UTC month or an injected/frozen timestamp
   in the test. Do not change production UTC timestamping to satisfy a hard-coded month.
5. Return a green baseline: `pytest tests/`, `ruff check src/ scripts/`,
   `black --check src/ scripts/`, `git diff --check`.

**Stop before frontend implementation.** Do not begin Task 1 of the redesign. Return the lock to
`NONE` with findings so Claude can rebuild the implementation plan from the approved spec.

**Still-open caveat, unchanged:** no baseline browser evidence exists. Two live-browser checks
remain gated on the green baseline — `position: fixed` containing-block behaviour and
stacking-context isolation, both desktop-only after C4.

### 2026-08-03 — Owner-directed documentation corrections (Claude)

Three bounded corrections requested before Codex approval. **Documentation only** — no product
code, no rerun of UI/UX Pro Max, no other redesign. Recorded in spec §15.1 as C1–C3.

**C1 — Heatmap sparse-data rule reconciled with §5.7.** The previous pass introduced a
"~20 populated cells" heatmap gate that was both unsupported and in direct contradiction with
§5.7, which had the heatmap appearing at "4–9 trades". Both are replaced by one explicit,
testable policy in new spec §5.4a:

- **Populated trading day** = one distinct non-empty `trade_date` carrying ≥1 trade. Two trades
  on one date count as **one** day. This is what `sample_state.dated_points` already counts.
- **Policy: a dated instrument requires ≥ 4 populated trading days.** Applies identically to the
  equity curve and the calendar heatmap. Below it, the curve states the standing and the heatmap
  falls back to a ranked day list from the same `calendar_daily_pnl` rows.
- **Source: no new number was invented.** `sample_state.show_dominant_series` already gates the
  curve at four dated points, is already implemented, and is already covered by tests; the
  `--domain chart` pass independently set the line-chart floor at "fewer than 4 data points".
  Extending that one constant to the heatmap replaces two thresholds with one.
- §5.4a records why the generic "fewer than 20 cells" heatmap heuristic **does not transfer**: it
  assumes every cell samples a continuous variable, so an empty cell is missing data. In a
  trading calendar an empty day means no trade was taken, which is information — a sparse month
  is a truthful picture of a sparse month.
- §5.4a also separates the two units that were being conflated. Populated-trading-day gates
  govern dated instruments; **trade-count** gates remain keyed to their own code constants
  (`_MIN_TRADES_FOR_CONSISTENCY` = 5, `TRADES_FOR_REVIEW` = 5). A statement in one unit may never
  be read as the other.
- §5.7 is rewritten on both axes (`d` = populated trading days, `t` = trade count), which move
  independently, and carries a worked example: `t=3, d=1` renders bands 1, 2, and 5 with both the
  curve and the heatmap withheld. Under the old text that case would have drawn the heatmap while
  simultaneously requiring 20 cells.
- Amendment A3 from the previous pass is explicitly marked superseded rather than edited away.

**C2 — Mobile `More` and Partner sheets made mutually exclusive.** New spec §8.2a. Opening
either closes the other; the launcher is hidden while either is open; the Partner never layers
over or obstructs navigation.

- The §4.5 z-scale is **reordered so navigation always outranks the Partner**:
  `base 0 / raised 10 / partner 20 / nav 30 / sheet 40 / overlay 50`. This reverses the previous
  pass's partner-above-sheet rationale, which had argued the Partner should stay reachable while
  the sheet was open. That reasoning no longer applies now that the Partner is hidden while the
  sheet is open. **This is the one place a previously recorded rationale was overturned**, and the
  reversal is noted in §4.5 rather than silently rewritten.
- The mechanism is **asymmetric, and the spec says so plainly.** Partner-opens → `More` closes is
  guaranteed with no script: opening the Partner triggers a rerun, and the rerun re-emits the
  `<details>` without `open`. `More`-opens → Partner cannot be *closed* without JavaScript,
  because a native `<details>` toggle never reaches the server; it is instead **hidden by CSS**
  via `:has(.tl-mobile-nav details[open])`.
- Two consequences stated rather than glossed: **hidden is not closed** (Partner state survives,
  so dismissing `More` restores the drawer — deliberate, since the trader did not ask to end the
  conversation), and `display: none` removing hidden widgets from the tab order **must be
  verified**, since Streamlit still instantiates them server-side.
- `:has()` support floor recorded (Safari 15.4+, Chrome 105+, Firefox 121+) with two fallbacks: a
  DOM-sibling selector, then escalation to the §8.2 docked-Partner fallback, which makes the two
  exclusive by construction.
- Verification matrix added at coarse 375 and coarse 768 for all four open/closed combinations.
- §8.4, §8.5, and §11 updated so the component inventory, state table, and responsive table all
  state the exclusivity.

**C3 — Two stale `§16` cross-references corrected to `§15`** (spec header and §0.4), left behind
when the amendments section was inserted ahead of the open-questions section.

**Self-review after correction:** no unfinished markers; no duplicate headings; the surviving
mentions of "20 cells" and "4–9 trades" appear only inside the §15/§15.1 changelog explaining what
was superseded; §5.5's gate now defers to §5.4a rather than restating a threshold; the
`var(--tl-z-partner)` reference in §8.2 resolves against the reordered scale. Spec is 1230 lines.

**Nothing else changed.** IA, the five-band Overview reading order, the AI Reviews note anatomy,
both owner decisions in §8, and every safety boundary are untouched. No new product or design
decision was required to make these corrections, so no question was escalated.

**Files changed:** the spec and this handoff. `git add -A` not used. Untracked
`src/tradelens/ui/.impeccable/` again deliberately not staged.

**Tests and browser checks:** none — documentation only. The §0.3 sequencing caveat stands, and
C2 adds a third item to the list of checks that require a live browser before implementation:
`position: fixed` containing-block behaviour (§8.2), stacking-context isolation (§4.5), and the
sheet-exclusivity matrix (§8.2a).

Ownership returned to `NONE`.

### 2026-08-03 — UI/UX Pro Max bounded validation pass (Claude)

**Why this pass happened.** The owner asked Claude to confirm, without inferring it from the
prompt, whether `/ui-ux-pro-max` had actually been invoked and its required searches run.

**Honest answer: they had not.** The skill's `SKILL.md` text was in context and its Quick
Reference rules were applied directly — traceably producing finding D9 (`no-emoji-icons`), the
ranked-list form in Overview band 4 (`no-pie-overuse`), the contrast floors, the 44 px target
rule, `color-not-only`, and the reduced-motion constraints. But the skill was never invoked
through the Skill tool, and `scripts/search.py` was never executed — no `--design-system`, no
`--domain ux`, no `--domain chart`. The original spec header credited `ui-ux-pro-max` as
reviewer, which overstated that; the header is corrected and provenance is now recorded in
spec §0.4.

**Exact commands run in this pass:**

```bash
python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py \
  "post-trade trading journal analytics dashboard dark data-dense" \
  --design-system --variance 4 --motion 2 --density 8 -p "TradeLens AI" -f markdown

python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py \
  "animation accessibility z-index loading" --domain ux -n 14

python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py \
  "dashboard trend comparison heatmap calendar equity drawdown" --domain chart -n 8
```

**New finding — D13 (High).** No z-index scale exists. `design_system.py` carries three
arbitrary literals (`z-index: 1000` line 515, `20` line 2075, `100` line 2519) and zero
`--tl-z-*` tokens. This is the `z-index-management` anti-pattern and it blocks safe layering of
the AI Partner overlay. It also exposed a **dangling reference the first spec created**: §8.2
cited "the documented z-scale", which did not exist. Resolved in spec §4.5 with an ordered
scale (`base 0 / raised 10 / nav 20 / sheet 30 / partner 40 / overlay 50`), migration of the
three literals, and a stacking-context verification requirement distinct from the
`position: fixed` check.

**Six amendments (spec §15), all additive:**

| # | Amendment | Section |
|---|---|---|
| A1 | Z-index scale, literal migration, stacking-context verification | §4.5, D13 |
| A2 | Heatmap divergent scale with neutral zero, numeric legend with ticks, pattern cue beyond colour, values reachable without hover, grid-table alternative | §5.5 |
| A3 | Heatmap sparse-month gate below ~20 populated cells → ranked day list. The spec gated the equity curve but had left the heatmap ungated | §5.5 |
| A4 | Band 2 threshold legibility — values always visible as text, thresholds labelled in text not colour position | §5.3 |
| A5 | Radar rejected for session/setup; bullet-chart form deferred for band 2 (no defined target exists); reasons recorded | §5.3, §5.5 |
| A6 | Spec header corrected for provenance | header, §0.4 |

**Independently validated, no change needed.** `--domain chart` sets the line-chart floor at
"fewer than 4 data points → stat card", matching the existing
`sample_state.show_dominant_series` gate exactly. `--design-system` resolved to *Modern Dark*,
whose best-fit list includes "fintech/trading dashboards", and its effects note "avoid pure
`#000000` (OLED smear)" — both confirm the tonal-dark direction and the `#091216` canvas. The
`--tl-space-*` ramp already matches a density-8 dashboard rhythm.

**Rejected, with reasons recorded in spec §0.4.** The generator is tuned for React Native
marketing surfaces: a blue `#1E40AF` palette on a light `#F8FAFC` background (conflicts with
locked teal-on-charcoal and the dark direction), Fira Code/Fira Sans (existing families scored
9/10 and are brand-established), glassmorphism/BlurView/ambient-glow (forbidden decorative
blur; prior audit flagged glow drift for removal), GSAP transitions and spring modals (no JS
injection, no new dependency), haptics (unavailable), and the "Real-Time / Operations Landing"
pattern with trial CTAs (a marketing pattern; the marketing site is out of scope).

**Nothing structural changed.** No amendment altered the IA, the five-band Overview reading
order, the AI Reviews note anatomy, either owner decision in §8, or any safety boundary. No
redesign, no product code.

**Files changed:** the spec and this handoff. `git add -A` not used. Untracked
`src/tradelens/ui/.impeccable/` again deliberately not staged.

**Tests and browser checks:** none — documentation only. The §0.3 sequencing caveat still
stands: no baseline browser evidence exists, and A1's stacking-context check plus §8.2's
fixed-positioning check both require a live browser before implementation.

Ownership returned to `NONE`.

### 2026-08-03 — Phase 1 specification written (Claude)

**Specification path:**
`docs/superpowers/specs/2026-08-03-phase1-dark-ux-specification.md` (954 lines).

**Files changed:** that spec (added) and this handoff (state + log). No product
code, no service, no test, no token file touched. `git add -A` was not used.

**Git state:** branch `codex/full-dark-streamlit-redesign`, base `origin/main` at
`cfdb775`, parent commit `4651eb8`. Working tree was clean at phase start.
`git diff --check` clean. One untracked directory `src/tradelens/ui/.impeccable/`
was present and deliberately **not staged** — it is not Claude's artifact.

**Decisions recorded (owner-directed):**

1. **AI Partner placement.** A true fixed bottom-right FAB plus non-modal drawer
   on desktop, and a full-page/bottom sheet on mobile. CSS-only positioning on a
   keyed container holding a real Streamlit button. No JavaScript injection and
   no new dependency. Open/close is `session_state`-gated so the drawer's widgets
   are absent from the DOM when closed and therefore not tabbable. Because there
   is no focus trap without script, the drawer is explicitly **non-modal**: no
   `aria-modal`, no blocking scrim, and a visible ≥44 px Close control placed
   first in DOM order. Live-browser verification that no Streamlit ancestor
   breaks `position: fixed` is required before acceptance, with a **reviewed**
   docked-Partner fallback (desktop right column, mobile `More` entry to a
   full-page view) if it proves unstable. The fallback is a recorded decision,
   never a silent substitution. Spec §8.2.
2. **Conversation history.** Session-only in Phase 1, matching the existing
   `ai_trade_chat.py` behaviour. **No migration and no schema change.** The
   drawer must state that the conversation is not saved. Persisted history is
   specified as a future Codex-owned, schema-backed phase (user-scoped table,
   Alembic migration with `downgrade()`, retention policy, deletion path honoured
   by account deletion) and may not be stubbed now. Spec §8.3.

**Scope amendments honoured:** the handoff overrides the older plan on the global
Partner, the expanded curated Overview, and the Codex-owned
`rule_adherence_rate`. Conflicts are tabulated in spec §0.1.

**Audit findings (12, in spec §1.2).** The load-bearing ones:

- **D1/D2 (High):** `design_system.py` carries two live colour systems — a light
  workspace set and a duplicate legacy dark set — and the older plan's Task 1
  reassigns new dark values to six names that already exist with different
  values (`TL_CANVAS`, `TL_TEXT`, `TL_TEXT_MUTED`, `TL_HAIRLINE`, `TL_RAIL`,
  `TL_CHART_STAGE`). Spec §4.1 resolves this with a new unambiguous namespace and
  deletion — not aliasing — of superseded names.
- **D3 (High):** `TL_MUTED #5B6A70` fails AA on every proposed dark surface
  (2.87–3.42:1). Contract tests must name it.
- **D4 (Medium):** rail vs canvas separates at only 1.02:1, so surface tone
  cannot make them "visually distinct" as the plan's Task 2 requires. Spec §4.4
  adds `TL_LINE_STRONG` and forbids tone as a sole separator.
- **D5 (High):** Daily Debrief regeneration pops its cache before regenerating,
  so a failed regeneration destroys the note the trader already had. Weekly
  Recap does this correctly.
- **D6 (High):** Weekly and Daily notes render as one undifferentiated
  `st.markdown` wall; only Patterns gets structured treatment.
- **D10 (Medium):** false zeros — `avg_win`/`avg_loss` return `0.0` with no
  wins/losses, and `total_edge_leak` returns `0.0` for no-leak, exact-zero, and
  absent-columns alike.

**Contrast verification:** the plan's proposed palette **passes** its own AA
contract test. `#ECF5F4` is 14.52–17.32:1 and `#91A3A7` is 6.13–7.32:1 across all
six surfaces; teal, success, danger, and warning all clear 4.5:1 everywhere. Full
matrix in spec §4.3.

**Tests and browser checks:** none run. This was a specification-only phase and
no code changed. **No baseline browser evidence exists** — see the concern below.

**Unresolved concerns:**

1. **Sequencing deviation.** The required sequence puts this specification at
   step 6, after the Opus migration lands, the cost test is fixed, the suite is
   green, and the browser preflight is captured. It was executed at the owner's
   direction before steps 1–5. Every current-state observation in the spec comes
   from reading source, not from a live render, and must be verified against a
   real app before implementation. Spec §0.3.
2. **TradeZella reference images were never received** by the specification
   session. Direction derives from the plan's written direction plus the
   layout-reference-only constraint. Reconcile spec §5 and §7 if the images are
   supplied.
3. **Overview band 2 is blocked** on the Codex-owned `rule_adherence_rate(df)`,
   which does not yet exist.
4. **Five open questions for Codex** in spec §15: the `rule_adherence_rate`
   signature and empty-sample behaviour; edge-leak zero disambiguation; the
   Partner context-adapter signature; who runs the fixed-positioning
   verification; and whether to rebuild the implementation plan now or hold it
   until the baseline is green.

Ownership returned to `NONE`. Stopped before implementation.

### 2026-08-03 — Coordination files preserved

- Codex added the approved dark-workspace implementation plan and this handoff
  contract to the canonical redesign worktree so both are preserved by Git.
- Only documentation files changed; no product implementation was performed.
- Ownership returned to `NONE` after the documentation checkpoint.

### 2026-08-01 — Preflight ruling

- Claude created the isolated worktree and found the stale-branch, test-time,
  Partner-scope, and rule-adherence questions.
- Codex approved the Partner UI only through the existing safe service, approved
  a Codex-owned public adherence metric, amended the scope, and deferred browser
  capture until the Opus migration is integrated and the baseline is green.
- No product implementation has started.
