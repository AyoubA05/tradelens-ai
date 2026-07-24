# Product Trust and Premium UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make TradeLens analytics internally coherent, calm under sparse data, and presentation-ready for a premium beta without adding product complexity.

**Architecture:** Add a Streamlit-free outcome validator at the write boundary, make metrics use signed P&L as the canonical classification when it exists, and introduce one reusable low-data policy for dashboards and charts. UI changes simplify the New Trade stepper and replace developer-facing AI details with evidence/sample/confidence disclosures. No schema change is included; multi-user isolation is handled by the separate isolation plan.

**Tech Stack:** Python 3.11, Streamlit 1.50.0, SQLAlchemy, Pandas, Plotly 6.7.0, pytest, Streamlit AppTest.

## Global Constraints

- TradeLens reviews completed trades only and never provides in-session direction.
- No database schema changes in this plan.
- No new dependencies.
- `src/tradelens/ui/design_system.py` remains the only source of color, spacing, radius, and typography tokens.
- Red is reserved for errors and negative performance; teal represents primary/active states.
- P&L is canonical for outcome classification when it is present. Manual outcome is allowed only when P&L is absent.
- Existing contradictory rows must render coherently but are never silently rewritten by this plan.
- Charts require at least two meaningful points or categories. Comparative labels require at least two categories.
- AI review UI exposes evidence, sample size, and confidence; it does not expose internal generation cost or model-reasoning summaries in the standard user path.
- `services/metrics.py` is owned by `metrics-agent`; its task runs in its own worktree/session and not concurrently with another metrics edit.
- `services/weekly.py` runs in a dedicated weekly session and does not touch `services/ai_client.py`.
- Preserve unrelated dirty work and stage exact paths only.

---

## File structure

- `src/tradelens/services/trade_validation.py` - canonical outcome rules shared by create/edit/import paths.
- `src/tradelens/services/trade_service.py` - enforces validation at persistence boundaries.
- `src/tradelens/services/metrics.py` - canonical outcome masks and low-sample-safe metrics.
- `src/tradelens/ui/components/data_state.py` - pure sample-state decisions and reusable Streamlit rendering.
- `src/tradelens/ui/pages/1_NewTrade.py` - coherent entry flow with one progress system.
- `src/tradelens/ui/pages/2_Trades.py` - coherent edit flow and debug-detail removal.
- `src/tradelens/ui/pages/4_Analytics.py` - low-data presentation policy.
- `src/tradelens/ui/pages/6_Insights.py` - evidence/sample/confidence presentation.
- `src/tradelens/ui/design_system.py` - scoped stepper/data-state CSS using existing tokens.
- `tests/test_trade_validation.py` - validator contract.
- `tests/test_metrics.py` - contradictory-row and low-sample behavior.
- `tests/test_data_state.py` - rendering thresholds.
- `tests/test_page_polish.py` - simplified UI/source contracts.

---

### Task 1: Enforce coherent outcome data at every write boundary

**Files:**
- Create: `src/tradelens/services/trade_validation.py`
- Modify: `src/tradelens/services/trade_service.py:91-143,221-238`
- Modify: `src/tradelens/ui/pages/1_NewTrade.py:373-410,641-654`
- Modify: `src/tradelens/ui/pages/2_Trades.py:566-603`
- Create: `tests/test_trade_validation.py`
- Modify: `tests/test_trade_service.py`

**Interfaces:**
- Produces: `canonical_outcome(result: object, pnl: object) -> str | None`; raises `OutcomeMismatch` when both values are supplied and disagree.
- Consumers: create trade, edit trade, CSV import in a later bounded task.

- [x] **Step 1: Write failing validator tests**

Create `tests/test_trade_validation.py`:

