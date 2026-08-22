# Phase 2 — Overview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/app` a real Overview — the KPI row, risk and discipline, performance trajectory, recurring edge, the trading-days calendar, the next review action, and recent trades — served through the Phase 0 FastAPI boundary and rendered in the Phase 1 shell.

**Architecture:** One new endpoint, `GET /v1/overview`, composes the existing pandas metric functions into a single owner-scoped payload. The `/app` page is a Server Component: it reads the session cookie and the period from the URL, makes one server-to-server call through `callApi`, and renders. No client-side data fetching, no second round trip, no new npm dependency.

**Tech Stack:** FastAPI · Pydantic v2 · pandas (existing metrics, unchanged) · Next.js 16 App Router (RSC) · TypeScript · Tailwind · inline SVG · pytest · Vitest

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md` (§7 phase 2, §8 Overview inventory, §2.2 request lifecycle, §12 design direction)

## Global Constraints

- **The Phase 0 security architecture is untouchable.** Preserved exactly: the domain-separated `X-TL-Session-Handle`, the HMAC boundary and its canonical-query contract, mandatory service-layer ownership, the R2 quarantine/finalization model, the generated OpenAPI/TypeScript contract gates.
- **The owner comes from the session row and nowhere else.** No user id from a header, query parameter, or body — ever.
- **Every service call passes an explicit `user_id`.** `require_user_id` guards it; no nullable-owner path may be reintroduced.
- TradeLens is a **post-trade reflection journal**. Never a signal app, a bot, or financial advice. This binds every label, empty state, error string, tooltip and comment. Nothing may imply a live market opinion or a good moment to trade.
- **No new npm dependencies.** Charts are inline SVG.
- Python 3.9.6 locally / 3.11 in CI and the container: `from __future__ import annotations` in new modules, no `X | Y` unions or other 3.10+ syntax.
- No Streamlit imports in `services/`, `db/`, or `src/tradelens/api/`.
- Gates: `pytest tests/ -q`, `ruff check src/ scripts/`, `black --check src/ scripts/ tests/`, and in `web/`: `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build`.
- jest-dom is not registered globally; new web test files need `import "@testing-library/jest-dom/vitest";` first.
- The `npm run build` needs `APP_ORIGIN`, `SITE_ORIGIN` and `SUPPORT_EMAIL` for the existing marketing prebuild step.

---

## Execution process for this phase

Lighter than Phase 1, at the owner's direction. Work is organised into **groups**, not
per-task review gates.

| Group | Review depth |
|---|---|
| A — shared policy, aggregation service, API endpoint | **Deep independent review.** Ownership, the API boundary, and metric correctness all land here. |
| B — Next.js data layer | **Deep independent review.** It crosses the security boundary. |
| C — KPI row and risk/discipline presentation | Light review at the group boundary. |
| D — trajectory, recurring edge, calendar | Light review, **except** the chart-correctness tests, which are TDD'd like data. |
| E — next review action, recent trades, assembly | Light review at the group boundary. |
| F — verification and handoff | Final phase-boundary review. |

**TDD applies to data contracts and metric correctness, not to routine presentation.** A stat
tile that renders a number it was handed does not need a test written before it. A function
deciding whether a sample has earned a chart does.

**Do not mutation-test routine presentation code.** Reserve that for a test whose validity is
genuinely in question — Phase 1 earned one such check and it found a real defect, but applying
it to every card is waste.

---

## Design decisions

**1. One endpoint, one payload.** `GET /v1/overview?from=&to=` returns the whole Overview.
Not eight endpoints. The page is a Server Component that renders once, so eight calls would be
eight round trips for one screen, and the period is a single shared input. When Phase 6 needs
per-lens fetching it can add endpoints then; Overview does not.

**2. The period is already authenticated.** Phase 0 binds the canonical query string into the
HMAC, so `?from=&to=` cannot be tampered with in transit — a modified range fails Lock 1
before any handler runs. This is the first phase to collect on that work. The server still
validates the range independently, because an authenticated request can still carry nonsense.

**3. The low-data policy moves out of `ui/` and becomes shared.** `data_state.py` already holds
a careful, Streamlit-free policy — what a sample has earned the right to display — and its
docstring says the answer must be the same on every surface. It currently lives under `ui/`,
which Phase 10 deletes. Phase 2 moves the pure decision functions to
`src/tradelens/services/sample_policy.py`; the Streamlit component re-exports from there so the
old app keeps working during parity. This is the one piece of shared infrastructure Overview
genuinely requires, and it is cheaper to move now than to have two policies disagree later.

**4. Green and red are never the only difference — this is computed, not assumed.**
Running the palette validator on the outcome pair against a dark surface:

```
CVD separation  worst adjacent #f56565↔#22c55e  ΔE 2.3 (deutan)   FAIL
Normal-vision   worst adjacent #f56565↔#22c55e  ΔE 33.2           PASS
```

To a deuteranope — the most common colour-vision deficiency — the win colour and the loss
colour are the same colour. Normal vision reads them as obviously different, which is exactly
why this ships undetected. So **every** positive/negative distinction carries a second channel:
the calendar uses a filled circle for a positive day and a hollow diamond for a negative one,
KPI values carry an explicit sign in the text, and the equity curve is a single series whose
value is labelled. No chart in this phase distinguishes anything by hue alone.

**5. The equity curve is one series, so it needs no legend and no categorical palette.** Its
line colour is a *status* colour — `positive` when the period ended up, `negative` when down —
which is honest about what the shape means and keeps teal reserved for actions, per the Phase 1
token discipline. A single line plus its labelled end value carries identity without colour.

**6. Charts are inline SVG.** A line/area curve and a month grid do not justify a charting
dependency, and adding one now would pick Phase 6's library before Phase 6 knows what it needs.

## Risks

**The metric functions expect specific DataFrame columns.** The parity harness already pins
their output for a fixed dataset; Phase 2's aggregation must feed them the same column shapes or
it will silently produce different numbers. Mitigation: the aggregation service is tested
against the same golden dataset the parity harness uses, asserting equality with the harness's
own snapshot rather than with hand-written expectations.

**Undefined metrics are not zero.** Profit factor is infinite with no losses; expectancy is
undefined with no trades. Phase 0 built `finite_or_state` for exactly this. A tile that renders
`0.0` where the truth is "no losses yet" is the confident-wrong-number failure the 10K audit
called out. Mitigation: every possibly-undefined figure crosses the boundary as a value plus a
state, and the tile renders the state.

**Low-sample states are the whole point of this screen.** An Overview that draws a full-height
bar for one trade reads as a finding. Mitigation: the shared policy decides, and the tests for
it are written first.

**The Overview page will grow large.** Seven sections in one route. Mitigation: each section is
its own component file under `web/components/app/overview/`, and the page composes them.

---

## File Structure

**Python — new**

| File | Responsibility |
|---|---|
| `src/tradelens/services/sample_policy.py` | The shared low-data policy: what a sample has earned the right to display. Pure. |
| `src/tradelens/services/overview.py` | Composes the existing metric functions into one owner-scoped Overview payload. Pure of HTTP. |
| `src/tradelens/api/schemas/overview.py` | Pydantic response models — the typed contract the TypeScript client is generated from. |
| `src/tradelens/api/routers/overview.py` | `GET /v1/overview`. Thin: validate the period, call the service with the session's owner, return. |

**Python — modified**

| File | Change |
|---|---|
| `src/tradelens/ui/components/data_state.py` | Re-export the moved policy so Streamlit keeps working unchanged. |
| `src/tradelens/api/app.py` | Register the overview router. |

**TypeScript — new**

| File | Responsibility |
|---|---|
| `web/lib/app/overview.ts` | Server-only fetch of the Overview payload: cookie → `callApi` → typed result. |
| `web/components/app/overview/stat-tile.tsx` | One figure with its label, sign, and undefined-state. |
| `web/components/app/overview/kpi-row.tsx` | Net P&L, win rate, expectancy, profit factor, trades. |
| `web/components/app/overview/risk-discipline.tsx` | Max drawdown, rule adherence, edge leak, consistency. |
| `web/components/app/overview/equity-curve.tsx` | The inline-SVG curve plus its low-sample state. |
| `web/components/app/overview/trajectory.tsx` | The curve alongside streaks and average win/loss. |
| `web/components/app/overview/recurring-edge.tsx` | Killzone and setup performance. |
| `web/components/app/overview/trading-calendar.tsx` | Month grid, shape-encoded day outcomes. |
| `web/components/app/overview/next-review-action.tsx` | The activation next step. |
| `web/components/app/overview/recent-trades.tsx` | The last few trades as a table. |

**TypeScript — modified**

| File | Change |
|---|---|
| `web/app/app/page.tsx` | Becomes the real Overview: fetches once, composes the sections. |
| `web/app/app/error.tsx` (new) | Route error boundary — finally gives `ErrorState` a caller. |
| `web/app/app/loading.tsx` (new) | Route loading state — gives `LoadingState` a caller. |

---

# GROUP A — Shared policy, aggregation, endpoint

*Deep independent review at the group boundary: ownership, API boundary, metric correctness.*

### Task A1: Move the low-data policy into services

**Files:**
- Create: `src/tradelens/services/sample_policy.py`
- Modify: `src/tradelens/ui/components/data_state.py`
- Test: `tests/test_sample_policy.py`

**Interfaces:**
- Consumes: nothing
- Produces: `SampleState` dataclass with fields `trades: int`, `dated_points: int`, `show_summary: bool`, `show_series: bool`, `show_dominant_series: bool`, `show_comparisons: bool`, `show_patterns: bool`; `sample_state(df) -> SampleState`; `trades_needed(state, threshold) -> int`; `MIN_DATED_POINTS`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sample_policy.py
"""The low-data policy, now shared by Streamlit and the API.

These thresholds are not arbitrary: a full-height bar for one trade and a
straight line between two points both read as findings when they are really a
small sample, which is the fastest way to lose a trader's trust.
"""
import pandas as pd
import pytest

from src.tradelens.services.sample_policy import (
    MIN_DATED_POINTS,
    SampleState,
    sample_state,
    trades_needed,
)


def _df(n, dated=None):
    """n trades; `dated` distinct trade dates (defaults to n)."""
    dates = [f"2026-08-{(i % (dated or n)) + 1:02d}" for i in range(n)]
    return pd.DataFrame({"trade_date": dates, "pnl": [10.0] * n})


def test_no_trades_earns_nothing():
    s = sample_state(pd.DataFrame())
    assert s.trades == 0
    assert not s.show_summary
    assert not s.show_series
    assert not s.show_comparisons


def test_one_trade_earns_a_summary_but_no_curve():
    s = sample_state(_df(1))
    assert s.show_summary
    assert not s.show_series, "two points are the minimum for a line"


def test_two_dated_points_earn_a_series_but_not_a_dominant_one():
    s = sample_state(_df(2))
    assert s.show_series
    assert not s.show_dominant_series, "a headline instrument needs four points"


def test_four_dated_points_earn_the_dominant_series():
    assert sample_state(_df(4)).show_dominant_series
    assert MIN_DATED_POINTS == 4


def test_patterns_need_five_trades():
    assert not sample_state(_df(4)).show_patterns
    assert sample_state(_df(5)).show_patterns


def test_dated_points_counts_distinct_days_not_rows():
    # Ten trades on two days is still two points on a curve.
    s = sample_state(_df(10, dated=2))
    assert s.trades == 10
    assert s.dated_points == 2
    assert not s.show_dominant_series


def test_none_is_treated_as_empty():
    assert sample_state(None).trades == 0


@pytest.mark.parametrize("have,threshold,want", [(0, 5, 5), (3, 5, 2), (5, 5, 0), (7, 5, 0)])
def test_trades_needed_never_goes_negative(have, threshold, want):
    assert trades_needed(sample_state(_df(have)) if have else sample_state(None), threshold) == want


def test_the_streamlit_component_re_exports_the_same_objects():
    """Streamlit must keep working during parity, on the same policy.

    Two copies of this policy would let the Dashboard and the API disagree about
    what a sample has earned — the exact thing its docstring forbids.
    """
    from src.tradelens.ui.components import data_state

    assert data_state.sample_state is sample_state
    assert data_state.SampleState is SampleState
    assert data_state.MIN_DATED_POINTS == MIN_DATED_POINTS
```

