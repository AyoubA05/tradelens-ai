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
- Current phase: `PHASE 1 SPECIFICATION COMPLETE — AWAITING CODEX REVIEW`
- Last completed work: Claude produced the Phase 1 UX specification at
  `docs/superpowers/specs/2026-08-03-phase1-dark-ux-specification.md`. Only
  documentation changed. No product implementation performed.
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
