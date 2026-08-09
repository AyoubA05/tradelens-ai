# Dark Workspace Priority Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve every Priority 1–3 finding from the final dark-workspace visual review, restore one coherent demo story across all pages, and produce clean product-only evidence for a fresh 10K Website Checklist re-score.

**Architecture:** Keep the fixed Python/Streamlit architecture and make the synthetic demo dataset the single source of truth for demo dates, Journal rows, Strategy Profile state, and AI Review date choices. Put reusable presentation transformations in small Streamlit-free component modules, preserve all database and AI safety boundaries, then recapture the product with the existing CDP screenshot harness after the behavior is verified. Execute sequentially under the existing one-writer handoff because the tasks overlap shared demo, shell, and page modules.

**Tech Stack:** Python 3.9-compatible syntax, Streamlit 1.50.0, Pandas, Plotly 6.7.0, SQLAlchemy/SQLite, pytest, Ruff, Black, Chrome DevTools Protocol, Pillow already present in the repository.

## Global Constraints

- Work only in `/Users/ayoub/tradelens-ai/.claude/worktrees/codex+full-dark-streamlit-redesign` on branch `codex/full-dark-streamlit-redesign`.
- Read and update `docs/coordination/CLAUDE_CODEX_HANDOFF.md`; claim the writer lock before source changes and release it to `NONE` after the final verified commit.
- Preserve the approved fully dark direction and all Phase 2–4 accessibility, privacy, security, responsive, and reduced-motion behavior.
- Preserve TradeLens as a completed-trade journal and post-trade reflection product. Do not add predictive, recommendation, or execution-oriented copy.
- Do not modify AI routing, system prompts, `services/ai_client.py`, authentication, database models, migrations, tenant isolation, secret management, or the marketing layout.
- Do not add React, JavaScript injection, Tailwind, TypeScript, animation libraries, or any new dependency.
- Use semantic roles from `src/tradelens/ui/design_system.py`; do not add raw color values in page or component code.
- Keep unsafe HTML disabled for user- or model-controlled content. Authored HTML must escape dynamic values.
- Do not weaken Phase 2–4 tests. When a prior contract describes superseded behavior, replace it with a stronger property test and document why.
- Preserve the five-step New Trade workflow, Journal row selection and detail behavior, Analytics filters and lenses, Strategy Profile persistence, destructive-action protections, and the existing safe AI Partner send path.
- Run tests with `/Users/ayoub/tradelens-ai/.venv/bin/python` and use the same interpreter for Ruff and Black.
- Do not push, merge, deploy, or finish the branch as part of this plan.

## Priority Coverage

| Priority | Finding | Implemented by |
|---|---|---|
| P1 | Demo dates extend beyond the viewing date and pages disagree about the same sample account | Tasks 1, 4, and 5 |
| P1 | Ownerless preview shows a dead AI Partner control and incorrect sign-in copy | Task 3 |
| P1 | Demo Journal exposes database-shaped values instead of the polished ledger presentation | Task 2 |
| P2 | Product evidence includes browser/Codex overlays and does not cover all destinations | Task 7 |
| P2 | Daily/Weekly review recovery is weak and Strategy onboarding is an open wall of fields | Tasks 4 and 5 |
| P3 | Structural emoji and inconsistent killzone/session terminology remain | Task 6 |

## File Structure

### New files

- `src/tradelens/ui/components/strategy_profile.py` — pure starter-profile fixture and completion helpers shared by Strategy, sidebar, demo previews, and screenshot seeding.
- `src/tradelens/ui/components/review_dates.py` — pure dated-review option and demo-row adapters for Daily Debrief and Weekly Recap.
- `docs/superpowers/audits/2026-08-09-priority-remediation-review.md` — final evidence, remaining limitations, and 10K re-score.
- `docs/superpowers/audits/assets/2026-08-09/` — clean product-only desktop and phone captures for every authenticated destination and AI Partner presentation.

### Existing files modified

- `src/tradelens/services/demo.py` — anchor 60 deterministic demo trades to an explicit `as_of` date.
- `src/tradelens/ui/components/ledger.py` — centralize result, money, R-multiple, session, and setup presentation for real and demo ledger rows.
- `src/tradelens/ui/pages/2_Trades.py` — render the demo Journal through the shared ledger transformation.
- `src/tradelens/ui/components/partner_turn.py` — add an explicit ownerless-preview availability state without changing the send-path owner guard.
- `src/tradelens/ui/components/partner_panel.py` — remove the dead ownerless launcher and duplicated unavailable presentation.
- `src/tradelens/ui/components/sidebar.py` — show the demo Strategy fixture rather than an empty account contradiction.
- `src/tradelens/ui/pages/5_Strategy.py` — use the shared fixture, render a truthful read-only demo profile, and collapse manual onboarding behind one deliberate route.
- `src/tradelens/ui/pages/6_Insights.py` — choose only dates/weeks containing demo trades and build demo debrief rows from the same frame.
- `src/tradelens/ui/app.py` — use killzone terminology for the ranked performance section.
- `src/tradelens/ui/components/corrections_sidebar.py`, `src/tradelens/ui/components/ai_review.py`, `src/tradelens/ui/components/screenshot_analyzer.py`, and `src/tradelens/ui/pages/5_Strategy.py` — replace remaining structural emoji with supported Material icons or plain text.
- `scripts/capture_app_screenshots.py` — add complete audit capture coverage and product-only verification assertions.
- `site/assets/` — replace only the four existing marketing product stills with clean recaptures; do not redesign the marketing site.
- Relevant test modules named in each task.
- `docs/coordination/CLAUDE_CODEX_HANDOFF.md` — writer lock, task evidence, final state, and unresolved deployment-only action.

---

### Task 1: Establish One Time-Bounded Demo Dataset and Shared Strategy Fixture

**Files:**
- Modify: `src/tradelens/services/demo.py`
- Create: `src/tradelens/ui/components/strategy_profile.py`
- Modify: `src/tradelens/ui/pages/5_Strategy.py`
- Modify: `scripts/capture_app_screenshots.py`
- Test: `tests/test_demo.py`
- Test: `tests/test_page_polish.py`
- Test: `tests/test_premium_page_contracts.py`

**Interfaces:**
- Consumes: existing `get_demo_df()`, `STARTER_TEMPLATE`, and `PLAYBOOK_SECTIONS` behavior.
- Produces: `get_demo_df(*, as_of: Optional[datetime.date] = None) -> pandas.DataFrame`, `STARTER_TEMPLATE: Mapping[str, str]`, `demo_strategy_profile() -> dict[str, str]`, and `profile_completion(profile: Mapping[str, object]) -> tuple[int, int]`.

- [ ] **Step 1: Claim the writer lock and record the execution baseline**

Edit the state block in `docs/coordination/CLAUDE_CODEX_HANDOFF.md` to:

```markdown
**Active writer:** CODEX
**Phase:** PRIORITY REMEDIATION — TASK 1
**Next owner:** CODEX
**Next action:** Implement `docs/superpowers/plans/2026-08-09-dark-workspace-priority-remediation.md` sequentially.
```

Run:

```bash
cd /Users/ayoub/tradelens-ai/.claude/worktrees/codex+full-dark-streamlit-redesign
git status --short --branch
git rev-parse --abbrev-ref HEAD
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest tests/test_demo.py tests/test_page_polish.py -q
```

Expected: branch is `codex/full-dark-streamlit-redesign`; the only pre-existing untracked path may be the explicitly ignored Impeccable cache; focused tests pass before changes.

- [ ] **Step 2: Write failing time-bound demo tests**

Add to `tests/test_demo.py`:

```python
import datetime as dt


def test_demo_rows_never_extend_beyond_the_supplied_view_date():
    from src.tradelens.services.demo import get_demo_df

    frame = get_demo_df(as_of=dt.date(2026, 8, 8))
    dates = frame["trade_date"].map(dt.date.fromisoformat)

    assert len(frame) == 60
    assert dates.max() <= dt.date(2026, 8, 8)
    assert all(day.weekday() < 5 for day in dates)


def test_demo_rows_are_deterministic_for_one_anchor():
    from src.tradelens.services.demo import get_demo_df

    left = get_demo_df(as_of=dt.date(2026, 8, 8))
    right = get_demo_df(as_of=dt.date(2026, 8, 8))

    assert left.to_dict("records") == right.to_dict("records")
    assert left.iloc[-1]["trade_date"] == "2026-08-07"
```

Run:

```bash
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest tests/test_demo.py::test_demo_rows_never_extend_beyond_the_supplied_view_date tests/test_demo.py::test_demo_rows_are_deterministic_for_one_anchor -q
```

Expected: FAIL because `get_demo_df` does not accept `as_of` and the current fixed series reaches 2026-08-24.

- [ ] **Step 3: Implement deterministic weekday generation ending at the anchor**

In `src/tradelens/services/demo.py`, add the public count and private date builder, then change the existing loop to consume the returned dates:

```python
DEMO_TRADE_COUNT = 60


def _demo_dates(
    *, as_of: dt.date, count: int = DEMO_TRADE_COUNT
) -> tuple[dt.date, ...]:
    dates = []
    cursor = as_of
    while len(dates) < count:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= dt.timedelta(days=1)
    return tuple(reversed(dates))


def get_demo_df(*, as_of: Optional[dt.date] = None):
    """Return 60 deterministic completed trades ending no later than `as_of`."""
    import pandas as pd

    anchor = as_of or dt.date.today()
    dates = _demo_dates(as_of=anchor)
    rows = []
    for i, day in enumerate(dates):
        a = (i * 37) % 100
        b = (i * 53) % 100
        result = "Win" if a < 55 else ("Loss" if a < 90 else "Breakeven")
        if result == "Win":
            pnl = round(120 + (b % 9) * 45, 2)
            rr = round(1.5 + (b % 5) * 0.5, 2)
        elif result == "Loss":
            pnl = round(-(80 + (b % 6) * 30), 2)
            rr = -1.0
        else:
            pnl, rr = 0.0, 0.0

        followed = 0 if (i % 5 == 0) else 1
        mistakes = [] if followed else [_MISTAKES[i % len(_MISTAKES)]]
        grade = _GRADES[i % len(_GRADES)]

        rows.append(
            _demo_row(
                i=i,
                day=day,
                a=a,
                pnl=pnl,
                rr=rr,
                result=result,
                followed=followed,
                mistakes=mistakes,
                grade=grade,
            )
        )
    return pd.DataFrame(rows)
```

Define the helper immediately above `get_demo_df` so the row schema remains explicit and testable:

```python
def _demo_row(
    *,
    i: int,
    day: dt.date,
    a: int,
    pnl: float,
    rr: float,
    result: str,
    followed: int,
    mistakes: list[str],
    grade: str,
) -> dict[str, object]:
    return {
        "id": i + 1,
        "trade_date": day.isoformat(),
        "day_of_week": _DOW[day.weekday()],
        "asset": _ASSETS[i % len(_ASSETS)],
        "asset_class": "Futures",
        "session": ["London", "NY AM", "NY PM", "Asia"][i % 4],
        "timeframe": ["5m", "15m", "1H"][i % 3],
        "strategy_used": "ICT OB Strategy",
        "setup_type": _SETUPS[i % len(_SETUPS)],
        "direction": "Long" if i % 2 == 0 else "Short",
        "entry_price": round(100 + a * 0.5, 2),
        "exit_price": round(100 + a * 0.5 + (pnl / 10.0), 2),
        "pnl": pnl,
        "result": result,
        "rr_realized": rr,
        "ai_grade": grade,
        "user_grade": grade if i % 3 else None,
        "killzone": _KILLZONES[i % len(_KILLZONES)],
        "htf_bias": ["bullish", "bearish", "neutral"][i % 3],
        "liquidity_sweep": i % 2,
        "fvg_used": (i + 1) % 2,
        "order_block_used": i % 2,
        "bos": (i + 1) % 2,
        "choch": i % 3 == 0,
        "confirmation_model": _CONFIRMATIONS[i % len(_CONFIRMATIONS)],
        "entry_type": _ENTRY_TYPES[i % len(_ENTRY_TYPES)],
        "mistake_tags": json.dumps(mistakes),
        "followed_rules": followed,
        "emotions_before": _EMOTIONS[i % len(_EMOTIONS)],
        "emotions_during": _EMOTIONS[(i + 1) % len(_EMOTIONS)],
        "emotions_after": _EMOTIONS[(i + 2) % len(_EMOTIONS)],
        "updated_at": f"{day.isoformat()}T12:00:00",
    }
```

Delete only the old fixed `start` declaration and the old `int(i * 1.4)` date loop. Preservation is verified by the deterministic record-equality test plus the existing all-columns/result-distribution tests. Python 3.9 compatibility requires `from __future__ import annotations`, which already exists.

- [ ] **Step 4: Write failing shared-strategy-fixture tests**

Add to `tests/test_page_polish.py`:

```python
def test_demo_strategy_fixture_is_complete_and_returns_a_fresh_copy():
    from src.tradelens.ui.components.strategy_profile import (
        demo_strategy_profile,
        profile_completion,
    )

    first = demo_strategy_profile()
    second = demo_strategy_profile()
    first["name"] = "Changed locally"

    assert second["name"] == "ICT/SMC Day Trading"
    assert profile_completion(second) == (6, 6)
```

Replace source-only assertions requiring `STARTER_TEMPLATE` to be declared inside `5_Strategy.py` with assertions that the page imports `STARTER_TEMPLATE`, `demo_strategy_profile`, and `profile_completion` from the pure component.