- [ ] **Step 2: Run it and watch it fail**

Run: `/Users/ayoub/tradelens-ai/.venv/bin/pytest tests/test_sample_policy.py -q`
Expected: FAIL — `ModuleNotFoundError: src.tradelens.services.sample_policy`

- [ ] **Step 3: Move the pure policy**

Create `src/tradelens/services/sample_policy.py` by moving — not copying — everything above the
render helper from `src/tradelens/ui/components/data_state.py`: the module docstring, the
threshold constants (`_MIN_SERIES_POINTS`, `_MIN_COMPARISON_TRADES`, `_MIN_CATEGORIES`,
`_MIN_PATTERN_TRADES`, `_MIN_DOMINANT_POINTS`, `MIN_DATED_POINTS`), the `SampleState` dataclass,
and the pure functions `sample_state`, `show_dated_instrument`, `leading_category`,
`has_variation`, `enough_categories` and `trades_needed`.

Adjust the docstring's first line to say it is shared by the Streamlit app and the API rather
than "every analytical surface", and drop the sentence about the render helper — that helper
stays behind.

- [ ] **Step 4: Re-export from the Streamlit component**

In `src/tradelens/ui/components/data_state.py`, delete the moved code and replace it with a
re-export, keeping only `render_data_state` (which touches Streamlit) local:

```python
"""Streamlit rendering for the shared low-data policy.

The policy itself moved to `services/sample_policy` so the API and the
Streamlit app decide identically what a sample has earned the right to
display. Only the render helper lives here, because only it touches Streamlit.
"""

from __future__ import annotations

from src.tradelens.services.sample_policy import (  # noqa: F401 — re-exported
    MIN_DATED_POINTS,
    SampleState,
    enough_categories,
    has_variation,
    leading_category,
    sample_state,
    show_dated_instrument,
    trades_needed,
)
```

Keep the existing `render_data_state` function below that import block, unchanged.

- [ ] **Step 5: Run the new test and the Streamlit suites that depend on it**

Run: `/Users/ayoub/tradelens-ai/.venv/bin/pytest tests/test_sample_policy.py tests/test_data_state.py tests/test_dashboard.py -q`
Expected: PASS. The existing `test_data_state.py` must pass **unchanged** — if it needs editing,
the move was not behaviour-preserving.

- [ ] **Step 6: Full suite, lint, commit**

```bash
/Users/ayoub/tradelens-ai/.venv/bin/pytest tests/ -q
/Users/ayoub/tradelens-ai/.venv/bin/ruff check src/ scripts/ && /Users/ayoub/tradelens-ai/.venv/bin/black --check src/ scripts/ tests/
git add -A
git commit -m "refactor(services): share the low-data policy with the API

The policy decides what a sample has earned the right to display, and its
own docstring says the answer must be the same on every surface — but it
lived under ui/, which Phase 10 deletes. Moved to services/; the
Streamlit component re-exports it so the old app runs on exactly the same
objects rather than a second copy free to drift."
```

---

### Task A2: The Overview aggregation service

**Files:**
- Create: `src/tradelens/services/overview.py`
- Modify: `src/tradelens/services/metrics.py` (add ONE new public function — see Step 0)
- Test: `tests/test_overview_service.py`

**Interfaces:**
- Consumes: `sample_state` (A1); `require_user_id`; the existing metric functions
- Produces: `build_overview(*, user_id: int, start: str, end: str, today: Optional[date] = None) -> dict`; `metrics.setup_performance(trades: pd.DataFrame) -> pd.DataFrame`

- [ ] **Step 0: Add `setup_performance` to metrics**

`by_setup_type` returns `[setup_type, trades, wins, losses, breakevens]` and carries **no
P&L column**, so the Overview's setup breakdown cannot be built from it. Add a new public
function beside `killzone_performance`, using the same private engine, which does yield
`total_pnl`:

```python
def setup_performance(trades: pd.DataFrame) -> pd.DataFrame:
    """Per-setup performance, shaped like `killzone_performance`.

    `by_setup_type` answers a different question — how many trades, won and
    lost, per setup — and carries no P&L column. The Overview shows setups and
    killzones side by side, so they must be the same shape or the comparison
    is not one.

    Returns columns: setup_type, trades, wins, losses, breakevens, win_rate,
    avg_rr_realized, total_pnl — sorted by total_pnl descending. Empty input
    gives an empty frame with those columns.
    """
    return _group_with_rr(trades, by="setup_type")
```

Add a test to `tests/test_metrics.py`:

```python
def test_setup_performance_carries_pnl_and_sample_size():
    """The Overview puts setups beside killzones, so it needs the same columns."""
    df = pd.DataFrame({
        "setup_type": ["FVG", "FVG", "OB"],
        "result": ["Win", "Loss", "Win"],
        "pnl": [100.0, -40.0, 25.0],
        "rr_realized": [2.0, -1.0, 1.0],
    })
    out = metrics.setup_performance(df)
    assert set(["setup_type", "trades", "total_pnl"]).issubset(out.columns)
    fvg = out[out["setup_type"] == "FVG"].iloc[0]
    assert fvg["trades"] == 2
    assert fvg["total_pnl"] == 60.0


def test_setup_performance_is_empty_without_setups():
    out = metrics.setup_performance(pd.DataFrame())
    assert out.empty
    assert "total_pnl" in out.columns
```

