# TradeLens Dark Workspace and AI Review Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the authenticated Streamlit product from the current light-workspace hybrid into a premium tonal-dark workspace that matches the TradeLens marketing identity, while making AI Reviews faster to scan, smoother during generation, and less visually clunky without changing product behavior, AI safety boundaries, persistence, or database schema.

**Architecture:** Keep Streamlit, Python, SQLAlchemy, Pandas, and Plotly. Retarget the shared token and component layer first, then migrate each existing page onto the dark system. Add one pure presentation parser for AI-generated Markdown so long reviews can be navigated progressively while the complete model response remains accessible and safely rendered. No AI service, prompt, database, authentication, or tenancy redesign is part of this phase.

**Tech Stack:** Python 3, Streamlit, Plotly, Pandas, SQLAlchemy, pytest, Streamlit AppTest, Ruff, Black, headless Chrome/browser verification.

## Global Constraints

- Treat the supplied TradeZella images as layout and interaction references only. Do not copy its brand, purple palette, scoring model, iconography, copy, or proprietary feature set.
- Use one fixed tonal-dark product theme. Do not add a user theme switcher.
- Do not make the interface one flat black surface. Preserve hierarchy with separate canvas, rail, panel, elevated panel, chart stage, field, and research-note tones.
- Preserve every current destination and workflow: Overview, New Trade, Journal, Analytics, AI Reviews, Strategy Profile, Settings, authentication, import/export, sample data, and destructive-action confirmations.
- Preserve the current information architecture and the mobile `More` sheet unless a task explicitly changes its presentation.
- Keep AI post-trade, reflective, and evidence-backed. Never introduce signals, predictions, live-trade advice, or entry recommendations.
- Never render model output with `unsafe_allow_html=True`. Generated prose must continue through Streamlit Markdown with HTML disabled.
- Do not change `src/tradelens/services/`, `src/tradelens/db/`, migrations, or persisted schemas in this plan.
- Do not add React, FastAPI, JavaScript injection, a new CSS framework, a new icon library, or a new runtime dependency.
- All colors, typography, spacing, radii, shadows, and motion values belong in `src/tradelens/ui/design_system.py`. Page modules may consume tokens and shared components but may not define raw color literals.
- Red remains reserved for losses, destructive actions, and errors. Green remains reserved for profitable outcomes or confirmed success. Teal is the product action/focus color.
- Color must never be the sole carrier of meaning; signs, labels, shapes, and text remain present.
- All visible interactive targets must be at least 44×44 CSS pixels at desktop, tablet, touch-tablet, and phone widths.
- Honor `prefers-reduced-motion: reduce`; no required information may depend on animation.
- Motion must use opacity and transform only, be 120–200 ms, use the shared ease-out, and never animate charts, long tables, validation messages, focus, or page load.
- Keep current exception-containment and tenant-isolation rules. Unexpected exceptions are logged and shown as fixed recovery copy; database, driver, API-key, DSN, SQL, and stack details never reach the UI.
- Keep all existing user-owned working-tree changes untouched. Implement from a clean worktree rather than staging unrelated local files.
- Make one local commit per task. Do not push, open a PR, merge, or deploy until the owner approves the complete phase.
- Use these skills intentionally at every task:
  - `tradelens-ai` for product, safety, stack, and security guardrails.
  - `ui-ux-pro-max` as the primary design reviewer.
  - `frontend-design` for production UI decisions and component hierarchy.
  - `impeccable` for specificity, token, accessibility, and cleanup review.
  - `emil-design-eng` only where motion adds state clarity.
- At every Codex review gate, stop and provide: changed files, focused/full test results, browser evidence, security findings, intentional deviations, local commit hash, and unresolved concerns.

---

## Direction Decision

Adopt a **premium tonal-dark workspace**, not an all-black skin.

The marketing site already establishes TradeLens as dark, analytical, and teal-led. Extending that identity into the product removes the current visual handoff from a dark marketing page to a bright application. The product still needs internal depth, so the working palette should distinguish at least these roles:

| Role | Proposed value | Purpose |
|---|---:|---|
| App canvas | `#091216` | Quiet page background |
| Navigation rail | `#071014` | Deepest structural surface |
| Primary panel | `#101B20` | Tables, filters, forms, composed sections |
| Elevated panel | `#152329` | Selected controls, temporary overlays, important readouts |
| Chart stage | `#0C181D` | Plotly instruments |
| Field surface | `#122026` | Inputs and selectors |
| Primary text | `#ECF5F4` | Main copy and values |
| Secondary text | `#91A3A7` | Descriptions and metadata |
| Hairline | `#26373D` | Structure without card-box noise |
| Action/focus | existing bright TradeLens teal | Primary actions and focus rings |

These values are design inputs, not permission to scatter literals. After Task 1, their values must exist only as Python/CSS tokens in `design_system.py`.

“Smoother AI” means:

1. The first useful conclusion is visible before the full note.
2. Long notes have a readable section index instead of one uninterrupted wall.
3. Existing generated content remains visible during regeneration.
4. First-load waiting preserves layout with a restrained skeleton.
5. Sample, confidence, and limitations stay attached to claims.
6. Complete generated prose remains accessible; no information is silently discarded.
7. No chat interface, animated assistant mascot, live coach, or new AI endpoint is added.

---

## Preflight: Isolate the Work and Prove the Baseline

**Files:** No product files changed.

- [ ] Read completely:
  - `/Users/ayoub/tradelens-ai/AGENTS.md`
  - `/Users/ayoub/tradelens-ai/PRODUCT.md`
  - `/Users/ayoub/tradelens-ai/.claude/MEMORY.md`
  - `/Users/ayoub/tradelens-ai/.agents/skills/tradelens-ai/SKILL.md`
  - `/Users/ayoub/tradelens-ai/docs/superpowers/specs/2026-07-27-streamlit-premium-redesign-design.md`
  - this plan.
- [ ] Record `git status --short` in the original checkout. Do not stage, amend, restore, format, or copy its unrelated modifications.
- [ ] Use `superpowers:using-git-worktrees` to create a clean worktree from current `main`:

```bash
git fetch origin
git worktree add ../tradelens-dark-workspace -b codex/dark-workspace-ai-review origin/main
```

- [ ] Run the baseline from `/Users/ayoub/tradelens-dark-workspace`:

```bash
pytest tests/
ruff check src/ scripts/
black --check src/ scripts/
git diff --check
```

