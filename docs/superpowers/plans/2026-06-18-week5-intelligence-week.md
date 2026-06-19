# Week 5 "Intelligence Week" Implementation Plan

> **For agentic workers:** Each phase = one coherent commit (max 2), message `week5-d<N>: <summary>`. Write failing tests FIRST, implement to green, run `venv/bin/python -m pytest -q` after every phase, report, then await approval for the next phase. Steps tracked per phase.

**Goal:** Turn TradeLens into an SMC/ICT-native post-trade reflection journal with killzone analytics, AI pattern detection, weekly AI review, a correction-learning loop, an AI partner chat, and hardening — all on the Anthropic API.

**Architecture:** Streamlit pages (render only) → `services/*.py` (all business logic, Streamlit-free) → SQLAlchemy/SQLite. All AI calls route through one new `services/ai_client.py` wrapping the **Anthropic SDK**. Every AI feature works under `DEMO_MODE=true` with zero spend.

**Tech Stack:** Python 3.11, Streamlit, SQLAlchemy 2.x, Alembic, Plotly, pandas, `anthropic` SDK, pytest.

## Global Constraints (verbatim from spec + CLAUDE.md)

- NO `streamlit` imports inside `services/` or `db/`.
- All business logic in `services/`; pages only render and call services.
- Alembic for every schema change; `downgrade()` implemented **and reversible on SQLite** (use `batch_alter_table`).
- All AI calls go through `services/ai_client.py` ONLY — never call the SDK from a page.
- Models: `claude-fable-5` (vision, journal, weekly, patterns, partner); `claude-haiku-4-5` (grading pre-pass only); `claude-opus-4-8` (refusal fallback).
- Adaptive thinking always on; `effort="medium"` default; thinking `display="summarized"`, store summary when present.
- Prompt caching (`cache_control`) on the Strategy Profile system block.
- Persist `tokens_input`, `tokens_output`, `cost_usd` on every call into `aianalysis`. Pricing: $10/M in, $50/M out, ~$1/M cache-read.
- Refusal → server-side `fallbacks=[{"model":"claude-opus-4-8"}]`; if the whole chain refuses, return typed `AIUnavailable` the UI renders gracefully.
- API keys from `st.secrets`/env only. Never hardcode.
- `DEMO_MODE=true` → cached/mock output, zero API spend.
- `prompts/` contracts: extend, never rewrite. (Only `screenshot_v2.txt` exists; the rest are created new per their contracts.)
- Do not change `scripts/seed.py` semantics (60 trades; note: README/seed say 60, CLAUDE.md says "60", spec says "50" — actual seed count to be confirmed and preserved).
- No live signals/predictions/recommendations anywhere, including UI copy.

## Baseline (verified 2026-06-18)

- **184 tests passing** (`venv/`, not `.venv/`), ~4.5s. This is the floor — never regress.
- **7 ruff errors** (all auto-fixable) — baseline is NOT clean; fixed in Phase 0.
- `black` not installed — install it in Phase 0 to honor the documented `black --check` command.
- **Phase 1 (week5-d1) already complete**: 11 SMC/ICT columns + migration `g7h8i9j0k1l2`, `sessions.assign_killzone()` (DST-correct ET), `screenshot_v2.txt` extended, `seed.py` SMC fields, `1_NewTrade.py` SMC setup + killzone auto-fill, `test_sessions.py`.
  - **Gap to fix (Phase 0):** migration `downgrade()` is a no-op on SQLite → not reversible. Re-implement with `batch_alter_table` + add an up/down round-trip test.

## Page numbering (resolves spec collision)

Existing: `1_NewTrade, 2_Trades, 3_TradeDetail, 4_Analytics, 5_Strategy, 7_Settings`.
New: `6_Calendar` (P2), `7_Weekly_Review` (P4), `8_AI_Partner` (P6). Rename `7_Settings.py` → `9_Settings.py` (P0, to free the slot and keep ordering sane).

---

## Phase 0 — Anthropic migration + DEMO_MODE + housekeeping (NEW, prerequisite)

Commit: `week5-d1.5: migrate AI layer to Anthropic (ai_client) + DEMO_MODE`

**Files:**
- Create `src/tradelens/services/ai_client.py`
- Modify `src/tradelens/config.py`
- Modify `src/tradelens/services/vision.py`, `journal.py`, `grading.py`
- Modify `requirements.txt` (add `anthropic`, `black`; remove `openai`)
- Modify `README.md`, `.env.example`, `.streamlit/secrets.toml.example`
- Rename `tests/test_openai_client.py` → `tests/test_ai_client.py`; update `tests/test_vision.py`, `test_journal.py`, `test_grading.py`, `test_ai_flow.py` to patch `ai_client.*`
- Delete `src/tradelens/services/openai_client.py`
- Modify migration `g7h8i9j0k1l2_add_smc_ict_fields.py` (reversible downgrade); `tests/test_migrations.py` (round-trip)
- Rename `7_Settings.py` → `9_Settings.py`
- Fix the 7 ruff errors; run `black`