This is a **new** public function, so it cannot change any output the parity harness pins.
Do not modify any existing function in `services/metrics.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_overview_service.py
"""The Overview payload.

Correctness here is checked against the SAME golden dataset the parity harness
pins, so the API cannot quietly compute different numbers from the ones the
services were verified to produce.
"""
import pytest

from src.tradelens.services import overview
from tests.parity.dataset import seed_golden_dataset

PERIOD = {"start": "2026-08-01", "end": "2026-08-31"}


@pytest.fixture
def seeded(two_users):
    owner, other = two_users
    seed_golden_dataset(owner)
    return owner, other


def test_requires_a_concrete_owner():
    with pytest.raises(ValueError):
        overview.build_overview(user_id=None, start=PERIOD["start"], end=PERIOD["end"])


def test_headline_numbers_match_the_golden_dataset(seeded):
    owner, _ = seeded
    data = overview.build_overview(user_id=owner, **PERIOD)
    # 480 - 220 + 410 + 0 - 95
    assert data["kpi"]["net_pnl"] == 575.0
    assert data["kpi"]["trades"] == 5
    assert data["kpi"]["wins"] == 2
    assert data["kpi"]["losses"] == 2


def test_sees_only_its_own_owner(seeded):
    """The cardinal property. A second trader's rows must never appear."""
    _, other = seeded
    data = overview.build_overview(user_id=other, **PERIOD)
    assert data["kpi"]["trades"] == 0
    assert data["kpi"]["net_pnl"] == 0.0


def test_undefined_profit_factor_is_named_not_zeroed(two_users):
    """No losses means the ratio has no denominator.

    Rendering 0.0 there would be a confident wrong number — the exact failure
    the audit called out.
    """
    owner, _ = two_users
    from src.tradelens.services import trade_service

    trade_service.create_trade({
        "user_id": owner, "trade_date": "2026-08-10", "asset": "NQ",
        "result": "Win", "pnl": 100.0,
    })
    data = overview.build_overview(user_id=owner, **PERIOD)
    assert data["kpi"]["profit_factor"] is None
    assert data["kpi"]["profit_factor_state"] == "undefined_positive_infinity"


def test_empty_period_reports_zero_trades_rather_than_failing(two_users):
    owner, _ = two_users
    data = overview.build_overview(user_id=owner, start="2020-01-01", end="2020-01-31")
    assert data["kpi"]["trades"] == 0
    assert data["sample"]["show_summary"] is False
    assert data["trajectory"]["equity_curve"] == []


def test_sample_flags_come_from_the_shared_policy(seeded):
    owner, _ = seeded
    data = overview.build_overview(user_id=owner, **PERIOD)
    assert data["sample"]["trades"] == 5
    assert data["sample"]["show_patterns"] is True
    assert data["sample"]["show_dominant_series"] is True


def test_every_value_survives_strict_json(seeded):
    """The boundary rejects NaN and Infinity, so the service must not emit them."""
    import json

    from src.tradelens.api.serialization import to_jsonable

    owner, _ = seeded
    json.dumps(to_jsonable(overview.build_overview(user_id=owner, **PERIOD)), allow_nan=False)


def test_recent_trades_are_newest_first_and_capped(seeded):
    owner, _ = seeded
    rows = overview.build_overview(user_id=owner, **PERIOD)["recent_trades"]
    assert len(rows) <= 5
    assert [r["trade_date"] for r in rows] == sorted(
        (r["trade_date"] for r in rows), reverse=True)


def test_calendar_reports_the_month_of_the_period_end(seeded):
    owner, _ = seeded
    cal = overview.build_overview(user_id=owner, **PERIOD)["calendar"]
    assert cal["year"] == 2026 and cal["month"] == 8
    outcomes = {d["outcome"] for d in cal["days"]}
    assert outcomes <= {"positive", "negative", "flat"}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `/Users/ayoub/tradelens-ai/.venv/bin/pytest tests/test_overview_service.py -q`
Expected: FAIL — `ModuleNotFoundError: src.tradelens.services.overview`

- [ ] **Step 3: Write the service**

```python
# src/tradelens/services/overview.py
"""Compose the Overview payload from the existing metric functions.

This module adds no arithmetic. Every figure comes from `services/metrics`,
which the parity harness already pins — the job here is to select, name, and
shape, so that the API and the Streamlit Dashboard cannot drift into two
different answers to the same question.

Two rules govern the shaping:

* **Undefined is not zero.** Profit factor with no losses, expectancy with no
  trades, a drawdown over an empty period — each crosses the boundary as a
  value plus a state, never as a plausible-looking number.
* **A sample decides what it has earned.** The flags come from
  `services/sample_policy`, so the client renders a low-data state rather than
  inventing one per component.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

import pandas as pd

from src.tradelens.api.serialization import finite_or_state
from src.tradelens.services import metrics
from src.tradelens.services.activation import activation_status
from src.tradelens.services.ownership import require_user_id
from src.tradelens.services.sample_policy import sample_state
from src.tradelens.services.strategy import get_active_strategy
from src.tradelens.services.trade_service import get_trades
from src.tradelens.services.weekly import get_weekly_reviews

RECENT_TRADE_LIMIT = 5

_TRADE_COLUMNS = (
    "id", "trade_date", "entry_time", "asset", "session", "setup_type", "timeframe",
    "result", "pnl", "rr_realized", "risk_amount", "followed_rules", "mistake_tags",
    "strategy_used", "htf_bias", "ltf_bias", "killzone", "day_of_week",
)


def _frame(trades: List[Any]) -> pd.DataFrame:
    """The metric functions take a DataFrame with these exact columns.

    Built explicitly rather than from `__dict__` so a schema change surfaces
    here as a missing column instead of silently changing a metric.
    """
    if not trades:
        return pd.DataFrame(columns=list(_TRADE_COLUMNS))
    return pd.DataFrame(
        [{c: getattr(t, c, None) for c in _TRADE_COLUMNS} for t in trades]
    )


def _pair(value: Any) -> Dict[str, Any]:
    """A possibly-undefined number as {value, state}."""
    number, state = finite_or_state(value)
    return {"value": number, "state": state}


def _need(mapping: Any, key: str) -> Any:
    """Read a required key, loudly.

    Deliberately not `.get(key, 0.0)`. Every figure here comes from
    `services/metrics`, and if one of those functions is renamed or its output
    reshaped, a defaulting read turns the mistake into a plausible $0.00 on a
    trader's dashboard instead of a failure. The pre-flight scan for this phase
    found six such wrong column names at once, five of which would have rendered
    as confident zeroes. Fail here instead.
    """
    if isinstance(mapping, dict):
        if key not in mapping:
            raise KeyError(f"metrics output is missing {key!r}; got {sorted(mapping)}")
        return mapping[key]
    if key not in mapping:
        raise KeyError(f"metrics frame is missing column {key!r}")
    return mapping[key]


def build_overview(
    *,
    user_id: int,
    start: str,
    end: str,
    today: Optional[dt.date] = None,
) -> dict:
    """Everything the Overview screen shows, for one owner over one period."""
    owner = require_user_id(user_id)
    now = today or dt.date.today()

    trades = get_trades(user_id=owner, start_date=start, end_date=end)
    df = _frame(trades)
    sample = sample_state(df)

    basic = metrics.compute_basic_metrics(df)
    equity = metrics.compute_equity_curve(df)
    streaks = metrics.compute_streaks(df)
    adherence = metrics.rule_adherence_rate(df)
    leak = metrics.edge_leak_summary(df)

    pf_value, pf_state = finite_or_state(metrics.compute_profit_factor_raw(df))
    expectancy_value, expectancy_state = finite_or_state(
        metrics.compute_expectancy(basic) if _need(basic, "total_trades") else float("nan")
    )

    end_date = dt.date.fromisoformat(end)

    return {
        "period": {"from": start, "to": end},
        "sample": {
            "trades": sample.trades,
            "dated_points": sample.dated_points,
            "show_summary": sample.show_summary,
            "show_series": sample.show_series,
            "show_dominant_series": sample.show_dominant_series,
            "show_comparisons": sample.show_comparisons,
            "show_patterns": sample.show_patterns,
        },
        "kpi": {
            "net_pnl": float(_need(basic, "total_pnl") or 0.0),
            "win_rate": _need(basic, "win_rate"),
            "expectancy": expectancy_value,
            "expectancy_state": expectancy_state,
            "profit_factor": pf_value,
            "profit_factor_state": pf_state,
            "trades": int(_need(basic, "total_trades") or 0),
            "wins": int(_need(basic, "wins") or 0),
            "losses": int(_need(basic, "losses") or 0),
            "today_pnl": metrics.today_pnl(df, today=now),
            "week_pnl": metrics.current_week_pnl(df, today=now),
        },
        "risk": {
            "max_drawdown": _pair(metrics.compute_max_drawdown(equity)),
            "rule_adherence": {
                "rate": adherence.rate,
                "followed": adherence.followed,
                "recorded": adherence.recorded,
            },
            # EdgeLeakSummary names these net_pnl / qualifying_trades /
            # recorded_trades; the API uses plainer words for the same figures.
            "edge_leak": {
                "amount": leak.net_pnl or 0.0,
                "trades": leak.qualifying_trades,
                "recorded": leak.recorded_trades,
            },
            "consistency": _pair(metrics.consistency_score(df)),
        },
        "trajectory": {
            "equity_curve": [] if not sample.show_series else [
                # daily_equity_curve names the column cumulative_pnl.
                {"date": str(r["trade_date"]), "equity": float(r["cumulative_pnl"])}
                for _, r in metrics.daily_equity_curve(df).iterrows()
            ],
            # compute_streaks names these current_streak / max_win_streak /
            # max_loss_streak.
            "current_streak": _need(streaks, "current_streak"),
            "streak_type": _need(streaks, "streak_type"),
            "best_streak": _need(streaks, "max_win_streak"),
            "worst_streak": _need(streaks, "max_loss_streak"),
            "average_win": _pair(_need(basic, "avg_win")),
            "average_loss": _pair(_need(basic, "avg_loss")),
        },
        "recurring_edge": {
            "killzones": _breakdown(metrics.killzone_performance(df), "killzone"),
            "setups": _breakdown(metrics.setup_performance(df), "setup_type"),
        },
        "calendar": _calendar(df, end_date.year, end_date.month),
        "next_review_action": _next_action(owner, trades),
        "recent_trades": [
            {
                "id": t.id,
                "trade_date": t.trade_date,
                "asset": t.asset,
                "session": t.session,
                "setup_type": t.setup_type,
                "result": t.result,
                "pnl": t.pnl,
                "rr_realized": t.rr_realized,
            }
            for t in trades[:RECENT_TRADE_LIMIT]
        ],
    }


def _breakdown(frame: pd.DataFrame, label_column: str) -> List[dict]:
    """A grouped metric frame as rows the client can render directly.

    Both groupers expose the P&L column as `total_pnl`; the API calls it
    `net_pnl` because that is what it means to a reader.
    """
    if frame is None or frame.empty or label_column not in frame.columns:
        return []
    for required in (label_column, "total_pnl", "trades"):
        if required not in frame.columns:
            raise KeyError(f"breakdown frame is missing column {required!r}")
    rows = []
    for _, r in frame.iterrows():
        rows.append({
            "label": str(r[label_column]),
            "net_pnl": float(r["total_pnl"] or 0.0),
            "trades": int(r["trades"] or 0),
        })
    return rows


def _calendar(df: pd.DataFrame, year: int, month: int) -> dict:
    """One month of trading days.

    An empty day means no trade was taken, which is information rather than
    missing data — so days without trades are simply absent from `days`.
    """
    frame = metrics.calendar_daily_pnl(df, year, month)
    days = []
    if frame is not None and not frame.empty:
        for _, r in frame.iterrows():
            pnl = float(_need(r, "net_pnl") or 0.0)
            days.append({
                "date": str(_need(r, "trade_date")),
                "pnl": pnl,
                "outcome": "positive" if pnl > 0 else "negative" if pnl < 0 else "flat",
            })
    return {"year": year, "month": month, "days": days}


def _next_action(owner: int, trades: List[Any]) -> dict:
    """Where the trader stands on the activation path."""
    status = activation_status(
        strategy=get_active_strategy(owner),
        trades=trades,
        weekly_review=(get_weekly_reviews(owner, limit=1) or [None])[0],
    )
    return {
        "completed": status.completed,
        "total": status.total,
        "next_key": status.next_key,
        "is_activated": status.is_activated,
        "trades_until_review": status.trades_until_review,
    }
```

- [ ] **Step 4: Run the tests**

Run: `/Users/ayoub/tradelens-ai/.venv/bin/pytest tests/test_overview_service.py -q`
Expected: PASS. If a metric function returns a column this code does not expect, fix `_frame`
or `_breakdown` — do not change `services/metrics`, which the parity harness pins.

- [ ] **Step 5: Confirm parity is untouched, then commit**

```bash
/Users/ayoub/tradelens-ai/.venv/bin/pytest tests/parity/ tests/test_overview_service.py -q
/Users/ayoub/tradelens-ai/.venv/bin/ruff check src/ scripts/ && /Users/ayoub/tradelens-ai/.venv/bin/black --check src/ scripts/ tests/
git add -A
git commit -m "feat(services): compose the Overview payload

Adds no arithmetic — every figure comes from services/metrics, which the
parity harness already pins, so the API cannot compute different numbers
from the ones the services were verified to produce.

Undefined crosses the boundary as a value plus a state rather than as a
plausible number: profit factor with no losses is null with
'undefined_positive_infinity', not 0.0."
```

---

### Task A3: The `/v1/overview` endpoint

**Files:**
- Create: `src/tradelens/api/schemas/__init__.py`, `src/tradelens/api/schemas/overview.py`, `src/tradelens/api/routers/overview.py`
- Modify: `src/tradelens/api/app.py`
- Test: `tests/test_api_overview.py`

**Interfaces:**
- Consumes: `build_overview` (A2); `current_user`; `to_jsonable`
- Produces: `GET /v1/overview?from=&to=` → `OverviewResponse`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_api_overview.py
"""The Overview endpoint.

The security properties are the point: the owner comes from the session row,
the period is validated server-side even though the HMAC already covers it,
and a second trader's data is unreachable.
"""
import time

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api.security import sign_request
from tests.parity.dataset import seed_golden_dataset

SECRET = "test-service-secret-value"
PATH = "/v1/overview"
QUERY = "from=2026-08-01&to=2026-08-31"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TL_SERVICE_SECRET", SECRET)
    monkeypatch.setenv("TL_ENV", "production")
    return TestClient(create_app(), raise_server_exceptions=False)


def _headers(handle, *, query=QUERY, path=PATH):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", path, query, b"")
    return {"X-TL-Signature": f"v1={ts}:{sig}", "X-TL-Session-Handle": handle}


def test_unsigned_request_is_refused(client, website_session_handle):
    _, handle = website_session_handle
    assert client.get(f"{PATH}?{QUERY}", headers={"X-TL-Session-Handle": handle}).status_code == 401


def test_request_without_a_session_is_refused(client):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", PATH, QUERY, b"")
    r = client.get(f"{PATH}?{QUERY}", headers={"X-TL-Signature": f"v1={ts}:{sig}"})
    assert r.status_code == 401


def test_returns_the_owner_s_overview(client, website_session_handle):
    user_id, handle = website_session_handle
    seed_golden_dataset(user_id)
    r = client.get(f"{PATH}?{QUERY}", headers=_headers(handle))
    assert r.status_code == 200
    body = r.json()
    assert body["kpi"]["net_pnl"] == 575.0
    assert body["kpi"]["trades"] == 5


def test_never_returns_another_owner_s_data(client, website_session_handle, two_users):
    """A signed, authenticated request still only sees its own rows."""
    user_id, handle = website_session_handle
    other = [u for u in two_users if u != user_id][0]
    seed_golden_dataset(other)
    body = client.get(f"{PATH}?{QUERY}", headers=_headers(handle)).json()
    assert body["kpi"]["trades"] == 0


def test_a_tampered_period_fails_the_signature(client, website_session_handle):
    """The query is bound into the HMAC, so the range cannot be edited in transit."""
    _, handle = website_session_handle
    r = client.get(f"{PATH}?from=1990-01-01&to=2099-01-01", headers=_headers(handle))
    assert r.status_code == 401


def test_a_nonsense_period_is_rejected_with_422(client, website_session_handle):
    """Authenticated is not the same as valid."""
    _, handle = website_session_handle
    bad = "from=not-a-date&to=2026-08-31"
    r = client.get(f"{PATH}?{bad}", headers=_headers(handle, query=bad))
    assert r.status_code == 422


def test_a_reversed_period_is_rejected(client, website_session_handle):
    _, handle = website_session_handle
    bad = "from=2026-08-31&to=2026-08-01"
    r = client.get(f"{PATH}?{bad}", headers=_headers(handle, query=bad))
    assert r.status_code == 422


def test_the_response_is_not_cacheable(client, website_session_handle):
    _, handle = website_session_handle
    r = client.get(f"{PATH}?{QUERY}", headers=_headers(handle))
    assert "no-store" in r.headers.get("cache-control", "")


def test_the_schema_is_typed_not_a_bare_dict(client, website_session_handle):
    """A dict response generates {[k:string]: unknown} and the drift gate then
    protects nothing."""
    from src.tradelens.api.routers.overview import get_overview

    assert get_overview.__annotations__["return"].__name__ == "OverviewResponse"
```

- [ ] **Step 2: Add the `website_session_handle` fixture**

Append to `conftest.py`:

```python
@pytest.fixture
def website_session_handle(website_session):
    """(user_id, session HANDLE) — the sha256 the API actually receives.

    The raw token never crosses into FastAPI; Next.js forwards only this hash.
    """
    import hashlib

    from src.tradelens.services.auth_sessions import WEBSITE_DOMAIN

    user_id, token = website_session
    return user_id, hashlib.sha256((WEBSITE_DOMAIN + token).encode("utf-8")).hexdigest()
```

- [ ] **Step 3: Run it and watch it fail**

Run: `/Users/ayoub/tradelens-ai/.venv/bin/pytest tests/test_api_overview.py -q`
Expected: FAIL — `ModuleNotFoundError: src.tradelens.api.routers.overview`

- [ ] **Step 4: Write the schemas**

```python
# src/tradelens/api/schemas/__init__.py
"""Pydantic response models — the typed contract TypeScript is generated from."""
```

```python
# src/tradelens/api/schemas/overview.py
"""The Overview response contract.

Typed rather than a bare dict, deliberately: a `-> dict` handler generates
`{[key: string]: unknown}` in the TypeScript client, and the drift gate then
guards a contract that says nothing.

`Optional[float]` paired with a `*_state` string is how an undefined figure
crosses the boundary. Null plus "undefined_positive_infinity" is a profit
factor with no losses to divide by — rendering 0.0 there would be a confident
wrong number.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class Period(BaseModel):
    from_: str
    to: str

    model_config = {"populate_by_name": True}


