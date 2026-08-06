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

- Active writer: `CLAUDE`
- Current phase: `PHASE 2 TASK 8 COMPLETE — TASK 9 IN PROGRESS`
- Last completed work: **Tasks 5, 6 and 7** — the Overview recomposed into its
  five bands: `243d0c9` (bands 1–2 and the shared date policy), `25616f9`
  (bands 3–4, trajectory and recurring edge), `00d2359` (band 5 and the state
  matrix). Task 4 is `3aa9e36`; Task 3 is `5a03834` + `16a81ee`.
- Plan path: `docs/superpowers/plans/2026-08-04-phase2-dark-workspace-implementation.md`
  (4900 lines, 17 tasks, 145 steps). It supersedes
  `docs/superpowers/plans/2026-07-31-streamlit-dark-workspace-ai-review.md`.
- Verification at `00d2359`: `1813 passed, 7 skipped` · Ruff clean · Black
  clean (181 files) · `git diff --check` clean · page boot checks 64 passed ·
  five bands in spec reading order at 1440, 1024, coarse 768 and coarse 375
  with the pointer state asserted at each coarse width, zero overflow, zero
  exceptions.
- Next owner: **`CLAUDE`**.
- Next action: **resume the approved Phase 2 master directive at Task 8** (New
  Trade on the dark workspace) and continue through Task 17 — one scoped
  commit and verification record per task — then release the lock to `NONE`
  and hand the complete Phase 2 diff to Codex.
- **No interim Codex review is requested.** The comprehensive Codex review
  remains scheduled after Task 17.
- Tasks 8–17 remain: New Trade, Journal, Analytics, the pure review document
  model, AI Reviews, Strategy Profile and Settings, the AI Partner desktop
  drawer and mobile destination, the cross-page audit, and the 10K re-score.
- Task 4 interfaces are present exactly as planned and verified green
  (`tests/test_metrics.py` + `tests/test_partner_context.py`, 129 passed).
  Claude must consume them, never reproduce their calculations or open a
  second data-access path in UI code.
- Deviations already approved by the user and in force for the remaining
  tasks: use `compute_breakdown` for P&L-ranked breakdowns because
  `by_setup_type` carries no P&L; use `killzone` as the session dimension with
  labels from `KILLZONE_LABELS`, because the Overview frame has no `session`
  column.
- Band logic lives in the pure `components/overview_bands.py`, not `app.py`:
  `app.py` runs its whole Streamlit script at module scope, so importing it in
  a unit test boots a page and needs a database.
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

### 2026-08-06 — Phase 2 Task 8: New Trade on the dark workspace (Claude)

**Commit:** see `feat(ui): New Trade on the dark workspace with one progress
system`. Task 8 only; Task 9 not started.

**Two of the plan's three Step-2 tests passed against the unchanged wizard.**
Transcribed verbatim and run before anything was edited: the progress-system
test names `render_stepper`, and this page has always called
`render_step_indicator`, so both its assertions were vacuous; the review-step
test passed because `_ticket_section` already drops blank rows and `"complete"`
already matched the heading `Completeness`. Only the waiting-state test failed,
and it names the wrong file. On their own the three would have licensed a no-op
task, so each is now paired with a test asserting what the plan's prose
actually requires.

**The real finding: the wizard was five bright pills.** `.tl-step-circle.done`
and `.active` both filled solid `--tl-accent-action`, and `.tl-step-connector.done`
was accent too — so a trader on step 5 saw five identical teal circles and four
teal connectors beside the teal `Continue` button. Teal is action and focus
(spec §4.1); a step already left is neither, and this is exactly the
unrestrained teal coverage 10K item 03 targets. Done now recedes to the
elevated surface behind a `TL_LINE_STRONG` edge, keeping its check glyph;
future keeps its number with no edge, so done and future differ by glyph and
edge rather than by tone. Exactly one circle carries the accent, and it is
always the active one. Contrast holds: secondary on elevated 6.13:1, strong
line on elevated 3.03:1.

**The waiting state now holds its height.** The screenshot analysis, its
spinner, and its scanning video all live in `ai_autofill_review.py`, not in
`1_NewTrade.py` where the plan looked. Both call sites — auto-trigger and
manual re-run — render inside one keyed container whose rule reserves 320px, so
the detection panel lands where the pending block stood instead of shoving the
page down. Two corrections to the plan's literal are recorded in the test's own
docstring: the file, and `tl_analysis_pending` rather than `tl-analysis-pending`
— authored HTML cannot wrap Streamlit widgets, so the height is reserved by
keying a real container, which is the mechanism `tl_wizard_bar` and `tl_step_N`
already use, and Streamlit builds `.st-key-<key>` from that key.

**The review step now offers the route it was only describing.** It counted
blank optional fields and then gave the trader no way to reach them.
`_ticket_html` returns `(html, blanks)` and the step renders one subordinate
`Complete N optional fields` action — not one per empty group, and not styled
to compete with Save, because none of those fields block saving. This moved
`_jump_to_context` above the step bodies: callbacks are bound while
`_STEP_BODIES[STEP]()` runs, which is before the action bar defines its own.

**One emoji retired**, the share Task 2's amendment assigned to this task: the
autofill success message carried a literal `✅` beside the icon `st.success`
already draws.

**Three guards mutation-checked**, each reverted in turn: the done circle back
to accent fails the pill test; dropping `min-height` fails the geometry test;
removing the action fails the completion test.

**Browser evidence — real coarse-pointer emulation with the pointer state
asserted at each coarse width:**

| Check | 1440 | 1024 | coarse 768 | coarse 375 |
|---|---|---|---|---|
| `innerWidth` | 1440 | 1024 | 768 | 375 |
| Rail on screen | yes | yes | no | no |
| Bottom nav on screen | no | no | no | yes |
| Both at once | **never** | never | never | never |
| Horizontal overflow | 0 | 0 | 0 | 0 |
| Undersized on-screen targets | 0 | 0 | 0 | 0 |
| Exceptions | 0 | 0 | 0 | 0 |

