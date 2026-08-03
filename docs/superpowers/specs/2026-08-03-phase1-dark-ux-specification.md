# TradeLens AI — Phase 1 Dark Workspace UX Specification

**Date:** 2026-08-03
**Author:** Claude Code — specification-only phase
**Design review:** `ui-ux-pro-max`. §0.4 records exactly which of its commands were run,
when, and which recommendations were adopted or rejected. The first draft applied the skill's
static Quick Reference guidance only; its search database was run afterwards as a bounded
validation pass, and §15 records the amendments that pass produced.
**Branch:** `codex/full-dark-streamlit-redesign`
**Worktree:** `/Users/ayoub/tradelens-ai/.claude/worktrees/codex+full-dark-streamlit-redesign`
**Status:** Specification. No product code changed. Implementation requires Codex review first.

---

## 0. What this document is

This is the design source of truth for the full-dark Streamlit redesign. It absorbs the
988-line implementation plan (`2026-07-31-streamlit-dark-workspace-ai-review.md`) and the
scope amendments in `docs/coordination/CLAUDE_CODEX_HANDOFF.md`. Where the older plan and
the handoff conflict, **the handoff wins** and this document records the resolved position.

The implementation plan will be rebuilt from this spec after Codex approves it. Until then
the older plan remains valid for its task sequencing, test-first discipline, and review
gates — none of which this spec replaces.

### 0.1 Resolved conflicts

| # | Older plan | Handoff amendment | Resolved position |
|---|---|---|---|
| 1 | "No chat interface… is added" (line 70) | §1, §3 approve a global Partner | **Global bottom-right AI Partner ships in Phase 1**, via existing `partner_reply(per_trade_qa=False)` only |
| 2 | Task 4 preserves today's Overview order; "no quick-action card grid" | §3 approves the expanded curated Overview | **Expanded fixed Overview** per §3. The "no card grid" prohibition survives and is strengthened in §5 below |
| 3 | "Do not change `src/tradelens/services/`" (line 20) | §2 adds `rule_adherence_rate(df)` | One Codex-authored addition to `services/metrics.py`. **Claude writes no service code** |
| 4 | Preflight worktree `../tradelens-dark-workspace`, branch `codex/dark-workspace-ai-review` | Canonical worktree/branch | Canonical worktree and branch named above |
| 5 | Task 11 re-scores against the 10K Checklist | — | Retained. Acceptance criteria in §13 |

### 0.2 Constraints inherited unchanged

Every global constraint in the older plan (lines 13–37) still binds. The load-bearing ones
for this spec:

- One fixed tonal-dark theme. No theme switcher.
- Never `unsafe_allow_html=True` for model output. Generated prose goes through
  `st.markdown` with HTML disabled.
- No React, no FastAPI, **no JavaScript injection**, no new CSS framework, no new icon
  library, no new runtime dependency.
- All colour/type/space/radius/shadow/motion values live in `design_system.py`. Pages
  consume tokens; pages never declare colour literals.
- Red = losses, destructive actions, errors. Green = profit or confirmed success. Teal =
  action and focus. Colour is never the sole carrier of meaning.
- All visible interactive targets ≥ 44×44 CSS px at 1440 / 1024 / coarse 768 / coarse 375.
- Honour `prefers-reduced-motion: reduce`. Motion is opacity/transform only, 120–200 ms,
  shared ease-out. Never animate charts, long tables, validation, focus, or page load.
- AI stays post-trade, reflective, evidence-backed. No signals, predictions, entries,
  position instructions, or financial advice — including in UI copy.

### 0.3 Known gaps in this spec

Stated rather than hidden:

1. **No baseline browser evidence.** The handoff's required sequence puts this
   specification at step 6, after the Opus 5 migration lands, the UTC cost test is fixed,
   the suite is green, and the browser preflight is captured. This spec was written at the
   owner's direction before steps 1–5. Every current-state observation below comes from
   reading source, not from a live render. Implementation must verify against a real app.
2. **TradeZella reference images were not available.** They did not reach the specification
   session. Direction below derives from the plan's explicit written direction and the
   constraint that TradeZella is a layout/interaction reference only — never its brand,
   purple palette, scoring model, iconography, or copy. If the images are supplied,
   reconcile §5 and §7 against them before implementing.
3. **`services/metrics.py` needs one Codex addition** (`rule_adherence_rate`). Overview
   band 2 is blocked on it. Everything else in the Overview is already computable.

---

### 0.4 Design-review provenance

Recorded so this is auditable rather than asserted.

**First draft.** The `ui-ux-pro-max` `SKILL.md` text was in context and its Quick Reference
rules were applied directly — traceably producing finding D9 (`no-emoji-icons`), the ranked-list
form in band 4 (`no-pie-overuse`), the contrast floors, the 44 px target rule,
`color-not-only`, and the reduced-motion constraints. **The skill's search database was not
queried, and the skill was not invoked through the Skill tool.** The original header credited
it as reviewer, which overstated that.

**Bounded validation pass, 2026-08-03.** Skill invoked through the Skill tool, then:

```bash
python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py \
  "post-trade trading journal analytics dashboard dark data-dense" \
  --design-system --variance 4 --motion 2 --density 8 -p "TradeLens AI" -f markdown

python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py \
  "animation accessibility z-index loading" --domain ux -n 14

python3 ~/.claude/skills/ui-ux-pro-max/scripts/search.py \
  "dashboard trend comparison heatmap calendar equity drawdown" --domain chart -n 8
```

**Adopted** (amendments in §15): the z-index scale and stacking-context verification (§4.5,
D13); heatmap divergent scale, numeric legend, pattern fallback, sparse-month gate, and grid
table (§5.5); the AAA threshold-legibility rule for band 2 (§5.3).

**Independently validated, no change needed:** `--domain chart` puts the line-chart floor at
"fewer than 4 data points → use a stat card", matching the existing
`sample_state.show_dominant_series` gate exactly. The `--design-system` style resolved to
*Modern Dark*, whose stated best-fit includes "fintech/trading dashboards", and its effects
note "avoid pure `#000000` (OLED smear)" — both confirm the tonal-dark-not-black direction and
the `#091216` canvas. The `--tl-space-*` ramp (4/8/12/16/20/24/32/48) already matches a
density-8 dashboard rhythm.

**Rejected, with reasons.** The generator is tuned for React Native marketing surfaces and much
of its output conflicts with locked decisions:

| Recommendation | Rejected because |
|---|---|
| Palette `#1E40AF` blue primary, `#F8FAFC` light background | Conflicts with the locked teal-on-charcoal identity and the fully-dark direction. The prior audit scored the existing colour system 8.5/10 and said keep it |
| Fira Code / Fira Sans | Schibsted Grotesk + Satoshi + JetBrains Mono scored 9/10 and are brand-established. The recommended *mood* ("dashboard, data, analytics, technical, precise") already describes them |
| Glassmorphism, BlurView, ambient light blobs, glow | The plan forbids decorative blur and the prior audit flagged ambient glow drift for removal. `blur-purpose` restricts blur to background dismissal |
| GSAP page transitions, spring modals, `scale 0.97` press | No JavaScript injection, no new dependency. Motion is capped at 120–200 ms opacity/transform |
| Haptics | Not available to Streamlit in a browser |
| "Real-Time / Operations Landing" pattern, nav CTA, trial CTA | A marketing-landing pattern. This is an authenticated product surface, and the marketing site is explicitly out of scope |
| Radar/spider for multi-attribute comparison | Its own guidance routes precise comparison to grouped bar; ranked lists retained (§5.5) |
| Bullet chart form for band 2 | Requires a defined target range, which TradeLens does not have. The accessibility rule it embodies was adopted; the form was not (§5.3) |

---

## 1. Current-state audit

Read from source in this worktree. File sizes: `design_system.py` 2858, `1_NewTrade.py`
1163, `ai_autofill_review.py` 881, `2_Trades.py` 874, `4_Analytics.py` 824, `charts.py` 744,
`6_Insights.py` 628, `app.py` 527, `auth_screen.py` 501, `9_Settings.py` 450, `5_Strategy.py`
403, `workspace.py` 364, `sidebar.py` 343.

### 1.1 What is already good and must survive

The primitive layer in `components/workspace.py` is the strongest asset in the codebase and
this spec builds on it rather than around it. It is pure (no Streamlit import), escapes every
caller value, emits one root element per renderer, and takes pre-formatted strings so no
presentation helper silently re-rounds a number. Existing builders:

`render_workspace_header` · `render_kpi_strip` · `render_evidence_rail` ·
`render_research_finding` · `render_research_note` · `render_note_skeleton` ·
`render_editorial_readout` · `render_filter_summary` · `render_section_header` ·
`render_evidence_disclosure`

Also already correct and not to be disturbed:

- **Tone reaches non-colour readers.** `render_kpi_strip` injects a visually hidden
  "Up:"/"Down:"/"Needs attention:" before the figure. `data-tone` is for styling and tests
  only and carries no meaning to assistive tech.
