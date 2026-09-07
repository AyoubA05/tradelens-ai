# Phase 6 — Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the four-lens analytics experience — performance, risk, timing and setups — onto the FastAPI + Next.js boundary with exact metric parity against the existing Python services, and with undefined figures staying undefined all the way to the screen.

**Architecture:** One `GET /v1/analytics` endpoint returns every figure the four lenses need for one owner, one period and one filter set, computed entirely by the existing `services/metrics.py` functions. No formula is reimplemented in TypeScript: the browser receives numbers and renders them. Every numeric field crosses the wire as the Phase 2 `{value, state}` pair, so "we could not compute this" is a distinguishable state rather than a plausible `0.00`. Charts are inline SVG, following `overview/equity-curve.tsx`, because the geometry is data and a wrong picture of an account is worse than no picture.

**Tech Stack:** FastAPI · Pydantic v2 · pandas (existing) · SQLAlchemy 2.x · Next.js 16 App Router · TypeScript · inline SVG · pytest · Vitest

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md` (§7 phase 6, §8 Analytics inventory)

## Global Constraints

- **`src/tradelens/services/metrics.py` is PARITY-PINNED. Do not edit it.** Every figure comes from its existing functions. If a metric appears to need a change, that is a finding to report, not a change to make — the Streamlit page and this page must agree to the cent.
- **No formula is reimplemented in TypeScript.** The browser formats and draws; it never computes a rate, an average, an expectancy or a drawdown. A number that exists in two languages will diverge.
- **Undefined never becomes zero.** Every numeric field is `{value, state}` with `state` one of the `UndefinedState` literals. `0.0` means measured zero; `null` + a state means not measurable. Reads from metric output use `_need()`, never `.get(key, 0.0)`.
- **Owner identity comes only from the authenticated session row.** Never a header, query, path segment or body field.
- **Service-layer tenant isolation is mandatory.** Every read resolves through `require_user_id()`.
- **404, never 403**, byte-identical to a genuine not-found, on every per-id route.
- **One period control for the whole product.** `web/lib/app/period.ts` is the single date lens and it lives in the URL. This page READS it. **No second date control may be introduced** — not a preset row, not a "compare to" picker, not a per-chart range.
- Next.js is the BFF: raw browser session credentials never reach FastAPI; only `sha256("tl.website.v1|" + token)` crosses. `TL_SERVICE_SECRET` never reaches the browser.
- Relays are same-origin, `no-store`, dynamic, and **fail shut when `SITE_ORIGIN` is unset**.
- Response schemas are `_Strict` (`extra="forbid"`, `strict=True`), so a service reshape is a loud failure rather than a silently missing figure.
- TradeLens is a post-trade reflection journal. Never a signal app, a bot, or financial advice — this binds every label, empty state, narrative string and error message. **No lens may say what to do next.**
- `prompts/` files are LOCKED.
- Python 3.9.6 floor: `from __future__ import annotations`, `Optional[X]` / `List[X]`, never `X | Y`.
- **No new npm dependencies and no new Python dependencies.** Charts are hand-rolled SVG; `visx` in the spec's phase table predates the no-new-dependency rule and is superseded by it.
- Gates: `pytest tests/ -q`; `ruff check src/ scripts/`; `black --check src/ scripts/ tests/`; in `web/`: `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build` (needs `SITE_ORIGIN`, `APP_ORIGIN`, `SUPPORT_EMAIL`).

---

## Execution process

Groups, not per-task gates — the model that has worked since Phase 2.

| Group | Review depth |
|---|---|
| A — the metric contract and parity harness | **Deepest in the phase.** Financial correctness is this phase's security boundary. Every figure, every undefined state, and the proof that the API and Streamlit agree. |
| B — the analytics endpoint | **Deep.** Tenant isolation, filter handling, period validation, and the cost of a large period. |
| C — the four lenses | Light at the group boundary, except the low-sample and incomplete-P&L states, which are deep. |
| D — charts, tables and responsive behaviour | Light at the group boundary. |
| E — verification, parity run and handoff | Final phase boundary. |

**Mutation-test every guard.** Across Phases 3–5, roughly a dozen tests were proven to pass against deliberately broken code. The shapes that recur here: a test asserting a value the implementation echoes back; a guard masked by a downstream gate that refuses first; an assertion that also holds when the property is violated; and — the one this phase is most exposed to — **a test that is correct about the wrong constant**. Phase 5 shipped a 1–5 quality scale against a 1–10 product with a test pinning the bug. For every guard: break it, confirm a *named* test fails, restore. A guard with no failing mutation is not defended.

---

## Scope

**In:** the four lenses (Performance, Risk, Timing, Setups); equity curve; daily P&L; drawdown series; R-multiple distribution; breakdowns by day of week, session, strategy, timeframe, asset, setup type and hour of day; killzone performance; confirmation-model performance; mistake frequency; total edge leak; rule adherence; consistency score; expectancy, win rate, profit factor, P&L and max drawdown; period deltas; asset/session/strategy filters; low-sample and incomplete-P&L states; responsive chart and table behaviour.

**Removed from scope during execution, with cause:** the **hour-of-day breakdown**. `metrics.by_hour_of_day` requires an `hour_of_day` column and its docstring asks callers to derive one "from a future time column". There is no such column: `entry_time` is **hash-only** — `trade_service` fingerprints it and drops it before insert — and the `Trade` model stores no clock component at all (`trade_date` is a bare ISO date). The function therefore returns zero rows for every real sample, and a panel built on it would sit permanently empty. An empty "by hour" chart does not read as *this feature has no data source*; it reads as *you have no hourly pattern*, which is a claim about the trader's record that we would be inventing. Restoring it needs a persisted time column, which is a schema change and a different phase. Pinned by `test_the_timing_lens_does_not_offer_an_hour_breakdown_it_cannot_fill`.

**Explicitly not in:** Strategy Profile (Phase 7), AI Partner (Phase 8), Settings (Phase 9), Streamlit retirement (Phase 10). Do not touch the Overview, Journal, Trade Detail or New Trade surfaces beyond reading their existing helpers. Do not add a second date control anywhere.

**Deployment gates tracked separately and NOT addressed here:** Docker build/startup/health; disposable PostgreSQL migration verification; real PostgreSQL concurrent AI-job verification; broader Python dependency audit; live Anthropic key + injection/model smoke; live R2 + browser smoke. They are recorded in the handoff and stay open.

**Known pre-existing failure, NOT this phase's to fix:** `tests/test_pages_boot.py::test_analytics_single_setup_readout_does_not_claim_a_ranking` and `::test_analytics_category_names_are_escaped_exactly_once` fail deterministically in the current environment (`marker not found: BOS &amp; FVG`). They fail identically at `fc4968d`, the commit that introduced them, and on `49b7eed`, which predates Phase 5 — so they are environment-sensitive and unrelated to this work. They exercise the **Streamlit** analytics page. Do not fix them here. If a Group A parity task genuinely cannot run without them, that is a finding to report, not a licence to edit them.

---

## What already exists — read before writing anything

This phase is **projection and presentation**, not computation. Verified in the code at `0db8593`:

- `services/metrics.py` — every function this phase needs, already written and parity-pinned. Note the exact names and return shapes:
  - `compute_basic_metrics(df) -> dict` (keys include `total_pnl`, `win_rate`, `total_trades`, `avg_win`, `avg_loss`, `wins`, `losses`)
  - `compute_expectancy(metrics: dict) -> float` — takes the **metrics dict**, not the frame
  - `compute_profit_factor_raw(df) -> float`, `compute_max_drawdown(equity_curve: pd.DataFrame) -> float`
  - `compute_equity_curve(df) -> pd.DataFrame`, `daily_pnl(df)`, `drawdown_series(df)`, `r_multiple_distribution(df, bins=20)`
  - `by_day_of_week`, `by_session`, `by_strategy`, `by_timeframe`, `by_asset`, `by_setup_type`, `by_hour_of_day`, `killzone_performance`, `setup_performance`, `confirmation_model_performance`, `emotion_vs_rr`, `mistake_frequency` — all `(df) -> pd.DataFrame`
  - `total_edge_leak(df) -> float`, `rule_adherence_rate(df) -> RuleAdherenceSummary`, `edge_leak_summary(df) -> EdgeLeakSummary`, `consistency_score(df) -> float`
  - `period_deltas(current_df, prior_df) -> dict`, `split_periods(...)`, `compute_streaks(df) -> dict`
- `services/sample_policy.py` — `sample_state(df) -> SampleState`, `show_dated_instrument(state)`, `enough_categories(df, column)`, `leading_category(...)`, `has_variation(...)`, and the thresholds `_MIN_SERIES_POINTS = 2`, `_MIN_COMPARISON_TRADES = 2`, `_MIN_CATEGORIES = 2`, `_MIN_PATTERN_TRADES = 5`, `MIN_DATED_POINTS = 4`. **This is the single decision about what a sample has earned the right to show.** Reuse it; do not invent a second threshold set.
- `services/overview.py` — the projection precedent: `_pair`, `_undefined`, `_money_pair`, `_sample_pair`, `_need`, `_frame`. Read all six before writing Group A; they encode the undefined-never-zero rule and the reasons behind it.
- `api/serialization.py:80` — `finite_or_state(value) -> tuple[Optional[float], Optional[str]]`.
- `api/schemas/overview.py` — `UndefinedState`, `_Strict`, `Period`, and the `{value, state}` model shape.
- `api/routers/overview.py:28` — `_validated_period(start, end)`, including why the regex pre-check exists (3.9 and 3.11 disagree about what `fromisoformat` accepts).
- `ui/pages/4_Analytics.py` — the four lenses, their questions, their filter set and their empty states. This is the **parity reference**, not a file to modify.
- `web/lib/app/period.ts` — the one date lens. Its own comment: *"Later phases READ this; no page may introduce a second date control."*
- `web/lib/app/trade-filters.ts` — `TRADE_FILTER_KEYS = ["asset", "session", "setup", "result"]`, URL-state helpers.
- `web/components/app/overview/equity-curve.tsx` — `buildCurvePath(points, width, height)`, exported *because the geometry is data*: it handles the flat-curve divide-by-zero and the inverted SVG y axis. Reuse it rather than writing a second one.
- `web/lib/app/trade-analysis-relay.ts` — the fail-shut relay guard shape.

## Design decisions

**1. One endpoint, not eleven.**
The four lenses answer four questions about *the same filtered sample*. Eleven endpoints would mean eleven chances for one of them to be computed over a slightly different frame — a different rounding of the period, a filter applied in a different order — and the trader would see a win rate that disagrees with the breakdown it is supposedly built from. One request, one frame, one set of numbers that are consistent by construction.

The cost is a larger response. That is the right trade here: the figures are small (numbers and short labels), the page renders all four lenses from one fetch, and lens switching becomes free rather than another round trip.

**2. Every number is `{value, state}`. No exceptions, including the ones that "obviously" have a value.**
Phase 2 learned this the hard way: a plan that wrapped metric reads in `.get(col, 0.0)` would have rendered five undefined figures as `$0.00`, and a four-trade trader was shown "0 out of 100" consistency as though it were a measurement. The rule is not "wrap the risky ones" — it is that a numeric field's type makes the undefined case unrepresentable-as-zero. A field typed as a bare `float` is a field that will eventually carry a fabricated zero.

`_sample_pair` exists because several metrics flatten "not enough data" into an ordinary finite `0.0` rather than a NaN — max drawdown below two points, consistency below five trades, a win rate over zero trades. `finite_or_state` cannot see those. The **caller** decides insufficiency from the sample counts it already holds.

**3. `services/metrics.py` is not edited, and parity is proven rather than asserted.**
The Streamlit page and this page must agree to the cent, because a trader who has both open and sees two different win rates has no way to know which is lying. Group A therefore builds a parity harness that runs *both* paths over the same seeded frame and compares field by field. That harness is the phase's most valuable test: it is the only thing that would catch a projection that quietly re-derives a figure instead of reading it.

**4. The browser computes nothing financial.**
`buildCurvePath` maps numbers to pixels, which is drawing, not arithmetic about money. Everything else — rates, averages, sums, ratios, drawdowns — arrives computed. A profit factor calculated in TypeScript would be a second implementation of a formula that already exists, and the two would diverge the first time either changed.

**5. One period control, and this page does not own it.**
`period.ts` already states the rule. The temptation here is real: analytics pages conventionally carry their own range picker, and `period_deltas` needs a *prior* period. But a second control means two windows on one screen and a reader who cannot tell which number belongs to which. The prior period is **derived** server-side from the current one via `split_periods`, never selected. The comparison is labelled with its actual dates so it is legible without a second control.

**6. Filters are URL state, reusing the journal's keys.**
`asset`, `session` and `strategy` filters live in the URL beside the period, so an analytics view is linkable and back-button-able. The journal's `TRADE_FILTER_KEYS` already defines three of these; `strategy` is added rather than a parallel scheme invented. A filter that round-trips into the URL but is not applied server-side is the failure Phase 3 already hit once.

**7. Low sample is a first-class state, not an empty chart.**
`sample_policy` already decides this for Streamlit. Reusing it means the two surfaces agree about when a figure has earned the right to be shown. An analytics page that draws a confident trend line through four points is making a claim the data does not support, and this product's whole posture is that a number without its sample size is not an answer.

---

## File structure

**Python — new**

| File | Responsibility |
|---|---|
| `src/tradelens/services/analytics.py` | Builds the whole analytics payload from one frame. The ONLY new module that reads `services/metrics`. Pure projection: no formulas. |
| `src/tradelens/api/schemas/analytics.py` | The strict response contract: `AnalyticsResponse` and its lens models. |
| `src/tradelens/api/routers/analytics.py` | `GET /v1/analytics` — period validation, filters, owner scoping. |
| `tests/test_analytics_service.py` | Projection correctness and every undefined state. |
| `tests/test_analytics_parity.py` | **The parity harness.** Both paths over one frame, field by field. |
| `tests/test_api_analytics.py` | Route-level: tenant isolation, period/filter validation, contract shape. |

**Python — modified**

| File | Change |
|---|---|
| `src/tradelens/api/app.py` | Register the analytics router. |

**Web — new**

| File | Responsibility |
|---|---|
| `web/lib/app/analytics.ts` | Server-only `callApi` bridge + generated types. |
| `web/lib/app/analytics-relay.ts` | Fail-shut relay guard. |
| `web/app/api/analytics/route.ts` | The relay. |
| `web/lib/app/analytics-filters.ts` | URL state for `asset`/`session`/`strategy`, reusing the journal's helpers. |
| `web/components/app/analytics/lens-tabs.tsx` | The four-lens selector (no date control). |
| `web/components/app/analytics/performance-lens.tsx` | Lens 1. |
| `web/components/app/analytics/risk-lens.tsx` | Lens 2. |
| `web/components/app/analytics/timing-lens.tsx` | Lens 3. |
| `web/components/app/analytics/setups-lens.tsx` | Lens 4. |
| `web/components/app/analytics/metric-value.tsx` | Renders one `{value, state}`. The single place an undefined figure becomes text. |
| `web/components/app/analytics/bar-chart.tsx` | Inline-SVG horizontal bars for breakdowns. |
| `web/components/app/analytics/distribution-chart.tsx` | Inline-SVG histogram for R-multiples. |
| `web/components/app/analytics/breakdown-table.tsx` | Responsive table with its own horizontal scroll container. |

**Web — modified**

| File | Change |
|---|---|
| `web/app/app/analytics/page.tsx` | Replace the placeholder; fetch, and render the lenses. |
| `web/lib/api/openapi.json`, `web/lib/api/schema.d.ts` | Regenerated. |

---

## Group A — the metric contract and parity harness

### Task A1: The value projection helpers

**Files:**
- Create: `src/tradelens/services/analytics.py`
- Create: `tests/test_analytics_service.py`

**Interfaces:**
- Consumes: `services.overview._pair`-style helpers (read them; do not import private names across modules — copy the four small helpers with their comments, as this module owns its own projection).
- Produces: `pair(value) -> Dict[str, Any]`, `undefined(state) -> Dict[str, Any]`, `money_pair(value, *, complete: bool) -> Dict[str, Any]`, `sample_pair(value, insufficient: bool) -> Dict[str, Any]`, `need(mapping, key) -> Any`, `frame(trades) -> pd.DataFrame`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_analytics_service.py`:

