# TradeLens AI Premium Streamlit Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the signed-in Streamlit product into a premium, organized AI day-trading journal with a light workspace, dark navigation and chart surfaces, a calmer information hierarchy, and evidence-backed AI review experiences while preserving every current workflow.

**Architecture:** Keep the current Python, Streamlit, SQLAlchemy, Pandas, and Plotly stack. Introduce a small presentation layer of pure HTML renderers and pure wizard-state helpers, centralize the fixed hybrid visual system in `design_system.py`, then recompose the existing pages around five destinations and shared editorial patterns. Services, database models, AI prompts, metric calculations, and the marketing site remain unchanged except for replacing the marketing site's in-app screenshots after the product redesign is verified.

**Tech Stack:** Python 3.12, Streamlit 1.50, Pandas, Plotly, SQLAlchemy, pytest, Streamlit AppTest, Ruff, CSS injected through the existing design system.

## Global Constraints

- Preserve all current functionality, stored data, service contracts, analytics math, AI generation behavior, and authentication behavior.
- Do not change files under `src/tradelens/services/`, `src/tradelens/models/`, or database migrations for this visual redesign.
- Keep the product post-trade only and use the project-approved reflective language throughout.
- Keep screenshot AI provenance explicit: AI suggestions are optional, user-confirmed, and never silently applied.
- Keep the marketing site frozen until the signed-in product is complete; then replace only its current in-app screenshots.
- Use one fixed hybrid theme: light workspace, dark sidebar, dark chart stages, and dark focused AI reading surfaces.
- Use UI/UX Pro Max as the primary reviewer for hierarchy, usability, responsive behavior, accessibility, and information density at every page gate.
- Use Frontend Design for production layout, typography, component composition, responsive decisions, and the Evidence Rail signature at every page gate.
- Use Impeccable in operate mode after each page is functionally complete to reduce template repetition, repair spacing, and remove visual residue. Load its craft-floor instructions immediately before the first UI implementation pass.
- Use Emil Design Eng only after the static interface is correct. Motion must be purposeful, use transform and opacity, finish in under 300 ms, support reduced motion, avoid broad transitions, and never animate keyboard navigation.
- Use red only for errors, losses, and destructive actions. Use success green for gains and completion, amber for caution or medium confidence, and teal for brand actions and focus.
- Do not add a theme toggle, new runtime dependency, broker integration, live-trading behavior, schema change, push, pull request, or deployment.
- Do not overwrite unrelated changes in the current dirty worktree. Stage only files named by the active task.

---

## Target Information Architecture

| Destination | Existing file | Product role | Primary action |
|---|---|---|---|
| Overview | `src/tradelens/ui/app.py` | Daily command center | Log completed trade |
| Journal | `src/tradelens/ui/pages/2_Trades.py` | Searchable ledger, calendar, and trade detail | Open a trade |
| Analytics | `src/tradelens/ui/pages/4_Analytics.py` | Composed performance instrument panel | Change analysis lens |
| AI Reviews | `src/tradelens/ui/pages/6_Insights.py` | Evidence-backed research note | Generate or refresh review |
| Strategy Profile | `src/tradelens/ui/pages/5_Strategy.py` | Personal trading playbook | Save profile |
| Settings | `src/tradelens/ui/pages/9_Settings.py` | Quiet utility destination | Save setting |

The New Trade workflow remains a prominent action rather than a sixth equal destination. Desktop navigation keeps a persistent **Log completed trade** button. Mobile navigation uses Home, Log, Journal, Review, and More.

## Planned File Map

### New files

- `src/tradelens/ui/components/workspace.py`
- `src/tradelens/ui/components/trade_wizard.py`
- `tests/test_workspace_components.py`
- `tests/test_trade_wizard.py`
- `tests/test_premium_shell.py`
- `tests/test_premium_page_contracts.py`
- `scripts/capture_app_screenshots.py`

### Existing files to modify

- `.streamlit/config.toml`
- `src/tradelens/ui/design_system.py`
- `src/tradelens/ui/components/theme.py`
- `src/tradelens/ui/components/sidebar.py`
- `src/tradelens/ui/components/ui.py`
- `src/tradelens/ui/components/charts.py`
- `src/tradelens/ui/components/data_state.py`
- `src/tradelens/ui/components/ai_review.py`
- `src/tradelens/ui/components/trade_calendar.py`
- `src/tradelens/ui/app.py`
- `src/tradelens/ui/pages/1_NewTrade.py`
- `src/tradelens/ui/pages/2_Trades.py`
- `src/tradelens/ui/pages/4_Analytics.py`
- `src/tradelens/ui/pages/5_Strategy.py`
- `src/tradelens/ui/pages/6_Insights.py`
- `src/tradelens/ui/pages/9_Settings.py`
- `tests/test_design_system.py`
- `tests/test_theme.py`
- `tests/test_dashboard.py`
- `tests/test_page_polish.py`
- `tests/test_pages_boot.py`
- `tests/test_insights_page.py`
- `tests/test_charts.py`
- `site/assets/shot-dashboard-wide.webp`
- `site/assets/shot-newtrade.webp`
- `site/assets/shot-analytics.webp`
- `site/assets/shot-strategy.webp`

---

## Task 1: Lock the Hybrid Design System and Shared Workspace Primitives

**Files**

- Create: `src/tradelens/ui/components/workspace.py`
- Create: `tests/test_workspace_components.py`
- Modify: `.streamlit/config.toml`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `src/tradelens/ui/components/theme.py`
- Modify: `src/tradelens/ui/components/ui.py`
- Modify: `tests/test_design_system.py`
- Modify: `tests/test_theme.py`

**Interfaces**