- **Confidence defaults downward.** `_confidence()` clamps unknown values to `low`, so an
  unrecognised level is never presented as more certain than it is.
- **Evidence-used is a native `<details>`.** Keyboard-reachable, no script, 44 px summary.
- **Undefined maths reads as N/A, not 0.** Profit factor 0/0 → `N/A`; wins with no losses →
  `∞`. `_money()` returns `N/A` for missing, never a bare `0`, never `--`.
- **Sparse data suppresses claims.** `sample_state()` gates the dominant equity curve below
  four dated points and states what unlocks it. `data_state.leading_category` owns the
  decision of what is true; pages only word it.
- **Exception containment is real.** Domain errors (`WeeklyReviewError`, `DebriefError`)
  carry trader-safe copy and are shown. Anything else is logged and replaced with fixed
  recovery copy, because driver text can carry a DSN or key.
- **Mobile `More` is a native `<details>`** with `<summary>` focusable, toggling on Enter or
  Space with no script, and it marks itself active when the current page lives inside it.

### 1.2 Defects and hazards found

| # | Severity | Finding | Location |
|---|---|---|---|
| D1 | High | **Two live colour systems.** A light workspace (`TL_CANVAS #F3F6F6`, `TL_PAPER`, `TL_MIST`, `TL_INK`, `TL_MUTED`, `TL_HAIRLINE #D9E2E2`, `TL_ACTION #087C71`, `*_INK`, `*_WASH`) coexists with a legacy dark one (`TL_BG #0d1117`, `TL_SURFACE`, `TL_SURFACE_2`, `TL_BORDER`, `TL_TEXT #e8eaed`, `TL_TEXT_MUTED #848d9c`, `TL_PRIMARY #00e5cc`, `TL_SUCCESS`, `TL_DANGER`, `TL_WARNING`, `TL_NEUTRAL`), plus dark islands inside the light app (`TL_RAIL #0F171B`, `TL_CHART_STAGE #101A1E`, `TL_FOCUS`) | `design_system.py:70–144` |
| D2 | High | **Name collision in the planned retarget.** The plan assigns new dark values to `TL_CANVAS`, `TL_TEXT`, `TL_TEXT_MUTED`, `TL_HAIRLINE`, `TL_RAIL`, `TL_CHART_STAGE` — six names that already exist with different values. Any consumer not migrated in the same commit silently flips meaning | `design_system.py` vs plan `1.2` |
| D3 | High | **`TL_MUTED #5B6A70` fails AA on every proposed dark surface** (2.87–3.42:1). It is the current light-workspace secondary text. Any component still importing it after the retarget becomes non-compliant with no test failure unless a test names it | computed, §4.3 |
| D4 | Medium | **Rail and canvas separate at 1.02:1.** `#071014` vs `#091216` is not distinguishable by luminance. The plan's Task 2 requires them "visually distinct"; surface tone alone cannot deliver it | computed, §4.3 |
| D5 | High | **Daily Debrief regeneration destroys the prior note.** `_render_daily_lens` pops `cache_key` *before* calling `_run_daily_debrief`, so a failed regeneration loses the review the trader already had. Weekly Recap does this correctly (keeps the note, replaces on success) | `6_Insights.py:576–580` |
| D6 | High | **Weekly and Daily notes render as one undifferentiated wall.** `_render_generated_note` emits `content_md` through a single `st.markdown`. No thesis separation, no section index, no limitations block, no next-review-actions block. Only the Patterns lens gets the structured `ResearchNote` treatment | `6_Insights.py:264–304` |
| D7 | Medium | **Inconsistent stats strip across lenses.** `_note_stats` renders a 5-cell strip for Weekly and Daily; Patterns renders none | `6_Insights.py:222–261, 319` |
| D8 | Medium | **Regeneration has no "updating" state.** Weekly's regenerate button is not disabled during the call and shows no inline progress; the skeleton only appears on first load | `6_Insights.py:478–491` |
| D9 | Medium | **Emoji used as structural icons.** `📓`, `📈`, `◆` are passed as `render_empty_state` icons; one call passes `""`. Emoji are font-dependent, not themeable, and cannot be token-controlled | `app.py:272,470,505`; `6_Insights.py:158,326,463` |
| D10 | Medium | **False zeros are indistinguishable from real ones.** `compute_basic_metrics` returns `avg_win`/`avg_loss` as `0.0` when there are no wins/losses. `total_edge_leak` returns `0.0` both for "no leak" and "signal columns absent". `consistency_score` needs ≥5 trades (`_MIN_TRADES_FOR_CONSISTENCY`) | `metrics.py:68–83, 1036–1073, 1085` |
| D11 | Low | **`rule_adherence_rate` does not exist.** Only a private `_is_followed` helper. Overview band 2 depends on the Codex-owned public function from handoff §2 | `metrics.py:1089` |
| D12 | Low | **AI Partner is trade-scoped only.** `ai_trade_chat.render_ask_ai` is imported by `2_Trades.py` alone; history lives in `session_state` and is never persisted | `ai_trade_chat.py`, `2_Trades.py:33` |
| D13 | High | **No z-index scale.** Three arbitrary literals (`1000`, `20`, `100`) and zero `--tl-z-*` tokens. The Partner overlay cannot be layered safely, and `1000` is an arbitrary ceiling that invites `1001` next. Found by the §0.4 validation pass | `design_system.py:515, 2075, 2519`; resolved §4.5 |

### 1.3 Current information architecture

Seven authenticated destinations plus the auth surface.

```
Auth (gate)  ── login / create account toggle, reset-request + reset-complete panel
│
├── Overview            app.py                 masthead → filter → KPI strip → next step
│                                              → [standing+calendar | equity+readout]
│                                              → recent trades
├── New Trade           1_NewTrade.py          5-step wizard, one progress system
├── Journal             2_Trades.py            radio: Trades | Calendar | Trade Detail
├── Analytics           4_Analytics.py         radio: Performance | Risk | Timing | Setups
├── AI Reviews          6_Insights.py          radio: Patterns | Weekly Recap | Daily Debrief
├── Strategy Profile    5_Strategy.py          playbook form, 5 accordions
└── Settings            9_Settings.py          Profile | Preferences | Data | Danger Zone
```

Navigation: sidebar rail ≥1024 px; bottom nav with 4 slots + native `<details>` `More`
sheet below 768 px. Breakpoints in `design_system.py`: `max-width: 767px`,
`max-width: 1023px`, `min-width: 768px`, `min-width: 560px`, container `max-width: 1320px`.

**The IA is correct and this spec does not change it.** Every destination survives. The AI
Partner is added as a persistent overlay, not a new destination.

---

## 2. Remove · Retain · Combine · Demote

### Remove

| Item | Why |
|---|---|
| Light-workspace tokens from all active selectors (`TL_PAPER`, `TL_MIST`, `TL_INK`, `TL_MUTED`, light `TL_CANVAS`, light `TL_HAIRLINE`, `TL_ACTION`, `*_INK`, `*_WASH`) | Superseded. Retain values in documentation history only |
| The duplicate legacy dark set (`TL_BG`, `TL_SURFACE`, `TL_SURFACE_2`, `TL_BORDER`, `TL_BORDER_SUBTLE`, `TL_TEXT_FAINT`) | Collapses into the one role set in §4 |
| Emoji as structural icons (D9) | Replace with the existing Material symbol convention already used by `sidebar.py` (`more_horiz`), or a token-styled glyph. No new icon dependency |
| Cache-clearing before regeneration in Daily Debrief (D5) | Destroys work on failure |
| The single-`st.markdown` note wall (D6) | Replaced by the shared reading shell in §7 |
| Any second filled primary action in the rail | One primary per viewport |

### Retain unchanged

The entire `workspace.py` primitive contract · exception containment and the domain/unexpected
error split · `sample_state` gating and `leading_category` ownership of truth · N/A and ∞
conventions · visually hidden tone announcements · downward confidence clamping · native
`<details>` for `More` and evidence-used · the 5-step wizard's session-state ownership · the
three Journal interaction paths · the four Analytics lenses · Strategy's 6-of-6 completion
truth and 5 accordions · Settings' four sections and contained Danger Zone · tenant scoping
on every service call.

### Combine

| Combine | Into |
|---|---|
| `design_system.render_section_header`, `ui.section_header`, `workspace.render_section_header` | Already delegating to one builder — keep it that way and add no fourth |
| Patterns' `ResearchNote` path and Weekly/Daily's `content_md` path | One reading shell (§7), fed by two adapters |
| `_note_stats` (Weekly/Daily) and Patterns' absent strip (D7) | One period strip on all three lenses |
| Overview's `render_next_step` activation card and `_overview_observation` readout | One "next review action" band (§5, band 5) |

### Demote

| Item | From | To |
|---|---|---|
| Today / This week P&L | Its own `render_section_header` + strip | Two cells inside band 1, subordinate to the five headline measures |
| Asset filter | An expander above the numbers | Collapsed control + the existing one-line `render_filter_summary` |
| Lens radio (Analytics, AI Reviews) | Visually competing with content | Secondary to the current question's `render_section_header` |
| Demo/sample labelling | Full-width banner | Masthead eyebrow (already done in `app.py`; apply everywhere) |
| Evidence-used | Inline prose | Collapsed `<details>` below the Evidence Rail |

