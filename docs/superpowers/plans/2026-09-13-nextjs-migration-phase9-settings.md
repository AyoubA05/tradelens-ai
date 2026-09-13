# Phase 9 — Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate Settings — account identity, timezone, AI availability, CSV export/import, sample trades, monthly AI cost, delete all trades and delete account — onto the FastAPI + Next.js boundary, and make both destructive actions actually erase what they promise, including stored screenshot objects and every session row.

**Architecture:** Group A fixes the shared deletion services first, because the Streamlit page and the new API both call them: objects in R2 are removed before the rows that name them, an incomplete cleanup deletes nothing and says so, and account deletion removes the non-cascading session and handoff rows before the user row. Group B adds one owner-singleton `/v1/settings` router — a single read that returns everything the page renders, and one narrow write per action with a strict allowlist and a typed confirmation for anything destructive. Groups C and D add same-origin relays and a page built from one Server Component read plus small client islands, following the Strategy and Partner patterns.

**Tech Stack:** FastAPI · Pydantic v2 · SQLAlchemy 2.x · R2 via `api/storage.py` · Next.js 16 App Router · TypeScript · pytest · Vitest

**Spec:** `docs/superpowers/specs/2026-08-16-nextjs-saas-migration-design.md` — §7 phase 9 ("Recovery email · timezone · CSV import/export · sample data · delete all trades · delete account · cost by feature"); §8 Settings ("recovery email · timezone · API-key guidance · CSV export · CSV import · load sample trades · clear sample trades · delete all trades · delete account · monthly cost by feature · demo banner"); §6 retention ("The future API/account deletion paths must invoke [owner/trade-key-validated R2 deletion] before the R2 feature ships; the legacy local-disk deletion helpers do not delete R2 objects"); §4 Class C (per-user cost attribution "which the Settings cost view depends on").

## Global Constraints

- Owner identity only from the authenticated session row. No request field names an owner, a user, a trade id for bulk actions, a file path or an object key.
- Service-layer tenant isolation mandatory (`services/ownership.require_user_id`).
- Next.js is the BFF; raw browser session credentials never reach FastAPI; `TL_SERVICE_SECRET` never reaches the browser. Relays are same-origin, `no-store`, dynamic, fail shut when `SITE_ORIGIN` is unset (before the session lookup), gate on `appLayoutRedirect`, and forward only fixed error shapes.
- **One account, one surface** (Phase 7, `9916c26`): Next.js Settings serves only `app_surface='nextjs'` accounts. Do not weaken it.
- Write/request schemas are strict positive allowlists (`extra="forbid"`, `strict=True`). The app-wide 422 handler emits only `type`/`loc`/`msg`; the unhandled-exception handler answers a fixed `internal_error` with `no-store` (Phase 8). Keep both.
- **Objects before rows** (Phase 3 `delete_trade_endpoint`): no row that names a stored object is deleted unless that object was deleted; an incomplete cleanup deletes nothing and reports `remaining` (retryable) separately from `unresolvable` (a retry cannot help).
- Destructive writes require the exact typed confirmation in the request body (`"DELETE"`, `"DELETE MY ACCOUNT"`), compared server-side, byte for byte after no normalisation.
- Driver and exception text never reach a response. Failures are fixed codes.
- AI copy: this page describes AI availability and cost only. No copy may suggest trades, signals, predictions or advice.
- Python 3.9.6 floor (`Optional[X]`, no `X | Y`). **No new Python or npm dependencies. No schema migration**; alembic head stays `g3h4i5j6k7l8`.
- `services/metrics.py` and `prompts/` untouched. The Streamlit Settings page keeps working against the same services until Phase 10 and inherits every deletion fix.
- Gates: `pytest tests/ -q`; `ruff check src/ scripts/`; `black --check src/ scripts/ tests/`; in `web/` (run from `web/`): `npx vitest run`, `npx tsc --noEmit`, `npx eslint .`, `npm run build` (localhost origins); `scripts/generate_openapi.py` **run from the repo root** + `npm --prefix web run api:types` must leave no diff.

---

## Execution process

| Group | Review depth |
|---|---|
| A — deletion correctness in the shared services | **Deepest in the phase.** Every row that names a user or a stored object; partial failure; the Streamlit caller. |
| B — the Settings API | **Deep.** Isolation, allowlists, typed confirmations, CSV size and row bounds, no echo. |
| C — relays and the server bridge | Deep for the destructive relays (confirmation forwarding, cookie clearing, sign-out ordering); light otherwise. |
| D — the Settings page | Light, except the Danger Zone and the account-deleted flow (deep). |
| E — verification, mutation battery, handoff | Final boundary. |

**Mutation discipline** (Phase 8 lessons, all binding): pristine copies keyed by full path; sha256 before/after and restore asserted every mutant; `PYTHONDONTWRITEBYTECODE=1`; NOT-APPLIED / NOT-RUN / ERROR never counted as caught; the harness parses parametrized test ids containing spaces (`^FAILED (.+?)(?: - |$)`); the final battery runs from a **clean HEAD** with a preflight and postflight `git status` check; gates run in private `git archive` extractions while a battery is editing the worktree (use a copied — not symlinked — `node_modules` for `next build`); reviewers work only in private extractions.

---

## Scope