```python
# src/tradelens/ui/components/workspace.py
from dataclasses import dataclass
from typing import Literal, Sequence

MetricTone = Literal["neutral", "positive", "negative", "warning"]
ConfidenceLevel = Literal["low", "medium", "high"]

@dataclass(frozen=True)
class MetricItem:
    label: str
    value: str
    detail: str | None = None
    tone: MetricTone = "neutral"

@dataclass(frozen=True)
class EvidenceItem:
    evidence: str
    sample: str
    confidence: ConfidenceLevel
    limitation: str | None = None

@dataclass(frozen=True)
class ResearchFinding:
    number: int
    title: str
    body: str
    evidence: EvidenceItem

def render_workspace_header(
    title: str,
    subtitle: str,
    eyebrow: str | None = None,
    meta: str | None = None,
) -> str: ...

def render_kpi_strip(items: Sequence[MetricItem]) -> str: ...
def render_evidence_rail(item: EvidenceItem) -> str: ...
def render_research_finding(item: ResearchFinding) -> str: ...
def render_editorial_readout(title: str, body: str, evidence: EvidenceItem) -> str: ...
def render_filter_summary(items: Sequence[tuple[str, str]]) -> str: ...
```

- [ ] Add failing tests for the new fixed palette and role-based tokens.

```python
def test_hybrid_palette_uses_light_workspace_and_dark_rail() -> None:
    from src.tradelens.ui import design_system as ds

    assert ds.TL_CANVAS == "#F3F6F6"
    assert ds.TL_PAPER == "#FFFFFF"
    assert ds.TL_RAIL == "#0F171B"
    assert ds.TL_CHART_STAGE == "#101A1E"
    assert ds.TL_ACTION == "#087F74"
    assert ds.TL_FOCUS == "#00E5CC"
```

- [ ] Add failing tests that every shared renderer escapes user-controlled text, produces one root element, and exposes the expected semantic class names.

```python
def test_evidence_rail_escapes_copy_and_exposes_semantic_fields() -> None:
    item = EvidenceItem(
        evidence="<b>21 trades</b>",
        sample="n=21",
        confidence="medium",
        limitation="Directional only",
    )
    html = render_evidence_rail(item)
    assert "<b>21 trades</b>" not in html
    assert "&lt;b&gt;21 trades&lt;/b&gt;" in html
    assert 'class="tl-evidence-rail"' in html
    assert "Evidence" in html
    assert "Sample" in html
    assert "Confidence" in html
    assert "Limitation" in html
```

- [ ] Run the focused tests and confirm they fail for the expected missing tokens and module.

Run:

```bash
pytest tests/test_design_system.py tests/test_theme.py tests/test_workspace_components.py -q
```

Expected: failures reference the new token names and missing `workspace.py`.

- [ ] Change `.streamlit/config.toml` from a dark base to a light base while keeping the same server, browser, and client behavior.

```toml
[theme]
base = "light"
primaryColor = "#087F74"
backgroundColor = "#F3F6F6"
secondaryBackgroundColor = "#FFFFFF"
textColor = "#132125"
font = "sans serif"
```

- [ ] Replace color literals in `design_system.py` with role-based tokens. Keep backward-compatible aliases for imports that are still used during migration.

```python
TL_CANVAS = "#F3F6F6"
TL_PAPER = "#FFFFFF"
TL_MIST = "#E9EFEF"
TL_INK = "#132125"
TL_MUTED = "#5B6A70"
TL_RAIL = "#0F171B"
TL_CHART_STAGE = "#101A1E"
TL_FOCUS = "#00E5CC"
TL_ACTION = "#087F74"
TL_SUCCESS = "#167A47"
TL_DANGER = "#B53A43"
TL_WARNING = "#A76500"
TL_BORDER = "#D9E2E2"
```

- [ ] Add typography variables for Schibsted, Satoshi, and JetBrains Mono. Use existing local assets if present; otherwise use a system fallback stack without introducing a dependency.

```css
:root {
  --tl-font-display: "Schibsted Grotesk", "Avenir Next", Inter, sans-serif;
  --tl-font-ui: Satoshi, Inter, -apple-system, BlinkMacSystemFont, sans-serif;
  --tl-font-mono: "JetBrains Mono", "SFMono-Regular", Consolas, monospace;
}
```

- [ ] Implement the pure renderers in `workspace.py`. Use `html.escape` on every text field. Keep all data formatting outside the renderer.
- [ ] Add CSS for the light canvas, white editorial sheets, dark chart stages, compact KPI strip, Evidence Rail, research finding, filter summary, focus rings, and legible table density.
- [ ] Re-export compatible theme tokens through `components/theme.py` so current chart imports keep working during migration.
- [ ] Make `components/ui.py` delegate shared header and evidence display to `workspace.py` instead of duplicating markup.
- [ ] Add a contrast contract test that checks each critical foreground/background pair against WCAG AA for normal text.
- [ ] Run focused tests until green.

Run:

```bash
pytest tests/test_design_system.py tests/test_theme.py tests/test_workspace_components.py -q
ruff check src/tradelens/ui/design_system.py src/tradelens/ui/components/workspace.py src/tradelens/ui/components/theme.py src/tradelens/ui/components/ui.py
```

Expected: all focused tests pass and Ruff reports no violations.

- [ ] UI/UX Pro Max review: verify hierarchy, contrast, focus visibility, readable line lengths, semantic status color, and dense-data legibility.
- [ ] Frontend Design review: verify the system has one recognizable signature—the Evidence Rail—and no generic glass-card treatment.
- [ ] Impeccable operate pass: remove redundant borders, excessive rounding, decorative gradients, and duplicated spacing declarations.
- [ ] Emil review: no motion is added in this task beyond defining approved timing and easing tokens.
- [ ] Commit the design-system foundation.

```bash
git add .streamlit/config.toml src/tradelens/ui/design_system.py src/tradelens/ui/components/theme.py src/tradelens/ui/components/ui.py src/tradelens/ui/components/workspace.py tests/test_design_system.py tests/test_theme.py tests/test_workspace_components.py
git commit -m "feat(ui): establish premium hybrid workspace system"
```

---

## Task 2: Rebuild the App Shell and Navigation Hierarchy

**Files**

- Create: `tests/test_premium_shell.py`
- Modify: `src/tradelens/ui/components/sidebar.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/test_page_polish.py`
- Modify: `tests/test_pages_boot.py`

**Interfaces**