- [ ] Start the current app with the project’s normal environment and capture baseline screenshots at 1440, 1024, coarse-pointer 768, and coarse-pointer 375 for all seven destinations.
- [ ] Confirm current baseline behavior before changing presentation:
  - New Trade preserves draft values across all five steps.
  - Journal row → detail → back and calendar day → detail both work.
  - Analytics renders one selected lens at a time.
  - AI Patterns, Weekly Recap, and Daily Debrief preserve cached notes and regenerate without exposing exceptions.
  - Strategy starter and edits persist.
  - Settings import/export and destructive confirmations remain tenant-scoped.

Do not create a baseline commit.

---

## Task 1: Establish the Dark Workspace Contract

**Purpose:** Make the visual direction explicit and testable before changing pages.

**Files:**

- Modify: `PRODUCT.md`
- Modify: `docs/superpowers/specs/2026-07-27-streamlit-premium-redesign-design.md`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `src/tradelens/ui/components/theme.py`
- Modify: `.streamlit/config.toml`
- Modify: `tests/test_design_system.py`
- Modify: `tests/test_theme.py`

### 1.1 Write the failing contract tests

- [ ] Replace assertions that require a light workspace with assertions for the new tonal-dark roles.
- [ ] Add tests that the public role tokens exist and have sufficient composited contrast:

```python
def test_dark_workspace_roles_are_distinct():
    assert TL_CANVAS != TL_RAIL
    assert TL_CANVAS != TL_PANEL
    assert TL_PANEL != TL_PANEL_ELEVATED
    assert TL_CHART_STAGE != TL_PANEL


def test_dark_workspace_text_contrast_meets_aa():
    assert contrast_ratio(TL_TEXT, TL_CANVAS) >= 4.5
    assert contrast_ratio(TL_TEXT, TL_PANEL) >= 4.5
    assert contrast_ratio(TL_TEXT_MUTED, TL_CANVAS) >= 4.5
    assert contrast_ratio(TL_TEXT_MUTED, TL_PANEL) >= 4.5
```

- [ ] Add a test that `.streamlit/config.toml` declares `base = "dark"` and maps primary/background/secondary/text colors to the dark contract.
- [ ] Keep the existing test that rejects raw color literals outside `:root` and extend it to every new dark role.
- [ ] Add a test that the previous light canvas and paper values are retired from active workspace selectors, while allowing them in historical documentation only.

- [ ] Run and verify the new tests fail for the expected light-workspace assumptions:

```bash
pytest tests/test_design_system.py tests/test_theme.py -q
```

### 1.2 Implement the token retarget

- [ ] Define semantic Python roles in `design_system.py` rather than reusing ambiguous legacy names:

```python
TL_CANVAS = "#091216"
TL_RAIL = "#071014"
TL_PANEL = "#101B20"
TL_PANEL_ELEVATED = "#152329"
TL_CHART_STAGE = "#0C181D"
TL_FIELD = "#122026"
TL_TEXT = "#ECF5F4"
TL_TEXT_MUTED = "#91A3A7"
TL_HAIRLINE = "#26373D"
```

- [ ] Export the same roles as CSS custom properties under the single `:root` block.
- [ ] Preserve the established TradeLens teal, success, danger, warning, type, spacing, radius, and motion ramps unless contrast testing requires a documented adjustment.
- [ ] Update `theme.py` re-exports so page code imports roles rather than literal values.
- [ ] Update the spec and `PRODUCT.md` to state that the authenticated product uses one fixed tonal-dark workspace. Explicitly mark the previous light-workspace contract as superseded by this approved phase.
- [ ] Preserve all non-theme product constraints in both documents.

### 1.3 Skill review

- [ ] `ui-ux-pro-max`: review hierarchy and AA contrast across every proposed surface pairing.
- [ ] `frontend-design`: verify the palette feels TradeLens-specific and avoids generic SaaS black-card styling.
- [ ] `impeccable`: remove alias duplication, stale light literals, unused shadows, and specificity workarounds made obsolete by the retarget.
- [ ] `emil-design-eng`: define no new motion in this task; confirm existing motion tokens remain valid on dark surfaces.

### 1.4 Verify and commit

```bash
pytest tests/test_design_system.py tests/test_theme.py -q
ruff check src/tradelens/ui/design_system.py src/tradelens/ui/components/theme.py tests/test_design_system.py tests/test_theme.py
black --check src/tradelens/ui/design_system.py src/tradelens/ui/components/theme.py tests/test_design_system.py tests/test_theme.py
git diff --check
git add PRODUCT.md docs/superpowers/specs/2026-07-27-streamlit-premium-redesign-design.md src/tradelens/ui/design_system.py src/tradelens/ui/components/theme.py .streamlit/config.toml tests/test_design_system.py tests/test_theme.py
git commit -m "feat(ui): establish tonal dark workspace contract"
```

**Codex Review Gate A:** Review the contract, token graph, contrast math, documentation consistency, and absence of scope expansion before Task 2.

---

## Task 2: Retarget the Shared Shell and Workspace Primitives

**Purpose:** Make every page inherit a coherent dark product shell before page-specific polish.

**Files:**

- Modify: `src/tradelens/ui/components/sidebar.py`
- Modify: `src/tradelens/ui/components/workspace.py`
- Modify: `src/tradelens/ui/components/ui.py`
- Modify: `src/tradelens/ui/components/demo_banner.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/test_premium_shell.py`
- Modify: `tests/test_workspace_components.py`
- Modify: `tests/test_pages_boot.py`

### 2.1 Write failing shared-component tests

- [ ] Assert the app canvas, main block container, masthead, filter disclosures, KPI strip, Evidence Rail, empty states, status banners, page links, and mobile `More` sheet consume dark semantic tokens.
- [ ] Assert no component introduces a second filled primary action in the rail.
- [ ] Assert the rail and canvas remain visually distinct at desktop and compact-tablet widths.
- [ ] Assert every shared component escapes caller-provided values before inserting authored HTML.
- [ ] Keep tests for `aria-current`, visually hidden current-page text, 44px targets, and reduced motion.

```bash
pytest tests/test_premium_shell.py tests/test_workspace_components.py tests/test_pages_boot.py -q
```

### 2.2 Implement the dark shell

- [ ] Retarget the main Streamlit app view, header, sidebar, collapsed sidebar handle, bottom navigation, mobile `More` sheet, and safe-area reservation to dark roles.
- [ ] Keep the rail as the deepest surface and the canvas one step lighter.
- [ ] Use hairlines and spacing for hierarchy; avoid enclosing every section in a rounded rectangle.
- [ ] Preserve the single bright `Log completed trade` action and outlined `Sign out` action.
- [ ] Retarget KPI strips and Evidence Rails so they read as ruled editorial structures, not generic cards.
- [ ] Ensure shared text rules are anchored strongly enough to beat Streamlit’s Markdown stylesheet without `!important` sprawl.
- [ ] Keep the mobile `More` sheet closed on arrival and after navigation; keep all three destinations keyboard and touch reachable.

