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
- Current phase: `PHASE 1 SPEC FINAL — HANDED TO CODEX FOR REVIEW + FOUNDATION SYNC`
- Last completed work: Claude produced the Phase 1 UX specification at
  `docs/superpowers/specs/2026-08-03-phase1-dark-ux-specification.md`, ran the
  UI/UX Pro Max validation pass against it, then applied three owner-directed
  documentation corrections (spec §15.1 C1–C3): one testable date-series policy
  replacing an unsupported heatmap threshold, mutual exclusivity between the
  mobile `More` and AI Partner sheets with navigation outranking the Partner in
  the z-scale, and two stale cross-references. Only documentation changed. No
  product implementation performed.
- Next owner: `CODEX`
- Next work: (1) review the specification for scope, AI safety, and tenancy
  implications; (2) answer the five open questions in spec §15; (3) integrate
  the separately committed Opus 5 migration; (4) repair the UTC-sensitive cost
  test and return a fully green baseline.
- Blocker: the Opus 5 migration is staged only in the main checkout and is not
  present on this branch. Creative implementation must not start from the stale
  model-routing baseline. This worktree's `CLAUDE.md` still declares
  `claude-fable-5` + `claude-haiku-4-5`; `main` declares single `claude-opus-5`.

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