```python
# src/tradelens/ui/components/sidebar.py
PRIMARY_NAV = (
    ("app.py", "/", "Overview", ":material/space_dashboard:"),
    ("pages/2_Trades.py", "/Trades", "Journal", ":material/menu_book:"),
    ("pages/4_Analytics.py", "/Analytics", "Analytics", ":material/analytics:"),
    ("pages/6_Insights.py", "/Insights", "AI Reviews", ":material/psychology:"),
    ("pages/5_Strategy.py", "/Strategy", "Strategy Profile", ":material/flag:"),
)

def render_primary_action(st) -> None: ...
def render_mobile_navigation(st, active_path: str) -> None: ...
def render_sidebar(df=None, today=None) -> None: ...
```

- [ ] Add failing source-contract tests for exactly five primary destinations, the renamed labels, the persistent New Trade action, and Settings outside the primary group.
- [ ] Add a failing AppTest assertion that every registered page boots with the custom shell and does not show Streamlit's default page navigation.
- [ ] Run the focused tests and confirm the expected failures.

Run:

```bash
pytest tests/test_premium_shell.py tests/test_page_polish.py tests/test_pages_boot.py -q
```

- [ ] Split the current `_NAV` into `PRIMARY_NAV`, the persistent action, and utility navigation.
- [ ] Rename Dashboard to Overview and Insights & Review to AI Reviews without renaming page files or URL slugs.
- [ ] Render a high-priority **Log completed trade** action immediately under the brand block.
- [ ] Move Settings below a utility divider with user identity and sign-out.
- [ ] Add a compact active-strategy context block that shows the profile name without competing with navigation.
- [ ] Add responsive CSS for a desktop dark rail, a collapsed tablet rail, and a five-item mobile bottom bar.
- [ ] Hide the desktop sidebar only at the existing mobile breakpoint. Keep the primary action reachable with one tap.
- [ ] Ensure all active, hover, focus, and disabled states have distinct non-color cues.
- [ ] Preserve `_nav_link`'s registry-less AppTest fallback.
- [ ] Run focused shell tests until green.

Run:

```bash
pytest tests/test_premium_shell.py tests/test_page_polish.py tests/test_pages_boot.py -q
ruff check src/tradelens/ui/components/sidebar.py
```

- [ ] UI/UX Pro Max review: verify five-item information architecture, mobile reachability, active-state clarity, and one-tap access to Log.
- [ ] Frontend Design review: verify the dark rail feels architectural rather than decorative and the workspace begins on a clean light plane.
- [ ] Impeccable operate pass: remove oversized controls, visual competition between profile context and navigation, and redundant separators.
- [ ] Emil motion pass: add a 160–220 ms active indicator and button press response using transform/opacity only, with hover gated to hover-capable devices and reduced-motion fallback.
- [ ] Commit the shell.

```bash
git add src/tradelens/ui/components/sidebar.py src/tradelens/ui/design_system.py tests/test_premium_shell.py tests/test_page_polish.py tests/test_pages_boot.py
git commit -m "feat(ui): reorganize premium product navigation"
```

---

## Task 3: Compose Overview as a Balanced Command Center

**Files**

- Modify: `src/tradelens/ui/app.py`
- Modify: `src/tradelens/ui/components/trade_calendar.py`
- Modify: `src/tradelens/ui/components/data_state.py`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_pages_boot.py`

**Interfaces**

```python
# src/tradelens/ui/app.py
def _overview_metrics(df: pd.DataFrame) -> list[MetricItem]: ...
def _render_today_brief(df: pd.DataFrame, activation: dict[str, object]) -> None: ...
def _render_recent_trades(recent: pd.DataFrame) -> None: ...

# src/tradelens/ui/components/trade_calendar.py
def render_trade_calendar(
    df: pd.DataFrame,
    *,
    compact: bool = False,
    selected_date: datetime.date | None = None,
) -> datetime.date | None: ...
```

- [ ] Add failing tests for the new header copy, compact KPI strip, Today Brief, Calendar, Equity, Recent Trades, and the persistent action.
- [ ] Add a failing test that Overview contains no six-card hero wrapper and no full-row success or danger tint.
- [ ] Add empty, sparse, and rich-data AppTest coverage for the page.
- [ ] Run the focused tests and confirm the expected structural failures.

Run:

```bash
pytest tests/test_dashboard.py tests/test_pages_boot.py -q
```

- [ ] Replace the current hero background and six separate KPI cards with one ruled KPI strip containing net P&L, win rate, expectancy, profit factor, and sample size.
- [ ] Use a two-column composition: a compact Today Brief and calendar on the left, dominant dark equity chart on the right.
- [ ] Move recent trades beneath the primary panel as a quiet ledger with restrained status badges and right-aligned monetary columns.
- [ ] Add one editorial observation below the chart using `render_editorial_readout`, grounded in existing metrics only.
- [ ] Keep asset filtering visible but compact. Render the active filter as a summary rather than another large control group.
- [ ] Preserve the current activation next step, demo banner, empty-state actions, and sample-data behavior.
- [ ] Update the calendar renderer for a compact overview mode without changing the full Analytics calendar.
- [ ] Keep chart calculations unchanged; only alter placement, styling, annotations, and data-state presentation.
- [ ] Run the focused tests until green.

Run:

```bash
pytest tests/test_dashboard.py tests/test_pages_boot.py tests/test_charts.py tests/test_data_state.py -q
ruff check src/tradelens/ui/app.py src/tradelens/ui/components/trade_calendar.py src/tradelens/ui/components/data_state.py
```

- [ ] UI/UX Pro Max review: verify glanceability in under ten seconds, primary action prominence, correct reading order, and sparse-data guidance.
- [ ] Frontend Design review: verify the command-center composition feels authored, not like a collection of equally weighted cards.
- [ ] Impeccable operate pass: reduce dashboard chrome, align baselines, normalize spacing, and remove duplicate labels that repeat chart titles.
- [ ] Emil motion pass: allow one subtle chart-stage reveal and one press interaction; do not animate KPI values or calendar navigation.
- [ ] Commit Overview.

```bash
git add src/tradelens/ui/app.py src/tradelens/ui/components/trade_calendar.py src/tradelens/ui/components/data_state.py tests/test_dashboard.py tests/test_pages_boot.py
git commit -m "feat(ui): compose premium overview command center"
```

---

## Task 4: Convert New Trade into a Real Five-Step Guided Wizard

**Files**

- Create: `src/tradelens/ui/components/trade_wizard.py`
- Create: `tests/test_trade_wizard.py`
- Modify: `src/tradelens/ui/pages/1_NewTrade.py`
- Modify: `src/tradelens/ui/components/ai_review.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/test_page_polish.py`
- Modify: `tests/test_pages_boot.py`

**Interfaces**

```python
# src/tradelens/ui/components/trade_wizard.py
from collections.abc import Mapping, MutableMapping, Sequence

