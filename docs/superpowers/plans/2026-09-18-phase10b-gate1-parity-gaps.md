# Phase 10B — Gate 1 parity gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three confirmed functional parity gaps that block Phase 10 Gate 1 — Overview asset filtering, screenshot upload on an already-saved trade, and emotion vs R-multiple in Analytics — so the R1 ledger can mark each `implemented` with a behavioural test.

**Architecture:** Each gap reuses machinery that already exists and is tested. Task 1 threads one optional `asset` filter through the Overview API into `build_overview`, applying it to the period frame only — lifetime activation and today/this-week reads stay unfiltered, so a scoped view never claims the account is empty. Task 2 adds no new endpoint: the trade-detail page mounts the existing `ScreenshotUpload` island against the existing owner-scoped presign → PUT → finalize relay. Task 3 surfaces the existing `metrics.emotion_vs_rr` through the Setups lens (where Streamlit's emotion panel lived) and renders it with the existing breakdown component.

**Tech Stack:** FastAPI · Pydantic v2 (strict) · SQLAlchemy 2.x · pandas · Next.js 16 App Router · TypeScript · pytest · Vitest

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md` §8 (Overview "filter panel"; Journal/Trades "per-trade screenshot upload"; Analytics "emotion vs RR") and §11.1. Parent: `docs/superpowers/plans/2026-09-14-nextjs-migration-phase10-streamlit-retirement.md` (Task R1, decision T8). Evidence of each gap: `docs/superpowers/parity/2026-09-14-phase10-parity-ledger.md`.

## Global Constraints

- Owner identity only from the authenticated session row. No request field names an owner; foreign and missing are identical.
- Service-layer isolation via `services/ownership.require_user_id`; every query owner-scoped.
- Next.js is the BFF: relays are same-origin, `no-store`, fail shut when `SITE_ORIGIN` is unset **before** the session lookup, and gate on `appLayoutRedirect`.
- Request schemas are strict positive allowlists (`extra="forbid"`, `strict=True`); unknown query parameters are refused with 422 (the Analytics router's `_refuse_unknown_params` rule).
- **Financial correctness:** a filter narrows what it claims to narrow and nothing else. Activation, "today" and "this week" are lifetime concepts and stay unfiltered. A filter that matches nothing renders an explicit empty-scope state, never a strip of zeros that reads as a flat account.
- `prompts/` locked; `services/metrics.py` **read-only** (reuse `emotion_vs_rr`, do not edit); parity snapshots untouched and never refreshed.
- Python 3.9.6 floor (`Optional[X]`, no `X | Y`). **No new Python or npm dependencies. No schema migration**; alembic head stays `h4i5j6k7l8m9`.
- AI copy rules unchanged: reflection only, never signals, predictions or advice.
- Gates per task: `pytest tests/ -q` for touched suites; `pytest tests/parity -q`; `ruff check src/ scripts/`; `black --check src/ scripts/ tests/`; in `web/`: `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build`; `scripts/generate_openapi.py` from the repo root + `npm --prefix web run api:types` leave no diff.
- **Mutation discipline** (hardened harness, Phase 9/10A): CAUGHT only when the intended tests collected, ran and at least one FAILED; ERROR / NOT-RUN / NOT-APPLIED never count; verdict controls first; final battery from a clean HEAD with sha256-verified restores.
- Independent review before merge, in a private `git archive` extraction. **Do not merge; stop at the review boundary.**
- Nothing here flips accounts, removes Streamlit, drops tables or touches Streamlit Cloud. The six pre-release gates stay open.

---

## What already exists — read before writing anything

Verified on `worktree-phase10-readiness` at `28e3ed5`:

- **Overview.** `api/routers/overview.py:71-85` — `get_overview(from_, to, user_id)` validates the period with `_validated_period` and calls `services/overview.build_overview(user_id=, start=, end=)` (`services/overview.py:157`). That function reads the period frame **and** a second unfiltered lifetime frame for activation and today/this-week. Streamlit's equivalent (`ui/app.py:472-506`) offered an **asset** selectbox built from the trader's own history (`sorted({...df["asset"]...})`), filtered the frame, rendered a filter summary, and on an empty result showed "No trades for {asset}" plus a "Show all assets" button — deliberately not zeros.
- **Screenshots.** `web/app/api/trades/[id]/screenshot/route.ts` is the single relay over FastAPI's three endpoints (presign, finalize, url ingest), owner-scoped and already tested. `web/lib/app/screenshot-upload.ts` exports `ACCEPTED_SCREENSHOT_TYPES`, `screenshotPreflight`, `screenshotUrlPreflight`, `attachScreenshot`, `attachScreenshotUrl`, `abandonScreenshotUpload` and `type UploadPhase`. `web/components/app/new-trade/screenshot-upload.tsx` exports `ScreenshotUpload` and `ScreenshotUploadStatus` and is imported **only** by `new-trade-form.tsx`. Trade detail renders `web/components/app/trade-detail/screenshot-gallery.tsx` (read-only) inside `trade-detail-view.tsx`.
- **Analytics.** `api/routers/analytics.py` refuses unknown query params and builds four lenses; `services/analytics.py:499 build_setups` is where Streamlit's emotion panel belongs (`ui/pages/4_Analytics.py:835-857` renders P&L by `emotions_before`). `services/metrics.py:791 emotion_vs_rr(trades)` returns columns `emotions_before`, `trades`, `avg_rr_realized`, excludes null emotions, and skips NaN R in the mean while still counting the trade. `api/schemas/analytics.py` defines `Breakdown`, `SetupsLens`, `RiskLens`, `TimingLens` (the latter documents why `by_hour` is absent — an owner-approved deliberate removal, unchanged here).

---

## File structure

**Task 1 — Overview asset filter**
- Modify `src/tradelens/services/overview.py` — `build_overview(..., asset: Optional[str] = None)`; period frame filtered, lifetime reads untouched; `filters` block in the payload.
- Modify `src/tradelens/api/schemas/overview.py` — `OverviewFilters` + `filters` field.
- Modify `src/tradelens/api/routers/overview.py` — optional `asset` query param, unknown-param refusal.
- Modify `web/lib/app/overview.ts`, `web/app/app/page.tsx`, create `web/components/app/overview/asset-filter.tsx`.
- Tests: `tests/test_overview_service.py`, `tests/test_api_overview.py`, `web/__tests__/overview-asset-filter.test.tsx`.

**Task 2 — Screenshot upload on an existing trade**
- Create `web/components/app/trade-detail/attach-screenshot.tsx` (client island reusing `ScreenshotUpload` + the relay).
- Modify `web/components/app/trade-detail/screenshot-gallery.tsx` (render the island beneath the gallery) and `trade-detail-view.tsx` if it owns the gallery's props.
- Tests: `web/__tests__/trade-detail-attach-screenshot.test.tsx`.

**Task 3 — Emotion vs RR**
- Modify `src/tradelens/services/analytics.py` — `build_setups` gains `by_emotion_rr`.
- Modify `src/tradelens/api/schemas/analytics.py` — `EmotionRRRow` + `SetupsLens.by_emotion_rr`.
- Modify `web/components/app/analytics/setups-lens.tsx` (or the component that renders the Setups lens) to show the panel.
- Tests: `tests/test_analytics_service.py`, `tests/test_api_analytics.py`, `web/__tests__/analytics-emotion-rr.test.tsx`.

**Task 4 — Ledger, battery, review** — `docs/superpowers/parity/2026-09-14-phase10-parity-ledger.md`, scratchpad harness.

---

## Task 1: Overview asset filter

**Files:**
- Modify: `src/tradelens/services/overview.py:157`, `src/tradelens/api/schemas/overview.py`, `src/tradelens/api/routers/overview.py:71-85`
- Modify: `web/lib/app/overview.ts`, `web/app/app/page.tsx`; Create: `web/components/app/overview/asset-filter.tsx`
- Test: `tests/test_overview_service.py`, `tests/test_api_overview.py`, `web/__tests__/overview-asset-filter.test.tsx`

**Interfaces:**
- Produces: `build_overview(*, user_id: int, start: str, end: str, today: Optional[dt.date] = None, asset: Optional[str] = None) -> dict`; payload gains `"filters": {"asset": Optional[str], "available_assets": List[str]}`. Schema `OverviewFilters(_Strict)` with `asset: Optional[str]` and `available_assets: List[str]`; `OverviewResponse.filters: OverviewFilters`. Route `GET /v1/overview?from=&to=&asset=`; unknown params → 422; an asset with no trades in the period is a valid empty scope (200), never a 404.
- Consumes: `metrics.*` unchanged.

- [ ] **Step 1: Write the failing service tests**

```python
def test_asset_filter_scopes_period_figures_but_not_lifetime(two_users):
    a, _ = two_users
    _trade(a, "2026-09-07", asset="NQ", pnl=100.0, result="Win")
    _trade(a, "2026-09-08", asset="ES", pnl=-50.0, result="Loss")
    everything = build_overview(user_id=a, start="2026-09-01", end="2026-09-30")
    scoped = build_overview(user_id=a, start="2026-09-01", end="2026-09-30", asset="NQ")
    assert everything["kpis"]["trades"]["value"] == 2
    assert scoped["kpis"]["trades"]["value"] == 1
    assert scoped["kpis"]["net_pnl"]["value"] == 100.0
    # Lifetime concepts are not scoped by a view filter.
    assert scoped["activation"] == everything["activation"]


def test_available_assets_come_from_the_owners_own_history(two_users):
    a, b = two_users
    _trade(a, "2026-09-07", asset="NQ")
    _trade(b, "2026-09-07", asset="GC")
    payload = build_overview(user_id=a, start="2026-09-01", end="2026-09-30")
    assert payload["filters"]["available_assets"] == ["NQ"]
    assert payload["filters"]["asset"] is None


def test_an_asset_with_no_trades_in_period_is_an_empty_scope_not_an_empty_account(two_users):
    a, _ = two_users
    _trade(a, "2026-09-07", asset="NQ")
    scoped = build_overview(user_id=a, start="2026-09-01", end="2026-09-30", asset="ES")
    assert scoped["kpis"]["trades"]["value"] == 0
    assert scoped["filters"]["asset"] == "ES"
    assert scoped["activation"]["complete_trades"] >= 1


def test_asset_match_is_exact_not_substring(two_users):
    a, _ = two_users
    _trade(a, "2026-09-07", asset="MNQ")
    scoped = build_overview(user_id=a, start="2026-09-01", end="2026-09-30", asset="NQ")
    assert scoped["kpis"]["trades"]["value"] == 0
```

`_trade(owner, day, **fields)` inserts a `Trade` row with `user_id=owner`, `trade_date=day`, and the given fields, committing through `SessionLocal()` — copy the helper already at the top of `tests/test_overview_service.py`.

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_overview_service.py -k asset -v`
Expected: FAIL — `TypeError: build_overview() got an unexpected keyword argument 'asset'`.

- [ ] **Step 3: Implement the service**

In `build_overview`, after `df = _frame(trades)` and before any metric call:

```python
    # Every asset this owner has traded in the period, for the filter control.
    available_assets = sorted(
        {str(value).strip() for value in df["asset"].dropna() if str(value).strip()}
    )
    if asset is not None:
        # Exact match, never `ilike('%..%')`: MNQ must not fold into an NQ view.
        df = df[df["asset"].astype(str) == asset].reset_index(drop=True)
```

Leave `lifetime_trades` / `lifetime_df` untouched — activation and today/this-week are lifetime concepts (the docstring already says so). Add to the returned payload:

```python
        "filters": {"asset": asset, "available_assets": available_assets},
```

- [ ] **Step 4: Run the service tests**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_overview_service.py -v`
Expected: all pass.

- [ ] **Step 5: Write the failing API tests** (`tests/test_api_overview.py`, using that file's existing signed-request helpers)

```python
def test_overview_asset_filter_is_owner_scoped_and_exact(client, two_users):
    a, b = two_users
    _trade(a, "2026-09-07", asset="NQ", pnl=100.0, result="Win")
    _trade(b, "2026-09-07", asset="NQ", pnl=999.0, result="Win")
    body = _get(client, "/v1/overview?from=2026-09-01&to=2026-09-30&asset=NQ", a).json()
    assert body["kpis"]["trades"]["value"] == 1
    assert body["filters"] == {"asset": "NQ", "available_assets": ["NQ"]}


def test_overview_refuses_an_unknown_query_parameter(client, two_users):
    a, _ = two_users
    assert _get(client, "/v1/overview?from=2026-09-01&to=2026-09-30&setup=FVG", a).status_code == 422


def test_overview_asset_with_no_trades_is_200_with_an_empty_scope(client, two_users):
    a, _ = two_users
    _trade(a, "2026-09-07", asset="NQ")
    response = _get(client, "/v1/overview?from=2026-09-01&to=2026-09-30&asset=ES", a)
    assert response.status_code == 200
    assert response.json()["kpis"]["trades"]["value"] == 0
```

- [ ] **Step 6: Run to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_api_overview.py -k "asset or unknown_query" -v`
Expected: FAIL — the `asset` parameter is ignored and `filters` is absent.

- [ ] **Step 7: Implement schema + route**

`api/schemas/overview.py`:

```python
class OverviewFilters(_Strict):
    """What the view is scoped to, and what it could be scoped to.

    `available_assets` comes from the owner's trades in the period, never a
    static list: a filter that offers instruments the trader never traded
    invites a scope that can only ever be empty.
    """

    asset: Optional[str]
    available_assets: List[str]
```

Add `filters: OverviewFilters` to `OverviewResponse`.

`api/routers/overview.py` — mirror the Analytics rule:

```python
_KNOWN_QUERY_PARAMS = frozenset({"from", "to", "asset"})


def _refuse_unknown_params(request: Request) -> None:
    unknown = sorted(set(request.query_params) - _KNOWN_QUERY_PARAMS)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail="unsupported query parameter(s): {}".format(", ".join(unknown)),
        )


@router.get("/overview")
def get_overview(
    request: Request,
    from_: str = Query(..., alias="from"),
    to: str = Query(...),
    asset: Optional[str] = Query(default=None),
    user_id: int = Depends(current_user),
) -> OverviewResponse:
    _refuse_unknown_params(request)
    start, end = _validated_period(from_, to)
    payload = to_jsonable(
        build_overview(user_id=user_id, start=start, end=end, asset=asset)
    )
    payload["period"] = {"from_": start, "to": end}
    return OverviewResponse.model_validate(payload)
```

(Keep the existing docstring; add `Request` and `Optional` to the imports.)

- [ ] **Step 8: Run the API tests and regenerate the contract**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_api_overview.py -v`, then from the repo root `python scripts/generate_openapi.py` and `npm --prefix web run api:types`.
Expected: tests pass; the regenerated client carries `filters` and the `asset` parameter.

- [ ] **Step 9: Write the failing web test** (`web/__tests__/overview-asset-filter.test.tsx`, mocks as `settings-page-load.test.tsx`)

Tests: (a) with `available_assets: ["ES", "NQ"]` and `asset: null` the control renders every option plus "All assets" and no scope summary; (b) choosing NQ navigates to `/app?asset=NQ` (assert on the mocked router `push`); (c) with `asset: "NQ"` and zero trades the page renders the empty-scope copy "No trades for NQ" and a "Show all assets" control, and **does not** render the KPI strip; (d) the page forwards `asset` to `fetchOverview` only when it is a non-empty string (`?asset=` and `?asset=<script>` are dropped); (e) with `available_assets: []` no filter control renders.

- [ ] **Step 10: Run to verify it fails, then implement the web side**

Run (from `web/`): `npx vitest run __tests__/overview-asset-filter.test.tsx` → FAIL (module missing).
Implement `asset-filter.tsx` (a `<select>` + summary line, 44px targets, `aria-label="Filter by asset"`), thread `asset` through `fetchOverview` in `web/lib/app/overview.ts`, and read `searchParams.asset` in `web/app/app/page.tsx`, passing it on only when `typeof value === "string" && value.trim() !== ""`.

- [ ] **Step 11: Run every gate for this task**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_overview_service.py tests/test_api_overview.py tests/parity -q`; `ruff check src/ scripts/`; `black --check src/ scripts/ tests/`; from `web/`: `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build` with `SITE_ORIGIN=http://localhost:3000 APP_ORIGIN=http://localhost:8501 SUPPORT_EMAIL=support@tradelens.dev`.
Expected: all green; parity snapshots unchanged.

- [ ] **Step 12: Commit**

```bash
git add src/tradelens/services/overview.py src/tradelens/api tests/test_overview_service.py tests/test_api_overview.py web/lib/app/overview.ts web/app/app/page.tsx web/components/app/overview/asset-filter.tsx web/__tests__/overview-asset-filter.test.tsx web/lib/api
git commit -m "feat(overview): scope the period view by asset without touching lifetime figures"
```

---

## Task 2: Screenshot upload on an existing trade

**Files:**
- Create: `web/components/app/trade-detail/attach-screenshot.tsx`
- Modify: `web/components/app/trade-detail/screenshot-gallery.tsx`, `web/components/app/trade-detail/trade-detail-view.tsx`
- Test: `web/__tests__/trade-detail-attach-screenshot.test.tsx`

**Interfaces:**
- Consumes: `attachScreenshot(tradeId: number, file: File, onPhase: (phase: UploadPhase, progress: number) => void)`, `attachScreenshotUrl(tradeId: number, url: string)`, `screenshotPreflight(file: File)`, `screenshotUrlPreflight(raw: string)`, `abandonScreenshotUpload(tradeId: number, key: string)`, `ACCEPTED_SCREENSHOT_TYPES`, `type UploadPhase` from `@/lib/app/screenshot-upload`; `ScreenshotUpload`, `type ScreenshotUploadStatus` from `@/components/app/new-trade/screenshot-upload`. **Read the real signatures before writing** — use them exactly; do not add a parameter.
- Produces: `AttachScreenshot({ tradeId }: { tradeId: number })`, default-exported nothing; used by the gallery.

- [ ] **Step 1: Write the failing test**

Cover: (a) idle renders a file input labelled for attaching a chart to this trade; (b) a valid PNG runs presign → PUT → finalize through the relay and then calls `router.refresh()` so the gallery shows the new image (assert the mocked `refresh` fired, and that `fetch` was called with `/api/trades/7/screenshot`); (c) a rejected preflight (wrong type, oversized) shows the fixed message and **never** calls `fetch`; (d) a relay failure shows a fixed failure sentence, leaves the gallery untouched and does not refresh; (e) a second click while busy sends one request; (f) the component never renders an `<img>` for a file that was not attached.

- [ ] **Step 2: Run to verify it fails**

Run (from `web/`): `npx vitest run __tests__/trade-detail-attach-screenshot.test.tsx`
Expected: FAIL — cannot resolve `@/components/app/trade-detail/attach-screenshot`.

- [ ] **Step 3: Implement the island**

`attach-screenshot.tsx` is `"use client"`, holds `ScreenshotUploadStatus` in state, drives the existing helpers in order (preflight → `attachScreenshot` with a phase callback → `router.refresh()`), guards re-entry with a ref exactly as `new-trade-form.tsx` does, and on failure calls `abandonScreenshotUpload` when a key was already presigned. Copy: idle "Attach a chart screenshot to this trade."; failure "That screenshot was not attached. Try again."

- [ ] **Step 4: Mount it and run the tests**

Render `<AttachScreenshot tradeId={trade.id} />` beneath the gallery in `screenshot-gallery.tsx` (pass `tradeId` down from `trade-detail-view.tsx` if the gallery does not already receive it).
Run: `npx vitest run __tests__/trade-detail-attach-screenshot.test.tsx __tests__/trade-detail-page-auth.test.tsx` → pass.

- [ ] **Step 5: Run every gate for this task**

Run (from `web/`): `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build` with the localhost origins.
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add web/components/app/trade-detail web/__tests__/trade-detail-attach-screenshot.test.tsx
git commit -m "feat(trade-detail): attach a screenshot to an existing trade through the owner-scoped relay"
```

---

## Task 3: Emotion vs RR in the Setups lens

**Files:**
- Modify: `src/tradelens/services/analytics.py:499` (`build_setups`), `src/tradelens/api/schemas/analytics.py`
- Modify: the Setups lens component under `web/components/app/analytics/`
- Test: `tests/test_analytics_service.py`, `tests/test_api_analytics.py`, `web/__tests__/analytics-emotion-rr.test.tsx`

**Interfaces:**
- Consumes: `metrics.emotion_vs_rr(df) -> DataFrame[emotions_before, trades, avg_rr_realized]` (read-only).
- Produces: `EmotionRRRow(_Strict)` with `emotion: str`, `trades: int`, `avg_rr_realized: MetricValue`; `SetupsLens.by_emotion_rr: List[EmotionRRRow]`; `build_setups` returns `"by_emotion_rr": [...]` ordered by `trades` descending then `emotion` ascending.

- [ ] **Step 1: Write the failing service test**

```python
def test_setups_lens_reports_average_r_by_pre_trade_emotion():
    df = pd.DataFrame(
        [
            {"emotions_before": "Calm", "rr_realized": 2.0, "pnl": 100.0, "result": "Win"},
            {"emotions_before": "Calm", "rr_realized": 1.0, "pnl": 50.0, "result": "Win"},
            {"emotions_before": "FOMO", "rr_realized": -1.0, "pnl": -80.0, "result": "Loss"},
            {"emotions_before": None, "rr_realized": 3.0, "pnl": 10.0, "result": "Win"},
        ]
    )
    rows = build_setups(df)["by_emotion_rr"]
    assert [r["emotion"] for r in rows] == ["Calm", "FOMO"]
    assert rows[0]["trades"] == 2 and rows[0]["avg_rr_realized"]["value"] == 1.5
    assert rows[1]["avg_rr_realized"]["value"] == -1.0


def test_emotion_rr_is_empty_when_no_emotion_was_recorded():
    df = pd.DataFrame([{"emotions_before": None, "rr_realized": 1.0, "result": "Win"}])
    assert build_setups(df)["by_emotion_rr"] == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_analytics_service.py -k emotion -v`
Expected: FAIL — `KeyError: 'by_emotion_rr'`.

- [ ] **Step 3: Implement the service**

In `build_setups`, using the module's existing `MetricValue` helper (`finite_or_state` or equivalent — read how `by_setup` builds its values and use the same helper):

```python
    emotion = metrics.emotion_vs_rr(df)
    by_emotion_rr = [
        {
            "emotion": str(row.emotions_before),
            "trades": int(row.trades),
            "avg_rr_realized": _metric(row.avg_rr_realized),
        }
        for row in emotion.sort_values(
            ["trades", "emotions_before"], ascending=[False, True]
        ).itertuples(index=False)
    ]
```

and add `"by_emotion_rr": by_emotion_rr` to the returned dict.

- [ ] **Step 4: Run the service tests, then add the API test**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_analytics_service.py -v` → pass.
Add to `tests/test_api_analytics.py`: the Setups lens carries `by_emotion_rr` for the authenticated owner only, and a second user's emotions never appear. Run it → FAIL until the schema is added, then implement `EmotionRRRow` + `SetupsLens.by_emotion_rr` and rerun.

- [ ] **Step 5: Regenerate the contract**

Run from the repo root: `python scripts/generate_openapi.py` then `npm --prefix web run api:types`.
Expected: `web/lib/api/schema.d.ts` gains `by_emotion_rr`; commit the regenerated files with this task.

- [ ] **Step 6: Write the failing web test and implement the panel**

`web/__tests__/analytics-emotion-rr.test.tsx`: with two rows the Setups lens renders a labelled panel titled "Average R by emotional state going in" listing each emotion with its trade count and average R (one decimal, negative values marked negative); with `by_emotion_rr: []` it renders the existing empty-state copy and no table. Run → FAIL, then render it in the Setups lens component with the breakdown primitive already used there.

- [ ] **Step 7: Run every gate for this task**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_analytics_service.py tests/test_api_analytics.py tests/parity -q`; `ruff check src/ scripts/`; `black --check src/ scripts/ tests/`; from `web/`: `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build`.
Expected: all green; parity snapshots unchanged (they pin metrics, not lens payloads — if one moves, stop and report rather than refreshing it).

- [ ] **Step 8: Commit**

```bash
git add src/tradelens/services/analytics.py src/tradelens/api tests/test_analytics_service.py tests/test_api_analytics.py web/components/app/analytics web/__tests__/analytics-emotion-rr.test.tsx web/lib/api
git commit -m "feat(analytics): average R by pre-trade emotional state in the Setups lens"
```

---

## Task 4: Ledger, mutation battery, review

**Files:**
- Modify: `docs/superpowers/parity/2026-09-14-phase10-parity-ledger.md`
- Harness: scratchpad only

- [ ] **Step 1: Flip the three ledger rows**

Change `Overview | filter panel`, `Journal / Trades | per-trade screenshot upload` and `Analytics | emotion vs RR` from `blocker` to `implemented`, each naming the new location **and** the behavioural test added above. Run `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_parity_ledger.py -v` → 3 passed.

- [ ] **Step 2: Run the mutation battery from a clean HEAD**

Verdict controls first. At minimum these mutants, each expected CAUGHT: asset filter applied to the lifetime frame; asset match via `str.contains` instead of `==`; `available_assets` built from all owners' trades; `filters` omitted from the payload; unknown-param refusal removed; the attach island skipping preflight; the island not calling `router.refresh()` on success; `abandonScreenshotUpload` not called after a failure; `by_emotion_rr` including null-emotion rows; its sort reversed; the emotion panel rendering when the list is empty.
Record NOT-APPLIED / ERROR / NOT-RUN honestly; a survivor is a test gap to close, not a note.

- [ ] **Step 3: Independent review, then stop**

Dispatch a reviewer against the task range in a private `git archive` extraction: financial correctness of the filter (lifetime vs period, exact match, empty scope), owner isolation on all three, relay reuse and no new endpoint for Task 2, and output/emptiness handling for Task 3. **Do not merge.** Report findings, the battery table and every gate with exact counts.

---

## Self-review (2026-09-18)

- **Spec coverage:** §8 Overview "filter panel" → Task 1; Journal/Trades "per-trade screenshot upload" → Task 2; Analytics "emotion vs RR" → Task 3; §11.1 evidence → Task 4. The other §8 items are already `implemented` or carry a recorded owner decision in the ledger.
- **Placeholder scan:** every code step carries real code; the two places where the implementer must read an existing signature first (the screenshot helpers, the analytics `MetricValue` helper) say so explicitly rather than inventing a name.
- **Type consistency:** `asset` / `filters.asset` / `available_assets` match across service, schema, route and web; `by_emotion_rr` and `EmotionRRRow.emotion` match across service, schema and component; `AttachScreenshot({ tradeId })` matches its mount site.
