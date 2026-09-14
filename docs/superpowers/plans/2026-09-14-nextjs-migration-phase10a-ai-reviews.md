# Phase 10A — AI Reviews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate AI Reviews — Patterns, Weekly Recap and Daily Debrief — from the Streamlit Insights page onto the FastAPI + Next.js boundary, so Phase 10 Gate 1 can mark every §8 AI Reviews item `implemented`.

**Architecture:** Group A moves the pieces Streamlit keeps under `ui/` (week/day options, period stats) into services, adds a persisted, owner-scoped daily debrief store, and makes every review source deletable with the trades it quotes. Group B adds `/v1/reviews`: one deterministic read (Patterns + available weeks/days + saved notes) and job-backed generation for the Weekly Recap and Daily Debrief through the existing `ai_jobs` worker, idempotent and rate-limited like trade summaries. Groups C and D add same-origin relays and replace the `/app/reviews` stub with a three-lens page that polls jobs.

**Tech Stack:** FastAPI · Pydantic v2 · SQLAlchemy 2.x · Alembic · `ai_jobs` worker · Next.js 16 App Router · TypeScript · pytest · Vitest

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md` — §8 AI Reviews ("Patterns (candidates, cards, confidence, evidence, sample size, next review action) · Weekly Recap (week selector, generate, retry, validated sections) · Daily Debrief (day selector, five sections) · read-full-note disclosure"); §9.5 (double AI spend → idempotency key per job); §11.1 and §11.5. Parent plan: `docs/superpowers/plans/2026-09-14-nextjs-migration-phase10-streamlit-retirement.md` (decision T1).

## Global Constraints

- Owner identity only from the authenticated session. No request field names an owner, a trade id set, or a review id belonging to anyone else; foreign and missing are identical (404).
- Service-layer isolation via `services/ownership.require_user_id`.
- Next.js is the BFF; relays are same-origin, `no-store`, fail shut on unset `SITE_ORIGIN` before the session lookup, gate on `appLayoutRedirect`, forward fixed error shapes only.
- Strict request schemas (`extra="forbid"`, `strict=True`); strict response models.
- **`prompts/` locked** (`weekly_recap_v1`, `debrief_v1` used unchanged). `services/metrics.py` untouched. Parity snapshots untouched.
- AI copy is reflection only — never signals, predictions or advice. Generated Markdown renders as text (no HTML path).
- Model: `claude-opus-5` via `services/ai_client` only. `DEMO_MODE=true` spends nothing.
- Every paid call is job-backed, idempotent per owner (`ai_jobs` unique key) and counted by `jobs.enqueue_with_limit`; usage logged through `on_usage` the moment the provider answers.
- Python 3.9.6 floor. **No new dependencies.** One Alembic migration (decision R1); head moves from `g3h4i5j6k7l8`.
- The Streamlit Insights page keeps working against the same services until Phase 10 Group X.
- Gates: `pytest tests/ -q` (record exact counts; the three known pre-existing Streamlit boot failures reported separately); `pytest tests/parity -q`; `ruff check src/ scripts/`; `black --check src/ scripts/ tests/`; in `web/`: `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build` (localhost origins); `scripts/generate_openapi.py` + `npm --prefix web run api:types` no diff; one alembic head; upgrade/downgrade drill.
- Mutation discipline: the Phase 9 hardened harness (CAUGHT only when intended tests ran and FAILED; ERROR/NOT-RUN/NOT-APPLIED never caught; verdict controls first; clean HEAD; sha256 restores).

---

## Execution process

| Group | Review depth |
|---|---|
| A — services: moved helpers, debrief store, deletion coverage | **Deep** (migration, deletion, isolation) |
| B — `/v1/reviews` API + worker handlers | **Deepest**: paid-call idempotency, rate limit, isolation, source-gone races |
| C — relays + server bridge | Deep for generate relays; light otherwise |
| D — the Reviews page | Medium; Markdown-as-text and polling deep |
| E — verification, battery, handoff, Codex request | Final boundary |

## Scope

**In:** Patterns lens (deterministic `patterns.generate_insights`, period strip, lead thesis + up to four findings, confidence/sample/limitation, review action); Weekly Recap (week selector over completed weeks with trades, saved recap reuse, explicit generate, regenerate that never loses the existing note, retry, 5 validated sections, stats strip, evidence used); Daily Debrief (day selector, generate, regenerate, retry, 5 validated sections, stats strip, link to the Journal for that day); read-full-note disclosure; Overview "next review action" deep link; deletion coverage.

**Not in:** the retired AI pattern-cards call (`patterns.generate_cards`, not used by Streamlit since Item 10); a review history browser beyond the selectors; streaming; Streamlit removal.

**Carried forward unchanged:** Phase 10 hard pre-release gates; Phase 9 non-blocking hardening items; the three known pre-existing Streamlit boot failures (recorded separately).

---

## What already exists (verified on `origin/main` `6c1f161`)

- `ui/pages/6_Insights.py` — parity reference. Lenses `("Patterns", "Weekly Recap", "Daily Debrief")` with questions "What keeps repeating in the journal?", "How did the completed week go?", "What happened on one trading day?". Header "AI Reviews — Evidence-backed reading of your own journal. Reflection only — never signals or advice." Weekly: gate `activation.TRADES_FOR_REVIEW = 5` complete trades unless a recap is saved; **auto-generates on page view**; regenerate overwrites only on success; `_AI_FAILED = "The review could not be generated. Try again."`. Daily: generated on click, **cached in session only (never persisted)**, logs `log_ai_usage("Daily Debrief", …)`. Patterns: `generate_insights(df, strategy)`, empty state "No repeating patterns yet"; limitation copy under five trades.
- `services/weekly.py` — `week_bounds`, `generate_weekly_review(week_start, user_id, strategy_profile) -> (dict, Usage)` (prompt `weekly_recap_v1`, sections `### What Worked / What Didn't / Observed Patterns / Rule Adherence / Focus for Next Week`), `save_weekly_review(review, user_id, overwrite)`, `get_weekly_review`, `get_weekly_reviews`. No `on_usage`. `WeeklyReview.user_id` nullable (legacy NULL rows never readable by owner-scoped queries); no unique constraint on `(user_id, week_start)`.
- `services/debrief.py` — `generate_debrief(trades, strategy_profile, period_label) -> (dict, Usage)` (prompt `debrief_v1`, sections `### Session Summary / Discipline & Rule Adherence / Emotional Review / Recurring Patterns / Improvement Actions`). No persistence, no `on_usage`.
- `ui/components/review_dates.py` — `review_day_options`, `review_week_options` (pure pandas). `ui/components/review_reader.py` — `period_stats` (metrics-backed five figures). Both under `ui/` (deleted in Phase 10).
- Job pattern: `api/routers/trades.py:292-406` (`enqueue_trade_summary`, `get_trade_summary_job`), `api/jobs.py` (`enqueue_with_limit(user_id, kind, key, payload, *, since, limit)`, `get_owned_job(job_id, user_id)`), `api/worker.py` `HANDLERS`, `services/trade_summary.save_trade_summary_result` (locks source trades `FOR UPDATE`, raises `TradeSummarySourceGone`). Forward-looking lexical guard `trade_summary._reject_forward_looking`.
- `services/data_deletion.py` — `_delete_trade_summary_state` removes `trade_summary` jobs and results on delete-all and sample deletion; weekly reviews are **not** removed (Phase 9 N6). `account._OWNED_BY_USER` includes `WeeklyReview`, `AIJob`.
- Web: `/app/reviews` stub; `lib/app/navigation.ts:34` links it; `components/app/overview/next-review-action.tsx:62` links it; `components/app/trades/summary-panel.tsx` is the polling + Markdown-as-text reference; `lib/app/trade-summary-relay.ts` the relay authorisation reference.
- Cost feature names: `cost._WEEKLY_REVIEW = "Weekly Review"`; Streamlit logs `"Daily Debrief"`.

## Decisions — approved by the owner (2026-09-14)

R1–R9 are **approved**. The clarifications below are **binding and override any task detail that
conflicts with them**; each task's implementer must read this section first.