### 2.3 Skill review

- [ ] `ui-ux-pro-max`: review desktop/tablet/phone navigation, touch targets, focus order, and current-page clarity.
- [ ] `frontend-design`: review surface hierarchy and remove any “dark cards floating on dark cards” effect.
- [ ] `impeccable`: audit Streamlit selector specificity, duplicate rules, raw colors, unscoped test IDs, and hover-only fixes.
- [ ] `emil-design-eng`: retain the existing 160 ms mobile-sheet reveal only; confirm no navigation item shifts position.

### 2.4 Browser verification

- [ ] At 1440, 1024, coarse-pointer 768, and coarse-pointer 375 verify:
  - zero horizontal overflow;
  - rail and bottom bar never appear together;
  - all targets are at least 44px;
  - all focus rings are visible;
  - no hover-gated rule contains non-hover color or layout behavior;
  - contrast passes after alpha compositing;
  - `More` links are not tabbable while closed.

### 2.5 Verify and commit

```bash
pytest tests/test_premium_shell.py tests/test_workspace_components.py tests/test_pages_boot.py -q
ruff check src/tradelens/ui/components/sidebar.py src/tradelens/ui/components/workspace.py src/tradelens/ui/components/ui.py src/tradelens/ui/components/demo_banner.py src/tradelens/ui/design_system.py tests/test_premium_shell.py tests/test_workspace_components.py tests/test_pages_boot.py
black --check src/tradelens/ui/components/sidebar.py src/tradelens/ui/components/workspace.py src/tradelens/ui/components/ui.py src/tradelens/ui/components/demo_banner.py tests/test_premium_shell.py tests/test_workspace_components.py tests/test_pages_boot.py
git diff --check
git add src/tradelens/ui/components/sidebar.py src/tradelens/ui/components/workspace.py src/tradelens/ui/components/ui.py src/tradelens/ui/components/demo_banner.py src/tradelens/ui/design_system.py tests/test_premium_shell.py tests/test_workspace_components.py tests/test_pages_boot.py
git commit -m "feat(ui): retarget premium shell to dark workspace"
```

---

## Task 3: Darken Forms, Tables, Disclosures, and Status States Globally

**Purpose:** Fix the common Streamlit chrome once so pages do not each reinvent dark inputs and tables.

**Files:**

- Modify: `src/tradelens/ui/design_system.py`
- Modify: `src/tradelens/ui/components/auth_screen.py`
- Modify: `tests/test_design_system.py`
- Modify: `tests/test_auth_screen.py`
- Modify: `tests/test_page_polish.py`

### 3.1 Write failing component-state tests

- [ ] Cover text input, textarea, date input, time input, selectbox, multiselect, radio, checkbox, file uploader, download button, normal button, page link, expander, data frame, disabled control, inline status, inline error, and danger states.
- [ ] Assert visible values, labels, help text, placeholders, and menu items meet contrast requirements.
- [ ] Assert disabled controls remain visibly unavailable and are excluded only where WCAG permits inactive-content contrast exemptions.
- [ ] Assert loss/error red is not used for warnings or missing optional configuration.
- [ ] Assert all app-owned controls have 44px visible wrappers at every width.

```bash
pytest tests/test_design_system.py tests/test_auth_screen.py tests/test_page_polish.py -q
```

### 3.2 Implement common control styling

- [ ] Retarget BaseWeb wrappers and Streamlit test-ID selectors using the narrowest proven selectors already recorded in `test_design_system.py`.
- [ ] Style menus, selected values, empty option lists, upload instructions, and calendar popovers on dark surfaces.
- [ ] Keep native semantics and focus behavior; do not replace widgets with authored HTML.
- [ ] Retarget the authentication card to the same product system while preserving its stronger privacy/entry boundary.
- [ ] Keep errors persistent and local to their fields rather than converting them to transient toast messages.

### 3.3 Skill review

- [ ] `ui-ux-pro-max`: inspect label/value hierarchy, validation comprehension, keyboard focus, and disabled-state clarity.
- [ ] `frontend-design`: keep fields quiet; do not use neon outlines when unfocused.
- [ ] `impeccable`: verify selectors reach tooltip-wrapped controls, reject `transition: all`, and remove stale light-surface overrides.
- [ ] `emil-design-eng`: add no form motion; validation and focus must be immediate.

### 3.4 Verify and commit

```bash
pytest tests/test_design_system.py tests/test_auth_screen.py tests/test_page_polish.py -q
ruff check src/tradelens/ui/design_system.py src/tradelens/ui/components/auth_screen.py tests/test_design_system.py tests/test_auth_screen.py tests/test_page_polish.py
black --check src/tradelens/ui/components/auth_screen.py tests/test_design_system.py tests/test_auth_screen.py tests/test_page_polish.py
git diff --check
git add src/tradelens/ui/design_system.py src/tradelens/ui/components/auth_screen.py tests/test_design_system.py tests/test_auth_screen.py tests/test_page_polish.py
git commit -m "feat(ui): unify dark controls and data surfaces"
```

**Codex Review Gate B:** Review Tasks 2–3 together in the live browser, with special attention to selector safety, authentication, exception containment, 44px targets, keyboard operation, coarse-pointer behavior, and contrast.

---

## Task 4: Recompose Overview as a Dark Command Center

**Purpose:** Preserve the existing focused Overview while making it visually continuous with the marketing identity and easier to scan.

**Files:**

- Modify: `src/tradelens/ui/app.py`
- Modify: `src/tradelens/ui/components/trade_calendar.py`
- Modify: `src/tradelens/ui/components/charts.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_charts.py`

### 4.1 Write failing Overview tests

- [ ] Keep the current information order: masthead → filter → ruled KPI strip → standing/calendar → dominant equity instrument → evidence-backed readout → recent-trade ledger.
- [ ] Assert there is still only one dominant chart and no quick-action card grid.
- [ ] Assert the compact calendar uses readable dark positive, negative, breakeven, and empty-day states with a textual legend.
- [ ] Assert the chart stage uses dark roles and the sample annotation remains inside the stage at phone and desktop widths.
- [ ] Assert sparse data still suppresses unsupported trend claims.

```bash
pytest tests/test_dashboard.py tests/test_charts.py -q
```

### 4.2 Implement the page treatment