**In:** Profile (account identity and verification state), Preferences (trading timezone, AI availability state), Data (CSV export, CSV import, load/clear sample trades, this month's AI cost by feature), Danger Zone (delete all trades, delete account), the demo-mode state line, the account-deleted landing, and the deletion-correctness fixes in the shared services.

**Explicitly not in:** changing the sign-in email (see decision S1 — needs its own verified-change flow), password change on this page (the existing forgot/reset flow already covers it), Streamlit retirement (Phase 10), a historical cost browser beyond the current month, background CSV import jobs, and a Strategy demo-playbook preview (see S3).

**Carried forward, NOT this phase's to close (hard pre-release gates, unchanged):** real PostgreSQL concurrency; authenticated desktop + true 375px browser smoke; Docker build/startup/health; live Anthropic adversarial smoke; dependency audit; live R2/browser verification (now including bulk and account-deletion object cleanup). The narrow in-flight Streamlit request race until Phase 10. The two deterministic `test_pages_boot.py` Streamlit analytics failures. The lexical Partner output guard remains defense-in-depth, not a semantic guarantee.

---

## What already exists — read before writing anything

Verified on `main` at `2de1d6c`:

- `src/tradelens/ui/pages/9_Settings.py` (450 lines) — the parity reference. Sections `Profile`, `Preferences`, `Data`, `Danger Zone`; one generic failure sentence (`"That did not work. Try again."`); confirmation beside the control; typed confirmations `DELETE` and `DELETE MY ACCOUNT` (the latter compared after `.strip()`); success copy `"Deleted {n} trades."`, `"Imported {n} trades, skipped {m} duplicates."`, `"That CSV was valid but had no rows."`, `"Loaded {n} sample trades."`, `"Removed {n} sample trades."`; timezone options `America/New_York, America/Chicago, Europe/London, Asia/Tokyo, Asia/Dubai, UTC`; AI state copy for key / demo / off; "Export first to see the column format an import expects."; account-deletion copy listing what is erased and that anonymous cost records are kept.
- `web/app/app/settings/page.tsx` — Phase 1 placeholder (`EmptyState` "Settings are not migrated yet").
- `services/account.py:delete_account(user_id) -> bool` — one transaction deleting `Screenshot`, `AIAnalysis`, `Correction` (by trade), `Trade`, then `Strategy`, `UserSetting`, `WeeklyReview`, `PerformanceMetrics`, `Correction` (by user); anonymises `AIUsageLog.user_id`; deletes the `User`; then removes **local-disk** files under `SCREENSHOTS_DIR` only.
  - **Defect 1 — R2 objects are never deleted.** Final screenshot keys (`u/{user}/t/{trade}/{uuid}.png`) are left in the bucket with no row naming them (spec §6 requires the R2 adapter here).
  - **Defect 2 — session and handoff rows are not deleted.** `auth_sessions.user_id` and `auth_handoffs.user_id` are `ForeignKey("users.id")`, `nullable=False`, **no `ondelete`** (`db/models.py` `AuthSession`, `AuthHandoff`). `revoke_all_for_user` only sets `revoked_at`. Deleting the user row therefore violates those constraints on PostgreSQL (SQLite in tests does not enforce foreign keys, which is why `tests/test_account_deletion.py` passes).
  - Tables with `ondelete="CASCADE"` on `users.id`: `user_settings`, `email_verifications`, `password_resets`, `ai_jobs`, `trade_summary_results`, `trade_drafts`. They cascade on PostgreSQL but not on SQLite-without-PRAGMA; delete them explicitly so behaviour is identical on both.
- `services/trade_service.py:delete_all_trades(user_id) -> int` — deletes `Correction`, `AIAnalysis`, `Screenshot`, `Trade` rows. **Defect 3 — no screenshot object cleanup at all** (neither R2 nor disk).
- `services/sample_data.py` — `count_sample_trades(user_id)`, `clear_sample_trades(user_id)` (bulk-deletes `Trade` rows with `is_sample == 1`), `load_sample_trades(user_id)` (clears then inserts `SAMPLE_COUNT = 20`). Sample trades are built in code and never carry screenshots.
- `services/csvio.py` — `CSV_COLUMNS`; `export_trades_csv(df) -> bytes`; `import_trades_csv(file, user_id) -> (inserted, skipped, errors)` reading `file.read()`, required columns `trade_date, asset, direction, result, pnl`, per-row errors as fixed sentences (`_ROW_FAILED`), never raises on a bad row.
- `services/cost.py:monthly_cost_by_feature(year, month, user_id) -> DataFrame[feature, cost_usd, calls]`.
- `services/app_settings.py` — `get_timezone(user_id)`, `set_timezone(user_id, tz)` (**no validation**: any string is stored), `DEFAULT_TIMEZONE`, `today_for_owner`.
- `services/users.py` — `get_user_by_id`, `set_email` (clears `email_verified_at` and re-arms `email_verification_required` on any change).
- `services/demo.py:is_demo()`; `services/ai_client.py:has_api_key()`; `services/password_reset.py:email_configured()`.
- `api/storage.py:delete_trade_objects(user_id, trade_id) -> ObjectCleanup(deleted, failed, skipped)` with `.complete`; owner-scoped through `trades.user_id`; idempotent; never raises for an object-store fault; a non-R2 key (legacy local path) is **skipped**, which blocks a single-trade delete as `unresolvable`.
- `api/routers/trades.py:delete_trade_endpoint` — the objects-before-rows pattern and the `503 {"error": "screenshot_cleanup_failed", "remaining", "unresolvable"}` body (`ScreenshotCleanupFailedResponse`).
- `api/deps.py` — `current_user`, `MAX_BODY_BYTES = 1_048_576`.
- Web: `lib/api/client.ts:callApi` (JSON), `lib/auth/session.ts:appLayoutRedirect` (unverified email → `/verify-email`), `lib/auth/login.ts:SESSION_COOKIE`, `app/api/auth/logout/route.ts` (revoke then clear cookie), `lib/app/strategy-relay.ts` + `strategy-relay-failure.ts` and `lib/app/partner-relay.ts` (the relay patterns to copy), `app/api/trades/[id]/route.ts` (the 503 retryable/unresolvable split in a relay).
- Tests to keep green and extend: `tests/test_account_deletion.py`, `tests/test_app_settings.py`, `tests/test_csvio.py`, `tests/test_csv_import_derivations.py`, `tests/test_sample_data.py`, `tests/test_cost.py`, `tests/test_settings_source.py`, `tests/test_account_ui.py`.

---

## Decisions that need owner approval

Each has a recommended default. The tasks below implement the default; a different choice changes only the task named.

**S1 — The email on the web Settings page is shown, not edited (recommended).** On the website the email is the sign-in identity (`lib/auth/login.ts` resolves `@` input by email only) and verification gates the app (`appLayoutRedirect`). Streamlit's `set_email` clears verification on any change, so porting the "Save recovery email" control would change how the trader signs in and immediately send them to `/verify-email`. Phase 9 shows the email and whether it is verified; changing it needs a verify-the-new-address-before-switching flow, planned separately. *Alternative:* add that flow now (a new token table would breach "no schema migration"). Affects Task D1 only.

**S2 — "API-key guidance" becomes an availability state, not instructions (recommended).** On the SaaS the key is an operator secret. The page shows one of three fixed states — `enabled`, `demo`, `unavailable` — and no secret-configuration steps. Affects Tasks B1 and D1.

**S3 — Demo mode is a state line on Settings; the Strategy demo-playbook preview stays out (recommended).** Phase 7 deferred that preview "to Phase 9", but it is not in the spec's Phase 9 list and needs a demo read path in the Strategy API. Settings reports `demo_mode` and the app-shell demo banner is **not** added here. *Alternative:* add an app-wide banner driven by a new `/v1/session` field (touches the shell on every page). Affects Tasks B1 and D1.

**S4 — CSV import is synchronous, JSON-wrapped, ≤ 1 MiB request, ≤ 5,000 data rows (recommended).** The existing body cap stays; the relay refuses larger files before the API sees them; more than 5,000 rows is refused whole with a fixed code rather than partially imported. Affects Tasks B2, C2, D2.

**S5 — Export neutralises spreadsheet formulas (recommended).** A cell beginning with `=`, `+`, `-`, `@`, tab or carriage return is prefixed with `'` in the exported file, so a trader's own note cannot execute when the CSV is opened in a spreadsheet. Numeric columns (`pnl`, `rr_*`, prices) are exempt because a negative number is data. Import strips one leading `'` from the same text columns so a round trip is lossless. Affects Task B2.

**S6 — Timezone is an allowlist of the six Streamlit options (recommended).** No new dependency and no reliance on the container's tz database. A legacy stored value outside the list is displayed and kept until the trader picks another. Affects Tasks A3 and B1.

**S7 — Delete all trades also removes trade summaries (recommended).** `trade_summary_results` are derived from the trader's trades and can quote their notes; keeping them after "every trade you have logged" is deleted would contradict the copy. Unsaved New Trade drafts (`trade_drafts`) are kept — they are not trades. Affects Task A1.

**S8 — Legacy local-path screenshots do not block deletion when the file is inside the screenshot store (recommended).** A `file_path` that is not an R2 key is skipped by `delete_trade_objects`, which would block a bulk or account delete forever for any trader migrated from Streamlit. For bulk and account deletion only, a skipped key that resolves inside `SCREENSHOTS_DIR` is removed from disk (or already absent) and counts as resolved; a key pointing at another tenant's R2 prefix, or anywhere else, stays `unresolvable` and blocks deletion. The single-trade delete keeps its Phase 3 behaviour. Affects Task A1.

**S9 — Account deletion confirms with the typed phrase only (recommended, Streamlit parity).** *Alternative:* also require the current password, verified in the Next.js relay before the API call — stronger against a stolen session, but it needs a password-verification helper exported from `lib/auth/login.ts` and a failure path of its own. Affects Tasks C2 and D3.

---

## File structure

**Python**
- Create `src/tradelens/services/data_deletion.py` — `purge_trade_screenshots`, `delete_all_trades_and_objects`, `delete_account_and_objects`, `DeletionOutcome`. One responsibility: erase rows only after the objects they name are gone.
- Modify `src/tradelens/services/account.py` — delete session/handoff and cascade-table rows explicitly inside the transaction.
- Modify `src/tradelens/services/trade_service.py` — `delete_all_trades` also deletes `trade_summary_results` (S7).
- Modify `src/tradelens/services/app_settings.py` — `TIMEZONE_OPTIONS`, validation in `set_timezone` (S6).
- Modify `src/tradelens/services/csvio.py` — `neutralise_formula`, `restore_formula`, `MAX_IMPORT_ROWS`, `import_trades_csv_text` (S4, S5).
- Modify `src/tradelens/ui/pages/9_Settings.py` — call the new deletion services and render their refusal (Streamlit keeps working).
- Create `src/tradelens/api/schemas/settings.py`, `src/tradelens/api/routers/settings.py`; modify `src/tradelens/api/app.py` to register it.
- Tests: `tests/test_data_deletion.py`, extend `tests/test_account_deletion.py`, `tests/test_app_settings.py`, `tests/test_csvio.py`; create `tests/test_api_settings.py`.

**Web**
- Create `web/lib/app/settings.ts` (server-only bridge + types), `web/lib/app/settings-relay.ts` (authorize + failure mapping).
- Create routes `web/app/api/settings/timezone/route.ts`, `web/app/api/settings/sample-trades/route.ts`, `web/app/api/settings/export/route.ts`, `web/app/api/settings/import/route.ts`, `web/app/api/settings/delete-trades/route.ts`, `web/app/api/settings/delete-account/route.ts`.
- Replace `web/app/app/settings/page.tsx`; create `web/app/app/settings/loading.tsx`, `web/app/app/settings/error.tsx`.
- Create `web/components/app/settings/profile-section.tsx`, `preferences-section.tsx`, `data-section.tsx`, `danger-zone.tsx`, `setting-status.tsx`.
- Create `web/app/account-deleted/page.tsx`.
- Tests: `web/__tests__/settings-relay.test.ts`, `settings-page.test.tsx`, `settings-data-section.test.tsx`, `settings-danger-zone.test.tsx`.

---

## Group A — deletion correctness in the shared services

### Task A1: Objects before rows for bulk and account deletion

**Files:**
- Create: `src/tradelens/services/data_deletion.py`
- Modify: `src/tradelens/services/trade_service.py` (`delete_all_trades`)
- Test: `tests/test_data_deletion.py`

**Interfaces:**
- Consumes: `api.storage.delete_trade_objects(user_id, trade_id) -> ObjectCleanup`; `services.account.SCREENSHOTS_DIR`, `services.account._resolve_owned_files`; `services.trade_service.delete_all_trades(user_id) -> int`; `services.account.delete_account(user_id) -> bool`; `services.ownership.require_user_id`.
- Produces:
  - `DeletionOutcome(deleted: int, remaining: int, unresolvable: int, blocked: bool)` (frozen dataclass).
  - `purge_trade_screenshots(user_id: int) -> tuple[int, int]` — `(remaining, unresolvable)` across all of the owner's trades.
  - `delete_all_trades_and_objects(user_id: int) -> DeletionOutcome`.
  - `delete_account_and_objects(user_id: int) -> DeletionOutcome` (`deleted` is 1 or 0).

- [ ] **Step 1: Write the failing tests**

```python
"""Bulk and account deletion erase objects before the rows that name them."""

from __future__ import annotations

import datetime as dt

from src.tradelens.api.storage import ObjectCleanup
from src.tradelens.db.models import Screenshot, Trade, TradeSummaryResult
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import data_deletion


def _trade(owner, file_path=None):
    db = SessionLocal()
    try:
        row = Trade(user_id=owner, asset="NQ", direction="Long", result="Win")
        db.add(row)
        db.commit()
        if file_path is not None:
            db.add(Screenshot(trade_id=row.id, file_path=file_path))
            db.commit()
        return row.id
    finally:
        db.close()


def _count(model, **where):
    db = SessionLocal()
    try:
        q = db.query(model)
        for key, value in where.items():
            q = q.filter(getattr(model, key) == value)
        return q.count()
    finally:
        db.close()


def test_every_trades_objects_are_deleted_before_any_row(two_users, monkeypatch):
    owner = two_users[1]
    first = _trade(owner, "u/%d/t/1/a.png" % owner)
    second = _trade(owner, "u/%d/t/2/b.png" % owner)
    seen = []

    def cleanup(user_id, trade_id):
        # Rows must still exist while objects are being removed.
        seen.append((user_id, trade_id, _count(Trade, id=trade_id)))
        return ObjectCleanup(deleted=["k"], failed=[], skipped=[])

    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", cleanup)
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(2, 0, 0, False)
    assert sorted(seen) == sorted([(owner, first, 1), (owner, second, 1)])
    assert _count(Trade, user_id=owner) == 0


def test_one_failed_object_deletes_nothing_and_reports_it_as_retryable(
    two_users, monkeypatch
):
    owner = two_users[1]
    _trade(owner, "u/%d/t/1/a.png" % owner)
    _trade(owner, "u/%d/t/2/b.png" % owner)
    results = iter(
        [
            ObjectCleanup(deleted=["k"], failed=[], skipped=[]),
            ObjectCleanup(deleted=[], failed=["k2"], skipped=[]),
        ]
    )
    monkeypatch.setattr(
        data_deletion.storage, "delete_trade_objects", lambda u, t: next(results)
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 1, 0, True)
    assert _count(Trade, user_id=owner) == 2


def test_a_key_outside_this_owners_prefix_blocks_as_unresolvable(
    two_users, monkeypatch
):
    first, owner = two_users
    _trade(owner, "u/%d/t/9/stolen.png" % first)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=["u/x"]),
    )
    monkeypatch.setattr(data_deletion, "_legacy_local_path_resolved", lambda key: False)
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 0, 1, True)
    assert _count(Trade, user_id=owner) == 1


def test_a_legacy_local_path_inside_the_store_does_not_block_bulk_deletion(
    two_users, monkeypatch, tmp_path
):
    owner = two_users[1]
    shots = tmp_path / "screenshots"
    shots.mkdir()
    legacy = shots / "old.png"
    legacy.write_bytes(b"png")
    _trade(owner, str(legacy))
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", shots)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=[str(legacy)]),
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome.blocked is False and outcome.deleted == 1
    assert not legacy.exists()


def test_bulk_deletion_never_touches_another_owners_trades(two_users, monkeypatch):
    first, owner = two_users
    theirs = _trade(first)
    _trade(owner)
    calls = []
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: calls.append((u, t)) or ObjectCleanup([], [], []),
    )
    data_deletion.delete_all_trades_and_objects(owner)
    assert all(u == owner for u, _t in calls)
    assert _count(Trade, id=theirs) == 1


def test_delete_all_trades_also_removes_trade_summaries(two_users, monkeypatch):
    owner = two_users[1]
    _trade(owner)
    db = SessionLocal()
    try:
        db.add(
            TradeSummaryResult(
                user_id=owner,
                summary_key="k" * 64,
                filters_json="{}",
                content_md="A summary that quotes a trade note.",
                reviewed_trades=1,
                created_at=dt.datetime.now(dt.timezone.utc),
            )
        )
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup([], [], []),
    )
    data_deletion.delete_all_trades_and_objects(owner)
    assert _count(TradeSummaryResult, user_id=owner) == 0