WIZARD_STEPS = ("Screenshot", "Context", "Execution", "Reflection", "Review")
WIZARD_STATE_KEY = "new_trade_step"

def current_step(state: Mapping[str, object]) -> int: ...
def set_step(state: MutableMapping[str, object], step: int) -> None: ...
def previous_step(state: MutableMapping[str, object]) -> None: ...
def next_step(state: MutableMapping[str, object]) -> None: ...
def step_progress(step: int) -> float: ...
def required_fields_for_step(step: int) -> tuple[str, ...]: ...
def missing_required_fields(step: int, values: Mapping[str, object]) -> list[str]: ...
def draft_completion(values: Mapping[str, object]) -> tuple[int, int]: ...
```

- [ ] Add failing pure tests for step clamping, back/continue behavior, per-step requirements, draft completion, and session-state persistence.
- [ ] Replace the existing source-contract expectation for one `st.tabs` call with a failing contract that requires a session-controlled wizard and forbids rendering all five panels at once.
- [ ] Add AppTest coverage for step one, step validation, returning to a previous step, and final review with optional fields blank.
- [ ] Run the focused tests and confirm the expected failures.

Run:

```bash
pytest tests/test_trade_wizard.py tests/test_page_polish.py tests/test_pages_boot.py -q
```

- [ ] Extract step state and validation into `trade_wizard.py`, keeping it pure and independently testable.
- [ ] Refactor widget values to use stable `st.session_state` keys so only the current step is rendered without losing prior inputs.
- [ ] Recompose the workflow as:
  1. Screenshot: upload or direct URL, AI review state, provenance, and user confirmation.
  2. Context: date, time, asset, timeframe, session, higher- and lower-timeframe bias.
  3. Execution: setup, confirmation evidence, direction, result, P&L, risk, R multiple, and rule adherence.
  4. Reflection: concise structured prompts, emotion, strengths, improvement, and mistake tags.
  5. Review: one editable summary, missing-field notice, AI provenance, and final save action.
- [ ] Replace the tab rail with one progress indicator that announces the current step and completion state.
- [ ] Add a sticky lower action bar with Back, Save draft state, and Continue or Save. Do not block completion for optional reflection fields.
- [ ] Keep `_build_trade_data`, `_validate`, `_soft_warnings`, `_persist`, `_do_save`, and current service calls behaviorally equivalent. Change their inputs only as needed to read stable state.
- [ ] Preserve screenshot AI behavior: show what AI suggested, what the user confirmed or changed, and never apply a suggestion without explicit confirmation.
- [ ] Reduce the Reflection step from four visually equal large text areas to guided prompts with progressive disclosure for longer notes.
- [ ] Keep error messages inline next to the relevant step and render a short summary in the sticky action bar.
- [ ] Add a safe reset after a successful save that clears only wizard-owned keys.
- [ ] Run the focused and adjacent tests until green.

Run:

```bash
pytest tests/test_trade_wizard.py tests/test_page_polish.py tests/test_pages_boot.py tests/test_trade_service.py -q
ruff check src/tradelens/ui/components/trade_wizard.py src/tradelens/ui/components/ai_review.py src/tradelens/ui/pages/1_NewTrade.py
```

Expected: the wizard advances and reverses without losing data; save behavior and service calls match current behavior.

- [ ] UI/UX Pro Max review: verify progressive disclosure, cognitive load, keyboard flow, inline errors, optional-field clarity, and mobile action reachability.
- [ ] Frontend Design review: verify the form reads as one premium workflow with deliberate whitespace, not a long settings form.
- [ ] Impeccable operate pass: shorten repetitive helper copy, standardize labels, remove redundant boxes, and align the five steps to one visual grammar.
- [ ] Emil motion pass: animate only step content enter/exit and progress movement in 180–240 ms; disable under reduced motion; never animate focus or validation text.
- [ ] Commit the wizard.

```bash
git add src/tradelens/ui/components/trade_wizard.py src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/components/ai_review.py src/tradelens/ui/design_system.py tests/test_trade_wizard.py tests/test_page_polish.py tests/test_pages_boot.py
git commit -m "feat(ui): guide completed trades through five-step wizard"
```

---

## Task 5: Recompose Journal as a Quiet Ledger, Calendar, and Trade Detail

**Files**

- Modify: `src/tradelens/ui/pages/2_Trades.py`
- Modify: `src/tradelens/ui/components/trade_calendar.py`
- Modify: `src/tradelens/ui/components/data_state.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/test_page_polish.py`
- Modify: `tests/test_pages_boot.py`
- Modify: `tests/test_premium_page_contracts.py`

**Interfaces**

```python
# src/tradelens/ui/pages/2_Trades.py
JOURNAL_VIEWS = ("Trades", "Calendar", "Trade Detail")

def _active_filters(
    *,
    date_from: object,
    date_to: object,
    asset: object,
    session: object,
    result: object,
    setup: object,
) -> list[tuple[str, str]]: ...