- [ ] Darken the Overview canvas and all ruled structures without turning the KPI strip into five separate floating cards.
- [ ] Give the equity curve the highest visual weight; use the existing teal trajectory and restrained area fill.
- [ ] Use calendar cell fills at low saturation, retain value signs/labels, and avoid TradeZella purple.
- [ ] Keep the Evidence Rail next to the readout and preserve current confidence/sample logic.
- [ ] Keep the ledger neutral by row; use semantic color only for signed money and explicit result markers.

### 4.3 Skill review

- [ ] `ui-ux-pro-max`: confirm five-second comprehension and that a trader can answer “where do I stand?” without scanning the whole page.
- [ ] `frontend-design`: ensure the result is an authored command center, not a copied widget dashboard.
- [ ] `impeccable`: remove redundant headings, duplicated labels, excess borders, and decorative chart chrome.
- [ ] `emil-design-eng`: no chart draw animation; preserve only existing low-frequency state reveals.

### 4.4 Verify and commit

```bash
pytest tests/test_dashboard.py tests/test_charts.py tests/test_data_state.py -q
ruff check src/tradelens/ui/app.py src/tradelens/ui/components/trade_calendar.py src/tradelens/ui/components/charts.py tests/test_dashboard.py tests/test_charts.py
black --check src/tradelens/ui/app.py src/tradelens/ui/components/trade_calendar.py src/tradelens/ui/components/charts.py tests/test_dashboard.py tests/test_charts.py
git diff --check
git add src/tradelens/ui/app.py src/tradelens/ui/components/trade_calendar.py src/tradelens/ui/components/charts.py src/tradelens/ui/design_system.py tests/test_dashboard.py tests/test_charts.py
git commit -m "feat(ui): compose dark overview command center"
```

---

## Task 5: Refine New Trade and Journal on the Dark Workspace

**Purpose:** Make the two highest-frequency workflows feel calm and fast while preserving all interaction contracts.

**Files:**

- Modify: `src/tradelens/ui/pages/1_NewTrade.py`
- Modify: `src/tradelens/ui/components/trade_wizard.py`
- Modify: `src/tradelens/ui/pages/2_Trades.py`
- Modify: `src/tradelens/ui/components/trade_calendar.py`
- Modify: `src/tradelens/ui/components/ai_autofill_review.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/test_trade_wizard.py`
- Modify: `tests/test_premium_page_contracts.py`
- Modify: `tests/journal_flow_check.py`
- Modify: `tests/test_pages_boot.py`

### 5.1 Preserve the interaction tests first

- [ ] Keep all three Journal interaction paths green:
  1. ledger row → detail → back → ledger;
  2. calendar day → trade opener → detail;
  3. AI summary renders as safe Markdown with its Evidence Rail separate.
- [ ] Keep the five-step wizard state tests: forward/back, draft survival, blocking-field validation, optional reflection fields, save, and scoped reset.
- [ ] Add assertions that the dark conversion does not restore stacked tab bodies or a red/green full-row ledger.
- [ ] Add a boot state for first-time empty Journal, sample Journal, filtered Journal, and selected Trade Detail.

```bash
pytest tests/test_trade_wizard.py tests/test_premium_page_contracts.py tests/test_pages_boot.py -q
python tests/journal_flow_check.py
```

### 5.2 Implement New Trade

- [ ] Keep the five-step wizard and session-state ownership unchanged.
- [ ] Make the current step, completed steps, blocking errors, and next/back action bar clear on dark surfaces.
- [ ] Use quiet progress and one primary action; do not create five bright pills.
- [ ] Keep screenshot AI confirmation user-controlled and preserve all current write staging.
- [ ] Keep first-load and analysis waiting states stable in height.

### 5.3 Implement Journal

- [ ] Keep Trades, Calendar, and Trade Detail as mutually exclusive native radio views.
- [ ] Keep the filter bar compact and preserve `More filters` progressive disclosure.
- [ ] Retarget the data frame, calendar, trade openers, detail ticket, and generated summary to tonal-dark surfaces.
- [ ] Keep the ledger neutral and scannable; do not add heavy cell boxes or every-row gradients.
- [ ] Keep the 7-column phone calendar and 44px day cells.

### 5.4 Skill review

- [ ] `ui-ux-pro-max`: perform keyboard and touch walkthroughs of every wizard step and Journal path.
- [ ] `frontend-design`: check density, action hierarchy, and form pacing.
- [ ] `impeccable`: audit session-state ownership, widget keys, selectors, redundant banners, and safe Markdown paths.
- [ ] `emil-design-eng`: retain only the 180 ms step/detail reveal; verify it fires once and is removed under reduced motion.

### 5.5 Verify and commit

```bash
pytest tests/test_trade_wizard.py tests/test_premium_page_contracts.py tests/test_pages_boot.py -q
python tests/journal_flow_check.py
ruff check src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/components/trade_wizard.py src/tradelens/ui/pages/2_Trades.py src/tradelens/ui/components/trade_calendar.py src/tradelens/ui/components/ai_autofill_review.py tests/test_trade_wizard.py tests/test_premium_page_contracts.py tests/journal_flow_check.py tests/test_pages_boot.py
black --check src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/components/trade_wizard.py src/tradelens/ui/pages/2_Trades.py src/tradelens/ui/components/trade_calendar.py src/tradelens/ui/components/ai_autofill_review.py tests/test_trade_wizard.py tests/test_premium_page_contracts.py tests/journal_flow_check.py tests/test_pages_boot.py
git diff --check
git add src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/components/trade_wizard.py src/tradelens/ui/pages/2_Trades.py src/tradelens/ui/components/trade_calendar.py src/tradelens/ui/components/ai_autofill_review.py src/tradelens/ui/design_system.py tests/test_trade_wizard.py tests/test_premium_page_contracts.py tests/journal_flow_check.py tests/test_pages_boot.py
git commit -m "feat(ui): refine dark trade and journal workflows"
```

**Codex Review Gate C:** Re-run the three Journal interactions and the full wizard as a second lens. Review state persistence, model-output safety, exception handling, tenancy, keyboard behavior, and mobile calendar geometry before Analytics work.

---

## Task 6: Turn Analytics into a Unified Dark Instrument Panel

**Purpose:** Keep the existing four-question lens architecture and improve its visual continuity, data density, and chart readability.

**Files:**

- Modify: `src/tradelens/ui/pages/4_Analytics.py`
- Modify: `src/tradelens/ui/components/charts.py`
- Modify: `src/tradelens/ui/components/trade_calendar.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/test_charts.py`
- Modify: `tests/test_pages_boot.py`
- Modify: `tests/test_premium_page_contracts.py`

### 6.1 Write failing Analytics tests