Round trip with a real 1200×700 PNG through `DOM.setFileInputFiles`, then
Continue → Back → Continue, at 1440 and coarse 375: **the draft count held at
`6 of 15` at every step**, matching the figure `8b35a6e` recorded, with zero
exceptions and an identical retained-chart `src` after Back. The stepper was
measured on step 4: **1 accent-filled circle, 0 accent connectors**, done
circles `rgb(21,35,41)` behind `rgb(92,110,119)`.

**Two driver corrections, both of which would have produced false evidence:**

1. **`innerWidth` must be re-read after navigation.** Metrics applied while
   `about:blank` is loaded describe `about:blank`, which has no viewport meta,
   so mobile emulation reports 981 whatever width was requested. The first
   coarse-375 pass reported 981 — it was measuring a desktop layout with a
   touch pointer. Re-applying metrics after load gives a true 375, and the
   driver now does this rather than leaving it to the caller.
2. **The undersized-target probe must exclude clipped elements.** It reported
   `stFileUploaderDropzoneInput` at 1×1 under `clip: rect(0,0,0,0)` at every
   width. That is the visually-hidden pattern — the styled dropzone carries the
   real target and the input stays keyboard-reachable. Excluding off-canvas,
   clipped, and transparent elements takes every width to 0.

**Verification:** `1820 passed, 7 skipped` (was `1813/7`); Ruff clean; Black
clean (83 files); `git diff --check` clean. The +7 is this task's tests. App
served from the canonical worktree, confirmed by reading the process's cwd
rather than assuming it — Task 2 measured the old palette by not checking.

**Files changed:** `design_system.py` (stepper tones, pending-state rule),
`ai_autofill_review.py` (pending container, emoji), `1_NewTrade.py`
(`_ticket_html` returns blanks, the complete action, `_jump_to_context` moved),
`tests/test_trade_wizard.py`, and this handoff. `git add -A` not used;
untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

**Unresolved concerns.**

1. **`TL_RULE = #AFBEC0` is still a light-surface value** — carried from Tasks
   1–3, still Task 12's.
2. **`theme.py`'s compatibility names still lie** (`PAPER` is a dark panel).
3. **Emoji remain on Journal, AI Reviews, and Strategy surfaces**, recorded by
   the Task 2 amendment against Tasks 9, 12 and 13. This task took only its own.

Ownership remains `CLAUDE`; continuing to Task 9 under the master directive.

### 2026-08-05 — Session boundary: paused at Task 8, lock released (Claude)

Documentation only. No product code changed in this entry — the last code
commit is `00d2359` (Task 7) and the tree is clean apart from the untracked
`src/tradelens/ui/.impeccable/`.

**Why the pause.** Tasks 5–7 each turned up a contract the plan had wrong, and
each was resolved and recorded rather than escalated. Tasks 8–17 are roughly
ten times the remaining work — New Trade, Journal, Analytics, the document
model, AI Reviews, Strategy and Settings, both Partner surfaces, the audit and
the re-score — and every one needs the same treatment: read the task,
test-first, discover the real runtime contracts, implement, browser-verify at
four widths, full suite, commit, log. Continuing in one stretch would have
produced exactly the thin commits the directive rules out.

**This is a session boundary, not a review gate.** No interim Codex review is
requested; the comprehensive review stays scheduled after Task 17. The lock is
`NONE` only so a fresh Claude session can claim it cleanly.

**What the next session needs, all recorded above rather than in context:**
the three Task 5–7 commits, the verified-green Task 4 interfaces, the two
user-approved deviations still in force (`compute_breakdown` for P&L-ranked
breakdowns; `killzone` as the session dimension with `KILLZONE_LABELS`), and
the architectural note that band logic belongs in the pure
`overview_bands.py` because `app.py` boots a page at import.

**Resume at Task 8.** Claim `Active writer: CLAUDE`, then follow the master
directive through Task 17.

### 2026-08-05 — Phase 2 Tasks 5–7: the Overview recomposed (Claude)

**Commits:** `243d0c9` (Task 5), `25616f9` (Task 6), `00d2359` (Task 7).
Tasks 8–17 not started.

Task 4's interfaces were verified against the plan before anything consumed
them — `RuleAdherenceSummary(followed, recorded, rate)`,
`EdgeLeakSummary(net_pnl, qualifying_trades, recorded_trades)`,
`PartnerContext`, `PartnerEvidenceSource`,
`build_global_partner_context(*, user_id)`, no Streamlit or Anthropic import —
and `tests/test_metrics.py` + `tests/test_partner_context.py` run green at
129 passed.

**The Overview is now five bands in five distinct forms**, in the spec's
reading order: a ruled KPI strip, a discipline panel, a dominant chart with
flanking figures, two ranked lists plus the calendar, and one editorial
readout. The anti-grid rule is enforced by a test asserting no two bands share
a builder, and by a second asserting the five appear in order.

**Honest-zero handling is the through-line.** Every band-2 measure has a way of
being unknown that is not zero: "Not recorded" adherence is distinct from a
real 0%; edge leak separates unknown, a clean sample, and rule-breaking that
netted exactly zero; consistency states how many more trades unlock it. Band 3
reads "No wins yet" rather than $0.00 when there are none. A positive edge leak
carries an explicit warning — verified in the browser on seeded data where
rule-breaking netted +$92,047.66.

**Four plan deviations, all forced by observed runtime behaviour**, all using
existing public services and all approved or recorded:

1. **`by_setup_type` cannot rank by P&L.** It is documented "No PnL or
   R-multiple metrics" and powers a stacked bar. Both ranked lists use
   `compute_breakdown`, which returns `total_pnl` already sorted. *(Approved.)*
2. **There is no `session` column** on the Overview frame. The product records
   `killzone`, which the spec names as the alternative; labels come from the
   same `KILLZONE_LABELS` map the ledger uses. *(Approved.)*
3. **`ActivationStatus` differs from the plan's sketch** — `is_activated` /
   `next_key` / `completed` / `total`, not a nested step object with
   `is_complete`. The plan says to adapt the caller, so the caller adapted.
4. **Max drawdown is signed in presentation.** `compute_max_drawdown` returns a
   positive magnitude by documented contract, which sat unsigned beside a
   positive edge leak and read as money made. The Codex-owned service is
   untouched; the sign is applied in the UI and pinned by its own test.

**A real gap found and closed:** the 0-trade welcome runs *before* the asset
filter, so a filter matching nothing rendered band 1 as a strip of zeros —
figures that read as a flat account rather than an empty scope. The bands are
now suppressed with the scope named and one control back.