**`ai_client.py` contract (the load-bearing new module):**
- `@dataclass Usage`: `model, tokens_in, tokens_out, total_tokens, cache_read_tokens, cost_usd, latency_s, thinking_summary, refused: bool`.
- `@dataclass AIUnavailable`: `reason, category` — typed result the UI renders as a friendly message.
- `def chat(user_message, system_message="", *, model=None, effort="medium", response_schema=None, cache_system=False, few_shot=None) -> tuple[str | AIUnavailable, Usage]`
- `def vision(image_path|paths, user_message, system_message="", *, model=None, effort="medium", response_schema=None, cache_system=False, few_shot=None) -> tuple[str | AIUnavailable, Usage]` — base64 image blocks (PNG/JPG/WEBP).
- Routing: default `model_primary` (`claude-fable-5`); callers pass `model=settings.model_grading` for the haiku pre-pass.
- Thinking: `{"type":"adaptive","display":"summarized"}`; capture summary into `Usage.thinking_summary`.
- Refusal: `client.beta.messages.create(..., betas=["server-side-fallback-2026-06-01"], fallbacks=[{"model": settings.model_fallback}])`; if final `stop_reason=="refusal"` → return `AIUnavailable`.
- Caching: when `cache_system`, put `cache_control:{"type":"ephemeral"}` on the system block (Strategy Profile).
- Cost: compute from `usage` (in/out + cache-read at ~0.1×) using per-model rates; populate `Usage.cost_usd`.
- `few_shot`: optional correction block, injected as a system/preamble segment (used by Phase 5).
- DEMO_MODE: if `settings.demo_mode`, return deterministic mock content (schema-valid JSON when `response_schema` given) + zero-cost `Usage`, no network.
- Keys: `anthropic.Anthropic()` resolves `ANTHROPIC_API_KEY` from env (config injects from `st.secrets`). Missing key + not DEMO_MODE → `AIUnavailable`.
- `load_prompt(name)` and `encode_image(...)` carried over from `openai_client.py`.

**config.py changes:** add `anthropic_api_key`, `model_primary="claude-fable-5"`, `model_grading="claude-haiku-4-5"`, `model_fallback="claude-opus-4-8"`, `effort_default="medium"`, `demo_mode: bool=False`; inject `ANTHROPIC_API_KEY` from `st.secrets`; keep `database_url`.

**Tests to add/adjust (hold ≥184):**
- `test_ai_client.py`: DEMO_MODE returns mock (no network); cost math; refusal→`AIUnavailable`; fallback path; `cache_control` present when `cache_system`; model routing (primary vs grading); image base64 build; few_shot injection in outbound payload; missing-key→`AIUnavailable`.
- vision/journal/grading tests: re-point patches to `ai_client.*`; assert grading uses `model_grading`.
- `test_migrations.py`: upgrade→downgrade→upgrade round-trip drops/re-adds SMC columns on SQLite.

---

## Phase 2 (Day 2) — Calendar heatmap + Killzone analytics

Commit: `week5-d2: calendar heatmap + killzone analytics`

**Files:** create `ui/pages/6_Calendar.py`; modify `services/metrics.py`; modify `ui/pages/4_Analytics.py` (render only); tests `tests/test_metrics.py` (extend).
**Migration:** none.
**Functions (metrics.py, pure pandas):** `killzone_performance(df)`, `confirmation_model_performance(df)`, `mistake_frequency(df)`, `calendar_daily_pnl(df, year, month)` → return win rate, avg R, profit factor, net P&L per group + day grid.
**Tests:** known-value fixture DataFrame for each aggregation; empty-DataFrame and single-trade edge cases; calendar month with no trades.

---

## Phase 3 (Day 3) — Pattern detection + Total Edge Leak

Commit: `week5-d3: pattern detection + edge leak`