- [ ] Keep exactly four lenses: Performance, Risk, Timing, Setups.
- [ ] Keep exactly one lens body rendered at a time.
- [ ] Assert each lens follows: question → ruled KPI strip → instrument → ranked evidence → editorial readout/Evidence Rail.
- [ ] Assert all Plotly figures pass through `apply_chart_stage`.
- [ ] Assert only two stage heights exist: 360 dominant and 240 supporting.
- [ ] Keep the fixed-risk alternative, one-category claim limits, filtered calendar, and in-stage sample annotations.
- [ ] Add dark-axis, gridline, trace, annotation, positive, and negative contrast checks.

```bash
pytest tests/test_charts.py tests/test_pages_boot.py tests/test_premium_page_contracts.py -q
```

### 6.2 Implement the dark instrument system

- [ ] Retarget `apply_chart_stage` so every chart gets consistent dark paper/plot backgrounds, margins, axis labels, gridlines, legends, and annotation bands.
- [ ] Keep chart colors semantic and limited; do not use a rainbow palette.
- [ ] Make filter controls quiet and keep lens selection visually secondary to the current question.
- [ ] Preserve all current comparability rules so one category is never described as strongest or weakest.
- [ ] Keep chart/table/readout composition editorial; do not split every metric into a separate widget card.

### 6.3 Skill review

- [ ] `ui-ux-pro-max`: review quantitative legibility, sample caveats, and mobile plot comprehension.
- [ ] `frontend-design`: ensure the four lenses feel like one product instrument, not four templates.
- [ ] `impeccable`: inspect Plotly defaults, clipped annotations, excessive tick density, and duplicate legends.
- [ ] `emil-design-eng`: no chart animation; lens changes may use the existing short content reveal only if it does not replay on unrelated reruns.

### 6.4 Verify and commit

```bash
pytest tests/test_charts.py tests/test_pages_boot.py tests/test_premium_page_contracts.py -q
ruff check src/tradelens/ui/pages/4_Analytics.py src/tradelens/ui/components/charts.py src/tradelens/ui/components/trade_calendar.py tests/test_charts.py tests/test_pages_boot.py tests/test_premium_page_contracts.py
black --check src/tradelens/ui/pages/4_Analytics.py src/tradelens/ui/components/charts.py src/tradelens/ui/components/trade_calendar.py tests/test_charts.py tests/test_pages_boot.py tests/test_premium_page_contracts.py
git diff --check
git add src/tradelens/ui/pages/4_Analytics.py src/tradelens/ui/components/charts.py src/tradelens/ui/components/trade_calendar.py src/tradelens/ui/design_system.py tests/test_charts.py tests/test_pages_boot.py tests/test_premium_page_contracts.py
git commit -m "feat(ui): unify dark analytics instrument panel"
```

---

## Task 7: Add a Pure AI Review Document Model

**Purpose:** Make long generated reviews navigable without changing model calls, prompts, caching, or stored content.

**Files:**

- Create: `src/tradelens/ui/components/review_document.py`
- Create: `tests/test_review_document.py`
- Modify: `src/tradelens/ui/components/__init__.py`

### 7.1 Define the pure interface

- [ ] Add immutable presentation types and a parser that uses only the standard library:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewSection:
    id: str
    title: str
    markdown: str


@dataclass(frozen=True)
class ReviewDocument:
    intro_markdown: str
    sections: tuple[ReviewSection, ...]


def parse_review_markdown(content_md: str) -> ReviewDocument:
    """Split H2/H3-authored AI Markdown into stable display sections."""
```

- [ ] The parser must:
  - preserve the original Markdown text of every section;
  - accept `##` and `###` headings;
  - keep prose before the first heading as `intro_markdown`;
  - create deterministic, unique IDs for duplicate headings;
  - ignore heading-looking text inside fenced code blocks;
  - return one safe fallback section when content has no headings;
  - return an empty document for blank content;
  - perform no HTML rendering, model calls, database access, or Streamlit calls.

### 7.2 Write failing parser tests

- [ ] Cover blank content, intro prose, H2 sections, H3 sections, duplicate headings, punctuation, Unicode, fenced code, no headings, and preservation of bullets/numbering/emphasis.
- [ ] Add a round-trip assertion that concatenating the parsed intro and section Markdown preserves all substantive source lines.

```python
def test_duplicate_headings_receive_stable_unique_ids():
    doc = parse_review_markdown("## Review\nA\n## Review\nB")
    assert [section.id for section in doc.sections] == ["review", "review-2"]


def test_heading_like_code_is_not_a_section():
    doc = parse_review_markdown("## Summary\n```md\n## Not a section\n```")
    assert [section.title for section in doc.sections] == ["Summary"]
```

```bash
pytest tests/test_review_document.py -q
```

### 7.3 Implement minimally

- [ ] Use a line-oriented parser with fence tracking and a compiled heading expression. Do not import a Markdown parser dependency.
- [ ] Normalize IDs using ASCII lowercase letters/numbers/hyphens, with `section` as the deterministic empty-slug fallback.
- [ ] Export only the three public names through `components/__init__.py` if the project convention requires it; otherwise import directly from the module.

### 7.4 Verify and commit

```bash
pytest tests/test_review_document.py -q
ruff check src/tradelens/ui/components/review_document.py tests/test_review_document.py
black --check src/tradelens/ui/components/review_document.py tests/test_review_document.py
git diff --check
git add src/tradelens/ui/components/review_document.py src/tradelens/ui/components/__init__.py tests/test_review_document.py
git commit -m "feat(ui): add ai review document model"
```

---

## Task 8: Rebuild AI Reviews Around Progressive Reading

**Purpose:** Make Patterns, Weekly Recap, and Daily Debrief feel smooth and concise while preserving complete evidence-backed content.

**Files:**

- Modify: `src/tradelens/ui/pages/6_Insights.py`
- Modify: `src/tradelens/ui/components/workspace.py`
- Modify: `src/tradelens/ui/components/review_document.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/test_insights_page.py`
- Modify: `tests/test_workspace_components.py`
- Modify: `tests/test_pages_boot.py`

### 8.1 Write failing AI experience tests

- [ ] Keep existing tests for automatic generation, caching, confidence, evidence disclosure, exception containment, and banned trade-action language.
- [ ] Add tests that generated notes use `parse_review_markdown` and render:
  - one concise note header;
  - one visible lead section;
  - a section navigator when more than one section exists;
  - one selected section body at a time in focused mode;
  - an explicit `Read full note` path that renders all original sections;
  - one Evidence Rail for the note, not repeated under every paragraph.
- [ ] Assert model Markdown is passed to `st.markdown` with HTML disabled.
- [ ] Assert regeneration keeps the previous note visible and marks it as updating; the skeleton appears only when no prior note exists.
- [ ] Assert the active section survives an unrelated rerun and clamps safely when a newly generated document has fewer sections.
- [ ] Assert Patterns, Weekly Recap, and Daily Debrief share the same reading shell even though Patterns begins as a structured `ResearchNote` rather than model Markdown.

```bash
pytest tests/test_insights_page.py tests/test_workspace_components.py tests/test_pages_boot.py -q
```

### 8.2 Add the shared reading shell

- [ ] Define a pure render contract in `workspace.py`:

```python
def render_review_reader(
    *,
    document: ReviewDocument,
    active_section_id: str | None,
    show_full_note: bool,
    evidence: EvidenceRail,
    updating: bool = False,
) -> str | None:
    """Render the note and return the selected section ID."""