- **C1 (R1) Provenance.** Stored daily debriefs stay owner-scoped and carry clear provenance:
  `day` (period), `input_fingerprint` (the job's effective-input fingerprint, C2), `job_id` of the job
  that produced it, `created_at` and `updated_at`. Weekly recaps saved by the job path record the same
  provenance: add nullable `input_fingerprint`, `job_id`, `updated_at` columns to `weekly_reviews` in the
  same Phase 10A migration (nullable so legacy and Streamlit rows stay valid).
- **C2 (R3) Effective-input fingerprint.** A new `services/review_inputs.py` owns
  `review_input_fingerprint(kind, owner, period, model_payload) -> str`: sha256 over canonical JSON of
  `kind`, `owner`, `period`, **the exact user-message payload supplied to the model** (the same object
  the service serialises — trade fields, stats, pattern candidates, truncated notes), the Strategy
  Profile block, **the prompt version** (prompt file name plus sha256 of its text as loaded by
  `ai_client.load_prompt`), and `trade_analysis.ai_input_version(owner)` (model id, effort, demo mode,
  corrections). Any change to any effective input — including an edited prompt file — yields a new key
  and a new job. The services expose the payload builders (`weekly.build_weekly_model_input(owner,
  monday)`, `debrief.build_daily_model_input(owner, day)`) so the router, worker and fingerprint use one
  source.
- **C3 Worker verification.** The job payload stores the period, source trade ids and the captured
  fingerprint — never trade text. The worker **recomputes the fingerprint from current data before any
  provider call**; a mismatch fails the job with the fixed message "This review is out of date. Generate
  it again." and spends nothing. **Before persistence**, inside the transaction that locks the source
  trades `FOR UPDATE`, it recomputes the fingerprint again and refuses to save on mismatch or on any
  missing source (fail closed; nothing written).
- **C4 (R7)** The forward-looking guard is **defense-in-depth, not a semantic guarantee**, and is recorded
  as such in code docstrings and the handoff.
- **C5 (R8) No resurrection.** Deleting source trades (delete-all, sample deletion, account deletion)
  removes review rows and review jobs, and the C3 locked pre-save check guarantees an already-running
  worker cannot write a weekly recap or daily debrief afterward. Tests pin both orders: save-wins-then-
  delete removes it; delete-wins-then-save writes nothing.
- **C6 (R6) Owner timezone, including DST.** Every day/week boundary (options, "not in the future",
  the period a job covers) is computed from `app_settings.today_for_owner` in the owner's zone. Tests
  include instants either side of a DST transition for `America/New_York` and `Europe/London`.

The original decision text follows, unchanged, for reference.


**R1 — Daily debriefs are persisted, owner-scoped (recommended).** A job-backed result must live somewhere the poll can read and a reload can reuse; session-only caching does not exist on the web. New table `daily_debriefs` (`id`, `user_id` NOT NULL FK `ondelete=CASCADE`, `day` ISO date, `input_key` sha256, `content_md`, `stats_json`, `reviewed_trades`, `created_at`), unique `(user_id, day)`; a regenerate replaces the row only on success. One Alembic migration with `downgrade()`. *Alternative:* store debrief prose only in a generic job-result table (still a migration, and a second result shape). Affects A2, B3.

**R2 — No auto-generation on view (recommended).** Streamlit spends an Opus call when the Weekly lens opens. The web shows a saved recap if one exists and otherwise an explicit "Generate weekly recap" button; opening, prefetching or refreshing the page never enqueues a paid job. Affects B2, D2.

**R3 — Generation is job-backed through `ai_jobs` (recommended).** Kinds `weekly_recap` and `daily_debrief`. Idempotency key = kind + sha256 of the canonical input: owner, period, the ordered snapshot of the period's trades (ids and the fields each prompt reads), and `trade_analysis.strategy_input_fingerprint(owner)`. Same input → same job (a double click never bills twice); changed trades or profile → a new job. Affects B2, B3.

**R4 — Rolling limits per owner (recommended):** `weekly_recap` 10 per 24h, `daily_debrief` 20 per 24h, via `enqueue_with_limit`; a 429 carries a fixed trader-readable sentence and saved notes stay readable. Affects B2, B3, D.

**R5 — Weekly gate stays server-side (recommended).** Generate is refused (409 `not_enough_trades`) when the owner has fewer than `activation.TRADES_FOR_REVIEW` complete trades in total and no recap is saved for that week — Streamlit's rule. A zero-trade week is refused (409 `empty_period`) without a job. Daily: a day with no trades is 409 `empty_period`. Affects B2, B3.

**R6 — Completed periods follow the owner's timezone (recommended).** Week options are Mondays of weeks with at least one trade whose Sunday is before `app_settings.today_for_owner(owner)`, plus the current week; day options are trade days on or before that date. Parity with Streamlit, which offered every week/day with trades; the web adds no future periods. Affects A1, B1.

**R7 — The forward-looking lexical guard applies to both notes, as defense-in-depth (recommended).** Reuse `trade_summary._reject_forward_looking` logic (moved to a shared `services/reflection_guard.py`) after section validation. "Focus for Next Week" and "Improvement Actions" are process reflection and pass the guard unless they name a trade direction or a price level. A rejection fails the job with the fixed message; it is recorded as a lexical check, not a semantic guarantee. Affects A1, B2, B3.

**R8 — Delete all trades and sample deletion also remove derived reviews (recommended, S7 rationale).** Weekly recaps and daily debriefs quote trades and notes, and their queued job payloads carry trade snapshots. `_delete_trade_summary_state` is generalised to delete `ai_jobs` of kinds `trade_summary`, `weekly_recap`, `daily_debrief`, and rows of `trade_summary_results`, `weekly_reviews`, `daily_debriefs` for the owner. Save paths lock their source trades `FOR UPDATE` and fail closed if any is gone (the Phase 9 Codex fix pattern), so a running worker cannot resurrect a note after deletion. `daily_debriefs` joins `account._OWNED_BY_USER` and the reference sweep. *Alternative:* keep reviews after delete-all (contradicts the Danger Zone copy "every trade you have logged … and the AI trade summaries made from them"). Affects A3, B2, B3, and the Settings copy.

**R9 — Patterns stay deterministic (recommended).** `patterns.generate_insights` only; no AI call; always available, including with AI unavailable. §8's "cards" are the deterministic insight findings. Affects B1, D1.

---

## File structure

**Python**
- Create `src/tradelens/services/review_periods.py` — `review_day_options`, `review_week_options`, `period_stats`, `completed_week_options(owner)`, `completed_day_options(owner)` (moved from `ui/components`, re-exported there so Streamlit keeps working).
- Create `src/tradelens/services/reflection_guard.py` — `reject_forward_looking(markdown, error_cls)`; `trade_summary` imports it (behaviour byte-identical).
- Create `src/tradelens/services/daily_debriefs.py` — `save_daily_debrief`, `get_daily_debrief`, `DebriefSourceGone`.
- Modify `src/tradelens/services/weekly.py` — `on_usage` hook; `save_weekly_review_locked(...)` with source lock; guard.
- Modify `src/tradelens/services/debrief.py` — `on_usage` hook; guard.
- Modify `src/tradelens/db/models.py` — `DailyDebrief`.
- Create `alembic/versions/h4i5j6k7l8m9_add_daily_debriefs.py`.
- Modify `src/tradelens/services/data_deletion.py`, `src/tradelens/services/account.py`.
- Modify `src/tradelens/ui/components/review_dates.py`, `review_reader.py` — re-export from services.
- Create `src/tradelens/api/schemas/reviews.py`, `src/tradelens/api/routers/reviews.py`; modify `src/tradelens/api/app.py`, `src/tradelens/api/worker.py`.
- Tests: `tests/test_review_periods.py`, `tests/test_reflection_guard.py`, `tests/test_daily_debriefs.py`, `tests/test_review_deletion.py`, `tests/test_api_reviews.py`, `tests/test_review_worker.py`; update `tests/test_account_deletion_references.py`.

> Revision note: the Phase 10 plan reserved `h4i5j6k7l8m9` for its flip migration. Phase 10A lands first and takes `h4i5j6k7l8m9`; when Phase 10 Group F starts, renumber its migrations to follow the actual head (`i5j6…`, `j6k7…`, `k7l8…`) and update that plan in the same commit.

**Web**
- Create `web/lib/app/reviews.ts` (server bridge + types), `web/lib/app/reviews-relay.ts` (authorise + failure mapping).
- Create routes `web/app/api/reviews/weekly/route.ts` (POST generate), `web/app/api/reviews/daily/route.ts` (POST generate), `web/app/api/reviews/jobs/[jobId]/route.ts` (GET poll).
- Replace `web/app/app/reviews/page.tsx`; create `web/app/app/reviews/loading.tsx`, `error.tsx`.
- Create `web/components/app/reviews/lens-tabs.tsx`, `patterns-lens.tsx`, `weekly-lens.tsx`, `daily-lens.tsx`, `review-note.tsx` (Markdown-as-text sections + read-full-note disclosure), `period-strip.tsx`, `use-review-job.ts` (enqueue + poll hook).
- Modify `web/components/app/overview/next-review-action.tsx` — deep link `?lens=weekly`.
- Tests: `web/__tests__/reviews-relay.test.ts`, `reviews-page.test.tsx`, `reviews-weekly-lens.test.tsx`, `reviews-daily-lens.test.tsx`, `reviews-note.test.tsx`, `reviews-job-hook.test.tsx`.

---

## Group A — services

### Task A1: Review periods and the shared reflection guard move into services

**Files:**
- Create: `src/tradelens/services/review_periods.py`, `src/tradelens/services/reflection_guard.py`
- Modify: `src/tradelens/ui/components/review_dates.py`, `src/tradelens/ui/components/review_reader.py` (re-export), `src/tradelens/services/trade_summary.py` (import the guard)
- Test: `tests/test_review_periods.py`, `tests/test_reflection_guard.py`

**Interfaces:**
- Produces: `review_periods.review_day_options(frame) -> tuple[date, ...]`; `review_week_options(frame) -> tuple[date, ...]`; `period_stats(frame) -> dict` (keys `trades, win_rate, total_pnl, profit_factor, total_edge_leak`); `completed_day_options(owner: int, *, today: date) -> tuple[date, ...]`; `completed_week_options(owner: int, *, today: date) -> tuple[date, ...]`; `reflection_guard.reject_forward_looking(markdown: str, error_cls: type) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_review_periods.py`:

```python
import datetime as dt

import pandas as pd

from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import review_periods
from src.tradelens.ui.components import review_dates, review_reader


def _trade(owner, day):
    db = SessionLocal()
    try:
        db.add(Trade(user_id=owner, asset="NQ", direction="Long", result="Win",
                     trade_date=day, pnl=10.0))
        db.commit()
    finally:
        db.close()


def test_streamlit_keeps_the_same_functions():
    assert review_dates.review_day_options is review_periods.review_day_options
    assert review_dates.review_week_options is review_periods.review_week_options
    assert review_reader.period_stats is review_periods.period_stats


def test_week_options_are_mondays_newest_first():
    frame = pd.DataFrame({"trade_date": ["2026-09-02", "2026-09-10", "bad", None]})
    assert review_periods.review_week_options(frame) == (
        dt.date(2026, 9, 7), dt.date(2026, 8, 31))


def test_owner_options_are_owner_scoped_and_never_future(two_users):
    a, b = two_users
    _trade(a, "2026-09-08")
    _trade(a, "2026-09-20")  # after "today"
    _trade(b, "2026-09-01")
    today = dt.date(2026, 9, 14)
    assert review_periods.completed_day_options(a, today=today) == (dt.date(2026, 9, 8),)
    assert review_periods.completed_week_options(a, today=today) == (dt.date(2026, 9, 7),)


def test_period_stats_of_nothing_is_zeroed():
    assert review_periods.period_stats(pd.DataFrame())["trades"] == 0
```

`tests/test_reflection_guard.py`:

```python
import pytest

from src.tradelens.services import reflection_guard, trade_summary


class Boom(Exception):
    pass


@pytest.mark.parametrize("text", [
    "### Focus for Next Week\nKeep logging HTF bias before every entry.",
    "Long entries were late last week.",
    "Next time I will size smaller after a loss.",
])
def test_process_reflection_passes(text):
    reflection_guard.reject_forward_looking(text, Boom)


@pytest.mark.parametrize("text", [
    "Next week, short the open.",
    "You should buy above 20150.",
    "Consider longs tomorrow.",
])
def test_trade_guidance_is_rejected_with_the_callers_error(text):
    with pytest.raises(Boom):
        reflection_guard.reject_forward_looking(text, Boom)


def test_trade_summary_still_raises_its_own_error():
    with pytest.raises(trade_summary.TradeSummaryError):
        trade_summary._reject_forward_looking("You should buy above 20150.")
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_review_periods.py tests/test_reflection_guard.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.tradelens.services.review_periods'`.

- [ ] **Step 3: Implement**

`src/tradelens/services/review_periods.py` — move `review_day_options` and `review_week_options` verbatim from `ui/components/review_dates.py` and `period_stats` verbatim from `ui/components/review_reader.py:65-105`, then add:

```python
def _owner_trade_frame(owner: int) -> pd.DataFrame:
    from src.tradelens.services.trade_service import get_trades

    trades = get_trades(user_id=require_user_id(owner))
    return pd.DataFrame({"trade_date": [t.trade_date for t in trades]})


def completed_day_options(owner: int, *, today: dt.date) -> tuple:
    """Trade days on or before the owner's today, newest first (decision R6)."""
    return tuple(d for d in review_day_options(_owner_trade_frame(owner)) if d <= today)


def completed_week_options(owner: int, *, today: dt.date) -> tuple:
    """Mondays of weeks with a trade on or before the owner's today, newest first."""
    days = completed_day_options(owner, today=today)
    return tuple(sorted({d - dt.timedelta(days=d.weekday()) for d in days}, reverse=True))
```

(imports: `datetime as dt`, `pandas as pd`, `require_user_id`). In `ui/components/review_dates.py` delete the two bodies and add `from src.tradelens.services.review_periods import review_day_options, review_week_options  # noqa: F401`; keep `demo_rows_for_day`. In `review_reader.py` replace `period_stats` with `from src.tradelens.services.review_periods import period_stats  # noqa: F401`.

`src/tradelens/services/reflection_guard.py` — move `_DIRECTION`, `_NOT_A_POSITION`, `_RECOMMENDS`, `_FUTURE`, `_LEVEL`, `_REFLECTIVE`, `_ADVICE_PATTERNS`, `_PRICE_PATTERNS` verbatim from `trade_summary.py:133-174`, and:

```python
def reject_forward_looking(markdown: str, error_cls: type) -> None:
    """Lexical defense-in-depth: refuse text that reads as a trade idea.

    Not a semantic guarantee. Past-tense and process reflection pass.
    """
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", markdown.lower()):
        if any(p.search(sentence) for p in _ADVICE_PATTERNS):
            raise error_cls("The AI review contained forward-looking trade guidance.")
        if re.search(_REFLECTIVE, sentence):
            continue
        if any(p.search(sentence) for p in _PRICE_PATTERNS):
            raise error_cls("The AI review contained forward-looking trade guidance.")
```

In `trade_summary.py` delete the moved constants and make `_reject_forward_looking` call `reject_forward_looking(markdown, TradeSummaryError)` — but keep its existing message: pass a small subclass-free wrapper:

```python
def _reject_forward_looking(markdown: str) -> None:
    try:
        reject_forward_looking(markdown, TradeSummaryError)
    except TradeSummaryError:
        raise TradeSummaryError("The AI summary contained forward-looking trade guidance.")
```

- [ ] **Step 4: Run**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_review_periods.py tests/test_reflection_guard.py tests/test_trade_summary.py tests/test_insights_page.py tests/test_review_reader.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradelens/services/review_periods.py src/tradelens/services/reflection_guard.py src/tradelens/services/trade_summary.py src/tradelens/ui/components/review_dates.py src/tradelens/ui/components/review_reader.py tests/test_review_periods.py tests/test_reflection_guard.py
git commit -m "refactor(reviews): review periods and the reflection guard move into services"
```

---

### Task A2: Persisted daily debriefs and source-locked saves (R1, R8)

**Files:**
- Modify: `src/tradelens/db/models.py` (add `DailyDebrief` after `WeeklyReview`)
- Create: `alembic/versions/h4i5j6k7l8m9_add_daily_debriefs.py`, `src/tradelens/services/daily_debriefs.py`
- Modify: `src/tradelens/services/weekly.py` (add `save_weekly_review_from_sources`), `src/tradelens/services/account.py` (`_OWNED_BY_USER` += `DailyDebrief`)
- Test: `tests/test_daily_debriefs.py`; modify `tests/test_account_deletion_references.py` (`OWNER_TABLES` += `"daily_debriefs"`)

**Interfaces:**
- Produces: `DailyDebrief` model; `ReviewSourceGone(RuntimeError)` in `daily_debriefs`; `save_daily_debrief(*, user_id, day: str, input_key: str, result: dict, source_trade_ids: list[int]) -> int`; `get_daily_debrief(*, user_id, day: str) -> Optional[dict]` (`day, content_md, stats, reviewed_trades, created_at`); `get_daily_debrief_by_id(result_id, user_id) -> Optional[dict]`; `weekly.save_weekly_review_from_sources(*, user_id, review: dict, source_trade_ids: list[int]) -> int` (returns row id; overwrites the week's row only inside the locked transaction; raises `daily_debriefs.ReviewSourceGone`).

- [ ] **Step 1: Write the failing tests** (`tests/test_daily_debriefs.py`)

```python
import pytest

from src.tradelens.db.models import DailyDebrief, Trade, WeeklyReview
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import daily_debriefs, weekly

RESULT = {"content_md": "### Session Summary\nok", "stats": {"trades": 1}, "reviewed_trades": 1}


def _trade(owner, day="2026-09-08"):
    db = SessionLocal()
    try:
        row = Trade(user_id=owner, asset="NQ", direction="Long", result="Win", trade_date=day)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _delete_trade(trade_id):
    db = SessionLocal()
    try:
        db.query(Trade).filter(Trade.id == trade_id).delete()
        db.commit()
    finally:
        db.close()


def test_save_and_read_are_owner_scoped(two_users):
    a, b = two_users
    t = _trade(a)
    rid = daily_debriefs.save_daily_debrief(user_id=a, day="2026-09-08", input_key="k",
                                            result=RESULT, source_trade_ids=[t])
    assert daily_debriefs.get_daily_debrief(user_id=a, day="2026-09-08")["content_md"].startswith("###")
    assert daily_debriefs.get_daily_debrief(user_id=b, day="2026-09-08") is None
    assert daily_debriefs.get_daily_debrief_by_id(rid, b) is None


def test_regenerate_replaces_the_day(two_users):
    a, _ = two_users
    t = _trade(a)
    daily_debriefs.save_daily_debrief(user_id=a, day="2026-09-08", input_key="k1",
                                      result=RESULT, source_trade_ids=[t])
    daily_debriefs.save_daily_debrief(user_id=a, day="2026-09-08", input_key="k2",
                                      result={**RESULT, "content_md": "### Session Summary\nnew"},
                                      source_trade_ids=[t])
    db = SessionLocal()
    try:
        assert db.query(DailyDebrief).filter(DailyDebrief.user_id == a).count() == 1
    finally:
        db.close()
    assert "new" in daily_debriefs.get_daily_debrief(user_id=a, day="2026-09-08")["content_md"]


def test_a_deleted_source_trade_fails_closed(two_users):
    a, _ = two_users
    t = _trade(a)
    _delete_trade(t)
    with pytest.raises(daily_debriefs.ReviewSourceGone):
        daily_debriefs.save_daily_debrief(user_id=a, day="2026-09-08", input_key="k",
                                          result=RESULT, source_trade_ids=[t])
    assert daily_debriefs.get_daily_debrief(user_id=a, day="2026-09-08") is None


def test_another_owners_trade_is_not_a_source(two_users):
    a, b = two_users
    theirs = _trade(b)
    with pytest.raises(daily_debriefs.ReviewSourceGone):
        daily_debriefs.save_daily_debrief(user_id=a, day="2026-09-08", input_key="k",
                                          result=RESULT, source_trade_ids=[theirs])


def test_weekly_save_from_sources_locks_and_overwrites(two_users):
    a, _ = two_users
    t = _trade(a)
    review = {"week_start": "2026-09-07", "content_md": "### What Worked\nx",
              "thinking_summary": None, "stats": {"trades": 1}, "cost_usd": 0.0}
    first = weekly.save_weekly_review_from_sources(user_id=a, review=review, source_trade_ids=[t])
    second = weekly.save_weekly_review_from_sources(
        user_id=a, review={**review, "content_md": "### What Worked\ny"}, source_trade_ids=[t])
    assert first == second
    assert weekly.get_weekly_review("2026-09-07", a)["content_md"].endswith("y")
    _delete_trade(t)
    with pytest.raises(daily_debriefs.ReviewSourceGone):
        weekly.save_weekly_review_from_sources(user_id=a, review=review, source_trade_ids=[t])
```

Add `"daily_debriefs"` to `OWNER_TABLES` in `tests/test_account_deletion_references.py`.

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_daily_debriefs.py tests/test_account_deletion_references.py -v`
Expected: FAIL — `ImportError: cannot import name 'DailyDebrief'`.

- [ ] **Step 3: Implement**

`models.py`:

```python
class DailyDebrief(Base):
    """One owner's saved debrief for one trading day (Phase 10A, decision R1).

    Replaced only by a successful regeneration. Saved only while every source
    trade still exists, locked in the same transaction (decision R8).
    """

    __tablename__ = "daily_debriefs"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_daily_debriefs_user_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day: Mapped[str] = mapped_column(String(10), nullable=False)
    input_key: Mapped[str] = mapped_column(String(64), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    stats_json: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Migration `h4i5j6k7l8m9_add_daily_debriefs.py` (`down_revision = "g3h4i5j6k7l8"`): `op.create_table("daily_debriefs", …same columns…, sa.UniqueConstraint("user_id", "day", name="uq_daily_debriefs_user_day"))`, `op.create_index("ix_daily_debriefs_user_id", "daily_debriefs", ["user_id"])`; `downgrade()` drops the index then the table.

`services/daily_debriefs.py`:

```python
"""Saved daily debriefs — owner-scoped, replaced only on success, source-locked."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional

from src.tradelens.db.models import DailyDebrief, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ownership import require_user_id


class ReviewSourceGone(RuntimeError):
    """A source trade was deleted before the review could be saved."""


def lock_sources(db, owner: int, source_trade_ids: List[int]) -> None:
    ids = {int(i) for i in source_trade_ids}
    if not ids:
        raise ReviewSourceGone("review source is gone")
    present = {
        tid for (tid,) in db.query(Trade.id)
        .filter(Trade.user_id == owner, Trade.id.in_(sorted(ids)))
        .with_for_update().all()
    }
    if present != ids:
        raise ReviewSourceGone("review source is gone")


def _to_dict(row: DailyDebrief) -> dict:
    return {
        "id": row.id,
        "day": row.day,
        "content_md": row.content_md,
        "stats": json.loads(row.stats_json or "{}"),
        "reviewed_trades": row.reviewed_trades,
        "created_at": row.created_at,
    }


def save_daily_debrief(*, user_id: int, day: str, input_key: str, result: dict,
                       source_trade_ids: List[int]) -> int:
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        lock_sources(db, owner, source_trade_ids)
        row = db.query(DailyDebrief).filter(
            DailyDebrief.user_id == owner, DailyDebrief.day == day).with_for_update().first()
        if row is None:
            row = DailyDebrief(user_id=owner, day=day)
            db.add(row)
        row.input_key = input_key
        row.content_md = str(result["content_md"])
        row.stats_json = json.dumps(result.get("stats") or {}, allow_nan=False, default=str)
        row.reviewed_trades = int(result["reviewed_trades"])
        row.created_at = datetime.now(timezone.utc)
        db.commit()
        return int(row.id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_daily_debrief(*, user_id: int, day: str) -> Optional[dict]:
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = db.query(DailyDebrief).filter(
            DailyDebrief.user_id == owner, DailyDebrief.day == day).first()
        return _to_dict(row) if row else None
    finally:
        db.close()


def get_daily_debrief_by_id(result_id: int, user_id: int) -> Optional[dict]:
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = db.query(DailyDebrief).filter(
            DailyDebrief.id == result_id, DailyDebrief.user_id == owner).first()
        return _to_dict(row) if row else None
    finally:
        db.close()
```

`weekly.py` — add (imports `from src.tradelens.services.daily_debriefs import lock_sources`, placed inside the function to avoid an import cycle):

```python
def save_weekly_review_from_sources(*, user_id: int, review: dict,
                                    source_trade_ids: list) -> int:
    """Job-path save: overwrite this week's recap only while every source trade exists."""
    from src.tradelens.services.daily_debriefs import lock_sources

    owner = require_user_id(user_id)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    db = SessionLocal()
    try:
        lock_sources(db, owner, source_trade_ids)
        row = (db.query(WeeklyReview)
               .filter(WeeklyReview.week_start == review["week_start"], WeeklyReview.user_id == owner)
               .order_by(WeeklyReview.id).with_for_update().first())
        if row is None:
            row = WeeklyReview(week_start=review["week_start"], created_at=now, user_id=owner)
            db.add(row)
        row.content_md = review.get("content_md")
        row.thinking_summary = review.get("thinking_summary")
        row.stats_json = json.dumps(review.get("stats") or {}, default=str)
        row.cost_usd = review.get("cost_usd")
        db.commit()
        return int(row.id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

`account.py`: import `DailyDebrief`; add it to `_OWNED_BY_USER` after `WeeklyReview`.

- [ ] **Step 4: Run**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_daily_debriefs.py tests/test_account_deletion_references.py tests/test_account_deletion.py tests/test_weekly.py tests/test_weekly_review.py -q`; then the migration drill: `DATABASE_URL=sqlite:///./data/p10a-drill.db alembic upgrade head`, `… alembic downgrade -1`, `… alembic upgrade head`; `alembic heads` shows only `h4i5j6k7l8m9`. Delete `data/p10a-drill.db`.
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradelens/db/models.py alembic/versions/h4i5j6k7l8m9_add_daily_debriefs.py src/tradelens/services/daily_debriefs.py src/tradelens/services/weekly.py src/tradelens/services/account.py tests/test_daily_debriefs.py tests/test_account_deletion_references.py
git commit -m "feat(reviews): persisted daily debriefs; source-locked review saves"
```

---

### Task A3: Deleting trades removes the reviews and review jobs made from them (R8)

**Files:**
- Modify: `src/tradelens/services/data_deletion.py:226-233` (`_delete_trade_summary_state` → `_delete_derived_review_state`) and its two callers
- Test: `tests/test_review_deletion.py`

**Interfaces:**
- Consumes: `DailyDebrief`, `WeeklyReview`, `AIJob`, `TradeSummaryResult`.
- Produces: `DERIVED_JOB_KINDS = ("trade_summary", "weekly_recap", "daily_debrief")` in `data_deletion`.

- [ ] **Step 1: Write the failing tests**

```python
import datetime as dt

from src.tradelens.api.storage import ObjectCleanup
from src.tradelens.db.models import AIJob, DailyDebrief, Trade, WeeklyReview
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import data_deletion


def _seed(owner):
    now = dt.datetime.now(dt.timezone.utc)
    db = SessionLocal()
    try:
        db.add(Trade(user_id=owner, asset="NQ", direction="Long", result="Win", trade_date="2026-09-08"))
        db.add(WeeklyReview(user_id=owner, week_start="2026-09-07", content_md="x"))
        db.add(DailyDebrief(user_id=owner, day="2026-09-08", input_key="k", content_md="x",
                            stats_json="{}", reviewed_trades=1, created_at=now))
        for kind in ("weekly_recap", "daily_debrief", "trade_summary", "trade_analysis"):
            db.add(AIJob(user_id=owner, kind=kind, idempotency_key=kind, payload="{}", created_at=now))
        db.commit()
    finally:
        db.close()


def _counts(owner):
    db = SessionLocal()
    try:
        return (
            db.query(WeeklyReview).filter(WeeklyReview.user_id == owner).count(),
            db.query(DailyDebrief).filter(DailyDebrief.user_id == owner).count(),
            sorted(k for (k,) in db.query(AIJob.kind).filter(AIJob.user_id == owner)),
        )
    finally:
        db.close()


def test_delete_all_trades_removes_reviews_and_review_jobs_for_that_owner_only(two_users, monkeypatch):
    a, b = two_users
    _seed(a)
    _seed(b)
    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects",
                        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=[]))
    assert data_deletion.delete_all_trades_and_objects(a).blocked is False
    assert _counts(a) == (0, 0, ["trade_analysis"])
    assert _counts(b) == (1, 1, ["daily_debrief", "trade_analysis", "trade_summary", "weekly_recap"])