---

## 3. Information architecture and page hierarchy

No destination is added, removed, renamed, or reordered. The AI Partner is a persistent
overlay available on all seven authenticated destinations and absent from the auth surface.

```
┌─ Shell (all authenticated pages) ────────────────────────────┐
│  Rail ≥1024  |  Bottom nav + More sheet ≤767                 │
│  Masthead: eyebrow · title · subtitle · meta                 │
│  ─────────────────────────────────────────────────────────   │
│  Page body                                                   │
│  ─────────────────────────────────────────────────────────   │
│  AI Partner launcher — fixed bottom-right (§8)               │
└──────────────────────────────────────────────────────────────┘
```

Every page follows one hierarchy contract:

1. **Masthead** — what this page is, what qualifies it, what period it covers.
2. **Scope** — filter control (collapsed) plus a one-line active-scope summary.
3. **Answer** — the page's primary readout, given the highest visual weight on the page.
4. **Support** — ranked evidence, secondary instruments, ledgers.
5. **Interpretation** — an editorial readout with its Evidence Rail, where the page earns one.

A page may omit steps but may not reorder them.

---

## 4. Dark-theme token roles

### 4.1 Naming rule (resolves D1, D2)

The retarget must not reuse a name whose meaning changes. Introduce a **new, unambiguous
role namespace** and retire the old names in the same commit:

```python
TL_SURFACE_CANVAS      = "#091216"   # quiet page background
TL_SURFACE_RAIL        = "#071014"   # deepest structural surface
TL_SURFACE_PANEL       = "#101B20"   # tables, filters, forms, composed sections
TL_SURFACE_ELEVATED    = "#152329"   # selected controls, overlays, important readouts
TL_SURFACE_CHART       = "#0C181D"   # Plotly stage
TL_SURFACE_FIELD       = "#122026"   # inputs and selectors
TL_CONTENT_PRIMARY     = "#ECF5F4"   # main copy and values
TL_CONTENT_SECONDARY   = "#91A3A7"   # descriptions and metadata
TL_LINE_HAIRLINE       = "#26373D"   # structure without card-box noise
TL_LINE_STRONG         = "#3A4E56"   # meaningful boundaries, rail edge  (new, see D4)
TL_ACCENT_ACTION       = TL_PRIMARY  # existing bright TradeLens teal — unchanged
```

`TL_PRIMARY`, `TL_SUCCESS`, `TL_DANGER`, `TL_WARNING` and the type/space/radius/motion ramps
keep their names and values. Semantic aliases (`tone-positive`, `tone-negative`,
`tone-warning`, `conf-low|medium|high`) keep their names and re-point to the roles above.

**Superseded** names — the light-workspace set and the duplicate legacy dark set listed in §2
— are **deleted, not aliased**. An alias is how D1 happened; a deleted name produces an import
error at implementation time, which is the outcome we want. This deletion rule does not apply
to `TL_PRIMARY`, `TL_SUCCESS`, `TL_DANGER`, `TL_WARNING`, or the type/space/radius/motion
ramps: those are not superseded, keep their names and values, and may be referenced by the new
roles (as `TL_ACCENT_ACTION` does above).

### 4.2 CSS custom properties

One `:root` block, mirroring the Python roles:

```
--tl-surface-canvas   --tl-surface-rail    --tl-surface-panel
--tl-surface-elevated --tl-surface-chart   --tl-surface-field
--tl-content-primary  --tl-content-secondary
--tl-line-hairline    --tl-line-strong     --tl-accent-action
```

### 4.3 Verified contrast (computed, WCAG 2.x relative luminance)

Foreground against each surface. `*` marks below 4.5:1.

| Foreground | canvas | rail | panel | elevated | chart | field |
|---|---:|---:|---:|---:|---:|---:|
| `TL_CONTENT_PRIMARY` `#ECF5F4` | 17.06 | 17.32 | 15.78 | 14.52 | 16.27 | 15.02 |
| `TL_CONTENT_SECONDARY` `#91A3A7` | 7.21 | 7.32 | 6.67 | 6.13 | 6.87 | 6.35 |
| teal `#00e5cc` | 11.79 | 11.96 | 10.90 | 10.03 | 11.24 | 10.38 |
| success `#22c55e` | 8.30 | 8.43 | 7.68 | 7.07 | 7.92 | 7.31 |
| danger `#f56565` | 6.25 | 6.34 | 5.78 | 5.31 | 5.96 | 5.50 |
| warning `#f59e0b` | 8.81 | 8.94 | 8.15 | 7.50 | 8.40 | 7.76 |
| **legacy `TL_MUTED` `#5B6A70`** | **3.37*** | **3.42*** | **3.12*** | **2.87*** | **3.21*** | **2.97*** |

The plan's own contract test (`TL_TEXT_MUTED` ≥ 4.5:1 on canvas and panel) **passes** with
`#91A3A7` at 7.21 and 6.67. Every semantic colour clears AA on every surface.

`TL_MUTED` fails everywhere (D3). The contract test must name it explicitly and fail if it
appears in any active workspace selector.

### 4.4 Surface separation is not a contrast problem (resolves D4)

| Pair | Ratio |
|---|---:|
| rail vs canvas | 1.02 |
| panel vs canvas | 1.08 |
| panel vs elevated | 1.09 |

These are correct for tonal design and must not be "fixed" by pushing surfaces apart — that
produces the dark-cards-on-dark-cards effect the plan forbids. The consequence is a hard rule:

> **Surface tone may never be the only thing separating two regions.** Every boundary that
> carries meaning is drawn with `TL_LINE_HAIRLINE`, or `TL_LINE_STRONG` where the boundary is
> load-bearing (the rail's inner edge, a Danger Zone perimeter, a drawer edge). Structure
> also comes from spacing and type scale, not from more boxes.

`TL_LINE_HAIRLINE` is 1.53:1 on canvas — fine for a decorative rule, insufficient where a
line is the sole indicator of a control boundary. `TL_LINE_STRONG` exists for that case and
must clear 3:1 against both adjacent surfaces.

### 4.5 Z-index scale (resolves D13)

**There is no z-index scale today.** `design_system.py` contains three arbitrary literals —
`z-index: 1000` (line 515), `20` (line 2075), `100` (line 2519) — and zero `--tl-z-*` tokens.
This is the `z-index-management` anti-pattern at High severity, and the AI Partner overlay
cannot be layered safely against it.

Define an explicit ordered scale, and forbid literals outside it:

```
--tl-z-base       0    page content
--tl-z-raised    10    sticky section headers, table headers
--tl-z-partner   20    AI Partner launcher and drawer
--tl-z-nav       30    navigation rail, bottom nav
--tl-z-sheet     40    mobile More sheet
--tl-z-overlay   50    blocking confirmations
```

**Navigation always outranks the Partner.** The Partner is the lowest overlay in the scale, so
it can never layer over the rail, the bottom nav, or the `More` sheet. A trader must never have
to dismiss a chat surface to reach navigation. The Partner is below blocking confirmations for
the same reason — a destructive confirmation must never be obscured by a chat surface.

On desktop the drawer is on the right and the rail is on the left, so the ordering never bites
geometrically; one scale therefore serves both widths with no per-breakpoint override.

**Stacking-context verification is required, separately from the `position: fixed` check in
§8.2.** A new stacking context resets z-index, so a correct scale value still loses if an
ancestor isolates it. Any ancestor carrying `z-index` with `position` other than `static`,
`transform`, `filter`, `opacity` below 1, `will-change`, `contain`, or `isolation` creates one.
Verify the Partner renders above the rail, the bottom nav, and the `More` sheet in a live
browser — not by reasoning about the scale alone.

Existing literals migrate to the scale in the same commit. `1000` in particular must be
replaced, not preserved: an arbitrary ceiling is how the next overlay ends up at `1001`.

### 4.6 Focus

Focus rings use `TL_ACCENT_ACTION` at ≥3:1 against the surface behind them (teal clears 10:1
on every surface). Focus is never removed, never animated, and never hover-gated. Because a
Streamlit rerun can move focus, no interaction may depend on focus persisting across a rerun.

---

## 5. Overview — curated fixed hierarchy

### 5.1 Principles

The Overview is a **fixed editorial composition**, not a widget surface. There is no
customisation, no drag, no add-a-card. Handoff §3 explicitly withholds authorisation for a
widget builder or a generic card wall.

The anti-grid rule is structural, not stylistic: **each band takes a different visual form.**
Five bands, five forms. A trader's eye cannot get lost in a rhythm of identical tiles because
there is no such rhythm.

| Band | Question | Form |
|---|---|---|
| 1 Current standing | Where do I stand? | One ruled KPI strip |
| 2 Risk and discipline | Can I trust this? | Discipline panel — figure + inline micro-chart pairs |
| 3 Performance trajectory | How did I get here? | One dominant chart with flanking figures |
| 4 Recurring edge | What repeats? | Two ranked lists + a calendar heatmap |
| 5 Next review action | What do I do about it? | One editorial readout + one link |

Reading order is top to bottom and is the argument: standing, then whether the standing is
trustworthy, then how it was reached, then what recurs, then the single action.

### 5.2 Band 1 — Current standing

**Form:** the existing `render_kpi_strip`, five cells, hairline-divided. Not five cards.

| Cell | Source | Notes |
|---|---|---|
| Net P&L | `compute_basic_metrics.total_pnl` | Signed, toned, detail = trade count |
| Win rate | `.win_rate` | Detail = `{wins} of {total}` |
| Expectancy | `compute_expectancy` | Signed, toned |
| Profit factor | `compute_profit_factor_raw` | `N/A` for 0/0, `∞` for wins-no-losses |
| Trades | `.total_trades` | Plain count, never toned |

Today / This week P&L demote to a second, quieter two-cell strip inside this band (§2).

**Retain exactly:** the N/A and ∞ conventions, `_money()` never emitting a bare 0, and the
visually hidden tone announcement.

### 5.3 Band 2 — Risk and discipline

**Form:** a discipline panel. Four measures, each a figure paired with a small inline
indicator, on `TL_SURFACE_PANEL` with hairline dividers. Not four cards, not a KPI strip —
the inline indicators are what make this band visually distinct from band 1.

| Measure | Source | Sample gate | Honest-zero rule |
|---|---|---|---|
| Max drawdown | `compute_max_drawdown(compute_equity_curve(df))` + `drawdown_series` sparkline | Needs the same ≥4 dated points as the curve; below that show the figure with no sparkline | — |
| Rule adherence | **`rule_adherence_rate(df)` — Codex-owned, does not yet exist (D11)** | Must display numerator/denominator or n beside the percentage (handoff §2) | A rate over an unknown sample reads `Not recorded`, never `0%` |
| Edge leak | `total_edge_leak(df)` | — | `0.0` is ambiguous (D10). Distinguish "no rule-breaking trades recorded" from "rule-breaking trades netted exactly zero" from "signal columns absent" |
| Consistency score | `consistency_score(df)` | `_MIN_TRADES_FOR_CONSISTENCY = 5` | Below 5 trades the score is not shown; state what unlocks it |

Edge leak carries sign semantics that must survive into copy: a positive edge leak means
rule-breaking happened to net a profit. That is *lucky, not repeatable*, and must never be
presented as a positive outcome. Tone it neutral with an explicit caption — never green.

Rule adherence and consistency are process measures. They may not be coloured red/green;
red and green are reserved for money outcomes. Use neutral figures with a band label
(e.g. a text qualifier), so colour is not doing semantic work it is not licensed for.

**Threshold legibility rule (adopted from the bullet-chart pattern, the only AAA-graded form
in the chart database).** For every measure in this band:

- The numeric value is **always visible as text**, never hover-only and never encoded solely
  in the length or fill of an indicator.
- Where a measure has bands or thresholds, each band is **labelled with its threshold in
  text** — not conveyed by colour position.

A true bullet chart was considered for rule adherence and consistency and **deferred**: the
pattern requires a defined target range, and TradeLens has no user-defined targets for either
measure. Introducing one would be a product decision, not a presentation decision, and is out
of scope. The accessibility rule above is adopted; the form is not.

### 5.4 Band 3 — Performance trajectory

**Form:** the dominant instrument. The equity curve keeps the highest visual weight on the
page at 360 px, `TL_SURFACE_CHART` stage, existing teal trajectory, restrained area fill.
Flanked by four figures that describe the *shape* of the sequence rather than repeating band 1.

| Flanking figure | Source | Notes |
|---|---|---|
| Current streak | `compute_streaks.current_streak` + `.streak_type` | Signed magnitude; `streak_type` gives the word so colour is not the only cue |
| Best streak | `.max_win_streak` | Paired with `.max_loss_streak` as context |
| Average win | `compute_basic_metrics.avg_win` | `0.0` with zero wins reads `No wins yet` (D10) |
| Average loss | `.avg_loss` | `0.0` with zero losses reads `No losses yet` (D10) |

**Retain:** the `sample_state.show_dominant_series` gate. Below four dated points there is no
shape to read, and a curve through two dots claims a trend the sample has not earned — state
the standing and say what unlocks the curve. Hover keeps date, cumulative P&L, and trades
that day. `theme=None` stays, so the TradeLens template owns the stage.

### 5.4a The date-series policy — one rule for every dated instrument

Two different units gate the Overview, and conflating them is what produced the contradiction
this section replaces. Both are defined here and used verbatim everywhere else.

**Populated trading day.** One distinct non-empty `trade_date` carrying at least one logged
trade. Two trades on the same date are **one** populated trading day. This is exactly what
`sample_state.dated_points` already counts.

**The policy — a dated instrument requires ≥ 4 populated trading days.**

| Instrument | ≥ 4 populated trading days | < 4 populated trading days |
|---|---|---|
| Equity curve | Draw the curve | State the standing; name how many more days unlock it |
| Calendar heatmap | Draw the grid | Ranked day list from the same `calendar_daily_pnl` rows |

**Source.** This is not a new number. `sample_state.show_dominant_series` already gates the
equity curve at four dated points, that gate is already implemented and covered by tests, and
the `--domain chart` pass independently set the line-chart floor at "fewer than 4 data points →
use a stat card". Extending the same constant to the heatmap adds no threshold and creates one
testable rule instead of two.

The generic heatmap heuristic of "fewer than 20 cells → use a bar chart" was considered and
**does not transfer**. It assumes every cell samples a continuous variable, so an unfilled cell
is missing data. In a trading calendar an empty day is *information* — it means no trade was
taken — so a sparse month is a truthful picture of a sparse month, not a misleading one. What
the four-day floor protects against is different and narrower: a grid with too few populated
days to show any weekday or clustering pattern at all.

**Trade-count gates are separate and are not affected by this policy.** They key to their own
code constants: consistency score needs ≥ 5 trades (`_MIN_TRADES_FOR_CONSISTENCY`), and the
Weekly Recap needs ≥ 5 complete trades (`TRADES_FOR_REVIEW`). A specification statement in
populated trading days may never be silently read as a trade count, or the reverse.

Both units live in the shared data-state policy alongside `sample_state`. Neither may be
recomputed in page code.

### 5.5 Band 4 — Recurring edge

**Form:** two ranked lists plus a calendar heatmap. Ranked lists, not pie charts — handoff
§3 authorises session and setup performance, and `no-pie-overuse` plus the plan's
comparability rules make ranking the correct form.

| Element | Source | Rules |
|---|---|---|
| Session performance | `by_session` / `killzone_performance` | Ranked by net P&L with n per row |
| Setup performance | `by_setup_type` | Ranked by net P&L with n per row |
| Calendar heatmap | `calendar_daily_pnl(df, year, month)` | See the heatmap rules immediately below |

**Calendar heatmap rules.** Daily P&L is signed, which determines the form:

- **Divergent scale, not a single gradient.** A one-directional gradient cannot represent ±
  data honestly — it makes a large loss and a large gain read as the same intensity. Use a
  divergent scale with a neutral midpoint at zero, in the existing semantic red/green, at low
  saturation.
- **Numeric legend with scale ticks**, not a bare colour ramp. A reader must be able to map a
  cell back to a magnitude.
- **Pattern or texture in addition to colour.** The heatmap form is graded only **B** for
  accessibility precisely because colour usually carries everything. Positive, negative,
  breakeven, and no-trade days each need a non-colour cue — sign, glyph, or texture — so the
  grid survives colour-blindness and greyscale printing.
- **Exact values on interaction**, and reachable without hover.
- **Grid-table alternative** with row and column labels, for screen readers and for anyone who
  needs to read exact values rather than compare intensities.
- **Sparse-data gate — the shared date-series policy in §5.4a.** The heatmap is gated on
  populated trading days by the same rule as the equity curve, not by a separate threshold.
  Below it, fall back to a compact ranked day list showing the same `calendar_daily_pnl` rows
  and state what would populate the grid.
- 7 columns at phone, 44 px day cells, no TradeZella purple.

**Comparability is a hard constraint, inherited from the plan and the prior audit.** With one
category present, nothing may be called strongest or weakest. `leading_category` already owns
this decision and reports `is_only_category`; the UI must honour it. A single-bar chart
proving nothing is exactly the trust failure the 2026-07-21 audit scored 4.5/10.

A radar/spider chart was considered for comparing sessions and setups across attributes and
**rejected**: the pattern's own guidance sends precise comparison to a grouped bar, and a
trader comparing session P&L needs to read magnitudes, not silhouette. The ranked lists stand.

### 5.6 Band 5 — Next review action

**Form:** one editorial readout with its Evidence Rail, then exactly one link.

Absorbs both of today's separate elements (§2): the activation `render_next_step` card and
the `_overview_observation` readout. Which one appears depends on state:

- **Not yet activated** → the activation next step, one action, with progress as
  `{completed} of {total}`. Never a checklist.
- **Activated** → the period observation from `_overview_observation`, with its existing
  Evidence Rail (evidence, sample `n=x of y`, confidence banded at 12/6, and the
  `is_only_category` limitation).
- **Neither earned** → the band is omitted entirely. An empty band is worse than no band.

The action is always a *review* action — what to go and re-read. Never a trade action.

### 5.7 Overview states

Two independent axes govern these states, per §5.4a: **populated trading days** (`d`) gate the
dated instruments, and **trade count** (`t`) gates the sample-dependent figures. They move
independently — six trades on two days is `t=6, d=2` — so each row below states both.

| State | Behaviour |
|---|---|
| `t=0` | Full-page welcome. Bands 1–5 all suppressed. Two paths: log first trade, load sample data |
| `d < 4` | **Equity curve and calendar heatmap both withheld** (§5.4a). The curve states the standing and names how many more days unlock it; the heatmap falls back to a ranked day list |
| `d ≥ 4` | Both the curve and the heatmap draw |
| `t < 5` | Consistency score withheld (`_MIN_TRADES_FOR_CONSISTENCY`), stating what unlocks it. Rule adherence and edge leak still show, with n beside them |
| `t ≥ 5` | Consistency score shows |
| One category only | Ranked lists render but may not rank — `leading_category.is_only_category` forbids strongest/weakest language |
| Filtered to empty | Bands suppressed; filter summary states the active scope and offers a clear path back |
| Sample data active | Labelled once, in the masthead eyebrow. Never a repeated banner |

Bands 1 and 5 are present whenever `t ≥ 1`. Band 5 is omitted only when neither an activation
next step nor a period observation is earned (§5.6).

Worked example, because this is where the previous version contradicted itself: three trades all
logged on one date is `t=3, d=1`. Bands 1, 2 (adherence and edge leak, no consistency), and 5
render. The curve and the heatmap are both withheld — under the old text the heatmap would have
appeared at "4–9 trades" while simultaneously requiring 20 cells.

---

## 6. Page specifications

### 6.1 Authentication and recovery

**Surface:** `components/auth_screen.py`. The one place with a stronger privacy boundary than
the workspace. No AI Partner, no rail, no bottom nav.

Hierarchy: brand → one positioning sentence → mode toggle (Sign in / Create account) → form →
recovery path → compliance line.

| State | Requirement |
|---|---|
| Sign in | Email + password, `autocomplete` set so the system can autofill, `type="password"` with a show/hide toggle |
| Create account | Adds password confirmation and an optional recovery email, with the consequence stated: without one the account cannot be recovered |
| Reset request | Email field → "Email me a code". Response must not reveal whether an address is registered |
| Reset complete | Code + new password → "Set new password" |
| SMTP unconfigured | Says it could not send. Never pretends success (already correct — preserve) |
| Error | Persistent, inline, next to the field. Never a toast. `role="alert"` |
| Success | Persistent confirmation, not a disappearing toast |

Accessibility: visible labels (never placeholder-only), errors adjacent to their field,
first invalid field receives focus after a failed submit, 44 px minimum input height, the
mode toggle is a real radio/segmented control with `aria` state.

Copy must state what the product is without implying signals or advice. Use the canonical
positioning sentence from the 2026-07-21 audit.

### 6.2 New Trade wizard

**Surface:** `1_NewTrade.py` (1163 lines), `trade_wizard.py`, `ai_autofill_review.py`.

Five steps, unchanged, with session-state ownership unchanged: chart → when/what →
setup/evidence → risk/outcome → reflection → review and save.

**One progress system only.** The prior audit found two simultaneously (text tabs plus a
numbered rail) and the duplicate rail was already removed — it must not return. Quiet
progress, one primary action, never five bright pills.

| State | Requirement |
|---|---|
| Step navigation | Forward/back preserves every draft value across all five steps |
| Blocking validation | Error adjacent to the field, on blur not per keystroke, stating cause and fix |
| Screenshot analysis | User-controlled confirmation. Waiting state holds its height — no collapse-and-jump |
| Optional fields | Progressive disclosure. Review must not become a wall of "Not entered yet"; hide empty groups and offer one "complete N fields" action |
| Outcome contradiction | Blocked at create and edit (`trade_validation.py`) — preserve |
| Save | Loading → success. Scoped reset only |
| Reflection | Optional, and visibly optional |

Motion: the existing 180 ms step reveal only, firing once, removed under reduced motion.

### 6.3 Journal — ledger, calendar, trade detail

**Surface:** `2_Trades.py` (874 lines).

Three mutually exclusive native radio views: Trades, Calendar, Trade Detail. All three
interaction paths must stay green:

1. ledger row → detail → back → ledger (with scroll and filter state restored)
2. calendar day → trade opener → detail
3. AI summary renders as safe Markdown with its Evidence Rail separate

| Element | Requirement |
|---|---|
| Filter bar | Compact. `More filters` stays progressive disclosure. `Clear filters` is a reset, styled subordinate — the prior audit flagged it as too primary |
| Ledger | Neutral by row. Semantic colour only on signed money and the explicit result badge. No full-row red/green, no per-row gradients, no heavy cell boxes |
| Numerals | Tabular/mono for money, dates, and R-multiples so columns do not shift |
| Calendar | 7 columns at phone, 44 px day cells, textual legend |
| Trade detail | Ticket on `TL_SURFACE_PANEL`; edit and delete behind separate disclosures; delete requires explicit confirmation |
| Sorting | `aria-sort` reflects current state |
| Overflow | Wide tables scroll inside their own container. The page body never scrolls horizontally |

### 6.4 Analytics — four lenses

**Surface:** `4_Analytics.py` (824 lines), `charts.py`.

Exactly four lenses — Performance, Risk, Timing, Setups — exactly one body rendered at a time.
Each lens follows one shape:

> question → ruled KPI strip → instrument → ranked evidence → editorial readout + Evidence Rail

| Requirement | Detail |
|---|---|
| Chart stage | Every Plotly figure passes through `apply_chart_stage`. Two heights only: 360 dominant, 240 supporting |
| Palette | Semantic and limited. No rainbow |
| Lens selector | Visually secondary to the current question's section header |
| Comparability | One category is never described as strongest or weakest. Fixed-risk alternative retained |
| Sample annotation | Stays inside the stage at phone and desktop |
| Sparse data | Compact explanatory state, never a full-size axis frame with two points |
| Accessibility | Legend near the chart and interactive; tooltips reachable without hover; axis units labelled; a text summary of the key insight for screen readers; ≥3:1 for data marks, ≥4.5:1 for data labels |
| Responsive | Charts reflow or simplify at 375 px — fewer ticks, horizontal bars where clearer |

### 6.5 AI Reviews

Specified in full in §7.

### 6.6 Strategy Profile

**Surface:** `5_Strategy.py` (403 lines).

Retain: 6-of-6 completion truth, saved facets, starter behaviour, five accordions, one local
error slot, one restrained save action, and the subprocess persistence scenarios (starter
persistence, blank-name refusal, corrected save, untouched-field preservation, contained
write failure with no DSN leak).

Dark treatment: subtle panels and hairlines so opened accordions do not read as a stack of
oversized cards. Preserve the scoped 180 ms accordion reveal with no-replay and
reduced-motion behaviour.

The Strategy Profile is one of the three context sources the AI Partner prioritises (§8), so
its completion state must be legible from the Partner's empty state.

### 6.7 Settings

**Surface:** `9_Settings.py` (450 lines). Four sections: Profile, Preferences, Data, Danger Zone.

**Settings is the quietest destination.** No chart, no promotional banner, no bright primary
CTA.

| Requirement | Detail |
|---|---|
| Warnings | Amber/neutral. Red is reserved for the Danger Zone and destructive actions |
| Danger Zone | One contained perimeter (`TL_LINE_STRONG`) around both disclosures, their confirmation fields, and their destructive buttons |
| Confirmations | Exact-match confirmation preserved for delete-all-trades and delete-account |
| Destructive separation | Spatially and visually separated from normal controls |
| Import/export | Tenant-scoped. Import failures sanitised |
| Sample data | Load and clear, both scoped to the authenticated user |
| Secrets | No deployment secret names surfaced more prominently than required. Prefer user-facing recovery guidance over operator jargon |
| Undo | Where an action is reversible, offer undo. Where it is not, say so before it runs |

---

## 7. AI Reviews — evidence-backed research notes

### 7.1 The core structural change

Today the three lenses take two different paths: Patterns builds a structured `ResearchNote`,
while Weekly Recap and Daily Debrief pour `content_md` through one `st.markdown` (D6). All
three must share **one reading shell** fed by two adapters.

```
                    ┌─ Patterns ──── generate_insights → ResearchNote ─┐
one reading shell ←─┤                                                  │
                    └─ Weekly/Daily ─ content_md → parse_review_markdown
```

`parse_review_markdown` is the pure presentation parser from the older plan's Task 7. It stays
pure: standard library only, no HTML rendering, no model calls, no database, no Streamlit. It
preserves the original Markdown of every section, accepts `##` and `###`, keeps pre-heading
prose as intro, makes deterministic unique IDs for duplicate headings, ignores heading-looking
text inside fenced code, returns one fallback section when there are no headings, and returns
an empty document for blank content.

### 7.2 Note anatomy — five separated regions

The ask is explicit that these must not blur into repetitive cards. Each region has a distinct
form and appears at most once per note.

| Region | Form | Content |
|---|---|---|
| 1 Note header | Title + sample line | What this note is, over what period, n |
| 2 Primary thesis | Single lead paragraph at display weight, 68–72 ch measure | The one strongest supported conclusion. Visible before anything else |
| 3 Supporting findings | Numbered `render_research_finding`, one section shown at a time | The findings that back the thesis, in reading order |
| 4 Evidence Rail | `render_evidence_rail` — hairline, indented, mono metadata | Evidence, sample, confidence, limitation. **Once per note, not under every paragraph** |
| 5 Limitations + next review actions | Plain block, then a short list | What the sample cannot support; then what to go and re-read |

Then, collapsed below: `render_evidence_disclosure` — what the note was based on, never how
it was produced. Model reasoning, prompt content, token counts, and call cost are operator
data and never appear in the user path.

### 7.3 Lens navigation

Three lenses, each a distinct question with a distinct period:

| Lens | Question |
|---|---|
| Patterns | What keeps repeating in the journal? |
| Weekly Recap | How did the completed week go? |
| Daily Debrief | What happened on one trading day? |

The lens control stays a native radio (no JavaScript) but demotes visually below the current
question's section header. The question, not the control, is the loudest thing in the region.

**Within a note**, long documents get a section index — native Streamlit controls only. Desktop:
a narrow index column beside one readable content column. Phone: a stacked selector above the
content, no horizontal scroll, no offscreen sticky panel. `Read full note` always renders every
original section; generated text is never truncated or discarded.

The active section survives an unrelated rerun and clamps safely when a regenerated document
has fewer sections than before.

### 7.4 Reading measure

68–72 characters for generated prose, enforced by a max-width on the content column, not by
inserting breaks. The prior audit found weekly-review prose had no measure and set 68 ch; that
holds. Content must not stretch into the unused right side, and no section may become a
1000 px-wide paragraph.

Mono is limited to metrics, dates, compact metadata, and labels. Long prose is body face.

### 7.5 Interaction states

| State | Behaviour |
|---|---|
| First load, no note | `render_note_skeleton` — holds the note's geometry, `role="status"`, `aria-busy`, `aria-live="polite"`, and a hidden "Writing this review…" |
| Note ready | Thesis and selected section visible immediately |
| Regenerating | **Prior note stays on screen.** Inline "Updating review…" announced politely, no page jump, regenerate control disabled while in flight. Skeleton appears only when there is no prior note (fixes D5, D8) |
| Regeneration succeeded | Replace, clear the error slot |
| Regeneration failed — domain error | Prior note stays. Show the trader-safe specific reason |
| Regeneration failed — unexpected | Prior note stays. Fixed generic recovery copy; exception logged, never rendered |
| Empty — no trades | One empty state and a path to log a trade |
| Empty — nothing in the period | States it plainly, offers a different period |
| Sparse — below 5 complete trades | Weekly Recap is not auto-generated. State what would unlock it. Attach the "read this as a description, not a rule" limitation |
| AI unavailable | Say so and state that the trades are still in the Journal. Never a raw error |

Confidence bands stay as they are: ≥20 high, ≥10 medium, else low, matching the prompt's bands.
Sample, confidence, period, and limitation travel with the claim.

### 7.6 Consistency across lenses

One period stats strip on all three lenses (fixes D7): Trades, Win rate, Net P&L, Profit
factor, Edge leak. Same builder, same cells, same conventions.

Motion: one 160–180 ms opacity/4 px transition, and only when the user changes section. No
animation on initial load, regeneration, errors, or under reduced motion.

Safety: no new prompts, no new AI calls, no service edits. Cache keys and user scoping
unchanged. "Reflection only — never signals or advice" stays visible in the masthead subtitle
and is not repeated in every section.

---

## 8. AI Partner — global, bottom-right

### 8.1 Authorised scope

Handoff §1 approves this, with boundaries that are not negotiable:

- Reuse `services/partner.py` via `partner_reply(..., per_trade_qa=False)`. No new endpoint,
  no new direct Anthropic call, no new system prompt.
- Context assembled **only** from the authenticated user's journal entries, completed trades,
  and active Strategy Profile — in that priority order.
- Every service query receives the authenticated `user_id`. No unscoped lookup.
- Never import the Anthropic SDK from a page or component.
- Log usage exactly once per completed response:
  `log_ai_usage("AI Partner", usage, user_id=uid)`.
- Keep the existing post-trade scope guard. Never signals, predictions, entries, position
  instructions, or financial advice.
- Model output goes through `st.markdown` with HTML disabled. Surrounding authored HTML
  escapes every value.
- The UI may surface evidence, sample size, confidence, and limitations **only when the
  service returns them**. It may not invent them.
- Claude owns the surface. Codex authors or approves any new context adapter, service
  signature, prompt, cost behaviour, or safety behaviour.

### 8.2 Decision 1 — true bottom-right FAB and drawer

**Approved position:** a genuine fixed bottom-right launcher on desktop, and a full-page /
bottom sheet on mobile. No JavaScript injection, no new dependency.

**Mechanism.** A real Streamlit button inside a keyed container, positioned by scoped CSS:

```
st.container(key="tl_partner_launcher")  →  .st-key-tl_partner_launcher
    position: fixed; right: var(--tl-space-6); bottom: var(--tl-space-6);
    z-index: var(--tl-z-partner);   /* the scale defined in §4.5 */
```

The launcher must be a real Streamlit widget, not authored HTML, so it stays keyboard-reachable
and needs no script.

**Open/close is state-driven, not CSS-driven.** `st.session_state["partner_open"]` gates
whether the drawer renders at all. Closed means the drawer's widgets are not in the DOM, so
they cannot be tabbed to — the same guarantee the mobile `More` sheet already provides. Opening
costs one rerun, which is how Streamlit works and is acceptable.

**The drawer is non-modal, and this is deliberate.** Without JavaScript there is no focus trap.
Claiming modal semantics we cannot enforce would be worse than not claiming them. Therefore:

- `<aside>` with `aria-label="AI Partner"`. **No `aria-modal="true"`.**
- No blocking scrim. The page behind stays operable.
- A visible Close control, ≥44×44, **first in the drawer's DOM order** so it is the first tab
  stop. There is no Esc-to-close without script, so the visible control is mandatory.

**Verification required before this ships.** `position: fixed` resolves against the nearest
ancestor establishing a containing block. Any ancestor carrying `transform`, `filter`,
`perspective`, `contain: paint`, or `will-change` silently converts fixed into
ancestor-relative. Streamlit's `stMainBlockContainer` and app-view wrappers must be inspected
in a live browser at 1440, 1024, coarse 768, and coarse 375 before this approach is accepted.
Confirm: the launcher stays viewport-anchored while the page scrolls; it survives a rerun; it
never overlaps the bottom nav or the safe-area inset; and it does not cover the wizard's
primary action or the Danger Zone's confirmation controls.

**Reviewed fallback, if fixed positioning proves unstable.** Degrade to a **docked Partner**,
as a reviewed decision recorded in the handoff — never a silent substitution:

- ≥1024 px: a persistent right-hand column, toggled from a rail entry.
- ≤767 px: a dedicated `More` sheet entry routing to a full-page Partner view.

This preserves every capability and every safety boundary while removing the dependency on
fixed positioning. It changes placement, not scope.

### 8.2a Mobile coexistence — the Partner and the `More` sheet are mutually exclusive

At coarse-pointer widths the `More` sheet and the Partner sheet occupy the same bottom region.
Only one may be open, and the Partner may never layer over or obstruct navigation.

**Rules.**

1. Opening either sheet closes the other.
2. The Partner launcher is hidden while **either** sheet is open.
3. The Partner never overlaps the bottom nav. The launcher is offset above it by the nav height
   plus the safe-area inset, per §4.5's ordering (`partner 20` < `nav 30` < `sheet 40`).

**Mechanism, and it is asymmetric — this is a real constraint, not an oversight.**

*Partner opens → `More` closes.* Guaranteed with no script. Opening the Partner writes
`session_state` and triggers a rerun; the rerun re-emits the `More` `<details>` without an
`open` attribute, so it returns closed. This is the behaviour the plan already requires — the
sheet is closed on arrival and after navigation.

*`More` opens → Partner hides.* The `<details>` toggles entirely client-side with no rerun, so
the server cannot observe it and `session_state` cannot react. Without JavaScript the Partner
cannot be *closed* by that event. It can, however, be **hidden by CSS**, because `[open]` is a
matchable state:

```css
.tl-shell:has(.tl-mobile-nav details[open]) .st-key-tl_partner_launcher,
.tl-shell:has(.tl-mobile-nav details[open]) .st-key-tl_partner_drawer {
  display: none;
}
```

Two consequences that must be stated rather than glossed:

- **Hidden is not closed.** If the Partner drawer was open when the trader opened `More`, the
  drawer is hidden but its `session_state` remains open, so closing `More` reveals it again.
  That is acceptable and arguably correct — the trader did not ask to end the conversation —
  but it must be a deliberate, documented outcome, not a surprise.
- **`display: none` removes the hidden widgets from the tab order**, which is what we want. Verify
  it, rather than assuming: Streamlit widgets inside a `display: none` ancestor are still
  instantiated server-side, and only the CSS removes them from focus traversal.

**`:has()` support floor and fallback.** `:has()` requires Safari 15.4+, Chrome 105+, Firefox
121+. Confirm against the project's supported-browser range during implementation. If `:has()`
cannot be relied on, the substitute is DOM ordering rather than script: render the launcher as a
later sibling of the nav and use `.tl-mobile-nav details[open] ~ .st-key-tl_partner_launcher`.
If neither selector is workable, escalate to the docked-Partner fallback in §8.2 — where the
Partner is a `More` entry routing to a full-page view, which makes the two mutually exclusive by
construction and needs no selector at all.

**Verification, at coarse 375 and coarse 768.** Open `More` with the Partner closed, then with
the Partner open. Open the Partner with `More` open. In every combination confirm: only one
sheet is visible; the launcher is hidden while either is open; no nav item is covered or
un-tappable; nothing hidden is reachable by Tab; and no bottom-nav target falls below 44 px or
under the safe-area inset.

### 8.3 Decision 2 — conversation history stays session-only in Phase 1

**Phase 1:** history lives in `st.session_state`, scoped per user, and is never persisted.
This matches how `ai_trade_chat.py` already works and requires **no migration and no schema
change** — both of which the older plan excludes and the handoff does not authorise.

Consequences that must be stated in the UI, not hidden:

- The drawer's empty state says the conversation is not saved and will end with the session.
- No "history" list, no thread switcher, no search. Promising persistence the product does not
  have is worse than the absence.
- Clearing the conversation is available and immediate.

**Future phase (specified, not built).** Persisted history requires a schema-backed design
owned by Codex: a user-scoped conversation table with an Alembic migration and an implemented
`downgrade()`, tenant-scoped reads, a retention policy, and a deletion path that account
deletion honours (account deletion already removes screenshot files and must extend to
conversations). The UX that unlocks then: a thread list in the drawer, per-thread titles
derived from the first question, resume-on-return, and export. **None of it is authorised now**
and none of it may be stubbed in Phase 1.

### 8.4 Partner component inventory

| Component | Form | Notes |
|---|---|---|
| Launcher | Fixed bottom-right Streamlit button, ≥44×44 | Accessible name states it opens the AI Partner. Not icon-only without a label |
| Drawer (desktop) | `<aside>`, `TL_SURFACE_ELEVATED`, `TL_LINE_STRONG` edge | Non-modal. Close first in DOM order |
| Sheet (mobile) | Full-page or bottom sheet | Above the bottom nav, respecting safe-area inset. Mutually exclusive with the `More` sheet (§8.2a) |
| Conversation | Alternating turns, clearly attributed | Model turns via `st.markdown`, HTML off |
| Suggested questions | 3–4 review-shaped prompts | Derived from the existing `_PROMPT_CHIPS` pattern — "What did I do well?", "What rule did I break?", "Summarize this trade in journal format." Never "what should I trade?" |
| Composer | Text input + send | Send disabled while a reply is in flight |
| Citation / evidence | Evidence Rail beneath a reply | Only when the service returns evidence. Journal entries and trades cite back to their records |
| Clear conversation | Subordinate control | Immediate, with the session-only consequence already stated |

### 8.5 Interaction states

| State | Behaviour |
|---|---|
| Closed | Launcher only. Drawer widgets absent from the DOM |
| `More` sheet open (coarse widths) | Launcher and drawer hidden; nothing hidden is tabbable. Partner state is preserved, so closing `More` restores it (§8.2a) |
| Open, empty | What the Partner can do, its three context sources, the session-only notice, and suggested questions |
| Open, no strategy profile | Says the Strategy Profile is not set and links to it — the Partner is materially better with it |
| Open, no trades | Says it has nothing to review yet and links to New Trade |
| Sending | Send disabled, inline pending state, `aria-live="polite"`. Prior turns stay visible |
| Reply ready | Appended. Focus is not stolen |
| Domain error | Trader-safe specific reason. Prior turns stay |
| Unexpected error | `"AI is temporarily unavailable. Please try again."` Exception logged, never rendered |
| AI disabled | Launcher states the Partner is unavailable rather than opening to a dead end |
| Out-of-scope question | The existing scope guard's refusal, phrased as redirection to what the Partner can review |

### 8.6 Safety copy rule

The Partner must never imply signals, predictions, entries, or advice — in its own output, its
suggested questions, its empty state, or its accessible names. Every suggested question is
retrospective. Any forward-looking phrasing is a spec violation, not a copy preference.

---

## 9. Component inventory

### Retained, retargeted to dark

`render_workspace_header` · `render_kpi_strip` · `render_evidence_rail` ·
`render_research_finding` · `render_research_note` · `render_note_skeleton` ·
`render_editorial_readout` · `render_filter_summary` · `render_section_header` ·
`render_evidence_disclosure` · `render_empty_state` · `render_next_step` · `render_badge` ·
`error_box` · sidebar rail · bottom nav + `More` sheet · `apply_chart_stage` ·
`render_trade_calendar` · trade wizard · `render_data_state`

### New

| Component | Purpose | Owner |
|---|---|---|
| `parse_review_markdown` + `ReviewSection` / `ReviewDocument` | Pure AI-note document model | Claude (pure presentation) |
| `render_review_reader` | The one reading shell for all three lenses | Claude |
| Discipline panel | Overview band 2 form | Claude |
| Ranked-performance list | Overview band 4 form, session and setup | Claude |
| Partner launcher / drawer / sheet | §8 | Claude (surface only) |
| `rule_adherence_rate(df)` | Overview band 2 measure | **Codex** |
| `TL_LINE_STRONG` | Load-bearing boundaries (D4) | Claude (token) |
| `--tl-z-*` scale | Ordered layering; replaces three arbitrary literals (D13) | Claude (token) |
| Heatmap sparse-month gate | Shared data-state policy, mirroring `show_dominant_series` (§5.5) | Claude (presentation policy) |

### Deleted

Light-workspace tokens · duplicate legacy dark tokens · emoji icon arguments · the
single-`st.markdown` note wall · pre-regeneration cache clearing.

---

## 10. Interaction states — global contract

Every interactive surface defines all eight. A state left undefined is a defect.

| State | Rule |
|---|---|
| Default | Quiet. Fields are not neon when unfocused |
| Hover | Visual only. **No hover-gated rule may carry non-hover colour or layout behaviour** — the plan requires a structural test for this |
| Focus | Visible teal ring ≥3:1, never removed, never animated, never hover-gated |
| Active / pressed | Feedback within 100 ms. Opacity or colour, never a layout-shifting transform |
| Disabled | Visibly unavailable, semantically disabled, not tappable. Distinct from read-only |
| Loading | Feedback under 300 ms; skeleton beyond it. Height is reserved — no collapse-and-jump |
| Error | Persistent, inline, adjacent to cause. States cause and fix. `role="alert"`. Never a toast for a validation failure |
| Empty | Explains why it is empty and offers one action. Never a blank panel or a bare axis frame |

---

## 11. Responsive behaviour

Existing breakpoints are correct and are kept: phone ≤767, tablet ≤1023, desktop ≥1024,
container max 1320.

| Width | Navigation | Overview bands | AI Reviews | Partner |
|---|---|---|---|---|
| ≥1440 | Rail | 1 strip · 2 panel · 3 chart + flanking · 4 lists + heatmap · 5 readout | Index column beside content | Fixed bottom-right drawer |
| 1024–1439 | Rail | Same; band 3 flanking figures may wrap | Index column beside content | Fixed bottom-right drawer |
| 768–1023 (coarse) | Bottom nav + `More` | Bands stack; band 4 lists stack | Stacked section selector | Sheet, above bottom nav; exclusive with `More` |
| ≤767 (coarse) | Bottom nav + `More` | Full stack; heatmap 7-col, 44 px cells | Stacked selector, then content | Full-page or bottom sheet; exclusive with `More` |

Hard rules: rail and bottom bar never appear together · zero horizontal page overflow at every
width · wide tables and charts scroll inside their own container · fixed elements reserve
padding so content is never hidden beneath them · `More` links are not tabbable while closed ·
coarse-pointer verification uses real media emulation (`pointer: coarse`, `hover: none`), not
desktop viewport resizing · `min-h-dvh` semantics rather than `100vh` where height is set ·
layout stays operable in landscape.

---

## 12. Accessibility requirements

Non-negotiable, and each one testable.

**Contrast.** Body text ≥4.5:1 on its actual composited surface; large text and non-text
indicators ≥3:1. Measure after alpha compositing — treating the first `rgba()` layer as opaque
is how contrast bugs survive tests. Data marks ≥3:1, data labels ≥4.5:1.

**Colour independence.** Every colour-carried meaning has a text, sign, shape, or label
companion. The KPI strip's hidden tone announcement is the pattern to follow. Red/green is
reserved for money; process measures (adherence, consistency) may not use it.

**Targets.** ≥44×44 CSS px visible, at all four widths, with ≥8 px between adjacent targets.
Extend the hit area rather than shrinking the visual.

**Keyboard.** Full operation. Tab order matches visual order. Focus visible everywhere. Modals
and multi-step flows offer cancel/back. After a failed submit, focus moves to the first invalid
field. After a route change, focus moves to the main content region. Drag-and-drop, if any, has
a keyboard alternative.

**Screen readers.** Icon-only controls carry accessible names. Headings are sequential with no
skipped level. Form fields use real labels with `for`. Errors announce via `role="alert"` or an
`aria-live` region. Toasts use `aria-live="polite"` and never steal focus. Charts carry a text
summary of the key insight and a table alternative. Sortable tables expose `aria-sort`. Current
navigation location exposes `aria-current` plus visually hidden current-page text.

**Motion.** `prefers-reduced-motion: reduce` honoured everywhere. No required information
depends on animation. Opacity and transform only, 120–200 ms, shared ease-out. Never animate
charts, long tables, validation, focus, or page load. Animations are interruptible and never
block input.

**Text scaling.** Layout survives increased text size without truncation. Prefer wrapping to
truncation; where truncating, provide the full text.

---

## 13. 10K Checklist acceptance criteria

The 2026-07-21 audit scored the app against the eight items. Phase 1 targets the four weakest.
Scoring rule from the older plan: **product experience is scored separately from business
proof, and the result may not be inflated because the theme is more attractive.**

| # | Item | App baseline | Phase 1 target | Evidence required |
|---|---|---:|---:|---|
| 01 | Point of view, not a template | 7.5 | 8.5 | Product and marketing read as one company. The app no longer looks hosted inside Streamlit. Five distinct band forms on Overview, not a card wall |
| 02 | Typography that does work | 8.0 | 8.5 | Generated prose at 68–72 ch. Mono limited to metrics, dates, metadata, labels. One editorial lead sentence per note |
| 03 | A restrained colour system | 8.5 | 9.0 | Teal coverage reduced to primary actions and one active state per viewport. Neutral hairlines on passive containers. No large red/green chart below a meaningful sample |
| 04 | **Hierarchy that breathes** | **6.5** | **8.5** | One progress system in New Trade. Overview's five bands in five forms. No empty chart canvases. No "Not entered yet" wall |
| 05 | Imagery with intent | 6.5 | 7.5 | Re-captured screenshots from coherent seeded data, no owner chrome, fewer and larger crops |
| 06 | **Motion that whispers** | **6.0** | **7.5** | Full motion inventory. Loading and state feedback improved rather than decoration added. Reduced motion verified |
| 07 | **Mobile that is designed, not shrunk** | **5.5** | **7.5** | Real coarse-pointer captures at 375 and 768 for all seven destinations plus the Partner sheet. Not CSS assertions alone |
| 08 | **The invisible expensive stuff** | **4.5** | **7.0** | No rendered exception in any audited state. Tenant scoping resolved at every call site. No secret, DSN, or stack text reachable. Full suite, ruff, black green |

Items 04, 06, 07, 08 are the phase's real work. 07 and 08 cannot be closed from source review
alone — they need the browser preflight that steps 1–5 of the handoff sequence produce.

---

## 14. Out of scope for Phase 1

Stated so scope creep is visible: no widget builder or customisable dashboard · no generic
card wall · no new AI endpoint, prompt, or model-routing change · no database migration or
schema change · no persisted conversation history · no theme switcher · no React, FastAPI,
JavaScript injection, CSS framework, or icon library · no marketing-site change except the
separately approved Higgsfield playback correction during the motion phase · no push, merge,
PR, or deploy without explicit owner approval.

---

## 15. Validation-pass amendments (2026-08-03)

What the `ui-ux-pro-max` database pass in §0.4 changed. Only material gaps were amended; the
specification was not redesigned.

| # | Amendment | Section | Severity |
|---|---|---|---|
| A1 | Z-index scale defined (`--tl-z-base` … `--tl-z-overlay`), three existing arbitrary literals scheduled for migration, stacking-context verification required separately from the `position: fixed` check. Resolves a dangling reference — §8.2 previously cited a "documented z-scale" that did not exist | §4.5, D13 | High |
| A2 | Calendar heatmap: divergent scale with neutral zero midpoint (signed data cannot use a one-directional gradient), numeric legend with scale ticks, pattern/texture cue beyond colour, exact values reachable without hover, grid-table alternative | §5.5 | Medium |
| A3 | Calendar heatmap gated on sparse data, falling back to a ranked day list. The spec previously gated the equity curve but left the heatmap ungated. **Superseded 2026-08-03 by C1 below** — the original "~20 populated cells" figure was unsupported and contradicted §5.7 | §5.5 | Medium |
| A4 | Band 2 threshold legibility: values always visible as text, thresholds labelled in text rather than by colour position | §5.3 | Medium |
| A5 | Radar rejected for session/setup comparison, bullet-chart form deferred for band 2, both with reasons recorded | §5.3, §5.5 | Low |
| A6 | Header corrected — it credited `ui-ux-pro-max` as reviewer before its searches had been run | header, §0.4 | — |

No amendment altered the IA, the five-band Overview reading order, the AI Reviews note anatomy,
either of the two owner decisions in §8, or any safety boundary.

### 15.1 Owner-directed corrections (2026-08-03, documentation only)

Three bounded corrections requested before Codex approval. No product code, no rerun of the
design database, no other redesign.

| # | Correction | Section |
|---|---|---|
| C1 | **Heatmap sparse-data rule reconciled with §5.7.** The unsupported "~20 populated cells" figure is removed and replaced by one explicit, testable policy in new §5.4a: a dated instrument requires **≥ 4 populated trading days**, where a populated trading day is one distinct non-empty `trade_date` with at least one trade. Source: the existing, already-tested `sample_state.show_dominant_series` gate, independently corroborated by the `--domain chart` line-chart floor. Extending that constant adds no new threshold. §5.4a also records why the generic 20-cell heatmap heuristic does not transfer, and separates populated-trading-day gates from trade-count gates (`_MIN_TRADES_FOR_CONSISTENCY`, `TRADES_FOR_REVIEW`). §5.7 is rewritten on the same two axes and now carries a worked example. Supersedes A3 | §5.4a, §5.5, §5.7 |
| C2 | **Mobile `More` and Partner sheets made mutually exclusive.** Opening either closes the other; the launcher is hidden while either is open; the Partner never layers over or obstructs navigation. The z-scale in §4.5 is reordered so navigation always outranks the Partner (`partner 20` < `nav 30` < `sheet 40`), reversing the earlier partner-above-sheet rationale. New §8.2a documents the asymmetric mechanism honestly — Partner-opens-closes-`More` is guaranteed by the rerun, while `More`-opens must *hide* the Partner via CSS because a native `<details>` toggle never reaches the server — plus the hidden-is-not-closed consequence, the `:has()` support floor, two fallbacks, and the verification matrix | §4.5, §8.2a, §8.4, §8.5, §11 |
| C3 | Two stale `§16` cross-references corrected to `§15` | header, §0.4 |

C1 and C2 change stated behaviour and both are owner-directed. C2's z-order reversal is the one
place a previously recorded rationale was overturned; the superseded reasoning is noted in §4.5
so the change is visible rather than silent.

---

## 16. Open questions for Codex

1. **`rule_adherence_rate(df)` signature and empty-sample behaviour.** Handoff §2 specifies a
   `0.0`–`1.0` fraction reusing `_is_followed`. Overview band 2 needs to distinguish "0% of a
   known sample" from "no sample recorded" (D10). Does the function return `None` for an
   unknown sample, or a separate count the UI reads? The UI cannot honestly render a
   percentage without n.
2. **Edge leak zero disambiguation.** `total_edge_leak` returns `0.0` for no-leak, exact-zero
   leak, and absent signal columns. Should the UI call a second function for the qualifying
   trade count, or does Codex prefer to widen the return? Claude will not compute this in page
   code.
3. **Partner context adapter.** Assembling journal entries + completed trades + Strategy
   Profile into `partner_reply`'s general reflective mode is a context adapter, which handoff
   §1 assigns to Codex. Confirm the signature before Claude builds against it.
4. **Fixed-positioning verification owner.** §8.2 needs a live-browser check that no Streamlit
   ancestor breaks `position: fixed`. This is a UI concern (Claude) but gates a scope decision
   (fallback vs FAB). Confirm Claude runs it and reports, rather than Codex.
5. **Sequencing.** This spec was written before the Opus 5 migration landed on this branch and
   before the browser preflight. Confirm whether Codex wants the implementation plan rebuilt
   now, or held until the baseline is green.