def test_account_deletion_is_blocked_by_an_incomplete_object_cleanup(
    two_users, monkeypatch
):
    owner = two_users[1]
    _trade(owner, "u/%d/t/1/a.png" % owner)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=["k"], skipped=[]),
    )
    deleted = []
    monkeypatch.setattr(
        data_deletion, "delete_account", lambda u: deleted.append(u) or True
    )
    outcome = data_deletion.delete_account_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 1, 0, True)
    assert deleted == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_data_deletion.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: src.tradelens.services.data_deletion`.

- [ ] **Step 3: Implement `services/data_deletion.py`**

```python
"""Bulk and account deletion: stored objects first, rows only after.

`delete_all_trades` and `delete_account` erase rows. A `screenshots` row is the
only record of an R2 object's key, so removing the row before the object leaves
a private image in the bucket that nothing points at. These wrappers are what
the API and the Streamlit Settings page call: every screenshot object of every
trade the owner has is removed first, and if anything is left behind, no row
is deleted and the caller is told how much, and whether a retry can help.

Streamlit-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from src.tradelens.api import storage
from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import account as _account
from src.tradelens.services.account import _resolve_owned_files, delete_account
from src.tradelens.services.ownership import require_user_id
from src.tradelens.services.trade_service import delete_all_trades


@dataclass(frozen=True)
class DeletionOutcome:
    deleted: int
    remaining: int
    unresolvable: int
    blocked: bool


def _owned_trade_ids(owner: int) -> list:
    db = SessionLocal()
    try:
        return [
            row_id
            for (row_id,) in db.query(Trade.id).filter(Trade.user_id == owner).all()
        ]
    finally:
        db.close()


def _legacy_local_path_resolved(key: str) -> bool:
    """A pre-R2 local path inside the screenshot store is removed or already gone.

    Anything that does not resolve inside `SCREENSHOTS_DIR` — another tenant's
    R2 key, an absolute path elsewhere, a `..` escape — is not ours to delete
    and stays unresolvable (decision S8).
    """
    # Read through the module at call time, so a patched directory applies.
    resolved = _resolve_owned_files([key], root=Path(_account.SCREENSHOTS_DIR))
    if not resolved:
        return False
    for path in resolved:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            return False
    return True


def purge_trade_screenshots(user_id: int) -> Tuple[int, int]:
    """Remove every stored screenshot object of every trade this owner has.

    Returns `(remaining, unresolvable)`. Never raises for an object-store
    fault; `delete_trade_objects` reports it instead.
    """
    owner = require_user_id(user_id)
    remaining = 0
    unresolvable = 0
    for trade_id in _owned_trade_ids(owner):
        cleanup = storage.delete_trade_objects(owner, trade_id)
        remaining += len(cleanup.failed)
        unresolvable += sum(
            1 for key in cleanup.skipped if not _legacy_local_path_resolved(key)
        )
    return remaining, unresolvable


def delete_all_trades_and_objects(user_id: int) -> DeletionOutcome:
    owner = require_user_id(user_id)
    remaining, unresolvable = purge_trade_screenshots(owner)
    if remaining or unresolvable:
        return DeletionOutcome(0, remaining, unresolvable, True)
    return DeletionOutcome(delete_all_trades(owner), 0, 0, False)


def delete_account_and_objects(user_id: int) -> DeletionOutcome:
    owner = require_user_id(user_id)
    remaining, unresolvable = purge_trade_screenshots(owner)
    if remaining or unresolvable:
        return DeletionOutcome(0, remaining, unresolvable, True)
    return DeletionOutcome(1 if delete_account(owner) else 0, 0, 0, False)
```

Modify `services/account.py:_resolve_owned_files` to accept an optional root so the helper above can reuse it without duplicating the path-escape guard:

```python
def _resolve_owned_files(paths: Iterable[str], root: Optional[Path] = None) -> list[Path]:
    """Absolute paths that are genuinely inside the screenshots directory.

    Anything else — an absolute path elsewhere, or one escaping via `..` —
    is dropped rather than deleted.
    """
    try:
        base = (root or SCREENSHOTS_DIR).resolve()
    except OSError:  # pragma: no cover — unreadable root
        return []

    safe: list[Path] = []
    for raw in paths:
        if not raw:
            continue
        try:
            candidate = Path(raw).resolve()
            candidate.relative_to(base)
        except (ValueError, OSError):
            _log.warning("Refusing to delete a path outside the screenshot store")
            continue
        safe.append(candidate)
    return safe
```

(Add `from typing import Iterable, Optional` in the same edit.) `data_deletion` reads `SCREENSHOTS_DIR` as `_account.SCREENSHOTS_DIR` at call time rather than importing the name, so patching `account.SCREENSHOTS_DIR` in a test reaches it; the E2 sweep forbids `globals()` in services, so that is the only way.

In `services/trade_service.py:delete_all_trades`, delete summaries in the same transaction, before the trades (S7):

```python
        db.query(TradeSummaryResult).filter(
            TradeSummaryResult.user_id == user_id
        ).delete(synchronize_session=False)
```

(Add `TradeSummaryResult` to that module's `db.models` import in the same edit.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_data_deletion.py tests/test_account_deletion.py tests/test_trade_service.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradelens/services/data_deletion.py src/tradelens/services/account.py src/tradelens/services/trade_service.py tests/test_data_deletion.py
git commit -m "fix(data): delete screenshot objects before bulk and account deletion"
```

### Task A2: Account deletion removes every row that references the user

**Files:**
- Modify: `src/tradelens/services/account.py` (`delete_account`)
- Test: `tests/test_account_deletion.py`

**Interfaces:**
- Consumes: `db.models.AuthSession`, `AuthHandoff`, `EmailVerification`, `PasswordReset`, `AIJob`, `TradeSummaryResult`, `TradeDraft`.
- Produces: `delete_account(user_id) -> bool` unchanged in signature; after it returns `True`, no row in any table references `user_id` except anonymised `ai_usage_log` rows (`user_id IS NULL`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_account_deletion.py`)

```python
import datetime as _dt
import hashlib as _hashlib

from sqlalchemy import text as _text

from src.tradelens.db.session import SessionLocal as _SessionLocal
from src.tradelens.services import account as _account


def _open_session_row(user_id):
    now = _dt.datetime.now(_dt.timezone.utc)
    db = _SessionLocal()
    try:
        db.execute(
            _text(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, "
                "expires_at, last_seen_at, surface) VALUES (:h,:u,:c,:e,:l,:s)"
            ),
            {
                "h": _hashlib.sha256(str(user_id).encode()).hexdigest(),
                "u": user_id,
                "c": now,
                "e": now + _dt.timedelta(hours=1),
                "l": now,
                "s": "website",
            },
        )
        db.commit()
    finally:
        db.close()


def _rows_referencing(user_id, table):
    db = _SessionLocal()
    try:
        return db.execute(
            _text("SELECT COUNT(*) FROM {} WHERE user_id = :u".format(table)),
            {"u": user_id},
        ).scalar()
    finally:
        db.close()


def test_session_and_handoff_rows_are_deleted_not_just_revoked(two_users):
    owner = two_users[1]
    _open_session_row(owner)
    assert _account.delete_account(owner) is True
    # Non-cascading NOT NULL foreign keys: on PostgreSQL a remaining row makes
    # the user delete fail outright. SQLite does not enforce them, so the
    # property is asserted directly.
    assert _rows_referencing(owner, "auth_sessions") == 0
    assert _rows_referencing(owner, "auth_handoffs") == 0


def test_every_user_referencing_table_is_emptied_for_the_account(two_users):
    owner = two_users[1]
    _open_session_row(owner)
    assert _account.delete_account(owner) is True
    for table in (
        "auth_sessions",
        "auth_handoffs",
        "user_settings",
        "email_verifications",
        "password_resets",
        "ai_jobs",
        "trade_summary_results",
        "trade_drafts",
        "strategies",
        "trades",
        "corrections",
        "weekly_reviews",
    ):
        assert _rows_referencing(owner, table) == 0, table
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_account_deletion.py -q -p no:cacheprovider -k "session_and_handoff or every_user_referencing"`
Expected: FAIL — `auth_sessions` still has 1 row.

- [ ] **Step 3: Implement** — in `delete_account`, extend `_OWNED_BY_USER` and delete by owner before the `User` row:

```python
from src.tradelens.db.models import (
    AIAnalysis,
    AIJob,
    AIUsageLog,
    AuthHandoff,
    AuthSession,
    Correction,
    EmailVerification,
    PasswordReset,
    PerformanceMetrics,
    Screenshot,
    Strategy,
    Trade,
    TradeDraft,
    TradeSummaryResult,
    User,
    UserSetting,
    WeeklyReview,
)

# Deleted wholesale by owner. Kept as a list so the sweep is explicit and a
# reviewer can see every table that holds personal data in one place.
#
# The auth and job tables are listed even where PostgreSQL would cascade:
# `auth_sessions` and `auth_handoffs` do NOT cascade (NOT NULL, no ondelete),
# so a remaining row makes the user delete fail on PostgreSQL; the cascading
# ones are deleted explicitly so SQLite and PostgreSQL behave identically.
_OWNED_BY_USER = (
    Strategy,
    UserSetting,
    WeeklyReview,
    PerformanceMetrics,
    Correction,
    AuthSession,
    AuthHandoff,
    EmailVerification,
    PasswordReset,
    AIJob,
    TradeSummaryResult,
    TradeDraft,
)
```

- [ ] **Step 4: Run to verify pass**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_account_deletion.py tests/test_data_deletion.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradelens/services/account.py tests/test_account_deletion.py
git commit -m "fix(account): delete session, handoff and job rows with the account"
```

### Task A3: Timezone allowlist and CSV hardening in the services

**Files:**
- Modify: `src/tradelens/services/app_settings.py`, `src/tradelens/services/csvio.py`
- Test: `tests/test_app_settings.py`, `tests/test_csvio.py`

**Interfaces:**
- Produces:
  - `app_settings.TIMEZONE_OPTIONS: tuple[str, ...]` = the six Streamlit options, in that order.
  - `app_settings.set_timezone(user_id, tz)` raises `ValueError("unsupported_timezone")` for a value not in `TIMEZONE_OPTIONS` (blank still means `DEFAULT_TIMEZONE`).
  - `csvio.MAX_IMPORT_ROWS = 5000`; `csvio.FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")`; `csvio.TEXT_COLUMNS: frozenset[str]`.
  - `csvio.neutralise_formula(value: str) -> str`, `csvio.restore_formula(value: str) -> str`.
  - `csvio.TooManyRows(Exception)`.
  - `csvio.import_trades_csv_text(csv_text: str, user_id: int) -> tuple[int, int, list[str]]` — raises `TooManyRows` before inserting anything when the file has more than `MAX_IMPORT_ROWS` data rows.

- [ ] **Step 1: Write the failing tests**

`tests/test_app_settings.py` (append):

```python
import pytest

from src.tradelens.services import app_settings


def test_timezone_options_are_the_streamlit_six_in_order():
    assert app_settings.TIMEZONE_OPTIONS == (
        "America/New_York",
        "America/Chicago",
        "Europe/London",
        "Asia/Tokyo",
        "Asia/Dubai",
        "UTC",
    )


@pytest.mark.parametrize("bad", ["Mars/Olympus", "america/new_york", " UTC", "EST"])
def test_an_unlisted_timezone_is_refused_and_nothing_is_stored(two_users, bad):
    owner = two_users[1]
    app_settings.set_timezone(owner, "Europe/London")
    with pytest.raises(ValueError, match="unsupported_timezone"):
        app_settings.set_timezone(owner, bad)
    assert app_settings.get_timezone(owner) == "Europe/London"
```

`tests/test_csvio.py` (append):

```python
import pytest

from src.tradelens.services import csvio


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_a_formula_leading_text_cell_is_neutralised_and_restored(prefix):
    raw = prefix + "HYPERLINK(\"http://x\")"
    assert csvio.neutralise_formula(raw) == "'" + raw
    assert csvio.restore_formula(csvio.neutralise_formula(raw)) == raw


def test_ordinary_text_is_untouched_both_ways():
    assert csvio.neutralise_formula("took the sweep") == "took the sweep"
    assert csvio.restore_formula("took the sweep") == "took the sweep"


def test_an_import_over_the_row_cap_inserts_nothing(two_users, monkeypatch):
    owner = two_users[1]
    header = "trade_date,asset,direction,result,pnl\n"
    body = "".join(
        "2026-09-01,NQ,Long,Win,{}\n".format(i) for i in range(csvio.MAX_IMPORT_ROWS + 1)
    )
    inserted = []
    monkeypatch.setattr(csvio, "create_trade", lambda data, user_id: inserted.append(1))
    with pytest.raises(csvio.TooManyRows):
        csvio.import_trades_csv_text(header + body, owner)
    assert inserted == []


def test_export_neutralises_notes_but_not_negative_pnl():
    import pandas as pd

    df = pd.DataFrame([{"notes": "=cmd|' /C calc'!A0", "pnl": -120.5}])
    text = csvio.export_trades_csv(df).decode("utf-8")
    assert "'=cmd" in text
    assert ",-120.5" in text
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_app_settings.py tests/test_csvio.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: ... has no attribute 'TIMEZONE_OPTIONS'` / `'neutralise_formula'`.

- [ ] **Step 3: Implement**

`services/app_settings.py`:

```python
# The options the Streamlit page offered, kept as an allowlist (decision S6):
# no new dependency, and nothing relies on the host's tz database.
TIMEZONE_OPTIONS = (
    "America/New_York",
    "America/Chicago",
    "Europe/London",
    "Asia/Tokyo",
    "Asia/Dubai",
    "UTC",
)


def set_timezone(user_id: int, tz: str) -> None:
    """Persist one user's timezone; a blank value becomes the default.

    Anything outside `TIMEZONE_OPTIONS` is refused before it is stored: every
    date the app derives for this owner is read through it.
    """
    value = tz or DEFAULT_TIMEZONE
    if value not in TIMEZONE_OPTIONS:
        raise ValueError("unsupported_timezone")
    set_setting(user_id, _TIMEZONE_KEY, value)
```

`DEFAULT_TIMEZONE` is `"America/New_York"` (`app_settings.py:14`), the first option, so the blank case stays valid.

`services/csvio.py`:

```python
MAX_IMPORT_ROWS = 5000

# A spreadsheet treats a cell starting with these as a formula. A trader's own
# note must never execute when their export is opened (decision S5).
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Free-text columns only: a leading "-" in pnl or a price is a negative number.
NUMERIC_COLUMNS = frozenset(
    {
        "entry_price",
        "stop_price",
        "tp_price",
        "exit_price",
        "position_size",
        "risk_amount",
        "pnl",
        "rr_planned",
        "rr_realized",
    }
)
TEXT_COLUMNS = frozenset(c for c in CSV_COLUMNS if c not in NUMERIC_COLUMNS)


class TooManyRows(ValueError):
    """The file exceeds MAX_IMPORT_ROWS; nothing was imported."""


def neutralise_formula(value):
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def restore_formula(value):
    if (
        isinstance(value, str)
        and len(value) > 1
        and value[0] == "'"
        and value[1:].startswith(FORMULA_PREFIXES)
    ):
        return value[1:]
    return value


def export_trades_csv(df: pd.DataFrame) -> bytes:
    """CSV bytes, column-ordered per CSV_COLUMNS, formulas neutralised."""
    out = df.reindex(columns=CSV_COLUMNS)
    for column in TEXT_COLUMNS:
        if column in out.columns:
            out[column] = out[column].map(neutralise_formula)
    return out.to_csv(index=False).encode("utf-8")


def import_trades_csv_text(csv_text: str, user_id: int) -> tuple[int, int, list[str]]:
    """`import_trades_csv` for text received over the API, row-capped first."""
    owner = require_user_id(user_id)
    try:
        frame = pd.read_csv(io.StringIO(csv_text))
    except Exception:
        _log.exception("CSV import failed to parse the uploaded text")
        return 0, 0, [_PARSE_FAILED]
    if len(frame.index) > MAX_IMPORT_ROWS:
        raise TooManyRows()
    return import_trades_csv(io.BytesIO(csv_text.encode("utf-8")), owner)
```

`NUMERIC_COLUMNS` is exactly the nine numeric entries of `CSV_COLUMNS` (`csvio.py:15`); the test above pins `notes` (text) and `pnl` (numeric). In `import_trades_csv`, apply `restore_formula` to `TEXT_COLUMNS` cells in the per-row `trade_data` dict before hashing:

```python
            trade_data = {
                k: (restore_formula(v) if k in TEXT_COLUMNS else v)
                for k, v in row.items()
                if pd.notna(v)
            }
```

- [ ] **Step 4: Run to verify pass**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_app_settings.py tests/test_csvio.py tests/test_csv_import_derivations.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/tradelens/services/app_settings.py src/tradelens/services/csvio.py tests/test_app_settings.py tests/test_csvio.py
git commit -m "fix(settings): allowlist timezones, cap CSV imports, neutralise formulas"
```

### Task A4: The Streamlit page uses the corrected services

**Files:**
- Modify: `src/tradelens/ui/pages/9_Settings.py`
- Test: `tests/test_settings_source.py`

- [ ] **Step 1: Write the failing test** (append)

```python
import re
from pathlib import Path

_PAGE = Path("src/tradelens/ui/pages/9_Settings.py").read_text(encoding="utf-8")


def test_the_streamlit_page_deletes_through_the_object_aware_services():
    assert "delete_all_trades_and_objects" in _PAGE
    assert "delete_account_and_objects" in _PAGE
    assert not re.search(r"^\s+delete_all_trades,\s*$", _PAGE, re.M)
    assert not re.search(r"import delete_account\b", _PAGE)


def test_a_blocked_deletion_says_nothing_was_deleted():
    assert "Some screenshots could not be removed, so nothing was deleted." in _PAGE
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/test_settings_source.py -q` → FAIL.

- [ ] **Step 3: Implement** — replace the two imports with `from src.tradelens.services.data_deletion import delete_account_and_objects, delete_all_trades_and_objects  # noqa: E402`, keep `get_trades` imported from `trade_service`, and replace the two handlers:

```python
            try:
                outcome = delete_all_trades_and_objects(uid)
            except Exception:  # noqa: BLE001 — never crash the page
                _log.exception("delete-all-trades failed for user %s", uid)
                _render_setting_status(False, _GENERIC_FAILURE)
            else:
                if outcome.blocked:
                    _render_setting_status(
                        False,
                        "Some screenshots could not be removed, so nothing was deleted.",
                    )
                else:
                    _render_setting_status(True, f"Deleted {outcome.deleted} trades.")
```

```python
            try:
                outcome = delete_account_and_objects(uid)
            except Exception:  # noqa: BLE001 — never crash the page
                _log.exception("account deletion failed for user %s", uid)
                _render_setting_status(False, _GENERIC_FAILURE)
            else:
                if outcome.blocked:
                    _render_setting_status(
                        False,
                        "Some screenshots could not be removed, so nothing was deleted.",
                    )
                elif outcome.deleted:
                    sign_out()
                    st.stop()
                else:
                    _render_setting_status(False, "That account no longer exists.")
```

Replace the timezone save's `except Exception` with an `except ValueError` branch first that renders `"Choose one of the listed timezones."`, then the existing generic branch.

- [ ] **Step 4: Run to verify pass** — `pytest tests/test_settings_source.py tests/test_account_ui.py tests/test_pages_boot.py -q -p no:cacheprovider`. Expected: PASS except the two recorded `test_pages_boot.py` analytics failures.

- [ ] **Step 5: Commit** — `git commit -m "fix(streamlit): Settings deletes through the object-aware services"`.

---

## Group B — the Settings API

### Task B1: `GET /v1/settings`, `PUT /v1/settings/timezone`, sample trades

**Files:**
- Create: `src/tradelens/api/schemas/settings.py`, `src/tradelens/api/routers/settings.py`
- Modify: `src/tradelens/api/app.py` (register router)
- Test: `tests/test_api_settings.py`

**Interfaces:**
- Consumes: `services.users.get_user_by_id`, `services.app_settings.{get_timezone, set_timezone, TIMEZONE_OPTIONS}`, `services.ai_client.has_api_key`, `services.demo.is_demo`, `services.password_reset.email_configured`, `services.sample_data.{count_sample_trades, load_sample_trades, clear_sample_trades}`, `services.cost.monthly_cost_by_feature`, `services.app_settings.today_for_owner`, `db.models.Trade`.
- Produces (schemas, all `_Strict`):
  - `SettingsAccount(username: str, email: Optional[str], email_verified: bool)`
  - `SettingsTimezone(current: str, options: List[str])`
  - `SettingsAI(state: Literal["enabled", "demo", "unavailable"])`
  - `SettingsData(trade_count: int, sample_count: int, csv_columns: List[str], max_import_rows: int)`
  - `SettingsCostRow(feature: str, cost_usd: float, calls: int)`
  - `SettingsCost(month: str, total_usd: float, rows: List[SettingsCostRow])`
  - `SettingsResponse(account, timezone, ai, data, cost, reset_email_configured: bool, demo_mode: bool)`
  - `TimezoneWrite(timezone: str)`
  - `SampleTradesResponse(count: int, sample_count: int)`
- Routes: `GET /v1/settings -> SettingsResponse`; `PUT /v1/settings/timezone -> SettingsResponse` (422 `[{field: "timezone", problem: "unsupported"}]`); `POST /v1/settings/sample-trades -> SampleTradesResponse`; `DELETE /v1/settings/sample-trades -> SampleTradesResponse`.

- [ ] **Step 1: Write the failing tests** — `tests/test_api_settings.py`, reusing the Phase 8 API test harness shape (`client` fixture with `TL_ENV=production`, `_session_handle_for(user_id)`, `_call` that signs the body). Copy those three helpers verbatim from `tests/test_api_partner.py` and add a `method` parameter to `_call`:

```python
def _call(client, handle, method, path, payload=None, *, sign=True):
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if sign:
        ts = str(int(time.time()))
        headers["X-TL-Signature"] = "v1={}:{}".format(
            ts, sign_request(SECRET, ts, method, path, "", body)
        )
    if handle is not None:
        headers["X-TL-Session-Handle"] = handle
    return client.request(method, path, content=body, headers=headers)


def test_settings_read_is_the_session_owners_not_user_one(client, two_users):
    first, second = two_users
    app_settings.set_timezone(first, "Asia/Tokyo")
    app_settings.set_timezone(second, "Europe/London")
    body = _call(client, _session_handle_for(second), "GET", "/v1/settings").json()
    assert body["timezone"]["current"] == "Europe/London"
    SettingsResponse.model_validate(body)


def test_every_route_needs_both_locks(client, two_users):
    handle = _session_handle_for(two_users[1])
    for method, path, payload in [
        ("GET", "/v1/settings", None),
        ("PUT", "/v1/settings/timezone", {"timezone": "UTC"}),
        ("POST", "/v1/settings/sample-trades", {}),
        ("DELETE", "/v1/settings/sample-trades", None),
    ]:
        assert _call(client, handle, method, path, payload, sign=False).status_code == 401
        assert _call(client, None, method, path, payload).status_code == 401


def test_an_unlisted_timezone_is_422_by_field_and_code_and_stores_nothing(
    client, two_users
):
    owner = two_users[1]
    app_settings.set_timezone(owner, "UTC")
    r = _call(
        client, _session_handle_for(owner), "PUT", "/v1/settings/timezone",
        {"timezone": "Mars/Olympus"},
    )
    assert r.status_code == 422
    assert r.json() == {"detail": [{"field": "timezone", "problem": "unsupported"}]}
    assert "Mars" not in r.text
    assert app_settings.get_timezone(owner) == "UTC"


@pytest.mark.parametrize(
    "extra", [{"user_id": 1}, {"owner": 1}, {"timezone": "UTC", "key": "x"}]
)
def test_the_timezone_write_is_a_strict_allowlist(client, two_users, extra):
    r = _call(
        client, _session_handle_for(two_users[1]), "PUT", "/v1/settings/timezone",
        dict({"timezone": "UTC"}, **extra),
    )
    assert r.status_code == 422


def test_ai_state_is_one_of_three_fixed_values(client, two_users, monkeypatch):
    handle = _session_handle_for(two_users[1])
    for key, demo, expected in [
        (True, False, "enabled"),
        (False, True, "demo"),
        (False, False, "unavailable"),
    ]:
        monkeypatch.setattr(settings_router, "has_api_key", lambda k=key: k)
        monkeypatch.setattr(settings_router, "is_demo", lambda d=demo: d)
        body = _call(client, handle, "GET", "/v1/settings").json()
        assert body["ai"] == {"state": expected}
        assert body["demo_mode"] is demo


def test_sample_trades_load_and_clear_only_this_owners(client, two_users):
    first, second = two_users
    sample_data.load_sample_trades(first)
    handle = _session_handle_for(second)
    loaded = _call(client, handle, "POST", "/v1/settings/sample-trades", {}).json()
    assert loaded["count"] == sample_data.SAMPLE_COUNT
    cleared = _call(client, handle, "DELETE", "/v1/settings/sample-trades").json()
    assert cleared == {"count": sample_data.SAMPLE_COUNT, "sample_count": 0}
    assert sample_data.count_sample_trades(first) == sample_data.SAMPLE_COUNT


def test_cost_is_this_owners_current_month(client, two_users, monkeypatch):
    owner = two_users[1]
    seen = []

    def fake(year, month, user_id):
        import pandas as pd

        seen.append((year, month, user_id))
        return pd.DataFrame([{"feature": "AI Partner", "cost_usd": 0.0123, "calls": 2}])

    monkeypatch.setattr(settings_router, "monthly_cost_by_feature", fake)
    body = _call(client, _session_handle_for(owner), "GET", "/v1/settings").json()
    assert seen and seen[0][2] == owner
    assert body["cost"]["rows"] == [
        {"feature": "AI Partner", "cost_usd": 0.0123, "calls": 2}
    ]
    assert body["cost"]["total_usd"] == 0.0123
```

(Imports: `json`, `time`, `pytest`, `TestClient`, `create_app`, `sign_request`, `SettingsResponse` from `api.schemas.settings`, `from src.tradelens.api.routers import settings as settings_router`, `app_settings`, `sample_data`.)

- [ ] **Step 2: Run to verify failure** — `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_api_settings.py -q -p no:cacheprovider` → FAIL (`ImportError`).

- [ ] **Step 3: Implement**

`src/tradelens/api/schemas/settings.py`:

```python
"""The Settings wire contract. Every model is `_Strict`."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import Field