def test_a_blocked_deletion_keeps_every_review(two_users, monkeypatch):
    a, _ = two_users
    _seed(a)
    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects",
                        lambda u, t: ObjectCleanup(deleted=[], failed=["k"], skipped=[]))
    assert data_deletion.delete_all_trades_and_objects(a).blocked is True
    assert _counts(a)[:2] == (1, 1)
```

(`trade_analysis` jobs are per-trade job rows outside R8's scope and are removed with their trades by existing logic, or kept, exactly as before — the test pins that R8 did not change them.)

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_review_deletion.py -v`
Expected: FAIL — reviews remain after deletion.

- [ ] **Step 3: Implement**

```python
DERIVED_JOB_KINDS = ("trade_summary", "weekly_recap", "daily_debrief")


def _delete_derived_review_state(db, owner: int) -> None:
    """Remove generated prose, and queued snapshots, derived from the owner's trades.

    Decision S7 (summaries) extended by Phase 10A R8: weekly recaps and daily
    debriefs quote trades and notes, and their job payloads carry snapshots.
    """
    db.query(AIJob).filter(AIJob.user_id == owner, AIJob.kind.in_(DERIVED_JOB_KINDS)).delete(
        synchronize_session=False)
    for model in (TradeSummaryResult, WeeklyReview, DailyDebrief):
        db.query(model).filter(model.user_id == owner).delete(synchronize_session=False)
```