```python
import pytest

from src.tradelens.services.trade_validation import OutcomeMismatch, canonical_outcome


@pytest.mark.parametrize(
    ("pnl", "expected"),
    [(250, "Win"), (-50, "Loss"), (0, "Breakeven"), ("125.25", "Win")],
)
def test_pnl_determines_outcome(pnl, expected):
    assert canonical_outcome(None, pnl) == expected


def test_manual_outcome_is_kept_when_pnl_is_missing():
    assert canonical_outcome("loss", None) == "Loss"


def test_conflicting_values_are_rejected():
    with pytest.raises(OutcomeMismatch, match="does not match"):
        canonical_outcome("Win", -500)


def test_unknown_manual_outcome_is_rejected():
    with pytest.raises(ValueError, match="Unknown outcome"):
        canonical_outcome("Great", None)
```

- [x] **Step 2: Run and verify failure**

Run: `.venv/bin/python -m pytest tests/test_trade_validation.py -q`  
Expected: FAIL with `ModuleNotFoundError`.

- [x] **Step 3: Implement the validator**

Create `src/tradelens/services/trade_validation.py`:

```python
from __future__ import annotations

from typing import Optional

VALID_OUTCOMES = {"win": "Win", "loss": "Loss", "breakeven": "Breakeven"}


class OutcomeMismatch(ValueError):
    pass


def _normalise_result(result: object) -> Optional[str]:
    if result is None or str(result).strip() == "":
        return None
    value = str(result).strip().lower()
    if value not in VALID_OUTCOMES:
        raise ValueError(f"Unknown outcome: {result!r}")
    return VALID_OUTCOMES[value]


def canonical_outcome(result: object, pnl: object) -> Optional[str]:
    normalised = _normalise_result(result)
    if pnl is None or str(pnl).strip() == "":
        return normalised
    value = float(pnl)
    expected = "Win" if value > 0 else "Loss" if value < 0 else "Breakeven"
    if normalised is not None and normalised != expected:
        raise OutcomeMismatch(
            f"Outcome {normalised!r} does not match P&L {value:,.2f}; expected {expected!r}."
        )
    return expected
```

- [x] **Step 4: Enforce in create and update**

In `create_trade()`, immediately after `data = dict(trade_data)`, add:

```python
from src.tradelens.services.trade_validation import canonical_outcome

data["result"] = canonical_outcome(data.get("result"), data.get("pnl"))
```

In `update_trade()`, after loading the row and before assigning fields, compute:

```python
candidate_result = updates.get("result", trade.result)
candidate_pnl = updates.get("pnl", trade.pnl)
if "result" in updates or "pnl" in updates:
    updates["result"] = canonical_outcome(candidate_result, candidate_pnl)
```

- [x] **Step 5: Make New Trade mismatch save-blocking**

Remove the warning block at lines 400-410. In `_validate(data)`, add:

```python
from src.tradelens.services.trade_validation import OutcomeMismatch, canonical_outcome

try:
    canonical_outcome(data.get("result"), data.get("pnl"))
except (OutcomeMismatch, ValueError) as exc:
    errors.append(str(exc))
```

Change the result label to `Result (derived from P&L when entered)` so the rule is visible before Review & Save.

- [x] **Step 6: Make Journal edits use the same error**

Wrap `update_trade(...)` in `try/except OutcomeMismatch` and render `st.error(str(exc))`; show success only when the service accepts the update.