def _trade_ledger_html(df: pd.DataFrame, selected_id: int | None) -> str: ...
def _render_trade_detail(row: pd.Series) -> None: ...
```

- [ ] Add failing source-contract tests for the three Journal views, compact filter summary, restrained ledger statuses, and dedicated Trade Detail view.
- [ ] Add a failing assertion that full-row gain/loss background fills are removed.
- [ ] Add AppTest cases for filtering, no results, selecting a trade, and calendar day detail.
- [ ] Run the focused tests and confirm the expected failures.

Run:

```bash
pytest tests/test_premium_page_contracts.py tests/test_page_polish.py tests/test_pages_boot.py -q
```

- [ ] Add a three-view Journal selector while preserving current filter controls and selected-trade behavior.
- [ ] Put the filter controls in a compact horizontal filter bar. Collapse secondary filters behind More filters on narrow layouts.
- [ ] Render active filters in `render_filter_summary` and show the result count adjacent to the view selector.
- [ ] Replace full-row red and green tints with neutral rows, a narrow semantic edge, status badge, and colored monetary text.
- [ ] Keep columns scannable: date, asset, session, setup, result, P&L, R, grade, and screenshot marker.
- [ ] Move expanded record content into Trade Detail. Use a two-column summary with screenshot, structured facts, process review, and AI provenance.
- [ ] Keep Calendar as a full monthly view with click-through to Trade Detail.
- [ ] Preserve current AI summary generation, download, filter, correction, and selection workflows.
- [ ] Move long generated summary content out of the table area and render it as a research note using the shared evidence treatment.
- [ ] Run focused and adjacent tests until green.

Run:

```bash
pytest tests/test_premium_page_contracts.py tests/test_page_polish.py tests/test_pages_boot.py tests/test_data_state.py -q
ruff check src/tradelens/ui/pages/2_Trades.py src/tradelens/ui/components/trade_calendar.py
```

- [ ] UI/UX Pro Max review: verify ledger scan speed, filter discoverability, selected-row clarity, calendar accessibility, and mobile table fallback.
- [ ] Frontend Design review: verify the page feels like a refined journal ledger, not a data-grid administration screen.
- [ ] Impeccable operate pass: simplify filters, normalize cell density, remove background noise, and reduce duplicate metadata in detail.
- [ ] Emil motion pass: use a short detail-panel reveal and selected-row transition only; do not animate sorting, filtering, or table rows.
- [ ] Commit Journal.

```bash
git add src/tradelens/ui/pages/2_Trades.py src/tradelens/ui/components/trade_calendar.py src/tradelens/ui/components/data_state.py src/tradelens/ui/design_system.py tests/test_page_polish.py tests/test_pages_boot.py tests/test_premium_page_contracts.py
git commit -m "feat(ui): organize journal as premium trading ledger"
```

---

## Task 6: Rebuild Analytics as One Composed Instrument Panel

**Files**

- Modify: `src/tradelens/ui/pages/4_Analytics.py`
- Modify: `src/tradelens/ui/components/charts.py`
- Modify: `src/tradelens/ui/components/data_state.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/test_charts.py`
- Modify: `tests/test_pages_boot.py`
- Modify: `tests/test_premium_page_contracts.py`

**Interfaces**

```python
# src/tradelens/ui/pages/4_Analytics.py
ANALYTICS_LENSES = ("Performance", "Risk", "Timing", "Setups")

def _render_performance_lens(df: pd.DataFrame) -> None: ...
def _render_risk_lens(df: pd.DataFrame) -> None: ...
def _render_timing_lens(df: pd.DataFrame) -> None: ...
def _render_setups_lens(df: pd.DataFrame) -> None: ...

# src/tradelens/ui/components/charts.py
def apply_chart_stage(fig, *, title: str | None = None, compact: bool = False): ...
def add_sample_annotation(fig, *, sample_size: int, minimum: int): ...
```

- [ ] Add failing tests for exactly four analytics lenses and one visible lens body at a time.
- [ ] Add failing source-contract tests for the composed order: ruled KPI strip, dominant chart, ranked evidence, and editorial readout.
- [ ] Add chart tests for the dark chart stage, accessible semantic colors, visible hover labels, and sample annotations.
- [ ] Add AppTest cases for empty, sparse, and rich datasets in each lens.
- [ ] Run the focused tests and confirm the expected failures.

Run:

```bash
pytest tests/test_charts.py tests/test_premium_page_contracts.py tests/test_pages_boot.py -q
```

- [ ] Replace the long sequential analytics page with four lenses: Performance, Risk, Timing, and Setups.
- [ ] Make Performance the default and compose it as one panel:
  - compact ruled metric strip;
  - dominant dark equity chart;
  - drawdown or distribution evidence;
  - ranked setup/session evidence table;
  - one editorial interpretation with sample and limitation.
- [ ] Compose Risk around average and median R, drawdown, risk consistency, and loss concentration. Remove the large near-empty risk chart when data has only one distinct value; show a compact evidence state instead.
- [ ] Compose Timing around session, day of week, and session-by-day heatmap. Keep color meaning consistent and provide a table equivalent beneath charts.
- [ ] Compose Setups around ranked setup performance, sample size, win rate, average P&L, and profit factor.
- [ ] Add `apply_chart_stage` and use it across all Plotly figures so grid, typography, margins, hover treatment, and backgrounds are consistent.
- [ ] Remove giant one-off metric cards such as Best Session and Worst Session. Put them in the ruled metric strip with non-truncated values.
- [ ] Keep all existing service calculations and chart source data unchanged.
- [ ] Add sample-size annotations and limitations at the panel level, not repeated inside every chart.
- [ ] Run focused and adjacent tests until green.

Run:

```bash
pytest tests/test_charts.py tests/test_premium_page_contracts.py tests/test_pages_boot.py tests/test_data_state.py tests/test_metrics.py -q
ruff check src/tradelens/ui/pages/4_Analytics.py src/tradelens/ui/components/charts.py
```

- [ ] UI/UX Pro Max review: verify chart comprehension, accessible color, table alternatives, filter persistence, sample-size communication, and responsive stacking.
- [ ] Frontend Design review: verify Analytics reads as one composed instrument panel rather than a reusable card grid.
- [ ] Impeccable operate pass: remove dead chart space, fix clipped values, unify axes and captions, reduce repeated titles, and make the editorial readout concise.
- [ ] Emil motion pass: use Plotly's restrained initial reveal only where it aids orientation; no perpetual animation and no animation on filter changes that hides the new state.
- [ ] Commit Analytics.

```bash
git add src/tradelens/ui/pages/4_Analytics.py src/tradelens/ui/components/charts.py src/tradelens/ui/components/data_state.py src/tradelens/ui/design_system.py tests/test_charts.py tests/test_pages_boot.py tests/test_premium_page_contracts.py
git commit -m "feat(ui): compose analytics instrument panel"
```

---

## Task 7: Turn AI Reviews into Concise Evidence-Backed Research Notes

**Files**

- Modify: `src/tradelens/ui/pages/6_Insights.py`
- Modify: `src/tradelens/ui/components/ai_review.py`
- Modify: `src/tradelens/ui/components/workspace.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/test_insights_page.py`
- Modify: `tests/test_pages_boot.py`
- Modify: `tests/test_workspace_components.py`
- Modify: `tests/test_premium_page_contracts.py`

**Interfaces**

```python
# src/tradelens/ui/components/ai_review.py
from dataclasses import dataclass
from typing import Sequence