Replace both calls of `_delete_trade_summary_state(db, owner)` with `_delete_derived_review_state(db, owner)`; delete the old function; import `WeeklyReview`, `DailyDebrief`. Update the Danger Zone copy in `web/components/app/settings/danger-zone.tsx` from "and the AI trade summaries made from them" to "and the AI summaries, weekly recaps and daily debriefs made from them", and its test expectation if one pins it.

- [ ] **Step 4: Run**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_review_deletion.py tests/test_data_deletion.py tests/test_api_settings.py -q`; from `web/`: `npx vitest run __tests__/settings-danger-zone.test.tsx`.
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradelens/services/data_deletion.py tests/test_review_deletion.py web/components/app/settings/danger-zone.tsx web/__tests__/settings-danger-zone.test.tsx
git commit -m "fix(reviews): deleting trades removes the reviews and review jobs made from them"
```

---

## Group B — `/v1/reviews` API and worker handlers

### Task B1: `GET /v1/reviews` — Patterns and the period selectors (R6, R9)

**Files:**
- Create: `src/tradelens/api/schemas/reviews.py`, `src/tradelens/api/routers/reviews.py`
- Modify: `src/tradelens/api/app.py` (`app.include_router(reviews.router)`)
- Test: `tests/test_api_reviews.py`

**Interfaces:**
- Consumes: `review_periods.*`, `patterns.generate_insights`, `strategy.get_active_strategy`, `app_settings.today_for_owner`, `weekly.get_weekly_review`, `daily_debriefs.get_daily_debrief`, `activation.is_complete_trade`, `activation.TRADES_FOR_REVIEW`.
- Produces (response `ReviewsResponse`): `patterns: PatternsLens{trades:int, stats:PeriodStats, insights: list[PatternInsight{title, body, confidence: Literal["low","medium","high"], type: str, min_trades:int}], strategy_included: bool}`; `weeks: list[str]` (ISO Mondays, newest first); `days: list[str]`; `complete_trades: int`; `trades_for_review: int`; `ai_available: bool`; `weekly: Optional[SavedNote]` for query `week`; `daily: Optional[SavedNote]` for query `day`. `SavedNote{period:str, content_md:str, stats:PeriodStats, reviewed_trades:int, created_at:str}`. `PeriodStats{trades:int, win_rate:float, total_pnl:float, profit_factor: Optional[float], total_edge_leak: float}`. Query: `week` and `day` optional ISO dates; unknown params 422 (analytics pattern).

- [ ] **Step 1: Write the failing tests** (copy `SECRET`, the `client` fixture, `_session_handle_for` and the signed request helpers from `tests/test_api_settings.py`; name them `_get(client, path, user_id)` and `_post(client, path, body, user_id)` here — then:)