Run:

```bash
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest tests/test_page_polish.py -q
```

Expected: FAIL because `src/tradelens/ui/components/strategy_profile.py` does not exist.

- [ ] **Step 5: Create the pure strategy fixture module and consume it from Strategy**

Create `src/tradelens/ui/components/strategy_profile.py` with the existing complete starter values and pure completion logic:

```python
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping


STARTER_TEMPLATE = MappingProxyType(
    {
        "name": "ICT/SMC Day Trading",
        "trading_style": "ICT / SMC",
        "markets": "NQ, ES, EURUSD, GBP/USD",
        "timeframes": "15m entry, 1H/4H HTF",
        "entry_rules": (
            "Wait for HTF POI, confirm BOS or CHoCH on LTF, "
            "enter on FVG or OB retest"
        ),
        "stop_rules": "Place SL below/above the swing that caused the BOS",
        "take_profit_rules": "TP at next liquidity level or opposing HTF POI",
        "risk_rules": (
            "Max 1% per trade, max 2 trades per session, no revenge trading"
        ),
        "setups_traded": (
            "Liquidity Sweep + FVG, BOS + OB Retest, CHoCH Entry"
        ),
        "setups_avoided": (
            "Counter-trend without BOS, news candle entries, off-session trades"
        ),
        "common_mistakes": (
            "FOMO entry, moving SL, off-session trades, overtrading"
        ),
    }
)

SECTION_FIELDS = (
    ("name", "trading_style", "markets", "timeframes"),
    ("entry_rules",),
    ("stop_rules", "take_profit_rules"),
    ("risk_rules",),
    ("setups_traded", "setups_avoided"),
    ("common_mistakes",),
)


def demo_strategy_profile() -> dict[str, str]:
    return dict(STARTER_TEMPLATE)


def profile_completion(profile: Mapping[str, object]) -> tuple[int, int]:
    written = sum(
        any(str(profile.get(field) or "").strip() for field in fields)
        for fields in SECTION_FIELDS
    )
    return written, len(SECTION_FIELDS)
```

In `5_Strategy.py`, delete the local constant and `_profile_completion`, import the pure equivalents, and convert the immutable mapping to a dict only at the existing write boundary:

```python
from src.tradelens.ui.components.strategy_profile import (
    STARTER_TEMPLATE,
    demo_strategy_profile,
    profile_completion,
)

if _starter_clicked:
    if _write(_STARTER_ERROR_KEY, **dict(STARTER_TEMPLATE)):
        st.toast(
            "Starter playbook saved as your active profile.",
            icon=":material/check_circle:",
        )
        st.rerun()
```

Change `_render_profile_summary` to call `profile_completion(profile)`.

- [ ] **Step 6: Update the screenshot seed reader and verify Task 1**

Delete the AST extraction of `STARTER_TEMPLATE` from `scripts/capture_app_screenshots.py`. Import the pure fixture and seed from `demo_strategy_profile()`.

Run:

```bash
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest tests/test_demo.py tests/test_page_polish.py tests/test_premium_page_contracts.py -q
/Users/ayoub/tradelens-ai/.venv/bin/python -m ruff check src/tradelens/services/demo.py src/tradelens/ui/components/strategy_profile.py src/tradelens/ui/pages/5_Strategy.py scripts/capture_app_screenshots.py tests/test_demo.py tests/test_page_polish.py tests/test_premium_page_contracts.py
/Users/ayoub/tradelens-ai/.venv/bin/python -m black --check src/tradelens/services/demo.py src/tradelens/ui/components/strategy_profile.py src/tradelens/ui/pages/5_Strategy.py scripts/capture_app_screenshots.py tests/test_demo.py tests/test_page_polish.py tests/test_premium_page_contracts.py
```

Expected: all focused tests pass; Ruff and Black are clean.

- [ ] **Step 7: Commit Task 1**

```bash
git add src/tradelens/services/demo.py src/tradelens/ui/components/strategy_profile.py src/tradelens/ui/pages/5_Strategy.py scripts/capture_app_screenshots.py tests/test_demo.py tests/test_page_polish.py tests/test_premium_page_contracts.py docs/coordination/CLAUDE_CODEX_HANDOFF.md
git commit -m "fix(demo): bound sample data to one coherent account"
```

---

### Task 2: Give the Demo Journal the Real Ledger Presentation

**Files:**
- Modify: `src/tradelens/ui/components/ledger.py`
- Modify: `src/tradelens/ui/pages/2_Trades.py`
- Test: `tests/test_premium_page_contracts.py`
- Test: `tests/test_page_polish.py`

**Interfaces:**
- Consumes: `get_demo_df(*, as_of=None)` from Task 1 and existing `humanize` and ledger row styling.
- Produces: `demo_ledger_frame(frame: pandas.DataFrame) -> pandas.DataFrame`, `format_money(value: object) -> str`, and `LEDGER_MARKS: Mapping[str, str]` used by both real and demo Journal rows.

- [ ] **Step 1: Write failing ledger-presentation tests**

Add to `tests/test_premium_page_contracts.py`:

```python
def test_demo_ledger_uses_human_labels_and_financial_formats():
    from src.tradelens.services.demo import get_demo_df
    from src.tradelens.ui.components.ledger import demo_ledger_frame

    rendered = demo_ledger_frame(
        get_demo_df(as_of=__import__("datetime").date(2026, 8, 8))
    )

    assert list(rendered.columns) == [
        "Date",
        "Asset",
        "Direction",
        "Setup",
        "Session",
        "Result",
        "P&L",
        "R",
    ]
    assert rendered["Session"].str.contains("_").sum() == 0
    assert rendered["P&L"].map(
        lambda value: value.startswith(("$", "-$"))
    ).all()
    assert rendered["R"].str.endswith("R").all()
    assert rendered["Result"].str.startswith(("▲", "▼", "■")).all()
```

Add a source contract asserting the demo branch calls `demo_ledger_frame` and no longer defines `_DEMO_COLUMNS`.

Run:

```bash
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest tests/test_premium_page_contracts.py -q
```

Expected: FAIL because the shared frame builder does not exist.

- [ ] **Step 2: Centralize the ledger transformation**

Move the existing `_LEDGER_MARKS` and `_fmt_money` behavior from `2_Trades.py` into `components/ledger.py`. Implement the frame builder so it accepts the demo DataFrame and the DataFrame built from real ORM rows:

```python
from __future__ import annotations

import pandas as pd

from src.tradelens.utils.format import humanize


LEDGER_MARKS = {"Win": "▲", "Loss": "▼", "Breakeven": "■"}


def format_money(value: object) -> str:
    if value is None or pd.isna(value):
        return "—"
    amount = float(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def demo_ledger_frame(frame: pd.DataFrame) -> pd.DataFrame:
    source = frame.copy()
    session = source.get("session", source.get("killzone"))
    result = source["result"].fillna("").map(humanize)
    return pd.DataFrame(
        {
            "Date": source["trade_date"].fillna("—").astype(str),
            "Asset": source["asset"].fillna("—").astype(str),
            "Direction": source["direction"].fillna("—").map(humanize),
            "Setup": source["setup_type"].fillna("—").map(humanize),
            "Session": session.fillna("—").map(humanize),
            "Result": result.map(
                lambda value: f"{LEDGER_MARKS.get(value, '·')} {value or '—'}"
            ),
            "P&L": source["pnl"].map(format_money),
            "R": source["rr_realized"].map(
                lambda value: "—" if pd.isna(value) else f"{float(value):.2f}R"
            ),
        }
    )
```

If `humanize` lives under a different current import path, use the exact existing import from `2_Trades.py`; do not create a duplicate humanizer.

- [ ] **Step 3: Route both demo and real rows through the shared presentation**

In the empty demo branch of `2_Trades.py`:

```python
if not trades_all and is_demo():
    demo_ledger = demo_ledger_frame(get_demo_df())
    st.caption("Showing the same sample account used across TradeLens.")
    st.dataframe(
        demo_ledger.style.apply(ledger_row_styles, axis=1),
        hide_index=True,
        width="stretch",
    )
    st.stop()
```

For real rows, preserve the existing row-building and selection flow. Replace only page-local references to `_LEDGER_MARKS` and `_fmt_money` with the imported `LEDGER_MARKS` and `format_money`; this guarantees demo and real rows share the same result glyph and money formatter without restructuring the row-selection code. Preserve `ids`, row selection, `labels`, the `st.dataframe` key, and the Trade Detail transition exactly.

- [ ] **Step 4: Verify the Journal and commit**

Run:

```bash
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest tests/test_premium_page_contracts.py tests/test_page_polish.py tests/test_pages_boot.py -q
/Users/ayoub/tradelens-ai/.venv/bin/python -m ruff check src/tradelens/ui/components/ledger.py src/tradelens/ui/pages/2_Trades.py tests/test_premium_page_contracts.py tests/test_page_polish.py
/Users/ayoub/tradelens-ai/.venv/bin/python -m black --check src/tradelens/ui/components/ledger.py src/tradelens/ui/pages/2_Trades.py tests/test_premium_page_contracts.py tests/test_page_polish.py
git diff --check
```

Expected: demo and real ledger contracts pass; page boot tests pass; no raw underscore identifiers remain in rendered demo ledger values.

```bash
git add src/tradelens/ui/components/ledger.py src/tradelens/ui/pages/2_Trades.py tests/test_premium_page_contracts.py tests/test_page_polish.py
git commit -m "fix(journal): present demo trades as a real ledger"
```

---

### Task 3: Make AI Partner Availability Truthful in Ownerless Preview Sessions

**Files:**
- Modify: `src/tradelens/ui/components/partner_turn.py`
- Modify: `src/tradelens/ui/components/partner_panel.py`
- Test: `tests/test_partner_turn.py`
- Test: `tests/test_partner_panel.py`
- Test: `tests/test_pages_boot.py`

**Interfaces:**
- Consumes: existing `PartnerAvailability`, `partner_availability`, `render_partner_launcher`, and owner validation in `send_turn`.
- Produces: `OWNERLESS_PREVIEW`, `PartnerAvailability.show_launcher`, a hidden ownerless desktop launcher, and one truthful dedicated-page status message.

- [ ] **Step 1: Write failing ownerless-preview state tests**

Add to `tests/test_partner_turn.py`:

```python
def test_ownerless_preview_never_builds_context_or_offers_a_launcher(monkeypatch):
    from src.tradelens.ui.components import partner_turn

    calls = []
    monkeypatch.setattr(
        partner_turn,
        "build_global_partner_context",
        lambda **kwargs: calls.append(kwargs),
    )

    state = partner_turn.partner_availability(
        user_id=None,
        ai_ready=True,
        context=None,
        context_failed=False,
    )

    assert state.can_send is False
    assert state.show_launcher is False
    assert state.reason == partner_turn.OWNERLESS_PREVIEW
    assert calls == []
```

Use the exact current parameter names from `partner_availability`; the test property is fixed even if the current signature orders them differently.

Add to `tests/test_partner_panel.py`:

```python
def test_ownerless_preview_renders_no_dead_desktop_launcher(fake_streamlit):
    fake_streamlit.session_state["authenticated"] = True
    fake_streamlit.session_state["user_id"] = None

    render_partner_launcher(fake_streamlit)

    assert fake_streamlit.buttons == []
    assert "Ask about a trade" not in fake_streamlit.rendered_text
    assert "Sign in to use the AI Partner" not in fake_streamlit.rendered_text
```

Run the two tests and confirm they fail against current behavior.

- [ ] **Step 2: Add the explicit preview state without weakening the send guard**

In `partner_turn.py`:

```python
OWNERLESS_PREVIEW = "AI Partner is unavailable in this preview account."


@dataclass(frozen=True)
class PartnerAvailability:
    can_send: bool
    reason: str = ""
    show_launcher: bool = True
```

In `partner_availability`, return this state before context construction for a non-positive or non-integer owner:

```python
if not isinstance(user_id, int) or user_id <= 0:
    return PartnerAvailability(
        can_send=False,
        reason=OWNERLESS_PREVIEW,
        show_launcher=False,
    )
```

Keep the direct `send_turn` owner check and `NO_USER_ERROR` defense. This presentation correction must not authorize ownerless context access or model calls.

- [ ] **Step 3: Remove the redundant launcher presentation**

In `render_partner_launcher`, compute availability before creating the keyed launcher container:

```python
availability = _availability(st)
if not availability.show_launcher:
    return
if not availability.can_send:
    st.markdown(
        render_partner_status(availability.reason),
        unsafe_allow_html=True,
    )
    return
```

Render a real button only in the sendable state. Do not render both a disabled button and a caption carrying the same reason. On the dedicated phone Partner page, render `OWNERLESS_PREVIEW` once as a non-action status and no composer.

- [ ] **Step 4: Update boot contracts, verify, and commit**

Change the ownerless boot expectation in `tests/test_pages_boot.py` from the sign-in instruction to `AI Partner is unavailable in this preview account.` Add a negative assertion for the old copy.

Run:

```bash
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest tests/test_partner_turn.py tests/test_partner_panel.py tests/test_pages_boot.py -q
/Users/ayoub/tradelens-ai/.venv/bin/python -m ruff check src/tradelens/ui/components/partner_turn.py src/tradelens/ui/components/partner_panel.py tests/test_partner_turn.py tests/test_partner_panel.py tests/test_pages_boot.py
/Users/ayoub/tradelens-ai/.venv/bin/python -m black --check src/tradelens/ui/components/partner_turn.py src/tradelens/ui/components/partner_panel.py tests/test_partner_turn.py tests/test_partner_panel.py tests/test_pages_boot.py
git diff --check
```