class SampleFlags(BaseModel):
    trades: int
    dated_points: int
    show_summary: bool
    show_series: bool
    show_dominant_series: bool
    show_comparisons: bool
    show_patterns: bool


class Undefinable(BaseModel):
    value: Optional[float] = None
    state: Optional[str] = None


class Kpi(BaseModel):
    net_pnl: float
    win_rate: Optional[float] = None
    expectancy: Optional[float] = None
    expectancy_state: Optional[str] = None
    profit_factor: Optional[float] = None
    profit_factor_state: Optional[str] = None
    trades: int
    wins: int
    losses: int
    today_pnl: float
    week_pnl: float


class RuleAdherence(BaseModel):
    rate: Optional[float] = None
    followed: int
    recorded: int


class EdgeLeak(BaseModel):
    amount: float
    trades: int
    recorded: int


class Risk(BaseModel):
    max_drawdown: Undefinable
    rule_adherence: RuleAdherence
    edge_leak: EdgeLeak
    consistency: Undefinable


class EquityPoint(BaseModel):
    date: str
    equity: float


class Trajectory(BaseModel):
    equity_curve: List[EquityPoint]
    current_streak: Optional[int] = None
    streak_type: Optional[str] = None
    best_streak: Optional[int] = None
    worst_streak: Optional[int] = None
    average_win: Undefinable
    average_loss: Undefinable


class BreakdownRow(BaseModel):
    label: str
    net_pnl: float
    trades: int


class RecurringEdge(BaseModel):
    killzones: List[BreakdownRow]
    setups: List[BreakdownRow]


class CalendarDay(BaseModel):
    date: str
    pnl: float
    outcome: str


class Calendar(BaseModel):
    year: int
    month: int
    days: List[CalendarDay]


class NextReviewAction(BaseModel):
    completed: int
    total: int
    next_key: Optional[str] = None
    is_activated: bool
    trades_until_review: int


class RecentTrade(BaseModel):
    id: int
    trade_date: Optional[str] = None
    asset: Optional[str] = None
    session: Optional[str] = None
    setup_type: Optional[str] = None
    result: Optional[str] = None
    pnl: Optional[float] = None
    rr_realized: Optional[float] = None


class OverviewResponse(BaseModel):
    period: Period
    sample: SampleFlags
    kpi: Kpi
    risk: Risk
    trajectory: Trajectory
    recurring_edge: RecurringEdge
    calendar: Calendar
    next_review_action: NextReviewAction
    recent_trades: List[RecentTrade]