**Three activation contracts were migrated, not weakened.** The
tenant-isolation guard still requires every activation input to be user-scoped
and now additionally asserts the whole computation is gated on an
authenticated user. The card-hiding test moved from grepping `app.py` for a
literal to exercising `next_review_action`, which is where the decision now
lives.

**Architecture note.** All band logic lives in the pure
`components/overview_bands.py`, not in `app.py`. `app.py` runs its entire
Streamlit script at module scope, so a unit test importing it boots a page and
needs a database — which is exactly what happened on the first attempt.

**Browser evidence, per task, at 1440 / 1024 / coarse 768 / coarse 375 with the
pointer state asserted at each coarse width:**

| Task | Result |
|---|---|
| 5 | Band 2 renders 4 untoned rows on the panel surface; 0 overflow, 0 exceptions |
| 6 | Bands 1–4 in order; two ranked lists with human-readable killzone labels, leader marked, chart present |
| 7 | All five bands in strict reading order |

**Verification:** `1813 passed, 7 skipped` (was `1711/7` after Task 3); Ruff
clean; Black clean (181 files); `git diff --check` clean; page boot checks 64
passed. Dev database untouched (`Jul 31`); all app and browser processes
stopped; no capture artifact entered the worktree; `.impeccable/` untouched.

**Remaining: Tasks 8–17.** New Trade, Journal, Analytics, the pure review
document model, AI Reviews, Strategy/Settings, both AI Partner surfaces, the
cross-page audit, and the 10K re-score. None started. The plan's Task 4
interfaces they depend on are verified present and green.

Ownership remains `CLAUDE`.

### 2026-08-05 — Phase 2 Task 4: service additions (Codex)

**Commit:** `3aa9e36`. Task 4 only. No UI, AI routing, authentication,
database-schema, secret, or model-service file changed.

**Produced interfaces:**

- `RuleAdherenceSummary(followed, recorded, rate)` and
  `rule_adherence_rate(trades)`;
- `EdgeLeakSummary(net_pnl, qualifying_trades, recorded_trades)` and
  `edge_leak_summary(trades)`;
- `PartnerEvidenceSource`, `PartnerContext`, and
  `build_global_partner_context(*, user_id)`;
- `MAX_CONTEXT_CHARS = 12000`, `MAX_EVIDENCE_SOURCES = 40`,
  `JOURNAL_HEADING`, `TRADES_HEADING`, and `STRATEGY_HEADING`.

The metrics distinguish unknown samples from known zero values without
changing `total_edge_leak()` for existing callers. The context adapter rejects
invalid owners before opening a session, repeats the owner predicate at every
trade hydration, reads the active profile through `get_active_strategy`, and
never calls the model or logs usage.

Prompt lines and evidence descriptors are admitted atomically under both
budgets. Oversized records are skipped rather than allowed to starve later
sections. Journal counts use the same stripped fallback logic as admitted
journal text, so whitespace-only process notes cannot hide a meaningful
fallback note or inflate the count.

**Plan hardening:** the plan did not cover embedded newlines in user-authored
notes, asset names, or Strategy Profile names. Those values are collapsed to
one line before prompt or evidence-label admission. A regression test proves
they cannot forge headings or extra evidence-looking bullet lines.

**Mutation checks:** removing the hydration owner predicate exposes the foreign
row and fails its dedicated test; restoring the truthiness note chain loses
fallback notes; counting SQL-prefiltered rows includes exotic whitespace. Each
mutation failed before the correct implementation was restored.

**Verification:** `38 passed` in `test_partner_context.py`; `91 passed` in
`test_metrics.py`; combined Task 4 `129 passed`; full suite `1757 passed, 7
skipped`; Ruff clean; Black clean (82 source/script files); `git diff --check`
clean. The development database was not used or modified; database tests used
an isolated in-memory SQLite database with `StaticPool`.

Ownership returned to `NONE`. Tasks 5, 14, and 15 are unblocked. Per the
user-approved master directive, Claude may now execute Tasks 5–17 continuously
and stop only for a genuine blocker or Codex-owned change.

### 2026-08-05 — Task 3 accuracy amendment; blocked on Task 4 (Claude)

**Commit:** `16a81ee`. Test naming and comments only — `design_system.py` is
byte-identical to Task 3's `5a03834`, verified with `git diff --quiet`.

**Two corrections, both requested at the Task 3 gate.**

1. **The 1.08:1 focus-ring claim is gone.** The allowlist note said
   `stBaseButton-secondary`'s default ring measured 1.08:1. That was disproven:
   `el.focus()` does not activate `:focus-visible` in Chrome, so the figure
   described `:focus`. Tabbing through 26 controls with our rule removed showed
   the default already clears 3:1. The note now gives the real rationale — the
   explicit rule pins focus to `TL_ACCENT_ACTION` rather than a framework
   default that can change between releases (spec §4.6).

2. **`test_each_alert_carries_primary_copy_on_a_semantic_tint` is renamed**
   `test_each_alert_kind_stays_readable_on_the_shared_quiet_ground`. There are
   no semantic tints: the implementation deliberately uses one shared elevated
   ground, because the container exposes its kind only through hashed `st-*`
   classes and differentiating it would need `:has()`. The docstring now
   describes what was built and why kind is carried by Streamlit's per-kind
   icon and by the sentence.

   **Its assertions are stronger, not weaker.** It still requires
   content-primary copy, and now also asserts that no kind recolours its own
   copy to a semantic hue and that the shared ground is the elevated surface.
   Mutation-checked by tinting the error alert's copy, which fails it.

**Verification:** `1711 passed, 7 skipped` — unchanged, which is the expected
result for a naming and comment amendment. Ruff clean; Black clean (177 files);
`git diff --check` clean.

**Blocked here, deliberately.** The master directive authorises Tasks 5–17
continuously and its closing line says to resume from Task 5, but the same
directive states: *"Do not start Task 5 until the handoff records Task 4 as
implemented, verified, committed, and released by Codex."* Checked in the tree:

| Task 4 artefact | Present? |
|---|---|
| `src/tradelens/services/partner_context.py` | **no** |
| `RuleAdherenceSummary` / `rule_adherence_rate` in `metrics.py` | **no** (0 occurrences) |
| `EdgeLeakSummary` / `edge_leak_summary` in `metrics.py` | **no** (0 occurrences) |
| `tests/test_partner_context.py` | **no** |

Task 5's band 2 consumes `rule_adherence_rate` and `edge_leak_summary`
directly, and the directive forbids both a UI-side substitute and duplicating
the calculation in page code. Starting Task 5 first would require one of them,
so the gate is honoured rather than worked around.

**For Codex.** The plan's Task 4 carries complete implementations and test
suites, executed against the real `metrics.py` while the plan was written:
34 `partner_context` tests and 15 metrics checks, with `_journal_text`,
`journal_entry_count`, atomic admission, and the tenant-scoped hydration guard
all mutation-checked. Ownership decisions are already settled there — the owner
validator is mirrored (matching `strategy.py`, `cost.py`, `app_settings.py`)
and the strategy profile is read through the public `get_active_strategy`, so
no other service file changes.

Ownership returned to `NONE`. **Next owner is CODEX for Task 4.** When the
handoff records Task 4 as released, the master directive authorises Claude to
claim the lock, verify the interfaces exist exactly as specified, run Task 4's
tests, and then execute Tasks 5–17 continuously with a separate commit per
task.

### 2026-08-05 — Phase 2 Task 3: controls and the eight interaction states (Claude)

**Commit:** `5a03834`. Task 4 not started, and it is Codex's.

**The plan's four given tests passed as written, before any change.** They are
regression guards, not drivers — the plan expected them to fail and they did
not. Rather than treat that as done, I audited what Task 3 actually had left:
eleven control families with no dark rule at all, and no focus or disabled
state on most of the styled ones. That audit produced 23 genuinely failing
tests, which is what the implementation was written against.

**Every selector was observed in the live DOM before a rule was written for
it**, by rendering a throwaway page containing each control the product uses.
That is this repo's standing rule for testids and it earned its keep: the
alert container turned out to expose its kind only through hashed `st-*`
classes, which changed the design.

**Newly styled, all previously bare:** text area, number input, checkbox,
slider, spinner, alerts, toasts. Fields now share one system — field surface
and hairline at rest, a border shift on hover, teal only on focus.

**Disabled and read-only are now distinguishable**, which they were not.
Disabled recedes to the canvas and takes the cursor with it; read-only keeps
content-primary text on the normal field surface, because its value is
information the trader is meant to read.

**Alerts use one quiet ground with content-primary copy.** Differentiating the
ground needs `:has()` to reach the container from the kind class inside it, and
the container's own kind is only in hashed classes. The kind is carried by
Streamlit's per-kind icon and by the sentence, so colour is not the sole
carrier either way — and a uniform ground is quieter.

**The 44px floor was driven by measurement, not assumption.** Measured under it
and corrected: `[data-baseweb="select"]` 40, `stNumberInputContainer` 40, its
steppers 38, `stFormSubmitButton` 40, and the dataframe toolbar at 22×22.
Re-measured after: **no undersized targets at 1440, 1024, 768 or 375.**

**Controls the product never renders — tabs, toggles, time inputs, data
editors, progress bars — are deliberately unstyled.** The plan's Step 3 lists
tabs and Step 4 says "every interactive control class"; CSS for a widget that
never appears is dead weight whose selector cannot be proven, and a blanket
`min-width` would have inflated small marks the spec says to leave alone.

**A correction to Task 2's evidence, which Codex approved partly on my word.**
Task 2 reported "real coarse-pointer" verification using
`Emulation.setEmulatedMedia` with pointer/hover features. **That call is
silently ignored by this Chrome** — I verified it directly: it leaves
`matchMedia('(pointer: coarse)')` false. Only `setTouchEmulationEnabled` plus
mobile device metrics flips the pointer media type.

Task 2's *conclusions* stand — its findings were width-driven — and I re-ran
the full 28-combination sweep under genuine coarse emulation, with an assertion
that the emulation took: **28/28 pass**, same nav pattern, same canvas, same
rail edge. But the claim "real media emulation, not desktop viewport resizing"
was not true when I made it. The drivers now assert the pointer state instead
of assuming it.

**A defect I reported to myself and then disproved.** A first focus probe
measured `stBaseButton-secondary` at 1.08:1 and I wrote a fix citing that
number. `el.focus()` does not trigger `:focus-visible` in Chrome — it was
measuring `:focus`. Re-measured by pressing Tab through 29 controls: every one
already showed a ring ≥3:1, and removing my rule left 26 controls still
passing. The rule is kept because spec §4.6 requires `TL_ACCENT_ACTION`
specifically and a framework default can change between releases — but its
comment now says that, not the false measurement.

**One existing contract needed refining, not weakening.**
`test_disabled_controls_keep_streamlits_dimming` forbids raising disabled copy
to primary, which is right. It fired on the read-only rule because
`:not(:disabled)` contains the substring. The guard now strips the negation
before deciding whether a rule targets disabled controls; mutation-checked by
raising a real disabled rule to primary, which still fails it.

**Browser verification:**

| Check | Result |
|---|---|
| 28 route/viewport combinations | pass, pointer emulation asserted |
| Undersized targets, 1440/1024/768/375 | **none** |
| Keyboard focus, 29 controls tabbed | all ≥3:1 |
| Coarse 375 | `pointer:coarse=true`, `hover:hover=false`, 0 overflow, 0 exceptions |
| Reduced motion | honoured, 0 elements still animating, 0 exceptions |

**Verification:** `1711 passed, 7 skipped` (was `1676/7`); Ruff clean; Black
clean (177 files); `git diff --check` clean. Dev database untouched (`Jul 31`);
all app and browser processes stopped; no capture artifact entered the
worktree.

**Files changed:** `design_system.py`, `tests/test_dark_workspace.py`,
`tests/test_design_system.py` (proven-testid allowlist),
`tests/test_premium_page_contracts.py`, and this handoff. `git add -A` not
used; untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

**A process note worth recording.** A `cat >>` ran with the shell's cwd reset
to the main checkout and created a stray `tests/test_dark_workspace.py` there.
The worktree file was untouched; the stray was deleted and the main checkout's
own modifications were left alone. Absolute paths for every write after that.