Mutation-check by temporarily restoring the old ownerless state and confirm the new tests fail, then restore the correct implementation.

```bash
git add src/tradelens/ui/components/partner_turn.py src/tradelens/ui/components/partner_panel.py tests/test_partner_turn.py tests/test_partner_panel.py tests/test_pages_boot.py
git commit -m "fix(partner): make preview availability truthful"
```

---

### Task 4: Give Demo Strategy a Coherent Profile and Simplify Empty Onboarding

**Files:**
- Modify: `src/tradelens/ui/components/sidebar.py`
- Modify: `src/tradelens/ui/pages/5_Strategy.py`
- Test: `tests/test_page_polish.py`
- Test: `tests/test_premium_page_contracts.py`
- Test: `tests/test_pages_boot.py`

**Interfaces:**
- Consumes: `demo_strategy_profile()` and `profile_completion()` from Task 1; existing `get_active_strategy` and `_write` persistence path.
- Produces: one read-only demo playbook presentation, a truthful sidebar badge, and an empty-account onboarding flow with one primary starter action plus a collapsed manual route.

- [ ] **Step 1: Write failing demo-coherence and onboarding tests**

Add pure/source contracts:

```python
def test_strategy_page_uses_demo_profile_for_ownerless_demo_preview():
    source = STRATEGY_PAGE.read_text(encoding="utf-8")

    assert "demo_strategy_profile() if is_demo()" in source
    assert 'st.expander("Build a playbook manually"' in source
    assert "if demo_preview:" in source
    assert "Save playbook" in source


def test_sidebar_uses_the_same_demo_strategy_fixture():
    source = SIDEBAR_COMPONENT.read_text(encoding="utf-8")

    assert "demo_strategy_profile" in source
    assert "Sample strategy" in source
```

Add an AppTest boot that enables demo mode with `user_id=None` and asserts:

```python
assert "ICT/SMC Day Trading" in rendered_text
assert "6 of 6 sections written" in rendered_text
assert "No playbook yet" not in rendered_text
assert "Save playbook" not in rendered_button_labels
```

Run the focused tests and confirm failure.

- [ ] **Step 2: Use one profile decision on the Strategy page**

At page load:

```python
stored_profile = get_active_strategy(uid) if uid is not None else None
demo_preview = bool(is_demo() and stored_profile is None)
profile = demo_strategy_profile() if demo_preview else stored_profile
```

Render the summary from `profile or {}`. For `demo_preview`, add one quiet sentence:

```python
st.caption(
    "Sample playbook used by demo reviews. It is read-only in this preview."
)
```

Do not render the starter save control or editable form in the demo preview branch. This prevents a signed-in-looking ownerless preview from offering writes that cannot be tenant-scoped.

- [ ] **Step 3: Collapse manual onboarding only for a real empty account**

For a real owner with no saved profile:

- Keep `Apply the ICT/SMC starter playbook` as the single primary action.
- Change its help to `Saves this complete starter playbook as your active profile. You can edit every rule afterward.`
- Place the manual form under `st.expander("Build a playbook manually", expanded=False)`.
- For a saved profile, render the editable form directly so ordinary maintenance does not gain an extra click.

Use one context choice rather than duplicating the form:

```python
form_shell = (
    st.expander("Build a playbook manually", expanded=False)
    if profile is None
    else st.container()
)
with form_shell:
    with st.container(key="tl_playbook_form"), st.form("strategy_form"):
        render_strategy_fields(profile or {})
```

Extract the current field declarations into `render_strategy_fields` inside the same page; do not change field keys, validation, `_write`, toast timing, or destructive behavior.

- [ ] **Step 4: Make the sidebar agree with the page**

In `sidebar.py`, after the existing owner-scoped lookup:

```python
demo_profile = is_demo() and strategy is None
if demo_profile:
    strategy = demo_strategy_profile()
```

Render `Sample strategy: ICT/SMC Day Trading` when `demo_profile` is true. Render the existing active-strategy treatment for stored profiles. Continue to show no strategy badge when neither condition holds.

- [ ] **Step 5: Verify persistence and commit**

Run:

```bash
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest tests/test_page_polish.py tests/test_premium_page_contracts.py tests/test_pages_boot.py tests/test_strategy.py tests/test_strategy_parsing.py -q
/Users/ayoub/tradelens-ai/.venv/bin/python -m ruff check src/tradelens/ui/components/sidebar.py src/tradelens/ui/pages/5_Strategy.py tests/test_page_polish.py tests/test_premium_page_contracts.py tests/test_pages_boot.py
/Users/ayoub/tradelens-ai/.venv/bin/python -m black --check src/tradelens/ui/components/sidebar.py src/tradelens/ui/pages/5_Strategy.py tests/test_page_polish.py tests/test_premium_page_contracts.py tests/test_pages_boot.py
git diff --check
```

Expected: demo preview is complete and read-only; a real empty account has one primary action and one collapsed manual route; saved-profile persistence tests remain green.

```bash
git add src/tradelens/ui/components/sidebar.py src/tradelens/ui/pages/5_Strategy.py tests/test_page_polish.py tests/test_premium_page_contracts.py tests/test_pages_boot.py
git commit -m "fix(strategy): align demo truth and simplify onboarding"
```

---

### Task 5: Restrict AI Reviews to Dates and Weeks That Actually Contain Trades

**Files:**
- Create: `src/tradelens/ui/components/review_dates.py`
- Modify: `src/tradelens/ui/pages/6_Insights.py`
- Test: `tests/test_insights_page.py`
- Test: `tests/test_pages_boot.py`

**Interfaces:**
- Consumes: the time-bounded demo DataFrame from Task 1 and demo strategy fixture from Task 1.
- Produces: `review_day_options(frame: pandas.DataFrame) -> tuple[datetime.date, ...]`, `review_week_options(frame: pandas.DataFrame) -> tuple[datetime.date, ...]`, and `demo_rows_for_day(frame, day) -> list[types.SimpleNamespace]`.

- [ ] **Step 1: Write failing pure date-option tests**

Create tests in `tests/test_insights_page.py`:

```python
import datetime as dt

import pandas as pd


def test_review_options_only_include_periods_with_completed_trades():
    from src.tradelens.ui.components.review_dates import (
        review_day_options,
        review_week_options,
    )

    frame = pd.DataFrame(
        {"trade_date": ["2026-08-03", "2026-08-03", "2026-08-07", "2026-08-10"]}
    )

    assert review_day_options(frame) == (
        dt.date(2026, 8, 10),
        dt.date(2026, 8, 7),
        dt.date(2026, 8, 3),
    )
    assert review_week_options(frame) == (
        dt.date(2026, 8, 10),
        dt.date(2026, 8, 3),
    )


def test_demo_rows_for_day_preserve_fields_used_by_debrief():
    from src.tradelens.services.demo import get_demo_df
    from src.tradelens.ui.components.review_dates import demo_rows_for_day

    frame = get_demo_df(as_of=dt.date(2026, 8, 8))
    day = review_day_options(frame)[0]
    rows = demo_rows_for_day(frame, day)

    assert rows
    assert all(row.trade_date == day.isoformat() for row in rows)
    assert all(hasattr(row, "pnl") for row in rows)
```