**Files:** create `services/patterns.py`, `prompts/patterns_v2.txt`; modify `services/metrics.py` (edge leak), `ui/pages/4_Analytics.py`, `services/strategy.py` (append insight); tests `tests/test_patterns.py`, extend `test_metrics.py`, `test_strategy.py`.
**Migration:** none.
**Functions:** `patterns.compute_candidates(df)` (deterministic pre-pass: killzone/bias/setup flags, streaks, mistake clusters, rule-violation cost); `patterns.generate_cards(candidates) -> list` (≤6 strict-JSON cards via `ai_client` + `patterns_v2.txt`, each with evidence stat + sample size; sample <5 labeled "early signal — low sample"); `metrics.total_edge_leak(df)` (Σ P&L where `followed_rules` is false OR `mistake_tags` non-empty).
**Tests:** edge-leak math; pattern JSON schema validation; low-sample labeling; `strategy.append_insight` round-trip; DEMO_MODE card generation.

---

## Phase 4 (Day 4) — Weekly AI Review

Commit: `week5-d4: weekly AI review`

**Files:** Alembic migration `add_weekly_reviews`; modify `db/models.py` (WeeklyReview); create `services/weekly.py`, `prompts/weekly_v2.txt`, `ui/pages/7_Weekly_Review.py`; tests `tests/test_weekly.py`, extend `test_migrations.py`.
**Migration:** `weekly_reviews(id, week_start, content_md, thinking_summary, stats_json, created_at)` — reversible (`batch_alter_table`/`drop_table`).
**Functions:** `weekly.week_window(date, tz)` (Mon–Sun); `weekly.gather(week_start)` (trades+metrics+top patterns+corrections); `weekly.generate(week_start, overwrite=False)` → 5 H3 sections via `ai_client` (`effort="high"`, thinking summarized), persist; re-run overwrites after confirm; zero-trade → no API call, friendly empty state.
**Tests:** week-window selection (user TZ, Mon–Sun); persistence round-trip; zero-trade graceful (asserts no AI call); overwrite behavior.

---

## Phase 5 (Day 5) — Correction memory (few-shot loop)

Commit: `week5-d5: correction few-shot learning loop`

**Files:** modify `services/corrections.py`; wire injection through `ai_client` for vision/journal/grading/weekly/patterns; modify pages for sidebar badge + toast; create `prompts/correction_v2.txt`; tests `tests/test_corrections.py` (extend).
**Migration:** none (corrections table exists).
**Functions:** `corrections.build_correction_few_shot(limit, scope)` → compact token-budgeted block (most-recent + most-repeated first); `corrections.repeat_counts()` for ≥5 threshold; badge count helper.
**Tests:** few-shot ordering, token budget, empty case; injection present in each service's outbound prompt (assert via `ai_client` spy); repeat-threshold (≥5) trigger.

---

## Phase 6 (Day 6) — AI Partner mode (chat over a trade)

Commit: `week5-d6: AI partner mode`

**Files:** create `ui/pages/8_AI_Partner.py`, `services/partner.py`; tests `tests/test_partner.py`.
**Migration:** none.
**Functions:** `partner.assemble_context(trade, ai_analysis, strategy, few_shot)` (Strategy Profile prompt-cached; vision block when screenshot exists); `partner.system_prompt()` with HARD SCOPE GUARD (declines predictions/signals/"what should I do tomorrow", redirects to process review); `partner.post_check(reply)`; `partner.trim_history(history, max_turns)` with running summary; per-conversation token/cost display.
**Tests:** context assembly; scope-guard text always present in outbound system prompt; history trimming; DEMO_MODE mock conversation; post-check blocks forecast asks.

---

## Phase 7 (Day 7) — Hardening, Consistency Score, Cost dashboard

Commit: `week5-d7: hardening + consistency score + cost dashboard`

**Files:** modify `services/metrics.py` (Consistency Score), `ui/app.py` (KPI), `ui/pages/4_Analytics.py` (AI usage section); failure-path hardening across services; tests `tests/test_metrics.py`, `tests/test_hardening.py`.
**Migration:** none.
**Functions:** `metrics.consistency_score(df)` 0–100 blending rule-adherence rate + mistake rate + grade trend (formula documented in docstring); `metrics.monthly_ai_cost(rows)` from `aianalysis.cost_usd`.
**Tests:** consistency-score formula on fixtures; cost summation; failure-path sweep (malformed JSON, refusal `AIUnavailable`, timeout, missing screenshot) each returns typed error, never a stack trace.
**Final:** `ruff check .` clean, `black --check .` clean, suite green (target well above 85; floor 184 + new tests).

---

## Open items flagged (non-blocking)

- Stray junk dirs `a/ don't/ have/ if/ yet/ you/` + duplicate `venv`/`.venv` — clutter; awaiting your OK to remove.
- Seed trade count: README/CLAUDE.md say 60, spec says 50 — I'll preserve whatever the seed actually produces and not change its semantics.
- `claude-fable-5` requires 30-day data retention (not available under ZDR) — relevant only for live (non-DEMO) use.