**Unresolved concerns.**

1. **`TL_RULE = #AFBEC0` is still a light-surface value** — carried from Task 1
   and Task 2. Belongs to Task 12, which restyles the Evidence Rail.
2. **`theme.py`'s compatibility names still lie** (`PAPER` is a dark panel).
3. **The dataframe toolbar fix was taken early from Task 9.** Its rule and
   allowlist entry are in place; Task 9's own step should find it already done.
4. **Checkbox, radio, slider and expander have no focus rule of ours.** The Tab
   probe shows the framework ring is adequate at ≥3:1, so nothing is broken,
   but they are not pinned to our token the way buttons and fields now are.

Ownership returned to `NONE`. **Task 4 is Codex-owned and must not be started
by Claude.**

### 2026-08-05 — Task 2 accuracy amendment (Claude)

**Commit:** `e21b9ba`, on top of `8919771`. Documentation and test naming only;
the source edits are comments. No UI behaviour changed. Task 3 not started.

**The guard's name claimed more than the guard checked.**
`test_no_structural_icon_is_an_emoji` reads as a statement about the product. It
checks three renderers: `render_empty_state`, `render_data_state`, and
Analytics' local `_empty` adapter. Renamed `test_no_empty_state_icon_is_an_emoji`,
with a docstring and a failure message that name the scope and name what it does
**not** cover.

**The handoff said "every emoji structural icon is a Material ligature".** That
was false. It now says every Phase 1 D9 **empty-state call site** was migrated,
which is what happened, and records the emoji-bearing controls that remain
against the tasks that own their surfaces:

| Surface | Remaining emoji | Owner |
|---|---|---|
| New Trade — autofill success, screenshot analyzer button and toasts | `✅`, `🔍` | Task 8 |
| Journal/trade detail toasts; corrections sidebar | `✅`, `🧠`, `💡`, `➕` | Task 9 |
| AI Reviews toasts and the `📝 AI Review` subheader | `✅`, `📝` | Task 12 |
| Strategy save toasts | `✅` | Task 13 |

They were not changed here on purpose: a toast icon or a button label is a
behaviour change, each sits on a surface a later task rebuilds, and Task 2 has
no browser evidence for any of them.

**Stale prose describing the opposite architecture, corrected.** The token change
falsified comments that were written for a light workspace and left describing it
as current:

- the Plotly template header ("Charts are DARK INSTRUMENTS inside the light
  workspace") — the reason a figure paints its own stage still holds, but not
  for that reason;
- the shared-component repaint note ("they carry the light workspace's ink by
  default");
- the hero note ("not reinstated on the light workspace");
- an Insights comment about `st.expander` on the light workspace;
- `test_app_and_marketing_site_share_one_brand_accent`'s docstring ("restated for
  the hybrid theme… the app is now a LIGHT workspace");
- `test_css_declares_the_hybrid_surface_variables` →
  `test_css_declares_the_role_surface_variables`;
- `test_navigation_rail_is_dark_and_workspace_is_light` →
  `test_the_rail_is_the_deepest_surface_and_the_canvas_sits_above_it` — both are
  dark now, so the assertion's premise moved: the separation is carried by the
  strong line, not by one being light;
- two `test_premium_page_contracts` docstrings.

Comments in `design_system.py` lines 54–57 were **kept**: they describe the
hybrid as something this commit *replaced*, which is accurate history rather
than a stale claim.

**Verification:** `1676 passed, 7 skipped` — unchanged, which is the expected
result for a naming and comment amendment. Ruff clean; Black clean (177 files);
`git diff --check` clean. Affected suites run directly: 328 passed across
`test_dark_workspace`, `test_design_system`, `test_premium_page_contracts`,
`test_premium_shell`, `test_insights_page`, `test_charts`.

**Files changed:** `design_system.py` and `6_Insights.py` (comments only),
`test_dark_workspace.py`, `test_design_system.py`,
`test_premium_page_contracts.py`, and this handoff. `git add -A` not used;
untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

Ownership returned to `NONE`. **Task 3 must not begin until Codex approves.**

### 2026-08-05 — Phase 2 Task 2: the shell retarget (Claude)

**Commit:** `8919771`. Task 2 only; Task 3 not started.

**The bridge is gone.** Task 1's compatibility aliases are deleted and every
rule now names a role token — **274 references**, not the 265 the first sweep
found. `design_system.py` is not the only file emitting `var(--tl-*)`:
`1_NewTrade.py` and `2_Trades.py` build inline styles for money colours and
captions, and those nine pointed at variables that no longer existed. An
undefined `var()` resolves to nothing and silently inherits, so this was
invisible until a test looked for it. A new guard scans every UI module and was
mutation-checked.

**The rail draws its edge with `TL_LINE_STRONG`.** Rail and canvas separate at
1.02:1, which no eye resolves. The one structural division present on every
screen has to be drawn rather than toned, and drawn at the weight that says
navigation is not work — the hairline is for things that belong together.

**Emoji in the D9 empty-state renderers (scope, stated precisely).** Every
Phase 1 D9 **empty-state call site** was migrated — the plan listed six, there
were nineteen. The first guard I wrote matched only `render_empty_state("x"` on
the following line and missed thirteen, including a whole page routing through a
local `_empty()` helper.

**This is not "every emoji in the product", and the guard no longer claims it
is.** `test_no_empty_state_icon_is_an_emoji` covers exactly three renderers —
`render_empty_state`, `render_data_state`, and Analytics' local `_empty`
adapter — and its docstring and failure message say so. Emoji-bearing controls
survive elsewhere and are left for the tasks that own those surfaces:

| Surface | Remaining emoji | Owner |
|---|---|---|
| New Trade — autofill success, screenshot analyzer button and toasts | `✅`, `🔍` | **Task 8** |
| Journal/trade detail toasts; corrections sidebar | `✅`, `🧠`, `💡`, `➕` | **Task 9** |
| AI Reviews toasts and the `📝 AI Review` subheader | `✅`, `📝` | **Task 12** |
| Strategy save toasts | `✅` | **Task 13** |

They were deliberately not modified here: each belongs to a surface a later task
rebuilds, and changing a control's label or a toast icon is a behaviour change
Task 2 has no browser evidence for.

Icons in scope are Material **ligature names** — plain escaped text styled by the
font the mobile nav already relies on. `:material/…:` cannot work here because
the icon is escaped into authored HTML, where it would render literally. All 13
names were verified in the browser to form real glyphs: 32px advance at 32px
font-size, against 167px for the same string as literal text. That matters
because Streamlit could have loaded a font subset; it has not. An absent icon now
emits no element rather than an empty 32px box.

Typographic **values** are deliberately untouched — `∞` for an undefined profit
factor, `▲▼■` deltas and ledger result marks, the stepper `✓`, `→` in link copy,
and `—` placeholders all carry meaning as text and are not icons.

**Browser verification — 28 route/viewport combinations, all pass:**

| Width | Canvas | Exceptions | Overflow | Rail | Bottom nav |
|---|---|---|---|---|---|
| 1440 | `rgb(9,18,22)` | 0 | 0 | visible | absent |
| 1024 | `rgb(9,18,22)` | 0 | 0 | visible | absent |
| coarse 768 | `rgb(9,18,22)` | 0 | 0 | absent | absent |
| coarse 375 | `rgb(9,18,22)` | 0 | 0 | absent | visible |

Rail edge computes to `rgb(92,110,119)` = `#5C6E77` at every width. The
navigation pattern matches the preflight's corrected mapping exactly, and rail
and bottom bar are never both visible — which required measuring **on-screen
geometry**, not `display`: at 375 Streamlit keeps the sidebar in the DOM,
translated `-256px` off-canvas.

**The auth widget overrides were measured and KEPT.** The instruction was to
remove them only if browser evidence proved them redundant. It proved them
*partly* redundant: card, inputs, labels and expander summary render identically
without them — same `rgb(236,245,244)` on `rgb(16,27,32)`, 15.78:1, zero
exceptions. But two rules still do work:

| | with | without |
|---|---|---|
| button text | `rgb(145,163,167)` | `rgb(236,245,244)` |
| placeholder | `rgb(145,163,167)` | `rgba(236,245,244,0.6)` |

The button one is load-bearing. Sign-in has one filled primary action and the
secondary control must stay quieter; without the override Streamlit paints both
at full content weight and the card reads as two primaries. Deleting 171 lines
on a partial result would have been a regression, so the evidence is recorded in
the source and the narrowing handed to **Task 13**, which owns the auth surface.

**Three measurement errors I made and corrected before drawing conclusions**,
recorded because each nearly became a false report:

1. Measured a block-level `<div>`'s width (690px) and read it as a broken
   ligature. It was the container; a Range around the text gives 32px.
2. Restarted the app from the main checkout instead of the worktree — the shell
   cwd resets between commands — and briefly measured the *old* palette.
3. Tested rail visibility with `display !== none`, which an off-canvas drawer
   passes. Only on-screen geometry answers that question.

**Test contract migrations.** Seven suites asserted the retired names. Two had
premises that no longer hold and were rewritten rather than repointed:
`test_no_semantic_hue_is_used_as_text_on_a_wash_or_mist` (the quiet grounds are
`*_DIM` now) and `test_trade_detail_uses_light_surface_tokens` → `..._dark_...`
(the card is a dark panel, so the reasoning inverts). `TL_LINE_STRONG` was added
to the neutral side-border set — "strong" is a weight, not a hue.

**Verification:** `1676 passed, 7 skipped` (was `1669/7`); Ruff clean; Black
clean (177 files); `git diff --check` clean. Dev database untouched (`Jul 31`);
all browser and app processes stopped; no capture artifact entered the worktree.

**Files changed:** `design_system.py`, `auth_screen.py`, `data_state.py`,
`app.py`, `1_NewTrade.py`, `2_Trades.py`, `4_Analytics.py`, `6_Insights.py`, and
four test modules. `git add -A` not used; untracked
`src/tradelens/ui/.impeccable/` deliberately not staged.

**Unresolved concerns.**

1. **`TL_RULE = #AFBEC0` is still a light-surface value.** Not in the deletion
   list or any contract test, so touching it stayed out of Task 1 and Task 2.
   It will read too bright on the Evidence Rail and belongs to Task 12.
2. **`theme.py`'s compatibility names still lie** — `PAPER` is a dark panel,
   `INK` is light text. Commented as such; they want retiring.
3. **Analytics was edited beyond Task 2's stated scope** — 19 empty-state icon
   replacements, 13 of them in `4_Analytics.py`, which Task 10 owns. The D9
   empty-state finding is one defect across files, and a guard covering the
   `_empty` adapter while thirteen of its call sites still passed emoji would
   have been false. Flagged so Task 10 knows the file moved.
5. **Emoji remain outside the empty-state renderers** — toasts, the screenshot
   analyzer button, the AI Reviews subheader, and the corrections sidebar. They
   are recorded above against Tasks 8, 9, 12 and 13 rather than changed here,
   because each is a control label or a toast on a surface a later task
   rebuilds.
4. **Empty states were not seen rendered.** The seeded database has 60 trades,
   so no empty state appeared in the sweep; the ligature mechanism was proved by
   injecting a real `.tl-empty-card` and measuring. Task 10 should confirm the
   real ones on a sparse database.

Ownership returned to `NONE`. **Task 3 must not begin until Codex approves.**

### 2026-08-04 — Task 1 amendment: chart template and auth z-scale (Claude)

**Commit:** `0b40b2e`, on top of Task 1's `dbae906`. Scope limited to the two
gate findings. Task 2 not started.

**1. Charts no longer resolve through `pio.templates.default`.**

That default is process-wide mutable state: import order decides it, any test
can swap it, and Streamlit sets its own. A figure that resolved correctly
through it was right by accident. `PLOTLY_TEMPLATE` is now pinned on
`_BASE_LAYOUT` and in `apply_chart_stage`, so the template travels with the
figure.

The old regression test proved nothing — it asserted against the global default,
which is exactly why it passed inside the suite and failed when run alone. The
rewrite sets the default to `plotly_white` first, builds a real figure, requires
the **embedded** template to still be the TradeLens stage, and restores the
global in a `finally` block with a post-condition assert so it cannot leak into
another test.

**2. `auth_screen.py` had the last raw z-index in the product.**

The card's bare `z-index: 1` is now `TL_Z_RAISED`, and the background photograph
and its scrim are `TL_Z_BASE` — the same ordering, stated in the one scale
everything else is measured against. The contract test now inspects `auth_css()`
as well as `build_css()`; a scale only one file is measured against is a
convention, not a contract. A second test pins bg < scrim < card explicitly, so
tokenising the layering cannot silently reorder it.

**Both mutation-checked.** Removing the explicit template fails the template
test; restoring `z-index: 1` fails both z-scale tests.

**3. Two stale comments the token change had falsified.** The
`apply_chart_stage` docstring still said "on the light workspace" — Codex named
this one. Reviewing it surfaced a second: `auth_screen.py` justified its
Streamlit widget overrides with "the workspace base is light", which is now the
opposite of true, and implies most of that block may be redundant now that
`base = "dark"`.

**The overrides were left in place.** Removing widget styling is a visual change
that needs a browser to confirm, and Task 1 has no browser evidence. The comment
now states that plainly and hands the deletion to Task 2.

**4. One assertion tightened rather than deleted.**
`test_charts_pin_the_stage_explicitly_so_streamlit_cannot_repaint_it` scanned
`repr(_BASE_LAYOUT)` for a transparent literal. Embedding the template object
put `rgba(0,0,0,0)` into that repr legitimately — from the template's own
internals, not from the stage. The repr scan was a proxy for "the stage keys are
not transparent", so it now checks those keys directly and additionally asserts
the template identity. The property is unchanged; the proxy was replaced.

**Verification.** Focused tests run individually and together, then the full
suite against the exact final state:

| Check | Result |
|---|---|
| 4 focused tests, one at a time | each 1 passed |
| theme + dark_workspace + charts + auth_screen + design_system | 169 passed |
| Full suite | **1669 passed, 7 skipped** |
| Ruff · Black · `git diff --check` | clean |

**Files changed:** `charts.py`, `auth_screen.py`, `tests/test_theme.py`,
`tests/test_dark_workspace.py`, and this handoff. `git add -A` not used;
untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

**Unresolved concerns carried forward from Task 1**, unchanged: no browser
evidence yet; `TL_RULE = #AFBEC0` still a light-surface value awaiting Task 2;
`theme.py`'s compatibility names still describe light surfaces. Added by this
amendment: the auth widget-override block is probably now redundant and should
be deleted in Task 2 once a browser confirms it.

Ownership returned to `NONE`. **Task 2 must not begin until Codex approves.**

### 2026-08-04 — Phase 2 Task 1: the dark token contract (Claude)

**Commit:** `dbae906`. Task 1 only; Task 2 not started.

**What shipped.** One role namespace (`TL_SURFACE_*`, `TL_CONTENT_*`,
`TL_LINE_*`, `TL_ACCENT_ACTION`) replaces the light workspace and the duplicate
legacy dark set. Superseded names are **deleted, not aliased** — an alias is how
two live systems came to coexist, and a deleted name raises ImportError at the
call site instead of silently changing meaning. 241 references across 5 source
and 6 test files were repointed. The `--tl-z-*` scale is defined and the three
arbitrary literals (1000, 20, 100) are migrated onto it.

**`TL_LINE_STRONG` is `#5C6E77`**, not the spec's original `#3A4E56`, which
measures 1.84–2.20:1 against a required ≥3:1. That was corrected in the
specification as amendment C6 before this task ran, so spec and code agree. The
contract test covers all six surfaces because `TL_SURFACE_ELEVATED` is the
binding case at 3.03:1.

**Three deviations from the plan's letter, all deliberate.**

1. **The skip link went to `--tl-z-overlay`, not `--tl-z-nav`.** The plan mapped
   the `1000` literal to the nav tier. Reading the selector, that literal is the
   keyboard skip link, which was above everything; putting it level with the
   rail lets DOM order decide whether it is reachable. Spec §12 requires full
   keyboard operation, and the spec outranks a line-level mapping in the plan.
2. **`.tl-mobile-nav` went to `--tl-z-nav`, not `--tl-z-sheet`.** Same cause: the
   plan's mapping was made from line numbers, and that selector is the bottom
   navigation itself, not the `More` sheet inside it.
3. **A CSS compatibility bridge was added.** The plan's Step 4 said *add* the
   role properties; my first pass also removed the old ones, which would have
   left every existing rule referencing undefined variables. The old CSS
   variable names now resolve to the new roles, clearly labelled, so the product
   renders between Task 1 and Task 2. **Task 2 must delete that block.** The
   Python names are still gone, so nothing can quietly keep importing them.

**Two defects found by executing, both fixed.**

- The skip link set `color: var(--tl-rail-ink)` — a variable defined nowhere,
  so it inherited onto a near-black background. Pre-existing, and invisible
  until the tokens were audited. A new test fails on **any** `var()` reference
  with no definition, and was mutation-checked by restoring the dangling name.
- `charts.py` carried two greys, muted and faint, one step apart. The role
  system has one secondary content colour and both now resolve to it. Recorded
  as an intended collapse: two greys differing by a hair carried no information
  a reader could use.

**Streamlit's own theme is now dark.** `.streamlit/config.toml` goes
`base = "dark"` with its four values pinned to the role tokens. Streamlit paints
its chrome from these, so leaving them light would have put two palettes on one
screen. Parity is tested.

**Grade chips** moved from the deleted light `PAPER` onto the dark panel, so the
A–F ramp re-points at the dark semantic family with brighter lime and orange
intermediates. All five clear 4.5:1 on the panel.

**Verification:** `1668 passed, 7 skipped` (was `1618/7`); Ruff clean; Black
clean (177 files); `git diff --check` clean. The +50 is 16 source-probe tests
and 37 dark-workspace contract tests, minus 3 hybrid tests deleted as
superseded.

**Files changed:** `.streamlit/config.toml`, `design_system.py`, `theme.py`,
`charts.py`, `auth_screen.py`, `2_Trades.py`; added `tests/source_probe.py`,
`tests/test_source_probe.py`, `tests/test_dark_workspace.py`; migrated
`test_design_system.py`, `test_theme.py`, `test_charts.py`,
`test_auth_screen.py`, `test_premium_page_contracts.py`. `git add -A` not used;
untracked `src/tradelens/ui/.impeccable/` deliberately not staged.

**Unresolved concerns for the gate.**

1. **No browser evidence yet.** Task 1 is a token change and the suite is green,
   but nothing has rendered in a real browser on this commit. Task 2's step 6 is
   the first browser check and will be the first proof the app looks right.
2. **`TL_RULE = #AFBEC0` was left alone.** It is a light-surface Evidence Rail
   colour, not in the spec's deletion list or the contract test, so touching it
   would have widened Task 1. On dark it will read too bright and belongs to
   Task 2, which restyles that component.
3. **`theme.py`'s public names now lie.** `PAPER` is a dark panel and `INK` is
   light text. They are compatibility re-exports with a comment saying so; Task
   2 retires them.
4. **`test_rendered_figures_resolve_to_the_dark_stage` is order-dependent.** It
   fails when run alone and passes in the full suite. Verified pre-existing by
   stashing this task's changes and reproducing it on the original code — not
   introduced here, but worth its own fix.

Ownership returned to `NONE`. **Task 2 must not begin until Codex approves.**

### 2026-08-04 — Journal hydration explicitly tenant-scoped (Claude)

Codex's last plan-gate blocker. Scope was Task 4 only.

**The finding was right, and so was the reason it needed its own guard.** The
journal hydration query filtered on `Trade.id.in_(wanted)` alone. Because
`wanted` is derived from an owner-scoped query, the output was correct — which
is precisely what made the gap invisible: `test_context_is_scoped_to_the_
authenticated_user` passes with or without the predicate.

**Fix.** The hydration is extracted into `_hydrate_journal_rows(db, owner,
wanted)` and filters on `Trade.user_id == owner` as well as the id set.
Extracting it is what creates a seam a test can reach; inline, there was no way
to hand the query a foreign id.

**Guard.** `test_hydration_refuses_a_trade_id_belonging_to_another_user` calls
the helper directly with another user's trade id — the thing the predicate
exists to refuse — and also checks a mixed list returns only the owner's row.
Two supporting tests cover requested-order preservation and the empty-selection
short circuit, which must not open a query at all.

**Mutation check, run both ways as Codex asked:**

| With `Trade.user_id == owner` removed | Result |
|---|---|
| Whole file | 1 failed, 36 passed |
| `test_context_is_scoped_to_the_authenticated_user` alone | **passed** — confirming it was insufficient |
| `test_hydration_refuses_a_trade_id_belonging_to_another_user` alone | **failed** — the only test that catches it |

**Verification, executed from the canonical worktree:**

| Artifact | Result |
|---|---|
| `tests/test_partner_context.py` | 37 passed |
| `tests/test_partner_turn.py` | 31 passed |
| Both together | 68 passed |
| Ruff / Black on all four files | clean |
| Plan code blocks parsing standalone | 40 of 41 |

Product code was copied into the worktree only to run and removed afterwards;
the tree is documentation-only and the `1618 passed, 7 skipped` baseline is
untouched. **No implementation has begun.**

**Files changed:** the plan and this handoff.

Ownership returned to `NONE`.

### 2026-08-04 — Task 4 and Task 14 amended for the final gate (Claude)

Scope was Task 4 and Task 14 only. The token, specification, layout, and Task 16
decisions were not reopened, and everything else in `f546922` is untouched.

**Task 14 — three containment boundaries, not one.**

`build_context(user_id=…)` now sits *inside* the containment. It opens a
database session, so it can fail with a driver error carrying a DSN, and that
failure was previously outside the `try` — it would have escaped as a raw
exception onto the page. A test raises a `psycopg2.OperationalError` carrying
`postgresql://tl:hunter2@…` and an `sk-ant-` key and asserts the question
survives, fixed copy is stored, the exception is logged exactly once, nothing
was billed, and no fragment of the DSN or key appears anywhere in state.

`log_ai_usage` is contained separately, **after** the reply is stored. Cost
logging is bookkeeping; a failed write must not discard an answer the trader has
already been given. The turn stays `ok=True`, `usage_logged` goes `False`, the
failure is logged, and no error slot is set — a rendered error would tell the
trader their answer failed when it did not.

**Task 14 — "Context used" is now per turn and persistent.**

Each assistant turn stores the labels it was answered from, so a rerun
re-renders the right records under the right answer instead of putting the
newest context under every one. Tests cover two successful turns with different
contexts plus a rerun, and an empty context storing no labels so no heading
renders.

`to_api_messages` then projects stored turns down to `role` and `content` before
the service sees them. Presentation metadata is ours; sending it would put
unrequested fields in the API payload and feed the model a list of record labels
as though it were conversation.

**Task 4 — one definition of a journal entry.**

`_journal_text` now strips each candidate *before* judging it. The previous
version tested truthiness first, so a `trade_process_notes` of `"   "` won the
`or` chain — a non-empty string is truthy — and a real `notes` value behind it
was silently lost. Process notes still take precedence when they say something.

`journal_entry_count` is computed with that same function rather than a SQL
count, so the number the trader is shown and the notes the prompt carries cannot
answer different questions. The SQL clause only narrows and is documented as
such: `TRIM` strips spaces but not tabs or newlines, so it cannot be the
authority.

**Six behaviours mutation-checked**, each reverted in turn to confirm the suite
fails: context assembly outside containment (3 failures), uncontained usage
logging (1), unprojected history (1), labels not stored per turn (2),
`_journal_text` back to the truthiness chain (4), and counting rows instead of
meaningful notes (1).

**One defect the verification caught.** The send-path test file imported
`partner_turn` by bare module name, which works in a scratch directory and
fails collection in the worktree. Corrected to the real path and re-run there.

**Verification, executed from the canonical worktree:**

| Artifact | Result |
|---|---|
| `tests/test_partner_context.py` | 34 passed |
| `tests/test_partner_turn.py` | 31 passed |
| Both together | 65 passed |
| Ruff / Black on all four files | clean |
| Plan code blocks parsing standalone | 40 of 41 |

Product code was copied into the worktree only to run and removed afterwards;
the tree is documentation-only and the `1618 passed, 7 skipped` baseline is
untouched.

**Files changed:** the plan and this handoff. The specification was not touched.

Ownership returned to `NONE`.

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