```python
def _trade(owner, day, **extra):
    from src.tradelens.db.models import Trade
    db = SessionLocal()
    try:
        row = Trade(user_id=owner, asset="NQ", direction="Long", result="Win",
                    trade_date=day, pnl=50.0, setup_type="FVG", followed_rules=1, **extra)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def test_reviews_read_is_owner_scoped(client, two_users):
    a, b = two_users
    _trade(a, "2026-09-08")
    _trade(b, "2026-08-03")
    body = _get(client, "/v1/reviews", b).json()
    assert body["days"] == ["2026-08-03"]
    assert body["weeks"] == ["2026-08-03"]
    assert body["patterns"]["trades"] == 1


def test_patterns_are_deterministic_and_need_no_ai(client, two_users, monkeypatch):
    a, _ = two_users
    monkeypatch.setattr("src.tradelens.services.ai_client.chat",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no AI")))
    for i in range(4):
        _trade(a, "2026-09-0%d" % (i + 1), killzone="London Open")
    response = _get(client, "/v1/reviews", a)
    assert response.status_code == 200
    assert isinstance(response.json()["patterns"]["insights"], list)


def test_saved_notes_are_returned_only_for_the_owner(client, two_users):
    from src.tradelens.services import daily_debriefs
    a, b = two_users
    t = _trade(a, "2026-09-08")
    daily_debriefs.save_daily_debrief(user_id=a, day="2026-09-08", input_key="k",
        result={"content_md": "### Session Summary\nok", "stats": {"trades": 1},
                "reviewed_trades": 1}, source_trade_ids=[t])
    assert _get(client, "/v1/reviews?day=2026-09-08", a).json()["daily"]["content_md"]
    assert _get(client, "/v1/reviews?day=2026-09-08", b).json()["daily"] is None


@pytest.mark.parametrize("query", ["?week=2026-9-7", "?day=tomorrow", "?owner=1", "?week=2026-09-08"])
def test_bad_or_unknown_query_is_422(client, two_users, query):
    a, _ = two_users
    assert _get(client, "/v1/reviews" + query, a).status_code == 422
```

(`?week=2026-09-08` is a Tuesday: `week` must be a Monday.)

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_api_reviews.py -v`
Expected: FAIL — 404 for `/v1/reviews`.

- [ ] **Step 3: Implement**

Schemas in `api/schemas/reviews.py` exactly as the Interfaces block, all subclassing the strict base used by `api/schemas/trades.py`. Router:

```python
router = APIRouter(prefix="/v1", tags=["reviews"])
_KNOWN = frozenset({"week", "day"})
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _iso_date(value: Optional[str], *, monday: bool = False) -> Optional[str]:
    if value is None:
        return None
    if not _ISO.fullmatch(value):
        raise HTTPException(status_code=422, detail="dates must be ISO YYYY-MM-DD")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="dates must be ISO YYYY-MM-DD") from None
    if monday and parsed.weekday() != 0:
        raise HTTPException(status_code=422, detail="week must be a Monday")
    return parsed.isoformat()


@router.get("/reviews")
def get_reviews(request: Request, week: Optional[str] = Query(default=None),
                day: Optional[str] = Query(default=None),
                user_id: int = Depends(current_user)) -> ReviewsResponse:
    unknown = sorted(set(request.query_params) - _KNOWN)
    if unknown:
        raise HTTPException(status_code=422, detail="unsupported query parameter(s)")
    week_iso, day_iso = _iso_date(week, monday=True), _iso_date(day)
    today = app_settings.today_for_owner(user_id)
    trades = get_trades(user_id=user_id)
    frame = pd.DataFrame([{c: getattr(t, c, None) for c in PATTERN_COLUMNS} for t in trades])
    if not frame.empty:
        frame = frame[frame["trade_date"].notna() & (frame["trade_date"] != "")].reset_index(drop=True)
    strategy = get_active_strategy(user_id)
    saved_week = weekly.get_weekly_review(week_iso, user_id) if week_iso else None
    saved_day = daily_debriefs.get_daily_debrief(user_id=user_id, day=day_iso) if day_iso else None
    return ReviewsResponse(
        patterns=PatternsLens(trades=len(frame), stats=review_periods.period_stats(frame),
                              insights=patterns.generate_insights(frame, strategy),
                              strategy_included=strategy is not None),
        weeks=[d.isoformat() for d in review_periods.completed_week_options(user_id, today=today)],
        days=[d.isoformat() for d in review_periods.completed_day_options(user_id, today=today)],
        complete_trades=sum(1 for t in trades if activation.is_complete_trade(t)),
        trades_for_review=activation.TRADES_FOR_REVIEW,
        ai_available=is_ai_enabled() or is_demo(),
        weekly=_note(saved_week, "week_start"),
        daily=_note(saved_day, "day"),
    )
```

`PATTERN_COLUMNS` is the `_DF_COLS` list copied verbatim from `6_Insights.py:134-150`. `_note(saved, key)` returns `None` or `SavedNote(period=saved[key], content_md=saved["content_md"], stats=saved.get("stats") or {}, reviewed_trades=int((saved.get("stats") or {}).get("trades") or saved.get("reviewed_trades") or 0), created_at=str(saved["created_at"]))`. `is_ai_enabled` from `src.tradelens.utils.ai_utils`; `is_demo` from `services.demo`. Stats pass through `to_jsonable` rules already enforced by the app (`profit_factor` is `None` for ∞).

- [ ] **Step 4: Run**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_api_reviews.py tests/test_api_security.py -q` (the route-walking owner test must include `/v1/reviews`); `python scripts/generate_openapi.py`; `npm --prefix web run api:types`.
Expected: pass; OpenAPI and `web/lib/api/schema.d.ts` updated (committed with this task).

- [ ] **Step 5: Commit**

```bash
git add src/tradelens/api tests/test_api_reviews.py web/lib/api
git commit -m "feat(api): GET /v1/reviews — deterministic patterns and review periods"
```

---

### Task B2: Weekly recap generation — enqueue, poll, worker (R2–R5, R7, R8)

**Files:**
- Modify: `src/tradelens/api/schemas/reviews.py`, `src/tradelens/api/routers/reviews.py`, `src/tradelens/api/worker.py`, `src/tradelens/services/weekly.py` (`on_usage`, guard, snapshot)
- Test: `tests/test_api_reviews.py`, `tests/test_review_worker.py`

**Interfaces:**
- Produces: `POST /v1/reviews/weekly` body `WeeklyRecapRequest{week: str}` → 202 `ReviewJobAccepted{job_id:int, status, created: bool}`; 409 `{"detail": "empty_period" | "not_enough_trades"}`; 429 fixed sentence; `GET /v1/reviews/jobs/{job_id}` → `ReviewJobStatus{job_id, kind: Literal["weekly_recap","daily_debrief"], status, note: Optional[SavedNote], error: Optional[str]}` (404 foreign/missing/other kinds). `weekly.WEEKLY_JOB_KIND = "weekly_recap"`; `weekly.MAX_WEEKLY_PER_WINDOW = 10`; `weekly.REVIEW_WINDOW_HOURS = 24`; `weekly.week_snapshot(user_id, monday) -> list[dict]` (id + `_TRADE_COLS`, ordered by id); `generate_weekly_review(..., on_usage: Optional[Callable[[Usage], None]] = None)` calls `on_usage(usage)` immediately after `chat` and runs `reflection_guard.reject_forward_looking(content, WeeklyReviewError)` after `_validate_sections`. Worker handler `_weekly_recap_handler(user_id, payload) -> "weekly_recap:<row id>"`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_api_reviews.py`)

```python
def _complete_week(owner, monday="2026-09-07", n=5):
    return [_trade(owner, "2026-09-%02d" % (7 + (i % 5))) for i in range(n)]


def test_generate_weekly_enqueues_one_job_for_a_double_click(client, two_users):
    a, _ = two_users
    _complete_week(a)
    first = _post(client, "/v1/reviews/weekly", {"week": "2026-09-07"}, a)
    second = _post(client, "/v1/reviews/weekly", {"week": "2026-09-07"}, a)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert (first.json()["created"], second.json()["created"]) == (True, False)


def test_a_changed_week_is_a_new_job(client, two_users):
    a, _ = two_users
    _complete_week(a)
    first = _post(client, "/v1/reviews/weekly", {"week": "2026-09-07"}, a).json()["job_id"]
    _trade(a, "2026-09-09")
    assert _post(client, "/v1/reviews/weekly", {"week": "2026-09-07"}, a).json()["job_id"] != first


def test_weekly_refuses_empty_and_undersized(client, two_users):
    a, _ = two_users
    assert _post(client, "/v1/reviews/weekly", {"week": "2026-09-07"}, a).json()["detail"] == "empty_period"
    _trade(a, "2026-09-08")
    r = _post(client, "/v1/reviews/weekly", {"week": "2026-09-07"}, a)
    assert (r.status_code, r.json()["detail"]) == (409, "not_enough_trades")


@pytest.mark.parametrize("body", [{"week": "2026-09-08"}, {"week": "2026-09-07", "user_id": 1}, {}])
def test_weekly_body_is_strict(client, two_users, body):
    a, _ = two_users
    assert _post(client, "/v1/reviews/weekly", body, a).status_code == 422


def test_weekly_rate_limit_is_429_and_keeps_existing_jobs(client, two_users, monkeypatch):
    from src.tradelens.services import weekly
    a, _ = two_users
    monkeypatch.setattr(weekly, "MAX_WEEKLY_PER_WINDOW", 1)
    _complete_week(a)
    first = _post(client, "/v1/reviews/weekly", {"week": "2026-09-07"}, a).json()["job_id"]
    _trade(a, "2026-09-10")
    assert _post(client, "/v1/reviews/weekly", {"week": "2026-09-07"}, a).status_code == 429
    assert _get(client, "/v1/reviews/jobs/%d" % first, a).status_code == 200


def test_job_poll_is_owner_and_kind_scoped(client, two_users):
    a, b = two_users
    _complete_week(a)
    job = _post(client, "/v1/reviews/weekly", {"week": "2026-09-07"}, a).json()["job_id"]
    assert _get(client, "/v1/reviews/jobs/%d" % job, b).status_code == 404
```

`tests/test_review_worker.py`:

```python
import json

import pytest

from src.tradelens.api import jobs, worker
from src.tradelens.db.models import AIJob, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import cost, weekly