- [x] **Step 7: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_trade_validation.py tests/test_trade_service.py -q
.venv/bin/ruff check src/tradelens/services/trade_validation.py src/tradelens/services/trade_service.py src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/pages/2_Trades.py
```

Expected: PASS and ruff clean.

- [x] **Step 8: Commit**

```bash
git add src/tradelens/services/trade_validation.py src/tradelens/services/trade_service.py src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/pages/2_Trades.py tests/test_trade_validation.py tests/test_trade_service.py
git commit -m "trades: prevent outcome and P&L contradictions"
```

### Task 2: Make metrics coherent for legacy contradictory rows

**Owner:** `metrics-agent` in a dedicated worktree.

**Files:**
- Modify: `src/tradelens/services/metrics.py:31-50`
- Modify: `tests/test_metrics.py`
- Modify: `tests/test_dashboard_metrics.py`

**Interfaces:**
- Produces: `_outcome_masks(df) -> tuple[pd.Series, pd.Series, pd.Series]`; non-null P&L wins per-row, text outcome is fallback only for rows without P&L.

- [x] **Step 1: Write contradictory-row tests**

```python
def test_pnl_sign_overrides_stale_result_for_metrics():
    df = pd.DataFrame(
        {"result": ["Win", "Loss", "Win"], "pnl": [-500.0, 250.0, None]}
    )
    m = compute_basic_metrics(df)
    assert m["wins"] == 2
    assert m["losses"] == 1
    assert m["win_rate"] == pytest.approx(2 / 3)
    assert m["avg_win"] == 250.0
    assert m["avg_loss"] == -500.0


def test_one_negative_trade_cannot_be_a_hundred_percent_win_rate():
    m = compute_basic_metrics(pd.DataFrame({"result": ["Win"], "pnl": [-500.0]}))
    assert m["win_rate"] == 0.0
    assert m["avg_win"] == 0.0
    assert m["avg_loss"] == -500.0