@dataclass(frozen=True)
class ResearchNote:
    title: str
    thesis: str
    findings: Sequence[ResearchFinding]
    actions: Sequence[str]
    evidence_used: Sequence[str]
    sample: str
    limitation: str
    generated_at: str | None = None

def render_research_note(note: ResearchNote) -> str: ...
def render_note_skeleton() -> str: ...
```

- [ ] Add failing renderer tests for a research note with thesis, numbered findings, one Evidence Rail per finding, actions, sample, limitation, and collapsed evidence.
- [ ] Add failing page-contract tests for Patterns, Weekly Recap, and Daily Debrief as the only three AI Review lenses.
- [ ] Add a failing assertion that the page does not render the current two-column reusable insight-card grid.
- [ ] Preserve and extend tests that ensure generated output exposes no internal reasoning, prompt content, token count, or provider cost.
- [ ] Add AppTest cases for no data, insufficient sample, cached output, generating output, and regeneration.
- [ ] Run the focused tests and confirm the expected failures.

Run:

```bash
pytest tests/test_insights_page.py tests/test_workspace_components.py tests/test_premium_page_contracts.py tests/test_pages_boot.py -q
```

- [ ] Recompose the page into three lenses: Patterns, Weekly Recap, and Daily Debrief.
- [ ] Render Patterns as a compact research note:
  - one plain-language thesis;
  - three to five numbered findings;
  - evidence, sample, confidence, and limitation attached through the Evidence Rail;
  - two or three prioritized next actions;
  - evidence-used details collapsed by default.
- [ ] Render Weekly Recap with one summary line, what worked, what needs attention, observed patterns, and next-week focus. Collapse extended prose and raw evidence.
- [ ] Render Daily Debrief as a shorter note optimized for one completed day, with direct links back to the relevant Journal detail.
- [ ] Convert current structured results into `ResearchNote` presentation objects without changing service payloads, prompts, caching, or generation behavior.
- [ ] Use a dark focused reading surface only for the note body; keep filters and controls on the light workspace.
- [ ] Replace repeated red/green insight cards with numbered editorial findings and semantic edge markers.
- [ ] Add a stable loading skeleton that preserves note geometry while generation is in progress.
- [ ] Keep confidence and sample size explicit, but say them once per finding instead of repeating a footer on every card.
- [ ] Run focused and adjacent tests until green.

Run:

```bash
pytest tests/test_insights_page.py tests/test_workspace_components.py tests/test_premium_page_contracts.py tests/test_pages_boot.py tests/test_patterns.py tests/test_weekly.py -q
ruff check src/tradelens/ui/pages/6_Insights.py src/tradelens/ui/components/ai_review.py src/tradelens/ui/components/workspace.py
```

- [ ] UI/UX Pro Max review: verify the hierarchy between thesis, findings, evidence, and actions; ensure limitations are visible and the note is readable at mobile width.
- [ ] Frontend Design review: verify AI Reviews feel like an authored research note, not an AI-chat transcript or reusable card grid.
- [ ] Impeccable operate pass: edit generated-content wrappers for concise line length, remove repeated disclaimers, reduce heavy boxes, and keep evidence scannable.
- [ ] Emil motion pass: use a brief skeleton-to-note crossfade and accordion disclosure only; no typing animation, bouncing indicators, or motion on long prose.
- [ ] Commit AI Reviews.

```bash
git add src/tradelens/ui/pages/6_Insights.py src/tradelens/ui/components/ai_review.py src/tradelens/ui/components/workspace.py src/tradelens/ui/design_system.py tests/test_insights_page.py tests/test_pages_boot.py tests/test_workspace_components.py tests/test_premium_page_contracts.py
git commit -m "feat(ui): present AI reviews as research notes"
```

---

## Task 8: Refine Strategy Profile into a Personal Playbook

**Files**

- Modify: `src/tradelens/ui/pages/5_Strategy.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/test_page_polish.py`
- Modify: `tests/test_pages_boot.py`
- Modify: `tests/test_premium_page_contracts.py`

**Interfaces**

```python
# src/tradelens/ui/pages/5_Strategy.py
PLAYBOOK_SECTIONS = (
    "Identity",
    "Entry Rules",
    "Exit Rules",
    "Risk Rules",
    "Setups",
    "Self-Awareness",
)

def _profile_completion(profile: dict[str, object]) -> tuple[int, int]: ...
def _render_profile_summary(profile: dict[str, object]) -> None: ...
```

- [ ] Add failing tests for the six playbook sections, profile completion, active-profile context, and a single clear save action.
- [ ] Add AppTest coverage for empty profile, starter template, validation, and existing-profile save.
- [ ] Run focused tests and confirm the expected failures.

Run:

```bash
pytest tests/test_premium_page_contracts.py tests/test_page_polish.py tests/test_pages_boot.py -q
```

- [ ] Replace the oversized banner and long wall of expanders with a compact profile summary and progressive sections.
- [ ] Keep Identity open by default. Keep rule and setup sections collapsed until needed.
- [ ] Add profile completion and a concise explanation that this playbook grounds reviews and grading.
- [ ] Preserve the starter template, active profile, all existing fields, validation, service calls, and save behavior.
- [ ] Render assets, timeframes, and setups as compact chips only when they improve scan speed.
- [ ] Keep the save action anchored at the end of the active form, not stretched across the entire viewport.
- [ ] Run focused and adjacent tests until green.

Run:

```bash
pytest tests/test_premium_page_contracts.py tests/test_page_polish.py tests/test_pages_boot.py tests/test_strategy.py -q
ruff check src/tradelens/ui/pages/5_Strategy.py
```

- [ ] UI/UX Pro Max review: verify progressive disclosure, edit confidence, completion feedback, and mobile form ordering.
- [ ] Frontend Design review: verify the page feels like a personal playbook, not a settings dump.
- [ ] Impeccable operate pass: remove banner noise, reduce nested containers, standardize section descriptions, and tighten chip usage.
- [ ] Emil motion pass: use accordion expansion only; keep save feedback immediate and motion-free for keyboard users.
- [ ] Commit Strategy Profile.

```bash
git add src/tradelens/ui/pages/5_Strategy.py src/tradelens/ui/design_system.py tests/test_page_polish.py tests/test_pages_boot.py tests/test_premium_page_contracts.py
git commit -m "feat(ui): refine strategy profile into playbook"
```

---

## Task 9: Make Settings Quiet, Safe, and Clearly Secondary

**Files**

- Modify: `src/tradelens/ui/pages/9_Settings.py`
- Modify: `src/tradelens/ui/design_system.py`
- Modify: `tests/test_page_polish.py`
- Modify: `tests/test_pages_boot.py`
- Modify: `tests/test_premium_page_contracts.py`

**Interfaces**

```python
# src/tradelens/ui/pages/9_Settings.py
SETTINGS_SECTIONS = ("Profile", "Preferences", "Data", "Danger Zone")