```python
"""Phase 6 analytics projection: undefined never becomes zero."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.tradelens.services import analytics as an


def test_a_real_zero_stays_a_measured_zero():
    """A trader who broke exactly even measured 0.00. That is an answer."""
    assert an.pair(0.0) == {"value": 0.0, "state": None}


def test_nan_becomes_an_undefined_state_not_a_zero():
    assert an.pair(float("nan"))["value"] is None
    assert an.pair(float("nan"))["state"] == "undefined_nan"


def test_infinite_profit_factor_is_named_not_flattened():
    """A profit factor with no losing trades is infinite, not huge and not 0."""
    assert an.pair(float("inf")) == {
        "value": None,
        "state": "undefined_positive_infinity",
    }


def test_none_is_no_sample_rather_than_a_silent_null():
    assert an.pair(None) == {"value": None, "state": "undefined_no_sample"}


def test_money_over_rows_that_do_not_record_pnl_is_incomplete_not_zero():
    """THE money rule. A journal with prices but no P&L has not made $0."""
    assert an.money_pair(0.0, complete=False) == {
        "value": None,
        "state": "undefined_incomplete_sample",
    }
    assert an.money_pair(250.0, complete=True) == {"value": 250.0, "state": None}


def test_a_metric_that_flattens_low_sample_to_zero_is_gated_by_the_caller():
    """`finite_or_state` cannot see this: 0.0 is finite.

    max_drawdown below two points, consistency below five trades and a win
    rate over zero trades all return an ordinary 0.0, so only the caller's
    knowledge of the sample size can tell "measured zero" from "no answer".
    """
    assert an.sample_pair(0.0, insufficient=True)["state"] == "undefined_no_sample"
    assert an.sample_pair(0.0, insufficient=False) == {"value": 0.0, "state": None}


def test_reading_a_missing_metric_key_raises_rather_than_defaulting():
    """A renamed metric must break loudly, not render a plausible $0.00.

    Phase 2's plan wrapped every read in `.get(col, 0.0)` and would have
    shipped five undefined figures as zero.
    """
    with pytest.raises(KeyError):
        an.need({"total_pnl": 1.0}, "net_pnl")


def test_the_frame_of_no_trades_is_empty_not_a_row_of_zeroes():
    built = an.frame([])
    assert isinstance(built, pd.DataFrame)
    assert built.empty
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_analytics_service.py -v`
Expected: FAIL — `ModuleNotFoundError: src.tradelens.services.analytics`.

- [ ] **Step 3: Implement the helpers**

Create `src/tradelens/services/analytics.py`:

```python
"""The analytics payload: one owner, one period, one filtered sample.

Pure projection. Every figure comes from `services/metrics`, which is
parity-pinned — this module reads those functions and shapes their output for
the wire, and computes nothing of its own. A formula that existed here as
well as there would be a second implementation, and the two would diverge
the first time either changed.

The one rule everything else follows: **an undefined figure stays
undefined.** `0.0` means a trader measured zero. `null` with a state means we
could not measure. Phase 2 shipped a plan that would have rendered five
undefined figures as `$0.00` and told a four-trade trader their consistency
was "0 out of 100"; the shape below is what stops that being expressible.

No Streamlit imports here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from src.tradelens.api.serialization import finite_or_state

_UNDEFINED_NO_SAMPLE = {"value": None, "state": "undefined_no_sample"}


def pair(value: Any) -> Dict[str, Any]:
    """A possibly-undefined number as `{value, state}`."""
    number, state = finite_or_state(value)
    if number is None and state is None:
        state = "undefined_no_sample"
    return {"value": number, "state": state}


def undefined(state: str) -> Dict[str, Any]:
    return {"value": None, "state": state}


def money_pair(value: Any, *, complete: bool) -> Dict[str, Any]:
    """A monetary figure that is only meaningful when its rows record P&L.

    A journal kept for the process — entries, stops, notes — with the P&L
    column left blank has not earned a total of $0.00. It has no total.
    """
    if not complete:
        return undefined("undefined_incomplete_sample")
    return pair(value)


def sample_pair(value: Any, insufficient: bool) -> Dict[str, Any]:
    """A number gated by sample size, not merely by non-finiteness.

    `finite_or_state` only recovers a state from NaN/±inf. Several metrics
    flatten "not enough data" into an ordinary finite 0.0 — max drawdown
    below two points, consistency below five trades, an average over zero
    members, a win rate over zero trades — so `pair` alone is a no-op on all
    of them and 0.0 would read as a real answer. `insufficient` is computed
    by the caller from sample counts it already holds, never from the
    metric's return value.
    """
    if insufficient:
        return dict(_UNDEFINED_NO_SAMPLE)
    return pair(value)


def need(mapping: Any, key: str) -> Any:
    """Read a required key, loudly.

    Deliberately not `.get(key, 0.0)`. If a metric is renamed or its output
    reshaped, a defaulting read turns that mistake into a plausible $0.00 on
    a trader's screen instead of a failing test.
    """
    if key not in mapping:
        raise KeyError(f"metric output has no key {key!r}")
    return mapping[key]


def frame(trades: List[Any]) -> pd.DataFrame:
    """ORM rows as the DataFrame `services/metrics` expects.

    An empty list yields an empty frame, never a single row of zeroes: the
    metric functions already know how to answer "no sample", and inventing a
    row here would answer it wrongly.
    """
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([_row(trade) for trade in trades])


_COLUMNS = (
    "id",
    "trade_date",
    "asset",
    "direction",
    "timeframe",
    "session",
    "killzone",
    "setup_type",
    "confirmation_model",
    "strategy_used",
    "htf_bias",
    "result",
    "pnl",
    "rr_planned",
    "rr_realized",
    "risk_amount",
    "position_size",
    "entry_time",
    "day_of_week",
    "followed_rules",
    "mistake_tags",
    "emotions_before",
    "emotions_during",
    "emotions_after",
    "ai_grade",
    "user_grade",
)


def _row(trade: Any) -> Dict[str, Any]:
    return {column: getattr(trade, column, None) for column in _COLUMNS}
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_analytics_service.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Mutate each guard and confirm a named test catches it**

| Mutation | Expected failing test |
|---|---|
| `need` becomes `return mapping.get(key, 0.0)` | `test_reading_a_missing_metric_key_raises_rather_than_defaulting` |
| `money_pair` ignores `complete` | `test_money_over_rows_that_do_not_record_pnl_is_incomplete_not_zero` |
| `sample_pair` ignores `insufficient` | `test_a_metric_that_flattens_low_sample_to_zero_is_gated_by_the_caller` |
| `pair(None)` returns `{"value": 0.0, "state": None}` | `test_none_is_no_sample_rather_than_a_silent_null` |
| `frame([])` returns a one-row zero frame | `test_the_frame_of_no_trades_is_empty_not_a_row_of_zeroes` |

Apply, run, record the named failure, restore. Confirm `git diff` is empty afterwards.

- [ ] **Step 6: Commit**

```bash
git add src/tradelens/services/analytics.py tests/test_analytics_service.py
git commit -m "feat(analytics): the value projection, where undefined stays undefined"
```

---

### Task A2: The performance and risk projections

**Files:**
- Modify: `src/tradelens/services/analytics.py`
- Test: `tests/test_analytics_service.py`

**Interfaces:**
- Consumes: `pair`, `money_pair`, `sample_pair`, `need`, `frame` (A1); `metrics.compute_basic_metrics`, `compute_expectancy`, `compute_profit_factor_raw`, `compute_equity_curve`, `compute_max_drawdown`, `daily_pnl`, `drawdown_series`, `r_multiple_distribution`, `compute_streaks`; `sample_policy.sample_state`.
- Produces: `build_performance(df) -> dict`, `build_risk(df) -> dict`, `pnl_is_complete(df) -> bool`, `insufficient_for(df, minimum: int) -> bool`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analytics_service.py`:

```python
def _trades_frame(rows):
    return pd.DataFrame(rows)


def _winning_row(**over):
    row = {
        "id": 1,
        "trade_date": "2026-09-01",
        "asset": "NQ",
        "direction": "Long",
        "result": "Win",
        "pnl": 250.0,
        "rr_realized": 2.0,
        "rr_planned": 2.0,
        "session": "New York",
        "killzone": "ny_am",
        "setup_type": "FVG",
        "confirmation_model": "BOS",
        "strategy_used": "ICT",
        "timeframe": "5m",
        "day_of_week": "Tuesday",
        "entry_time": "09:35",
        "followed_rules": 1,
        "mistake_tags": "[]",
    }
    row.update(over)
    return row


def test_expectancy_is_read_from_the_metrics_dict_not_recomputed():
    """`compute_expectancy` takes the metrics DICT, not the frame.

    Passing the frame would raise or, worse, silently produce a different
    number — this pins the call shape as well as the value.
    """
    from src.tradelens.services.metrics import (
        compute_basic_metrics,
        compute_expectancy,
    )

    df = _trades_frame([_winning_row(), _winning_row(id=2, result="Loss", pnl=-100.0)])
    built = an.build_performance(df)

    assert built["expectancy"]["value"] == pytest.approx(
        compute_expectancy(compute_basic_metrics(df))
    )


def test_a_journal_with_no_pnl_reports_no_total_rather_than_zero():
    """The process-only journal: prices and notes, P&L never filled in."""
    df = _trades_frame(
        [_winning_row(pnl=None), _winning_row(id=2, pnl=None, result="Loss")]
    )
    built = an.build_performance(df)

    assert built["total_pnl"] == {
        "value": None,
        "state": "undefined_incomplete_sample",
    }


def test_profit_factor_with_no_losses_is_infinite_not_a_big_number():
    df = _trades_frame([_winning_row(), _winning_row(id=2)])
    assert (
        an.build_performance(df)["profit_factor"]["state"]
        == "undefined_positive_infinity"
    )


def test_max_drawdown_under_two_points_is_undefined_not_zero():
    """A single trade has no drawdown to measure. 0.0 would claim it does."""
    df = _trades_frame([_winning_row()])
    assert an.build_risk(df)["max_drawdown"]["state"] == "undefined_no_sample"


def test_an_empty_sample_reports_every_figure_as_undefined():
    """Not one plausible zero anywhere on the page."""
    built = an.build_performance(pd.DataFrame())
    for field in ("total_pnl", "win_rate", "expectancy", "profit_factor"):
        assert built[field]["value"] is None, field
        assert built[field]["state"] is not None, field


def test_a_measured_zero_pnl_is_not_reported_as_undefined():
    """The other direction, and it matters just as much.

    A trader who genuinely broke even measured 0.00. Reporting that as "no
    data" would erase a real result — over-gating is as wrong as under-gating.
    """
    df = _trades_frame(
        [
            _winning_row(pnl=100.0),
            _winning_row(id=2, result="Loss", pnl=-100.0),
        ]
    )
    built = an.build_performance(df)
    assert built["total_pnl"] == {"value": 0.0, "state": None}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_analytics_service.py -k "performance or risk or pnl or drawdown or expectancy" -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'build_performance'`.

- [ ] **Step 3: Implement**

Append to `src/tradelens/services/analytics.py`:

```python
from src.tradelens.services.metrics import (
    compute_basic_metrics,
    compute_equity_curve,
    compute_expectancy,
    compute_max_drawdown,
    compute_profit_factor_raw,
    compute_streaks,
    daily_pnl,
    drawdown_series,
    r_multiple_distribution,
)
from src.tradelens.services.sample_policy import (
    _MIN_SERIES_POINTS,
    sample_state,
)

# Below this many rows a drawdown is not a measurement. `sample_policy` owns
# the number; naming it here rather than writing `2` keeps the two surfaces
# agreeing about what a sample has earned.
MIN_DRAWDOWN_POINTS = _MIN_SERIES_POINTS


def pnl_is_complete(df: pd.DataFrame) -> bool:
    """Whether every row in this sample records a P&L.

    Not "some rows have P&L". A total over a sample where half the rows are
    blank is a number with no meaning: it is neither the trader's real
    result nor a subset they chose.
    """
    if df.empty or "pnl" not in df.columns:
        return False
    return bool(df["pnl"].notna().all())


def insufficient_for(df: pd.DataFrame, minimum: int) -> bool:
    """Whether this sample is too small for a figure that needs `minimum` rows."""
    return len(df) < minimum


def build_performance(df: pd.DataFrame) -> Dict[str, Any]:
    """Lens 1 — how did this period actually go?"""
    if df.empty:
        return {
            "total_pnl": undefined("undefined_no_sample"),
            "win_rate": dict(_UNDEFINED_NO_SAMPLE),
            "expectancy": dict(_UNDEFINED_NO_SAMPLE),
            "profit_factor": dict(_UNDEFINED_NO_SAMPLE),
            "total_trades": 0,
            "equity_curve": [],
            "daily_pnl": [],
            "streaks": {
                "current": dict(_UNDEFINED_NO_SAMPLE),
                "max_win": dict(_UNDEFINED_NO_SAMPLE),
                "max_loss": dict(_UNDEFINED_NO_SAMPLE),
            },
        }

    basic = compute_basic_metrics(df)
    complete = pnl_is_complete(df)
    total = len(df)
    streaks = compute_streaks(df)

    return {
        # `need`, not `.get`: a renamed metric key must fail a test, not
        # render as a plausible $0.00.
        "total_pnl": money_pair(need(basic, "total_pnl"), complete=complete),
        "win_rate": sample_pair(
            need(basic, "win_rate"), insufficient_for(df, 1)
        ),
        "expectancy": money_pair(compute_expectancy(basic), complete=complete),
        "profit_factor": pair(compute_profit_factor_raw(df)),
        "total_trades": total,
        # VERIFIED column names. `compute_equity_curve` emits
        # `trade_date/pnl/cumulative_pnl` and `daily_pnl` emits
        # `trade_date/daily_pnl` — not `date`/`equity`/`pnl`. A wrong name
        # here returns an EMPTY series rather than raising, so the chart
        # would simply be blank and nothing would say why.
        "equity_curve": _series(compute_equity_curve(df), "trade_date", "cumulative_pnl"),
        "daily_pnl": _series(daily_pnl(df), "trade_date", "daily_pnl"),
        "streaks": {
            "current": sample_pair(
                need(streaks, "current_streak"), insufficient_for(df, 1)
            ),
            "max_win": sample_pair(
                need(streaks, "max_win_streak"), insufficient_for(df, 1)
            ),
            "max_loss": sample_pair(
                need(streaks, "max_loss_streak"), insufficient_for(df, 1)
            ),
        },
    }


def build_risk(df: pd.DataFrame) -> Dict[str, Any]:
    """Lens 2 — how much was at stake, and what did it cost?"""
    if df.empty:
        return {
            "max_drawdown": dict(_UNDEFINED_NO_SAMPLE),
            "drawdown_series": [],
            "r_multiples": [],
            "avg_win": dict(_UNDEFINED_NO_SAMPLE),
            "avg_loss": dict(_UNDEFINED_NO_SAMPLE),
        }

    basic = compute_basic_metrics(df)
    complete = pnl_is_complete(df)
    curve = compute_equity_curve(df)

    return {
        # A drawdown needs at least two points to exist. `compute_max_drawdown`
        # returns a finite 0.0 below that, which `pair` cannot distinguish
        # from a real flat period — hence the caller-side gate.
        "max_drawdown": sample_pair(
            compute_max_drawdown(curve),
            insufficient_for(df, MIN_DRAWDOWN_POINTS) or not complete,
        ),
        "drawdown_series": _series(drawdown_series(df), "trade_date", "drawdown"),
        "r_multiples": _histogram(r_multiple_distribution(df)),
        "avg_win": money_pair(
            need(basic, "avg_win"),
            complete=complete and int(need(basic, "wins")) > 0,
        ),
        "avg_loss": money_pair(
            need(basic, "avg_loss"),
            complete=complete and int(need(basic, "losses")) > 0,
        ),
    }


def _series(
    built: pd.DataFrame, date_column: str, value_column: str
) -> List[Dict[str, Any]]:
    """A dated series as wire rows, dropping points that cannot be plotted.

    A NaN in the middle of an equity curve is not a zero and must not be
    drawn as one; the point is omitted and the gap is visible.
    """
    # Both column names are REQUIRED arguments and are asserted present: a
    # mistyped name must fail loudly, not yield an empty chart that reads as
    # "no trades". Guessing a date column by position was how the first
    # draft of this plan would have silently emptied three charts.
    if built is None or built.empty:
        return []
    if date_column not in built.columns or value_column not in built.columns:
        raise KeyError(
            f"series expects {date_column!r} and {value_column!r}, got {list(built.columns)}"
        )
    rows: List[Dict[str, Any]] = []
    for _, row in built.iterrows():
        number, _state = finite_or_state(row[value_column])
        if number is None:
            continue
        rows.append({"date": str(row[date_column]), "value": number})
    return rows


def _histogram(built: pd.DataFrame) -> List[Dict[str, Any]]:
    """R-multiple buckets as `{label, count}`.

    VERIFIED: `r_multiple_distribution` emits `bin_left/bin_right/count`.
    The label is built from the two edges — taking `columns[0]` would print
    a bare bin edge like `-1.5` as though it were a category name.
    """
    if built is None or built.empty:
        return []
    return [
        {
            "label": f"{float(row['bin_left']):.1f} to {float(row['bin_right']):.1f}R",
            "count": int(row["count"]),
        }
        for _, row in built.iterrows()
    ]
```

> **The column names above are VERIFIED against real function output**, not remembered. The first draft of this plan had six of them wrong, and four would have failed *silently* — an empty equity curve, an empty daily-P&L series, setup P&L permanently undefined, and rule adherence permanently undefined. Re-verify before changing any of them:
>
> ```
> compute_basic_metrics  -> avg_loss avg_rr_realized avg_win best_trade breakevens
>                           loss_rate losses profit_factor total_pnl total_trades
>                           win_rate wins worst_trade
> compute_streaks        -> current_streak max_loss_streak max_win_streak streak_type
> compute_equity_curve   -> trade_date pnl cumulative_pnl
> daily_pnl              -> trade_date daily_pnl
> drawdown_series        -> trade_date cumulative_pnl running_peak drawdown
> r_multiple_distribution-> bin_left bin_right count
> by_day_of_week/by_session/setup_performance
>                        -> <key> trades wins losses breakevens win_rate
>                           avg_rr_realized total_pnl
> by_setup_type          -> setup_type trades wins losses breakevens   (NO P&L)
> by_hour_of_day         -> hour_of_day trades total_pnl avg_rr_realized
> killzone_performance   -> killzone ... win_rate avg_rr_realized profit_factor total_pnl
> by_asset/by_strategy/by_timeframe/confirmation_model_performance
>                        -> <key> trades wins losses breakevens win_rate total_pnl profit_factor
> mistake_frequency      -> mistake_tag count total_pnl avg_pnl
> RuleAdherenceSummary   -> followed recorded rate          (NOT recorded_trades)
> EdgeLeakSummary        -> net_pnl qualifying_trades recorded_trades
> ```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_analytics_service.py -v`
Expected: PASS.

- [ ] **Step 5: Mutate and confirm**

| Mutation | Expected failing test |
|---|---|
| `money_pair(..., complete=True)` hardcoded in `build_performance` | `test_a_journal_with_no_pnl_reports_no_total_rather_than_zero` |
| `max_drawdown` uses `pair` instead of `sample_pair` | `test_max_drawdown_under_two_points_is_undefined_not_zero` |
| `pnl_is_complete` uses `.any()` instead of `.all()` | `test_a_journal_with_no_pnl_reports_no_total_rather_than_zero` |
| `insufficient_for` always returns `True` | `test_a_measured_zero_pnl_is_not_reported_as_undefined` |
| `_series` keeps NaN points as `0.0` | add `test_a_nan_point_is_omitted_from_a_series_not_drawn_as_zero` first, then mutate |

- [ ] **Step 6: Commit**

```bash
git add src/tradelens/services/analytics.py tests/test_analytics_service.py
git commit -m "feat(analytics): performance and risk projections"
```

---

### Task A3: The timing and setups projections

**Files:**
- Modify: `src/tradelens/services/analytics.py`
- Test: `tests/test_analytics_service.py`

**Interfaces:**
- Consumes: A1/A2 helpers; `metrics.by_day_of_week`, `by_session`, `by_hour_of_day`, `killzone_performance`, `by_asset`, `by_setup_type`, `by_strategy`, `by_timeframe`, `confirmation_model_performance`, `mistake_frequency`, `total_edge_leak`, `rule_adherence_rate`, `edge_leak_summary`, `consistency_score`; `sample_policy.enough_categories`.
- Produces: `build_timing(df) -> dict`, `build_setups(df) -> dict`, `build_discipline(df) -> dict`, `breakdown(built: pd.DataFrame, key_column: str, *, complete: bool) -> dict`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analytics_service.py`:

```python
def test_a_breakdown_reports_whether_it_can_be_compared():
    """One category is not a ranking.

    The Streamlit page already refuses to call a single setup "best"; the API
    has to carry that judgement rather than leaving the browser to guess,
    or the two surfaces will disagree about the same sample.
    """
    df = _trades_frame([_winning_row(), _winning_row(id=2)])  # one setup only
    built = an.build_setups(df)

    assert built["by_setup"]["comparable"] is False
    assert len(built["by_setup"]["rows"]) == 1


def test_two_categories_are_comparable():
    df = _trades_frame(
        [_winning_row(), _winning_row(id=2, setup_type="OB", result="Loss", pnl=-50.0)]
    )
    assert an.build_setups(df)["by_setup"]["comparable"] is True


def test_a_breakdown_row_with_no_pnl_carries_an_undefined_total():
    df = _trades_frame([_winning_row(pnl=None), _winning_row(id=2, pnl=None)])
    rows = an.build_setups(df)["by_setup"]["rows"]

    assert rows[0]["total_pnl"]["state"] == "undefined_incomplete_sample"


def test_rule_adherence_over_rows_that_never_recorded_it_is_undefined():
    """A blank `followed_rules` is not a broken rule.

    Counting unrecorded rows as violations would tell a trader their
    discipline was 0% when they simply had not filled the field in.
    """
    df = _trades_frame(
        [_winning_row(followed_rules=None), _winning_row(id=2, followed_rules=None)]
    )
    assert an.build_discipline(df)["rule_adherence"]["state"] == "undefined_no_sample"


def test_consistency_below_five_trades_is_undefined_not_zero():
    """Phase 2 shipped "0 out of 100" to a four-trade trader. Not again."""
    df = _trades_frame([_winning_row(id=i) for i in range(4)])
    assert an.build_discipline(df)["consistency"]["state"] == "undefined_no_sample"


def test_mistake_frequency_over_an_empty_sample_is_an_empty_list():
    assert an.build_setups(pd.DataFrame())["mistakes"] == []
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_analytics_service.py -k "breakdown or adherence or consistency or mistake" -v`
Expected: FAIL — `build_setups` / `build_timing` / `build_discipline` do not exist.

- [ ] **Step 3: Implement**

Append to `src/tradelens/services/analytics.py`:

```python
from src.tradelens.services.metrics import (
    by_asset,
    by_day_of_week,
    by_hour_of_day,
    by_session,
    by_setup_type,
    by_strategy,
    by_timeframe,
    confirmation_model_performance,
    consistency_score,
    edge_leak_summary,
    killzone_performance,
    mistake_frequency,
    rule_adherence_rate,
    setup_performance,
    total_edge_leak,
)
from src.tradelens.services.sample_policy import (
    _MIN_PATTERN_TRADES,
    enough_categories,
)

MIN_CONSISTENCY_TRADES = _MIN_PATTERN_TRADES


def breakdown(
    built: pd.DataFrame, key_column: str, *, complete: bool
) -> Dict[str, Any]:
    """One category breakdown, plus whether it can honestly be compared.

    `comparable` travels on the wire rather than being inferred in the
    browser: `sample_policy.enough_categories` is the single decision about
    when a breakdown is a ranking and when it is one bar, and duplicating
    that rule in TypeScript is how the two surfaces come to disagree about
    the same sample.
    """
    if built is None or built.empty or key_column not in built.columns:
        return {"rows": [], "comparable": False}

    rows: List[Dict[str, Any]] = []
    for _, row in built.iterrows():
        entry: Dict[str, Any] = {"key": str(row[key_column])}
        entry["trades"] = int(row["trades"]) if "trades" in built.columns else 0
        if "total_pnl" in built.columns:
            entry["total_pnl"] = money_pair(row["total_pnl"], complete=complete)
        else:
            entry["total_pnl"] = undefined("undefined_no_sample")
        entry["win_rate"] = (
            pair(row["win_rate"]) if "win_rate" in built.columns else dict(_UNDEFINED_NO_SAMPLE)
        )
        rows.append(entry)

    return {"rows": rows, "comparable": bool(enough_categories(built, key_column))}


def build_timing(df: pd.DataFrame) -> Dict[str, Any]:
    """Lens 3 — when does the edge show up?"""
    complete = pnl_is_complete(df)
    if df.empty:
        empty = {"rows": [], "comparable": False}
        return {
            "by_day_of_week": empty,
            "by_session": empty,
            "by_hour": empty,
            "by_killzone": empty,
        }
    return {
        "by_day_of_week": breakdown(by_day_of_week(df), "day_of_week", complete=complete),
        "by_session": breakdown(by_session(df), "session", complete=complete),
        "by_killzone": breakdown(killzone_performance(df), "killzone", complete=complete),
    }


def build_setups(df: pd.DataFrame) -> Dict[str, Any]:
    """Lens 4 — which setups carry the edge?"""
    complete = pnl_is_complete(df)
    if df.empty:
        empty = {"rows": [], "comparable": False}
        return {
            "by_setup": empty,
            "by_asset": empty,
            "by_strategy": empty,
            "by_timeframe": empty,
            "by_confirmation": empty,
            "mistakes": [],
        }
    return {
        # `setup_performance`, NOT `by_setup_type`. VERIFIED: `by_setup_type`
        # emits only trades/wins/losses/breakevens — no `total_pnl` and no
        # `win_rate` — so building the setups lens from it would report every
        # setup's P&L as undefined forever. Phase 2 hit this exact gap and
        # added `setup_performance` for it.
        "by_setup": breakdown(setup_performance(df), "setup_type", complete=complete),
        "by_asset": breakdown(by_asset(df), "asset", complete=complete),
        "by_strategy": breakdown(by_strategy(df), "strategy_used", complete=complete),
        "by_timeframe": breakdown(by_timeframe(df), "timeframe", complete=complete),
        "by_confirmation": breakdown(
            confirmation_model_performance(df), "confirmation_model", complete=complete
        ),
        "mistakes": _mistakes(mistake_frequency(df)),
    }


def build_discipline(df: pd.DataFrame) -> Dict[str, Any]:
    """Rule adherence and consistency — the process figures."""
    if df.empty:
        return {
            "rule_adherence": dict(_UNDEFINED_NO_SAMPLE),
            "consistency": dict(_UNDEFINED_NO_SAMPLE),
            "edge_leak": dict(_UNDEFINED_NO_SAMPLE),
            "recorded_trades": 0,
        }

    adherence = rule_adherence_rate(df)
    leak = edge_leak_summary(df)
    # `.recorded`, VERIFIED — the field is NOT `recorded_trades`, and a
    # `getattr(..., "recorded_trades", 0)` default would have made rule
    # adherence permanently "no data" while looking careful. That is the
    # `.get(key, 0.0)` disease wearing a different hat.
    recorded = int(adherence.recorded)

    return {
        # A blank `followed_rules` is not a violation. Gating on the RECORDED
        # count, not the row count, is what stops an unfilled field reading
        # as 0% discipline.
        "rule_adherence": sample_pair(adherence.rate, recorded < 1),
        "consistency": sample_pair(
            consistency_score(df), insufficient_for(df, MIN_CONSISTENCY_TRADES)
        ),
        "edge_leak": money_pair(
            total_edge_leak(df),
            complete=pnl_is_complete(df) and int(leak.qualifying_trades) > 0,
        ),
        "recorded_trades": recorded,
    }


def _mistakes(built: pd.DataFrame) -> List[Dict[str, Any]]:
    """VERIFIED: `mistake_frequency` emits `mistake_tag/count/total_pnl/avg_pnl`."""
    if built is None or built.empty:
        return []
    return [
        {"tag": str(row["mistake_tag"]), "count": int(row["count"])}
        for _, row in built.iterrows()
    ]
```

> Column names here are VERIFIED too — see the table in Task A2. Two traps this task walks into if they are not respected: `by_setup_type` carries **no** `total_pnl` or `win_rate` (use `setup_performance`), and `RuleAdherenceSummary` exposes `.recorded`, **not** `.recorded_trades`. Both were wrong in this plan's first draft, and both fail silently — a defaulted `getattr` turns a typo into "no data" that looks like a careful undefined state.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_analytics_service.py -v`
Expected: PASS.

- [ ] **Step 5: Mutate and confirm**

| Mutation | Expected failing test |
|---|---|
| `comparable` hardcoded `True` | `test_a_breakdown_reports_whether_it_can_be_compared` |
| `rule_adherence` gated on `len(df)` instead of `recorded` | `test_rule_adherence_over_rows_that_never_recorded_it_is_undefined` |
| `consistency` uses `pair` instead of `sample_pair` | `test_consistency_below_five_trades_is_undefined_not_zero` |
| `breakdown` rows use `pair` for `total_pnl` | `test_a_breakdown_row_with_no_pnl_carries_an_undefined_total` |

- [ ] **Step 6: Commit**

```bash
git add src/tradelens/services/analytics.py tests/test_analytics_service.py
git commit -m "feat(analytics): timing, setups and discipline projections"
```

---

### Task A4: The parity harness

**Files:**
- Create: `tests/test_analytics_parity.py`

**Interfaces:**
- Consumes: everything from A1–A3; `services/metrics` directly.
- Produces: no source symbols — this task's deliverable is the proof.

This is the most valuable test in the phase. It is the only thing that catches a projection that quietly re-derives a figure instead of reading it, and it is what makes "metric parity" a fact rather than an intention.

- [ ] **Step 1: Write the failing test**

Create `tests/test_analytics_parity.py`:

```python
"""The API's figures and `services/metrics`' figures are the same figures.

A trader with the Streamlit page and the new page open must not see two
different win rates. There is no way for them to tell which one is lying, so
the only acceptable difference is none.

This compares the PROJECTION against the metric functions directly, field by
field, over one shared frame. It is deliberately not a snapshot test: a
snapshot pins whatever the code currently does, including a mistake, whereas
this pins the projection to its source of truth.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.tradelens.services import analytics as an
from src.tradelens.services import metrics as m


def _mixed_frame():
    """A sample with wins, losses, a breakeven, two setups and two sessions."""
    rows = []
    for index, (result, pnl, setup, session) in enumerate(
        [
            ("Win", 250.0, "FVG", "New York"),
            ("Loss", -120.0, "FVG", "London"),
            ("Win", 480.0, "OB", "New York"),
            ("Breakeven", 0.0, "OB", "London"),
            ("Loss", -75.0, "FVG", "New York"),
            ("Win", 310.0, "OB", "New York"),
        ]
    ):
        rows.append(
            {
                "id": index + 1,
                "trade_date": f"2026-09-0{index + 1}",
                "asset": "NQ",
                "direction": "Long",
                "result": result,
                "pnl": pnl,
                "rr_realized": round(pnl / 100.0, 2),
                "rr_planned": 2.0,
                "session": session,
                "killzone": "ny_am",
                "setup_type": setup,
                "confirmation_model": "BOS",
                "strategy_used": "ICT",
                "timeframe": "5m",
                "day_of_week": "Tuesday",
                "entry_time": "09:35",
                "followed_rules": 1,
                "mistake_tags": "[]",
            }
        )
    return pd.DataFrame(rows)


def test_headline_performance_figures_match_the_metric_functions():
    df = _mixed_frame()
    basic = m.compute_basic_metrics(df)
    built = an.build_performance(df)

    assert built["total_pnl"]["value"] == pytest.approx(basic["total_pnl"])
    assert built["win_rate"]["value"] == pytest.approx(basic["win_rate"])
    assert built["expectancy"]["value"] == pytest.approx(m.compute_expectancy(basic))
    assert built["profit_factor"]["value"] == pytest.approx(
        m.compute_profit_factor_raw(df)
    )
    assert built["total_trades"] == len(df)


def test_risk_figures_match_the_metric_functions():
    df = _mixed_frame()
    built = an.build_risk(df)

    assert built["max_drawdown"]["value"] == pytest.approx(
        m.compute_max_drawdown(m.compute_equity_curve(df))
    )
    assert len(built["drawdown_series"]) == len(m.drawdown_series(df))


def test_every_breakdown_matches_its_metric_function_row_for_row():
    """Row counts AND per-row totals, for all four timing breakdowns.

    A projection that dropped a category, reordered rows, or summed a column
    itself would pass a count-only check.
    """
    df = _mixed_frame()
    built = an.build_timing(df)

    for wire_key, metric_fn, column in (
        ("by_day_of_week", m.by_day_of_week, "day_of_week"),
        ("by_session", m.by_session, "session"),
        ("by_killzone", m.killzone_performance, "killzone"),
    ):
        source = metric_fn(df)
        rows = built[wire_key]["rows"]
        assert len(rows) == len(source), wire_key
        for wire_row, (_, source_row) in zip(rows, source.iterrows()):
            assert wire_row["key"] == str(source_row[column]), wire_key
            if "total_pnl" in source.columns:
                assert wire_row["total_pnl"]["value"] == pytest.approx(
                    source_row["total_pnl"]
                ), wire_key


def test_the_setups_breakdown_matches_row_for_row():
    df = _mixed_frame()
    source = m.by_setup_type(df)
    rows = an.build_setups(df)["by_setup"]["rows"]

    assert len(rows) == len(source)
    assert [r["key"] for r in rows] == [str(v) for v in source["setup_type"]]


def test_discipline_figures_match_the_metric_functions():
    df = _mixed_frame()
    built = an.build_discipline(df)

    assert built["consistency"]["value"] == pytest.approx(m.consistency_score(df))
    assert built["edge_leak"]["value"] == pytest.approx(m.total_edge_leak(df))


def test_no_projected_figure_is_computed_rather_than_read():
    """A structural guard, not a value check.

    `services/analytics` must contain no arithmetic on money: no `sum(`,
    no `/ len(`, no `mean()`. Every number is read from a metric function.
    A formula here would be a second implementation, and the two would
    diverge the first time either changed.
    """
    import inspect

    source = inspect.getsource(an)
    for forbidden in ("sum(", ".mean()", ".sum()", "/ len(", "* 100"):
        assert forbidden not in source, f"analytics computes: {forbidden}"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_analytics_parity.py -v`
Expected: FAIL on any projection that does not yet match. **Fix the projection, never the metric function or the assertion.** If a parity test cannot be made to pass without editing `services/metrics.py`, stop and report it — that is a finding about the metric, not a licence to change it.

- [ ] **Step 3: Make the projections match**

No new code; adjust `services/analytics.py` until every field matches its source. Where a mismatch reveals that a metric returns a different column name than assumed, fix the projection's column name.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_analytics_parity.py tests/test_analytics_service.py -v`
Expected: PASS.

- [ ] **Step 5: Mutate and confirm the harness actually bites**

| Mutation | Expected failing test |
|---|---|
| `build_performance` returns `pair(basic["total_pnl"] * 1.01)` | `test_headline_performance_figures_match_the_metric_functions` |
| `breakdown` drops the last row (`rows[:-1]`) | `test_every_breakdown_matches_its_metric_function_row_for_row` |
| `build_discipline` recomputes consistency as `len(df) * 10` | `test_discipline_figures_match_the_metric_functions` |
| Add `total = sum(df["pnl"])` to `services/analytics.py` | `test_no_projected_figure_is_computed_rather_than_read` |

The last one is the structural guard. Confirm it fails, then restore.

- [ ] **Step 6: Commit**

```bash
git add tests/test_analytics_parity.py
git commit -m "test(analytics): parity harness against services/metrics"
```

**Group A review gate.** Deepest review in the phase. Financial correctness is the boundary: verify every figure's undefined state, the parity harness, and that no formula was reimplemented.

---

## Group B — the analytics endpoint

### Task B1: The response contract

**Files:**
- Create: `src/tradelens/api/schemas/analytics.py`
- Test: `tests/test_api_analytics.py`

**Interfaces:**
- Consumes: `api/schemas/overview.UndefinedState` and its `_Strict` base — import them rather than redefining; two definitions of "undefined" would eventually disagree.
- Produces: `MetricValue`, `SeriesPoint`, `BreakdownRow`, `Breakdown`, `PerformanceLens`, `RiskLens`, `TimingLens`, `SetupsLens`, `DisciplineBlock`, `AnalyticsResponse`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_analytics.py`:

```python
"""`GET /v1/analytics` — one owner, one period, one filtered sample."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api.security import sign_request
from src.tradelens.services import trade_service

SECRET = "test-service-secret-value-at-least-32-bytes"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TL_SERVICE_SECRET", SECRET)
    monkeypatch.delenv("TL_SERVICE_SECRET_PREVIOUS", raising=False)
    monkeypatch.setenv("TL_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@example.invalid/tradelens?sslmode=require",
    )
    return TestClient(create_app(), raise_server_exceptions=False)


def _headers(handle: str, method: str, path: str, query: str = "") -> dict:
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, method, path, query, b"")
    return {
        "X-TL-Signature": f"v1={ts}:{sig}",
        "X-TL-Session-Handle": handle,
    }


def _get(client, handle, query: str):
    path = "/v1/analytics"
    return client.get(f"{path}?{query}", headers=_headers(handle, "GET", path, query))


def _seed(user_id: int, *, pnl=250.0, asset="NQ", session="New York"):
    return trade_service.create_trade(
        {
            "asset": asset,
            "trade_date": "2026-09-01",
            "result": "Win",
            "pnl": pnl,
            "session": session,
            "setup_type": "FVG",
        },
        user_id=user_id,
    )


def test_the_response_carries_every_numeric_field_as_value_and_state(
    client, website_session_handle
):
    """No bare floats on the wire.

    A field typed as a plain number is a field that will eventually carry a
    fabricated zero, because there is nowhere else for "not measurable" to go.
    """
    owner, handle = website_session_handle
    _seed(owner)

    body = _get(client, handle, "from=2026-09-01&to=2026-09-30").json()

    for field in ("total_pnl", "win_rate", "expectancy", "profit_factor"):
        assert set(body["performance"][field]) == {"value", "state"}


def test_another_owner_s_trades_never_appear_in_this_owner_s_analytics(
    client, website_session_handle, two_users
):
    """Tenant isolation on an aggregate is easy to get wrong and invisible
    when it fails: the number is merely larger, not obviously foreign."""
    owner, handle = website_session_handle
    other = next(u for u in two_users if u != owner)
    _seed(owner, pnl=100.0)
    _seed(other, pnl=9999.0)

    body = _get(client, handle, "from=2026-09-01&to=2026-09-30").json()

    assert body["performance"]["total_pnl"]["value"] == pytest.approx(100.0)
    assert body["performance"]["total_trades"] == 1


def test_a_malformed_period_is_refused(client, website_session_handle):
    _owner, handle = website_session_handle
    assert _get(client, handle, "from=2026-9-1&to=2026-09-30").status_code == 422


def test_an_inverted_period_is_refused(client, website_session_handle):
    _owner, handle = website_session_handle
    assert _get(client, handle, "from=2026-09-30&to=2026-09-01").status_code == 422


def test_a_filter_actually_narrows_the_sample(client, website_session_handle):
    """A filter that round-trips into the URL but is not applied is the
    failure Phase 3 already shipped once."""
    owner, handle = website_session_handle
    _seed(owner, asset="NQ", pnl=100.0)
    _seed(owner, asset="ES", pnl=500.0)

    body = _get(client, handle, "from=2026-09-01&to=2026-09-30&asset=NQ").json()

    assert body["performance"]["total_trades"] == 1
    assert body["performance"]["total_pnl"]["value"] == pytest.approx(100.0)


def test_an_empty_period_reports_undefined_rather_than_zeroes(
    client, website_session_handle
):
    owner, handle = website_session_handle
    _seed(owner)

    body = _get(client, handle, "from=2020-01-01&to=2020-01-31").json()

    assert body["performance"]["total_trades"] == 0
    assert body["performance"]["total_pnl"]["value"] is None
    assert body["performance"]["total_pnl"]["state"] is not None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/bin/pytest tests/test_api_analytics.py -v`
Expected: FAIL — 404 on an unregistered route.

- [ ] **Step 3: Implement the schemas**

Create `src/tradelens/api/schemas/analytics.py`:

```python
"""The analytics wire contract.

Every numeric field is `{value, state}`. That is not defensive style — it is
the type making a fabricated zero unrepresentable. A field typed as a bare
`float` has nowhere to put "not measurable", so it eventually puts a zero
there, and a zero on a trading dashboard is a claim about someone's money.

`UndefinedState` and `_Strict` are imported from the overview contract rather
than redefined: two definitions of "undefined" would drift apart, and then
two pages would disagree about what a missing figure looks like.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import ConfigDict, Field

from src.tradelens.api.schemas.overview import UndefinedState, _Strict


class MetricValue(_Strict):
    value: Optional[float]
    state: Optional[UndefinedState]


class SeriesPoint(_Strict):
    date: str
    value: float


class HistogramBucket(_Strict):
    label: str
    count: int


class MistakeCount(_Strict):
    tag: str
    count: int


class BreakdownRow(_Strict):
    key: str
    trades: int
    total_pnl: MetricValue
    win_rate: MetricValue


class Breakdown(_Strict):
    """A category breakdown, plus whether it can honestly be compared.

    `comparable` is decided server-side by `sample_policy.enough_categories`.
    One category is not a ranking, and letting the browser decide that would
    put the rule in two places.
    """

    rows: List[BreakdownRow]
    comparable: bool


class StreakBlock(_Strict):
    current: MetricValue
    max_win: MetricValue
    max_loss: MetricValue


class PerformanceLens(_Strict):
    total_pnl: MetricValue
    win_rate: MetricValue
    expectancy: MetricValue
    profit_factor: MetricValue
    total_trades: int
    equity_curve: List[SeriesPoint]
    daily_pnl: List[SeriesPoint]
    streaks: StreakBlock


class RiskLens(_Strict):
    max_drawdown: MetricValue
    drawdown_series: List[SeriesPoint]
    r_multiples: List[HistogramBucket]
    avg_win: MetricValue
    avg_loss: MetricValue


class TimingLens(_Strict):
    by_day_of_week: Breakdown
    by_session: Breakdown
    by_killzone: Breakdown


class SetupsLens(_Strict):
    by_setup: Breakdown
    by_asset: Breakdown
    by_strategy: Breakdown
    by_timeframe: Breakdown
    by_confirmation: Breakdown
    mistakes: List[MistakeCount]


class DisciplineBlock(_Strict):
    rule_adherence: MetricValue
    consistency: MetricValue
    edge_leak: MetricValue
    recorded_trades: int


class AnalyticsPeriod(_Strict):
    from_: str = Field(alias="from")
    to: str

    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class AnalyticsResponse(_Strict):
    """Everything the four lenses need, over one sample.

    One response rather than four: the lenses answer four questions about the
    SAME filtered sample, and separate requests would give four chances for
    one of them to be computed over a slightly different frame.
    """

    period: AnalyticsPeriod
    filters: Dict[str, str]
    performance: PerformanceLens
    risk: RiskLens
    timing: TimingLens
    setups: SetupsLens
    discipline: DisciplineBlock
```

- [ ] **Step 4: Implement the route**

Create `src/tradelens/api/routers/analytics.py`:

```python
"""`GET /v1/analytics` — the four lenses over one owner's filtered sample."""

from __future__ import annotations

from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query

from src.tradelens.api.deps import current_user
from src.tradelens.api.routers.overview import _validated_period
from src.tradelens.api.schemas.analytics import AnalyticsResponse
from src.tradelens.services import analytics
from src.tradelens.services.trade_service import get_trades

router = APIRouter(prefix="/v1", tags=["analytics"])


@router.get("/analytics")
def get_analytics(
    from_: str = Query(alias="from"),
    to: str = Query(),
    asset: Optional[str] = Query(default=None),
    session: Optional[str] = Query(default=None),
    strategy: Optional[str] = Query(default=None),
    user_id: int = Depends(current_user),
) -> AnalyticsResponse:
    """Every figure the four lenses need, for this owner and this window.

    Owner comes from the session and from nowhere else. The filters narrow
    the sample SERVER-SIDE: a filter applied only in the browser would show a
    win rate computed over rows the trader cannot see on the page.
    """
    start, end = _validated_period(from_, to)
    trades = get_trades(user_id=user_id, start_date=start, end_date=end)

    df = analytics.frame(trades)
    applied: Dict[str, str] = {}
    for name, value in (("asset", asset), ("session", session), ("strategy", strategy)):
        if value:
            applied[name] = value
    df = analytics.apply_filters(df, applied)

    return AnalyticsResponse(
        period={"from": start, "to": end},
        filters=applied,
        performance=analytics.build_performance(df),
        risk=analytics.build_risk(df),
        timing=analytics.build_timing(df),
        setups=analytics.build_setups(df),
        discipline=analytics.build_discipline(df),
    )
```

Add `apply_filters` to `services/analytics.py`:

```python
_FILTER_COLUMNS = {
    "asset": "asset",
    "session": "session",
    "strategy": "strategy_used",
}


def apply_filters(df: pd.DataFrame, filters: Dict[str, str]) -> pd.DataFrame:
    """Narrow the sample by the allowlisted filters, server-side.

    An allowlist, not a passthrough: a caller must not be able to name an
    arbitrary column, and the wire names (`strategy`) deliberately differ
    from the column names (`strategy_used`) so the browser is not writing
    schema into a query string.
    """
    if df.empty:
        return df
    narrowed = df
    for name, value in filters.items():
        column = _FILTER_COLUMNS.get(name)
        if column is None or column not in narrowed.columns:
            continue
        narrowed = narrowed[narrowed[column] == value]
    return narrowed
```

Register the router in `src/tradelens/api/app.py` beside the existing ones.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/test_api_analytics.py -v`
Expected: PASS.

- [ ] **Step 6: Mutate and confirm**

| Mutation | Expected failing test |
|---|---|
| `get_trades(user_id=1, ...)` — owner hardcoded | `test_another_owner_s_trades_never_appear_in_this_owner_s_analytics` |
| `apply_filters` returns `df` unchanged | `test_a_filter_actually_narrows_the_sample` |
| `_validated_period` replaced by `return from_, to` | `test_a_malformed_period_is_refused` and `test_an_inverted_period_is_refused` |
| `_FILTER_COLUMNS` replaced by `{name: name for name in filters}` | add `test_a_filter_cannot_name_an_arbitrary_column` first, then mutate |

- [ ] **Step 7: Regenerate the contract and commit**

```bash
.venv/bin/python scripts/generate_openapi.py
cd web && npm run api:types && cd ..
git add src/tradelens/api tests/test_api_analytics.py web/lib/api/
git commit -m "feat(api): GET /v1/analytics over one owner's filtered sample"
```

**Group B review gate.** Deep review: tenant isolation on an aggregate, filter allowlisting, period validation.

---

## Group C — the four lenses

### Task C1: The relay and the metric-value renderer

**Files:**
- Create: `web/lib/app/analytics-relay.ts`, `web/lib/app/analytics.ts`, `web/app/api/analytics/route.ts`
- Create: `web/components/app/analytics/metric-value.tsx`
- Test: `web/__tests__/analytics-relay.test.ts`, `web/__tests__/metric-value.test.tsx`

**Interfaces:**
- Consumes: `authenticateSessionToken`, `sessionTokenFrom`, `appLayoutRedirect`, `isSameOriginRequest`, `optionalEnv`; generated `AnalyticsResponse` type.
- Produces: `authorizeAnalyticsRelay(request)`, `ANALYTICS_NO_STORE`, `fetchAnalytics(token, params)`, `<MetricValueText value={MetricValue} kind="money"|"percent"|"ratio"|"number" />`.

- [ ] **Step 1: Write the failing test**

Create `web/__tests__/metric-value.test.tsx`:

```tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetricValueText } from "@/components/app/analytics/metric-value";

/**
 * The single place an undefined figure becomes text. Every rule about
 * never showing a fabricated zero ends here, so this is where it is pinned.
 */
describe("MetricValueText", () => {
  it("renders a measured zero as zero, because that is a real result", () => {
    render(<MetricValueText value={{ value: 0, state: null }} kind="money" />);
    expect(screen.getByText("$0.00")).toBeInTheDocument();
  });

  it("never renders an undefined figure as a number", () => {
    render(
      <MetricValueText
        value={{ value: null, state: "undefined_no_sample" }}
        kind="money"
      />,
    );
    expect(screen.queryByText(/\$0/)).not.toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("says WHY a figure is missing, not just that it is", () => {
    render(
      <MetricValueText
        value={{ value: null, state: "undefined_incomplete_sample" }}
        kind="money"
      />,
    );
    // The distinction a trader needs: nothing to measure vs. rows that did
    // not record it. "—" alone leaves them unable to act.
    expect(screen.getByTitle(/not every trade in this range records/i)).toBeInTheDocument();
  });

  it("names an infinite profit factor rather than printing a symbol", () => {
    render(
      <MetricValueText
        value={{ value: null, state: "undefined_positive_infinity" }}
        kind="ratio"
      />,
    );
    expect(screen.getByText(/no losing trades/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run __tests__/metric-value.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `web/components/app/analytics/metric-value.tsx` rendering `{value, state}`:

- a non-null `value` formats by `kind` (`money` via `lib/app/format`, `percent`, `ratio`, `number`);
- a null `value` renders `—` with a `title` explaining the state, mapping each `UndefinedState` to a plain sentence: `undefined_no_sample` → "No trades in this range to measure this."; `undefined_incomplete_sample` → "Not every trade in this range records this, so a total would be misleading."; `undefined_positive_infinity` → "No losing trades in this range, so there is no ratio to report."; `undefined_negative_infinity` → the mirror; `undefined_nan` → "This could not be computed from the trades in this range.";
- **no branch may produce `0`, `0.00`, `$0.00`, `0%` or `N/A` for a null value.**

Create the relay files mirroring `trade-analysis-relay.ts` exactly: fail shut when `SITE_ORIGIN` is unset, `no-store`, `nodejs`, `force-dynamic`, and forward only the backend's status.

- [ ] **Step 4: Run the tests**

Run: `cd web && npx vitest run __tests__/metric-value.test.tsx __tests__/analytics-relay.test.ts`
Expected: PASS.

- [ ] **Step 5: Mutate and confirm**

| Mutation | Expected failing test |
|---|---|
| null `value` renders `formatMoney(0)` | `never renders an undefined figure as a number` |
| the `title` explanation is dropped | `says WHY a figure is missing, not just that it is` |
| relay `!siteOrigin \|\|` → `siteOrigin &&` | `refuses with 403 when SITE_ORIGIN is unset` |

- [ ] **Step 6: Commit**

```bash
git add web/lib/app/analytics-relay.ts web/lib/app/analytics.ts web/app/api/analytics web/components/app/analytics/metric-value.tsx web/__tests__/analytics-relay.test.ts web/__tests__/metric-value.test.tsx
git commit -m "feat(web): analytics relay and the undefined-safe metric renderer"
```

---

### Task C2: The lens shell, filters and the four panels

**Files:**
- Create: `web/lib/app/analytics-filters.ts`, `web/components/app/analytics/lens-tabs.tsx`, `web/components/app/analytics/{performance,risk,timing,setups}-lens.tsx`
- Modify: `web/app/app/analytics/page.tsx`
- Test: `web/__tests__/analytics-page.test.tsx`, `web/__tests__/analytics-lenses.test.tsx`

**Interfaces:**
- Consumes: `fetchAnalytics`, `MetricValueText` (C1); `readPeriod` from `lib/app/period`; `TRADE_FILTER_KEYS` helpers from `lib/app/trade-filters`.
- Produces: `<LensTabs active lens />`, one component per lens, `readAnalyticsFilters(params)` / `writeAnalyticsFilters(...)`.

Requirements each test must pin:

1. **Exactly one date control on the page.** The period lens is chrome; this page renders **no** date input, preset row or range picker of its own. Assert on the absence: querying for any `type="date"` input or a preset labelled like the period presets inside the analytics region returns nothing.
2. The active lens lives in the URL, so a lens is linkable and survives a refresh.
3. Filters (`asset`, `session`, `strategy`) live in the URL beside the period and are sent to the API.
4. A period with no trades renders the empty state, not four lenses of dashes.
5. An undefined figure renders through `MetricValueText`, never as a locally formatted number — assert no lens formats a number itself.
6. A breakdown with `comparable: false` renders **without** ranking language ("best", "strongest", "top"), and says why one category cannot be compared.
7. The prior-period comparison, if shown, is labelled with its actual dates and is **derived**, never selectable.

- [ ] **Step 1–6:** Write the failing tests first, run them, implement, run, mutate each of the seven properties above and confirm a named test fails, commit.

```bash
git add web/lib/app/analytics-filters.ts web/components/app/analytics web/app/app/analytics/page.tsx web/__tests__/analytics-page.test.tsx web/__tests__/analytics-lenses.test.tsx
git commit -m "feat(web): the four analytics lenses over one period"
```

**Group C review gate.** Light at the boundary, except the low-sample and incomplete-P&L states, which get a deep pass.

---

## Group D — charts, tables and responsive behaviour

### Task D1: Charts and responsive tables

**Files:**
- Create: `web/components/app/analytics/{bar-chart,distribution-chart,breakdown-table}.tsx`
- Test: `web/__tests__/analytics-charts.test.tsx`

**Interfaces:**
- Consumes: `buildCurvePath` from `components/app/overview/equity-curve` for line geometry; `MetricValueText`.
- Produces: `<BarChart rows />`, `<DistributionChart buckets />`, `<BreakdownTable breakdown />`.

Requirements each test must pin:

1. **A chart with no plottable points renders an explanation, not an empty axis.** An empty chart frame reads as "zero", which is a claim.
2. **A gap in a series is a gap.** A missing point is not interpolated and not drawn as zero — assert the path has a break, or the point is absent.
3. Bars scale from a real maximum; a single-category breakdown does not render a full-width bar implying dominance.
4. A negative value renders on the correct side of zero, and the axis includes zero when values straddle it.
5. **Every table scrolls inside its own container** — the page body never scrolls horizontally at 375px.
6. Numbers use the tabular/mono treatment the rest of the app uses, so columns align.

- [ ] **Step 1–6:** Failing tests first; implement; mutate each property (invert the y axis, interpolate a gap, hardcode the bar maximum, drop the scroll container) and confirm a named test fails; commit.

```bash
git add web/components/app/analytics web/__tests__/analytics-charts.test.tsx
git commit -m "feat(web): analytics charts and responsive breakdown tables"
```

**Group D review gate.** Light at the group boundary.

---

## Group E — verification, parity run and handoff

### Task E1: Full gates, mutation re-run, and the handoff

**Files:**
- Modify: `docs/coordination/CLAUDE_CODEX_HANDOFF.md`

- [ ] **Step 1: Run every gate and record the real numbers**

```bash
.venv/bin/pytest tests/ -q
.venv/bin/ruff check src/ scripts/
.venv/bin/black --check src/ scripts/ tests/
.venv/bin/python -m alembic heads
```

```bash
cd web && npx vitest run && npx tsc --noEmit && npx eslint .
```

```bash
cd web && SITE_ORIGIN=https://tradelens.ai APP_ORIGIN=https://app.tradelens.ai SUPPORT_EMAIL=support@tradelens.ai npm run build
```

**Expect two known failures** in `tests/test_pages_boot.py` (the analytics Streamlit page-boot tests described under Scope). They are pre-existing and environment-sensitive. Record them as such; do not fix them. If the count of failures is anything other than those exact two, that is a regression from this phase.

- [ ] **Step 2: Confirm no API contract drift**

```bash
.venv/bin/python scripts/generate_openapi.py
cd web && npm run api:types && cd ..
git status --short
```
Expected: clean.

- [ ] **Step 3: Confirm no Streamlit import leaked into the server**

```bash
.venv/bin/python - <<'PY'
import pkgutil, subprocess, sys
import src.tradelens as pkg

bad = []
for mod in pkgutil.walk_packages(pkg.__path__, "src.tradelens."):
    if not mod.name.startswith(
        ("src.tradelens.services", "src.tradelens.db", "src.tradelens.api")
    ):
        continue
    code = f"import {mod.name}, sys; sys.exit(1 if 'streamlit' in sys.modules else 0)"
    if subprocess.run([sys.executable, "-c", code]).returncode:
        bad.append(mod.name)
print("LEAKS:", bad or "none")
PY
```
Expected: `LEAKS: none`. A fresh subprocess per module — importing them all in one process cannot tell you which one pulled Streamlit in.

- [ ] **Step 4: Confirm `services/metrics.py` is byte-untouched**

```bash
git diff --stat $(git merge-base HEAD origin/main)..HEAD -- src/tradelens/services/metrics.py
```
Expected: **no output.** Any change here means parity was broken rather than proven, and it must be reverted and re-derived through the projection.

- [ ] **Step 5: Re-run every mutation from Groups A–D**

Roughly twenty-five across the phase. For each: apply, run, record the **named** failing test, restore, confirm `git diff` is empty. A mutation you could not actually run is a mutation you did not run — say so rather than reporting it as caught.

- [ ] **Step 6: Browser smoke at desktop and 375px**

Start the dev server and check, at both widths: the four lenses render; exactly one date control exists on the page; a period with no trades shows the empty state; an undefined figure shows `—` with its explanation rather than a zero; tables scroll inside their own containers and the body does not scroll horizontally. Record what you saw. **This is a smoke, not one of the six deployment gates**; those stay open.

- [ ] **Step 7: Write the handoff section**

Append a `# Phase 6 — Analytics` section recording: branch and ancestry; the real gate numbers; the mutation table with test names; the parity harness result; anything found and fixed; anything deliberately left; the two known pre-existing `test_pages_boot.py` failures with the evidence that they predate this work; and an explicit restatement that **the six pre-deployment gates remain open and were not this phase's to close**.

- [ ] **Step 8: Commit**

```bash
git add docs/coordination/CLAUDE_CODEX_HANDOFF.md
git commit -m "docs(handoff): Phase 6 record"
```

---

## Self-review

**1. Spec coverage.** Every item in the owner's brief and the spec's Analytics inventory maps to a task:

| Requirement | Task |
|---|---|
| performance over time (equity curve, daily P&L) | A2, C2, D1 |
| asset/setup/session/killzone breakdowns | A3, C2, D1 (hour-of-day removed — see Scope) |
| mistake and confirmation analysis | A3 (`mistakes`, `by_confirmation`), C2 |
| rule adherence / discipline | A3 (`build_discipline`), C2 |
| expectancy, win rate, P&L, drawdown | A2 |
| date/filter interactions | B1 (`apply_filters`), C2 |
| low-sample and incomplete-P&L states | A1–A3 (`sample_pair`, `money_pair`, `comparable`), C1, C2 |
| responsive chart/table behaviour | D1 |
| exact tenant isolation | B1 |
| no duplicate conflicting time controls | C2 property 1, design decision 5 |
| reuse existing metric services | A1–A4, enforced structurally by `test_no_projected_figure_is_computed_rather_than_read` |
| undefined never silently zero | A1 (the whole task), C1 |
| fixtures checked against the real backend contract | A4 (parity harness), B1 (strict schema), E1 step 2 (drift) |
| six deployment gates untouched | Scope, E1 step 7 |

Spec inventory items not separately tasked and why: `emotion_vs_rr` and `trade_of_the_week` are in the spec's list but not in the owner's brief; they are **deliberately deferred** — say so at the Group C gate rather than silently dropping them. `period_deltas` is covered by design decision 5 (derived prior period) and surfaces in C2 property 7.

**2. Placeholder scan.** Groups C2 and D1 give numbered behavioural requirements plus a mutation per property rather than full component source. That is deliberate for presentation code whose markup depends on tokens the implementer will read from neighbouring components — but each requirement is falsifiable and paired with a named mutation, which is the part that matters. Every Python task carries real code. No "TBD", no "add error handling", no "similar to Task N".

**3. Type consistency.** `pair`/`undefined`/`money_pair`/`sample_pair`/`need`/`frame` are defined in A1 and used in A2, A3, B1. `breakdown(built, key_column, *, complete)` is defined in A3 and used by `build_timing` and `build_setups`. `MetricValue` in B1 matches the `{value, state}` dicts the service emits. `apply_filters` is introduced in B1 alongside the route that calls it. `buildCurvePath` is reused from Overview rather than redefined.

**Three issues found and fixed while reviewing:**

- A2's first draft called `compute_expectancy(df)`. It takes the **metrics dict**, not the frame — a wrong call that would have raised or, worse, silently produced a different number. The test now pins the call shape as well as the value.
- A2 and A3 originally trusted my memory of metric column names. Phase 2 lost real time to exactly that (six wrong names, five of which the plan's `.get(col, 0.0)` would have rendered as `$0.00`). Both tasks now carry an explicit instruction to verify every key and column against real function output before trusting the code.
- The plan initially had no test for the *opposite* error. Over-gating is as wrong as under-gating: a trader who genuinely broke even measured `0.00`, and reporting that as "no data" erases a real result. `test_a_measured_zero_pnl_is_not_reported_as_undefined` was added.

**One thing worth the reviewer's attention, stated rather than hidden:** `test_no_projected_figure_is_computed_rather_than_read` scans source text for `sum(`, `.mean()` and similar. It is a blunt instrument — it will fire on a harmless `sum()` over a list of row counts, and it can be evaded by anyone determined to. It is in the plan because the alternative is trusting that nobody reimplements a formula, and this phase's whole premise is that the two surfaces must agree to the cent. Treat a failure as a prompt to justify the arithmetic, not as a rule to route around.