Run and confirm import failure.

- [ ] **Step 2: Implement the pure review-date adapter**

Create `src/tradelens/ui/components/review_dates.py`:

```python
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pandas as pd


def review_day_options(frame: pd.DataFrame) -> tuple[dt.date, ...]:
    parsed = pd.to_datetime(frame.get("trade_date"), errors="coerce").dropna()
    return tuple(sorted(set(parsed.dt.date), reverse=True))


def review_week_options(frame: pd.DataFrame) -> tuple[dt.date, ...]:
    mondays = {
        day - dt.timedelta(days=day.weekday())
        for day in review_day_options(frame)
    }
    return tuple(sorted(mondays, reverse=True))


def demo_rows_for_day(
    frame: pd.DataFrame, day: dt.date
) -> list[SimpleNamespace]:
    day_iso = day.isoformat()
    selected = frame.loc[frame["trade_date"].astype(str) == day_iso]
    return [SimpleNamespace(**record) for record in selected.to_dict("records")]
```

- [ ] **Step 3: Make demo strategy and daily rows coherent**

In `6_Insights.py`, set `_strategy` to the demo fixture only when demo mode is active and no stored profile is available:

```python
_strategy = get_active_strategy(uid) if uid is not None else None
if is_demo() and _strategy is None:
    _strategy = demo_strategy_profile()
```

In `_render_daily_lens`, replace the unrestricted date input with a selectbox populated from `review_day_options(df)`:

```python
days = review_day_options(df)
if not days:
    _render_no_trades_state()
    return
day = st.selectbox(
    "Trading day to review",
    days,
    format_func=lambda value: value.strftime("%b %-d, %Y"),
    key="ins_dbf_day",
)
day_iso = day.isoformat()
day_trades = (
    demo_rows_for_day(df, day)
    if is_demo()
    else get_trades(start_date=day_iso, end_date=day_iso, user_id=uid)
)
```

Use a platform-safe formatter helper for Windows compatibility if required by existing tests; macOS/Linux capture can use `%-d`, but the preferred pure formatter is `f"{value:%b} {value.day}, {value:%Y}"`.

- [ ] **Step 4: Restrict Weekly Recap to populated weeks and add a recovery route**

Use `review_week_options(df)` and display each option as `Aug 3–9, 2026`. The selected value is already Monday, so call `week_bounds(monday)` without re-normalizing an arbitrary day.

When no options exist, render the existing empty-state component with:

- Heading: `No completed week to review`
- Body: `Log completed trades, then return here for a weekly recap.`
- One Journal route labeled `Open Journal →`

Keep the sample-size activation gate, saved-note reuse, regeneration containment, and existing-note preservation unchanged.

- [ ] **Step 5: Add AppTest coverage for demo recovery**

Add boot tests that select `Daily Debrief` and `Weekly Recap` in demo mode and assert:

```python
assert "No trades logged on this day" not in rendered_text
assert "This week has nothing logged to review" not in rendered_text
assert "ICT/SMC Day Trading" in captured_strategy_context
```

For a manually injected empty frame, assert `Open Journal →` is present and the model/generator spy has zero calls.

- [ ] **Step 6: Verify and commit Task 5**

Run:

```bash
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest tests/test_insights_page.py tests/test_pages_boot.py tests/test_ai_review.py -q
/Users/ayoub/tradelens-ai/.venv/bin/python -m ruff check src/tradelens/ui/components/review_dates.py src/tradelens/ui/pages/6_Insights.py tests/test_insights_page.py tests/test_pages_boot.py
/Users/ayoub/tradelens-ai/.venv/bin/python -m black --check src/tradelens/ui/components/review_dates.py src/tradelens/ui/pages/6_Insights.py tests/test_insights_page.py tests/test_pages_boot.py
git diff --check
```

Expected: every offered day/week contains at least one trade; demo daily rows come from the demo frame, not the database; AI error and regeneration tests remain green.

```bash
git add src/tradelens/ui/components/review_dates.py src/tradelens/ui/pages/6_Insights.py tests/test_insights_page.py tests/test_pages_boot.py
git commit -m "fix(reviews): offer only populated review periods"
```

---

### Task 6: Remove Structural Emoji and Standardize Killzone Terminology

**Files:**
- Modify: `src/tradelens/ui/app.py`
- Modify: `src/tradelens/ui/components/corrections_sidebar.py`
- Modify: `src/tradelens/ui/components/ai_review.py`
- Modify: `src/tradelens/ui/components/screenshot_analyzer.py`
- Modify: `src/tradelens/ui/pages/5_Strategy.py`
- Test: `tests/test_toast_icons.py`
- Test: `tests/test_premium_page_contracts.py`
- Test: `tests/test_overview_bands.py`

**Interfaces:**
- Consumes: Streamlit Material icon syntax already used by New Trade and Journal.
- Produces: one approved icon vocabulary and user-facing `Killzone performance` terminology wherever the ranked dimension is `killzone`.

- [ ] **Step 1: Write failing structural-icon and terminology contracts**

Extend `tests/test_toast_icons.py` so every live `st.toast(..., icon=...)` value must start with `:material/` and end with `:`. Exclude `_archive` pages explicitly because they are not routed product surfaces.

Add to `tests/test_premium_page_contracts.py`:

```python
def test_live_ui_uses_no_structural_emoji():
    live_sources = [
        path
        for path in UI_ROOT.rglob("*.py")
        if "_archive" not in path.parts
    ]
    forbidden = ("✅", "❌", "💡", "🧠", "➕", "🔍")

    failures = {
        str(path): [glyph for glyph in forbidden if glyph in path.read_text(encoding="utf-8")]
        for path in live_sources
    }
    assert {path: glyphs for path, glyphs in failures.items() if glyphs} == {}


def test_overview_names_the_dimension_it_ranks():
    source = APP_PAGE.read_text(encoding="utf-8")
    assert '"Session performance"' not in source
    assert '"Killzone performance"' in source
```

Keep the semantic ledger and calendar shape allowlist: `▲`, `▼`, `■`, filled circle, diamond, and hollow ring are information channels, not decorative emoji.

- [ ] **Step 2: Replace live structural emoji with Material names**

Use:

- `:material/check_circle:` for successful saves and completed analysis.
- `:material/error:` for an error toast only.
- `:material/lightbulb:` for correction guidance.
- `:material/add:` through the button `icon=` parameter for add actions.
- Plain copy without an icon where the symbol adds no meaning.