GOOD = "\n\n".join("%s\nReflection." % h for h in weekly._REQUIRED_SECTIONS)


def _trade(owner, day):
    db = SessionLocal()
    try:
        row = Trade(user_id=owner, asset="NQ", direction="Long", result="Win", trade_date=day, pnl=5.0)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _payload(owner):
    ids = [_trade(owner, "2026-09-08") for _ in range(2)]
    return {"week": "2026-09-07", "key": "weekly_recap:x",
            "source_trade_ids": ids, "strategy_fingerprint": "f"}


def test_handler_saves_and_logs_usage_even_when_validation_fails(two_users, monkeypatch):
    a, _ = two_users
    logged = []
    monkeypatch.setattr(worker, "log_ai_usage", lambda feature, usage, user_id: logged.append(feature))
    monkeypatch.setattr("src.tradelens.services.weekly.chat",
                        lambda **k: ("### What Worked\nonly one", _usage()))
    with pytest.raises(weekly.WeeklyReviewError):
        worker._weekly_recap_handler(a, _payload(a))
    assert logged == ["Weekly Review"]


def test_handler_refuses_trade_guidance(two_users, monkeypatch):
    a, _ = two_users
    monkeypatch.setattr(worker, "log_ai_usage", lambda *x, **k: None)
    bad = GOOD.replace("Reflection.", "Next week, short the open.", 1)
    monkeypatch.setattr("src.tradelens.services.weekly.chat", lambda **k: (bad, _usage()))
    with pytest.raises(weekly.WeeklyReviewError):
        worker._weekly_recap_handler(a, _payload(a))


def test_handler_fails_closed_when_trades_were_deleted(two_users, monkeypatch):
    from src.tradelens.services.daily_debriefs import ReviewSourceGone
    a, _ = two_users
    monkeypatch.setattr(worker, "log_ai_usage", lambda *x, **k: None)
    monkeypatch.setattr("src.tradelens.services.weekly.chat", lambda **k: (GOOD, _usage()))
    payload = _payload(a)
    db = SessionLocal()
    try:
        db.query(Trade).filter(Trade.user_id == a).delete()
        db.commit()
    finally:
        db.close()
    with pytest.raises((ReviewSourceGone, weekly.WeeklyReviewError)):
        worker._weekly_recap_handler(a, payload)
    assert weekly.get_weekly_review("2026-09-07", a) is None


def test_handler_is_registered():
    assert worker.HANDLERS["weekly_recap"] is worker._weekly_recap_handler


def _usage():
    from src.tradelens.services.ai_client import Usage
    return Usage("claude-opus-5", 1, 1, 0, 0.0, 0.0)
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_api_reviews.py tests/test_review_worker.py -v`
Expected: FAIL — 405/404 on `/v1/reviews/weekly`; `AttributeError: _weekly_recap_handler`.

- [ ] **Step 3: Implement**

`weekly.py`: add constants; `on_usage` parameter (call right after `chat`, before the `AIUnavailable` check, exactly as `trade_summary.generate_trade_summary`); guard after `_validate_sections`; and

```python
def week_snapshot(user_id: int, monday: str) -> list:
    owner = require_user_id(user_id)
    _, sunday = week_bounds(monday)
    rows = get_trades(start_date=monday, end_date=sunday, user_id=owner)
    return [{"id": int(t.id), **{c: getattr(t, c, None) for c in _TRADE_COLS}}
            for t in sorted(rows, key=lambda r: r.id)]
```

Router:

```python
@router.post("/reviews/weekly", status_code=status.HTTP_202_ACCEPTED)
def enqueue_weekly_recap(payload: WeeklyRecapRequest, user_id: int = Depends(current_user)) -> ReviewJobAccepted:
    monday = _iso_date(payload.week, monday=True)
    snapshot = weekly.week_snapshot(user_id, monday)
    if not snapshot:
        raise HTTPException(status_code=409, detail="empty_period")
    complete = sum(1 for t in get_trades(user_id=user_id) if activation.is_complete_trade(t))
    if complete < activation.TRADES_FOR_REVIEW and weekly.get_weekly_review(monday, user_id) is None:
        raise HTTPException(status_code=409, detail="not_enough_trades")
    try:
        fingerprint = trade_analysis.strategy_input_fingerprint(user_id)
    except trade_analysis.AIInputVersionUnavailable:
        raise HTTPException(status_code=503, detail="review_unavailable") from None
    key = weekly.WEEKLY_JOB_KIND + ":" + _input_key(user_id, monday, snapshot, fingerprint)
    job_payload = {"week": monday, "key": key, "strategy_fingerprint": fingerprint,
                   "source_trade_ids": [row["id"] for row in snapshot]}
    job_id, created = jobs.enqueue_with_limit(
        user_id, weekly.WEEKLY_JOB_KIND, key, job_payload,
        since=datetime.now(timezone.utc) - timedelta(hours=weekly.REVIEW_WINDOW_HOURS),
        limit=weekly.MAX_WEEKLY_PER_WINDOW)
    if job_id is None:
        raise HTTPException(status_code=429, detail=WEEKLY_LIMIT_MESSAGE)
    job = jobs.get_owned_job(job_id, user_id)
    if job is None:
        raise HTTPException(status_code=500, detail="review job unavailable")
    return ReviewJobAccepted(job_id=job_id, status=job.status, created=created)