def _render_setting_status(saved: bool, message: str) -> None: ...
```

- [ ] Add failing tests for four quiet sections, destructive-action separation, explicit confirmation, and no oversized primary button.
- [ ] Add AppTest coverage for preference save, sample-data action, export, and destructive confirmation.
- [ ] Run focused tests and confirm the expected failures.

Run:

```bash
pytest tests/test_premium_page_contracts.py tests/test_page_polish.py tests/test_pages_boot.py -q
```

- [ ] Recompose existing settings into Profile, Preferences, Data, and Danger Zone without changing available actions.
- [ ] Keep routine settings on white paper with compact labels and inline save status.
- [ ] Put exports and sample-data tools in Data with explanatory copy.
- [ ] Put destructive actions in a separate bordered section at the bottom with explicit confirmation and recovery implications.
- [ ] Keep Settings outside primary navigation and remove any promotional visual treatment.
- [ ] Run focused and adjacent tests until green.

Run:

```bash
pytest tests/test_premium_page_contracts.py tests/test_page_polish.py tests/test_pages_boot.py tests/test_app_settings.py tests/test_account_deletion.py -q
ruff check src/tradelens/ui/pages/9_Settings.py
```

- [ ] UI/UX Pro Max review: verify settings findability, save feedback, destructive safety, and keyboard order.
- [ ] Frontend Design review: verify Settings is intentionally quiet and does not visually compete with core product pages.
- [ ] Impeccable operate pass: remove repeated dividers, compress explanatory copy, and standardize field grouping.
- [ ] Emil motion pass: no decorative motion; allow only immediate confirmation disclosure and save-state feedback.
- [ ] Commit Settings.

```bash
git add src/tradelens/ui/pages/9_Settings.py src/tradelens/ui/design_system.py tests/test_page_polish.py tests/test_pages_boot.py tests/test_premium_page_contracts.py
git commit -m "feat(ui): simplify product settings"
```

---

## Task 10: Complete Responsive, Accessibility, and State Hardening

**Files**

- Modify: `src/tradelens/ui/design_system.py`
- Modify: `src/tradelens/ui/components/sidebar.py`
- Modify: `src/tradelens/ui/components/workspace.py`
- Modify: `src/tradelens/ui/components/data_state.py`
- Modify: `tests/test_design_system.py`
- Modify: `tests/test_premium_shell.py`
- Modify: `tests/test_premium_page_contracts.py`
- Modify: `tests/test_pages_boot.py`

**Interfaces**

```python
# tests/test_design_system.py
def contrast_ratio(foreground: str, background: str) -> float: ...
```

- [ ] Add failing contracts for desktop, tablet, and mobile breakpoints; minimum 44 px touch targets; visible focus; reduced motion; no horizontal page overflow; and table overflow containment.
- [ ] Add failing data-state tests for loading, empty, sparse, error, and rich states across Overview, Journal, Analytics, and AI Reviews.
- [ ] Add an AppTest matrix for unauthenticated, empty authenticated, demo, and seeded user states.
- [ ] Run the focused tests and confirm the expected failures.

Run:

```bash
pytest tests/test_design_system.py tests/test_premium_shell.py tests/test_premium_page_contracts.py tests/test_pages_boot.py -q
```

- [ ] Add responsive rules for:
  - 1440 px and above: full rail and two-column workspace;
  - 1024–1439 px: narrower rail and reduced gutters;
  - 768–1023 px: stacked panels with compact rail;
  - below 768 px: no desktop rail, mobile bottom navigation, single-column forms, scroll-contained tables.
- [ ] Ensure all interactive elements have visible keyboard focus and no hover-only meaning.
- [ ] Add reduced-motion CSS that disables non-essential transforms and transitions.
- [ ] Verify chart tooltips, legends, annotations, and table alternatives remain usable without relying on color alone.
- [ ] Keep text measure between roughly 55 and 75 characters for AI prose and editorial readouts.
- [ ] Ensure monetary values use monospaced numerals and do not truncate at common widths.
- [ ] Normalize loading, empty, sparse, and error states through `data_state.py`.
- [ ] Run the full UI test subset until green.

Run:

```bash
pytest tests/test_design_system.py tests/test_theme.py tests/test_workspace_components.py tests/test_premium_shell.py tests/test_premium_page_contracts.py tests/test_page_polish.py tests/test_dashboard.py tests/test_insights_page.py tests/test_charts.py tests/test_data_state.py tests/test_pages_boot.py -q
ruff check src/tradelens/ui
```

- [ ] UI/UX Pro Max review: complete the main product audit across accessibility, responsive behavior, empty states, consistency, and task completion.
- [ ] Frontend Design review: compare all pages together and correct any drift in typography, density, surface hierarchy, and Evidence Rail use.
- [ ] Impeccable operate pass: perform one cross-page consistency cleanup, including spacing rhythm, border weight, radius scale, icon scale, and copy length.
- [ ] Emil motion review: verify every animation is under 300 ms, uses approved properties, respects reduced motion, and is absent from keyboard navigation.
- [ ] Commit hardening.

```bash
git add src/tradelens/ui/design_system.py src/tradelens/ui/components/sidebar.py src/tradelens/ui/components/workspace.py src/tradelens/ui/components/data_state.py tests/test_design_system.py tests/test_premium_shell.py tests/test_premium_page_contracts.py tests/test_pages_boot.py
git commit -m "fix(ui): harden responsive and accessible product states"
```

---

## Task 11: Verify the Whole Product and Refresh Marketing App Screenshots

**Files**

- Create: `scripts/capture_app_screenshots.py`
- Modify: `site/assets/shot-dashboard-wide.webp`
- Modify: `site/assets/shot-newtrade.webp`
- Modify: `site/assets/shot-analytics.webp`
- Modify: `site/assets/shot-strategy.webp`
- Modify: `tests/test_page_polish.py`
- Modify: `tests/test_pages_boot.py`
- Modify: `README.md` only if local screenshot instructions need documenting

**Interfaces**

```python
# scripts/capture_app_screenshots.py
CAPTURES = (
    ("overview", "/", "site/assets/shot-dashboard-wide.webp"),
    ("new-trade", "/NewTrade", "site/assets/shot-newtrade.webp"),
    ("analytics", "/Analytics", "site/assets/shot-analytics.webp"),
    ("strategy", "/Strategy", "site/assets/shot-strategy.webp"),
)
```

- [ ] Add or update source-contract tests that confirm the marketing site still references the same four asset paths.
- [ ] Run the complete test suite before visual capture.

Run:

```bash
ruff check src/ scripts/
pytest tests/ -v --tb=short
pytest --cov=src/tradelens/services --cov-fail-under=80 -q
```

Expected: all checks pass with no service coverage regression.

- [ ] Start the local Streamlit app with demo data using the project's existing environment setup.

Run:

```bash
streamlit run src/tradelens/ui/app.py --server.headless true
```

- [ ] Capture Overview, New Trade, Analytics, AI Reviews, Journal, Strategy Profile, Settings, and mobile navigation at desktop, tablet, and mobile widths for review.
- [ ] Compare each capture against the approved specification:
  - fixed hybrid theme is consistent;
  - navigation hierarchy is correct;
  - Overview is balanced;
  - New Trade is guided and preserves state;
  - Journal is a quiet ledger;
  - Analytics is one composed panel;
  - AI Reviews read as research notes;
  - Strategy Profile reads as a playbook;
  - Settings remains secondary;
  - Evidence Rail is recognizable but not overused.
- [ ] Fix any verified visual or functional defect through the smallest responsible component, add a regression test, and rerun the relevant focused tests.
- [ ] Use `scripts/capture_app_screenshots.py` to create the four marketing-ready WebP files at the exact existing asset paths.
- [ ] Confirm the marketing HTML and CSS are unchanged and only the in-app screenshots differ.
- [ ] Reopen the marketing site locally and verify image dimensions, crops, loading, and alt text.
- [ ] Perform the final four-skill approval:
  - UI/UX Pro Max: main usability and accessibility sign-off;
  - Frontend Design: production visual and composition sign-off;
  - Impeccable: final cleanup and consistency sign-off;
  - Emil Design Eng: final motion and reduced-motion sign-off.
- [ ] Run final verification once more after screenshot replacement.

Run:

```bash
ruff check src/ scripts/
pytest tests/ -v --tb=short
git diff --check
git status --short
```

- [ ] Commit the completed redesign and refreshed screenshots. Do not push or deploy.

```bash
git add src/tradelens/ui .streamlit/config.toml scripts/capture_app_screenshots.py tests site/assets/shot-dashboard-wide.webp site/assets/shot-newtrade.webp site/assets/shot-analytics.webp site/assets/shot-strategy.webp
git commit -m "feat(ui): complete premium TradeLens product redesign"
```

---

## Acceptance Checklist

### Product shell

- [ ] Five primary destinations are present: Overview, Journal, Analytics, AI Reviews, and Strategy Profile.
- [ ] Log completed trade is a persistent high-priority action.
- [ ] Settings is present but visually secondary.
- [ ] Desktop, tablet, and mobile navigation preserve the same hierarchy.

### Visual system

- [ ] Workspace is light; sidebar, charts, and focused AI reading surfaces are dark.
- [ ] White paper surfaces, mist dividers, ink text, and deep-teal actions are consistent.
- [ ] Red is limited to errors, losses, and destructive actions.
- [ ] Typography, radius, spacing, border, and shadow scales are consistent.
- [ ] The Evidence Rail is the recognizable signature component.

### Core workflows

- [ ] Existing authentication, demo data, persistence, filters, exports, analytics, AI generation, weekly review, daily debrief, corrections, and strategy behavior still work.
- [ ] New Trade preserves draft values across five guided steps.
- [ ] AI screenshot suggestions remain explicitly user-confirmed.
- [ ] Journal supports ledger, calendar, and trade detail.
- [ ] Analytics supports Performance, Risk, Timing, and Setups.
- [ ] AI Reviews supports Patterns, Weekly Recap, and Daily Debrief.

### Editorial quality

- [ ] Overview is a composed command center, not a wall of cards.
- [ ] Analytics is one instrument panel per lens, not a reusable card grid.
- [ ] AI Reviews are concise research notes with thesis, findings, evidence, sample, confidence, limitation, and actions.
- [ ] Strategy Profile reads as a personal playbook.
- [ ] Settings is quiet and safe.

### Accessibility and motion

- [ ] Critical text meets WCAG AA contrast.
- [ ] Focus is visible and keyboard order is logical.
- [ ] Color is never the only status cue.
- [ ] Touch targets are at least 44 px.
- [ ] Tables and charts remain usable on small screens.
- [ ] Motion is purposeful, under 300 ms, transform/opacity based, and disabled or reduced when requested by the operating system.

### Release boundary

- [ ] All tests and Ruff pass.
- [ ] Marketing markup and copy are unchanged.
- [ ] Only the four existing marketing app screenshots are refreshed.
- [ ] No service, schema, dependency, broker, push, pull request, or deployment change is included.