Do not place ligature names in Markdown labels; pass them through Streamlit's supported `icon=` parameter.

- [ ] **Step 3: Correct terminology and positive edge-leak explanation**

In `app.py`, rename the ranked heading and its unlocking copy:

```python
render_ranked_list(
    "Killzone performance",
    killzone_rows,
    empty_copy="Tag a killzone on completed trades to compare recurring windows.",
)
```

Keep the approved metric label `Edge leak`, but when rule-breaking trades are net-positive, retain the visible explanation that the amount is rule-break P&L and a warning rather than repeatable performance. Do not change the metric calculation or service interfaces.

Update `tests/test_overview_bands.py` expected headings accordingly.

- [ ] **Step 4: Verify and commit Task 6**

Run:

```bash
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest tests/test_toast_icons.py tests/test_premium_page_contracts.py tests/test_overview_bands.py tests/test_page_polish.py -q
/Users/ayoub/tradelens-ai/.venv/bin/python -m ruff check src/tradelens/ui tests/test_toast_icons.py tests/test_premium_page_contracts.py tests/test_overview_bands.py
/Users/ayoub/tradelens-ai/.venv/bin/python -m black --check src/tradelens/ui tests/test_toast_icons.py tests/test_premium_page_contracts.py tests/test_overview_bands.py
git diff --check
```

Expected: no structural emoji remain on live surfaces; every toast icon uses supported Material syntax; Overview ranks killzones under the correct name.

```bash
git add src/tradelens/ui/app.py src/tradelens/ui/components/corrections_sidebar.py src/tradelens/ui/components/ai_review.py src/tradelens/ui/components/screenshot_analyzer.py src/tradelens/ui/pages/5_Strategy.py tests/test_toast_icons.py tests/test_premium_page_contracts.py tests/test_overview_bands.py
git commit -m "fix(copy): align icons and trading terminology"
```

---

### Task 7: Capture Clean Product-Only Evidence for Every Destination

**Files:**
- Modify: `scripts/capture_app_screenshots.py`
- Create: `tests/test_capture_app_screenshots.py`
- Modify: `site/assets/shot-dashboard-wide.webp`
- Modify: `site/assets/shot-newtrade.webp`
- Modify: `site/assets/shot-analytics.webp`
- Modify: `site/assets/shot-strategy.webp`
- Create: `docs/superpowers/audits/assets/2026-08-09/*.png`

**Interfaces:**
- Consumes: verified app behavior from Tasks 1–6 and existing isolated SQLite/CDP capture helpers.
- Produces: `MARKETING_CAPTURES`, `AUDIT_CAPTURES`, `capture_marketing()`, and `capture_audit()` plus clean artifacts with no browser chrome, Codex overlays, or app-manager overlays.

- [ ] **Step 1: Write failing capture-manifest tests**

Create `tests/test_capture_app_screenshots.py`:

```python
from scripts.capture_app_screenshots import AUDIT_CAPTURES, MARKETING_CAPTURES


def test_audit_manifest_covers_every_destination_and_partner_presentation():
    names = {capture.name for capture in AUDIT_CAPTURES}
    assert names == {
        "overview-desktop",
        "new-trade-desktop",
        "journal-desktop",
        "analytics-desktop",
        "ai-reviews-desktop",
        "strategy-desktop",
        "settings-desktop",
        "partner-drawer-desktop",
        "partner-page-phone",
    }


def test_marketing_manifest_preserves_the_four_existing_asset_paths():
    paths = {capture.output.as_posix() for capture in MARKETING_CAPTURES}
    assert paths == {
        "site/assets/shot-dashboard-wide.webp",
        "site/assets/shot-newtrade.webp",
        "site/assets/shot-analytics.webp",
        "site/assets/shot-strategy.webp",
    }


def test_audit_captures_never_write_into_the_marketing_site():
    assert all("site/assets" not in capture.output.as_posix() for capture in AUDIT_CAPTURES)
```

Run and confirm failure because the two manifests do not exist.

- [ ] **Step 2: Add typed capture manifests and CLI modes**

Use a frozen dataclass:

```python
@dataclass(frozen=True)
class CaptureSpec:
    name: str
    route: str
    output: Path
    width: int
    height: int
    coarse_pointer: bool = False
    open_partner: bool = False
```

Define four marketing captures at their existing dimensions and nine audit captures under `docs/superpowers/audits/assets/2026-08-09/`. Add `--marketing`, `--audit`, and `--all` mutually exclusive CLI modes; default to `--all` only when invoked intentionally from this plan.

- [ ] **Step 3: Make the browser assertions part of capture success**

Before writing each file, evaluate and assert:

```javascript
(() => ({
  overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  exceptionCount: document.querySelectorAll('[data-testid="stException"]').length,
  coarse: matchMedia('(pointer: coarse)').matches,
  reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
  text: document.body.innerText,
}))()
```

Require:

- `overflow <= 0`
- `exceptionCount == 0`
- coarse-pointer result equals the manifest expectation
- body text does not contain `Sign in to use the AI Partner`
- body text does not contain a date later than the fixed seeded capture anchor

Use CDP `Page.captureScreenshot` so browser chrome, Codex input bars, and operating-system UI cannot enter the image.

- [ ] **Step 4: Add a real desktop Partner opening action**

Do not call JavaScript `.click()`. Resolve the button's box with CDP and dispatch a physical pointer sequence through `Input.dispatchMouseEvent` at the center:

```python
def click_center(tab, selector: str) -> None:
    box = tab.box_model(selector)
    x = (box[0] + box[2] + box[4] + box[6]) / 4
    y = (box[1] + box[3] + box[5] + box[7]) / 4
    tab.mouse("mouseMoved", x=x, y=y)
    tab.mouse("mousePressed", x=x, y=y, button="left", click_count=1)
    tab.mouse("mouseReleased", x=x, y=y, button="left", click_count=1)
```

Use the actual selector already emitted by the keyed Partner launcher. Wait for the drawer heading and confirm exactly one Partner presentation before capture.

- [ ] **Step 5: Verify genuine coarse emulation**

For 375px phone capture, use `Emulation.setDeviceMetricsOverride` with `mobile=True`, enable touch emulation, and assert `(pointer: coarse)` from inside the page. Do not describe it as physical-device evidence in the report.

- [ ] **Step 6: Generate and inspect the artifacts**

Run:

```bash
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest tests/test_capture_app_screenshots.py tests/test_capture_cleanup.py -q
/Users/ayoub/tradelens-ai/.venv/bin/python scripts/capture_app_screenshots.py --all
```

Inspect all thirteen outputs. Confirm:

- only the TradeLens viewport is present;
- no Codex composer or browser controls are present;
- the demo date range ends at or before the capture anchor;
- Journal uses human labels and formatted money;
- AI Partner ownerless clutter is absent;
- Strategy and sidebar show the same sample playbook;
- Daily and Weekly selectors default to populated periods;
- the four marketing WebPs still match the dimensions declared in `site/index.html`.

- [ ] **Step 7: Commit Task 7**

```bash
git add scripts/capture_app_screenshots.py tests/test_capture_app_screenshots.py site/assets/shot-dashboard-wide.webp site/assets/shot-newtrade.webp site/assets/shot-analytics.webp site/assets/shot-strategy.webp docs/superpowers/audits/assets/2026-08-09
git commit -m "docs(product): recapture clean dark workspace evidence"
```

---

### Task 8: Run the Full Quality Gate, Re-score the 10K Checklist, and Release the Handoff

**Files:**
- Create: `docs/superpowers/audits/2026-08-09-priority-remediation-review.md`
- Modify: `docs/coordination/CLAUDE_CODEX_HANDOFF.md`

**Interfaces:**
- Consumes: all Task 1–7 behavior and screenshot evidence.
- Produces: final test/browser evidence, an honest eight-item 10K re-score, exact remaining limitations, and a released writer lock.

- [ ] **Step 1: Run the full automated gate from a quiet environment**

Stop any capture-only Streamlit and Chrome processes started by Task 7, then run:

```bash
cd /Users/ayoub/tradelens-ai/.claude/worktrees/codex+full-dark-streamlit-redesign
/Users/ayoub/tradelens-ai/.venv/bin/python -m pytest -q
/Users/ayoub/tradelens-ai/.venv/bin/python -m ruff check .
/Users/ayoub/tradelens-ai/.venv/bin/python -m black --check .
git diff --check
```

Expected: the test count is at least the approved Phase 4 baseline of 2129 passed and 7 skipped plus the new tests; Ruff, Black, and `git diff --check` are clean.

- [ ] **Step 2: Run the complete browser matrix**

Verify all seven authenticated destinations plus the desktop Partner drawer and phone Partner page at:

- 1440px desktop
- 1024px tablet
- 768px genuine coarse-pointer emulation
- 375px genuine coarse-pointer phone emulation
- 1440px reduced-motion

At every configuration record:

- rendered exceptions: 0
- horizontal overflow: 0
- visible interactive targets below 44px: 0
- stale light surfaces: 0
- contradictory demo states: 0
- dates later than the capture anchor: 0
- old ownerless Partner sign-in copy: 0
- raw underscore identifiers in visible Journal labels: 0
- structural emoji in live controls or toasts: 0

Walk keyboard navigation with actual Tab and Shift+Tab dispatch on Overview, Journal, AI Reviews, Strategy, and the Partner drawer. Do not use `element.focus()` as evidence for `:focus-visible`.

- [ ] **Step 3: Write the final audit and 10K re-score**

Create `docs/superpowers/audits/2026-08-09-priority-remediation-review.md` with these sections:

```markdown
# Dark Workspace Priority Remediation Review

## Scope and reviewed commits
## Before / after priority table
## Automated verification
## Browser matrix
## Accessibility evidence
## Demo coherence evidence
## Clean screenshot inventory
## 10K Website Checklist re-score
## Remaining limitations
## Exact Git state
```

Re-score all eight original checklist categories against observed evidence. Do not pre-award imagery points merely because screenshots were created; score the composition, crop, legibility, relevance, and production cleanliness of the new assets. Link every scored claim to a capture or test.

Carry forward any unresolved framework limitation honestly, including Streamlit dataframe `aria-sort` and toolbar accessible-name limitations if they remain. Do not expand this task into a JavaScript injection or authored-table rewrite.

- [ ] **Step 4: Verify protected boundaries**

Run:

```bash
git diff 63421f7 -- src/tradelens/services/ai_client.py src/tradelens/services/partner.py src/tradelens/db src/tradelens/ui/components/auth.py alembic .streamlit/config.toml
```

Expected: no changes in AI routing, Partner safety service, schema, authentication, migrations, or secret/config management. If any output appears, stop and remove the out-of-scope change before continuing.

- [ ] **Step 5: Update and release the handoff**

Set the handoff state to:

```markdown
**Active writer:** NONE
**Phase:** PRIORITY REMEDIATION COMPLETE — AWAITING OWNER REVIEW
**Next owner:** OWNER
**Next action:** Review the final audit and decide whether to finish, push, or deploy the branch.
```

Record:

- every task commit;
- the final test count;
- Ruff, Black, and diff-check results;
- browser matrix result;
- screenshot inventory;
- exact unresolved limitations;
- confirmation that nothing was pushed, merged, or deployed;
- the owner-only Streamlit Cloud secrets check carried forward from Phase 4.

- [ ] **Step 6: Commit the final audit and handoff**

```bash
git add docs/superpowers/audits/2026-08-09-priority-remediation-review.md docs/coordination/CLAUDE_CODEX_HANDOFF.md
git commit -m "docs(review): close dark workspace priority remediation"
git status --short --branch
```

Expected: branch remains `codex/full-dark-streamlit-redesign`; writer lock is `NONE`; the working tree is clean except any explicitly ignored machine cache; nothing is pushed, merged, or deployed.

## Plan Self-Review

### Spec coverage

- P1 demo time boundary: Task 1.
- P1 same account across Overview, Journal, Analytics, AI Reviews, Strategy, and sidebar: Tasks 1, 2, 4, and 5.
- P1 ownerless AI Partner presentation: Task 3.
- P1 Journal presentation parity: Task 2.
- P2 Daily/Weekly recovery and Strategy onboarding: Tasks 4 and 5.
- P2 clean imagery and full destination coverage: Task 7.
- P3 icon and terminology cleanup: Task 6.
- Full regression, responsive, keyboard, reduced-motion, protected-boundary, and 10K evidence: Task 8.

### Dependency and type consistency

- `get_demo_df` keeps its no-argument compatibility while adding the keyword-only `as_of` test seam.
- `demo_strategy_profile` always returns a mutable fresh copy; `STARTER_TEMPLATE` remains immutable.
- `demo_ledger_frame` accepts the canonical DataFrame shape emitted by `get_demo_df`; real rows reuse its exported glyph and money-format primitives without changing selection behavior.
- `review_day_options`, `review_week_options`, and `demo_rows_for_day` are Streamlit-free and safe to import in tests.
- `PartnerAvailability.show_launcher` defaults to `True`, preserving all existing constructed states until the ownerless branch opts out.
- Screenshot manifests separate marketing assets from audit evidence, so audit work cannot overwrite site images accidentally.

### Scope discipline

- No database or migration work.
- No authentication change.
- No AI service, routing, prompt, or safety change.
- No new dependency or JavaScript injection.
- No marketing redesign; only existing product stills are replaced.
- No branch finishing, push, merge, or deploy action.