```

- [x] **Step 2: Run and verify failure**

Run: `.venv/bin/python -m pytest tests/test_metrics.py -q -k "stale_result or hundred_percent"`  
Expected: FAIL because text outcome currently wins.

- [x] **Step 3: Replace `_outcome_masks`**

```python
def _outcome_masks(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
    false = pd.Series(False, index=df.index)
    pnl = (
        pd.to_numeric(df["pnl"], errors="coerce")
        if "pnl" in df.columns
        else pd.Series(float("nan"), index=df.index)
    )
    has_pnl = pnl.notna()
    result = (
        df["result"].fillna("").astype(str).str.lower()
        if "result" in df.columns
        else pd.Series("", index=df.index)
    )
    win = (has_pnl & pnl.gt(0)) | (~has_pnl & result.eq("win"))
    loss = (has_pnl & pnl.lt(0)) | (~has_pnl & result.eq("loss"))
    breakeven = (has_pnl & pnl.eq(0)) | (~has_pnl & result.eq("breakeven"))
    return win.astype(bool), loss.astype(bool), breakeven.astype(bool)
```

- [x] **Step 4: Verify all metric consumers**

Run:

```bash
.venv/bin/python -m pytest tests/test_metrics.py tests/test_dashboard_metrics.py tests/test_weekly.py tests/test_patterns.py -q
.venv/bin/ruff check src/tradelens/services/metrics.py
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/tradelens/services/metrics.py tests/test_metrics.py tests/test_dashboard_metrics.py
git commit -m "metrics: use P&L as canonical outcome when present"
```

### Task 3: Add one low-data policy for every analytical surface

**Files:**
- Create: `src/tradelens/ui/components/data_state.py`
- Create: `tests/test_data_state.py`
- Modify: `src/tradelens/ui/pages/4_Analytics.py:250-469`
- Modify: `src/tradelens/ui/app.py:251-309`
- Modify: `src/tradelens/ui/design_system.py:460-535`

**Interfaces:**
- Produces: `SampleState` and `sample_state(df: pd.DataFrame) -> SampleState`; chart rules are shared rather than page-specific.

- [x] **Step 1: Write threshold tests**

```python
def test_one_trade_allows_summary_but_not_series_or_comparisons():
    state = sample_state(pd.DataFrame({"trade_date": ["2026-07-18"], "pnl": [-500]}))
    assert state.show_summary
    assert not state.show_series
    assert not state.show_comparisons


def test_two_dated_trades_allow_series():
    df = pd.DataFrame(
        {"trade_date": ["2026-07-17", "2026-07-18"], "pnl": [100, -50]}
    )
    assert sample_state(df).show_series


def test_five_trades_allow_pattern_sections():
    df = pd.DataFrame({"trade_date": [f"2026-07-{d:02d}" for d in range(1, 6)]})
    assert sample_state(df).show_patterns
```

- [x] **Step 2: Implement `SampleState`**

```python
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SampleState:
    trades: int
    dated_points: int
    show_summary: bool
    show_series: bool
    show_comparisons: bool
    show_patterns: bool


def sample_state(df: pd.DataFrame) -> SampleState:
    trades = 0 if df is None else len(df)
    dated = 0
    if trades and "trade_date" in df.columns:
        dated = int(pd.to_datetime(df["trade_date"], errors="coerce").dropna().nunique())
    return SampleState(
        trades=trades,
        dated_points=dated,
        show_summary=trades >= 1,
        show_series=trades >= 2 and dated >= 2,
        show_comparisons=trades >= 2,
        show_patterns=trades >= 5,
    )
```

- [x] **Step 3: Replace oversized sparse charts**

In Dashboard and Analytics:

- Render KPI summaries for one or more trades.
- When `show_series` is false, render the existing `render_empty_state()` with title `Add one more dated trade` and body `Two trading dates are needed to draw a meaningful curve.`
- When a breakdown has fewer than two categories, render a compact table/statement rather than a bar chart.
- When best and worst resolve to the same category, render one card labeled `Only session in this range`.
- Do not render drawdown, heatmap, day-of-week bars, or emotional comparisons until their data has at least two meaningful points/categories.

- [x] **Step 4: Add a compact data-state style**

Use the existing `render_empty_state` surface and add only `.tl-data-state` spacing/width rules in `design_system.py`; do not add new colors.

- [x] **Step 5: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_data_state.py tests/test_metrics.py tests/test_dashboard.py tests/test_pages_boot.py -q
.venv/bin/ruff check src/tradelens/ui/components/data_state.py src/tradelens/ui/pages/4_Analytics.py src/tradelens/ui/app.py
```

Expected: PASS; a one-trade AppTest run contains no Plotly chart for equity/drawdown/breakdowns.

- [x] **Step 6: Commit**

```bash
git add src/tradelens/ui/components/data_state.py src/tradelens/ui/pages/4_Analytics.py src/tradelens/ui/app.py src/tradelens/ui/design_system.py tests/test_data_state.py tests/test_dashboard.py
git commit -m "analytics: replace sparse charts with meaningful data states"
```

### Task 4: Simplify New Trade to one progress system

**Files:**
- Modify: `src/tradelens/ui/pages/1_NewTrade.py:150-220,690-760`
- Modify: `src/tradelens/ui/design_system.py:600-650`
- Modify: `tests/test_page_polish.py`

**Interfaces:**
- Produces: one `.tl-stepper` rail with accessible `aria-current="step"`; removes the duplicate text-tab row.

- [x] **Step 1: Add source/UI contract tests**

```python
def test_new_trade_has_one_progress_component():
    src = NEW_TRADE.read_text(encoding="utf-8")
    assert src.count("render_stepper(") == 1
    assert "Screenshot & AI    2 · Market Context" not in src


def test_stepper_marks_current_step_semantically():
    html = render_stepper(3)
    assert html.count('aria-current="step"') == 1
    assert ">Trade Details<" in html
```

- [x] **Step 2: Run and verify failure**

Run: `.venv/bin/python -m pytest tests/test_page_polish.py -q -k stepper`  
Expected: FAIL.

- [x] **Step 3: Keep only the numbered rail**

Delete the duplicated markdown/tab heading. Update `render_stepper()` so completed steps use a check mark plus label, the current step uses its number plus `aria-current`, and future steps use neutral numbers. Keep connectors neutral/teal through existing tokens.

- [x] **Step 4: Make navigation actions stable**

At the bottom of each step, render a two-column Previous/Continue row. Previous uses secondary styling; Continue/Review/Save is the only primary action. Required errors appear immediately above this row.

- [x] **Step 5: Verify and commit**

Run: `.venv/bin/python -m pytest tests/test_page_polish.py tests/test_pages_boot.py tests/test_ai_autofill_review.py -q`  
Expected: PASS.

```bash
git add src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/design_system.py tests/test_page_polish.py
git commit -m "new-trade: simplify wizard to one progress system"
```

### Task 5: Replace developer-facing AI details with evidence and confidence

**Owner:** weekly service edits run in the dedicated weekly session.

**Files:**
- Modify: `src/tradelens/ui/pages/6_Insights.py:203-410`
- Modify: `src/tradelens/ui/pages/2_Trades.py:314-360`
- Modify: `src/tradelens/services/weekly.py:33-40`
- Modify: `prompts/weekly_recap_v1.txt:30-60`
- Modify: `tests/test_insights_page.py`
- Modify: `tests/test_weekly.py`

**Interfaces:**
- Produces: user-facing disclosure titled `Evidence used`; weekly required section titled `Observed Patterns`; internal cost/reasoning data remains stored for Settings/admin accounting but is not rendered in the normal journal path.

- [x] **Step 1: Update failing copy contracts**

Change required-section tests to expect `### Observed Patterns`. Add source assertions that Insights and Journal do not render `thinking_summary` or `cost_usd` captions in their normal page code.

- [x] **Step 2: Run and verify failure**

Run: `.venv/bin/python -m pytest tests/test_weekly.py tests/test_insights_page.py -q`  
Expected: FAIL on the old heading and developer-detail rendering.

- [x] **Step 3: Rename the weekly section**

Change `_REQUIRED_SECTIONS` and the prompt heading to `### Observed Patterns`. Update the prompt instruction to request three to six evidence-backed behavioral observations with an explicit sample count and confidence label.

- [x] **Step 4: Replace the UI disclosure**

Delete the model-reasoning expander and generation-cost caption. Render:

```python
with st.expander("Evidence used"):
    st.markdown(f"- **Trades reviewed:** {stats.get('total_trades', 0)}")
    st.markdown(f"- **Period:** {monday} to {sunday}")
    st.markdown(f"- **Strategy profile:** {'Included' if _strategy else 'Not included'}")
    st.markdown(f"- **Confidence:** {_confidence_label(stats.get('total_trades', 0))}")
```

Define `_confidence_label(n)` as `Low` for `<10`, `Developing` for `10-19`, and `Higher` for `>=20`.

- [x] **Step 5: Verify and commit**

Run:

```bash
.venv/bin/python -m pytest tests/test_weekly.py tests/test_insights_page.py tests/test_journal.py tests/test_pages_boot.py -q
.venv/bin/ruff check src/tradelens/services/weekly.py src/tradelens/ui/pages/6_Insights.py src/tradelens/ui/pages/2_Trades.py
```

Expected: PASS.

```bash
git add src/tradelens/services/weekly.py prompts/weekly_recap_v1.txt src/tradelens/ui/pages/6_Insights.py src/tradelens/ui/pages/2_Trades.py tests/test_weekly.py tests/test_insights_page.py
git commit -m "ai-review: show evidence and confidence instead of debug details"
```

### Task 6: Make secondary actions visually secondary

**Files:**
- Modify: `src/tradelens/ui/pages/2_Trades.py:90-160`
- Modify: `src/tradelens/ui/pages/4_Analytics.py:170-250`
- Modify: `src/tradelens/ui/design_system.py:319-347`
- Modify: `tests/test_page_polish.py`

**Interfaces:**
- Produces: `.tl-secondary-action` styling for reset/regenerate/navigation actions; only save/start/continue actions use solid teal.

- [x] **Step 1: Add a failing style contract**

Assert `Clear Filters`, regenerate actions, and Previous navigation are rendered as secondary/outline controls, while Save Trade remains primary.

- [x] **Step 2: Implement scoped secondary action CSS**

Use widget-key containers rather than bare button selectors:

```css
[class*="st-key-secondary_"] button {
  background: transparent;
  color: var(--tl-text);
  border-color: var(--tl-border);
  box-shadow: none;
}
@media (hover: hover) and (pointer: fine) {
  [class*="st-key-secondary_"] button:hover {
    background: var(--tl-surface-2);
    border-color: var(--tl-text-muted);
  }
}
```

Give reset/regenerate/previous controls keys beginning `secondary_`.

- [x] **Step 3: Verify and commit**

Run: `.venv/bin/python -m pytest tests/test_page_polish.py tests/test_design_system.py tests/test_pages_boot.py -q`  
Expected: PASS.

```bash
git add src/tradelens/ui/pages/2_Trades.py src/tradelens/ui/pages/4_Analytics.py src/tradelens/ui/design_system.py tests/test_page_polish.py
git commit -m "ui: reserve solid teal for primary actions"
```

### Task 7: Re-capture trustworthy product imagery

**Files:**
- Modify: `site/assets/shot-dashboard-wide.webp`
- Modify: `site/assets/shot-journal.webp`
- Modify: `site/assets/shot-analytics.webp`
- Modify: `site/assets/shot-newtrade.webp`
- Modify: `site/assets/shot-insights.webp`
- Modify: `site/assets/shot-calendar.webp`
- Modify: `site/assets/shot-strategy.webp`

**Interfaces:**
- Consumes: Tasks 1-6 complete and a deterministic demo user with coherent sample data.
- Produces: screenshot set with no contradictory values, owner toolbar, account name, access token, or implementation cost.

- [x] **Step 1: Seed coherent demo data**

Run `DEMO_MODE=true .venv/bin/python scripts/seed.py` in a temporary database and verify every row passes `canonical_outcome(row.result, row.pnl)`.

- [x] **Step 2: Capture at 1600px desktop and 390px phone**

Capture auth plus the seven primary pages. Desktop images feed marketing; phone images are QA evidence and need not ship.

- [x] **Step 3: Apply the image acceptance checklist**

- No provider/owner toolbar in the crop.
- No username or private strategy name.
- No impossible metric or empty giant chart.
- Text readable at the marketing crop size.
- Consistent viewport, crop, and 3:2 ratio.
- WebP quality 80, each screenshot under 200 KB.

- [x] **Step 4: Commit**

```bash
git add site/assets/shot-dashboard-wide.webp site/assets/shot-journal.webp site/assets/shot-analytics.webp site/assets/shot-newtrade.webp site/assets/shot-insights.webp site/assets/shot-calendar.webp site/assets/shot-strategy.webp
git commit -m "site: refresh product imagery after trust fixes"
```

### Task 8: Full product verification

**Files:**
- Modify: only fixes discovered during verification.

**Interfaces:**
- Produces: release evidence for one-trade, five-trade, and twenty-trade states.

- [x] **Step 1: Run focused suites**

```bash
.venv/bin/python -m pytest tests/test_trade_validation.py tests/test_trade_service.py tests/test_metrics.py tests/test_dashboard_metrics.py tests/test_data_state.py tests/test_weekly.py tests/test_insights_page.py tests/test_page_polish.py tests/test_pages_boot.py -q
```

Expected: PASS.

- [x] **Step 2: Run full quality gates**

```bash
.venv/bin/ruff check src/ scripts/
.venv/bin/black --check src/ scripts/
DEMO_MODE=true .venv/bin/python -m pytest tests/ -q
```

Expected: all clean/passing.

- [x] **Step 3: Visual matrix**

Verify desktop and phone for:

- 0 trades: guided empty state.
- 1 trade: summary metrics, no comparative chart.
- 5 trades: early observed patterns with low confidence.
- 20 trades: full analytics and higher-confidence review.
- Attempted contradictory save/edit: blocked with one clear error.