```

- [ ] Use native Streamlit controls for section selection; do not inject JavaScript.
- [ ] Desktop composition: narrow section index plus one readable content column, with a maximum reading measure.
- [ ] Phone composition: stacked section selector followed by content; no horizontal scroll and no offscreen sticky panel.
- [ ] Keep the complete note available through `Read full note`; never truncate or discard generated text.
- [ ] Put sample, confidence, period, and limitation in one Evidence Rail below the reading body.

### 8.3 Smooth the three states

- [ ] **No note yet:** stable-height skeleton and clear neutral copy.
- [ ] **Note ready:** selected section visible immediately.
- [ ] **Regenerating:** old note stays visible, controls are safely disabled where needed, and an inline `Updating review…` state is announced without page jump.
- [ ] **Unexpected failure:** old note remains; show fixed generic recovery copy and log the exception.
- [ ] **Domain-safe failure:** preserve the current trader-safe specific explanation.

### 8.4 Preserve AI and security boundaries

- [ ] Do not edit files under `src/tradelens/services/`.
- [ ] Do not add new prompts or AI calls.
- [ ] Do not expose model reasoning, tokens, raw request payloads, costs, stack traces, or exception strings in the note.
- [ ] Keep all existing user scoping and cache keys.
- [ ] Keep “reflection only—never signals or advice” visible but avoid repeating it in every section.

### 8.5 Skill review

- [ ] `ui-ux-pro-max`: time-to-first-insight, reading measure, section navigation, keyboard order, and phone comprehension.
- [ ] `frontend-design`: make the note feel like a premium research document, not a chat transcript or reusable card grid.
- [ ] `impeccable`: inspect safe Markdown paths, state ownership, loading continuity, duplicated evidence, empty headings, and stale section IDs.
- [ ] `emil-design-eng`: one 160–180 ms opacity/4px section transition only when the user changes sections; no animation on initial page load, regeneration text, errors, or reduced motion.

### 8.6 Browser and interaction verification

- [ ] At 1440 and coarse-pointer 375 verify all three lenses in first-load, cached, regenerating, success, and failure states.
- [ ] Keyboard-open evidence disclosure and navigate every section.
- [ ] Sample the DOM throughout regeneration to prove the previous note never disappears.
- [ ] Verify content width does not stretch into the unused right side and no section becomes a 1,000px-wide paragraph.

### 8.7 Verify and commit

```bash
pytest tests/test_insights_page.py tests/test_workspace_components.py tests/test_pages_boot.py tests/test_review_document.py -q
ruff check src/tradelens/ui/pages/6_Insights.py src/tradelens/ui/components/workspace.py src/tradelens/ui/components/review_document.py tests/test_insights_page.py tests/test_workspace_components.py tests/test_pages_boot.py tests/test_review_document.py
black --check src/tradelens/ui/pages/6_Insights.py src/tradelens/ui/components/workspace.py src/tradelens/ui/components/review_document.py tests/test_insights_page.py tests/test_workspace_components.py tests/test_pages_boot.py tests/test_review_document.py
git diff --check
git add src/tradelens/ui/pages/6_Insights.py src/tradelens/ui/components/workspace.py src/tradelens/ui/components/review_document.py src/tradelens/ui/design_system.py tests/test_insights_page.py tests/test_workspace_components.py tests/test_pages_boot.py tests/test_review_document.py
git commit -m "feat(ui): streamline ai review reading flow"
```

**Codex Review Gate D:** Perform a security and interaction review of the AI layer. Specifically verify safe Markdown, no new AI calls, cache stability, tenant scoping, exception containment, full-content availability, regeneration continuity, banned-language compliance, and reduced-motion behavior.

---

## Task 9: Finish Strategy Profile and Settings in the Dark System

**Purpose:** Complete the theme without disturbing the playbook and account-safety workflows.

**Files:**

- Modify: `src/tradelens/ui/pages/5_Strategy.py`
- Modify: `src/tradelens/ui/pages/9_Settings.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/strategy_flow_check.py`
- Modify: `tests/settings_flow_check.py`
- Modify: `tests/test_premium_page_contracts.py`
- Modify: `tests/test_pages_boot.py`

### 9.1 Preserve real persistence tests

- [ ] Keep the Strategy subprocess scenarios: starter persistence, blank-name refusal, corrected save, untouched-field preservation, and contained write failure with no DSN leak.
- [ ] Keep Settings scenarios: profile/preferences persistence, sample data load/clear, tenant-scoped export, sanitized import failures, exact destructive confirmation, account deletion, sign-out, and other-account preservation.
- [ ] Add visual-contract assertions for dark playbook summary, dark accordions, dark data controls, and a single contained Danger Zone.

```bash
python tests/strategy_flow_check.py
python tests/settings_flow_check.py
pytest tests/test_premium_page_contracts.py tests/test_pages_boot.py -q
```

### 9.2 Implement Strategy Profile

- [ ] Keep the 6-of-6 completion truth, saved facets, starter behavior, form fields, five accordions, one local error slot, and one restrained save action.
- [ ] Use subtle panels and hairlines so opened accordions do not look like a stack of oversized cards.
- [ ] Preserve the scoped 180 ms accordion reveal and its no-replay/reduced-motion behavior.

### 9.3 Implement Settings

- [ ] Keep Profile, Preferences, Data, and Danger Zone as the four sections.
- [ ] Keep Settings the quietest destination: no chart, no promotional banner, and no bright primary CTA.
- [ ] Keep warning copy amber/neutral and reserve red for the Danger Zone/destructive actions.
- [ ] Keep the Danger Zone border around both disclosures, confirmation fields, and destructive buttons.
- [ ] Do not expose deployment secret names more prominently than the current product requires; prefer user-facing recovery guidance over operator jargon where behavior permits.

### 9.4 Skill review

- [ ] `ui-ux-pro-max`: review long-form editing, status placement, recovery comprehension, and destructive safeguards.
- [ ] `frontend-design`: keep the playbook purposeful and Settings restrained.
- [ ] `impeccable`: inspect error containment, exact confirmations, stale chips, global expander leaks, and repeated form chrome.
- [ ] `emil-design-eng`: keep the playbook-only reveal; Settings remains motionless.

### 9.5 Verify and commit

```bash
python tests/strategy_flow_check.py
python tests/settings_flow_check.py
pytest tests/test_premium_page_contracts.py tests/test_pages_boot.py -q
ruff check src/tradelens/ui/pages/5_Strategy.py src/tradelens/ui/pages/9_Settings.py tests/strategy_flow_check.py tests/settings_flow_check.py tests/test_premium_page_contracts.py tests/test_pages_boot.py
black --check src/tradelens/ui/pages/5_Strategy.py src/tradelens/ui/pages/9_Settings.py tests/strategy_flow_check.py tests/settings_flow_check.py tests/test_premium_page_contracts.py tests/test_pages_boot.py
git diff --check
git add src/tradelens/ui/pages/5_Strategy.py src/tradelens/ui/pages/9_Settings.py src/tradelens/ui/design_system.py tests/strategy_flow_check.py tests/settings_flow_check.py tests/test_premium_page_contracts.py tests/test_pages_boot.py
git commit -m "feat(ui): finish dark playbook and settings"
```

---

## Task 10: Cross-Page Accessibility, Security, and Consistency Audit

**Purpose:** Treat the redesign as a system and catch defects that component tests or desktop resizing miss.

**Files:**

- Modify only when a verified defect requires it: `src/tradelens/ui/design_system.py`
- Modify only when a verified defect requires it: affected files under `src/tradelens/ui/`
- Modify: `tests/test_design_system.py`
- Modify: `tests/test_page_polish.py`
- Modify: `tests/test_pages_boot.py`
- Modify: `tests/test_failure_paths.py`
- Modify: `tests/test_user_isolation.py`
- Create: `tests/test_dark_workspace_audit.py`

### 10.1 Build the audit before fixing findings

- [ ] Test all seven destinations in these contexts:
  - desktop 1440, fine pointer, normal motion;
  - tablet 1024, fine pointer, normal motion;
  - touch tablet 768, `pointer: coarse`, `hover: none`;
  - touch phone 375, `pointer: coarse`, `hover: none`;
  - desktop and phone under reduced motion.
- [ ] Measure fully composited foreground/background contrast rather than treating the first `rgba()` layer as opaque.
- [ ] Audit horizontal overflow, clipped money, unreadable chart labels, uncontained tables, duplicate navigation, hidden-but-tabbable controls, visible focus, target size, and animation under reduced motion.
- [ ] Walk keyboard focus through every destination.
- [ ] Add structural tests that no non-hover color/layout rule can be nested inside a hover/fine-pointer media query.
- [ ] Scan page/component/service exception handlers and fail if an unexpected exception value is interpolated into user-visible UI.
- [ ] Resolve every tenant-scoped service call at its full argument list and verify the active user ID is supplied.

### 10.2 Fix only reproduced defects

- [ ] For every failure, record:
  - exact destination/state/viewport/pointer mode;
  - computed style or exception evidence;
  - smallest responsible selector or component;
  - regression test that fails before the fix and passes after it.
- [ ] Do not use this task for aesthetic redesign or new features.
- [ ] Do not restyle Streamlit’s canvas-backed virtual data-grid internals unless a visible, actionable control is genuinely inaccessible and a safe stable selector exists.

### 10.3 Full verification

```bash
pytest tests/
ruff check src/ scripts/
black --check src/ scripts/
git diff --check
```

- [ ] Confirm service coverage remains at or above the repository’s 80% gate.
- [ ] Confirm no unexpected rendered exception in any audited state.
- [ ] Confirm no AI signal/advice language was introduced.
- [ ] Confirm no schema, service, migration, or dependency change entered the branch.

### 10.4 Four-skill sign-off

- [ ] `ui-ux-pro-max`: accessibility, responsiveness, hierarchy, and five-second comprehension.
- [ ] `frontend-design`: visual coherence and avoidance of generic dark-dashboard tropes.
- [ ] `impeccable`: specificity, token usage, dead CSS, unsafe rendering, exception leakage, and scope discipline.
- [ ] `emil-design-eng`: motion inventory, replay behavior, coarse-pointer behavior, and reduced-motion compliance.

### 10.5 Commit

```bash
git add src/tradelens/ui tests/test_design_system.py tests/test_page_polish.py tests/test_pages_boot.py tests/test_failure_paths.py tests/test_user_isolation.py tests/test_dark_workspace_audit.py
git commit -m "test(ui): verify dark workspace quality gates"
```

**Codex Review Gate E:** Review the complete branch as the independent code/security lens. Do not approve based only on Claude Code’s summary; inspect the diff, run the gates, exercise critical paths, and report findings by severity.

---

## Task 11: Refresh Product Evidence and Re-Score the 10K Checklist

**Purpose:** Update marketing proof only after the product is verified, and measure whether the phase improved the actual weak points.

**Files:**

- Modify: `scripts/capture_app_screenshots.py`
- Modify: the four existing marketing product screenshot assets referenced by the site
- Create: `docs/audits/2026-07-31-dark-workspace-10k-reassessment.md`
- Modify: `tests/test_capture_cleanup.py`
- Modify: relevant marketing screenshot contract tests already present in `tests/`

### 11.1 Preserve capture safety

- [ ] Keep the isolated, seeded SQLite capture database.
- [ ] Keep the ownership marker and exact-directory validation.
- [ ] Keep the Chrome profile inside the owned capture directory.
- [ ] Keep PID-scoped shutdown, `wait`, one cleanup, signal exit codes, and token non-disclosure.
- [ ] Do not write to the developer database.
- [ ] Keep captures under reduced motion.

### 11.2 Capture the verified dark product

- [ ] Capture these four product views with complete, unclipped content:
  1. Overview command center;
  2. New Trade wizard;
  3. Analytics instrument panel;
  4. complete Strategy Profile or concise AI Review reader, choosing the view that best proves the new dark system without overstating AI capability.
- [ ] Verify natural dimensions, declared dimensions, aspect ratio, decode success, alt text, and no marketing-page overflow.
- [ ] Confirm marketing HTML/CSS/JS remains byte-identical unless the owner separately approves marketing changes.

### 11.3 Re-score against the supplied checklist

- [ ] Use `/Users/ayoub/Downloads/The_10K_Checklist.pdf` and record evidence for each applicable criterion.
- [ ] Compare directly with the prior 8.1/10 assessment.
- [ ] Score product experience separately from business proof. Do not inflate the result because the dark theme is more attractive.
- [ ] Explicitly re-evaluate:
  - product/marketing visual continuity;
  - AI review scanability;
  - dashboard distinctiveness;
  - trust/data consistency;
  - responsive/accessibility evidence;
  - screenshot quality;
  - remaining business gaps such as social proof, onboarding proof, or broker automation.

### 11.4 Verify and commit

```bash
pytest tests/test_capture_cleanup.py tests/test_landing.py tests/test_site_metadata.py tests/test_site_copy.py -q
pytest tests/
ruff check src/ scripts/
black --check src/ scripts/
git diff --check
git add scripts/capture_app_screenshots.py tests/test_capture_cleanup.py docs/audits/2026-07-31-dark-workspace-10k-reassessment.md
git add site/assets/shot-dashboard-wide.webp site/assets/shot-newtrade.webp site/assets/shot-analytics.webp site/assets/shot-strategy.webp
git commit -m "docs(ui): refresh dark product evidence and audit"
```

The executor must replace the final `git add` operand with the four already tracked asset paths shown by `git diff --name-only`; it must not add unrelated binary files from the original dirty checkout.

---

## Final Verification and Handoff

- [ ] Run the full project gate from the clean worktree:

```bash
pytest tests/
ruff check src/ scripts/
black --check src/ scripts/
git diff --check
git status --short
```

- [ ] Confirm every task has one local commit and no commit contains unrelated files.
- [ ] Confirm `git diff origin/main...HEAD -- src/tradelens/services src/tradelens/db` is empty.
- [ ] Confirm `git diff origin/main...HEAD -- requirements.txt pyproject.toml` is empty unless those files do not exist.
- [ ] Confirm no untracked capture database, Chrome profile, token, credential, DSN, screenshot scratch file, or temporary artifact remains.
- [ ] Confirm the original `/Users/ayoub/tradelens-ai` dirty working tree is unchanged from the Preflight record.
- [ ] Ask Codex for the final second-lens review and address only reproduced actionable findings.
- [ ] Stop for owner approval. Do not push, open a PR, merge, or deploy.

---

## Plan Self-Review Checklist

- [ ] Re-read the owner’s request and confirm the plan covers both goals: a dark TradeLens-aligned Streamlit product and a smoother AI reading experience.
- [ ] Confirm the plan preserves the already-completed premium IA rather than restarting the redesign.
- [ ] Confirm every named task includes exact files, a failing-test step, implementation boundaries, verification commands, a local commit, and relevant skill reviews.
- [ ] Confirm every new public interface has complete names and types:
  - `ReviewSection`
  - `ReviewDocument`
  - `parse_review_markdown(content_md: str) -> ReviewDocument`
  - `render_review_reader(...) -> str | None`
- [ ] Confirm no task changes AI services, prompts, database schema, migrations, authentication logic, or dependencies.
- [ ] Confirm generated Markdown never enters an HTML-enabled rendering path.
- [ ] Confirm AI regeneration continuity and complete-note access are tested.
- [ ] Confirm coarse-pointer verification is real media emulation, not desktop-only viewport resizing.
- [ ] Confirm all seven destinations and the auth surface are covered by dark-theme verification.
- [ ] Confirm the screenshot task retains exact-directory cleanup, PID ownership, signal semantics, isolated data, and secret non-disclosure.
- [ ] Run an unfinished-marker scan and resolve every result before execution:

```bash
rg -n "TBD|TO[ ]DO|FIXME|fill this in|decide later" docs/superpowers/plans/2026-07-31-streamlit-dark-workspace-ai-review.md
```

- [ ] Run a file-path validation scan:

```bash
python - <<'PY'
from pathlib import Path