def _input_key(owner: int, period: str, snapshot: list, fingerprint: str) -> str:
    canonical = json.dumps({"owner": owner, "period": period, "trades": snapshot,
                            "strategy": fingerprint},
                           sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                           allow_nan=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

`WEEKLY_LIMIT_MESSAGE = "You've reached today's limit for weekly recaps. Recaps you've already generated are still available."` The job payload carries **trade ids only, never trade text** — the worker re-reads trades inside the owner's tenant.

Poll route `GET /reviews/jobs/{job_id}`: `get_owned_job`; 404 unless `kind in ("weekly_recap", "daily_debrief")`; on `succeeded`, parse `result_ref` `"<kind>:<int>"` (same strict prefix/int checks as `trades.py:386-400`), resolve with `weekly.get_weekly_review_by_id` / `daily_debriefs.get_daily_debrief_by_id` owner-scoped (add `get_weekly_review_by_id(result_id, user_id) -> Optional[dict]` to `weekly.py`), 500 fixed detail on any mismatch; `error` is the job's stored safe message.

Worker:

```python
def _weekly_recap_handler(user_id: int, payload: dict) -> str:
    monday = payload["week"]
    source_ids = [int(i) for i in payload["source_trade_ids"]]
    review, _usage = generate_weekly_review(
        monday, user_id=user_id, strategy_profile=get_active_strategy(user_id),
        on_usage=lambda usage: log_ai_usage("Weekly Review", usage, user_id=user_id),
    )
    if review["empty"]:
        raise WeeklyReviewError("This week has nothing logged to review.")
    row_id = save_weekly_review_from_sources(user_id=user_id, review=review,
                                             source_trade_ids=source_ids)
    return f"weekly_recap:{row_id}"
```

Register `"weekly_recap": _weekly_recap_handler` in `HANDLERS`.

- [ ] **Step 4: Run**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_api_reviews.py tests/test_review_worker.py tests/test_weekly.py tests/test_weekly_review.py tests/test_api_security.py -q`; regenerate OpenAPI + types.
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradelens tests/test_api_reviews.py tests/test_review_worker.py web/lib/api
git commit -m "feat(reviews): job-backed weekly recap — idempotent, rate-limited, source-locked"
```

---

### Task B3: Daily debrief generation (R1, R3–R5, R7, R8)

**Files:**
- Modify: `src/tradelens/api/schemas/reviews.py`, `src/tradelens/api/routers/reviews.py`, `src/tradelens/api/worker.py`, `src/tradelens/services/debrief.py`
- Test: `tests/test_api_reviews.py`, `tests/test_review_worker.py`

**Interfaces:**
- Produces: `POST /v1/reviews/daily` body `DailyDebriefRequest{day: str}` → 202 `ReviewJobAccepted`; 409 `empty_period`; 429 `DAILY_LIMIT_MESSAGE = "You've reached today's limit for daily debriefs. Debriefs you've already generated are still available."`. `debrief.DAILY_JOB_KIND = "daily_debrief"`, `MAX_DAILY_PER_WINDOW = 20`; `generate_debrief(..., on_usage=None)` with guard after `_validate_sections` (raising `DebriefError`). Worker `_daily_debrief_handler(user_id, payload) -> "daily_debrief:<row id>"`, feature `"Daily Debrief"`, saves with `save_daily_debrief(user_id=, day=, input_key=payload["key"], result={"content_md", "stats", "reviewed_trades": len(trades)}, source_trade_ids=)`.

- [ ] **Step 1: Write the failing tests** — the six B2 API tests repeated for `/v1/reviews/daily` with `{"day": "2026-09-08"}` (double click → one job; changed day's trades → new job; empty day → 409 `empty_period`; strict body including `{"day": "2026-09-08", "trades": [1]}` → 422; rate limit via `monkeypatch.setattr(debrief, "MAX_DAILY_PER_WINDOW", 1)` → 429; foreign poll → 404), and the four B2 worker tests repeated for `_daily_debrief_handler` with `debrief._REQUIRED_SECTIONS`, patching `src.tradelens.services.debrief.chat`, payload `{"day": "2026-09-08", "key": "daily_debrief:x", "source_trade_ids": ids, "strategy_fingerprint": "f"}`, feature `"Daily Debrief"`, and `daily_debriefs.get_daily_debrief(user_id=a, day="2026-09-08") is None` after a deleted source. Write each test out in full in the two files (no shared parametrisation across kinds, so a failure names its kind).

- [ ] **Step 2: Run to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_api_reviews.py -k daily tests/test_review_worker.py -k daily -v`
Expected: FAIL — 404/405 and missing handler.

- [ ] **Step 3: Implement** — mirror B2: `_iso_date(payload.day)`; the day must be in `completed_day_options(owner, today=today_for_owner(owner))` else 409 `empty_period`; snapshot = `get_trades(start_date=day, end_date=day, user_id=owner)` → `[{"id", **{f: getattr(t, f) for f in debrief._PAYLOAD_FIELDS}, "notes": (t.notes or "")[:200]}]` ordered by id; no weekly gate; key `daily_debrief:<_input_key(owner, day, snapshot, fingerprint)>`; payload ids only. Worker re-reads `get_trades(start_date=day, end_date=day, user_id=user_id)`, calls `generate_debrief(trades, strategy_profile=get_active_strategy(user_id), period_label=f"Trading day {day}", on_usage=…)`, raises `DebriefError("No trades logged on this day.")` when empty, saves, returns the pointer. Register in `HANDLERS`.

- [ ] **Step 4: Run** — `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_api_reviews.py tests/test_review_worker.py tests/test_debrief.py tests/test_api_security.py -q`; regenerate OpenAPI + types. Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/tradelens tests/test_api_reviews.py tests/test_review_worker.py web/lib/api
git commit -m "feat(reviews): job-backed daily debrief — persisted, idempotent, source-locked"
```

---

## Group C — relays and the server bridge

### Task C1: `lib/app/reviews.ts`, `lib/app/reviews-relay.ts`, three routes

**Files:**
- Create: `web/lib/app/reviews.ts`, `web/lib/app/reviews-relay.ts`, `web/app/api/reviews/weekly/route.ts`, `web/app/api/reviews/daily/route.ts`, `web/app/api/reviews/jobs/[jobId]/route.ts`
- Test: `web/__tests__/reviews-relay.test.ts`

**Interfaces:**
- Produces: types `ReviewsResponse`, `ReviewJobAccepted`, `ReviewJobStatus`, `SavedNote` from `components["schemas"]`; `fetchReviews(token, { week?, day? })`; `enqueueWeeklyRecap(token, body: unknown)`; `enqueueDailyDebrief(token, body: unknown)`; `fetchReviewJob(token, jobId: number)`; `REVIEWS_NO_STORE`; `authorizeReviewsRelay(request)` (identical contract to `authorizeTradeSummaryRelay`: 403 when `SITE_ORIGIN` unset or cross-origin **before** the session lookup, 401 no session, 403 `appLayoutRedirect`); `reviewsRelayFailure(error: unknown): NextResponse` mapping `ApiError` 409 → `{ ok:false, detail: "empty_period" | "not_enough_trades" }` (any other 409 detail → `{ ok:false }`), 429 → `{ ok:false, error:"rate_limited", detail }` when detail is a string, 422/404/401/403 → `{ ok:false }` with that status, anything else → 502 `{ ok:false }`.

- [ ] **Step 1: Write the failing tests** (`web/__tests__/reviews-relay.test.ts`, mocking `@/lib/auth/session`, `@/lib/env` and `@/lib/app/reviews` as `web/__tests__/settings-relay.test.ts` does):

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";

const env = { SITE_ORIGIN: "https://app.test" as string | undefined };
const authenticate = vi.fn();
const appRedirect = vi.fn();
const enqueueWeekly = vi.fn();
const enqueueDaily = vi.fn();
const fetchJob = vi.fn();

vi.mock("@/lib/env", () => ({ optionalEnv: (k: string) => (env as Record<string, string | undefined>)[k] }));
vi.mock("@/lib/auth/session", () => ({
  sessionTokenFrom: () => "tok",
  authenticateSessionToken: (...a: unknown[]) => authenticate(...a),
  appLayoutRedirect: (...a: unknown[]) => appRedirect(...a),
}));
vi.mock("@/lib/app/reviews", async (orig) => ({
  ...(await orig<typeof import("@/lib/app/reviews")>()),
  enqueueWeeklyRecap: (...a: unknown[]) => enqueueWeekly(...a),
  enqueueDailyDebrief: (...a: unknown[]) => enqueueDaily(...a),
  fetchReviewJob: (...a: unknown[]) => fetchJob(...a),
}));

import { ApiError } from "@/lib/api/client";
import { POST as weekly } from "@/app/api/reviews/weekly/route";
import { POST as daily } from "@/app/api/reviews/daily/route";
import { GET as job } from "@/app/api/reviews/jobs/[jobId]/route";

function post(body: unknown, origin = "https://app.test") {
  return new Request("https://app.test/api/reviews/weekly", {
    method: "POST", headers: { origin, "content-type": "application/json" }, body: JSON.stringify(body),
  });
}

beforeEach(() => {
  env.SITE_ORIGIN = "https://app.test";
  authenticate.mockReset().mockResolvedValue({ userId: 2 });
  appRedirect.mockReset().mockReturnValue(null);
  enqueueWeekly.mockReset();
  enqueueDaily.mockReset();
  fetchJob.mockReset();
});

describe.each([["weekly", weekly, enqueueWeekly], ["daily", daily, enqueueDaily]] as const)(
  "the %s generate relay", (_name, route, enqueue) => {
    it("refuses with 403 before reading the session when SITE_ORIGIN is unset", async () => {
      env.SITE_ORIGIN = undefined;
      expect((await route(post({ week: "2026-09-07" }))).status).toBe(403);
      expect(authenticate).not.toHaveBeenCalled();
    });

    it("refuses a cross-origin request", async () => {
      expect((await route(post({}, "https://evil.test"))).status).toBe(403);
      expect(enqueue).not.toHaveBeenCalled();
    });

    it("refuses an ineligible account before the backend", async () => {
      appRedirect.mockReturnValue("/onboarding");
      expect((await route(post({ week: "2026-09-07" }))).status).toBe(403);
      expect(enqueue).not.toHaveBeenCalled();
    });

    it("forwards 202, no-store", async () => {
      enqueue.mockResolvedValue({ job_id: 9, status: "queued", created: true });
      const res = await route(post({ week: "2026-09-07" }));
      expect(res.status).toBe(202);
      expect(res.headers.get("cache-control")).toContain("no-store");
      expect(await res.json()).toEqual({ job_id: 9, status: "queued", created: true });
    });

    it("maps a 409 to its fixed code and nothing else", async () => {
      enqueue.mockRejectedValue(new ApiError(409, { detail: "not_enough_trades", secret: "x" }));
      const res = await route(post({ week: "2026-09-07" }));
      expect(await res.json()).toEqual({ ok: false, detail: "not_enough_trades" });
    });

    it("never forwards an unknown 409 detail", async () => {
      enqueue.mockRejectedValue(new ApiError(409, { detail: "driver said postgres://u:p@h" }));
      expect(await (await route(post({ week: "2026-09-07" }))).json()).toEqual({ ok: false });
    });

    it("forwards a 429 sentence", async () => {
      enqueue.mockRejectedValue(new ApiError(429, { detail: "limit" }));
      const res = await route(post({ week: "2026-09-07" }));
      expect(res.status).toBe(429);
      expect(await res.json()).toEqual({ ok: false, error: "rate_limited", detail: "limit" });
    });
  });

describe("the job poll relay", () => {
  const params = (jobId: string) => ({ params: Promise.resolve({ jobId }) });
  const get = () => new Request("https://app.test/api/reviews/jobs/9", { headers: { origin: "https://app.test" } });

  it.each(["0", "-1", "abc", "1e3", "99999999999999999"])("404s a malformed id %s without the backend", async (id) => {
    expect((await job(get(), params(id))).status).toBe(404);
    expect(fetchJob).not.toHaveBeenCalled();
  });

  it("forwards a job", async () => {
    fetchJob.mockResolvedValue({ job_id: 9, kind: "weekly_recap", status: "running", note: null, error: null });
    expect((await job(get(), params("9"))).status).toBe(200);
  });
});
```

(If `ApiError`'s constructor signature differs, read `web/lib/api/client.ts` and construct it the way `settings-relay.test.ts` does.)

- [ ] **Step 2: Run to verify it fails** — from `web/`: `npx vitest run __tests__/reviews-relay.test.ts`. Expected: FAIL — cannot resolve `@/app/api/reviews/weekly/route`.

- [ ] **Step 3: Implement** — `reviews.ts` (`import "server-only"`), `callApi` wrappers: `fetchReviews` builds `?week=`/`?day=` only for present values; the enqueue helpers POST the parsed body as-is (FastAPI validates); `fetchReviewJob` GETs `/v1/reviews/jobs/${jobId}`. `reviews-relay.ts` copies `lib/app/trade-summary-relay.ts` (renamed exports) plus `reviewsRelayFailure` per the Interfaces block. Each route: `runtime = "nodejs"`, `dynamic = "force-dynamic"`, authorise, bounded `request.json()` (400 `{ ok:false }` on parse failure), call, 202/200 with `REVIEWS_NO_STORE`, `catch (error) { return reviewsRelayFailure(error); }`. Poll route uses the `parseJobId` regex from `app/api/trades/summary/[jobId]/route.ts`.

- [ ] **Step 4: Run** — `npx vitest run __tests__/reviews-relay.test.ts`, `npx tsc --noEmit`, `npx eslint .`. Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add web/lib/app/reviews.ts web/lib/app/reviews-relay.ts web/app/api/reviews web/__tests__/reviews-relay.test.ts
git commit -m "feat(web): AI Reviews relays and server bridge"
```

---

## Group D — the Reviews page

### Task D1: Page, lens tabs, Patterns lens, note reader

**Files:**
- Replace: `web/app/app/reviews/page.tsx`; create `web/app/app/reviews/loading.tsx`, `web/app/app/reviews/error.tsx`
- Create: `web/components/app/reviews/lens-tabs.tsx`, `patterns-lens.tsx`, `review-note.tsx`, `period-strip.tsx`
- Test: `web/__tests__/reviews-page.test.tsx`, `web/__tests__/reviews-note.test.tsx`

**Interfaces:**
- Page: Server Component; search params `lens` ∈ `patterns|weekly|daily` (default `patterns`), `week`, `day` (forwarded to `fetchReviews` only when ISO-shaped); failed load → `ErrorState` "AI Reviews did not load" and **no generate controls**.
- `ReviewNote({ title, sample, content, confidence, limitation? })` — splits on `^### `, renders each section heading as `<h3>` and body as text (bold `**x**` and `- ` lists only, exactly `summary-panel.tsx`'s `MarkdownBody`), first section open and the rest inside `<details><summary>Read full note</summary>…</details>`; **never** `dangerouslySetInnerHTML`.
- `PeriodStrip({ stats })` — Trades, Win rate, Net P&L, Profit factor (`∞` when `profit_factor` is null and trades > 0; `N/A` when trades is 0), Edge leak.

- [ ] **Step 1: Write the failing tests**

`reviews-note.test.tsx`:

```tsx
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReviewNote } from "@/components/app/reviews/review-note";

const MD = "### What Worked\nKept **rules**.\n\n### What Didn't\n- late entries\n\n### Observed Patterns\n<img src=x onerror=alert(1)>";

describe("ReviewNote", () => {
  it("renders model markdown as text, never as HTML", () => {
    const { container } = render(<ReviewNote title="Week in review" sample="2026-09-07" content={MD} confidence="low" />);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  });

  it("shows the first section and discloses the rest", () => {
    render(<ReviewNote title="Week in review" sample="2026-09-07" content={MD} confidence="low" />);
    expect(screen.getByRole("heading", { name: "What Worked" })).toBeVisible();
    expect(screen.getByText("Read full note")).toBeInTheDocument();
  });

  it("states the sample and confidence", () => {
    render(<ReviewNote title="Day in review" sample="2026-09-08" content={MD} confidence="medium" limitation="Small sample — read this as a description, not a rule." />);
    expect(screen.getByText(/confidence: medium/i)).toBeInTheDocument();
    expect(screen.getByText(/Small sample/)).toBeInTheDocument();
  });
});
```

`reviews-page.test.tsx` (mocks as `settings-page-load.test.tsx`: `next/headers`, `next/navigation`, `@/lib/auth/session`, `@/lib/app/reviews`):

```tsx
// fixture
function reviews(overrides = {}) {
  return {
    patterns: { trades: 12, stats: { trades: 12, win_rate: 0.5, total_pnl: 120, profit_factor: 1.4, total_edge_leak: -20 },
      insights: [{ title: "London Open", body: "Best window.", confidence: "medium", type: "positive", min_trades: 3 },
                 { title: "After a loss", body: "Re-entries lose.", confidence: "low", type: "negative", min_trades: 3 }],
      strategy_included: true },
    weeks: ["2026-09-07"], days: ["2026-09-08"], complete_trades: 12, trades_for_review: 5,
    ai_available: true, weekly: null, daily: null, ...overrides,
  };
}
```

Tests: (1) default lens is Patterns — heading "AI Reviews", tab "Patterns" `aria-selected="true"`, the lead insight body "Best window." as the thesis, "After a loss" as finding 1, strip shows "12" trades and "1.4x"; (2) `lens=weekly` passes `week` through to `fetchReviews` only when ISO (`week=2026-09-07` → called with `{ week: "2026-09-07" }`; `week=../x` → called with `{}`); (3) a failed `fetchReviews` renders role `alert` "AI Reviews did not load" and zero buttons; (4) patterns with `insights: []` renders "No repeating patterns yet" and "Journal … more completed trades" copy when trades < 5; (5) the page contains the sentence "Reflection only — never signals or advice."; (6) invalid session → `redirect:/login` and `fetchReviews` not called.

- [ ] **Step 2: Run to verify they fail** — `npx vitest run __tests__/reviews-page.test.tsx __tests__/reviews-note.test.tsx`. Expected: FAIL — modules not found.

- [ ] **Step 3: Implement** the page (auth sequence identical to `web/app/app/settings/page.tsx:27-42`), `LensTabs` (links `?lens=` with `role="tab"`, `aria-selected`, 44px targets, questions from `6_Insights.py:109-113` as each lens's subheading), `PatternsLens` (sort by confidence high→medium→low; lead = first; findings = next four; review action "Re-read the trades behind “<lead>” in the Journal." linking `/app/journal`; limitation under five trades "Fewer than five trades — these describe a handful of records, not a pattern."; evidence list "Trades reviewed: N", "Strategy profile: included|not included", "Computed from your journal — no AI call"), `ReviewNote`, `PeriodStrip`. `loading.tsx` uses the existing skeleton primitive; `error.tsx` the existing `ErrorState` with a retry.

- [ ] **Step 4: Run** — the two test files, `npx tsc --noEmit`, `npx eslint .`. Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add web/app/app/reviews web/components/app/reviews web/__tests__/reviews-page.test.tsx web/__tests__/reviews-note.test.tsx
git commit -m "feat(web): AI Reviews page — lenses, deterministic patterns, safe note reader"
```

### Task D2: Weekly and Daily lenses with the job hook

**Files:**
- Create: `web/components/app/reviews/use-review-job.ts`, `weekly-lens.tsx`, `daily-lens.tsx`
- Modify: `web/components/app/overview/next-review-action.tsx:62` (`href="/app/reviews?lens=weekly"`)
- Test: `web/__tests__/reviews-job-hook.test.tsx`, `reviews-weekly-lens.test.tsx`, `reviews-daily-lens.test.tsx`

**Interfaces:**
- `useReviewJob(endpoint: "/api/reviews/weekly" | "/api/reviews/daily")` → `{ state: "idle"|"running"|"succeeded"|"failed"|"rate_limited"|"refused", note: SavedNote|null, message: string|null, start(body: object): Promise<void> }`. Poll delays copied from `summary-panel.tsx:15-20`; AbortController cleared on controller identity; a 409 → `refused` with message mapped from `detail` (`empty_period` → "Nothing is logged for this period.", `not_enough_trades` → "Journal more completed trades before a weekly recap."); 429 → `rate_limited` with the server sentence; any other failure → `failed` "The review could not be generated. Try again.".
- `WeeklyLens({ weeks, selectedWeek, saved, completeTrades, tradesForReview, aiAvailable })`: week `<select>` (navigates `?lens=weekly&week=`); empty weeks → "No completed week to review" + Journal link; gate copy "Journal N more completed trades" when `completeTrades < tradesForReview` and no saved note; saved note shown with `PeriodStrip` + `ReviewNote` titled "Week in review"; button "Generate weekly recap" (no saved note) / "Regenerate this week" (saved); **the saved note stays on screen while regenerating and after a failed regeneration**; nothing is enqueued on render; AI unavailable → no button, "AI reviews are unavailable right now. Saved recaps are still shown."
- `DailyLens({ days, selectedDay, saved, aiAvailable })`: same pattern; button "Generate debrief for <day>" (the lens has no per-day count; the API refuses an empty day with `empty_period`); saved note titled "Day in review" with link "Open these trades in the Journal" → `/app/journal?from=<day>&to=<day>`.

- [ ] **Step 1: Write the failing tests** — hook: (a) `start` POSTs once for a double call while running; (b) succeeds after `queued → running → succeeded` polls and exposes `note`; (c) `failed` job → `failed` message; (d) 429 → server sentence; (e) 409 `not_enough_trades` → mapped copy; (f) unmount aborts without setting state. Weekly lens: (a) render never calls `fetch`; (b) gate copy when undersized with no saved note and no button; (c) saved note visible, click "Regenerate this week", job fails → saved note still visible and failure copy shown; (d) success replaces the note; (e) AI unavailable → saved note shown, no button. Daily lens: (a) render never calls `fetch`; (b) generate → poll → "Day in review" note; (c) journal link href includes `from=2026-09-08&to=2026-09-08`. Use `vi.useFakeTimers()` with `await vi.advanceTimersByTimeAsync(…)` for polling, and a `fetchMock` sequence (`mockResolvedValueOnce`) per scenario; write each test body out in full.

- [ ] **Step 2: Run to verify they fail** — `npx vitest run __tests__/reviews-job-hook.test.tsx __tests__/reviews-weekly-lens.test.tsx __tests__/reviews-daily-lens.test.tsx`. Expected: FAIL — modules not found.

- [ ] **Step 3: Implement** per the Interfaces block; wire the lenses into the page for `lens=weekly|daily`; update the Overview link.

- [ ] **Step 4: Run** — full `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build` (localhost origins). Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add web/components/app/reviews web/components/app/overview/next-review-action.tsx web/app/app/reviews web/__tests__/reviews-*.test.tsx
git commit -m "feat(web): weekly recap and daily debrief lenses — explicit generate, polled jobs"
```

---

## Group E — verification, battery, handoff

- [ ] **E1 Gates** at the tip with exact counts (Python full suite with the three known Streamlit boot failures named separately; parity; ruff; black; OpenAPI/types drift; one alembic head `h4i5j6k7l8m9` and the upgrade/downgrade drill; web vitest/tsc/eslint/build; credential scan of added lines).
- [ ] **E2 Mutation battery** (hardened harness, controls first, clean HEAD) — at minimum: idempotency key omits the trade snapshot; key omits the strategy fingerprint; `enqueue_with_limit` replaced by `enqueue`; weekly gate removed; empty-period check removed; poll accepts another kind; poll resolves result without owner filter; worker saves without `lock_sources`; `on_usage` called after validation; guard call removed (weekly, daily); `_delete_derived_review_state` omits `WeeklyReview` / `DailyDebrief` / a job kind; `DailyDebrief` missing from `_OWNED_BY_USER`; relay forwards unknown 409 detail; relay checks session before `SITE_ORIGIN`; `ReviewNote` uses `dangerouslySetInnerHTML`; lens enqueues on render; failed regeneration clears the saved note; page renders controls over a failed load.
- [ ] **E3 Review** — independent reviewer in a private extraction; deepest on B2/B3 and A2/A3.
- [ ] **E4 Handoff** in `docs/coordination/CLAUDE_CODEX_HANDOFF.md`: commits; decisions R1–R9 as approved; parity mapping of each §8 AI Reviews item to file + test (for Phase 10 R1 ledger); battery table; gates with exact counts; honest gaps (authenticated browser smoke NOT RUN; real PostgreSQL race of save-versus-delete NOT RUN; live Anthropic not exercised; lexical guard is defense-in-depth); Phase 10 hard gates and Phase 9 hardening items carried; the migration-number note for Phase 10 Group F. Request Codex review. **Stop before merge.**

---

## Self-review (2026-09-14)

- **Spec coverage (§8 AI Reviews):** Patterns candidates/cards/confidence/evidence/sample size → B1, D1; next review action → D1 (review action) and D2 (Overview deep link); Weekly Recap week selector/generate/retry/validated sections → B2, D2; Daily Debrief day selector/five sections → B3, D2; read-full-note disclosure → D1 `ReviewNote`. §9.5 double spend → R3/R4 in B2/B3. Deletion honesty (S7/R8) → A3.
- **Placeholder scan:** B3 and D2 tests are specified per scenario with the exact assertions; implementers write them in full (no shared parametrisation across kinds).
- **Type consistency:** `SavedNote`, `ReviewJobAccepted`, `ReviewJobStatus`, `PeriodStats` names match across B1–B3, C1 and D1–D2; job kinds `weekly_recap`/`daily_debrief` match router, worker, deletion and relay.