```

- [ ] **Step 5: Write the router**

```python
# src/tradelens/api/routers/overview.py
"""The Overview endpoint.

Thin by design: validate the period, call the service with the session's owner,
return. All arithmetic lives in `services/overview`, and all ownership lives in
the services beneath it.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query

from src.tradelens.api.deps import current_user
from src.tradelens.api.schemas.overview import OverviewResponse
from src.tradelens.api.serialization import to_jsonable
from src.tradelens.services.overview import build_overview

router = APIRouter(prefix="/v1", tags=["overview"])


def _validated_period(start: str, end: str) -> tuple:
    """Parse and order the range, or refuse it.

    The HMAC already covers the query, so this cannot be edited in transit —
    but an authenticated caller can still send a range that means nothing, and
    a window nothing can render is worse than a refusal.
    """
    try:
        first = dt.date.fromisoformat(start)
        last = dt.date.fromisoformat(end)
    except ValueError:
        raise HTTPException(status_code=422, detail="period must be two ISO dates")
    if first > last:
        raise HTTPException(status_code=422, detail="period start is after its end")
    return first.isoformat(), last.isoformat()


@router.get("/overview")
def get_overview(
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    user_id: int = Depends(current_user),
) -> OverviewResponse:
    """Everything the Overview screen shows, for the authenticated owner.

    The owner is the session row's. Nothing in the query, the headers, or the
    body can name a different account.
    """
    start, end = _validated_period(from_, to)
    payload = to_jsonable(build_overview(user_id=user_id, start=start, end=end))
    payload["period"] = {"from_": start, "to": end}
    return OverviewResponse.model_validate(payload)
```

- [ ] **Step 6: Register the router**

In `src/tradelens/api/app.py`, import the new router alongside the session one and add
`app.include_router(overview.router)` next to the existing `include_router` call.

- [ ] **Step 7: Run the tests, regenerate the contract, commit**

```bash
/Users/ayoub/tradelens-ai/.venv/bin/pytest tests/test_api_overview.py -q
/Users/ayoub/tradelens-ai/.venv/bin/python scripts/generate_openapi.py
cd web && npm run api:types && cd ..
/Users/ayoub/tradelens-ai/.venv/bin/pytest tests/ -q
/Users/ayoub/tradelens-ai/.venv/bin/ruff check src/ scripts/ && /Users/ayoub/tradelens-ai/.venv/bin/black --check src/ scripts/ tests/
git add -A
git commit -m "feat(api): GET /v1/overview

One endpoint returning the whole Overview, because the page is a server
component that renders once — eight endpoints would be eight round trips
for one screen.

Typed with a Pydantic model rather than a dict: a dict generates
{[key: string]: unknown} and the drift gate would then protect nothing.

The period is validated server-side even though the HMAC already binds the
query. Being authenticated is not the same as being meaningful."
```

**GROUP A REVIEW — deep, independent.** Ownership at every service call; the owner deriving
only from the session row; cross-owner isolation; period validation; the typed contract; that
`services/metrics` was not modified; that the parity snapshot is unchanged.

---

# GROUP B — The Next.js data layer

*Deep independent review at the group boundary: it crosses the security boundary.*

### Task B1: Server-side Overview fetch

**Files:**
- Create: `web/lib/app/overview.ts`
- Test: `web/__tests__/overview-fetch.test.ts`

**Interfaces:**
- Consumes: `callApi` from `@/lib/api/client`; `periodToParams` from `@/lib/app/period`
- Produces: `fetchOverview(sessionToken: string, period: Period): Promise<OverviewResponse>`; the `OverviewResponse` type re-exported from the generated schema

- [ ] **Step 1: Write the failing test**

```typescript
// web/__tests__/overview-fetch.test.ts
import "@testing-library/jest-dom/vitest";
import { describe, expect, it, vi, beforeEach } from "vitest";

const callApi = vi.fn();
vi.mock("@/lib/api/client", () => ({ callApi: (...a: unknown[]) => callApi(...a) }));

import { fetchOverview } from "@/lib/app/overview";

beforeEach(() => callApi.mockReset());

describe("fetchOverview", () => {
  it("asks for the period it was given", async () => {
    callApi.mockResolvedValue({ kpi: { trades: 0 } });
    await fetchOverview("tok", { from: "2026-08-01", to: "2026-08-31", presetId: "custom" });
    const [path, token, init] = callApi.mock.calls[0];
    expect(path).toBe("/v1/overview");
    expect(token).toBe("tok");
    expect(init.query).toContain("from=2026-08-01");
    expect(init.query).toContain("to=2026-08-31");
  });

  it("sends the session token, never a user id", () => {
    // The API derives the owner from the session row. A caller that could name
    // an account would defeat the whole boundary.
    const source = String(fetchOverview);
    expect(source).not.toMatch(/user_?[Ii]d/);
  });

  it("passes the payload through untouched", async () => {
    const payload = { kpi: { trades: 5, net_pnl: 575 } };
    callApi.mockResolvedValue(payload);
    await expect(
      fetchOverview("tok", { from: "2026-08-01", to: "2026-08-31", presetId: "custom" }),
    ).resolves.toBe(payload);
  });

  it("lets an API error propagate rather than returning empty data", async () => {
    // Swallowing this would render an Overview of zeros — indistinguishable
    // from a trader who had a flat month.
    callApi.mockRejectedValue(new Error("boom"));
    await expect(
      fetchOverview("tok", { from: "2026-08-01", to: "2026-08-31", presetId: "custom" }),
    ).rejects.toThrow();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run __tests__/overview-fetch.test.ts`
Expected: FAIL — cannot resolve `@/lib/app/overview`

- [ ] **Step 3: Implement**

```typescript
// web/lib/app/overview.ts
import "server-only";

import { callApi } from "@/lib/api/client";
import { periodToParams, type Period } from "@/lib/app/period";
import type { components } from "@/lib/api/schema";

/**
 * The Overview payload, typed from the generated OpenAPI schema so the shape
 * cannot drift from what the backend actually returns.
 */
export type OverviewResponse = components["schemas"]["OverviewResponse"];

/**
 * Fetch the Overview for the authenticated owner.
 *
 * Server-only. The session token is forwarded to `callApi`, which hashes it
 * into the domain-separated handle — the raw credential never leaves Next.js.
 * Nothing here names an account: the API derives the owner from the session
 * row, and a caller that could pass a user id would defeat that.
 *
 * Errors are not caught. An Overview of zeros is indistinguishable from a
 * trader who had a flat month, so a failed fetch must reach the route's error
 * boundary rather than be rendered as data.
 */
export async function fetchOverview(
  sessionToken: string,
  period: Period,
): Promise<OverviewResponse> {
  return callApi<OverviewResponse>("/v1/overview", sessionToken, {
    query: periodToParams(period).toString(),
  });
}
```

- [ ] **Step 4: Run the test, typecheck, commit**

```bash
cd web && npx vitest run __tests__/overview-fetch.test.ts && npx tsc --noEmit && npx eslint . && cd ..
git add -A
git commit -m "feat(app): server-side Overview fetch

Typed from the generated schema, so the client shape cannot drift from
what the backend returns. Errors propagate deliberately: an Overview of
zeros looks exactly like a flat month, so a failed fetch belongs in the
error boundary, not on the screen."
```

---

### Task B2: Route boundaries and page wiring

**Files:**
- Modify: `web/app/app/page.tsx`
- Create: `web/app/app/loading.tsx`, `web/app/app/error.tsx`
- Test: `web/__tests__/overview-page-boundaries.test.tsx`

**Interfaces:**
- Consumes: `fetchOverview` (B1); `LoadingState`, `ErrorState` from Phase 1
- Produces: `/app` renders the Overview; the route has loading and error boundaries

- [ ] **Step 1: Write the failing test**

```tsx
// web/__tests__/overview-page-boundaries.test.tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import Loading from "@/app/app/loading";
import ErrorBoundary from "@/app/app/error";

describe("route boundaries", () => {
  it("the loading state says what is loading", () => {
    render(<Loading />);
    expect(screen.getByRole("status")).toHaveTextContent(/overview/i);
  });

  it("the error boundary offers a way out", () => {
    const reset = vi.fn();
    render(<ErrorBoundary error={new Error("x")} reset={reset} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    screen.getByRole("button", { name: /try again/i }).click();
    expect(reset).toHaveBeenCalled();
  });

  it("the error boundary does not leak the underlying message", () => {
    // A backend error string can carry internals a trader should not see.
    render(<ErrorBoundary error={new Error("connection refused at 10.0.0.4")} reset={() => {}} />);
    expect(screen.getByRole("alert").textContent).not.toContain("10.0.0.4");
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run __tests__/overview-page-boundaries.test.tsx`
Expected: FAIL — cannot resolve `@/app/app/loading`

- [ ] **Step 3: Write the boundaries**

```tsx
// web/app/app/loading.tsx
import { LoadingState } from "@/components/app/states/loading-state";

export default function Loading() {
  return <LoadingState label="Loading your overview" />;
}
```

```tsx
// web/app/app/error.tsx
"use client";

import { ErrorState } from "@/components/app/states/error-state";

/**
 * The route's error boundary.
 *
 * The underlying message is deliberately not shown: a backend failure string
 * can carry hosts, queries, or internals, and none of it helps a trader decide
 * what to do next.
 */
export default function OverviewError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto max-w-6xl pt-6">
      <ErrorState
        title="Your overview did not load"
        description="The figures could not be fetched just now. Nothing in your journal has changed."
        retry={{ onRetry: reset }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Wire the page**

```tsx
// web/app/app/page.tsx
import { headers } from "next/headers";

import { sessionTokenFromCookieHeader } from "@/lib/auth/session";
import { fetchOverview } from "@/lib/app/overview";
import { periodFromParams } from "@/lib/app/period";
import { OverviewSections } from "@/components/app/overview/sections";

export const dynamic = "force-dynamic";

/**
 * The Overview.
 *
 * A Server Component: one server-to-server call, rendered once. The layout has
 * already established that this request has a session and that the account is
 * opted in, so the token is read here only to forward it.
 */
export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = new URLSearchParams(
    Object.entries(await searchParams).flatMap(([k, v]) =>
      typeof v === "string" ? [[k, v] as [string, string]] : [],
    ),
  );
  const period = periodFromParams(params);
  const token = sessionTokenFromCookieHeader((await headers()).get("cookie"));
  const data = await fetchOverview(token ?? "", period);

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="font-display text-3xl font-bold">Overview</h1>
      <p className="mt-2 text-muted">Where the week stands, and what deserves review next.</p>
      <OverviewSections data={data} />
    </div>
  );
}
```

- [ ] **Step 5: Run the tests**

Run: `cd web && npx vitest run __tests__/overview-page-boundaries.test.tsx`
Expected: PASS. `OverviewSections` does not exist until Group E — do NOT run `npm run build`
or `tsc` in this task; Task E3 runs them once every section exists.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(app): Overview route boundaries and page wiring

The page is a server component making one call. loading.tsx and error.tsx
finally give the Phase 1 loading and error primitives real callers.

The error boundary shows its own copy rather than the underlying message,
which can carry hosts or queries and helps a trader with nothing."
```

**GROUP B REVIEW — deep, independent.** That the raw token never reaches the API; that no user
id is sent; that errors are not swallowed into empty data; that the error boundary leaks
nothing.

---

# GROUP C — KPI row and risk/discipline

*Light review at the group boundary. Presentation; no mutation testing.*

### Task C1: The stat tile and the KPI row

**Files:**
- Create: `web/components/app/overview/stat-tile.tsx`, `web/components/app/overview/kpi-row.tsx`
- Test: `web/__tests__/overview-kpi.test.tsx`

**Interfaces:**
- Consumes: `OverviewResponse` (B1)
- Produces: `<StatTile label value hint? tone? />` where `tone?: "positive" | "negative" | "neutral"`; `<KpiRow kpi sample />`

- [ ] **Step 1: Write the test**

```tsx
// web/__tests__/overview-kpi.test.tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatTile } from "@/components/app/overview/stat-tile";
import { KpiRow } from "@/components/app/overview/kpi-row";

const kpi = {
  net_pnl: 575, win_rate: 0.4, expectancy: 115, expectancy_state: null,
  profit_factor: 2.9, profit_factor_state: null, trades: 5, wins: 2, losses: 2,
  today_pnl: 0, week_pnl: 575,
};
const sample = {
  trades: 5, dated_points: 5, show_summary: true, show_series: true,
  show_dominant_series: true, show_comparisons: true, show_patterns: true,
};

describe("stat tile", () => {
  it("shows its label and value", () => {
    render(<StatTile label="Net P&L" value="$575.00" />);
    expect(screen.getByText("Net P&L")).toBeInTheDocument();
    expect(screen.getByText("$575.00")).toBeInTheDocument();
  });

  it("carries the sign in the text, not only in colour", () => {
    // Green and red are ΔE 2.3 apart for a deuteranope — colour alone is not a
    // distinction for a large share of readers.
    render(<StatTile label="Net P&L" value="-$220.00" tone="negative" />);
    expect(screen.getByText("-$220.00")).toBeInTheDocument();
  });
});

describe("kpi row", () => {
  it("shows the five headline figures", () => {
    render(<KpiRow kpi={kpi} sample={sample} />);
    for (const label of ["Net P&L", "Win rate", "Expectancy", "Profit factor", "Trades"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("names an undefined profit factor instead of printing a number", () => {
    render(
      <KpiRow
        kpi={{ ...kpi, profit_factor: null, profit_factor_state: "undefined_positive_infinity" }}
        sample={sample}
      />,
    );
    expect(screen.getByText(/no losses yet/i)).toBeInTheDocument();
  });

  it("says the sample is too small rather than showing confident figures", () => {
    render(<KpiRow kpi={{ ...kpi, trades: 0 }} sample={{ ...sample, trades: 0, show_summary: false }} />);
    expect(screen.getByText(/no trades in this period/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run __tests__/overview-kpi.test.tsx`
Expected: FAIL — cannot resolve `@/components/app/overview/stat-tile`

- [ ] **Step 3: Implement the tile**

```tsx
// web/components/app/overview/stat-tile.tsx
/**
 * One figure, its label, and an optional line of context.
 *
 * Tone tints the value, but never carries meaning alone: the sign lives in the
 * text. Measured against a dark surface, the positive and negative tokens are
 * ΔE 2.3 apart under deuteranopia — indistinguishable to the most common
 * colour-vision deficiency, and obviously different to everyone else, which is
 * how that ships unnoticed.
 */
export function StatTile({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "positive" | "negative" | "neutral";
}) {
  const toneClass =
    tone === "positive" ? "text-positive" : tone === "negative" ? "text-negative" : "text-text";
  return (
    <div className="border-l border-line px-4 py-3 first:border-l-0 first:pl-0">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</div>
      <div className={`mt-1 font-mono text-xl ${toneClass}`}>{value}</div>
      {hint && <div className="mt-0.5 font-mono text-[11px] text-muted">{hint}</div>}
    </div>
  );
}
```

- [ ] **Step 4: Implement the KPI row**

```tsx
// web/components/app/overview/kpi-row.tsx
import { StatTile } from "@/components/app/overview/stat-tile";
import { EmptyState } from "@/components/app/states/empty-state";
import type { OverviewResponse } from "@/lib/app/overview";

const money = (n: number) =>
  `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** Why a figure has no number, in words a trader can act on. */
function undefinedReason(state: string | null | undefined): string {
  if (state === "undefined_positive_infinity") return "No losses yet";
  if (state === "undefined_negative_infinity") return "No wins yet";
  return "Not enough data";
}

export function KpiRow({
  kpi,
  sample,
}: {
  kpi: OverviewResponse["kpi"];
  sample: OverviewResponse["sample"];
}) {
  if (!sample.show_summary) {
    return (
      <EmptyState
        title="No trades in this period"
        description="Widen the period, or log a completed trade to start the record."
        action={{ href: "/app/trades/new", label: "Log completed trade" }}
      />
    );
  }

  const tone = (n: number) => (n > 0 ? "positive" : n < 0 ? "negative" : "neutral") as const;

  return (
    <div className="grid grid-cols-2 rounded-xl border border-line bg-surface p-4 sm:grid-cols-3 lg:grid-cols-5">
      <StatTile
        label="Net P&L"
        value={money(kpi.net_pnl)}
        hint={`${kpi.trades} ${kpi.trades === 1 ? "trade" : "trades"}`}
        tone={tone(kpi.net_pnl)}
      />
      <StatTile
        label="Win rate"
        value={kpi.win_rate === null || kpi.win_rate === undefined ? "—" : `${(kpi.win_rate * 100).toFixed(1)}%`}
        hint={`${kpi.wins} of ${kpi.trades}`}
      />
      <StatTile
        label="Expectancy"
        value={kpi.expectancy === null ? "—" : money(kpi.expectancy)}
        hint={kpi.expectancy === null ? undefinedReason(kpi.expectancy_state) : "per trade"}
        tone={kpi.expectancy === null ? "neutral" : tone(kpi.expectancy)}
      />
      <StatTile
        label="Profit factor"
        value={kpi.profit_factor === null ? "—" : `${kpi.profit_factor.toFixed(2)}x`}
        hint={kpi.profit_factor === null ? undefinedReason(kpi.profit_factor_state) : undefined}
      />
      <StatTile label="Trades" value={String(kpi.trades)} hint={`${kpi.losses} losing`} />
    </div>
  );
}
```

- [ ] **Step 5: Run the tests and commit**

```bash
cd web && npx vitest run __tests__/overview-kpi.test.tsx && npx eslint . && cd ..
git add -A
git commit -m "feat(app): KPI row

An undefined profit factor reads 'No losses yet' rather than a number.
Tone tints a value but never carries meaning alone — the positive and
negative tokens are ΔE 2.3 apart under deuteranopia, so the sign lives in
the text."
```

---

### Task C2: Risk and discipline

**Files:**
- Create: `web/components/app/overview/risk-discipline.tsx`
- Test: `web/__tests__/overview-risk.test.tsx`

**Interfaces:**
- Consumes: `StatTile` (C1); `OverviewResponse["risk"]`
- Produces: `<RiskDiscipline risk sample />`

- [ ] **Step 1: Write the test**

```tsx
// web/__tests__/overview-risk.test.tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RiskDiscipline } from "@/components/app/overview/risk-discipline";

const risk = {
  max_drawdown: { value: -220, state: null },
  rule_adherence: { rate: 0.67, followed: 2, recorded: 3 },
  edge_leak: { amount: -220, trades: 1, recorded: 3 },
  consistency: { value: null, state: "undefined_nan" },
};
const sample = {
  trades: 5, dated_points: 5, show_summary: true, show_series: true,
  show_dominant_series: true, show_comparisons: true, show_patterns: true,
};

describe("risk and discipline", () => {
  it("asks whether the numbers describe a process or a run of luck", () => {
    render(<RiskDiscipline risk={risk} sample={sample} />);
    expect(screen.getByText(/Risk and discipline/i)).toBeInTheDocument();
    for (const label of ["Max drawdown", "Rule adherence", "Edge leak", "Consistency"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("shows adherence as a rate with its sample size", () => {
    render(<RiskDiscipline risk={risk} sample={sample} />);
    expect(screen.getByText("67%")).toBeInTheDocument();
    expect(screen.getByText(/2 of 3/)).toBeInTheDocument();
  });

  it("says a consistency score is not yet earned rather than showing zero", () => {
    render(<RiskDiscipline risk={risk} sample={sample} />);
    expect(screen.getByText(/not yet/i)).toBeInTheDocument();
  });

  it("renders nothing measurable when the sample has not earned it", () => {
    render(<RiskDiscipline risk={risk} sample={{ ...sample, show_summary: false }} />);
    expect(screen.queryByText("Max drawdown")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run __tests__/overview-risk.test.tsx`
Expected: FAIL — cannot resolve the module

- [ ] **Step 3: Implement**

```tsx
// web/components/app/overview/risk-discipline.tsx
import { StatTile } from "@/components/app/overview/stat-tile";
import type { OverviewResponse } from "@/lib/app/overview";

const money = (n: number) =>
  `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/**
 * Whether the headline numbers describe a process or a run of luck.
 *
 * A score the sample has not earned reads "Not yet" rather than a figure. A
 * consistency of 0.0 and a consistency that cannot yet be computed look
 * identical on screen and mean opposite things.
 */
export function RiskDiscipline({
  risk,
  sample,
}: {
  risk: OverviewResponse["risk"];
  sample: OverviewResponse["sample"];
}) {
  if (!sample.show_summary) return null;

  const adherence = risk.rule_adherence;
  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Risk and discipline</h2>
      <p className="mt-1 text-sm text-muted">
        Whether the numbers above describe a process or a run of luck.
      </p>
      <div className="mt-4 grid grid-cols-2 rounded-xl border border-line bg-surface p-4 lg:grid-cols-4">
        <StatTile
          label="Max drawdown"
          value={risk.max_drawdown.value === null ? "—" : money(risk.max_drawdown.value)}
          hint={`${sample.dated_points} trading ${sample.dated_points === 1 ? "day" : "days"}`}
          tone={risk.max_drawdown.value && risk.max_drawdown.value < 0 ? "negative" : "neutral"}
        />
        <StatTile
          label="Rule adherence"
          value={adherence.rate === null ? "—" : `${Math.round(adherence.rate * 100)}%`}
          hint={`${adherence.followed} of ${adherence.recorded}`}
        />
        <StatTile
          label="Edge leak"
          value={money(risk.edge_leak.amount)}
          hint={`${risk.edge_leak.trades} of ${risk.edge_leak.recorded} recorded`}
          tone={risk.edge_leak.amount < 0 ? "negative" : "neutral"}
        />
        <StatTile
          label="Consistency"
          value={risk.consistency.value === null ? "Not yet" : risk.consistency.value.toFixed(0)}
          hint={risk.consistency.value === null ? "More trades needed to score it" : "out of 100"}
        />
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run the tests and commit**

```bash
cd web && npx vitest run __tests__/overview-risk.test.tsx && npx eslint . && cd ..
git add -A
git commit -m "feat(app): risk and discipline section

A consistency score the sample has not earned reads 'Not yet'. Zero and
not-yet-computable look identical on screen and mean opposite things."
```

**GROUP C REVIEW — light.** Copy quality, the undefined states, and that nothing distinguishes
by colour alone.

---

# GROUP D — Trajectory, recurring edge, calendar

*Light review, except the chart-geometry tests, which are TDD'd like data.*

### Task D1: The equity curve

**Files:**
- Create: `web/components/app/overview/equity-curve.tsx`
- Test: `web/__tests__/equity-curve.test.tsx`

**Interfaces:**
- Consumes: `OverviewResponse["trajectory"]["equity_curve"]`
- Produces: `<EquityCurve points sample />`; `buildCurvePath(points, width, height): { line: string; area: string }`

- [ ] **Step 1: Write the test — the geometry is data, so it is tested first**

```tsx
// web/__tests__/equity-curve.test.tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EquityCurve, buildCurvePath } from "@/components/app/overview/equity-curve";

const points = [
  { date: "2026-08-10", equity: 480 },
  { date: "2026-08-11", equity: 260 },
  { date: "2026-08-12", equity: 670 },
  { date: "2026-08-14", equity: 575 },
];
const earned = { show_series: true, show_dominant_series: true, dated_points: 4 };

describe("curve geometry", () => {
  it("maps the first point to the left edge and the last to the right", () => {
    const { line } = buildCurvePath(points, 100, 40);
    expect(line.startsWith("M0")).toBe(true);
    expect(line).toContain("L100");
  });

  it("puts the highest equity above the lowest on screen", () => {
    // SVG y grows downward, so the maximum must have the SMALLER y.
    const { line } = buildCurvePath(points, 100, 40);
    const ys = [...line.matchAll(/[ML]([\d.]+),([\d.]+)/g)].map((m) => Number(m[2]));
    expect(ys[2]).toBeLessThan(ys[1]); // 670 is above 260
  });

  it("closes the area path back to the baseline", () => {
    const { area } = buildCurvePath(points, 100, 40);
    expect(area.endsWith("Z")).toBe(true);
  });

  it("survives a flat curve without dividing by zero", () => {
    const flat = [
      { date: "2026-08-10", equity: 100 },
      { date: "2026-08-11", equity: 100 },
    ];
    const { line } = buildCurvePath(flat, 100, 40);
    expect(line).not.toContain("NaN");
  });

  it("survives a single point", () => {
    const { line } = buildCurvePath([{ date: "2026-08-10", equity: 5 }], 100, 40);
    expect(line).not.toContain("NaN");
  });
});

describe("equity curve", () => {
  it("draws the curve when the sample has earned it", () => {
    const { container } = render(<EquityCurve points={points} sample={earned} />);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("explains itself instead of drawing a line from two points", () => {
    render(
      <EquityCurve points={points.slice(0, 2)} sample={{ ...earned, show_dominant_series: false, dated_points: 2 }} />,
    );
    expect(screen.getByText(/not enough dated trades/i)).toBeInTheDocument();
    expect(screen.getByText(/2 more trading days/i)).toBeInTheDocument();
  });

  it("labels the curve so identity is never colour alone", () => {
    render(<EquityCurve points={points} sample={earned} />);
    expect(screen.getByText(/\$575/)).toBeInTheDocument();
  });

  it("gives the chart an accessible description", () => {
    render(<EquityCurve points={points} sample={earned} />);
    expect(screen.getByRole("img", { name: /equity/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run __tests__/equity-curve.test.tsx`
Expected: FAIL — cannot resolve the module

- [ ] **Step 3: Implement**

```tsx
// web/components/app/overview/equity-curve.tsx
import type { OverviewResponse } from "@/lib/app/overview";

type Point = { date: string; equity: number };

/**
 * Map equity points into an SVG line and its closed area.
 *
 * Exported because the geometry is data, not decoration: an inverted y axis or
 * a divide-by-zero on a flat curve is a wrong picture, and a wrong picture of
 * an account is worse than no picture.
 */
export function buildCurvePath(points: Point[], width: number, height: number) {
  if (points.length === 0) return { line: "", area: "" };

  const values = points.map((p) => p.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  // A flat curve has no range; centre it rather than dividing by zero.
  const span = max - min || 1;
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;

  const coords = points.map((p, i) => {
    const x = points.length > 1 ? i * stepX : width / 2;
    // SVG y grows downward, so the largest value gets the smallest y.
    const y = height - ((p.equity - min) / span) * height;
    return `${Number(x.toFixed(2))},${Number(y.toFixed(2))}`;
  });

  const line = `M${coords[0]}` + coords.slice(1).map((c) => `L${c}`).join("");
  const area = `${line}L${Number((points.length > 1 ? width : width / 2).toFixed(2))},${height}L${points.length > 1 ? 0 : Number((width / 2).toFixed(2))},${height}Z`;
  return { line, area };
}

const money = (n: number) =>
  `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

/**
 * The account's path through the period.
 *
 * One series, so no legend — the title names it and the end value is labelled.
 * The line takes a status colour rather than the brand accent: teal means
 * "act" everywhere else in this product, and an equity line is not an action.
 */
export function EquityCurve({
  points,
  sample,
}: {
  points: Point[];
  sample: Pick<OverviewResponse["sample"], "show_dominant_series" | "dated_points">;
}) {
  const MIN_POINTS = 4;
  if (!sample.show_dominant_series) {
    const needed = MIN_POINTS - sample.dated_points;
    return (
      <div className="rounded-xl border border-line bg-surface p-6">
        <p className="text-sm font-medium text-text">Not enough dated trades for a curve</p>
        <p className="mt-1 max-w-sm text-sm text-muted">
          {needed} more trading {needed === 1 ? "day" : "days"} will unlock the equity curve. The
          figures above already reflect every trade logged.
        </p>
      </div>
    );
  }

  const W = 720;
  const H = 180;
  const { line, area } = buildCurvePath(points, W, H);
  const last = points[points.length - 1]?.equity ?? 0;
  const up = last >= 0;
  const stroke = up ? "#22c55e" : "#f56565";

  return (
    <figure className="rounded-xl border border-line bg-chart p-4">
      <figcaption className="flex items-baseline justify-between">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          Equity curve
        </span>
        <span className={`font-mono text-sm ${up ? "text-positive" : "text-negative"}`}>
          {money(last)}
        </span>
      </figcaption>
      <svg
        role="img"
        aria-label={`Equity curve over ${points.length} trading days, ending at ${money(last)}`}
        viewBox={`0 0 ${W} ${H}`}
        className="mt-3 h-44 w-full"
        preserveAspectRatio="none"
      >
        <path d={area} fill={stroke} fillOpacity="0.08" />
        <path d={line} fill="none" stroke={stroke} strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <p className="mt-2 font-mono text-[11px] text-muted">
        n={points.length} trading days
        {points.length < 5 ? " · small sample, 5 needed to read a pattern" : ""}
      </p>
    </figure>
  );
}
```

- [ ] **Step 4: Run the tests and commit**

```bash
cd web && npx vitest run __tests__/equity-curve.test.tsx && npx eslint . && cd ..
git add -A
git commit -m "feat(app): equity curve

Geometry is exported and tested because it is data: an inverted axis or a
divide-by-zero on a flat curve is a wrong picture of an account.

One series, so no legend — the title names it and the end value is
labelled. The line takes a status colour rather than the accent, since
teal means 'act' everywhere else and a curve is not an action."
```

---

### Task D2: Trajectory and recurring edge

**Files:**
- Create: `web/components/app/overview/trajectory.tsx`, `web/components/app/overview/recurring-edge.tsx`
- Test: `web/__tests__/overview-trajectory.test.tsx`

**Interfaces:**
- Consumes: `EquityCurve` (D1); `StatTile` (C1)
- Produces: `<Trajectory trajectory sample />`, `<RecurringEdge edge sample />`

- [ ] **Step 1: Write the test**

```tsx
// web/__tests__/overview-trajectory.test.tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Trajectory } from "@/components/app/overview/trajectory";
import { RecurringEdge } from "@/components/app/overview/recurring-edge";

const trajectory = {
  equity_curve: [
    { date: "2026-08-10", equity: 480 },
    { date: "2026-08-11", equity: 260 },
    { date: "2026-08-12", equity: 670 },
    { date: "2026-08-14", equity: 575 },
  ],
  current_streak: 1,
  streak_type: "win",
  best_streak: 1,
  worst_streak: 1,
  average_win: { value: 445, state: null },
  average_loss: { value: -157.5, state: null },
};
const sample = {
  trades: 5, dated_points: 4, show_summary: true, show_series: true,
  show_dominant_series: true, show_comparisons: true, show_patterns: true,
};

describe("trajectory", () => {
  it("shows the path the account took", () => {
    render(<Trajectory trajectory={trajectory} sample={sample} />);
    expect(screen.getByText(/Performance trajectory/i)).toBeInTheDocument();
    expect(screen.getByText("Average win")).toBeInTheDocument();
    expect(screen.getByText("Average loss")).toBeInTheDocument();
  });
});

describe("recurring edge", () => {
  it("shows where the account repeats itself, with sample sizes", () => {
    render(
      <RecurringEdge
        edge={{
          killzones: [{ label: "NY AM", net_pnl: 670, trades: 3 }],
          setups: [{ label: "Liquidity Sweep + FVG", net_pnl: 670, trades: 3 }],
        }}
        sample={sample}
      />,
    );
    expect(screen.getByText("NY AM")).toBeInTheDocument();
    expect(screen.getByText("Liquidity Sweep + FVG")).toBeInTheDocument();
    expect(screen.getAllByText(/n=3/).length).toBeGreaterThan(0);
  });

  it("withholds comparisons the sample has not earned", () => {
    render(
      <RecurringEdge
        edge={{ killzones: [{ label: "NY AM", net_pnl: 1, trades: 1 }], setups: [] }}
        sample={{ ...sample, show_comparisons: false }}
      />,
    );
    expect(screen.queryByText("NY AM")).not.toBeInTheDocument();
    expect(screen.getByText(/not enough trades to compare/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run __tests__/overview-trajectory.test.tsx`
Expected: FAIL — cannot resolve the modules

- [ ] **Step 3: Implement trajectory**

```tsx
// web/components/app/overview/trajectory.tsx
import { EquityCurve } from "@/components/app/overview/equity-curve";
import { StatTile } from "@/components/app/overview/stat-tile";
import type { OverviewResponse } from "@/lib/app/overview";

const money = (n: number) =>
  `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** The path the account took to get here. */
export function Trajectory({
  trajectory,
  sample,
}: {
  trajectory: OverviewResponse["trajectory"];
  sample: OverviewResponse["sample"];
}) {
  if (!sample.show_summary) return null;

  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Performance trajectory</h2>
      <p className="mt-1 text-sm text-muted">The path the account took to get here.</p>
      <div className="mt-4 grid gap-4 lg:grid-cols-[2fr_1fr]">
        <EquityCurve points={trajectory.equity_curve} sample={sample} />
        <div className="grid grid-cols-2 gap-x-2 rounded-xl border border-line bg-surface p-4 lg:grid-cols-1 lg:gap-y-2">
          <StatTile
            label="Current streak"
            value={trajectory.current_streak === null ? "—" : String(trajectory.current_streak)}
            hint="most recent first"
          />
          <StatTile
            label="Best run"
            value={trajectory.best_streak === null ? "—" : String(trajectory.best_streak)}
            hint={trajectory.worst_streak === null ? undefined : `longest losing run ${trajectory.worst_streak}`}
          />
          <StatTile
            label="Average win"
            value={trajectory.average_win.value === null ? "—" : money(trajectory.average_win.value)}
            tone={trajectory.average_win.value === null ? "neutral" : "positive"}
          />
          <StatTile
            label="Average loss"
            value={trajectory.average_loss.value === null ? "—" : money(trajectory.average_loss.value)}
            tone={trajectory.average_loss.value === null ? "neutral" : "negative"}
          />
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Implement recurring edge**

```tsx
// web/components/app/overview/recurring-edge.tsx
import type { OverviewResponse } from "@/lib/app/overview";

const money = (n: number) =>
  `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function Breakdown({ title, rows }: { title: string; rows: OverviewResponse["recurring_edge"]["killzones"] }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{title}</h3>
      <ul className="mt-3 space-y-2">
        {rows.length === 0 && <li className="text-sm text-muted">Nothing recorded yet.</li>}
        {rows.map((row) => (
          <li key={row.label} className="flex items-baseline justify-between gap-4">
            <span className="min-w-0 truncate text-sm text-text">
              {row.label}
              <span className="ml-2 font-mono text-[11px] text-muted">n={row.trades}</span>
            </span>
            <span
              className={`shrink-0 font-mono text-sm ${row.net_pnl > 0 ? "text-positive" : row.net_pnl < 0 ? "text-negative" : "text-text"}`}
            >
              {money(row.net_pnl)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Where the account repeats itself, and how large the sample is.
 *
 * The sample size sits beside every row on purpose: a killzone that "wins"
 * over three trades is a sentence about three trades.
 */
export function RecurringEdge({
  edge,
  sample,
}: {
  edge: OverviewResponse["recurring_edge"];
  sample: OverviewResponse["sample"];
}) {
  if (!sample.show_summary) return null;

  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Recurring edge</h2>
      <p className="mt-1 text-sm text-muted">
        Where the account repeats itself, and how large the sample is.
      </p>
      {!sample.show_comparisons ? (
        <div className="mt-4 rounded-xl border border-line bg-surface p-6">
          <p className="text-sm text-muted">
            Not enough trades to compare sessions or setups yet. Two trades is the minimum for a
            comparison to mean anything.
          </p>
        </div>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Breakdown title="Killzone performance" rows={edge.killzones} />
          <Breakdown title="Setup performance" rows={edge.setups} />
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 5: Run the tests and commit**

```bash
cd web && npx vitest run __tests__/overview-trajectory.test.tsx && npx eslint . && cd ..
git add -A
git commit -m "feat(app): trajectory and recurring edge

Sample size sits beside every breakdown row: a killzone that wins over
three trades is a sentence about three trades, and the old app's habit of
stating that as a finding is what the low-data policy exists to stop."
```

---

### Task D3: The trading-days calendar

**Files:**
- Create: `web/components/app/overview/trading-calendar.tsx`
- Test: `web/__tests__/trading-calendar.test.tsx`

**Interfaces:**
- Consumes: `OverviewResponse["calendar"]`
- Produces: `<TradingCalendar calendar sample />`

- [ ] **Step 1: Write the test**

```tsx
// web/__tests__/trading-calendar.test.tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TradingCalendar } from "@/components/app/overview/trading-calendar";

const calendar = {
  year: 2026,
  month: 8,
  days: [
    { date: "2026-08-12", pnl: 480, outcome: "positive" },
    { date: "2026-08-13", pnl: -220, outcome: "negative" },
    { date: "2026-08-15", pnl: 410, outcome: "positive" },
  ],
};
const sample = {
  trades: 5, dated_points: 4, show_summary: true, show_series: true,
  show_dominant_series: true, show_comparisons: true, show_patterns: true,
};

describe("trading calendar", () => {
  it("names the month it is showing", () => {
    render(<TradingCalendar calendar={calendar} sample={sample} />);
    expect(screen.getByText(/August 2026/)).toBeInTheDocument();
  });

  it("marks traded days and leaves untraded ones blank", () => {
    render(<TradingCalendar calendar={calendar} sample={sample} />);
    expect(screen.getByLabelText(/12 August 2026, up \$480/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/13 August 2026, down \$220/i)).toBeInTheDocument();
    // The 14th had no trade, which is information rather than missing data.
    expect(screen.queryByLabelText(/14 August 2026, up/i)).not.toBeInTheDocument();
  });

  it("distinguishes outcome by SHAPE, not only by colour", () => {
    // The positive and negative tokens are ΔE 2.3 apart under deuteranopia.
    // Colour alone would make this calendar unreadable for those readers.
    const { container } = render(<TradingCalendar calendar={calendar} sample={sample} />);
    expect(container.querySelectorAll('[data-outcome="positive"] circle').length).toBe(2);
    expect(container.querySelectorAll('[data-outcome="negative"] rect').length).toBe(1);
  });

  it("explains itself when the month is too sparse to read", () => {
    render(
      <TradingCalendar
        calendar={{ ...calendar, days: calendar.days.slice(0, 1) }}
        sample={{ ...sample, show_dominant_series: false, dated_points: 1 }}
      />,
    );
    expect(screen.getByText(/not enough trading days/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run __tests__/trading-calendar.test.tsx`
Expected: FAIL — cannot resolve the module

- [ ] **Step 3: Implement**

```tsx
// web/components/app/overview/trading-calendar.tsx
import type { OverviewResponse } from "@/lib/app/overview";

const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"];

const money = (n: number) => `$${Math.abs(n).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

/**
 * The month's trading days.
 *
 * **Outcome is encoded by shape as well as colour.** Measured against a dark
 * surface, the positive and negative tokens are ΔE 2.3 apart under
 * deuteranopia — the same colour to the most common colour-vision deficiency,
 * and obviously different to everyone else, which is exactly how a calendar
 * like this ships unreadable. A winning day is a filled circle; a losing day
 * is a square.
 *
 * A day with no trade is left blank rather than greyed: an untraded day is
 * information, not missing data, and a sparse month is a truthful picture of a
 * sparse month.
 */
export function TradingCalendar({
  calendar,
  sample,
}: {
  calendar: OverviewResponse["calendar"];
  sample: OverviewResponse["sample"];
}) {
  if (!sample.show_summary) return null;

  const byDay = new Map(calendar.days.map((d) => [Number(d.date.slice(8, 10)), d]));
  const first = new Date(Date.UTC(calendar.year, calendar.month - 1, 1));
  const daysInMonth = new Date(Date.UTC(calendar.year, calendar.month, 0)).getUTCDate();
  // Monday-first: JS getUTCDay() is 0=Sunday.
  const leading = (first.getUTCDay() + 6) % 7;
  const cells: Array<number | null> = [
    ...Array(leading).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Trading days</h2>
      {!sample.show_dominant_series ? (
        <div className="mt-4 rounded-xl border border-line bg-surface p-6">
          <p className="text-sm text-muted">
            Not enough trading days to read a month yet. The calendar fills in as you log trades.
          </p>
        </div>
      ) : (
        <div className="mt-4 rounded-xl border border-line bg-surface p-4">
          <div className="font-mono text-sm text-text">
            {MONTHS[calendar.month - 1]} {calendar.year}
          </div>
          <div className="mt-3 grid grid-cols-7 gap-1">
            {WEEKDAYS.map((d, i) => (
              <div key={i} className="pb-1 text-center font-mono text-[10px] text-muted">{d}</div>
            ))}
            {cells.map((day, i) => {
              if (day === null) return <div key={`pad-${i}`} />;
              const entry = byDay.get(day);
              const label = entry
                ? `${day} ${MONTHS[calendar.month - 1]} ${calendar.year}, ${entry.pnl >= 0 ? "up" : "down"} ${money(entry.pnl)}`
                : undefined;
              return (
                <div
                  key={day}
                  aria-label={label}
                  data-outcome={entry?.outcome}
                  className="flex h-9 flex-col items-center justify-center rounded"
                >
                  <span className="font-mono text-[11px] text-muted">{day}</span>
                  {entry && (
                    <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true" className="mt-0.5">
                      {entry.outcome === "positive" ? (
                        <circle cx="4" cy="4" r="3" fill="#22c55e" />
                      ) : entry.outcome === "negative" ? (
                        <rect x="1" y="1" width="6" height="6" fill="#f56565" />
                      ) : (
                        <line x1="1" y1="4" x2="7" y2="4" stroke="#9aa4b2" strokeWidth="1.5" />
                      )}
                    </svg>
                  )}
                </div>
              );
            })}
          </div>
          <p className="mt-3 font-mono text-[10px] text-muted">
            ● winning day · ■ losing day · — flat. Blank days had no trade.
          </p>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Run the tests and commit**

```bash
cd web && npx vitest run __tests__/trading-calendar.test.tsx && npx eslint . && cd ..
git add -A
git commit -m "feat(app): trading-days calendar

Outcome is encoded by shape as well as colour, because the positive and
negative tokens measure ΔE 2.3 apart under deuteranopia — the same colour
to the most common colour-vision deficiency, and obviously different to
everyone else, which is how a calendar like this ships unreadable.

Untraded days are blank rather than greyed: a day with no trade is
information, and a sparse month is a truthful picture of a sparse month."
```

**GROUP D REVIEW — light, except the geometry.** Review `buildCurvePath` properly; the rest is
presentation.

---

# GROUP E — Next review action, recent trades, assembly

*Light review at the group boundary.*

### Task E1: Next review action and recent trades

**Files:**
- Create: `web/components/app/overview/next-review-action.tsx`, `web/components/app/overview/recent-trades.tsx`
- Test: `web/__tests__/overview-next-and-recent.test.tsx`

**Interfaces:**
- Consumes: `OverviewResponse["next_review_action"]`, `OverviewResponse["recent_trades"]`
- Produces: `<NextReviewAction action />`, `<RecentTrades trades />`

- [ ] **Step 1: Write the test**

```tsx
// web/__tests__/overview-next-and-recent.test.tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NextReviewAction } from "@/components/app/overview/next-review-action";
import { RecentTrades } from "@/components/app/overview/recent-trades";

describe("next review action", () => {
  it("tells the trader what to re-read, not what to trade", () => {
    render(
      <NextReviewAction
        action={{ completed: 2, total: 3, next_key: "first_review", is_activated: false, trades_until_review: 2 }}
      />,
    );
    expect(screen.getByText(/2 of 3/)).toBeInTheDocument();
    expect(screen.getByText(/2 more completed trades/i)).toBeInTheDocument();
  });

  it("says the path is complete once it is", () => {
    render(
      <NextReviewAction
        action={{ completed: 3, total: 3, next_key: null, is_activated: true, trades_until_review: 0 }}
      />,
    );
    expect(screen.getByText(/nothing waiting/i)).toBeInTheDocument();
  });
});

describe("recent trades", () => {
  const trades = [
    { id: 3, trade_date: "2026-08-15", asset: "NQ", session: "New York Open", setup_type: "Liquidity Sweep + FVG", result: "Win", pnl: 410, rr_realized: 2.7 },
    { id: 2, trade_date: "2026-08-13", asset: "ES", session: "New York Open", setup_type: "Liquidity Sweep + FVG", result: "Loss", pnl: -220, rr_realized: null },
  ];

  it("lists the most recent trades with their outcome in text", () => {
    render(<RecentTrades trades={trades} />);
    expect(screen.getByText("NQ")).toBeInTheDocument();
    expect(screen.getByText("Win")).toBeInTheDocument();
    expect(screen.getByText("Loss")).toBeInTheDocument();
  });

  it("shows a dash where an R multiple was never recorded", () => {
    render(<RecentTrades trades={trades} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("invites the first trade when there are none", () => {
    render(<RecentTrades trades={[]} />);
    expect(screen.getByRole("link", { name: /log completed trade/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run __tests__/overview-next-and-recent.test.tsx`
Expected: FAIL — cannot resolve the modules

- [ ] **Step 3: Implement both**

```tsx
// web/components/app/overview/next-review-action.tsx
import Link from "next/link";

import type { OverviewResponse } from "@/lib/app/overview";

const STEP_COPY: Record<string, { title: string; body: string }> = {
  strategy_profile: {
    title: "Write down your strategy",
    body: "Reviews are read against your own rules, so they need the rules first.",
  },
  first_trade: {
    title: "Log your first completed trade",
    body: "The journal starts with one trade you have already closed.",
  },
  first_review: {
    title: "Review your first useful sample",
    body: "A few more completed trades and the weekly review has something true to say.",
  },
};

/** What to go and re-read, not what to trade. */
export function NextReviewAction({ action }: { action: OverviewResponse["next_review_action"] }) {
  const step = action.next_key ? STEP_COPY[action.next_key] : undefined;

  return (
    <section className="mt-10">
      <h2 className="font-display text-xl font-bold">Next review action</h2>
      <p className="mt-1 text-sm text-muted">What to go and re-read, not what to trade.</p>
      <div className="mt-4 rounded-xl border border-line bg-surface p-5">
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-accent">
          {action.completed} of {action.total} done
        </div>
        {step ? (
          <>
            <p className="mt-2 font-medium text-text">{step.title}</p>
            <p className="mt-1 text-sm text-muted">
              {action.next_key === "first_review" && action.trades_until_review > 0
                ? `${action.trades_until_review} more completed trades to unlock it.`
                : step.body}
            </p>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted">
            Nothing waiting — the activation path is complete. Keep logging and the weekly review
            keeps getting more to work with.
          </p>
        )}
        <Link href="/app/reviews" className="mt-4 inline-block text-sm text-accent hover:underline">
          Open AI Reviews →
        </Link>
      </div>
    </section>
  );
}
```

```tsx
// web/components/app/overview/recent-trades.tsx
import Link from "next/link";

import { EmptyState } from "@/components/app/states/empty-state";
import type { OverviewResponse } from "@/lib/app/overview";

const money = (n: number | null | undefined) =>
  n === null || n === undefined
    ? "—"
    : `${n < 0 ? "-" : ""}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** The last few trades. Outcome is a word, so it never depends on colour. */
export function RecentTrades({ trades }: { trades: OverviewResponse["recent_trades"] }) {
  return (
    <section className="mt-10">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-xl font-bold">Recent trades</h2>
        <Link href="/app/journal" className="text-sm text-accent hover:underline">View all →</Link>
      </div>
      {trades.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            title="Nothing logged in this period"
            description="Trades you log appear here, most recent first."
            action={{ href: "/app/trades/new", label: "Log completed trade" }}
          />
        </div>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-xl border border-line bg-surface">
          <table className="w-full min-w-[40rem] text-sm">
            <thead>
              <tr className="border-b border-line text-left font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                <th scope="col" className="px-4 py-3">Date</th>
                <th scope="col" className="px-4 py-3">Asset</th>
                <th scope="col" className="px-4 py-3">Session</th>
                <th scope="col" className="px-4 py-3">Setup</th>
                <th scope="col" className="px-4 py-3">Result</th>
                <th scope="col" className="px-4 py-3 text-right">P&amp;L</th>
                <th scope="col" className="px-4 py-3 text-right">R</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id} className="border-b border-line/60 last:border-0">
                  <td className="px-4 py-3 font-mono text-xs">{t.trade_date ?? "—"}</td>
                  <td className="px-4 py-3">{t.asset ?? "—"}</td>
                  <td className="px-4 py-3 text-muted">{t.session ?? "—"}</td>
                  <td className="px-4 py-3 text-muted">{t.setup_type ?? "—"}</td>
                  <td className="px-4 py-3">{t.result ?? "—"}</td>
                  <td
                    className={`px-4 py-3 text-right font-mono ${(t.pnl ?? 0) > 0 ? "text-positive" : (t.pnl ?? 0) < 0 ? "text-negative" : ""}`}
                  >
                    {money(t.pnl)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-muted">
                    {t.rr_realized === null || t.rr_realized === undefined ? "—" : `${t.rr_realized.toFixed(2)}R`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Run the tests and commit**

```bash
cd web && npx vitest run __tests__/overview-next-and-recent.test.tsx && npx eslint . && cd ..
git add -A
git commit -m "feat(app): next review action and recent trades

The next action names something to re-read. Trade outcome is a word in
its own column, so the table never depends on colour to say what
happened."
```

---

### Task E2: Compose the sections

**Files:**
- Create: `web/components/app/overview/sections.tsx`
- Test: `web/__tests__/overview-sections.test.tsx`

**Interfaces:**
- Consumes: every Group C, D and E component
- Produces: `<OverviewSections data />`

- [ ] **Step 1: Write the test**

```tsx
// web/__tests__/overview-sections.test.tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OverviewSections } from "@/components/app/overview/sections";

const data = {
  period: { from_: "2026-08-01", to: "2026-08-31" },
  sample: { trades: 5, dated_points: 4, show_summary: true, show_series: true, show_dominant_series: true, show_comparisons: true, show_patterns: true },
  kpi: { net_pnl: 575, win_rate: 0.4, expectancy: 115, expectancy_state: null, profit_factor: 2.9, profit_factor_state: null, trades: 5, wins: 2, losses: 2, today_pnl: 0, week_pnl: 575 },
  risk: { max_drawdown: { value: -220, state: null }, rule_adherence: { rate: 0.67, followed: 2, recorded: 3 }, edge_leak: { amount: -220, trades: 1, recorded: 3 }, consistency: { value: null, state: "undefined_nan" } },
  trajectory: { equity_curve: [{ date: "2026-08-10", equity: 480 }, { date: "2026-08-11", equity: 260 }, { date: "2026-08-12", equity: 670 }, { date: "2026-08-14", equity: 575 }], current_streak: 1, streak_type: "win", best_streak: 1, worst_streak: 1, average_win: { value: 445, state: null }, average_loss: { value: -157.5, state: null } },
  recurring_edge: { killzones: [{ label: "NY AM", net_pnl: 670, trades: 3 }], setups: [{ label: "Liquidity Sweep + FVG", net_pnl: 670, trades: 3 }] },
  calendar: { year: 2026, month: 8, days: [{ date: "2026-08-12", pnl: 480, outcome: "positive" }] },
  next_review_action: { completed: 2, total: 3, next_key: "first_review", is_activated: false, trades_until_review: 2 },
  recent_trades: [{ id: 1, trade_date: "2026-08-15", asset: "NQ", session: "New York Open", setup_type: "Liquidity Sweep + FVG", result: "Win", pnl: 410, rr_realized: 2.7 }],
} as never;

describe("overview sections", () => {
  it("renders every section in reading order", () => {
    render(<OverviewSections data={data} />);
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual([
      "Risk and discipline",
      "Performance trajectory",
      "Recurring edge",
      "Trading days",
      "Next review action",
      "Recent trades",
    ]);
  });

  it("shows the headline figures above everything else", () => {
    render(<OverviewSections data={data} />);
    expect(screen.getByText("Net P&L")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run __tests__/overview-sections.test.tsx`
Expected: FAIL — cannot resolve the module

- [ ] **Step 3: Implement**

```tsx
// web/components/app/overview/sections.tsx
import { KpiRow } from "@/components/app/overview/kpi-row";
import { RiskDiscipline } from "@/components/app/overview/risk-discipline";
import { Trajectory } from "@/components/app/overview/trajectory";
import { RecurringEdge } from "@/components/app/overview/recurring-edge";
import { TradingCalendar } from "@/components/app/overview/trading-calendar";
import { NextReviewAction } from "@/components/app/overview/next-review-action";
import { RecentTrades } from "@/components/app/overview/recent-trades";
import type { OverviewResponse } from "@/lib/app/overview";

/**
 * The Overview, in reading order: what happened, whether it was a process,
 * how it got there, what repeats, when it happened, what to review, and the
 * trades themselves.
 */
export function OverviewSections({ data }: { data: OverviewResponse }) {
  return (
    <div className="mt-8">
      <KpiRow kpi={data.kpi} sample={data.sample} />
      <RiskDiscipline risk={data.risk} sample={data.sample} />
      <Trajectory trajectory={data.trajectory} sample={data.sample} />
      <RecurringEdge edge={data.recurring_edge} sample={data.sample} />
      <TradingCalendar calendar={data.calendar} sample={data.sample} />
      <NextReviewAction action={data.next_review_action} />
      <RecentTrades trades={data.recent_trades} />
    </div>
  );
}
```

- [ ] **Step 4: Everything compiles now — run the full web gates**

```bash
cd web && npx vitest run && npx tsc --noEmit && npx eslint . && \
  APP_ORIGIN=https://tradelens-app.streamlit.app SITE_ORIGIN=https://www.tradelensai.io SUPPORT_EMAIL=support@tradelensai.io npm run build && cd ..
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(app): compose the Overview

Reading order: what happened, whether it was a process, how it got there,
what repeats, when it happened, what to review, and the trades."
```

**GROUP E REVIEW — light.** Composition, reading order, and copy.

---

# GROUP F — Verification and handoff

### Task F1: Verify and record

**Files:**
- Modify: `docs/coordination/CLAUDE_CODEX_HANDOFF.md`

- [ ] **Step 1: Run every gate and record the real numbers**

```bash
cd web && npx vitest run && npx tsc --noEmit && npx eslint . && \
  APP_ORIGIN=https://tradelens-app.streamlit.app SITE_ORIGIN=https://www.tradelensai.io SUPPORT_EMAIL=support@tradelensai.io npm run build && cd ..
/Users/ayoub/tradelens-ai/.venv/bin/pytest tests/ -q
/Users/ayoub/tradelens-ai/.venv/bin/ruff check src/ scripts/
/Users/ayoub/tradelens-ai/.venv/bin/black --check src/ scripts/ tests/
/Users/ayoub/tradelens-ai/.venv/bin/python scripts/generate_openapi.py && cd web && npm run api:types && cd .. && git diff --exit-code -- web/lib/api
```

Record the actual numbers. The last command must produce no diff — a drift there means the
committed contract does not match the code.

- [ ] **Step 2: Look at it**

The Overview cannot be verified by tests alone; it is a screen of numbers whose job is to be
trustworthy. Start a dev server against a database that has the Phase 0 schema and an opted-in
account, then check at 1440px and 375px:

- Every figure has a label and, where it could be undefined, says so in words rather than
  showing a number.
- No section distinguishes anything by colour alone — check the calendar specifically.
- With a small sample, the low-data states appear instead of charts.
- The period lens changes the figures.

Record what you saw, including anything that looked wrong.

- [ ] **Step 3: Append the Phase 2 record to the handoff**

Include: the real gate numbers; the decisions above and anything that changed while building;
every deviation from this plan and why; and what Phase 3 inherits — specifically that
`/v1/overview` is the pattern for later endpoints, and that `sample_policy` is now the one
low-data policy for both surfaces.

State plainly that the Docker build/startup/health gate remains open.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs(handoff): Phase 2 Overview complete"
```

- [ ] **Step 5: Stop**

Phase 2 is complete. **Do not begin Phase 3.** Trades, Trade Detail and New Trade wait for
their own plan.

---

## Self-Review

**Spec coverage.** §8's Overview inventory, item by item: KPI row (C1) · today and week P&L
(A2 payload, C1) · max drawdown, rule adherence, edge leak, consistency (C2) · equity curve
(D1) · streaks, average win/loss (D2) · killzone and setup performance (D2) · trading-days
calendar (D3) · activation next step (E1) · recent trades (E1) · low-data states (A1, and every
component) · filter panel — **the period lens from Phase 1 is the filter**, which is why this
plan adds no second date control. §2.2's request lifecycle is implemented exactly by A3 and B1.

**Deliberate deviations, both argued above:**
1. **One endpoint rather than per-section endpoints.** The page renders once server-side; eight
   endpoints would be eight round trips for one screen.
2. **The low-data policy moves out of `ui/`.** It is shared infrastructure Overview genuinely
   requires, its own docstring demands one answer across surfaces, and it would otherwise die
   with `ui/` at Phase 10.

**Placeholder scan.** No TBD/TODO. Every step carries real code. F1's "look at it" step lists
concrete things to check rather than "verify it looks good".

**Type consistency.** `OverviewResponse` is produced in B1 and consumed by every component with
the same shape. `sample` is `OverviewResponse["sample"]` everywhere, and the two components that
need only part of it (`EquityCurve`) say so with `Pick<...>`. `StatTile`'s props
(`label`, `value`, `hint?`, `tone?`) are identical in C1's definition and in C2's and D2's uses.
`buildCurvePath(points, width, height)` has one signature. The Python `finite_or_state` pairs in
A2 map to the `Undefinable` model in A3 and to `{ value, state }` in the TypeScript.

**Colour.** The one computed check — the outcome pair at ΔE 2.3 under deuteranopia — drives a
concrete requirement in three places: the calendar's shapes, the tone-plus-text rule in
`StatTile`, and the outcome word in the recent-trades table.