required = [
    "src/tradelens/ui/design_system.py",
    "src/tradelens/ui/components/workspace.py",
    "src/tradelens/ui/components/charts.py",
    "src/tradelens/ui/components/trade_wizard.py",
    "src/tradelens/ui/pages/1_NewTrade.py",
    "src/tradelens/ui/pages/2_Trades.py",
    "src/tradelens/ui/pages/4_Analytics.py",
    "src/tradelens/ui/pages/5_Strategy.py",
    "src/tradelens/ui/pages/6_Insights.py",
    "src/tradelens/ui/pages/9_Settings.py",
]
missing = [item for item in required if not Path(item).exists()]
assert not missing, missing
PY
```

---

## Claude Code Kickoff Prompt

Copy this into Claude Code from the TradeLens repository:

```text
Work on the approved TradeLens “Dark Workspace and AI Review Flow” phase.

Repository: /Users/ayoub/tradelens-ai
Implementation plan: /Users/ayoub/tradelens-ai/docs/superpowers/plans/2026-07-31-streamlit-dark-workspace-ai-review.md

Before acting, read AGENTS.md, PRODUCT.md, .claude/MEMORY.md, the project tradelens-ai skill, the current premium redesign spec, and the complete implementation plan. The existing checkout has unrelated user changes, so use superpowers:using-git-worktrees and create a clean worktree/branch exactly as the plan describes. Do not stage, restore, format, or copy the existing dirty files.

