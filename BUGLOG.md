# BUGLOG — Week 6 Phase 5 (bug bash + coverage)

Scripted full-flow pass over seed/synthetic data, run 2026-06-20. Every item in
the §a–§i sequence was exercised and its result recorded below.

## Scripted flow pass (§a–§i)

| Item | Flow | Result |
|---|---|---|
| §a | Every page boot (empty DB + seed DB) | PASS — covered by `tests/test_pages_boot.py` (12 subprocess boots); no exceptions. |
| §b | CSV import → export round-trip (`csvio.py`) | PASS — `tests/test_csvio.py` round-trip + error paths; no bugs found. |
| §c | Screenshot upload: PNG / JPG / WEBP / oversized (>10MB) / corrupt (`screenshot_service.py`) | PASS — `tests/test_screenshot_service.py`; oversized & corrupt persist with null dims, no crash. |
| §d | All Plotly charts render | PASS — `tests/test_charts.py`; every chart returns a Figure on populated and empty input. |
| §e | Calendar: month with trades, empty month, Dec→Jan boundary | PASS — `tests/test_metrics.py` calendar cases incl. boundary; no month leakage. |
| §f | Weekly review: week with trades, empty week (no API call) | PASS — `tests/test_weekly.py`; zero-trade week makes no AI call. |
| §g | Strategy profile: save → reload → values match | PASS — `tests/test_strategy.py` round-trip. |
| §h | Corrections loop: add correction → appears in next AI call few-shot | PASS — `tests/test_correction_injection.py`; injected centrally into `_complete()`. |
| §i | Killzone DST edges: March forward, November back | PASS — `tests/test_sessions_dst.py`; same UTC instant maps to different killzone across DST (ET-aware). |

## Bugs found and fixed

| ID | File | Root Cause | Fix | Test Added |
|---|---|---|---|---|
| — | — | — | — | — |

**No new bugs found in scripted flow pass.** Every flow item behaved correctly;
Phase 5 added characterization/coverage tests around previously-untested modules
(`csvio`, `screenshot_service`, `trade_service`) without changing `src/` behavior.

## Coverage outcome

Per-module service coverage raised to ≥80% on every module (see the d5 commit
report). Aggregate: 87% → 92%. Suite: 435 → 474 passing.