from src.tradelens.api.schemas.trades import _Strict


class SettingsAccount(_Strict):
    username: str
    email: Optional[str]
    email_verified: bool


class SettingsTimezone(_Strict):
    current: str
    options: List[str]


class SettingsAI(_Strict):
    state: Literal["enabled", "demo", "unavailable"]


class SettingsData(_Strict):
    trade_count: int
    sample_count: int
    csv_columns: List[str]
    max_import_rows: int


class SettingsCostRow(_Strict):
    feature: str
    cost_usd: float
    calls: int


class SettingsCost(_Strict):
    month: str
    total_usd: float
    rows: List[SettingsCostRow]


class SettingsResponse(_Strict):
    account: SettingsAccount
    timezone: SettingsTimezone
    ai: SettingsAI
    data: SettingsData
    cost: SettingsCost
    reset_email_configured: bool
    demo_mode: bool


class TimezoneWrite(_Strict):
    timezone: str = Field(max_length=64)


class SampleTradesResponse(_Strict):
    count: int
    sample_count: int
```

`src/tradelens/api/routers/settings.py`:

```python
"""`/v1/settings` — preferences, data tools and account controls.

An owner-singleton: no route takes an id, and no body names an owner. Failures
are fixed codes, never exception or driver text.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from src.tradelens.api.deps import current_user
from src.tradelens.api.schemas.settings import (
    SampleTradesResponse,
    SettingsAccount,
    SettingsAI,
    SettingsCost,
    SettingsCostRow,
    SettingsData,
    SettingsResponse,
    SettingsTimezone,
    TimezoneWrite,
)
from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ai_client import has_api_key
from src.tradelens.services.app_settings import (
    TIMEZONE_OPTIONS,
    get_timezone,
    set_timezone,
    today_for_owner,
)
from src.tradelens.services.cost import monthly_cost_by_feature
from src.tradelens.services.csvio import CSV_COLUMNS, MAX_IMPORT_ROWS
from src.tradelens.services.demo import is_demo
from src.tradelens.services.password_reset import email_configured
from src.tradelens.services.sample_data import (
    clear_sample_trades,
    count_sample_trades,
    load_sample_trades,
)
from src.tradelens.services.users import get_user_by_id

router = APIRouter(prefix="/v1/settings", tags=["settings"])


def _trade_count(owner: int) -> int:
    db = SessionLocal()
    try:
        return db.query(Trade).filter(Trade.user_id == owner).count()
    finally:
        db.close()


def _ai_state() -> str:
    if has_api_key():
        return "enabled"
    if is_demo():
        return "demo"
    return "unavailable"


def _response(owner: int) -> SettingsResponse:
    user = get_user_by_id(owner)
    today = today_for_owner(owner)
    frame = monthly_cost_by_feature(today.year, today.month, user_id=owner)
    rows = [
        SettingsCostRow(
            feature=str(r["feature"]),
            cost_usd=round(float(r["cost_usd"]), 6),
            calls=int(r["calls"]),
        )
        for r in frame.to_dict("records")
    ]
    return SettingsResponse(
        account=SettingsAccount(
            username=str(getattr(user, "username", "") or ""),
            email=getattr(user, "email", None),
            email_verified=getattr(user, "email_verified_at", None) is not None,
        ),
        timezone=SettingsTimezone(
            current=get_timezone(owner), options=list(TIMEZONE_OPTIONS)
        ),
        ai=SettingsAI(state=_ai_state()),
        data=SettingsData(
            trade_count=_trade_count(owner),
            sample_count=count_sample_trades(owner),
            csv_columns=list(CSV_COLUMNS),
            max_import_rows=MAX_IMPORT_ROWS,
        ),
        cost=SettingsCost(
            month="{:04d}-{:02d}".format(today.year, today.month),
            total_usd=round(sum(r.cost_usd for r in rows), 6),
            rows=rows,
        ),
        reset_email_configured=bool(email_configured()),
        demo_mode=bool(is_demo()),
    )


def _field_problem(field: str, problem: str) -> JSONResponse:
    return JSONResponse(
        status_code=422, content={"detail": [{"field": field, "problem": problem}]}
    )


@router.get("", response_model=SettingsResponse)
def read_settings(user_id: int = Depends(current_user)):
    return _response(user_id)


@router.put("/timezone", response_model=SettingsResponse, responses={422: {}})
def write_timezone(payload: TimezoneWrite, user_id: int = Depends(current_user)):
    try:
        set_timezone(user_id, payload.timezone)
    except ValueError:
        return _field_problem("timezone", "unsupported")
    return _response(user_id)


@router.post("/sample-trades", response_model=SampleTradesResponse)
def load_samples(user_id: int = Depends(current_user)):
    count = load_sample_trades(user_id)
    return SampleTradesResponse(count=count, sample_count=count_sample_trades(user_id))


@router.delete("/sample-trades", response_model=SampleTradesResponse)
def clear_samples(user_id: int = Depends(current_user)):
    count = clear_sample_trades(user_id)
    return SampleTradesResponse(count=count, sample_count=count_sample_trades(user_id))
```

`POST /v1/settings/sample-trades` takes no body model; the signed empty JSON object `{}` is accepted by `verified_body` and ignored. In `api/app.py` add `settings` to the router import tuple and `app.include_router(settings.router)` after `partner`.

- [ ] **Step 4: Run to verify pass** — `PYTHONDONTWRITEBYTECODE=1 pytest tests/test_api_settings.py tests/test_api_security.py -q -p no:cacheprovider` → PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(api): Settings read, timezone and sample trades"`.

### Task B2: CSV export and import

**Files:**
- Modify: `src/tradelens/api/schemas/settings.py`, `src/tradelens/api/routers/settings.py`
- Test: `tests/test_api_settings.py`

**Interfaces:**
- Produces:
  - `CsvExportResponse(filename: Literal["trades.csv"], row_count: int, csv: str)`
  - `CsvImportWrite(csv: str = Field(min_length=1, max_length=900_000))`
  - `CsvImportResponse(inserted: int, skipped: int, errors: List[str])` — `errors` are the service's fixed sentences, capped at 20 entries.
  - `GET /v1/settings/export -> CsvExportResponse`
  - `POST /v1/settings/import -> CsvImportResponse`; 422 `[{field: "csv", problem: "too_many_rows"}]` when over `MAX_IMPORT_ROWS`.

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_export_contains_only_this_owners_trades(client, two_users):
    first, second = two_users
    sample_data.load_sample_trades(first)
    body = _call(client, _session_handle_for(second), "GET", "/v1/settings/export").json()
    assert body["filename"] == "trades.csv"
    assert body["row_count"] == 0
    assert body["csv"].splitlines()[0].split(",")[:3] == csvio.CSV_COLUMNS[:3]


def test_import_inserts_for_the_session_owner_and_reports_counts(client, two_users):
    owner = two_users[1]
    text = "trade_date,asset,direction,result,pnl\n2026-09-01,NQ,Long,Win,100\n"
    r = _call(
        client, _session_handle_for(owner), "POST", "/v1/settings/import", {"csv": text}
    )
    assert r.status_code == 200
    assert r.json() == {"inserted": 1, "skipped": 0, "errors": []}


def test_an_import_over_the_row_cap_is_422_and_inserts_nothing(
    client, two_users, monkeypatch
):
    owner = two_users[1]
    monkeypatch.setattr(csvio, "MAX_IMPORT_ROWS", 2)
    text = "trade_date,asset,direction,result,pnl\n" + "2026-09-01,NQ,Long,Win,1\n" * 3
    r = _call(
        client, _session_handle_for(owner), "POST", "/v1/settings/import", {"csv": text}
    )
    assert r.status_code == 422
    assert r.json() == {"detail": [{"field": "csv", "problem": "too_many_rows"}]}


def test_import_errors_never_echo_the_file(client, two_users):
    owner = two_users[1]
    text = "trade_date,asset\nSECRET-NOTE,NQ\n"
    body = _call(
        client, _session_handle_for(owner), "POST", "/v1/settings/import", {"csv": text}
    ).json()
    assert "SECRET-NOTE" not in json.dumps(body)


@pytest.mark.parametrize("payload", [{"csv": ""}, {"csv": 7}, {"file": "x"}, {}])
def test_the_import_body_is_a_strict_allowlist(client, two_users, payload):
    r = _call(client, _session_handle_for(two_users[1]), "POST", "/v1/settings/import", payload)
    assert r.status_code == 422
```

(`from src.tradelens.services import csvio`.) Note `CsvImportWrite.max_length=900_000` keeps a JSON-escaped body under `MAX_BODY_BYTES`.

- [ ] **Step 2: Run to verify failure** — FAIL (404 on the new paths).

- [ ] **Step 3: Implement** — schemas as listed; routes:

```python
@router.get("/export", response_model=CsvExportResponse)
def export_csv(user_id: int = Depends(current_user)):
    import pandas as pd

    trades = get_trades(user_id=user_id)
    frame = pd.DataFrame(
        [{col: getattr(t, col, None) for col in CSV_COLUMNS} for t in trades]
    )
    return CsvExportResponse(
        filename="trades.csv",
        row_count=len(frame.index),
        csv=export_trades_csv(frame).decode("utf-8"),
    )


@router.post("/import", response_model=CsvImportResponse, responses={422: {}})
def import_csv(payload: CsvImportWrite, user_id: int = Depends(current_user)):
    try:
        inserted, skipped, errors = import_trades_csv_text(payload.csv, user_id)
    except TooManyRows:
        return _field_problem("csv", "too_many_rows")
    return CsvImportResponse(inserted=inserted, skipped=skipped, errors=errors[:20])
```

(Imports: `get_trades` from `services.trade_service`; `export_trades_csv`, `import_trades_csv_text`, `TooManyRows` from `services.csvio`. `import_trades_csv_text` reads the module-level `MAX_IMPORT_ROWS` when it runs, so the test's `monkeypatch.setattr(csvio, "MAX_IMPORT_ROWS", 2)` applies.)

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(api): Settings CSV export and import"`.

### Task B3: Delete all trades and delete account

**Files:**
- Modify: `src/tradelens/api/schemas/settings.py`, `src/tradelens/api/routers/settings.py`
- Test: `tests/test_api_settings.py`

**Interfaces:**
- Consumes: `services.data_deletion.{delete_all_trades_and_objects, delete_account_and_objects, DeletionOutcome}`; `api.schemas.trades.ScreenshotCleanupFailedResponse`.
- Produces:
  - `DeleteTradesWrite(confirm: Literal["DELETE"])`
  - `DeleteAccountWrite(confirm: Literal["DELETE MY ACCOUNT"])`
  - `DeleteTradesResponse(deleted: int)`
  - `POST /v1/settings/delete-trades -> DeleteTradesResponse`; 503 `{"detail": {"error": "screenshot_cleanup_failed", "remaining": int, "unresolvable": int}}`
  - `POST /v1/settings/delete-account -> 204`; same 503; 404 `{"detail": "Not Found"}` if the account is already gone.

- [ ] **Step 1: Write the failing tests** (append)

```python
@pytest.mark.parametrize(
    "path, phrase",
    [("/v1/settings/delete-trades", "DELETE"), ("/v1/settings/delete-account", "DELETE MY ACCOUNT")],
)
@pytest.mark.parametrize(
    "confirm", ["delete", "DELETE ", " DELETE", "DELETE MY  ACCOUNT", "", None, 1]
)
def test_a_wrong_confirmation_is_422_and_deletes_nothing(
    client, two_users, monkeypatch, path, phrase, confirm
):
    if confirm == phrase:
        return
    called = []
    monkeypatch.setattr(settings_router, "delete_all_trades_and_objects", lambda u: called.append(u))
    monkeypatch.setattr(settings_router, "delete_account_and_objects", lambda u: called.append(u))
    r = _call(client, _session_handle_for(two_users[1]), "POST", path, {"confirm": confirm})
    assert r.status_code == 422
    assert called == []


def test_delete_trades_runs_for_the_session_owner(client, two_users, monkeypatch):
    first, second = two_users
    seen = []
    monkeypatch.setattr(
        settings_router,
        "delete_all_trades_and_objects",
        lambda u: seen.append(u) or DeletionOutcome(3, 0, 0, False),
    )
    r = _call(client, _session_handle_for(second), "POST", "/v1/settings/delete-trades", {"confirm": "DELETE"})
    assert r.json() == {"deleted": 3}
    assert seen == [second]


@pytest.mark.parametrize("path, phrase", [("/v1/settings/delete-trades", "DELETE"), ("/v1/settings/delete-account", "DELETE MY ACCOUNT")])
def test_a_blocked_cleanup_is_503_with_the_retryable_split(client, two_users, monkeypatch, path, phrase):
    blocked = DeletionOutcome(0, 2, 1, True)
    monkeypatch.setattr(settings_router, "delete_all_trades_and_objects", lambda u: blocked)
    monkeypatch.setattr(settings_router, "delete_account_and_objects", lambda u: blocked)
    r = _call(client, _session_handle_for(two_users[1]), "POST", path, {"confirm": phrase})
    assert r.status_code == 503
    assert r.json() == {"detail": {"error": "screenshot_cleanup_failed", "remaining": 2, "unresolvable": 1}}


def test_account_deletion_is_204_and_the_session_no_longer_works(client, two_users, monkeypatch):
    owner = two_users[1]
    monkeypatch.setattr(storage, "delete_trade_objects", lambda u, t: ObjectCleanup([], [], []))
    handle = _session_handle_for(owner)
    r = _call(client, handle, "POST", "/v1/settings/delete-account", {"confirm": "DELETE MY ACCOUNT"})
    assert r.status_code == 204
    assert _call(client, handle, "GET", "/v1/settings").status_code == 401
```

(Imports: `DeletionOutcome` from `services.data_deletion`; `storage` from `api`; `ObjectCleanup` from `api.storage`.)

- [ ] **Step 2: Run to verify failure** — FAIL (404).

- [ ] **Step 3: Implement**

```python
def _cleanup_failed(outcome) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "error": "screenshot_cleanup_failed",
            "remaining": outcome.remaining,
            "unresolvable": outcome.unresolvable,
        },
    )


@router.post(
    "/delete-trades",
    response_model=DeleteTradesResponse,
    responses={503: {"model": ScreenshotCleanupFailedResponse}},
)
def delete_trades(payload: DeleteTradesWrite, user_id: int = Depends(current_user)):
    outcome = delete_all_trades_and_objects(user_id)
    if outcome.blocked:
        raise _cleanup_failed(outcome)
    return DeleteTradesResponse(deleted=outcome.deleted)


@router.post(
    "/delete-account",
    status_code=204,
    responses={404: {}, 503: {"model": ScreenshotCleanupFailedResponse}},
)
def delete_my_account(payload: DeleteAccountWrite, user_id: int = Depends(current_user)):
    outcome = delete_account_and_objects(user_id)
    if outcome.blocked:
        raise _cleanup_failed(outcome)
    if not outcome.deleted:
        raise HTTPException(status_code=404, detail="Not Found")
    return Response(status_code=204)
```

`payload` is unused beyond validation: the `Literal` type is the confirmation check, so a request that reaches the body of the route has already typed the phrase exactly. (Imports: `HTTPException`, `Response` from `fastapi`.)

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Regenerate the contract from the repository root and commit**

```bash
python scripts/generate_openapi.py
npm --prefix web run api:types
git add src/tradelens/api tests/test_api_settings.py web/lib/api/openapi.json web/lib/api/schema.d.ts
git commit -m "feat(api): Settings deletions with typed confirmation and object cleanup"
```

---

## Group C — relays and the server bridge

### Task C1: `lib/app/settings.ts` and `lib/app/settings-relay.ts`

**Files:**
- Create: `web/lib/app/settings.ts`, `web/lib/app/settings-relay.ts`
- Test: `web/__tests__/settings-relay.test.ts` (C2 extends it)

**Interfaces:**
- Produces:
  - Types `SettingsResponse`, `SampleTradesResponse`, `CsvExportResponse`, `CsvImportResponse`, `DeleteTradesResponse` from `components["schemas"]`.
  - `fetchSettings(token)`, `writeTimezone(token, body)`, `loadSampleTrades(token)`, `clearSampleTrades(token)`, `exportTradesCsv(token)`, `importTradesCsv(token, body)`, `deleteAllTrades(token, body)`, `deleteAccount(token, body)`.
  - `SETTINGS_NO_STORE`, `authorizeSettingsRelay(request)`, `settingsRelayFailure(err, ApiError)` mapping: 422 → `{ok:false, detail:[{field, problem}]}` field/code only; 503 with `screenshot_cleanup_failed` → `{ok:false, detail:"screenshot_cleanup_failed", unresolvable: boolean}`; 404 → `{ok:false}`; other `ApiError` → `{ok:false}` with its status; non-`ApiError` → 502 `{ok:false}`.

- [ ] **Step 1: Write the failing test** — copy the authorization `describe.each` block from `web/__tests__/strategy-relay.test.ts` (missing `SITE_ORIGIN` → 403 before the session read; cross-origin → 403; no session → 401; ineligible `appSurface: "streamlit"` → 403; only the session token is forwarded; `runtime`/`dynamic`), replacing the mocked module with `@/lib/app/settings` and the route table with the six routes from Task C2. Add the failure-mapping block:

```ts
it("maps a cleanup 503 to a fixed code and a boolean, never counts or keys", async () => {
  const { settingsRelayFailure } = await import("@/lib/app/settings-relay");
  const { ApiError } = await import("@/lib/api/client");
  const r = settingsRelayFailure(
    new ApiError(503, { detail: { error: "screenshot_cleanup_failed", remaining: 2, unresolvable: 1, key: "u/9/t/1/x.png" } }),
    ApiError,
  );
  expect(r.status).toBe(503);
  expect(await r.json()).toEqual({ ok: false, detail: "screenshot_cleanup_failed", unresolvable: true });
});

it("forwards a 422 by field and code only", async () => {
  const { settingsRelayFailure } = await import("@/lib/app/settings-relay");
  const { ApiError } = await import("@/lib/api/client");
  const r = settingsRelayFailure(
    new ApiError(422, { detail: [{ field: "csv", problem: "too_many_rows", input: "SECRET" }] }),
    ApiError,
  );
  expect(await r.json()).toEqual({ ok: false, detail: [{ field: "csv", problem: "too_many_rows" }] });
});
```

- [ ] **Step 2: Run** — `cd web && npx vitest run __tests__/settings-relay.test.ts` → FAIL.

- [ ] **Step 3: Implement** — `settings.ts` mirrors `lib/app/strategy.ts`:

```ts
import "server-only";

import { callApi } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type SettingsResponse = components["schemas"]["SettingsResponse"];
export type SampleTradesResponse = components["schemas"]["SampleTradesResponse"];
export type CsvExportResponse = components["schemas"]["CsvExportResponse"];
export type CsvImportResponse = components["schemas"]["CsvImportResponse"];
export type DeleteTradesResponse = components["schemas"]["DeleteTradesResponse"];

export const fetchSettings = (t: string) => callApi<SettingsResponse>("/v1/settings", t);
export const writeTimezone = (t: string, body: unknown) =>
  callApi<SettingsResponse>("/v1/settings/timezone", t, { method: "PUT", body });
export const loadSampleTrades = (t: string) =>
  callApi<SampleTradesResponse>("/v1/settings/sample-trades", t, { method: "POST", body: {} });
export const clearSampleTrades = (t: string) =>
  callApi<SampleTradesResponse>("/v1/settings/sample-trades", t, { method: "DELETE" });
export const exportTradesCsv = (t: string) =>
  callApi<CsvExportResponse>("/v1/settings/export", t);
export const importTradesCsv = (t: string, body: unknown) =>
  callApi<CsvImportResponse>("/v1/settings/import", t, { method: "POST", body });
export const deleteAllTrades = (t: string, body: unknown) =>
  callApi<DeleteTradesResponse>("/v1/settings/delete-trades", t, { method: "POST", body });
export const deleteAccount = (t: string, body: unknown) =>
  callApi<void>("/v1/settings/delete-account", t, { method: "POST", body });
```

`settings-relay.ts` copies `authorizePartnerRelay` verbatim (renamed, same fail-shut order and headers) and implements the mapping above:

```ts
export function settingsRelayFailure(err: unknown, apiError: typeof ApiError): NextResponse {
  if (!(err instanceof apiError)) {
    return NextResponse.json({ ok: false }, { status: 502, headers: SETTINGS_NO_STORE });
  }
  const detail = (err.body as { detail?: unknown } | undefined)?.detail;
  if (err.status === 422 && Array.isArray(detail)) {
    const problems = detail.flatMap((item) => {
      const field = (item as { field?: unknown })?.field;
      const problem = (item as { problem?: unknown })?.problem;
      return typeof field === "string" && typeof problem === "string" ? [{ field, problem }] : [];
    });
    return NextResponse.json(problems.length ? { ok: false, detail: problems } : { ok: false }, {
      status: 422,
      headers: SETTINGS_NO_STORE,
    });
  }
  const cleanup = detail as { error?: unknown; unresolvable?: unknown } | undefined;
  if (err.status === 503 && cleanup?.error === "screenshot_cleanup_failed") {
    return NextResponse.json(
      {
        ok: false,
        detail: "screenshot_cleanup_failed",
        unresolvable: typeof cleanup.unresolvable === "number" && cleanup.unresolvable > 0,
      },
      { status: 503, headers: SETTINGS_NO_STORE },
    );
  }
  return NextResponse.json({ ok: false }, { status: err.status, headers: SETTINGS_NO_STORE });
}
```

- [ ] **Step 4: Run** — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(web): Settings server bridge and relay authorization"`.

### Task C2: The six relay routes

**Files:**
- Create: `web/app/api/settings/{timezone,sample-trades,export,import,delete-trades,delete-account}/route.ts`
- Test: `web/__tests__/settings-relay.test.ts`

**Interfaces:**
- `PUT /api/settings/timezone` → body forwarded unchanged → 200 `SettingsResponse`.
- `POST /api/settings/sample-trades`, `DELETE /api/settings/sample-trades` → 200 `SampleTradesResponse`.
- `GET /api/settings/export` → 200 `text/csv; charset=utf-8`, `Content-Disposition: attachment; filename="trades.csv"`, body = `csv`; `no-store`.
- `POST /api/settings/import` → refuses a `Content-Length` over `1_048_576` with 413 `{ok:false}` before reading; body forwarded → 200 `CsvImportResponse`.
- `POST /api/settings/delete-trades` → 200 `DeleteTradesResponse`.
- `POST /api/settings/delete-account` → on backend 204: **clears the session cookie** (`response.cookies.delete(SESSION_COOKIE)`) and answers 200 `{ok:true, next:"/account-deleted"}`; on any failure the cookie is kept.

- [ ] **Step 1: Write the failing tests** (append to `settings-relay.test.ts`)

```ts
it("serves the export as a CSV attachment with no-store", async () => {
  exportTradesCsv.mockResolvedValue({ filename: "trades.csv", row_count: 1, csv: "a,b\n1,2\n" });
  const { GET } = await import("@/app/api/settings/export/route");
  const r = await GET(req("GET", "/api/settings/export"));
  expect(r.headers.get("Content-Type")).toBe("text/csv; charset=utf-8");
  expect(r.headers.get("Content-Disposition")).toBe('attachment; filename="trades.csv"');
  expect(r.headers.get("Cache-Control")).toBe("no-store, private");
  expect(await r.text()).toBe("a,b\n1,2\n");
});

it("refuses an oversized import before reading or forwarding it", async () => {
  const { POST } = await import("@/app/api/settings/import/route");
  const r = await POST(req("POST", "/api/settings/import", { "content-length": "2000000" }, "{}"));
  expect(r.status).toBe(413);
  expect(importTradesCsv).not.toHaveBeenCalled();
});

it("clears the session cookie only after the account is really deleted", async () => {
  deleteAccount.mockResolvedValue(undefined);
  const { POST } = await import("@/app/api/settings/delete-account/route");
  const r = await POST(req("POST", "/api/settings/delete-account", {}, JSON.stringify({ confirm: "DELETE MY ACCOUNT" })));
  expect(await r.json()).toEqual({ ok: true, next: "/account-deleted" });
  expect(r.headers.get("set-cookie") ?? "").toMatch(/tl_session=;/);
});

it("keeps the session cookie when account deletion is blocked", async () => {
  const { ApiError } = await import("@/lib/api/client");
  deleteAccount.mockRejectedValue(new ApiError(503, { detail: { error: "screenshot_cleanup_failed", remaining: 1, unresolvable: 0 } }));
  const { POST } = await import("@/app/api/settings/delete-account/route");
  const r = await POST(req("POST", "/api/settings/delete-account", {}, JSON.stringify({ confirm: "DELETE MY ACCOUNT" })));
  expect(r.status).toBe(503);
  expect(r.headers.get("set-cookie")).toBeNull();
});
```

`SESSION_COOKIE` is `"tl_session"` (`web/lib/auth/login.ts:39`), which the `set-cookie` regex above matches.

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement** — each route copies the Strategy relay shape (`authorizeSettingsRelay` → parse JSON → call → `settingsRelayFailure`). The two with different bodies:

`export/route.ts`:

```ts
export async function GET(request: Request) {
  const auth = await authorizeSettingsRelay(request);
  if (auth instanceof NextResponse) return auth;
  try {
    const result = await exportTradesCsv(auth.token);
    return new NextResponse(result.csv, {
      status: 200,
      headers: {
        ...SETTINGS_NO_STORE,
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="trades.csv"',
      },
    });
  } catch (err) {
    return settingsRelayFailure(err, ApiError);
  }
}
```

`delete-account/route.ts`:

```ts
export async function POST(request: Request) {
  const auth = await authorizeSettingsRelay(request);
  if (auth instanceof NextResponse) return auth;
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400, headers: SETTINGS_NO_STORE });
  }
  try {
    await deleteAccount(auth.token, body);
  } catch (err) {
    return settingsRelayFailure(err, ApiError);
  }
  // The backend has already deleted every session row for this account, so
  // the cookie names nothing; clearing it stops the browser presenting it.
  const response = NextResponse.json(
    { ok: true, next: "/account-deleted" },
    { status: 200, headers: SETTINGS_NO_STORE },
  );
  response.cookies.delete(SESSION_COOKIE);
  return response;
}
```

All six export `runtime = "nodejs"` and `dynamic = "force-dynamic"`.

- [ ] **Step 4: Run** — PASS; `npx tsc --noEmit` clean.

- [ ] **Step 5: Commit** — `git commit -m "feat(web): Settings relays"`.

---

## Group D — the Settings page

### Task D1: Page, Profile and Preferences

**Files:**
- Replace: `web/app/app/settings/page.tsx`; create `loading.tsx`, `error.tsx`
- Create: `web/components/app/settings/setting-status.tsx`, `profile-section.tsx`, `preferences-section.tsx`
- Test: `web/__tests__/settings-page.test.tsx`

**Interfaces:**
- `SettingStatus({ tone: "ok" | "fail", text })` — `<p role="status">`.
- `ProfileSection({ account, resetEmailConfigured })` — shows username, email or "No email on this account", verified/unverified; **no edit control** (S1).
- `PreferencesSection({ timezone, ai, demoMode })` — `<select>` of `timezone.options`, saving on change through `PUT /api/settings/timezone`; AI state line from three fixed strings.

- [ ] **Step 1: Write the failing tests**

```tsx
import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PreferencesSection } from "@/components/app/settings/preferences-section";
import { ProfileSection } from "@/components/app/settings/profile-section";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("profile", () => {
  it("shows the email and its verification but offers no way to change it here", () => {
    render(
      <ProfileSection
        account={{ username: "trader", email: "t@example.com", email_verified: true }}
        resetEmailConfigured
      />,
    );
    expect(screen.getByText("t@example.com")).toBeInTheDocument();
    expect(screen.getByText(/verified/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
  });
});

describe("preferences", () => {
  const timezone = { current: "UTC", options: ["America/New_York", "UTC"] };

  it("saves a timezone change through the relay and confirms beside the control", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ timezone: { current: "America/New_York", options: timezone.options } }) });
    render(<PreferencesSection timezone={timezone} ai={{ state: "enabled" }} demoMode={false} />);
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/trading timezone/i), { target: { value: "America/New_York" } });
    });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/settings/timezone");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ timezone: "America/New_York" });
    expect(screen.getByRole("status")).toHaveTextContent("Trading timezone saved — America/New_York.");
  });

  it.each([
    ["enabled", /AI features are enabled/],
    ["demo", /Demo mode/],
    ["unavailable", /AI features are unavailable/],
  ] as const)("describes the %s AI state without secret instructions", (state, copy) => {
    render(<PreferencesSection timezone={timezone} ai={{ state }} demoMode={state === "demo"} />);
    expect(screen.getByText(copy)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/ANTHROPIC_API_KEY|secrets\.toml|\.env/);
  });
});
```

- [ ] **Step 2: Run** — FAIL.

- [ ] **Step 3: Implement** — `page.tsx` is a Server Component: `sessionTokenFrom` cookies → `authenticateSessionToken` → `appLayoutRedirect` (redirect) → `fetchSettings(token)`; a thrown `ApiError` renders `error.tsx`'s state. Sections render in the Streamlit order with the Streamlit section headers and ledes. Copy for the AI states:
  - `enabled`: "AI features are enabled."
  - `demo`: "Demo mode — AI sections read cached sample responses. No key, no spend."
  - `unavailable`: "AI features are unavailable on this deployment right now."
  - Timezone save success: "Trading timezone saved — {tz}."; 422: "Choose one of the listed timezones."; anything else: "That did not work. Try again."

```tsx
"use client";

import { useState } from "react";

import { SettingStatus } from "@/components/app/settings/setting-status";

const AI_COPY = {
  enabled: "AI features are enabled.",
  demo: "Demo mode — AI sections read cached sample responses. No key, no spend.",
  unavailable: "AI features are unavailable on this deployment right now.",
} as const;

export function PreferencesSection({
  timezone,
  ai,
  demoMode,
}: {
  timezone: { current: string; options: string[] };
  ai: { state: keyof typeof AI_COPY };
  demoMode: boolean;
}) {
  const [current, setCurrent] = useState(timezone.current);
  const [status, setStatus] = useState<{ tone: "ok" | "fail"; text: string } | null>(null);
  const options = timezone.options.includes(current) ? timezone.options : [current, ...timezone.options];

  async function save(next: string) {
    const previous = current;
    setCurrent(next);
    setStatus(null);
    try {
      const r = await fetch("/api/settings/timezone", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ timezone: next }),
      });
      if (r.ok) {
        setStatus({ tone: "ok", text: `Trading timezone saved — ${next}.` });
        return;
      }
      setCurrent(previous);
      setStatus({
        tone: "fail",
        text: r.status === 422 ? "Choose one of the listed timezones." : "That did not work. Try again.",
      });
    } catch {
      setCurrent(previous);
      setStatus({ tone: "fail", text: "That did not work. Try again." });
    }
  }

  return (
    <section aria-labelledby="settings-preferences" className="mt-10">
      <h2 id="settings-preferences" className="font-display text-xl font-bold">Preferences</h2>
      <p className="mt-1 text-sm text-muted">How the app interprets what you log.</p>
      <label htmlFor="settings-timezone" className="mt-4 block text-sm text-text">
        Trading timezone
      </label>
      <select
        id="settings-timezone"
        value={current}
        onChange={(e) => void save(e.target.value)}
        className="mt-1 min-h-[44px] rounded-lg border border-line bg-bg px-3 text-sm text-text"
      >
        {options.map((tz) => (
          <option key={tz} value={tz}>{tz}</option>
        ))}
      </select>
      <p className="mt-1 text-xs text-muted">Used to detect your killzone and session from the entry time on New Trade.</p>
      {status ? <SettingStatus tone={status.tone} text={status.text} /> : null}
      <p className={`mt-6 text-sm ${ai.state === "unavailable" ? "text-muted" : "text-text"}`}>
        {AI_COPY[ai.state]}
      </p>
      {demoMode ? <p className="mt-1 text-xs text-muted">This deployment is running in demo mode.</p> : null}
    </section>
  );
}
```

`ProfileSection` renders "Signed in as {username}", the email (or "No email on this account"), "Verified" / "Not verified yet", and — when `resetEmailConfigured` is false — "Outgoing email is not configured on this deployment yet, so reset messages cannot be delivered." It renders no input.

- [ ] **Step 4: Run** — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(web): Settings page, profile and preferences"`.

### Task D2: Data section — export, import, sample trades, cost

**Files:**
- Create: `web/components/app/settings/data-section.tsx`
- Test: `web/__tests__/settings-data-section.test.tsx`

**Interfaces:**
- `DataSection({ data, cost })`.
- Export is a plain link to `/api/settings/export` (`download` attribute, `href` same-origin) labelled "Export {trade_count} trades as CSV".
- Import: `<input type="file" accept=".csv,text/csv">`; a file over 900,000 bytes is refused client-side with "That file is larger than 1 MB. Split it and import each part." and never sent; otherwise `file.text()` → `POST /api/settings/import` `{csv}`. Copy: `"Imported {inserted} trades, skipped {skipped} duplicates."`, `"That CSV was valid but had no rows."`, the returned `errors` rendered as a list, 422 `too_many_rows` → "That file has more than {max_import_rows} trades. Split it and import each part.", anything else "That did not work. Try again."
- Sample trades: "Load sample trades" → `POST`; "Clear sample trades" (disabled when `sample_count === 0`) → `DELETE`; copy `"Loaded {count} sample trades."` / `"Removed {count} sample trades."`; note "{sample_count} sample trades are loaded. They are flagged as samples and clearing them never touches a trade you logged."
- Cost: a table of `rows` (feature, `$` + 4 decimals, calls) and "AI spend this month: ${total}."; empty → "No AI spend recorded this month."

- [ ] **Step 1: Write the failing tests**

```tsx
it("never sends a file over the size limit", async () => {
  render(<DataSection data={data} cost={emptyCost} />);
  const big = new File(["x".repeat(900_001)], "t.csv", { type: "text/csv" });
  await act(async () => {
    fireEvent.change(screen.getByLabelText(/import trades from csv/i), { target: { files: [big] } });
  });
  expect(fetchMock).not.toHaveBeenCalled();
  expect(screen.getByRole("status")).toHaveTextContent(/larger than 1 MB/);
});

it("imports the file text and reports counts in the Streamlit wording", async () => {
  fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ inserted: 3, skipped: 1, errors: [] }) });
  render(<DataSection data={data} cost={emptyCost} />);
  const file = new File(["trade_date,asset\n"], "t.csv", { type: "text/csv" });
  await act(async () => {
    fireEvent.change(screen.getByLabelText(/import trades from csv/i), { target: { files: [file] } });
  });
  expect(fetchMock.mock.calls[0][0]).toBe("/api/settings/import");
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ csv: "trade_date,asset\n" });
  expect(screen.getByRole("status")).toHaveTextContent("Imported 3 trades, skipped 1 duplicates.");
});

it("links the export to the same-origin relay", () => {
  render(<DataSection data={data} cost={emptyCost} />);
  expect(screen.getByRole("link", { name: /export 12 trades as csv/i })).toHaveAttribute("href", "/api/settings/export");
});

it("disables clearing when there are no sample trades", () => {
  render(<DataSection data={{ ...data, sample_count: 0 }} cost={emptyCost} />);
  expect(screen.getByRole("button", { name: /clear sample trades/i })).toBeDisabled();
});

it("shows this month's cost with four decimals and the total", () => {
  render(<DataSection data={data} cost={{ month: "2026-09", total_usd: 0.0123, rows: [{ feature: "AI Partner", cost_usd: 0.0123, calls: 2 }] }} />);
  expect(screen.getByRole("cell", { name: "$0.0123" })).toBeInTheDocument();
  expect(screen.getByText("AI spend this month: $0.0123.")).toBeInTheDocument();
});
```

(Fixtures at the top of the file: `const data = { trade_count: 12, sample_count: 20, csv_columns: ["trade_date"], max_import_rows: 5000 }; const emptyCost = { month: "2026-09", total_usd: 0, rows: [] };` plus the `fetch` stub from D1. jsdom 26 does not implement `File.prototype.text`, so the test file also starts with `Object.defineProperty(File.prototype, "text", { configurable: true, value() { return new Response(this).text(); } });`.)

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** to the interface above (same status/state pattern as D1). **Step 4: Run** — PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(web): Settings data tools and monthly AI cost"`.

### Task D3: Danger Zone and the account-deleted landing

**Files:**
- Create: `web/components/app/settings/danger-zone.tsx`, `web/app/account-deleted/page.tsx`
- Test: `web/__tests__/settings-danger-zone.test.tsx`

**Interfaces:**
- `DangerZone()` — two disclosures ("Delete all trades", "Delete my account") inside the only bordered region on the page, with the Streamlit copy verbatim (what is erased; anonymous cost records kept; "Export your trades first if you want to keep them.").
- Delete all trades: text input "Type DELETE to confirm"; button "Delete all trades permanently" enabled only when the value is exactly `DELETE`; sends `{confirm: "DELETE"}`; success "Deleted {n} trades."; 503 → `unresolvable` false: "Some screenshots could not be removed, so nothing was deleted. Try again." / true: "Some screenshots could not be removed, so nothing was deleted. Contact support — trying again will not fix this."; other → "That did not work. Try again."
- Delete account: input "Type DELETE MY ACCOUNT to confirm"; button enabled only when `value.trim() === "DELETE MY ACCOUNT"` (Streamlit parity); sends `{confirm: "DELETE MY ACCOUNT"}` (the trimmed constant, never the raw input); on `{ok:true, next}` → `window.location.assign(next)`; same 503 copy; other → generic.
- Both buttons disabled while a request is in flight (synchronous ref guard, as Phase 8's conversation).
- `/account-deleted` — a public page: "Your account has been deleted." and a link to the marketing home. It reads no session.

- [ ] **Step 1: Write the failing tests**

```tsx
it.each(["delete", "DELETE ", "DELET"])("keeps delete-all-trades disabled for %j", (typed) => {
  render(<DangerZone />);
  fireEvent.click(screen.getByText("Delete all trades"));
  fireEvent.change(screen.getByLabelText(/type DELETE to confirm/i), { target: { value: typed } });
  expect(screen.getByRole("button", { name: /delete all trades permanently/i })).toBeDisabled();
});

it("sends the constant confirmation, never the typed text", async () => {
  fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true, next: "/account-deleted" }) });
  const assign = vi.fn();
  vi.stubGlobal("location", { assign });
  render(<DangerZone />);
  fireEvent.click(screen.getByText("Delete my account"));
  fireEvent.change(screen.getByLabelText(/type DELETE MY ACCOUNT to confirm/i), { target: { value: "  DELETE MY ACCOUNT  " } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /delete my account permanently/i }));
  });
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ confirm: "DELETE MY ACCOUNT" });
  expect(assign).toHaveBeenCalledWith("/account-deleted");
});

it("says nothing was deleted when screenshot cleanup is blocked, and whether retrying helps", async () => {
  fetchMock.mockResolvedValue({ ok: false, status: 503, json: async () => ({ ok: false, detail: "screenshot_cleanup_failed", unresolvable: true }) });
  render(<DangerZone />);
  fireEvent.click(screen.getByText("Delete all trades"));
  fireEvent.change(screen.getByLabelText(/type DELETE to confirm/i), { target: { value: "DELETE" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /delete all trades permanently/i }));
  });
  expect(screen.getByRole("status")).toHaveTextContent(/nothing was deleted/);
  expect(screen.getByRole("status")).toHaveTextContent(/trying again will not fix this/);
});

it("sends one request for a double click", async () => {
  let release: (v: unknown) => void = () => {};
  fetchMock.mockImplementation(() => new Promise((r) => (release = r)));
  render(<DangerZone />);
  fireEvent.click(screen.getByText("Delete all trades"));
  fireEvent.change(screen.getByLabelText(/type DELETE to confirm/i), { target: { value: "DELETE" } });
  const button = screen.getByRole("button", { name: /delete all trades permanently/i });
  await act(async () => {
    fireEvent.click(button);
    fireEvent.click(button);
  });
  expect(fetchMock).toHaveBeenCalledTimes(1);
  await act(async () => release({ ok: true, status: 200, json: async () => ({ deleted: 0 }) }));
});
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** to the interface. **Step 4: Run** — PASS; `npx tsc --noEmit`; `npx eslint .`.

- [ ] **Step 5: Commit** — `git commit -m "feat(web): Settings danger zone and account-deleted landing"`.

---

## Group E — verification and handoff

- [ ] **E1 Invariants:** `git diff 2de1d6c -- src/tradelens/services/metrics.py prompts/ requirements*.txt web/package.json web/package-lock.json alembic/versions` empty; `alembic heads` → `g3h4i5j6k7l8`; Streamlit leak check over `services/` and `api/` (every module, including `data_deletion`) → none; `tests/test_ai_system_message_sweep.py` still green (Settings adds no AI call site and must not import an AI entry point outside `services/` — `has_api_key` is not one).
- [ ] **E2 Deletion sweep:** one test reflects `db.models` and asserts that every table with a `user_id` column appears either in `account._OWNED_BY_USER`, in the per-trade deletes, or in `account.ANONYMISED` — so a table added later without a deletion decision fails the build.
- [ ] **E3 Contract drift:** regenerate from the **repo root**; `git status --porcelain --untracked-files=all` clean.
- [ ] **E4 Full gates** (Global Constraints). Record the Python result exactly, including the two known `test_pages_boot.py` failures; do not describe the suite as fully green unless it is.
- [ ] **E5 Mutation battery** — one harness, every mutation from Groups A–D, run from a clean HEAD. At minimum:
  - rows deleted before objects; blocked outcome still deletes rows; `remaining`/`unresolvable` swapped or merged; legacy local path outside the store treated as resolved; another owner's trade purged;
  - `auth_sessions` / `auth_handoffs` / `ai_jobs` dropped from `_OWNED_BY_USER`; summaries not deleted;
  - timezone allowlist removed; row cap removed; formula prefix list missing `=`; numeric column neutralised;
  - owner hardcoded to 1 in the router; `Literal` confirmation loosened to `str`; 503 detail forwarded with counts or keys by the relay; cookie cleared on a failed account deletion; oversized import forwarded; export `Content-Disposition` dropped;
  - confirmation compared against the raw typed text; double-click guard removed; unresolvable copy shown for a retryable failure; profile gains an email input.
  Report applied / caught / NOT-RUN / ERROR / survived with the catching test named; restore by sha256; clean before and after.
- [ ] **E6 Independent review** in a private `git archive` extraction of the phase tip, with a no-leftover proof. Focus: objects-before-rows under partial failure; every user-referencing table; typed confirmations; cross-owner isolation on every route; CSV injection and size bounds; cookie/sign-out ordering; S1–S9 as approved.
- [ ] **E7 Browser smoke** — attempt the Settings page at desktop and true 375px only if an authenticated dev session exists; otherwise record it as not run. Never claim it.
- [ ] **E8 Handoff:** a Phase 9 section with S1–S9 as approved, the three service defects fixed (R2 objects on bulk and account deletion; session/handoff rows; timezone validation) and where each is pinned, the mutation table, verification numbers recorded exactly, and the carried-forward hard gates unchanged — real PostgreSQL concurrency (now including account deletion against the non-cascading foreign keys), authenticated desktop + true 375px smoke, Docker build/startup/health, live Anthropic adversarial smoke, dependency audit, live R2/browser verification (now including bulk and account-deletion object cleanup); the narrow in-flight Streamlit race until Phase 10; the two `test_pages_boot.py` failures; the lexical Partner output guard as defense-in-depth, not a semantic guarantee.

Commit `docs(handoff): Phase 9 record`. **Do not merge**; report and wait for review. Do not begin Phase 10.