Use superpowers:subagent-driven-development as the execution method and superpowers:test-driven-development inside each implementation task. Apply the skills intentionally at every major task/page in this order:
1. tradelens-ai — product, stack, AI-safety, tenancy, and exception guardrails.
2. ui-ux-pro-max — primary design review and accessibility judgment.
3. frontend-design — production UI hierarchy and component decisions.
4. impeccable — CSS specificity, token discipline, state cleanup, security-adjacent rendering review, and final polish.
5. emil-design-eng — motion only where the plan explicitly permits it.

This is not an open-ended redesign. Implement the fixed tonal-dark direction in the plan, preserve every current workflow, and do not copy TradeZella’s brand or feature set. Do not change services, prompts, database schema, migrations, authentication behavior, tenancy, or dependencies. Never render model output with unsafe HTML. Do not push, open a PR, merge, or deploy.

Start with Preflight and Task 1 only. Work test-first, make the single local Task 1 commit, then stop. Report:
- exact files changed;
- focused and full validation results;
- UI/UX Pro Max findings;
- Frontend Design decisions;
- Impeccable cleanup/security findings;
- Emil motion decision;
- browser evidence at the widths required by the task;
- intentional deviations from the plan;
- local commit hash;
- concerns before Task 2.

Wait for owner approval and a Codex second-lens review before continuing.
```
