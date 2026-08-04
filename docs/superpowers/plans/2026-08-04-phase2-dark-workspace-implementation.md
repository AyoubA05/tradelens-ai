# TradeLens Phase 2 — Dark Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the authenticated TradeLens product from its light-workspace hybrid into one tonal-dark workspace, recompose the Overview into five distinct bands, turn AI Reviews into evidence-backed research notes, and add a global post-trade AI Partner — without changing product behaviour, AI safety boundaries, tenancy, persistence, or database schema.

**Architecture:** Retarget the shared token layer first so every later task consumes tokens rather than literals, then migrate the shell, then the controls, then each page. Three service additions are Codex-owned and land in one reviewed commit before the surfaces that consume them. The AI Partner reuses the existing `partner_reply` service through one Codex-authored context adapter; the UI owns only presentation. One pure Markdown document model makes long AI notes navigable without touching how they are generated.

**Tech Stack:** Streamlit 1.50.0, Plotly, Pandas, SQLAlchemy 2.x, pytest 8.4.2, Streamlit AppTest (`streamlit.testing.v1`), Ruff 0.15.16, Black 25.1.0, headless Chrome over CDP for browser verification.

## Toolchain

The redesign worktree has **no `.venv` of its own**. Every command in this plan runs from the canonical worktree against the interpreter in the main checkout. Export this once per shell before running anything:

```bash
export PY=/Users/ayoub/tradelens-ai/.venv/bin/python
cd /Users/ayoub/tradelens-ai/.claude/worktrees/codex+full-dark-streamlit-redesign
"$PY" -V && "$PY" -m pytest --version && "$PY" -m ruff --version && "$PY" -m black --version
```

Verified 2026-08-04 from the canonical worktree: `Python 3.9.6`, `pytest 8.4.2`, `ruff 0.15.16`, `black 25.1.0`, `streamlit 1.50.0`. `"$PY" -m pytest tests/test_data_state.py -q` → `17 passed`.

Ruff and Black are invoked as `"$PY" -m ruff` / `"$PY" -m black`, not as bare binaries, so a stray `ruff` on `PATH` cannot be used by accident.

> **The interpreter is Python 3.9.6, not 3.11.** `CLAUDE.md` names 3.11; the environment that produced the `1618 passed` baseline is 3.9.6, and that is the one these commands use. The consequence binds every task: **every new module in this plan must open with `from __future__ import annotations`**, because PEP 604 unions (`str | None`) and builtin generics in annotations are otherwise a runtime `TypeError` on 3.9. `app.py:1` and `workspace.py` already carry it for exactly this reason; `metrics.py` does not, which is why Task 4 uses `typing.Optional` there rather than `| None`.

**Sources this plan is built from — read all three before Task 1:**

- `docs/superpowers/specs/2026-08-03-phase1-dark-ux-specification.md` — the design source of truth (1332 lines). Section references below (§4.1, §5.3, …) point into it.
- `docs/superpowers/audits/2026-08-03-browser-preflight.md` — live browser evidence. Its findings override any source-only assumption.
- `docs/coordination/CLAUDE_CODEX_HANDOFF.md` — the two-writer coordination contract, ownership boundaries, and the Codex engineering rulings.

This plan **supersedes** `docs/superpowers/plans/2026-07-31-streamlit-dark-workspace-ai-review.md`. That plan's direction survives inside the spec; its task list does not.

---

## Global Constraints

Every task's requirements implicitly include this section.

- **Baseline to preserve:** `1618 passed, 7 skipped`; Ruff clean; Black clean (174 files); `git diff --check` clean. Every task ends at or above this count.
- One fixed tonal-dark theme. No theme switcher. Not one flat black surface — canvas, rail, panel, elevated, chart stage, and field stay distinct roles.
- Every destination survives: Overview, New Trade, Journal, Analytics, AI Reviews, Strategy Profile, Settings, authentication and recovery, import/export, sample data, destructive confirmations.
- Never `unsafe_allow_html=True` for model output. Generated prose goes through `st.markdown` with HTML disabled. Authored HTML escapes every interpolated value.
- **No Streamlit import inside `services/` or `db/`.** All business logic lives in `services/`; pages render and call services.
- **Claude writes no service code.** `services/ai_client.py`, `services/partner.py`, `services/metrics.py`, and every auth/database/cost/tenant/secret module are Codex-owned. Task 4 is Codex's.
- No React, FastAPI, **no JavaScript injection**, no new CSS framework, no new icon library, no new runtime dependency.
- No database migration, no schema change, no persisted conversation history, no new AI endpoint, prompt, or model-routing change.
- All colour, type, space, radius, shadow, motion, and z-index values live in `src/tradelens/ui/design_system.py`. Page modules consume tokens; pages never declare colour literals and never declare a raw `z-index`.
- Red = losses, destructive actions, errors. Green = profit or confirmed success. Teal = action and focus. Process measures (rule adherence, consistency) may **not** use red/green. Colour is never the sole carrier of meaning.
- All visible interactive targets ≥ 44×44 CSS px at 1440, 1024, coarse 768, and coarse 375, with ≥ 8 px between adjacent targets.
- Honour `prefers-reduced-motion: reduce`. Motion is opacity/transform only, 120–200 ms, shared ease-out. Never animate charts, long tables, validation, focus, or page load.
- AI stays post-trade, reflective, evidence-backed. No signals, predictions, entries, position instructions, or financial advice — including in UI copy, suggested questions, empty states, and accessible names.
- Keep exception containment: domain errors show trader-safe copy; anything else is logged and replaced with fixed recovery copy. No DSN, SQL, driver, key, or stack text reaches the UI.
- Tenant scoping on every service call. Every query receives the authenticated `user_id`.
- One local commit per task. **No push, merge, PR, or deploy** until the owner explicitly approves.
- Do not run `git add -A`. Stage only explicitly reviewed paths. Leave the untracked `src/tradelens/ui/.impeccable/` alone.

---

## Coordination and review gates

This plan runs inside the two-writer contract in `docs/coordination/CLAUDE_CODEX_HANDOFF.md`.

1. Before each task: read the handoff, run `git status --short`, and do not begin if `Active writer` names the other tool.
2. The incoming owner sets `Active writer` to its own name before editing.
3. At each task's commit: update `Current handoff state` with owner, phase, files changed, tests and browser checks, unresolved risks, exact commit, next owner, next action. Set `Active writer: NONE` before asking for review.
4. **Codex review gate after every task.** Provide: changed files, focused and full test results, browser evidence where the task requires it, security findings, intentional deviations, the local commit hash, and unresolved concerns. Codex reviews the diff, not the prose.
5. Task 4 is executed by Codex. Tasks 1–3 and 5–17 are executed by Claude.

**Task ownership at a glance**

| Task | Owner | Blocks |
|---|---|---|
| 1 Token contract | Claude | everything |
| 2 Shell | Claude | 3–17 |
| 3 Controls | Claude | 5–13 |
| 4 Service additions | **Codex** | 5, 14, 15 |
| 5–7 Overview | Claude | 17 |
| 8 New Trade | Claude | 17 |
| 9 Journal | Claude | 17 |
| 10 Analytics | Claude | 17 |
| 11 Review document model | Claude | 12 |
| 12 AI Reviews | Claude | 17 |
| 13 Strategy + Settings | Claude | 17 |
| 14 Partner drawer | Claude | 15 |
| 15 Partner mobile page | Claude | 16 |
| 16 Accessibility + security audit | Claude, reviewed by Codex | 17 |
| 17 Evidence + 10K re-score | Claude | — |

---

## What the browser preflight already changed

Three live findings override earlier source-only reasoning. They are folded into the tasks below; they are restated here so no task re-derives them.

1. **Partner breakpoints.** At coarse 768 the bottom navigation does **not** render — Streamlit uses its collapsed-sidebar control. The Partner drawer therefore applies at **every sidebar-navigation width (≥768)**, and the full-page `More` destination applies only where bottom navigation actually exists (**≤767**). Spec §1.3, §8.2a, §11, §15.2 C5.
2. **Streamlit dataframe toolbar targets fail.** The four toolbar controls (`Show/hide columns`, `Download as CSV`, `Search`, `Fullscreen`) measure ≈22.4×22.4 CSS px at 1440. Task 9 corrects or replaces them.
3. **Nested-route console 404s** for relative `_stcore` health/host-config requests under `/NewTrade/…` are pre-existing infrastructure noise, not a redesign regression. Task 16 rechecks; no task treats them as a target.

The New Trade Back-navigation blocker (`StreamlitValueAssignmentNotAllowedError` for `nt_shot`) is **fixed and cleared** in commits `8b35a6e` and `3bb4a5f`. Task 8 preserves that fix; it does not redo it.

---

## File Structure

**Created**

| File | Responsibility |
|---|---|
| `src/tradelens/ui/components/review_document.py` | Pure Markdown → `ReviewDocument` parser. Standard library only. No Streamlit, no HTML, no model, no database |
| `src/tradelens/ui/components/review_reader.py` | The one reading shell all three AI Reviews lenses use. Pure HTML builders plus one Streamlit render entry point |
| `src/tradelens/ui/components/overview_bands.py` | Pure HTML builders for Overview bands 2 and 4 — the discipline panel and the ranked-performance list |
| `src/tradelens/ui/components/partner_panel.py` | Partner presentation: launcher, drawer, full-page body, conversation, composer. Consumes the Codex adapter; never imports the Anthropic SDK |
| `src/tradelens/ui/pages/7_Partner.py` | The Partner destination reached from the mobile `More` sheet |
| `tests/test_review_document.py` | Parser unit tests |
| `tests/test_review_reader.py` | Reading-shell tests |
| `tests/test_overview_bands.py` | Band builder tests |
| `tests/test_partner_panel.py` | Partner surface tests |
| `tests/test_dark_workspace.py` | Cross-cutting dark-system contract tests (token roles, z-scale, no literals, no deleted names) |
| `tests/source_probe.py` | Shared source- and CSS-inspection helpers used by several test files |

**Modified**

| File | Change |
|---|---|
| `src/tradelens/ui/design_system.py` (2858 lines) | New role namespace, z-scale, deletion of superseded names, dark CSS retarget |
| `src/tradelens/ui/components/workspace.py` (364) | No contract change — retargeted styling only, via `design_system` |
| `src/tradelens/ui/components/sidebar.py` (343) | One `MOBILE_MORE` entry for the Partner; rail omits it |
| `src/tradelens/ui/components/data_state.py` | One shared dated-instrument gate |
| `src/tradelens/ui/components/charts.py` (744) | Dark stage, divergent calendar heatmap, two heights only |
| `src/tradelens/ui/app.py` (527) | Overview recomposed into five bands |
| `src/tradelens/ui/pages/1_NewTrade.py` (1163) | Dark treatment; one progress system |
| `src/tradelens/ui/pages/2_Trades.py` (874) | Dark ledger, calendar, trade detail; toolbar target fix |
| `src/tradelens/ui/pages/4_Analytics.py` (824) | One lens shape across four lenses |
| `src/tradelens/ui/pages/6_Insights.py` (628) | Reading shell; regeneration no longer destroys the prior note |
| `src/tradelens/ui/pages/5_Strategy.py` (403), `9_Settings.py` (450) | Dark treatment; contained Danger Zone |
| `src/tradelens/ui/components/auth_screen.py` (501) | Dark auth surface |
| `src/tradelens/services/metrics.py` (1510) | **Codex only** — two additions (Task 4) |
| `src/tradelens/services/partner_context.py` | **Codex only** — new adapter (Task 4) |

---

## Shared test helpers

Several tasks assert against source text and generated CSS. Those helpers are defined once, in `tests/source_probe.py`, created as the first step of Task 1. Every later task imports from here rather than redefining them.

**This source is verified, not sketched.** It and its test file were executed together on 2026-08-04 with the toolchain above: `16 passed`, Ruff clean, Black clean. The first draft of `function_source` and `outside` were both broken — they used `re.search(r"^\S", rest[1:], re.M)` to find a block end, which matches at offset 0 and truncated every block to a single character. That is why these now carry their own tests.

`tests/source_probe.py`:

```python
"""Source- and CSS-inspection helpers shared across the dark-workspace tests.

Structural assertions against source are a blunt instrument, and they are used
deliberately: several rules in this phase (no hover-gated layout, one usage log,
no cache clear before regeneration) are properties of *where* code sits, which
no runtime assertion can observe.

Every function returns a value rather than raising when its target is absent,
so a caller fails on the assertion it wrote instead of on a lookup error.
"""

from __future__ import annotations

import re

_DEF = re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\(", re.M)


def near(source: str, anchor: str, radius: int = 400) -> str:
    """The text surrounding the first occurrence of ``anchor``.

    Returns "" when the anchor is absent, so an assertion on the window fails
    on its own terms rather than on an IndexError.
    """
    at = source.find(anchor)
    if at == -1:
        return ""
    return source[max(0, at - radius) : at + radius]


def _block_end(lines: list[str], start: int) -> int:
    """Index of the first line after the block opening at ``start``.

    A top-level block ends at the next line that is non-blank, unindented, and
    not a decorator continuation. Comments at column 0 end it too: a top-level
    comment belongs to whatever follows, not to what preceded it.
    """
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if not line.strip():
            continue
        if line[:1].isspace():
            continue
        return index
    return len(lines)


def function_source(source: str, name: str) -> str:
    """The complete body of a top-level ``def name(...)``, decorators included.

    Returns "" when the function is absent. Nested defs of the same name are
    ignored — only a definition at column 0 counts, because these probes make
    claims about module-level structure.
    """
    lines = source.splitlines(keepends=True)
    for index, line in enumerate(lines):
        match = _DEF.match(line)
        if not match or match.group(1) != name:
            continue
        start = index
        # Walk back over stacked decorators so @property/@staticmethod stay
        # attached to the function they modify.
        while start and lines[start - 1].lstrip().startswith("@"):
            start -= 1
        return "".join(lines[start : _block_end(lines, index)])
    return ""


def outside(source: str, name: str) -> str:
    """``source`` with the complete top-level block ``name`` removed.

    Used to prove a token appears only inside the region licensed to carry it —
    for example that TL_DANGER is referenced only within the Danger Zone
    renderer. ``name`` is a top-level ``def`` name; when it is absent the whole
    source is returned, so the caller's assertion still runs against real text.
    """
    block = function_source(source, name)
    if not block:
        return source
    return source.replace(block, "", 1)


def media_context(css: str, block: str) -> str:
    """The ``@media (...)`` condition ``block`` sits inside, or "".

    Brace-counted rather than "the nearest preceding @media": an earlier media
    query that already closed must not be reported as the enclosing one.
    """
    at = css.find(block)
    if at == -1:
        return ""
    depth = 0
    stack: list[tuple[int, str]] = []
    for match in re.finditer(r"@media([^{]*)\{|\{|\}", css[:at]):
        token = match.group(0)
        if token.startswith("@media"):
            stack.append((depth, match.group(1).strip()))
            depth += 1
        elif token == "{":
            depth += 1
        else:
            depth -= 1
            while stack and stack[-1][0] >= depth:
                stack.pop()
    return stack[-1][1] if stack else ""
```

`tests/test_source_probe.py`:

```python
"""The probes make structural claims, so they need structural tests.

A probe that silently returns a truncated block turns every assertion built on
it into a false pass — which is exactly what the first version of
function_source did.
"""

import source_probe
from source_probe import function_source, media_context, near, outside

SAMPLE = '''\
"""Module docstring."""

import re

CONSTANT = 1


def alpha(x):
    """First."""
    if x:
        return 1
    return 0


@decorator
@decorator_two
def beta():
    return "beta body"


class Gamma:
    def alpha(self):
        """A nested alpha that must not be picked up."""
        return None


def delta():
    return 3
'''


def test_function_source_returns_the_complete_body():
    block = function_source(SAMPLE, "alpha")
    assert block.startswith("def alpha(x):")
    assert '"""First."""' in block
    assert "return 0" in block
    assert "def beta" not in block


def test_function_source_stops_before_the_next_top_level_statement():
    assert "CONSTANT" not in function_source(SAMPLE, "alpha")
    assert "class Gamma" not in function_source(SAMPLE, "beta")


def test_function_source_includes_stacked_decorators():
    block = function_source(SAMPLE, "beta")
    assert block.startswith("@decorator\n@decorator_two\ndef beta():")
    assert 'return "beta body"' in block


def test_function_source_ignores_a_nested_method_of_the_same_name():
    block = function_source(SAMPLE, "alpha")
    assert "must not be picked up" not in block


def test_function_source_handles_the_last_function_in_a_file():
    block = function_source(SAMPLE, "delta")
    assert block.strip() == "def delta():\n    return 3"


def test_function_source_returns_empty_for_a_missing_name():
    assert function_source(SAMPLE, "nope") == ""


def test_outside_removes_the_whole_block_and_keeps_everything_else():
    rest = outside(SAMPLE, "beta")
    assert "beta body" not in rest
    assert "@decorator_two" not in rest
    assert "def alpha(x):" in rest
    assert "def delta():" in rest
    assert "CONSTANT = 1" in rest


def test_outside_returns_the_source_unchanged_for_a_missing_name():
    assert outside(SAMPLE, "nope") == SAMPLE


def test_outside_removes_only_the_first_match():
    doubled = SAMPLE + "\n\ndef delta():\n    return 4\n"
    rest = outside(doubled, "delta")
    assert rest.count("def delta():") == 1


def test_near_returns_a_window_and_empty_for_a_missing_anchor():
    assert "CONSTANT" in near(SAMPLE, "import re", radius=60)
    assert near(SAMPLE, "absent") == ""


CSS = """
.a { color: red; }
@media (max-width: 767px) {
  .in-phone { display: none; }
}
.after-phone { color: blue; }
@media (min-width: 768px) {
  .in-desktop { display: block; }
  @supports (display: grid) {
    .nested { display: grid; }
  }
}
.top-level-last { color: green; }
"""


def test_media_context_reports_the_enclosing_query():
    assert media_context(CSS, ".in-phone") == "(max-width: 767px)"
    assert media_context(CSS, ".in-desktop") == "(min-width: 768px)"


def test_media_context_is_empty_for_a_rule_outside_every_query():
    assert media_context(CSS, ".a {") == ""
    assert media_context(CSS, ".top-level-last") == ""


def test_a_closed_media_query_is_not_reported_as_enclosing():
    """The bug this replaced: '.after-phone' follows a closed max-width query
    and would have been reported as living inside it."""
    assert media_context(CSS, ".after-phone") == ""


def test_media_context_survives_a_nested_at_rule():
    assert media_context(CSS, ".nested") == "(min-width: 768px)"


def test_media_context_is_empty_for_absent_text():
    assert media_context(CSS, ".missing") == ""


def test_the_probes_import_nothing_beyond_the_standard_library():
    source = open(source_probe.__file__).read()
    assert "import streamlit" not in source
    assert "from src." not in source
```
### Shared data builders

Two frame builders are used by several test files. Define them once in `tests/source_probe.py` alongside the probes, so no task invents a second shape.

```python
def sample_frame(days: int = 6, trades_per_day: int = 2):
    """A trade frame with `days` distinct dates and mixed outcomes.

    Imported lazily so source_probe stays importable without pandas for the
    pure-structural tests that are its main job.
    """
    import pandas as pd

    rows = []
    for day in range(days):
        for n in range(trades_per_day):
            rows.append(
                {
                    "trade_date": f"2026-08-{day + 1:02d}",
                    "asset": ["EURUSD", "GBPUSD"][n % 2],
                    "session": ["London", "New York"][n % 2],
                    "setup_type": ["FVG", "OB"][n % 2],
                    "pnl": 120.0 if (day + n) % 3 else -80.0,
                    "followed_rules": (day + n) % 4 != 0,
                    "mistake_tags": '["fomo"]' if (day + n) % 4 == 0 else "",
                }
            )
    return pd.DataFrame(rows)


def daily_frame(pnls):
    """A calendar_daily_pnl-shaped frame: one row per supplied value.

    `None` means a day with no trade, which is information rather than missing
    data — the heatmap has to render it as its own state.
    """
    import pandas as pd

    return pd.DataFrame(
        [
            {"trade_date": f"2026-08-{i + 1:02d}", "pnl": value, "trades": 0 if value is None else 1}
            for i, value in enumerate(pnls)
        ]
    )
```

### Rendering a page in a test — use the existing subprocess boot

**Do not write an in-process page-rendering helper.** `tests/app_boot_check.py` carries an explicit, measured warning against it: setting `DATABASE_URL`, purging `src.tradelens.*` from `sys.modules`, and re-importing creates a *second* copy of `ai_client`, and every downstream `isinstance(x, AIUnavailable)` check bound at collection time then fails. That was measured at 34–47 spurious failures. The subprocess is the correct isolation boundary.

Reuse the established mechanism from `tests/test_pages_boot.py`:

```python
def _boot(page: str, db_path: Path, seed: str, marker: str = "-", state: str = "{}"):
    """Boot one page under AppTest in a subprocess with an isolated tmp DB.

    `state` is JSON applied to session_state before the first run, which is how
    a test reaches a specific view (a Journal detail, an error slot) without the
    runner knowing anything about that page.
    """
```

Any task needing rendered output calls `_boot(...)` with a `tmp_path` database and asserts on the child's exit code and captured output. `ALL_PAGES` in `tests/test_pages_boot.py` is the canonical page list and gains `7_Partner.py` in Task 15.

---

## Task 1: Establish the dark token contract

**Files:**
- Modify: `src/tradelens/ui/design_system.py:60-144` (token block), `:515`, `:2075`, `:2519` (z-index literals)
- Create: `tests/source_probe.py`, `tests/test_dark_workspace.py`
- Test: `tests/test_design_system.py` (update)

**Interfaces:**
- Consumes: `contrast_ratio(foreground, background)` — already exists at `tests/test_design_system.py:572`.
- Produces: the eleven role tokens and six z tokens below, plus `tests/source_probe.py`'s `near`, `function_source`, `outside`, `media_context`. Every later task imports from these names and from no others.

Resolves spec findings D1, D2, D3, D4, D13.

### `TL_LINE_STRONG` — the spec's proposed value does not pass

The spec (§4.1, §4.4) proposes `#3A4E56` and simultaneously requires ≥3:1 against adjacent surfaces. Measured with the WCAG 2.x relative-luminance formula, it does not:

| Surface | `#3A4E56` (spec) | `#5C6E77` (this plan) |
|---|---:|---:|
| canvas `#091216` | 2.17 ✗ | **3.56** ✓ |
| rail `#071014` | 2.20 ✗ | **3.61** ✓ |
| panel `#101B20` | 2.00 ✗ | **3.29** ✓ |
| elevated `#152329` | 1.84 ✗ | **3.03** ✓ |
| chart `#0C181D` | 2.07 ✗ | **3.39** ✓ |
| field `#122026` | 1.91 ✗ | **3.14** ✓ |

`#5C6E77` is the smallest value on the same cool blue-grey ramp clearing 3:1 everywhere. **`elevated` is the binding case**, not canvas — it is the lightest surface and it is where the Partner drawer's edge sits, so the three-surface check the spec implies would have passed a value that still failed on the drawer.

`TL_LINE_HAIRLINE` stays `#26373D` (1.53:1 on canvas). It is decorative by design; the plan's rule is that a *load-bearing* boundary uses `TL_LINE_STRONG`, so the hairline is not required to clear 3:1 and must stay visibly quieter.

**The specification has been amended to match** (2026-08-04, recorded as C6 in spec §15.3). §4.1's token block now reads `#5C6E77` and §4.4 carries the measured table for both values plus the all-six-surface contract. Spec and plan agree; neither is a silent deviation from the other.

- [ ] **Step 0: Create `tests/source_probe.py` and its tests**

Write both files exactly as given in the "Shared test helpers" section above. Both are staged in this task's commit. Run them before anything else:

Run: `"$PY" -m pytest tests/test_source_probe.py -v`
Expected: `16 passed`. Verified 2026-08-04 in a scratch directory against this exact source.

The probes are not a convenience — several rules in this phase are properties of *where* code sits, which no runtime assertion can observe. A probe that silently returns a truncated block turns every assertion built on it into a false pass, so they are tested first and tested directly.

- [ ] **Step 1: Write the failing contract tests**

Create `tests/test_dark_workspace.py`:

```python
"""Contract tests for the one dark token system.

Two live colour systems (D1) and a planned name retarget that would have
silently flipped six existing names (D2) are what these tests exist to
prevent. A deleted name must stay deleted: an alias is how D1 happened.
"""

import re
from pathlib import Path

import pytest

from src.tradelens.ui import design_system as ds
from tests.test_design_system import contrast_ratio

SURFACES = (
    "TL_SURFACE_CANVAS",
    "TL_SURFACE_RAIL",
    "TL_SURFACE_PANEL",
    "TL_SURFACE_ELEVATED",
    "TL_SURFACE_CHART",
    "TL_SURFACE_FIELD",
)

# Deleted in this task, never aliased. Spec §2 and §4.1.
DELETED_TOKENS = (
    "TL_CANVAS", "TL_PAPER", "TL_MIST", "TL_INK", "TL_MUTED", "TL_HAIRLINE",
    "TL_ACTION", "TL_ACTION_HOVER",
    "TL_SUCCESS_INK", "TL_DANGER_INK", "TL_WARNING_INK",
    "TL_SUCCESS_WASH", "TL_DANGER_WASH", "TL_WARNING_WASH", "TL_ACTION_WASH",
    "TL_RAIL", "TL_CHART_STAGE",
    "TL_BG", "TL_SURFACE", "TL_SURFACE_2", "TL_BORDER", "TL_BORDER_SUBTLE",
    "TL_TEXT", "TL_TEXT_MUTED", "TL_TEXT_FAINT",
)

Z_SCALE = (
    ("TL_Z_BASE", 0),
    ("TL_Z_RAISED", 10),
    ("TL_Z_PARTNER", 20),
    ("TL_Z_NAV", 30),
    ("TL_Z_SHEET", 40),
    ("TL_Z_OVERLAY", 50),
)


def test_every_role_token_exists_and_is_a_hex_colour():
    names = SURFACES + (
        "TL_CONTENT_PRIMARY",
        "TL_CONTENT_SECONDARY",
        "TL_LINE_HAIRLINE",
        "TL_LINE_STRONG",
        "TL_ACCENT_ACTION",
    )
    for name in names:
        value = getattr(ds, name)
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", value), f"{name} = {value!r}"


def test_body_text_clears_aa_on_every_surface():
    for surface in SURFACES:
        bg = getattr(ds, surface)
        for fg_name in ("TL_CONTENT_PRIMARY", "TL_CONTENT_SECONDARY"):
            ratio = contrast_ratio(getattr(ds, fg_name), bg)
            assert ratio >= 4.5, f"{fg_name} on {surface} = {ratio:.2f}"


def test_semantic_colours_clear_aa_on_every_surface():
    for surface in SURFACES:
        bg = getattr(ds, surface)
        for fg_name in ("TL_PRIMARY", "TL_SUCCESS", "TL_DANGER", "TL_WARNING"):
            ratio = contrast_ratio(getattr(ds, fg_name), bg)
            assert ratio >= 4.5, f"{fg_name} on {surface} = {ratio:.2f}"


def test_grade_ramp_clears_aa_on_the_panel_surface():
    # Grade chips move from the deleted light PAPER onto the dark panel, so
    # the whole ramp is re-pointed at the dark semantic family.
    for name in ("TL_GRADE_A", "TL_GRADE_B", "TL_GRADE_C", "TL_GRADE_D", "TL_GRADE_F"):
        ratio = contrast_ratio(getattr(ds, name), ds.TL_SURFACE_PANEL)
        assert ratio >= 4.5, f"{name} on panel = {ratio:.2f}"


def test_line_strong_is_a_usable_boundary_on_every_surface():
    # D4: rail vs canvas separates at 1.02:1, so tone cannot carry a boundary.
    # All six, not just three: the drawer edge sits on ELEVATED, which is the
    # lightest surface and therefore the binding constraint.
    for surface in SURFACES:
        ratio = contrast_ratio(ds.TL_LINE_STRONG, getattr(ds, surface))
        assert ratio >= 3.0, f"TL_LINE_STRONG on {surface} = {ratio:.2f}"


def test_the_hairline_stays_quieter_than_the_strong_line():
    """Two line weights that measure the same are one line weight."""
    assert contrast_ratio(ds.TL_LINE_HAIRLINE, ds.TL_SURFACE_CANVAS) < contrast_ratio(
        ds.TL_LINE_STRONG, ds.TL_SURFACE_CANVAS
    )


@pytest.mark.parametrize("name", DELETED_TOKENS)
def test_superseded_tokens_are_deleted_not_aliased(name):
    assert not hasattr(ds, name), (
        f"{name} still exists. Superseded names are deleted so a stale import "
        f"fails loudly instead of silently changing meaning (D1/D2)."
    )


def test_z_scale_is_defined_and_ordered():
    values = [getattr(ds, name) for name, _ in Z_SCALE]
    assert values == [expected for _, expected in Z_SCALE]
    assert values == sorted(values)


def test_navigation_always_outranks_the_partner():
    # A trader must never dismiss a chat surface to reach navigation (§4.5).
    assert ds.TL_Z_PARTNER < ds.TL_Z_NAV < ds.TL_Z_SHEET < ds.TL_Z_OVERLAY


def test_css_declares_no_z_index_outside_the_scale():
    css = ds.build_css()
    allowed = {"0", "10", "20", "30", "40", "50"}
    found = re.findall(r"z-index:\s*([^;]+);", css)
    for raw in found:
        value = raw.strip()
        assert value.startswith("var(--tl-z-") or value in allowed, (
            f"raw z-index {value!r} outside the scale — see §4.5"
        )


def test_css_exposes_every_role_as_a_custom_property():
    css = ds.build_css()
    for prop in (
        "--tl-surface-canvas", "--tl-surface-rail", "--tl-surface-panel",
        "--tl-surface-elevated", "--tl-surface-chart", "--tl-surface-field",
        "--tl-content-primary", "--tl-content-secondary",
        "--tl-line-hairline", "--tl-line-strong", "--tl-accent-action",
        "--tl-z-base", "--tl-z-raised", "--tl-z-partner",
        "--tl-z-nav", "--tl-z-sheet", "--tl-z-overlay",
    ):
        assert f"{prop}:" in css, f"{prop} missing from :root"


def test_no_page_module_declares_a_colour_literal():
    ui = Path("src/tradelens/ui")
    offenders = []
    for path in list(ui.glob("pages/*.py")) + [ui / "app.py"]:
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if re.search(r"#[0-9A-Fa-f]{6}\b", line):
                offenders.append(f"{path}:{lineno}")
    assert not offenders, f"colour literals outside design_system: {offenders}"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `"$PY" -m pytest tests/test_dark_workspace.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'TL_SURFACE_CANVAS'`, and the deletion tests fail because the old names still exist.

- [ ] **Step 3: Replace the token block**

In `src/tradelens/ui/design_system.py`, delete the `LIGHT WORKSPACE`, `DARK INSTRUMENTS`, and superseded parts of the `DARK INSTRUMENT RAMP` blocks at lines 60–144 and write one role set. Keep `TL_PRIMARY`, `TL_PRIMARY_HOVER`, `TL_PRIMARY_DIM`, `TL_SUCCESS`, `TL_SUCCESS_DIM`, `TL_DANGER`, `TL_DANGER_DIM`, `TL_WARNING`, `TL_WARNING_DIM`, `TL_NEUTRAL`, `TL_NEUTRAL_DIM`, `TL_FOCUS`, and every type/space/radius/motion ramp exactly as they are.

```python
# =========================================================================
# ONE DARK ROLE SYSTEM
# =========================================================================
# One namespace, one meaning per name. The previous light-workspace set and
# the duplicate legacy dark set are deleted rather than aliased: a deleted
# name raises ImportError at the call site, and an alias is precisely how
# two live colour systems came to coexist (D1/D2).
#
# Surfaces separate by 1.02-1.09:1, which is correct for tonal design and
# must not be "fixed" by pushing them apart. Boundaries are drawn with
# TL_LINE_HAIRLINE, or TL_LINE_STRONG where the line is load-bearing (D4).
TL_SURFACE_CANVAS = "#091216"  # quiet page background
TL_SURFACE_RAIL = "#071014"  # deepest structural surface
TL_SURFACE_PANEL = "#101B20"  # tables, filters, forms, composed sections
TL_SURFACE_ELEVATED = "#152329"  # selected controls, overlays, readouts
TL_SURFACE_CHART = "#0C181D"  # Plotly stage
TL_SURFACE_FIELD = "#122026"  # inputs and selectors

TL_CONTENT_PRIMARY = "#ECF5F4"  # 14.52-17.32:1 across the six surfaces
TL_CONTENT_SECONDARY = "#91A3A7"  # 6.13-7.32:1 across the six surfaces

TL_LINE_HAIRLINE = "#26373D"  # structure without card-box noise
# The spec proposed #3A4E56. Measured, it is 1.84-2.20:1 across the six
# surfaces - below the 3:1 floor a non-text boundary needs, and it would have
# failed the contract test in this task. #5C6E77 is the smallest value on the
# same cool blue-grey ramp that clears 3:1 on all six, ELEVATED being the
# binding case at 3.03:1.
TL_LINE_STRONG = "#5C6E77"  # load-bearing boundaries; >=3:1 on every surface

TL_ACCENT_ACTION = TL_PRIMARY  # unchanged bright TradeLens teal

# Grade chips read on the dark panel now that PAPER is gone, so the ramp
# uses the dark semantic family with brighter lime/orange intermediates.
TL_GRADE_A = TL_SUCCESS
TL_GRADE_B = "#A3E635"
TL_GRADE_C = TL_WARNING
TL_GRADE_D = "#FB923C"
TL_GRADE_F = TL_DANGER

# =========================================================================
# Z-INDEX SCALE (D13)
# =========================================================================
# Navigation always outranks the Partner: a trader must never dismiss a chat
# surface to reach navigation. Blocking confirmations outrank everything.
# No module may declare a raw z-index outside this scale.
TL_Z_BASE = 0
TL_Z_RAISED = 10  # sticky section and table headers
TL_Z_PARTNER = 20  # AI Partner launcher and drawer
TL_Z_NAV = 30  # navigation rail, bottom nav
TL_Z_SHEET = 40  # mobile More sheet
TL_Z_OVERLAY = 50  # blocking confirmations
```

- [ ] **Step 4: Mirror the roles as CSS custom properties**

In the `:root` block emitted by `build_css()`, add the following. **This is a fragment of an existing f-string, not a standalone statement** — the doubled braces are f-string escapes and it will not parse on its own:

```python
    :root {{
      --tl-surface-canvas: {TL_SURFACE_CANVAS};
      --tl-surface-rail: {TL_SURFACE_RAIL};
      --tl-surface-panel: {TL_SURFACE_PANEL};
      --tl-surface-elevated: {TL_SURFACE_ELEVATED};
      --tl-surface-chart: {TL_SURFACE_CHART};
      --tl-surface-field: {TL_SURFACE_FIELD};
      --tl-content-primary: {TL_CONTENT_PRIMARY};
      --tl-content-secondary: {TL_CONTENT_SECONDARY};
      --tl-line-hairline: {TL_LINE_HAIRLINE};
      --tl-line-strong: {TL_LINE_STRONG};
      --tl-accent-action: {TL_ACCENT_ACTION};
      --tl-z-base: {TL_Z_BASE};
      --tl-z-raised: {TL_Z_RAISED};
      --tl-z-partner: {TL_Z_PARTNER};
      --tl-z-nav: {TL_Z_NAV};
      --tl-z-sheet: {TL_Z_SHEET};
      --tl-z-overlay: {TL_Z_OVERLAY};
    }}
```

- [ ] **Step 5: Migrate the three z-index literals**

`design_system.py:515` (`z-index: 1000`) → `z-index: var(--tl-z-nav);`. `:2075` (`z-index: 20`) → `z-index: var(--tl-z-raised);`. `:2519` (`z-index: 100`) → `z-index: var(--tl-z-sheet);`. The `1000` must be replaced rather than preserved — an arbitrary ceiling is how the next overlay ends up at `1001`.

- [ ] **Step 6: Fix every import of a deleted name**

Run: `"$PY" -m pytest tests/ -x -q 2>&1 | head -40`
Follow each `ImportError` and repoint the call site at its role token. This is the deletion working as designed — it converts a silent meaning change into a build failure.

- [ ] **Step 7: Update `tests/test_design_system.py`**

`test_hybrid_palette_uses_light_workspace_and_dark_rail` and `test_light_workspace_semantics_are_separate_tokens` assert the two-system arrangement this task removes. Delete both and add:

```python
def test_one_role_system_replaces_the_light_and_legacy_dark_sets():
    """The hybrid is gone: canvas, rail, panel, elevated, chart, and field
    are one family, and the deleted names are covered in test_dark_workspace."""
    assert ds.TL_SURFACE_CANVAS != ds.TL_SURFACE_PANEL
    assert ds.TL_ACCENT_ACTION == ds.TL_PRIMARY == ds.TL_FOCUS
```

Keep `test_dark_instrument_palette_is_unchanged` — `TL_PRIMARY`, `TL_SUCCESS`, `TL_DANGER`, `TL_WARNING` are not superseded.

- [ ] **Step 8: Run the full suite, Ruff, Black**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/
"$PY" -m black --check src/ scripts/
git diff --check
```
Expected: all green, count ≥ baseline plus the new tests.

- [ ] **Step 9: Commit**

```bash
git add src/tradelens/ui/design_system.py \
        tests/source_probe.py tests/test_source_probe.py \
        tests/test_dark_workspace.py tests/test_design_system.py
git commit -m "feat(design): one dark role system and an ordered z-scale"
```

- [ ] **Step 10: Update the handoff and hand to Codex for review**

Record files changed, test counts, the list of call sites repointed, and the commit. Set `Active writer: NONE`.

---

## Task 2: Retarget the shell — rail, bottom nav, masthead, surfaces

**Files:**
- Modify: `src/tradelens/ui/design_system.py` (shell selectors), `src/tradelens/ui/components/sidebar.py`, `src/tradelens/ui/components/workspace.py`
- Test: `tests/test_premium_shell.py`, `tests/test_workspace_components.py`, `tests/test_dark_workspace.py`

**Interfaces:**
- Consumes: every role and z token from Task 1.
- Produces: no new Python interface. `workspace.py`'s builder signatures are unchanged — this task changes only what they are styled against.

- [ ] **Step 1: Write the failing shell tests**

Append to `tests/test_dark_workspace.py`:

```python
def test_rail_and_canvas_are_separated_by_a_line_not_by_tone():
    """D4: rail vs canvas is 1.02:1. Tone alone cannot carry the boundary,
    so the rail must draw an explicit strong edge."""
    css = ds.build_css()
    rail_rules = [
        block for block in css.split("}")
        if "stSidebar" in block and "border-right" in block
    ]
    assert rail_rules, "the rail declares no right edge"
    assert any("--tl-line-strong" in block for block in rail_rules)


def test_shell_surfaces_use_role_variables_not_literals():
    css = ds.build_css()
    body = css.split(":root", 1)[1].split("}", 1)[1]
    literals = re.findall(r"(?<!-)#[0-9A-Fa-f]{6}\b", body)
    assert not literals, f"raw colours outside :root: {sorted(set(literals))[:10]}"
```

- [ ] **Step 2: Run to verify failure**

Run: `"$PY" -m pytest tests/test_dark_workspace.py -k "rail or shell_surfaces" -v`
Expected: FAIL — the rail has no strong edge and shell rules still carry literals.

- [ ] **Step 3: Retarget the shell CSS**

In `design_system.py`, repoint the app-view container, sidebar rail, bottom nav, `More` sheet, masthead, and section headers onto `var(--tl-surface-*)`, `var(--tl-content-*)`, and `var(--tl-line-*)`. Give the rail `border-right: 1px solid var(--tl-line-strong);`. Structure comes from spacing, type scale, and hairlines — do not add card boxes.

- [ ] **Step 4: Replace emoji structural icons (D9)**

`app.py:272,470,505` and `6_Insights.py:158,326,463` pass `📓`, `📈`, `◆`, and one `""` as `render_empty_state` icons. Replace each with the Material symbol convention `sidebar.py` already uses (`:material/…:`) or a token-styled glyph. Change `data_state.render_data_state`'s default `icon: str = "◆"` to the same convention. No new icon dependency.

- [ ] **Step 5: Run shell and component tests**

Run: `"$PY" -m pytest tests/test_premium_shell.py tests/test_workspace_components.py tests/test_dark_workspace.py tests/test_pages_boot.py -q`
Expected: PASS.

- [ ] **Step 6: Browser verification — the shell renders dark and does not overflow**

Boot the app against a throwaway seeded SQLite database in the scratchpad with `DEMO_MODE=true`, and drive headless Chrome over CDP. At 1440, 1024, coarse 768, and coarse 375, for all seven authenticated routes, assert: expected page heading present, zero `stException` elements, no document-level horizontal overflow, and the computed `background-color` of `[data-testid="stAppViewContainer"]` equals `rgb(9, 18, 22)`.

Never point the browser at `data/tradelens.db`. Capture no artifact into the worktree.

- [ ] **Step 7: Full verification and commit**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/ && "$PY" -m black --check src/ scripts/ && git diff --check
git add src/tradelens/ui/design_system.py src/tradelens/ui/components/sidebar.py \
        src/tradelens/ui/components/workspace.py src/tradelens/ui/components/data_state.py \
        src/tradelens/ui/app.py src/tradelens/ui/pages/6_Insights.py tests/test_dark_workspace.py
git commit -m "feat(ui): retarget the shell onto the dark role system"
```

- [ ] **Step 8: Update the handoff with browser evidence and release the lock**

---

## Task 3: Darken forms, tables, disclosures, and status states

**Files:**
- Modify: `src/tradelens/ui/design_system.py` (control selectors)
- Test: `tests/test_dark_workspace.py`, `tests/test_design_system.py`, `tests/test_components.py`

**Interfaces:**
- Consumes: Task 1 tokens, Task 2 shell.
- Produces: the eight global interaction states every later page task relies on (spec §10).

- [ ] **Step 1: Write the failing state tests**

```python
def test_focus_is_never_removed_and_never_hover_gated():
    """A Streamlit rerun can move focus, so no interaction may depend on it
    persisting — but it must always be visible when it lands somewhere."""
    css = ds.build_css()
    compact = css.replace(" ", "")
    assert "outline:none" not in compact and "outline:0" not in compact
    for block in css.split("}"):
        if ":hover" in block and ":focus" not in block:
            assert "outline" not in block, f"hover-gated focus rule: {block[:120]}"


def test_no_hover_rule_carries_layout_behaviour():
    """Hover is visual only — a coarse pointer never receives it, so layout
    that only exists on hover does not exist on a phone."""
    layout = ("display:", "position:", "width:", "height:", "margin:", "padding:")
    for block in ds.build_css().split("}"):
        if ":hover" not in block:
            continue
        rules = block.split("{", 1)[-1]
        for prop in layout:
            assert prop not in rules.replace(" ", ""), f"hover layout rule: {block[:120]}"


def test_disabled_controls_are_distinguishable_from_read_only():
    css = ds.build_css()
    assert ":disabled" in css or '[disabled]' in css


def test_field_surface_is_quiet_when_unfocused():
    """A field is not neon until it is focused."""
    ratio = contrast_ratio(ds.TL_LINE_HAIRLINE, ds.TL_SURFACE_FIELD)
    assert ratio < contrast_ratio(ds.TL_ACCENT_ACTION, ds.TL_SURFACE_FIELD)
```

- [ ] **Step 2: Run to verify failure**

Run: `"$PY" -m pytest tests/test_dark_workspace.py -k "focus or hover or disabled or field_surface" -v`
Expected: FAIL on at least the hover-layout and focus rules.

- [ ] **Step 3: Implement the control system**

Retarget inputs, selects, textareas, buttons, tabs, radios, checkboxes, sliders, expanders, `<details>`, dataframes, alerts, and toasts onto the role tokens. Each control defines all eight states from spec §10: default (quiet), hover (visual only), focus (teal ring ≥3:1, never removed), active (feedback within 100 ms, no layout-shifting transform), disabled (visibly unavailable and semantically disabled), loading (feedback under 300 ms, height reserved), error (persistent, inline, `role="alert"`), empty (explains why, offers one action).

- [ ] **Step 4: Enforce the 44 px floor globally**

Add one rule setting `min-height: 44px; min-width: 44px;` on every interactive control class, extending hit area rather than shrinking visuals. Keep the existing 44 px tests in `tests/test_page_polish.py` green.

- [ ] **Step 5: Run tests, lint, commit**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/ && "$PY" -m black --check src/ scripts/
git add src/tradelens/ui/design_system.py tests/test_dark_workspace.py
git commit -m "feat(ui): darken controls and define all eight interaction states"
```

- [ ] **Step 6: Update the handoff and release the lock**

---

## Task 4: Service additions — **Codex-owned**

**Executed by Codex.** Claude must not write any part of this task. If Claude reaches this task, it stops, updates the handoff, and hands the lock to Codex.

**Files:**
- Modify: `src/tradelens/services/metrics.py:1036-1100`
- Create: `src/tradelens/services/partner_context.py`
- Test: `tests/test_metrics.py`, `tests/test_partner_context.py` (create)

**Interfaces:**
- Consumes: `_is_followed` (`metrics.py:1089`), `_parse_mistake_tags` (`:962`), `_safe_float` (`:22`), `total_edge_leak` (`:1036`); `get_active_strategy` (`strategy.py:128`); `Trade` (`db/models.py:67`); `SessionLocal` (`db/session.py:34`).
- Produces: `RuleAdherenceSummary`, `rule_adherence_rate`, `EdgeLeakSummary`, `edge_leak_summary`, `PartnerContext`, `PartnerEvidenceSource`, `build_global_partner_context`, and the module constants `MAX_CONTEXT_CHARS`, `MAX_EVIDENCE_SOURCES`, `JOURNAL_HEADING`, `TRADES_HEADING`, `STRATEGY_HEADING`. Tasks 5, 14, and 15 import exactly these names.

The interfaces are fixed by handoff §16.1–16.3 and may not be renegotiated in implementation.

**Files this task does NOT change.** Both open questions from the previous draft are settled in Step 7: the owner validator is **mirrored** (matching three existing service modules) and the strategy profile is read through the **public** `get_active_strategy`. No other service file is touched.

- [ ] **Step 1: Write the failing metrics tests**

Append to `tests/test_metrics.py`:

```python
import pandas as pd

from src.tradelens.services.metrics import (
    EdgeLeakSummary,
    RuleAdherenceSummary,
    edge_leak_summary,
    rule_adherence_rate,
)


def test_rule_adherence_all_followed():
    df = pd.DataFrame({"followed_rules": [True, True, True]})
    assert rule_adherence_rate(df) == RuleAdherenceSummary(3, 3, 1.0)


def test_rule_adherence_none_followed_is_a_known_zero():
    df = pd.DataFrame({"followed_rules": [False, False]})
    assert rule_adherence_rate(df) == RuleAdherenceSummary(0, 2, 0.0)


def test_rule_adherence_mixed():
    df = pd.DataFrame({"followed_rules": [True, False, True, False]})
    assert rule_adherence_rate(df) == RuleAdherenceSummary(2, 4, 0.5)


def test_rule_adherence_unrecorded_rows_leave_the_sample():
    df = pd.DataFrame({"followed_rules": [True, None, "", False]})
    assert rule_adherence_rate(df) == RuleAdherenceSummary(1, 2, 0.5)


def test_rule_adherence_empty_frame_is_unknown_not_zero_percent():
    assert rule_adherence_rate(pd.DataFrame()) == RuleAdherenceSummary(0, 0, None)


def test_rule_adherence_missing_column_is_unknown():
    df = pd.DataFrame({"pnl": [1.0, -2.0]})
    assert rule_adherence_rate(df) == RuleAdherenceSummary(0, 0, None)


def test_edge_leak_summary_distinguishes_all_three_zero_states():
    unknown = edge_leak_summary(pd.DataFrame())
    assert unknown == EdgeLeakSummary(None, 0, 0)

    clean = pd.DataFrame({"followed_rules": [True, True], "pnl": [10.0, -4.0]})
    assert edge_leak_summary(clean) == EdgeLeakSummary(0.0, 0, 2)

    netted = pd.DataFrame(
        {"followed_rules": [False, False, True], "pnl": [12.0, -12.0, 5.0]}
    )
    result = edge_leak_summary(netted)
    assert result.net_pnl == 0.0 and result.qualifying_trades == 2
    assert result.recorded_trades == 3


def test_edge_leak_summary_agrees_with_the_existing_scalar():
    from src.tradelens.services.metrics import total_edge_leak

    df = pd.DataFrame(
        {"followed_rules": [False, True, False], "pnl": [-30.0, 8.0, 5.0]}
    )
    assert edge_leak_summary(df).net_pnl == total_edge_leak(df)
```

- [ ] **Step 2: Run to verify failure**

Run: `"$PY" -m pytest tests/test_metrics.py -k "adherence or edge_leak_summary" -v`
Expected: FAIL with `ImportError: cannot import name 'RuleAdherenceSummary'`.

- [ ] **Step 3: Implement the two metrics additions**

`metrics.py` has **no** `from __future__ import annotations`, so this uses `typing.Optional`, not `| None`. `Optional` is already imported there.

This implementation was executed against the real `metrics.py` on 2026-08-04 — `_is_followed`, `_parse_mistake_tags`, and `_safe_float` are the shipped ones, not paraphrases — and passed 15/15 checks, including agreement with `total_edge_leak` across five frame shapes.

```python
def _is_recorded(value) -> bool:
    """True when followed_rules carries an explicit, parseable answer.

    None, NaN, and blank strings are the absence of an answer, not a "no".
    Folding them into the denominator would report a trader who left the field
    empty as having broken their rules.
    """
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, float) and value != value:  # NaN
        return False
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        try:
            int(float(text))
        except ValueError:
            return text.lower() in {"true", "false", "yes", "no"}
        return True
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


@dataclass(frozen=True)
class RuleAdherenceSummary:
    """Adherence with the sample it was measured over.

    A bare float cannot tell a known 0% apart from an unknown sample: 0% over
    forty recorded trades and 0% over nothing look identical. `rate` is None
    when nothing was recorded, so the UI can never print a false 0%.
    """

    followed: int
    recorded: int
    rate: Optional[float]


def rule_adherence_rate(trades: pd.DataFrame) -> RuleAdherenceSummary:
    """Share of recorded trades that followed the plan, with its sample."""
    if trades is None or trades.empty or "followed_rules" not in trades.columns:
        return RuleAdherenceSummary(0, 0, None)
    recorded = [v for v in trades["followed_rules"] if _is_recorded(v)]
    if not recorded:
        return RuleAdherenceSummary(0, 0, None)
    followed = sum(1 for v in recorded if _is_followed(v))
    return RuleAdherenceSummary(followed, len(recorded), followed / len(recorded))


@dataclass(frozen=True)
class EdgeLeakSummary:
    """Edge leak with enough context to read its zero honestly."""

    net_pnl: Optional[float]
    qualifying_trades: int
    recorded_trades: int


def _leak_mask(trades: pd.DataFrame):
    """The mask total_edge_leak builds, extracted so the two cannot drift.

    Returns (mask, has_followed, has_mistakes).
    """
    has_followed = "followed_rules" in trades.columns
    has_mistakes = "mistake_tags" in trades.columns
    mask = pd.Series([False] * len(trades), index=trades.index)
    if has_followed:
        fr = pd.to_numeric(trades["followed_rules"], errors="coerce")
        mask = mask | (fr == 0)
    if has_mistakes:
        mask = mask | trades["mistake_tags"].apply(
            lambda raw: len(_parse_mistake_tags(raw)) > 0
        )
    return mask, has_followed, has_mistakes


def _has_leak_evidence(row, has_followed: bool, has_mistakes: bool) -> bool:
    """Whether one row carries a usable rule-adherence or mistake signal."""
    if has_followed and _is_recorded(row.get("followed_rules")):
        return True
    if has_mistakes and len(_parse_mistake_tags(row.get("mistake_tags"))) > 0:
        return True
    return False


def edge_leak_summary(trades: pd.DataFrame) -> EdgeLeakSummary:
    """Companion to total_edge_leak. The scalar is unchanged for its callers.

    Distinguishes the three states the Overview needs and the scalar cannot
    express: unknown (None, 0, 0), a known clean sample (0.0, 0, n), and
    rule-breaking trades that netted exactly zero (0.0, q, n) with q > 0.
    """
    if trades is None or trades.empty or "pnl" not in trades.columns:
        return EdgeLeakSummary(None, 0, 0)
    mask, has_followed, has_mistakes = _leak_mask(trades)
    if not has_followed and not has_mistakes:
        return EdgeLeakSummary(None, 0, 0)
    recorded = sum(
        1
        for _, row in trades.iterrows()
        if _has_leak_evidence(row, has_followed, has_mistakes)
    )
    if recorded == 0:
        return EdgeLeakSummary(None, 0, 0)
    pnl = pd.to_numeric(trades["pnl"], errors="coerce").fillna(0.0)
    return EdgeLeakSummary(_safe_float(pnl[mask].sum()), int(mask.sum()), recorded)
```

`total_edge_leak(trades) -> float` keeps its current signature and behaviour for every existing caller; refactoring it to call `_leak_mask` is optional and must not change its results.

> **`mistake_tags` is a JSON-list string, not a bare tag.** `_parse_mistake_tags("fomo")` returns `[]`; `_parse_mistake_tags('["fomo"]')` returns `["fomo"]`. Test data must use the JSON form or the leak mask silently sees nothing. This cost two false failures while verifying the implementation above.

- [ ] **Step 4: Run the metrics tests to verify they pass**

Run: `"$PY" -m pytest tests/test_metrics.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing Partner-context tests**

Create `tests/test_partner_context.py`. **Verified 2026-08-04: this exact file and the implementation in Step 7 were run together — `34 passed`, Ruff clean, Black clean.** Two behaviours were mutation-checked: reverting `_journal_text` to the truthiness chain fails 4 tests, and counting rows instead of meaningful notes fails 1.

The fixtures follow the isolation pattern already established at `tests/test_user_isolation.py:28`. Both `partner_context.SessionLocal` and `strategy.SessionLocal` are patched, because the adapter reads trades through its own session and the strategy profile through the public `get_active_strategy`, which opens its own. `StaticPool` is required: without it each connection gets a fresh in-memory database and the seeded rows vanish.

```python
"""Tenancy, budgets, and the source-iff-contribution invariant."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.tradelens.services.partner_context as partner_context
import src.tradelens.services.strategy as strategy_service
from src.tradelens.db.models import Base, Strategy, Trade, User
from src.tradelens.services.partner_context import (
    PartnerContext,
    _journal_text,
    PartnerEvidenceSource,
    build_global_partner_context,
)


@pytest.fixture
def isolated_db(monkeypatch):
    """Point every session this flow opens at one throwaway database.

    Both modules are patched: build_global_partner_context reads trades through
    its own SessionLocal and the strategy profile through the public
    get_active_strategy, which opens its own.

    StaticPool keeps every connection on the same in-memory database; without it
    each connection gets a fresh empty one and the seeded rows vanish.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(partner_context, "SessionLocal", factory)
    monkeypatch.setattr(strategy_service, "SessionLocal", factory)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _seed_user(
    factory, username, *, trades=0, asset="EURUSD", note="note", strategy=True
):
    db = factory()
    try:
        user = User(username=username, password_hash=f"hash-{username}")
        db.add(user)
        db.commit()
        db.refresh(user)
        uid = user.id
        if strategy:
            db.add(Strategy(user_id=uid, name=f"{username} playbook", is_active=1))
        for n in range(trades):
            db.add(
                Trade(
                    user_id=uid,
                    asset=asset,
                    trade_date=f"2026-08-{(n % 28) + 1:02d}",
                    pnl=100.0 if n % 2 else -40.0,
                    trade_process_notes=(f"{note} {n}" if note else None),
                )
            )
        db.commit()
        return uid
    finally:
        db.close()


@pytest.fixture
def seeded_user(isolated_db):
    return _seed_user(isolated_db, "alice", trades=6)


@pytest.fixture
def seeded_two_users(isolated_db):
    owner = _seed_user(isolated_db, "alice", trades=4, asset="EURUSD")
    _seed_user(isolated_db, "bob", trades=4, asset="ZZZBOBONLY", note="bobsecret")
    return owner, "ZZZBOBONLY"


@pytest.fixture
def seeded_large_user(isolated_db):
    return _seed_user(isolated_db, "carol", trades=400)


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [None, True, False, 0, -1, "3", 2.0])
def test_invalid_owner_is_rejected_before_a_session_opens(bad, monkeypatch):
    def explode(*_a, **_k):
        raise AssertionError("a session was opened for an invalid owner")

    monkeypatch.setattr(partner_context, "SessionLocal", explode)
    with pytest.raises(ValueError):
        build_global_partner_context(user_id=bad)


def test_context_is_scoped_to_the_authenticated_user(seeded_two_users):
    owner, other_asset = seeded_two_users
    context = build_global_partner_context(user_id=owner)
    assert isinstance(context, PartnerContext)
    assert other_asset not in context.context_text
    assert "bobsecret" not in context.context_text
    assert all(s.user_id == owner for s in context.evidence_sources)


# ---------------------------------------------------------------------------
# Ordering and counts
# ---------------------------------------------------------------------------
def test_context_orders_journal_notes_before_trades_before_strategy(seeded_user):
    text = build_global_partner_context(user_id=seeded_user).context_text
    assert (
        text.index(partner_context.JOURNAL_HEADING)
        < text.index(partner_context.TRADES_HEADING)
        < text.index(partner_context.STRATEGY_HEADING)
    )


def test_counts_report_the_whole_journal_not_the_truncated_sample(seeded_large_user):
    context = build_global_partner_context(user_id=seeded_large_user)
    assert context.completed_trade_count == 400
    assert context.journal_entry_count == 400
    assert len(context.evidence_sources) < 400


# ---------------------------------------------------------------------------
# The invariant: a source exists iff its record contributed a line
# ---------------------------------------------------------------------------
def _assert_invariant(context):
    for source in context.evidence_sources:
        if source.kind == "strategy":
            assert source.label in context.context_text
        else:
            assert str(source.occurred_on) in context.context_text
    lines = [line for line in context.context_text.split("\n") if line.startswith("- ")]
    assert len(lines) == len(context.evidence_sources)


def test_the_invariant_holds_on_a_normal_sample(seeded_user):
    _assert_invariant(build_global_partner_context(user_id=seeded_user))


def test_the_invariant_holds_under_character_truncation(isolated_db, monkeypatch):
    monkeypatch.setattr(partner_context, "MAX_CONTEXT_CHARS", 240)
    uid = _seed_user(isolated_db, "dave", trades=12, note="x" * 60)
    context = build_global_partner_context(user_id=uid)
    assert 0 < len(context.context_text) <= 240
    _assert_invariant(context)


def test_the_invariant_holds_under_evidence_truncation(isolated_db, monkeypatch):
    monkeypatch.setattr(partner_context, "MAX_EVIDENCE_SOURCES", 3)
    uid = _seed_user(isolated_db, "erin", trades=10)
    context = build_global_partner_context(user_id=uid)
    assert len(context.evidence_sources) == 3
    _assert_invariant(context)


def test_an_oversized_first_note_is_skipped_and_never_cited(isolated_db, monkeypatch):
    """One journal note larger than the whole budget must not be half-admitted,
    and must not suppress the sections behind it."""
    monkeypatch.setattr(partner_context, "MAX_CONTEXT_CHARS", 400)
    uid = _seed_user(isolated_db, "fred", trades=0)
    db = isolated_db()
    try:
        db.add(
            Trade(
                user_id=uid,
                asset="HUGE",
                trade_date="2026-08-28",
                pnl=1.0,
                trade_process_notes="z" * 5000,
            )
        )
        db.add(
            Trade(
                user_id=uid,
                asset="SMALL",
                trade_date="2026-08-01",
                pnl=2.0,
                trade_process_notes="tiny note",
            )
        )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    assert "z" * 100 not in context.context_text
    assert not any(
        s.label.startswith("Journal note - HUGE") for s in context.evidence_sources
    )
    _assert_invariant(context)


def test_the_later_sections_survive_an_oversized_note(isolated_db, monkeypatch):
    monkeypatch.setattr(partner_context, "MAX_CONTEXT_CHARS", 600)
    uid = _seed_user(isolated_db, "gina", trades=0)
    db = isolated_db()
    try:
        db.add(
            Trade(
                user_id=uid,
                asset="HUGE",
                trade_date="2026-08-28",
                pnl=1.0,
                trade_process_notes="z" * 5000,
            )
        )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    # The trade row and the strategy still make it in: skipping is per candidate,
    # not a stop.
    assert partner_context.TRADES_HEADING in context.context_text
    assert partner_context.STRATEGY_HEADING in context.context_text
    _assert_invariant(context)


def test_a_blank_note_produces_neither_a_line_nor_a_source(isolated_db):
    uid = _seed_user(isolated_db, "hana", trades=0)
    db = isolated_db()
    try:
        db.add(
            Trade(
                user_id=uid,
                asset="BLANK",
                trade_date="2026-08-02",
                pnl=1.0,
                trade_process_notes="   ",
                notes="",
            )
        )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    journal_sources = [s for s in context.evidence_sources if s.kind == "journal"]
    assert journal_sources == []
    assert partner_context.JOURNAL_HEADING not in context.context_text
    _assert_invariant(context)


def test_no_heading_is_emitted_over_an_empty_section(isolated_db):
    uid = _seed_user(isolated_db, "iris", trades=0, strategy=False)
    context = build_global_partner_context(user_id=uid)
    assert context.context_text == ""
    assert context.evidence_sources == ()


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------
def test_adapter_never_calls_the_model_or_logs_usage(seeded_user, monkeypatch):
    import src.tradelens.services.cost as cost
    import src.tradelens.services.partner as partner

    monkeypatch.setattr(
        partner,
        "partner_reply",
        lambda *a, **k: pytest.fail("adapter called the model"),
    )
    monkeypatch.setattr(
        cost, "log_ai_usage", lambda *a, **k: pytest.fail("adapter logged usage")
    )
    build_global_partner_context(user_id=seeded_user)


def test_evidence_sources_are_structured_not_parsed_from_prompt_text(seeded_user):
    context = build_global_partner_context(user_id=seeded_user)
    assert context.evidence_sources
    first = context.evidence_sources[0]
    assert isinstance(first, PartnerEvidenceSource)
    assert isinstance(first.record_id, int)
    assert isinstance(first.label, str) and first.label
    assert first.kind in {"journal", "trade", "strategy"}


def test_a_user_with_nothing_yet_still_returns_a_usable_context(isolated_db):
    uid = _seed_user(isolated_db, "jane", trades=0)
    context = build_global_partner_context(user_id=uid)
    assert context.completed_trade_count == 0
    assert context.journal_entry_count == 0


def test_the_module_imports_no_streamlit():
    source = open(partner_context.__file__).read()
    assert "import streamlit" not in source


# ---------------------------------------------------------------------------
# What counts as a journal entry
# ---------------------------------------------------------------------------
class _Row:
    """Stand-in for either a Trade or the narrow column tuple the count uses."""

    def __init__(self, trade_process_notes=None, notes=None):
        self.trade_process_notes = trade_process_notes
        self.notes = notes


@pytest.mark.parametrize(
    "row, expected",
    [
        (_Row(None, None), ""),
        (_Row("", ""), ""),
        (_Row("   ", None), ""),
        (_Row("\t\n ", ""), ""),
        (_Row("process", "fallback"), "process"),
        (_Row(None, "fallback"), "fallback"),
        (_Row("", "fallback"), "fallback"),
        (_Row("  process  ", None), "process"),
    ],
)
def test_journal_text_judges_each_candidate_after_stripping(row, expected):
    assert _journal_text(row) == expected


def test_whitespace_only_process_notes_fall_back_to_a_meaningful_note():
    """The bug this pins: a non-empty string is truthy, so "   " won the `or`
    chain and the real note behind it was never reached."""
    assert _journal_text(_Row("   ", "the real note")) == "the real note"
    assert _journal_text(_Row("\t\n", "the real note")) == "the real note"


def test_blank_notes_are_excluded_from_the_journal_count(isolated_db):
    uid = _seed_user(isolated_db, "kara", trades=0)
    db = isolated_db()
    try:
        for process, note in (
            ("a real note", None),
            (None, "another real note"),
            ("   ", None),  # whitespace-only, no fallback
            ("\t\n ", ""),  # exotic whitespace, empty fallback
            (None, None),  # nothing at all
            ("", ""),  # empty strings
            ("   ", "rescued"),  # blank process note, meaningful fallback
        ):
            db.add(
                Trade(
                    user_id=uid,
                    asset="EURUSD",
                    trade_date="2026-08-05",
                    pnl=1.0,
                    trade_process_notes=process,
                    notes=note,
                )
            )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    assert context.journal_entry_count == 3
    assert context.completed_trade_count == 7


def test_the_count_matches_the_journal_lines_actually_admitted(isolated_db):
    """The count and the prompt answer the same question, by construction."""
    uid = _seed_user(isolated_db, "liam", trades=0)
    db = isolated_db()
    try:
        for process, note in (
            ("kept one", None),
            ("  ", "kept two"),
            ("   ", "  "),
            (None, "kept three"),
        ):
            db.add(
                Trade(
                    user_id=uid,
                    asset="EURUSD",
                    trade_date="2026-08-06",
                    pnl=1.0,
                    trade_process_notes=process,
                    notes=note,
                )
            )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    journal_sources = [s for s in context.evidence_sources if s.kind == "journal"]
    assert context.journal_entry_count == 3
    assert len(journal_sources) == 3
    for token in ("kept one", "kept two", "kept three"):
        assert token in context.context_text


def test_a_rescued_fallback_note_reaches_the_prompt(isolated_db):
    uid = _seed_user(isolated_db, "mira", trades=0)
    db = isolated_db()
    try:
        db.add(
            Trade(
                user_id=uid,
                asset="EURUSD",
                trade_date="2026-08-07",
                pnl=1.0,
                trade_process_notes="   ",
                notes="I moved my stop again",
            )
        )
        db.commit()
    finally:
        db.close()

    context = build_global_partner_context(user_id=uid)
    assert context.journal_entry_count == 1
    assert "I moved my stop again" in context.context_text
    _assert_invariant(context)


def test_journal_rows_stay_in_most_recent_first_order(isolated_db):
    uid = _seed_user(isolated_db, "nina", trades=0)
    db = isolated_db()
    try:
        for day, text in ((1, "oldest"), (15, "middle"), (28, "newest")):
            db.add(
                Trade(
                    user_id=uid,
                    asset="EURUSD",
                    trade_date=f"2026-08-{day:02d}",
                    pnl=1.0,
                    trade_process_notes=text,
                )
            )
        db.commit()
    finally:
        db.close()

    text = build_global_partner_context(user_id=uid).context_text
    assert text.index("newest") < text.index("middle") < text.index("oldest")
```

- [ ] **Step 6: Run to verify failure**

Run: `"$PY" -m pytest tests/test_partner_context.py -q`
Expected: FAIL — the module does not exist.

- [ ] **Step 7: Implement the adapter**

**Exact imports, no decisions left open.** Two were settled while verifying this:

- **Owner validator: mirrored, not promoted.** `_require_concrete_user_id` already exists as a private copy in `strategy.py:121`, `cost.py:34`, and `app_settings.py:16`. Three service modules carrying their own copy *is* the codebase's convention, so a fourth follows it rather than introducing a cross-service import for six lines. **No other service file changes.**
- **Strategy serializer: the public API, not the private one.** The adapter calls `get_active_strategy(user_id)` rather than importing `strategy._to_dict`. It is public, already owner-validated, already tested, and its dict already carries `id` — which is what the evidence descriptor needs. **No other service file changes.**

Task 4's file list is therefore unchanged: `metrics.py` plus the new `partner_context.py`.

```python
"""User-scoped context assembly for the global AI Partner.

Codex-owned. This module reads one authenticated trader's own records and
shapes them into prompt text plus a parallel set of citable descriptors. It
never calls the model and never logs usage — both belong to the UI turn that
produced a reply.

The invariant that shapes the whole file: **a PartnerEvidenceSource exists if
and only if its record contributed a line to context_text.** Budgets are applied
while admitting, not by trimming two lists afterwards, because trimming
independently produces exactly the two lies this surface cannot tell — an
evidence link to a record the model never saw, and a claim drawn from a record
the trader cannot open.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy import func

from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.strategy import get_active_strategy

# Service-owned budgets. A page cannot raise these; that is the point.
MAX_CONTEXT_CHARS = 12_000
MAX_EVIDENCE_SOURCES = 40
MAX_JOURNAL_ROWS = 15
MAX_TRADE_ROWS = 24
# Row budgets sum to 40 with the single strategy row, so MAX_EVIDENCE_SOURCES is
# a backstop rather than a limit that silently starves the later sections.

JOURNAL_HEADING = "## Journal notes"
TRADES_HEADING = "## Completed trades"
STRATEGY_HEADING = "## Active strategy profile"


@dataclass(frozen=True)
class PartnerEvidenceSource:
    """One record that contributed to the prompt, kept out of the prompt text.

    The UI renders links from these fields. It must never recover a record id by
    parsing model output: a model can produce a plausible id for a trade that
    does not exist, and the link would open an absence of a trade as if it were
    evidence.
    """

    kind: str  # "journal" | "trade" | "strategy"
    record_id: int
    user_id: int
    label: str
    occurred_on: Optional[str] = None


@dataclass(frozen=True)
class PartnerContext:
    context_text: str
    strategy_profile: Optional[dict]
    evidence_sources: Tuple[PartnerEvidenceSource, ...]
    completed_trade_count: int
    journal_entry_count: int


@dataclass(frozen=True)
class _Candidate:
    """One admissible unit: a prompt line and the record that produced it."""

    heading: str
    line: str
    source: PartnerEvidenceSource


def _require_concrete_user_id(user_id: int) -> int:
    """Reject an ownerless read before any session opens.

    Mirrors the identical private helper in strategy.py, cost.py, and
    app_settings.py. Mirrored rather than shared on purpose: three service
    modules already carry their own copy, so a fourth follows the established
    convention instead of introducing a cross-service import for six lines.
    """
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def _journal_text(row) -> str:
    """The trader's own words on this row, or "" when there are none.

    Each candidate is stripped *before* it is judged. An earlier version tested
    truthiness first, so a `trade_process_notes` of "   " won — a non-empty
    string is truthy — and the row silently lost a real `notes` value behind it.
    Process notes still take precedence when they say something.

    This is the single definition of a meaningful journal entry. The SQL filter
    below only narrows; this decides.
    """
    for field in ("trade_process_notes", "notes"):
        text = (getattr(row, field, None) or "").strip()
        if text:
            return text
    return ""


def _has_note_text():
    """SQL prefilter: drop NULL and blank notes before they reach Python.

    An optimisation, not the authority — SQL TRIM only strips spaces, so
    tab- or newline-only values still survive it and are removed by
    _journal_text. Keeping one authority is why the count below is computed
    from _journal_text rather than from this clause.
    """
    return (
        (Trade.trade_process_notes.isnot(None))
        & (func.trim(Trade.trade_process_notes) != "")
    ) | ((Trade.notes.isnot(None)) & (func.trim(Trade.notes) != ""))


def _admit(
    candidates: List[_Candidate],
) -> Tuple[str, Tuple[PartnerEvidenceSource, ...]]:
    """Admit candidates in order, atomically, under both budgets.

    A candidate is admitted only when its line *and* its source both fit. A
    candidate that does not fit is skipped and the walk continues, so one
    oversized journal note cannot suppress the completed-trade and strategy
    sections behind it.

    A heading is emitted only when its first candidate is admitted, so no
    section header ever stands over nothing.
    """
    blocks: List[str] = []
    sources: List[PartnerEvidenceSource] = []
    emitted_headings: set = set()
    length = 0

    for candidate in candidates:
        if len(sources) >= MAX_EVIDENCE_SOURCES:
            break

        pending: List[str] = []
        if candidate.heading not in emitted_headings:
            pending.append(candidate.heading)
        pending.append(candidate.line)

        # +1 per joined newline, counted only for lines after the first.
        added = sum(len(p) for p in pending) + len(pending) - (0 if blocks else 1)
        if length + added > MAX_CONTEXT_CHARS:
            continue

        if candidate.heading not in emitted_headings:
            emitted_headings.add(candidate.heading)
        blocks.extend(pending)
        sources.append(candidate.source)
        length += added

    return "\n".join(blocks), tuple(sources)


def build_global_partner_context(*, user_id: int) -> PartnerContext:
    """Assemble one user's reflective context for the global Partner.

    Order is the trader's own words first: journal notes, then completed-trade
    facts, then the active Strategy Profile. A reflective partner should reason
    from what the trader wrote before what the system computed.
    """
    owner = _require_concrete_user_id(user_id)

    db = SessionLocal()
    try:
        # Counts describe the journal, never the truncated sample: a budget
        # trims the prompt, it does not shrink what the trader has done.
        completed_trade_count = db.query(Trade).filter(Trade.user_id == owner).count()

        # Two narrow columns for every candidate row, so "how many journal
        # entries are there" is answered by the same function that decides what
        # a journal entry says. A SQL count would answer a slightly different
        # question and drift from the prompt the trader is shown.
        note_rows = (
            db.query(
                Trade.id,
                Trade.trade_date,
                Trade.trade_process_notes,
                Trade.notes,
            )
            .filter(Trade.user_id == owner, _has_note_text())
            .order_by(Trade.trade_date.desc())
            .all()
        )
        meaningful_ids = [row.id for row in note_rows if _journal_text(row)]
        journal_entry_count = len(meaningful_ids)

        wanted = meaningful_ids[:MAX_JOURNAL_ROWS]
        journal_rows = (
            db.query(Trade).filter(Trade.id.in_(wanted)).all() if wanted else []
        )
        position = {trade_id: index for index, trade_id in enumerate(wanted)}
        journal_rows.sort(key=lambda row: position[row.id])
        trade_rows = (
            db.query(Trade)
            .filter(Trade.user_id == owner)
            .order_by(Trade.trade_date.desc())
            .limit(MAX_TRADE_ROWS)
            .all()
        )
    finally:
        db.close()

    strategy_profile = get_active_strategy(owner)

    admissible: List[_Candidate] = []

    for row in journal_rows:
        note = _journal_text(row)
        if not note:
            # Unreachable via the selection above, which already applied
            # _journal_text. Kept because this loop must not depend on that.
            continue
        admissible.append(
            _Candidate(
                heading=JOURNAL_HEADING,
                line=f"- {row.trade_date}: {note}",
                source=PartnerEvidenceSource(
                    kind="journal",
                    record_id=row.id,
                    user_id=owner,
                    label=f"Journal note - {row.asset} {row.trade_date}",
                    occurred_on=row.trade_date,
                ),
            )
        )

    for row in trade_rows:
        admissible.append(
            _Candidate(
                heading=TRADES_HEADING,
                line=f"- {row.trade_date} {row.asset} P&L {row.pnl}",
                source=PartnerEvidenceSource(
                    kind="trade",
                    record_id=row.id,
                    user_id=owner,
                    label=f"{row.asset} {row.trade_date}",
                    occurred_on=row.trade_date,
                ),
            )
        )

    if strategy_profile and strategy_profile.get("id") is not None:
        name = strategy_profile.get("name") or "Strategy Profile"
        admissible.append(
            _Candidate(
                heading=STRATEGY_HEADING,
                line=f"- {name}",
                source=PartnerEvidenceSource(
                    kind="strategy",
                    record_id=int(strategy_profile["id"]),
                    user_id=owner,
                    label=name,
                ),
            )
        )

    context_text, evidence_sources = _admit(admissible)

    return PartnerContext(
        context_text=context_text,
        strategy_profile=strategy_profile,
        evidence_sources=evidence_sources,
        completed_trade_count=completed_trade_count,
        journal_entry_count=journal_entry_count,
    )
```

**Why admission is atomic.** An earlier draft built both lists in lockstep and then trimmed them independently — `context_text` by character budget, `evidence_sources` by count. That produces exactly the two lies this surface cannot tell: an evidence link to a record the model never saw, and a claim drawn from a record the trader cannot open. `_admit` therefore admits a line and its source together or neither, and **skips** a candidate that does not fit instead of stopping, so one oversized journal note cannot suppress the completed-trade and strategy sections behind it.

**One definition of a journal entry.** `_journal_text` strips each candidate *before* judging it, so a `trade_process_notes` of `"   "` no longer wins the comparison and hide a real `notes` value behind it — a non-empty string is truthy, which is how the earlier version lost them. The same function decides `journal_entry_count`, so the number the trader is shown and the notes the prompt carries can never answer different questions. The SQL clause only narrows; it is not the authority, because `TRIM` strips spaces but not tabs or newlines.

Row budgets sum to `MAX_EVIDENCE_SOURCES` with the single strategy row, so the evidence cap is a backstop rather than a limit that silently starves later sections. The truncation tests reach it by monkeypatching the constant.
- [ ] **Step 8: Run tests, lint, commit**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/ && "$PY" -m black --check src/ scripts/
git add src/tradelens/services/metrics.py src/tradelens/services/partner_context.py \
        tests/test_metrics.py tests/test_partner_context.py
git commit -m "feat(services): rule adherence, edge-leak, and Partner context summaries"
```

- [ ] **Step 9: Hand the lock back to Claude**

Record the exact produced signatures in the handoff. Tasks 5, 14, and 15 are unblocked.

---

## Task 5: Overview bands 1 and 2, and the shared date-series policy

**Files:**
- Modify: `src/tradelens/ui/components/data_state.py`, `src/tradelens/ui/app.py:157-265,392-460`
- Create: `src/tradelens/ui/components/overview_bands.py`, `tests/test_overview_bands.py`
- Test: `tests/test_data_state.py`, `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `rule_adherence_rate`, `edge_leak_summary` (Task 4); `compute_basic_metrics`, `compute_expectancy`, `compute_profit_factor_raw`, `compute_max_drawdown`, `compute_equity_curve`, `consistency_score`, `_MIN_TRADES_FOR_CONSISTENCY = 5`; `render_kpi_strip`, `MetricItem`.
- Produces:
  - `data_state.MIN_DATED_POINTS: int = 4`
  - `data_state.show_dated_instrument(state: SampleState) -> bool`
  - `overview_bands.DisciplineMeasure(label: str, value: str, sample: str, note: str | None = None)`
  - `overview_bands.render_discipline_panel(measures: Sequence[DisciplineMeasure]) -> str`

Bands are five distinct forms, one per question (spec §5.1). The anti-grid rule is structural: no band may reuse another band's form.

- [ ] **Step 1: Write the failing date-series policy test**

Append to `tests/test_data_state.py`:

```python
from src.tradelens.ui.components.data_state import (
    MIN_DATED_POINTS,
    sample_state,
    show_dated_instrument,
)


def test_a_dated_instrument_needs_four_populated_trading_days():
    """Spec §5.4a. One rule for the equity curve and the calendar heatmap."""
    assert MIN_DATED_POINTS == 4


def test_two_trades_on_one_date_are_one_populated_trading_day():
    df = pd.DataFrame(
        {"trade_date": ["2026-08-01", "2026-08-01", "2026-08-02"], "pnl": [1, 2, 3]}
    )
    assert sample_state(df).dated_points == 2
    assert show_dated_instrument(sample_state(df)) is False


def test_four_populated_days_unlock_the_dated_instruments():
    dates = ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"]
    df = pd.DataFrame({"trade_date": dates, "pnl": [1, 2, 3, 4]})
    assert show_dated_instrument(sample_state(df)) is True


@pytest.mark.parametrize("days", range(0, 9))
def test_the_shared_gate_agrees_with_the_existing_dominant_series_gate(days):
    """Extending one constant, not inventing a threshold: every populated day
    carries at least one trade, so dated >= 4 already implies trades >= 4."""
    dates = [f"2026-08-{d + 1:02d}" for d in range(days)]
    df = pd.DataFrame({"trade_date": dates, "pnl": [1.0] * days})
    state = sample_state(df)
    assert show_dated_instrument(state) == state.show_dominant_series
```

- [ ] **Step 2: Run to verify failure**

Run: `"$PY" -m pytest tests/test_data_state.py -k dated -v`
Expected: FAIL — `ImportError: cannot import name 'MIN_DATED_POINTS'`.

- [ ] **Step 3: Implement the shared gate**

In `data_state.py`, beside `_MIN_DOMINANT_POINTS`:

```python
# Spec §5.4a. One rule governs every dated instrument — the equity curve and
# the calendar heatmap alike. This is not a new threshold: it is the existing
# dominant-series constant, exposed publicly so the heatmap cannot drift onto
# a second one. The generic "fewer than 20 cells" heatmap heuristic does not
# transfer, because an empty calendar day is information (no trade was taken),
# not missing data.
MIN_DATED_POINTS = _MIN_DOMINANT_POINTS


def show_dated_instrument(state: SampleState) -> bool:
    """Whether a dated instrument has earned the right to draw."""
    return state.dated_points >= MIN_DATED_POINTS
```

- [ ] **Step 4: Run to verify it passes**

Run: `"$PY" -m pytest tests/test_data_state.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing discipline-panel tests**

Create `tests/test_overview_bands.py`:

```python
"""Band 2 is a discipline panel, not a KPI strip and not four cards.

The form is what keeps the Overview from becoming a card wall: five bands,
five forms (spec §5.1).
"""

from src.tradelens.ui.components.overview_bands import (
    DisciplineMeasure,
    render_discipline_panel,
)


def test_every_value_is_visible_as_text_never_encoded_only_in_an_indicator():
    html = render_discipline_panel(
        [DisciplineMeasure(label="Rule adherence", value="72%", sample="18 of 25")]
    )
    assert "72%" in html and "18 of 25" in html


def test_a_measure_always_carries_its_sample_beside_the_figure():
    html = render_discipline_panel(
        [DisciplineMeasure(label="Rule adherence", value="72%", sample="18 of 25")]
    )
    assert html.index("72%") < html.index("18 of 25")


def test_process_measures_are_never_toned_red_or_green():
    """Red and green are reserved for money outcomes (spec §5.3)."""
    html = render_discipline_panel(
        [DisciplineMeasure(label="Consistency", value="64", sample="n=31")]
    )
    assert 'data-tone="positive"' not in html
    assert 'data-tone="negative"' not in html


def test_the_panel_is_not_a_kpi_strip():
    html = render_discipline_panel(
        [DisciplineMeasure(label="Max drawdown", value="-$412.00", sample="n=25")]
    )
    assert "tl-kpi-strip" not in html
    assert "tl-discipline" in html


def test_every_caller_value_is_escaped():
    html = render_discipline_panel(
        [DisciplineMeasure(label="<script>x</script>", value="1", sample="n=1")]
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_one_root_element():
    html = render_discipline_panel(
        [DisciplineMeasure(label="A", value="1", sample="n=1")]
    ).strip()
    assert html.startswith("<div") and html.count("<div class=\"tl-discipline\"") == 1
```

- [ ] **Step 6: Run to verify failure**

Run: `"$PY" -m pytest tests/test_overview_bands.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 7: Implement the discipline panel**

Create `src/tradelens/ui/components/overview_bands.py`. Pure, no Streamlit import, escapes every caller value, emits one root element, takes pre-formatted strings so nothing re-rounds a number — the same contract `workspace.py` already keeps.

```python
@dataclass(frozen=True)
class DisciplineMeasure:
    """One row of the discipline panel. Values arrive pre-formatted.

    `sample` is not optional. A rate without its sample reads as certainty
    the journal has not earned, and handoff §2 requires the numerator and
    denominator beside the percentage.
    """

    label: str
    value: str
    sample: str
    note: str | None = None


def render_discipline_panel(measures: Sequence[DisciplineMeasure]) -> str:
    """Four measures as figure + inline indicator pairs on one panel."""
```

- [ ] **Step 8: Run to verify it passes**

Run: `"$PY" -m pytest tests/test_overview_bands.py -v`
Expected: PASS.

- [ ] **Step 9: Write the failing Overview band tests**

Append to `tests/test_dashboard.py`:

```python
def test_band_one_keeps_the_five_headline_measures_in_order():
    from src.tradelens.ui.app import _overview_metrics  # noqa: PLC0415

    labels = [item.label for item in _overview_metrics(sample_frame())]
    assert labels[:5] == [
        "Net P&L", "Win rate", "Expectancy", "Profit factor", "Trades"
    ]


def test_trade_count_is_never_toned():
    from src.tradelens.ui.app import _overview_metrics  # noqa: PLC0415

    trades = [i for i in _overview_metrics(sample_frame()) if i.label == "Trades"][0]
    assert trades.tone == "neutral"


def test_unknown_adherence_reads_not_recorded_never_zero_percent():
    from src.tradelens.ui.app import _discipline_measures  # noqa: PLC0415

    measures = _discipline_measures(pd.DataFrame())
    adherence = [m for m in measures if m.label == "Rule adherence"][0]
    assert adherence.value == "Not recorded"
    assert "0%" not in adherence.value


def test_a_known_zero_adherence_is_shown_as_zero_with_its_sample():
    from src.tradelens.ui.app import _discipline_measures  # noqa: PLC0415

    df = pd.DataFrame({"followed_rules": [False, False], "pnl": [-1.0, -2.0]})
    adherence = [
        m for m in _discipline_measures(df) if m.label == "Rule adherence"
    ][0]
    assert adherence.value == "0%"
    assert adherence.sample == "0 of 2"


def test_a_positive_edge_leak_is_never_presented_as_a_good_outcome():
    """Rule-breaking that happened to net a profit is lucky, not repeatable."""
    from src.tradelens.ui.app import _discipline_measures  # noqa: PLC0415

    df = pd.DataFrame({"followed_rules": [False, True], "pnl": [40.0, 10.0]})
    leak = [m for m in _discipline_measures(df) if m.label == "Edge leak"][0]
    assert leak.note and "not repeatable" in leak.note.lower()


def test_consistency_is_withheld_below_five_trades_and_says_what_unlocks_it():
    from src.tradelens.ui.app import _discipline_measures  # noqa: PLC0415

    df = pd.DataFrame({"pnl": [1.0, 2.0, 3.0]})
    score = [m for m in _discipline_measures(df) if m.label == "Consistency"][0]
    assert "2 more" in score.sample
```

- [ ] **Step 10: Run to verify failure**

Run: `"$PY" -m pytest tests/test_dashboard.py -k "band_one or adherence or edge_leak or consistency" -v`
Expected: FAIL — `_discipline_measures` does not exist.

- [ ] **Step 11: Implement bands 1 and 2 in `app.py`**

Band 1 keeps `render_kpi_strip` with five cells: Net P&L (signed, toned, detail = trade count), Win rate (detail `{wins} of {total}`), Expectancy (signed, toned), Profit factor (`N/A` for 0/0, `∞` for wins-no-losses), Trades (plain count, never toned). Today / This week P&L demote into a quieter two-cell strip inside the same band. Retain the N/A and ∞ conventions, `_money()` never emitting a bare 0, and the visually hidden tone announcement.

Add `_discipline_measures(df) -> list[DisciplineMeasure]` for band 2: max drawdown (with a sparkline only when `show_dated_instrument`), rule adherence (`Not recorded` when `rate is None`, otherwise `{rate:.0%}` with `{followed} of {recorded}`), edge leak (three states from `EdgeLeakSummary`, with the positive-leak note), consistency score (withheld below `_MIN_TRADES_FOR_CONSISTENCY`, stating what unlocks it). Adherence and consistency stay neutral-toned with a text band label — colour does no semantic work it is not licensed for.

- [ ] **Step 12: Run tests, lint, commit**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/ && "$PY" -m black --check src/ scripts/
git add src/tradelens/ui/components/data_state.py \
        src/tradelens/ui/components/overview_bands.py src/tradelens/ui/app.py \
        tests/test_data_state.py tests/test_overview_bands.py tests/test_dashboard.py
git commit -m "feat(overview): standing strip and discipline panel on one date policy"
```

- [ ] **Step 13: Update the handoff and release the lock**

---

## Task 6: Overview bands 3 and 4 — trajectory and recurring edge

**Files:**
- Modify: `src/tradelens/ui/app.py:444-523`, `src/tradelens/ui/components/charts.py:687-744`, `src/tradelens/ui/components/overview_bands.py`
- Test: `tests/test_overview_bands.py`, `tests/test_charts.py`, `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `show_dated_instrument` and `MIN_DATED_POINTS` (Task 5); `compute_streaks`, `by_session`, `killzone_performance`, `by_setup_type`, `calendar_daily_pnl`; `leading_category(...).is_only_category`; `apply_chart_stage`.
- Produces: `overview_bands.RankedRow(label: str, value: str, sample: str)` and `overview_bands.render_ranked_list(title: str, rows: Sequence[RankedRow], *, rankable: bool) -> str`.

- [ ] **Step 1: Write the failing ranked-list tests**

```python
from src.tradelens.ui.components.overview_bands import RankedRow, render_ranked_list


def test_each_row_carries_its_own_sample_size():
    html = render_ranked_list(
        "Session performance",
        [RankedRow("London", "+$820.00", "n=14"), RankedRow("NY", "-$110.00", "n=6")],
        rankable=True,
    )
    assert "n=14" in html and "n=6" in html


def test_one_category_is_never_called_strongest():
    """leading_category.is_only_category owns this decision (spec §5.5)."""
    html = render_ranked_list(
        "Setup performance",
        [RankedRow("FVG", "+$420.00", "n=9")],
        rankable=False,
    )
    lowered = html.lower()
    for word in ("strongest", "weakest", "best", "worst", "top"):
        assert word not in lowered


def test_a_rankable_list_marks_its_leader():
    html = render_ranked_list(
        "Session performance",
        [RankedRow("London", "+$820.00", "n=14"), RankedRow("NY", "-$110.00", "n=6")],
        rankable=True,
    )
    assert 'data-rank="1"' in html


def test_ranked_rows_escape_caller_values():
    html = render_ranked_list(
        "S", [RankedRow("<b>x</b>", "1", "n=1")], rankable=False
    )
    assert "<b>x</b>" not in html
```

- [ ] **Step 2: Write the failing heatmap tests**

Append to `tests/test_charts.py`:

```python
def test_the_calendar_heatmap_uses_a_divergent_scale_with_a_neutral_zero():
    """Signed data cannot use a one-directional gradient: it makes a large
    loss and a large gain read as the same intensity (spec §5.5)."""
    daily = daily_frame([-300.0, 0.0, 250.0])
    fig = calendar_heatmap_chart(daily, 2026, 8)
    trace = fig.data[0]
    assert trace.zmid == 0
    assert len(trace.colorscale) >= 3


def test_the_heatmap_legend_carries_numeric_ticks_not_a_bare_ramp():
    fig = calendar_heatmap_chart(daily_frame([-300.0, 250.0]), 2026, 8)
    bar = fig.data[0].colorbar
    assert bar.tickvals is not None and len(bar.tickvals) >= 3


def test_every_day_kind_carries_a_non_colour_cue():
    """Positive, negative, breakeven, and no-trade must survive greyscale."""
    fig = calendar_heatmap_chart(
        daily_frame([120.0, -80.0, 0.0, None]), 2026, 8
    )
    text = " ".join(str(t) for row in fig.data[0].text for t in row)
    assert "+" in text and "−" in text


def test_exact_values_are_reachable_without_hover():
    fig = calendar_heatmap_chart(daily_frame([120.0]), 2026, 8)
    assert fig.data[0].texttemplate or fig.data[0].text is not None
```

- [ ] **Step 3: Run both sets to verify failure**

Run: `"$PY" -m pytest tests/test_overview_bands.py tests/test_charts.py -k "ranked or heatmap or divergent or non_colour" -v`
Expected: FAIL.

- [ ] **Step 4: Implement the ranked list**

Add `RankedRow` and `render_ranked_list` to `overview_bands.py`. `rankable=False` suppresses every ordinal marker and comparative word; the caller passes `not leading.is_only_category`.

- [ ] **Step 5: Implement the heatmap rules**

In `charts.py:687`, rewrite `calendar_heatmap_chart` to use a divergent red→neutral→green scale with `zmid=0` at low saturation, a colorbar with numeric tickvals, per-cell text carrying a sign glyph (`+`, `−`, `=` for breakeven, blank for no-trade), and `texttemplate` so values render without hover. Keep 7 columns at phone and 44 px day cells. No TradeZella purple.

- [ ] **Step 6: Implement band 3 and band 4 in `app.py`**

Band 3: the equity curve keeps the highest visual weight on the page at 360 px on `TL_SURFACE_CHART`, gated by `show_dated_instrument`. Flanked by four figures describing the *shape* rather than repeating band 1 — current streak (`compute_streaks.current_streak` plus `.streak_type`, so a word carries the meaning and not only colour), best streak paired with `.max_loss_streak`, average win (`No wins yet` when there are none — D10), average loss (`No losses yet`). Below the gate, state the standing and name how many more days unlock the curve.

Band 4: two ranked lists plus the heatmap. Below the gate, the heatmap falls back to a ranked day list built from the same `calendar_daily_pnl` rows, stating what would populate the grid. Add a grid-table alternative with row and column labels for screen readers and for anyone who needs exact values rather than intensities.

- [ ] **Step 7: Run tests, lint, commit**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/ && "$PY" -m black --check src/ scripts/
git add src/tradelens/ui/components/overview_bands.py src/tradelens/ui/components/charts.py \
        src/tradelens/ui/app.py tests/test_overview_bands.py tests/test_charts.py tests/test_dashboard.py
git commit -m "feat(overview): trajectory band and recurring-edge band"
```

- [ ] **Step 8: Update the handoff and release the lock**

---

## Task 7: Overview band 5 and the state matrix

**Files:**
- Modify: `src/tradelens/ui/app.py:198-245,408-527`
- Test: `tests/test_dashboard.py`, `tests/test_activation.py`

**Interfaces:**
- Consumes: `render_editorial_readout`, `EvidenceItem`, `render_next_step`, `_overview_observation` (`app.py:198`), `sample_state`, `show_dated_instrument`, `leading_category`, `consistency_score`, `_MIN_TRADES_FOR_CONSISTENCY`.
- Produces, in `app.py`:
  - `NextReviewAction` — a frozen dataclass with `kind: str` (`"next_step"` or `"observation"`), `title: str`, `body: str`, `progress: str | None` (`"{completed} of {total}"`, next-step only), and `evidence: EvidenceItem | None` (observation only).
  - `_next_review_action(df, activation) -> NextReviewAction | None` — returns the band 5 payload, or `None` when the band is omitted entirely.

The complete implementation of both is in Step 3 of this task. Band 5 absorbs two existing elements into one.

- [ ] **Step 1: Write the failing state tests**

```python
def test_band_five_is_omitted_when_neither_element_is_earned():
    """An empty band is worse than no band (spec §5.6)."""
    from src.tradelens.ui.app import _next_review_action  # noqa: PLC0415

    assert _next_review_action(pd.DataFrame(), activation=None) is None


def test_an_unactivated_account_gets_one_action_never_a_checklist():
    from src.tradelens.ui.app import _next_review_action  # noqa: PLC0415

    band = _next_review_action(sample_frame(), activation=_incomplete_activation())
    assert band.kind == "next_step"
    assert band.progress == "2 of 4"


def test_the_action_is_always_a_review_action_never_a_trade_action():
    from src.tradelens.ui.app import _next_review_action  # noqa: PLC0415

    band = _next_review_action(sample_frame(), activation=_complete_activation())
    lowered = band.body.lower()
    for word in ("buy", "sell", "enter", "entry", "target", "should trade"):
        assert word not in lowered


def test_three_trades_on_one_day_withholds_both_dated_instruments():
    """The worked example from spec §5.7: t=3, d=1 renders bands 1, 2, and 5.

    Under the superseded text the heatmap would have appeared at "4-9 trades"
    while simultaneously requiring 20 populated cells."""
    from src.tradelens.services.metrics import _MIN_TRADES_FOR_CONSISTENCY
    from src.tradelens.ui.app import _discipline_measures  # noqa: PLC0415

    df = pd.DataFrame(
        {"trade_date": ["2026-08-01"] * 3, "pnl": [10.0, -4.0, 2.0]}
    )
    state = sample_state(df)
    assert state.trades == 3 and state.dated_points == 1
    assert show_dated_instrument(state) is False

    # t=3 is below the consistency gate, so that one measure states what
    # unlocks it while adherence and edge leak still show with their n.
    assert state.trades < _MIN_TRADES_FOR_CONSISTENCY
    labels = [m.label for m in _discipline_measures(df)]
    consistency = [m for m in _discipline_measures(df) if m.label == "Consistency"][0]
    assert "Rule adherence" in labels and "Edge leak" in labels
    assert "2 more" in consistency.sample
```

- [ ] **Step 2: Run to verify failure**

Run: `"$PY" -m pytest tests/test_dashboard.py -k "band_five or unactivated or review_action or one_day" -v`
Expected: FAIL — `_next_review_action` does not exist.

- [ ] **Step 3: Implement band 5**

`app.py` already carries `from __future__ import annotations` at line 1, so `| None` is safe there.

```python
@dataclass(frozen=True)
class NextReviewAction:
    """The one thing to go and re-read. Never a trade action.

    Two of today's elements collapse into this: the activation next-step card
    and the period observation. Which one appears is a state question, not a
    layout question, so it is decided here rather than in the render path.
    """

    kind: str                        # "next_step" | "observation"
    title: str
    body: str
    progress: str | None = None      # "{completed} of {total}", next_step only
    evidence: EvidenceItem | None = None   # observation only


def _next_review_action(df, activation) -> NextReviewAction | None:
    """The band 5 payload, or None when the band is omitted entirely.

    An empty band is worse than no band, so "neither element earned" returns
    None rather than a placeholder.
    """
    # Activation outranks the observation: a trader who has not finished
    # setting up does not need a pattern read, they need the next setup step.
    if activation is not None and not activation.is_complete:
        step = activation.next_step          # (title, body, completed, total)
        return NextReviewAction(
            kind="next_step",
            title=step.title,
            body=step.body,
            progress=f"{step.completed} of {step.total}",
        )

    observation = _overview_observation(df)   # existing helper, app.py:198
    if observation is None:
        return None

    title, body, evidence = observation
    return NextReviewAction(
        kind="observation", title=title, body=body, evidence=evidence
    )
```

`_overview_observation` already returns the tuple carrying its Evidence Rail (evidence, sample `n=x of y`, confidence banded at 12/6, and the `is_only_category` limitation) — this reuses it rather than recomputing. Confirm its exact return shape at `app.py:198` before wiring; if it differs, adapt this destructuring and nothing else.

Test fixtures for the two activation states, defined in `tests/test_dashboard.py`:

```python
from src.tradelens.services.activation import TRADES_FOR_REVIEW  # noqa: F401


class _Step:
    def __init__(self, title, body, completed, total):
        self.title, self.body = title, body
        self.completed, self.total = completed, total


class _Activation:
    def __init__(self, complete, step=None):
        self.is_complete = complete
        self.next_step = step


def _incomplete_activation():
    return _Activation(
        False, _Step("Log five completed trades", "Then the weekly recap unlocks.", 2, 4)
    )


def _complete_activation():
    return _Activation(True)
```

These stand in for whatever `activation.py` returns. **Before writing them, read `src/tradelens/services/activation.py` and match its real attribute names**; if they differ, change the stubs, not the service.

- [ ] **Step 4: Implement the state matrix**

Wire spec §5.7 into the page. Two independent axes: populated trading days `d` gate the dated instruments; trade count `t` gates the sample-dependent figures.

| State | Behaviour |
|---|---|
| `t=0` | Full-page welcome. Bands 1–5 suppressed. Two paths: log first trade, load sample data |
| `d < 4` | Curve and heatmap both withheld; curve states the standing and names how many more days unlock it; heatmap falls back to a ranked day list |
| `d ≥ 4` | Both draw |
| `t < 5` | Consistency withheld, stating what unlocks it; adherence and edge leak still show with n |
| `t ≥ 5` | Consistency shows |
| One category only | Ranked lists render but do not rank |
| Filtered to empty | Bands suppressed; filter summary states the active scope and offers a path back |
| Sample data active | Labelled once in the masthead eyebrow, never a repeated banner |

Bands 1 and 5 are present whenever `t ≥ 1`, with band 5 omitted only per §5.6.

- [ ] **Step 5: Demote the asset filter**

Replace the expander above the numbers with a collapsed control plus the existing one-line `render_filter_summary`.

- [ ] **Step 6: Run tests, lint, commit**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/ && "$PY" -m black --check src/ scripts/
git add src/tradelens/ui/app.py tests/test_dashboard.py tests/test_activation.py
git commit -m "feat(overview): next-review-action band and the full state matrix"
```

- [ ] **Step 7: Browser verification of the five bands**

At 1440, 1024, coarse 768, coarse 375, against a throwaway database seeded to hit `t=0`, `t=3/d=1`, and `t≥5/d≥4`: assert zero exceptions, no horizontal overflow, and that the five bands render five distinct forms — one KPI strip, one discipline panel, one dominant chart, two ranked lists plus a heatmap, one editorial readout. Record the evidence in the handoff.

- [ ] **Step 8: Update the handoff and release the lock**

---

## Task 8: New Trade on the dark workspace

**Files:**
- Modify: `src/tradelens/ui/pages/1_NewTrade.py`, `src/tradelens/ui/components/ai_autofill_review.py`
- Test: `tests/test_trade_wizard.py`, `tests/test_ai_autofill_review.py`, `tests/test_quick_exact_trade.py`

**Interfaces:**
- Consumes: Task 1–3 tokens and controls; existing `trade_wizard` contract — `UNSETTABLE_WIDGET_KEYS`, `SCREENSHOT_DRAFT_KEY`, `sync_screenshot_mirror`, `effective_screenshot`, `keep_alive`, `reset_wizard_state`, `scope_wizard_to_owner`.
- Produces: no new interface.

**The screenshot fix from `8b35a6e` is load-bearing and must not be touched.** This task changes presentation only.

- [ ] **Step 1: Confirm the existing guards still hold before changing anything**

Run: `"$PY" -m pytest tests/test_trade_wizard.py -v`
Expected: PASS, 59 tests. If any fail, stop — a later task broke the wizard and that is the bug to fix first.

- [ ] **Step 2: Write the failing presentation tests**

```python
def test_the_wizard_has_exactly_one_progress_system():
    """The prior audit found two — text tabs plus a numbered rail — and the
    duplicate rail was removed. It must not return."""
    source = Path("src/tradelens/ui/pages/1_NewTrade.py").read_text()
    assert source.count("render_stepper") <= 1
    assert "tl-wizard-rail" not in source


def test_the_review_step_hides_empty_groups_instead_of_listing_them():
    at = _wizard(new_trade_step=5, nt_asset="EURUSD", nt_entry_time="09:30")
    body = " ".join(m.value for m in at.markdown)
    assert body.count("Not entered yet") <= 1
    assert "complete" in body.lower()


def test_the_screenshot_waiting_state_reserves_its_height():
    source = Path("src/tradelens/ui/pages/1_NewTrade.py").read_text()
    assert "tl-analysis-pending" in source
```

- [ ] **Step 3: Run to verify failure**

Run: `"$PY" -m pytest tests/test_trade_wizard.py -k "progress_system or empty_groups or waiting_state" -v`
Expected: FAIL.

- [ ] **Step 4: Implement the dark treatment**

Quiet progress, one primary action, never five bright pills. Blocking validation renders adjacent to its field, on blur rather than per keystroke, stating cause and fix. Screenshot analysis stays user-confirmed and its waiting state holds its height — no collapse-and-jump. Optional fields use progressive disclosure so the review step is not a wall of "Not entered yet": hide empty groups and offer one "complete N fields" action. Keep the outcome-contradiction block at create and edit (`trade_validation.py`), the loading→success save path, and the scoped reset. Reflection stays optional and visibly optional. Motion is the existing 180 ms step reveal only, firing once, removed under reduced motion.

- [ ] **Step 5: Run the wizard suite and the full suite**

Run: `"$PY" -m pytest tests/test_trade_wizard.py tests/test_ai_autofill_review.py -v` then `"$PY" -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Browser round trip with a real file**

Re-run the CDP driver used for `8b35a6e`: upload a real PNG through `DOM.setFileInputFiles`, then Continue → Back → Continue. The draft count must hold at `6 of 15` at every step with zero exceptions and a byte-identical retained chart. Run at 1440 and coarse 375.

- [ ] **Step 7: Commit**

```bash
git add src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/components/ai_autofill_review.py \
        tests/test_trade_wizard.py
git commit -m "feat(ui): New Trade on the dark workspace with one progress system"
```

- [ ] **Step 8: Update the handoff with browser evidence and release the lock**

---

## Task 9: Journal — ledger, calendar, trade detail

**Files:**
- Modify: `src/tradelens/ui/pages/2_Trades.py`, `src/tradelens/ui/components/trade_calendar.py`, `src/tradelens/ui/design_system.py` (dataframe toolbar)
- Test: `tests/test_journal.py`, `tests/test_page_polish.py`

**Interfaces:**
- Consumes: Task 1–3 tokens and controls.
- Produces: no new interface.

- [ ] **Step 1: Write the failing toolbar-target test**

The preflight measured the four Streamlit dataframe toolbar controls at ≈22.4×22.4 CSS px at 1440 — a documented failure of the 44×44 requirement.

```python
def test_the_dataframe_toolbar_controls_are_lifted_to_the_target_floor():
    """Live preflight measured these at 22.4x22.4 CSS px at 1440."""
    css = ds.build_css()
    toolbar = [b for b in css.split("}") if "stElementToolbarButton" in b]
    assert toolbar, "no rule targets the dataframe toolbar buttons"
    joined = " ".join(toolbar).replace(" ", "")
    assert "min-height:44px" in joined and "min-width:44px" in joined
```

- [ ] **Step 2: Run to verify failure**

Run: `"$PY" -m pytest tests/test_page_polish.py -k toolbar -v`
Expected: FAIL — no rule targets the toolbar.

- [ ] **Step 3: Fix the toolbar targets**

Add a scoped rule raising `[data-testid="stElementToolbarButton"]` to the 44 px floor by extending the hit area, keeping the icon's visual size. If Streamlit's internal layout resists, replace the toolbar with page-level controls of our own — the requirement is the visible target size, not the specific widget.

- [ ] **Step 4: Write the failing Journal presentation tests**

```python
def test_the_ledger_is_neutral_by_row():
    """No full-row red/green, no per-row gradients, no heavy cell boxes."""
    css = ds.build_css()
    for block in css.split("}"):
        if "tl-ledger" in block and "tr" in block:
            assert "linear-gradient" not in block


def test_money_and_dates_use_tabular_numerals():
    css = ds.build_css()
    assert "font-variant-numeric: tabular-nums" in css


def test_clear_filters_is_subordinate_to_the_primary_action():
    source = Path("src/tradelens/ui/pages/2_Trades.py").read_text()
    assert 'type="primary"' not in near(source, "Clear filters")
```

- [ ] **Step 5: Run to verify failure, then implement**

Compact filter bar with `More filters` as progressive disclosure and `Clear filters` styled subordinate. Ledger neutral by row, with semantic colour only on signed money and the explicit result badge. Tabular/mono numerals for money, dates, and R-multiples so columns do not shift. Calendar at 7 columns on phone with 44 px day cells and a textual legend. Trade detail as a ticket on `TL_SURFACE_PANEL`, with edit and delete behind separate disclosures and delete requiring explicit confirmation. `aria-sort` reflects the current sort state. Wide tables scroll inside their own container; the page body never scrolls horizontally.

- [ ] **Step 6: Verify all three interaction paths in a browser**

1. ledger row → detail → **Back to trades** → the full ledger, with scroll and filter state restored;
2. calendar day → trade opener → detail;
3. the AI summary renders as safe Markdown with its Evidence Rail separate.

Measure the toolbar controls again at 1440 and assert ≥44×44.

- [ ] **Step 7: Run tests, lint, commit**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/ && "$PY" -m black --check src/ scripts/
git add src/tradelens/ui/pages/2_Trades.py src/tradelens/ui/components/trade_calendar.py \
        src/tradelens/ui/design_system.py tests/test_journal.py tests/test_page_polish.py
git commit -m "feat(ui): dark Journal and 44px dataframe toolbar targets"
```

- [ ] **Step 8: Update the handoff and release the lock**

---

## Task 10: Analytics — four lenses, one shape

**Files:**
- Modify: `src/tradelens/ui/pages/4_Analytics.py`, `src/tradelens/ui/components/charts.py`
- Test: `tests/test_charts.py`, `tests/test_dashboard_metrics.py`

**Interfaces:**
- Consumes: `apply_chart_stage(fig, *, title=None, compact=False)`, `add_sample_annotation`, `leading_category`, `sample_state`.
- Produces: no new interface. Two chart heights only.

- [ ] **Step 1: Write the failing lens-shape tests**

```python
def test_every_plotly_figure_passes_through_the_chart_stage():
    source = Path("src/tradelens/ui/pages/4_Analytics.py").read_text()
    plots = source.count("st.plotly_chart(")
    staged = source.count("apply_chart_stage(")
    assert staged >= plots, f"{plots - staged} figure(s) bypass the stage"


def test_charts_use_exactly_two_heights():
    heights = set(re.findall(r"height=(\d+)", Path(
        "src/tradelens/ui/components/charts.py").read_text()))
    assert heights <= {"360", "240"}, f"unexpected chart heights: {heights}"


def test_the_lens_selector_is_visually_secondary_to_the_question():
    source = Path("src/tradelens/ui/pages/4_Analytics.py").read_text()
    assert source.index("render_section_header") < source.index("st.radio")


def test_sparse_data_gets_a_compact_state_not_an_empty_axis_frame():
    fig = equity_curve_chart(pd.DataFrame({"trade_date": [], "pnl": []}))
    assert fig.layout.xaxis.visible is False
```

- [ ] **Step 2: Run to verify failure, then implement**

Exactly four lenses — Performance, Risk, Timing, Setups — with exactly one body rendered at a time. Each lens follows one shape: question → ruled KPI strip → instrument → ranked evidence → editorial readout with its Evidence Rail. Every Plotly figure passes through `apply_chart_stage`. Two heights only: 360 dominant, 240 supporting. Semantic, limited palette — no rainbow. One category is never described as strongest or weakest; the fixed-risk alternative is retained. The sample annotation stays inside the stage at phone and desktop. Sparse data gets a compact explanatory state, never a full-size axis frame with two points.

- [ ] **Step 3: Implement chart accessibility**

Legend near the chart and interactive; tooltips reachable without hover; axis units labelled; a text summary of the key insight for screen readers; ≥3:1 for data marks and ≥4.5:1 for data labels. At 375 px charts reflow or simplify — fewer ticks, horizontal bars where clearer.

- [ ] **Step 4: Run tests, lint, browser-check the lens switch**

Switch Performance → Risk → Timing → Setups at 1440 and coarse 375. Zero exceptions, no horizontal overflow, one body at a time.

- [ ] **Step 5: Commit**

```bash
git add src/tradelens/ui/pages/4_Analytics.py src/tradelens/ui/components/charts.py \
        tests/test_charts.py tests/test_dashboard_metrics.py
git commit -m "feat(ui): one dark instrument shape across the four Analytics lenses"
```

- [ ] **Step 6: Update the handoff and release the lock**

---

## Task 11: The pure AI review document model

**Files:**
- Create: `src/tradelens/ui/components/review_document.py`, `tests/test_review_document.py`

**Interfaces:**
- Consumes: nothing. Standard library only.
- Produces:
  - `ReviewSection(id: str, level: int, title: str, body_md: str)` — frozen
  - `ReviewDocument(intro_md: str, sections: tuple[ReviewSection, ...])` — frozen, with `is_empty` property
  - `parse_review_markdown(content_md: str) -> ReviewDocument`

Task 12 consumes exactly these names. The parser is pure: no Streamlit, no HTML rendering, no model call, no database.

- [ ] **Step 1: Write the failing parser tests**

Create `tests/test_review_document.py`:

````python
"""The parser is presentation only.

It never rewrites what the model produced: every section keeps its original
Markdown, so `Read full note` can always render the complete response. A
parser that dropped content would silently discard a trader's review.
"""

import pytest

from src.tradelens.ui.components.review_document import (
    ReviewDocument,
    ReviewSection,
    parse_review_markdown,
)


def test_blank_content_returns_an_empty_document():
    doc = parse_review_markdown("")
    assert doc == ReviewDocument(intro_md="", sections=())
    assert doc.is_empty is True


def test_content_with_no_headings_returns_one_fallback_section():
    doc = parse_review_markdown("Just a paragraph of review prose.")
    assert len(doc.sections) == 1
    assert isinstance(doc.sections[0], ReviewSection)
    assert doc.sections[0].body_md == "Just a paragraph of review prose."


def test_prose_before_the_first_heading_becomes_the_intro():
    doc = parse_review_markdown("Lead sentence.\n\n## What happened\nBody.")
    assert doc.intro_md == "Lead sentence."
    assert doc.sections[0].title == "What happened"


def test_both_h2_and_h3_open_a_section():
    doc = parse_review_markdown("## A\nx\n### B\ny")
    assert [s.level for s in doc.sections] == [2, 3]
    assert [s.title for s in doc.sections] == ["A", "B"]


def test_original_markdown_is_preserved_verbatim():
    body = "- one\n- two\n\n**bold** and `code`"
    doc = parse_review_markdown(f"## Findings\n{body}")
    assert doc.sections[0].body_md == body


def test_duplicate_headings_get_deterministic_unique_ids():
    doc = parse_review_markdown("## Risk\na\n## Risk\nb")
    ids = [s.id for s in doc.sections]
    assert ids[0] != ids[1]
    assert parse_review_markdown("## Risk\na\n## Risk\nb").sections[1].id == ids[1]


def test_headings_inside_fenced_code_are_not_sections():
    doc = parse_review_markdown("## Real\n```\n## Not a heading\n```\n")
    assert len(doc.sections) == 1
    assert "## Not a heading" in doc.sections[0].body_md


def test_a_tilde_fence_also_protects_its_contents():
    doc = parse_review_markdown("## Real\n~~~\n## Not a heading\n~~~\n")
    assert len(doc.sections) == 1


def test_no_section_content_is_ever_dropped():
    source = "intro\n\n## A\nalpha\n\n## B\nbeta\n"
    doc = parse_review_markdown(source)
    rebuilt = doc.intro_md + "".join(s.body_md for s in doc.sections)
    for token in ("intro", "alpha", "beta"):
        assert token in rebuilt


@pytest.mark.parametrize("junk", [None, 123, [], {}])
def test_non_string_input_degrades_to_an_empty_document(junk):
    """This runs inside a render path — raising would blank the page."""
    assert parse_review_markdown(junk).is_empty is True


def test_a_backtick_fence_is_not_closed_by_tildes():
    doc = parse_review_markdown("## Real\n```\n~~~\n## Still code\n```\n## After\nx")
    assert [s.title for s in doc.sections] == ["Real", "After"]


def test_an_unclosed_fence_swallows_the_rest_rather_than_raising():
    doc = parse_review_markdown("## Real\n```\n## Not a heading\n")
    assert len(doc.sections) == 1


def test_a_heading_with_no_alphanumerics_still_gets_an_id():
    doc = parse_review_markdown("## ???\nbody")
    assert doc.sections[0].id == "section"
````

- [ ] **Step 2: Run to verify failure**

Run: `"$PY" -m pytest tests/test_review_document.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the parser**

Verified 2026-08-04: this exact source passes all 13 tests above plus 3 extra edge cases (an unclosed fence, a backtick fence not closed by tildes, a heading with no alphanumerics) — `16 passed`, Ruff clean, Black clean.

````python
"""A pure document model for AI-generated review Markdown.

Standard library only. No Streamlit, no HTML, no model, no database — this
decides where a long note's sections begin and ends there. Rendering,
sanitising, and safety belong to the caller, which keeps this testable without a
browser and keeps the model-output path unchanged.

It never rewrites what the model produced: every section keeps its original
Markdown, so `Read full note` can always render the complete response. A parser
that dropped content would silently discard a trader's review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple

_HEADING = re.compile(r"^(#{2,3})\s+(.*\S)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class ReviewSection:
    """One `##`/`###` section, with its Markdown exactly as generated."""

    id: str
    level: int
    title: str
    body_md: str


@dataclass(frozen=True)
class ReviewDocument:
    """Prose before the first heading, then the sections in reading order."""

    intro_md: str
    sections: Tuple[ReviewSection, ...]

    @property
    def is_empty(self) -> bool:
        return not self.intro_md.strip() and not self.sections


def _slug(title: str, taken: dict) -> str:
    """A deterministic id, suffixed on collision.

    Deterministic matters: the id survives a rerun, so the reader's selected
    section is still selected after an unrelated widget change.
    """
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "section"
    taken[base] = taken.get(base, 0) + 1
    return base if taken[base] == 1 else f"{base}-{taken[base]}"


def parse_review_markdown(content_md: object) -> ReviewDocument:
    """Split generated Markdown into an intro and its sections.

    Non-string input degrades to an empty document rather than raising: this
    runs inside a render path, where an exception blanks the page.
    """
    if not isinstance(content_md, str) or not content_md.strip():
        return ReviewDocument(intro_md="", sections=())

    intro: list = []
    sections: list = []
    current: dict | None = None
    taken: dict = {}
    fence: str | None = None

    for line in content_md.splitlines(keepends=True):
        opener = _FENCE.match(line)
        if opener:
            marker = opener.group(1)
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            (current["body"] if current else intro).append(line)
            continue

        heading = None if fence else _HEADING.match(line.rstrip("\n"))
        if heading:
            if current:
                sections.append(current)
            title = heading.group(2)
            current = {
                "id": _slug(title, taken),
                "level": len(heading.group(1)),
                "title": title,
                "body": [],
            }
            continue

        (current["body"] if current else intro).append(line)

    if current:
        sections.append(current)

    intro_md = "".join(intro).strip()

    if not sections:
        # No headings at all: one fallback section carrying everything, so the
        # reader has something to select and nothing is lost.
        return ReviewDocument(
            intro_md="",
            sections=(
                ReviewSection(id="note", level=2, title="Review", body_md=intro_md),
            ),
        )

    return ReviewDocument(
        intro_md=intro_md,
        sections=tuple(
            ReviewSection(
                id=s["id"],
                level=s["level"],
                title=s["title"],
                body_md="".join(s["body"]).strip(),
            )
            for s in sections
        ),
    )
````

Two decisions worth naming. **Ids are deterministic** (`section`, `section-2`, …) because the reader's selected section must survive an unrelated rerun; a hash of position would not. **A document with no headings returns one fallback section rather than an empty one**, so `Read full note` always has something to render and the no-heading case is not a special path for every caller to remember.
- [ ] **Step 4: Run to verify it passes**

Run: `"$PY" -m pytest tests/test_review_document.py -v`
Expected: PASS.

- [ ] **Step 5: Add a purity guard**

```python
def test_the_parser_imports_nothing_from_streamlit_or_the_services():
    source = Path("src/tradelens/ui/components/review_document.py").read_text()
    for banned in ("import streamlit", "from src.tradelens.services", "requests"):
        assert banned not in source
```

- [ ] **Step 6: Run tests, lint, commit**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/ && "$PY" -m black --check src/ scripts/
git add src/tradelens/ui/components/review_document.py tests/test_review_document.py
git commit -m "feat(ai-reviews): pure Markdown document model for generated notes"
```

- [ ] **Step 7: Update the handoff and release the lock**

---

## Task 12: AI Reviews — one reading shell for three lenses

**Files:**
- Create: `src/tradelens/ui/components/review_reader.py`, `tests/test_review_reader.py`
- Modify: `src/tradelens/ui/pages/6_Insights.py:222-320,446-600`
- Test: `tests/test_insights_page.py`, `tests/test_ai_review.py`

**Interfaces:**
- Consumes: `parse_review_markdown`, `ReviewDocument` (Task 11); `ResearchNote`, `ResearchFinding`, `EvidenceItem`, `render_research_note`, `render_evidence_rail`, `render_note_skeleton`, `render_evidence_disclosure`, `MetricItem`, `render_kpi_strip`.
- Produces:
  - `review_reader.ReviewView(title: str, sample: str, thesis_md: str, document: ReviewDocument, evidence: EvidenceItem, actions: Sequence[str], evidence_used: Sequence[str])` — frozen. The thesis is lifted out of the document, so `document.sections` never repeats it.
  - `review_reader.view_from_note(note: ResearchNote) -> ReviewView`
  - `review_reader.view_from_markdown(*, title, sample, content_md, evidence, actions, evidence_used) -> ReviewView`
  - `review_reader.clamp_section(*, index: int, total: int) -> int`
  - `review_reader.build_note_regions(view: ReviewView) -> str` — **pure**, returns the five regions' chrome HTML with every caller value escaped, exactly as `workspace.py`'s builders do. Generated Markdown is *not* embedded here; it is handed separately to `st.markdown` with HTML off. This is what makes the shell testable without a browser.
  - `review_reader.render_review_reader(st, view: ReviewView, *, state_key: str) -> None` — the only Streamlit-touching entry point.

Resolves spec findings D5, D6, D7, D8.

- [ ] **Step 1: Write the failing adapter and shell tests**

Create `tests/test_review_reader.py`:

```python
"""One reading shell, two adapters.

Patterns builds a structured ResearchNote; Weekly and Daily produce
content_md. Both must arrive at the same five-region note anatomy, or the
product has two different ideas of what a review looks like (D6).
"""

from src.tradelens.ui.components.review_reader import (
    ReviewView,
    build_note_regions,
    view_from_markdown,
    view_from_note,
)
from src.tradelens.ui.components.workspace import (
    EvidenceItem,
    ResearchFinding,
    ResearchNote,
)

_EVIDENCE = EvidenceItem(
    evidence="18 completed trades", sample="n=18 of 25", confidence="medium",
    limitation="One session dominates the sample.",
)


def test_a_structured_note_and_markdown_reach_the_same_shape():
    note = ResearchNote(
        title="Patterns", thesis="You size up after losses.",
        findings=(ResearchFinding(1, "Revenge sizing", "body", _EVIDENCE),),
        actions=("Re-read Tuesday's entries.",), evidence_used=("25 trades",),
        sample="n=25", limitation="Small sample.",
    )
    md = view_from_markdown(
        title="Weekly Recap", sample="n=25",
        content_md="You size up after losses.\n\n## Revenge sizing\nbody",
        evidence=_EVIDENCE, actions=("Re-read Tuesday's entries.",),
        evidence_used=("25 trades",),
    )
    assert isinstance(view_from_note(note), ReviewView)
    assert view_from_note(note).thesis_md.strip() == md.thesis_md.strip()


def test_the_thesis_is_the_lead_paragraph_and_is_not_repeated_in_a_section():
    view = view_from_markdown(
        title="Weekly Recap", sample="n=9",
        content_md="Lead claim.\n\n## Detail\nbody",
        evidence=_EVIDENCE, actions=(), evidence_used=(),
    )
    assert view.thesis_md == "Lead claim."
    assert "Lead claim." not in view.document.sections[0].body_md


def test_the_evidence_rail_appears_once_per_note_not_under_every_paragraph():
    view = view_from_markdown(
        title="Weekly Recap", sample="n=9",
        content_md="Lead.\n\n## A\na\n\n## B\nb",
        evidence=_EVIDENCE, actions=(), evidence_used=(),
    )
    html = build_note_regions(view)
    assert html.count("tl-evidence-rail") == 1


def test_read_full_note_renders_every_original_section():
    """Generated text is never truncated or discarded."""
    content = "Lead.\n\n## A\nalpha\n\n## B\nbeta"
    view = view_from_markdown(
        title="W", sample="n=1", content_md=content,
        evidence=_EVIDENCE, actions=(), evidence_used=(),
    )
    full = view.thesis_md + "".join(s.body_md for s in view.document.sections)
    for token in ("Lead.", "alpha", "beta"):
        assert token in full


def test_the_active_section_clamps_when_a_regenerated_note_has_fewer_sections():
    from src.tradelens.ui.components.review_reader import clamp_section  # noqa

    assert clamp_section(index=5, total=2) == 1
    assert clamp_section(index=-1, total=2) == 0
    assert clamp_section(index=0, total=0) == 0
```

- [ ] **Step 2: Write the failing regeneration tests**

Append to `tests/test_insights_page.py`:

```python
def test_daily_debrief_regeneration_keeps_the_prior_note_on_failure():
    """D5: _render_daily_lens popped the cache key BEFORE regenerating, so a
    failed regeneration destroyed the review the trader already had. Weekly
    does this correctly — Daily must match it."""
    source = Path("src/tradelens/ui/pages/6_Insights.py").read_text()
    body = function_source(source, "_render_daily_lens")
    pop = body.find(".pop(")
    run = body.find("_run_daily_debrief(")
    assert pop == -1 or run < pop, "cache cleared before regeneration"


def test_all_three_lenses_render_the_same_period_stats_strip():
    """D7: Weekly and Daily had a 5-cell strip; Patterns had none."""
    source = Path("src/tradelens/ui/pages/6_Insights.py").read_text()
    for lens in ("_render_patterns_lens", "_render_weekly_lens", "_render_daily_lens"):
        assert "_note_stats(" in function_source(source, lens)


def test_the_regenerate_control_is_disabled_while_a_call_is_in_flight():
    """D8: the button stayed live and showed no inline progress."""
    source = Path("src/tradelens/ui/pages/6_Insights.py").read_text()
    assert "disabled=" in near(source, "Regenerate")


def test_the_skeleton_appears_only_when_there_is_no_prior_note():
    source = Path("src/tradelens/ui/pages/6_Insights.py").read_text()
    assert "render_note_skeleton" in source
    assert near(source, "render_note_skeleton").count("if ") >= 1
```

- [ ] **Step 3: Run both sets to verify failure**

Run: `"$PY" -m pytest tests/test_review_reader.py tests/test_insights_page.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement the reading shell**

Create `review_reader.py` with the five-region note anatomy from spec §7.2, each region appearing at most once per note and taking a distinct form:

1. **Note header** — title plus sample line.
2. **Primary thesis** — a single lead paragraph at display weight, 68–72 ch measure, visible before anything else.
3. **Supporting findings** — numbered `render_research_finding`, one section shown at a time.
4. **Evidence Rail** — `render_evidence_rail`, hairline, indented, mono metadata, **once per note**.
5. **Limitations, then next review actions** — a plain block, then a short list.

Then, collapsed below: `render_evidence_disclosure` — what the note was based on, never how it was produced. Model reasoning, prompt content, token counts, and call cost are operator data and never enter the user path.

Section navigation uses native Streamlit controls only. Desktop: a narrow index column beside one readable content column. Phone: a stacked selector above the content, no horizontal scroll, no offscreen sticky panel. `Read full note` always renders every original section. The active section survives an unrelated rerun and clamps safely when a regenerated document has fewer sections.

- [ ] **Step 5: Rewire the three lenses**

Replace `_render_generated_note` (`6_Insights.py:264`) with `render_review_reader`. Patterns feeds `view_from_note`; Weekly and Daily feed `view_from_markdown`. Give all three the same `_note_stats` period strip: Trades, Win rate, Net P&L, Profit factor, Edge leak (D7).

Fix D5: in `_render_daily_lens`, do not pop `cache_key` before calling `_run_daily_debrief`. Keep the note and replace it only on success, exactly as Weekly already does.

Fix D8: disable the regenerate control while a call is in flight and show an inline "Updating review…" announced politely, with no page jump. The skeleton appears only when there is no prior note.

Demote the lens radio below the current question's `render_section_header`.

- [ ] **Step 6: Preserve the interaction states**

Wire spec §7.5 exactly: first load with no note → `render_note_skeleton` holding the note's geometry with `role="status"`, `aria-busy`, `aria-live="polite"`, and a hidden "Writing this review…"; note ready → thesis and selected section immediately; regenerating → prior note stays; regeneration succeeded → replace and clear the error slot; domain error → prior note stays with the trader-safe specific reason; unexpected error → prior note stays with fixed generic recovery copy, exception logged and never rendered; empty with no trades → one empty state and a path to log a trade; empty in-period → states it plainly and offers a different period; sparse below `TRADES_FOR_REVIEW` → Weekly is not auto-generated and states what would unlock it; AI unavailable → says so and states the trades are still in the Journal.

Confidence bands stay `≥20 high, ≥10 medium, else low` (`_CONF_BY_SAMPLE`). Sample, confidence, period, and limitation travel with the claim.

- [ ] **Step 7: Confirm the safety boundary is untouched**

```python
def test_the_reading_shell_added_no_prompt_call_or_service_edit():
    source = Path("src/tradelens/ui/components/review_reader.py").read_text()
    for banned in ("import anthropic", "from src.tradelens.prompts", "generate_"):
        assert banned not in source, f"the shell reaches past presentation: {banned}"


def test_generated_prose_never_takes_the_unsafe_html_path():
    """Authored chrome may use unsafe_allow_html; model output may not."""
    source = Path("src/tradelens/ui/components/review_reader.py").read_text()
    for anchor in ("thesis_md", "body_md"):
        assert "unsafe_allow_html=True" not in near(source, anchor)
```

Model prose goes through `st.markdown` with HTML disabled. Cache keys and user scoping are unchanged. "Reflection only — never signals or advice" stays in the masthead subtitle and is not repeated in every section.

- [ ] **Step 8: Motion**

One 160–180 ms opacity/4 px transition, and only when the user changes section. No animation on initial load, regeneration, errors, or under reduced motion.

- [ ] **Step 9: Run tests, lint, browser-check**

Browser: load each lens, regenerate Daily Debrief, and confirm the prior note stays on screen with the control disabled during the call. Then force a domain failure and confirm the prior note survives and the reason is trader-safe.

- [ ] **Step 10: Commit**

```bash
git add src/tradelens/ui/components/review_reader.py src/tradelens/ui/pages/6_Insights.py \
        tests/test_review_reader.py tests/test_insights_page.py tests/test_ai_review.py
git commit -m "feat(ai-reviews): one reading shell and non-destructive regeneration"
```

- [ ] **Step 11: Update the handoff and release the lock**

---

## Task 13: Strategy Profile and Settings

**Files:**
- Modify: `src/tradelens/ui/pages/5_Strategy.py`, `src/tradelens/ui/pages/9_Settings.py`, `src/tradelens/ui/components/auth_screen.py`
- Test: `tests/test_strategy.py`, `tests/test_app_settings.py`, `tests/test_auth_screen.py`, `tests/test_account_ui.py`

**Interfaces:**
- Consumes: Task 1–3 tokens and controls.
- Produces: no new interface.

- [ ] **Step 1: Confirm the persistence scenarios still pass first**

Run: `"$PY" -m pytest tests/test_strategy.py tests/test_app_settings.py tests/test_account_deletion.py -v`
Expected: PASS. These cover starter persistence, blank-name refusal, corrected save, untouched-field preservation, and contained write failure with no DSN leak. They are the contract this task must not break.

- [ ] **Step 2: Write the failing Danger Zone test**

```python
def test_the_danger_zone_is_one_contained_perimeter():
    """Both disclosures, their confirmation fields, and their destructive
    buttons sit inside one boundary drawn with the strong line token."""
    css = ds.build_css()
    zone = [b for b in css.split("}") if "tl-danger-zone" in b]
    assert zone
    assert any("--tl-line-strong" in b for b in zone)


def test_warnings_outside_the_danger_zone_are_not_red():
    """Red is reserved for the Danger Zone and destructive actions."""
    source = Path("src/tradelens/ui/pages/9_Settings.py").read_text()
    assert "TL_DANGER" not in outside(source, "danger_zone")
```

- [ ] **Step 3: Run to verify failure, then implement Strategy Profile**

Retain the 6-of-6 completion truth, saved facets, starter behaviour, five accordions, one local error slot, and one restrained save action. Dark treatment uses subtle panels and hairlines so opened accordions do not read as a stack of oversized cards. Preserve the scoped 180 ms accordion reveal with its no-replay and reduced-motion behaviour. The completion state must be legible from the Partner's empty state — the Strategy Profile is one of the Partner's three context sources.

- [ ] **Step 4: Implement Settings**

Four sections: Profile, Preferences, Data, Danger Zone. Settings is the quietest destination — no chart, no promotional banner, no bright primary CTA. Warnings are amber/neutral. One contained `TL_LINE_STRONG` perimeter around both destructive disclosures. Exact-match confirmation preserved for delete-all-trades and delete-account. Destructive controls are spatially and visually separated from normal controls. Import/export stays tenant-scoped with sanitised import failures. Sample data load and clear stay scoped to the authenticated user. No deployment secret name is surfaced more prominently than required — prefer user-facing recovery guidance over operator jargon. Where an action is reversible, offer undo; where it is not, say so before it runs.

- [ ] **Step 5: Implement the auth surface**

Hierarchy: brand → one positioning sentence → mode toggle → form → recovery path → compliance line. Sign in with `autocomplete` set and a show/hide password toggle. Create account adds confirmation and an optional recovery email, stating the consequence of omitting it. Reset request must not reveal whether an address is registered. SMTP unconfigured says it could not send and never pretends success — already correct, preserve it. Errors are persistent and inline with `role="alert"`, never a toast; success is a persistent confirmation. Visible labels, never placeholder-only. First invalid field receives focus after a failed submit. 44 px minimum input height. The mode toggle is a real radio/segmented control with `aria` state. No AI Partner, no rail, no bottom nav on this surface.

- [ ] **Step 6: Run tests, lint, browser-check, commit**

Browser: change and save the Strategy Name in an isolated database, navigate away, return, and verify persistence. Open both Settings accordions and confirm the typed `DELETE` and `DELETE MY ACCOUNT` gates render — **execute neither**.

```bash
git add src/tradelens/ui/pages/5_Strategy.py src/tradelens/ui/pages/9_Settings.py \
        src/tradelens/ui/components/auth_screen.py tests/test_strategy.py \
        tests/test_app_settings.py tests/test_auth_screen.py
git commit -m "feat(ui): dark Strategy Profile, Settings, and auth surface"
```

- [ ] **Step 7: Update the handoff and release the lock**

---

## Task 14: AI Partner — the desktop drawer

**Files:**
- Create: `src/tradelens/ui/components/partner_panel.py` (rendering), `src/tradelens/ui/components/partner_turn.py` (Streamlit-free send path), `tests/test_partner_panel.py`, `tests/test_partner_turn.py`
- Modify: `src/tradelens/ui/design_system.py` (launcher and drawer selectors)

**Interfaces:**
- Consumes: `build_global_partner_context(*, user_id)`, `PartnerContext`, `PartnerEvidenceSource` (Task 4); `partner_reply(messages, *, trade_context, strategy_profile, image_b64, per_trade_qa) -> tuple[str, Usage]` and `PartnerError` (`partner.py:272`, `:135`); `log_ai_usage(feature, usage, user_id=None)` (`cost.py:41`); `current_user_id()`; `TL_Z_PARTNER`.
- Produces, in `partner_turn.py` (pure):
  - `UNEXPECTED_ERROR: str`, `CONTEXT_USED_LABEL: str = "Context used"`, `CONTEXT_FIELD: str`, `API_TURN_FIELDS: tuple[str, ...]`
  - `history_key(user_id) -> str`, `error_key(user_id) -> str`
  - `TurnResult(ok, reply, error, usage_logged, context_used)` — frozen
  - `send_turn(state, *, user_id, text, build_context, partner_reply, log_ai_usage, partner_error, log_exception=None) -> TurnResult`
  - `to_api_messages(history) -> list[dict]` — projects stored turns to `role`/`content` only
  - `context_used_for(turn) -> tuple[str, ...]` — the labels one stored assistant turn was answered from
  - `context_used_rows(context) -> tuple[str, ...]`
- Produces, in `partner_panel.py` (rendering):
  - `PARTNER_OPEN_KEY: str = "partner_open"`
  - `SUGGESTED_QUESTIONS: tuple[str, ...]` — 3–4 retrospective prompts
  - `EMPTY_STATE_BODY: str` — states the three context sources and that the conversation is not saved
  - `render_partner_launcher(st) -> None`
  - `render_partner_drawer(st) -> None`
  - `render_partner_body(st, *, surface: str) -> None` — shared by the drawer and Task 15's page

Task 15 imports `history_key` from `partner_turn`, not from `partner_panel`.

The drawer applies at **every sidebar-navigation width (≥768)** per the live preflight. There is no mobile launcher and no bottom sheet.

- [ ] **Step 1: Write the failing safety tests**

Create `tests/test_partner_panel.py`:

```python
"""The Partner surface owns presentation and nothing else.

Handoff §1 approves the global Partner only through the existing service.
These tests are the boundary: a new endpoint, a direct SDK import, an
unscoped query, or a double usage log is a scope violation, not a bug.
"""

from pathlib import Path

import pytest

from src.tradelens.ui.components import partner_panel
from tests.source_probe import function_source, near

_SOURCE = Path("src/tradelens/ui/components/partner_panel.py").read_text()


@pytest.mark.parametrize(
    "banned", ["import anthropic", "from anthropic", "Anthropic(", "requests.post"]
)
def test_the_surface_never_reaches_the_model_directly(banned):
    assert banned not in _SOURCE


def test_the_surface_opens_no_data_access_path_of_its_own():
    for banned in ("get_session", "select(", "session.query", "text("):
        assert banned not in _SOURCE, f"{banned}: context comes from the adapter only"


def test_context_is_built_with_the_authenticated_user_id():
    assert "build_global_partner_context(user_id=" in _SOURCE


def test_partner_reply_is_called_in_general_reflective_mode():
    assert "per_trade_qa=False" in _SOURCE


def test_usage_is_logged_exactly_once_per_completed_response():
    assert _SOURCE.count("log_ai_usage(") == 1
    assert 'log_ai_usage("AI Partner"' in _SOURCE
    assert "user_id=" in near(_SOURCE, "log_ai_usage(")


def test_model_output_never_takes_the_unsafe_html_path():
    assert "unsafe_allow_html=True" not in near(_SOURCE, "reply")


def test_every_suggested_question_is_retrospective():
    forward = (
        "should i", "will ", "predict", "forecast", "entry", "target",
        "buy", "sell", "next trade", "setup today",
    )
    for chip in partner_panel.SUGGESTED_QUESTIONS:
        lowered = chip.lower()
        for token in forward:
            assert token not in lowered, f"forward-looking chip: {chip!r}"


def test_the_empty_state_says_the_conversation_is_not_saved():
    assert "not saved" in partner_panel.EMPTY_STATE_BODY.lower()


def test_history_is_scoped_per_user():
    from src.tradelens.ui.components import partner_turn

    assert partner_turn.history_key(7) != partner_turn.history_key(8)


def test_the_drawer_does_not_claim_modal_semantics_it_cannot_enforce():
    """No focus trap exists without script, so claiming aria-modal would be
    worse than not claiming it (spec §8.2)."""
    assert 'aria-modal' not in _SOURCE
    assert 'aria-label="AI Partner"' in _SOURCE


def test_the_close_control_is_first_in_the_drawer_dom_order():
    drawer = function_source(_SOURCE, "render_partner_drawer")
    assert drawer.index("Close") < drawer.index("SUGGESTED_QUESTIONS")
```

- [ ] **Step 2: Run to verify failure**

Run: `"$PY" -m pytest tests/test_partner_panel.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the launcher and drawer**

A real Streamlit button inside a keyed container, positioned by scoped CSS. The launcher must be a real Streamlit widget, not authored HTML, so it stays keyboard-reachable and needs no script:

```
st.container(key="tl_partner_launcher")  →  .st-key-tl_partner_launcher
    position: fixed; right: var(--tl-space-6); bottom: var(--tl-space-6);
    z-index: var(--tl-z-partner);
```

**Open/close is state-driven, not CSS-driven.** `st.session_state["partner_open"]` gates whether the drawer renders at all. Closed means the drawer's widgets are not in the DOM and therefore cannot be tabbed to — the same guarantee the mobile `More` sheet already provides. Opening costs one rerun, which is how Streamlit works and is acceptable.

The drawer is `<aside>` with `aria-label="AI Partner"`, **no `aria-modal`**, no blocking scrim, and a visible ≥44×44 Close control first in DOM order. There is no Esc-to-close without script, so the visible control is mandatory.

- [ ] **Step 4: Implement the send path**

The send path lives in `src/tradelens/ui/components/partner_turn.py`, **free of Streamlit**, so its orderings can be proved without a browser. `partner_panel.py` renders and wires the real collaborators. The split follows `trade_wizard.py`: the rules that must be right do not need a browser to prove, and proving them in one costs a suite nobody runs.

**Verified 2026-08-04: this module and its tests were run together — `31 passed`, Ruff clean, Black clean. Four guarantees were mutation-checked** by reverting each in turn and confirming the suite fails: context assembly outside containment (3 failures), uncontained usage logging (1), unprojected history (1), and labels not stored per turn (2).

```python
"""The AI Partner send path, kept free of Streamlit so it can be tested.

`partner_panel.py` renders; this decides what one turn does. The split follows
`trade_wizard.py`: the rules that must be right do not need a browser to prove,
and proving them in one costs a suite that nobody runs.

Five behaviours here are load-bearing and each is pinned by a test:

1. **The user's turn is appended before anything can fail.** A failed turn must
   leave the trader's question on screen; re-typing it is the one thing an error
   must never cost.
2. **Context construction is inside the containment.** Assembling context opens
   a database session, so it can fail with a driver error carrying a DSN. That
   failure has to be caught exactly like a model failure, not left to escape as
   a raw exception onto the page.
3. **Usage logging is contained separately, after the reply.** A cost-table
   write that fails must not discard an answer the trader already paid for. The
   turn stays successful; only `usage_logged` records the truth.
4. **Each assistant turn carries the context it was answered from.** The labels
   are stored on the turn, so a rerun re-renders the right list under the right
   answer instead of showing the newest context under every one.
5. **Stored history is projected to role and content before the model sees it.**
   Presentation metadata is ours, not the API's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, MutableMapping, Optional, Sequence, Tuple

# What the UI shows when something outside the domain fails. Fixed copy: the
# exception may carry a DSN, a driver string, or an API key.
UNEXPECTED_ERROR = "AI is temporarily unavailable. Please try again."

HISTORY_PREFIX = "partner_history_"
ERROR_PREFIX = "partner_error_"

# The heading the drawer and the Partner page put above the record list. It is
# part of the contract, not a caption choice — see context_used_rows.
CONTEXT_USED_LABEL = "Context used"

# Where a turn keeps the labels it was answered from. Stripped before the
# history reaches the model.
CONTEXT_FIELD = "context_used"

# The only keys the Anthropic message API may receive from a stored turn.
API_TURN_FIELDS = ("role", "content")


def history_key(user_id: object) -> str:
    """Per-user history slot. Session state can outlive a sign-out in one tab,
    so the key carries the owner rather than trusting the session."""
    return f"{HISTORY_PREFIX}{user_id}"


def error_key(user_id: object) -> str:
    return f"{ERROR_PREFIX}{user_id}"


@dataclass(frozen=True)
class TurnResult:
    """What the render path needs to know about the turn that just ran."""

    ok: bool
    reply: Optional[str] = None
    error: Optional[str] = None
    usage_logged: bool = False
    context_used: Tuple[str, ...] = ()


def to_api_messages(history: Sequence[dict]) -> List[dict]:
    """Project stored turns down to what the model API accepts.

    Stored turns carry presentation metadata — the context labels each answer
    was produced from. That belongs to the UI. Sending it would put unrequested
    fields into the API payload and, worse, feed the model a list of record
    labels as though it were part of the conversation.
    """
    return [
        {field: turn[field] for field in API_TURN_FIELDS if field in turn}
        for turn in history
    ]


def context_used_for(turn: dict) -> Tuple[str, ...]:
    """The labels a single stored assistant turn was answered from.

    Empty for a user turn, and empty for an assistant turn produced when the
    trader had no records yet — in which case the UI renders no heading at all
    rather than an empty one.
    """
    return tuple(turn.get(CONTEXT_FIELD) or ())


def context_used_rows(context) -> Tuple[str, ...]:
    """Labels for the records fed into the prompt — not citations for an answer.

    `partner_reply` returns only text and usage. It cannot report which records
    a given sentence drew on, so presenting these as per-answer citations would
    assert a relationship the service never established. They are labelled
    "Context used" for that reason, and the wording is part of the contract
    rather than a caption choice.
    """
    return tuple(source.label for source in getattr(context, "evidence_sources", ()))


def send_turn(
    state: MutableMapping,
    *,
    user_id: int,
    text: str,
    build_context: Callable,
    partner_reply: Callable,
    log_ai_usage: Callable,
    partner_error: type,
    log_exception: Optional[Callable] = None,
) -> TurnResult:
    """Run one Partner turn against the authenticated user's own context.

    Every collaborator is injected rather than imported here, so a test can
    prove the ordering without a database, a model, or a cost table. The page
    wires the real ones.
    """
    question = (text or "").strip()
    if not question:
        return TurnResult(ok=False, error=None)

    history: List[Dict] = state.setdefault(history_key(user_id), [])
    state.pop(error_key(user_id), None)

    # 1. The trader's turn lands first and stays, whatever happens next.
    history.append({"role": "user", "content": question})

    def _contain(exc_label: str) -> TurnResult:
        """Log the failure, store fixed copy, and tell the trader nothing about
        the driver, the DSN, or the key that produced it."""
        if log_exception is not None:
            log_exception(exc_label)
        state[error_key(user_id)] = UNEXPECTED_ERROR
        return TurnResult(ok=False, error=UNEXPECTED_ERROR)

    # 2. Context assembly opens a session, so it fails like anything else that
    #    touches a database — inside the containment, never outside it.
    try:
        context = build_context(user_id=user_id)
    except partner_error as exc:
        state[error_key(user_id)] = str(exc)
        return TurnResult(ok=False, error=str(exc))
    except Exception:
        return _contain("AI Partner context assembly failed")

    labels = context_used_rows(context)

    try:
        reply, usage = partner_reply(
            to_api_messages(history),
            trade_context=context.context_text,
            strategy_profile=context.strategy_profile,
            per_trade_qa=False,
        )
    except partner_error as exc:
        # Domain failure: the service already phrased this for a trader.
        state[error_key(user_id)] = str(exc)
        return TurnResult(ok=False, error=str(exc))
    except Exception:
        return _contain("AI Partner turn failed")

    # 3. The answer is the trader's now. Append it before anything else can go
    #    wrong, and carry the labels it was produced from.
    history.append({"role": "assistant", "content": reply, CONTEXT_FIELD: list(labels)})

    # 4. Cost logging is bookkeeping. If it fails, the answer still stands; the
    #    result records that the write did not happen rather than pretending.
    usage_logged = False
    try:
        log_ai_usage("AI Partner", usage, user_id=user_id)
        usage_logged = True
    except Exception:
        if log_exception is not None:
            log_exception("AI Partner usage logging failed")

    return TurnResult(
        ok=True, reply=reply, usage_logged=usage_logged, context_used=labels
    )
```

**Three containment boundaries, not one.** Context assembly opens a database session, so it can fail with a driver error carrying a DSN — it sits *inside* the containment, not before it. The model call is contained separately. Usage logging is contained separately again and **after** the reply is already stored: a cost-table write that fails must not discard an answer the trader has already been given, so the turn stays `ok=True` and only `usage_logged` records that the write did not happen.

**Evidence is labelled "Context used", and that wording is a contract.** `partner_reply` returns `(reply_text, usage)` — nothing more. It cannot report which records a given sentence drew on, so rendering the adapter's records as per-answer citations would assert a relationship the service never established. If per-answer sourcing is ever wanted it is a Codex-owned service change, not a UI relabel.

**Labels are stored on the turn they belong to.** Each assistant turn carries the list it was answered from, so a rerun re-renders the right records under the right answer instead of putting the newest context under every one. `to_api_messages` then projects stored turns down to `role` and `content` before the service sees them — presentation metadata is ours, and feeding a model a list of record labels as if it were conversation would be a quiet corruption of the prompt.

- [ ] **Step 5: Write the send-path tests**

Create `tests/test_partner_turn.py`:

```python
"""The send path's orderings, pinned."""

from dataclasses import dataclass
from typing import Optional, Tuple

import pytest
from src.tradelens.ui.components.partner_turn import (
    CONTEXT_FIELD,
    UNEXPECTED_ERROR,
    TurnResult,
    context_used_for,
    context_used_rows,
    error_key,
    history_key,
    send_turn,
    to_api_messages,
)


class FakePartnerError(Exception):
    pass


@dataclass(frozen=True)
class FakeSource:
    kind: str
    record_id: int
    user_id: int
    label: str
    occurred_on: Optional[str] = None


@dataclass(frozen=True)
class FakeContext:
    context_text: str = "## Journal notes\n- 2026-08-01: sized up after a loss"
    strategy_profile: Optional[dict] = None
    evidence_sources: Tuple[FakeSource, ...] = ()
    completed_trade_count: int = 6
    journal_entry_count: int = 6


def _recorder():
    calls = []

    def fn(*args, **kwargs):
        calls.append((args, kwargs))

    fn.calls = calls
    return fn


def _reply_ok(*_a, **_k):
    return "You sized up after two losses.", {"input_tokens": 10, "output_tokens": 4}


def _wire(**overrides):
    wiring = dict(
        build_context=lambda *, user_id: FakeContext(),
        partner_reply=_reply_ok,
        log_ai_usage=_recorder(),
        partner_error=FakePartnerError,
        log_exception=_recorder(),
    )
    wiring.update(overrides)
    return wiring


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------
def test_a_successful_turn_appends_both_turns_in_order():
    state = {}
    result = send_turn(state, user_id=7, text="What did I do well?", **_wire())
    assert isinstance(result, TurnResult) and result.ok
    history = state[history_key(7)]
    assert [t["role"] for t in history] == ["user", "assistant"]
    assert history[0]["content"] == "What did I do well?"
    assert history[1]["content"] == "You sized up after two losses."


def test_partner_reply_receives_exactly_the_agreed_arguments():
    seen = {}

    def spy(messages, **kwargs):
        seen["messages"] = messages
        seen["kwargs"] = kwargs
        return _reply_ok()

    context = FakeContext(strategy_profile={"id": 3, "name": "playbook"})
    send_turn(
        {},
        user_id=7,
        text="What rule did I break?",
        **_wire(partner_reply=spy, build_context=lambda *, user_id: context),
    )
    assert seen["kwargs"] == {
        "trade_context": context.context_text,
        "strategy_profile": context.strategy_profile,
        "per_trade_qa": False,
    }
    assert [t["role"] for t in seen["messages"]] == ["user"]


def test_the_model_sees_the_user_turn_it_is_answering():
    """The history passed to the service must already contain the question."""
    seen = {}

    def spy(messages, **kwargs):
        seen["last"] = messages[-1]
        return _reply_ok()

    send_turn({}, user_id=7, text="Summarize this week.", **_wire(partner_reply=spy))
    assert seen["last"] == {"role": "user", "content": "Summarize this week."}


def test_the_service_cannot_mutate_the_stored_history():
    """A projection goes to the service; trim_history rewrites what it is given."""
    captured = {}

    def spy(messages, **kwargs):
        captured["messages"] = messages
        messages.clear()
        return _reply_ok()

    state = {}
    send_turn(state, user_id=7, text="hello", **_wire(partner_reply=spy))
    assert captured["messages"] == []
    assert len(state[history_key(7)]) == 2


def test_usage_is_logged_exactly_once_with_the_authenticated_user():
    logger = _recorder()
    send_turn({}, user_id=7, text="hi", **_wire(log_ai_usage=logger))
    assert len(logger.calls) == 1
    args, kwargs = logger.calls[0]
    assert args[0] == "AI Partner"
    assert kwargs == {"user_id": 7}


def test_a_prior_error_is_cleared_when_a_turn_succeeds():
    state = {error_key(7): "stale failure"}
    send_turn(state, user_id=7, text="hi", **_wire())
    assert error_key(7) not in state


# ---------------------------------------------------------------------------
# Failure preserves the trader's work
# ---------------------------------------------------------------------------
def test_a_domain_error_keeps_the_question_and_shows_the_service_reason():
    def boom(*_a, **_k):
        raise FakePartnerError("The review period has no completed trades.")

    state = {}
    result = send_turn(
        state, user_id=7, text="Why did I lose?", **_wire(partner_reply=boom)
    )
    assert result.ok is False
    assert result.error == "The review period has no completed trades."
    history = state[history_key(7)]
    assert [t["role"] for t in history] == ["user"]
    assert history[0]["content"] == "Why did I lose?"
    assert state[error_key(7)] == "The review period has no completed trades."


def test_a_domain_error_logs_no_usage():
    def boom(*_a, **_k):
        raise FakePartnerError("nope")

    logger = _recorder()
    result = send_turn(
        {}, user_id=7, text="hi", **_wire(partner_reply=boom, log_ai_usage=logger)
    )
    assert logger.calls == []
    assert result.usage_logged is False


def test_an_unexpected_error_never_reaches_the_trader():
    def boom(*_a, **_k):
        raise RuntimeError(
            "psycopg2 OperationalError dsn=postgresql://u:pw@host/db key=sk-ant-123"
        )

    state = {}
    logger = _recorder()
    exc_log = _recorder()
    result = send_turn(
        state,
        user_id=7,
        text="hi",
        **_wire(partner_reply=boom, log_ai_usage=logger, log_exception=exc_log),
    )
    assert result.error == UNEXPECTED_ERROR
    assert state[error_key(7)] == UNEXPECTED_ERROR
    for leak in ("psycopg2", "postgresql://", "sk-ant-", "OperationalError"):
        assert leak not in state[error_key(7)]
    assert logger.calls == []
    assert len(exc_log.calls) == 1


def test_an_unexpected_error_still_keeps_the_question():
    def boom(*_a, **_k):
        raise RuntimeError("kaboom")

    state = {}
    send_turn(state, user_id=7, text="Keep me", **_wire(partner_reply=boom))
    assert state[history_key(7)][0]["content"] == "Keep me"


def test_prior_turns_survive_a_failure():
    def boom(*_a, **_k):
        raise FakePartnerError("nope")

    state = {}
    send_turn(state, user_id=7, text="first", **_wire())
    send_turn(state, user_id=7, text="second", **_wire(partner_reply=boom))
    history = state[history_key(7)]
    assert [t["role"] for t in history] == ["user", "assistant", "user"]


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("blank", ["", "   ", "\n", None])
def test_a_blank_question_is_not_sent(blank):
    logger = _recorder()
    called = _recorder()
    result = send_turn(
        {}, user_id=7, text=blank, **_wire(partner_reply=called, log_ai_usage=logger)
    )
    assert result.ok is False
    assert called.calls == [] and logger.calls == []


def test_history_is_scoped_per_user():
    assert history_key(7) != history_key(8)
    state = {}
    send_turn(state, user_id=7, text="mine", **_wire())
    send_turn(state, user_id=8, text="theirs", **_wire())
    assert state[history_key(7)][0]["content"] == "mine"
    assert state[history_key(8)][0]["content"] == "theirs"


# ---------------------------------------------------------------------------
# Evidence presentation is honest about what the service proved
# ---------------------------------------------------------------------------
def test_context_used_rows_report_the_records_fed_to_the_prompt():
    context = FakeContext(
        evidence_sources=(
            FakeSource("journal", 1, 7, "Journal note - EURUSD 2026-08-01"),
            FakeSource("trade", 2, 7, "EURUSD 2026-08-01"),
        )
    )
    assert context_used_rows(context) == (
        "Journal note - EURUSD 2026-08-01",
        "EURUSD 2026-08-01",
    )


def test_no_context_means_no_rows_rather_than_an_invented_one():
    assert context_used_rows(FakeContext()) == ()


def test_the_label_states_context_used_not_a_citation_claim():
    """partner_reply returns text and usage only. It cannot report which
    records a sentence drew on, so the heading promises context, not sourcing.

    Asserted on the API surface rather than on prose: the docstrings explain
    why citations are not claimed, and a text scan cannot tell an explanation
    from a claim.
    """
    from src.tradelens.ui.components import partner_turn

    assert partner_turn.CONTEXT_USED_LABEL == "Context used"
    lowered = partner_turn.CONTEXT_USED_LABEL.lower()
    assert "cite" not in lowered and "source" not in lowered


def test_no_public_name_promises_per_answer_sourcing():
    import ast

    from src.tradelens.ui.components import partner_turn

    tree = ast.parse(open(partner_turn.__file__).read())
    names = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    ] + [
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    ]
    for name in names:
        low = name.lower()
        assert "citation" not in low and "cited" not in low, name


# ---------------------------------------------------------------------------
# Context assembly fails inside the containment
# ---------------------------------------------------------------------------
def test_a_failing_context_build_is_contained_like_any_other_failure():
    """Assembling context opens a database session, so it can fail with a
    driver error carrying a DSN. That must not escape onto the page."""

    def boom(*, user_id):
        raise RuntimeError(
            'psycopg2.OperationalError: dsn="postgresql://tl:hunter2@db:5432/tl" '
            "key=sk-ant-api03-SECRET"
        )

    state = {}
    exc_log = _recorder()
    logger = _recorder()
    result = send_turn(
        state,
        user_id=7,
        text="What did I do well?",
        **_wire(build_context=boom, log_exception=exc_log, log_ai_usage=logger),
    )

    assert result.ok is False
    assert result.error == UNEXPECTED_ERROR
    # The question survives.
    assert [t["role"] for t in state[history_key(7)]] == ["user"]
    assert state[history_key(7)][0]["content"] == "What did I do well?"
    # Fixed copy only, nothing sensitive anywhere in state.
    assert state[error_key(7)] == UNEXPECTED_ERROR
    blob = repr(state)
    for leak in ("psycopg2", "postgresql://", "hunter2", "sk-ant-", "OperationalError"):
        assert leak not in blob, f"state leaked {leak!r}"
    # Logged exactly once, and nothing was billed.
    assert len(exc_log.calls) == 1
    assert logger.calls == []
    assert result.usage_logged is False


def test_the_model_is_never_called_when_context_assembly_fails():
    def boom(*, user_id):
        raise RuntimeError("kaboom")

    called = _recorder()
    send_turn(
        {}, user_id=7, text="hi", **_wire(build_context=boom, partner_reply=called)
    )
    assert called.calls == []


def test_a_domain_error_from_context_keeps_its_trader_safe_reason():
    def boom(*, user_id):
        raise FakePartnerError("Your Strategy Profile is not set up yet.")

    state = {}
    result = send_turn(state, user_id=7, text="hi", **_wire(build_context=boom))
    assert result.error == "Your Strategy Profile is not set up yet."
    assert state[error_key(7)] == "Your Strategy Profile is not set up yet."


# ---------------------------------------------------------------------------
# Usage-logging failure must not cost the trader their answer
# ---------------------------------------------------------------------------
def test_a_failing_usage_log_keeps_the_answer_and_the_question():
    def boom(*_a, **_k):
        raise RuntimeError("cost table write failed: dsn=postgresql://tl:pw@db/tl")

    state = {}
    exc_log = _recorder()
    result = send_turn(
        state,
        user_id=7,
        text="What rule did I break?",
        **_wire(log_ai_usage=boom, log_exception=exc_log),
    )

    assert result.ok is True
    assert result.usage_logged is False
    history = state[history_key(7)]
    assert [t["role"] for t in history] == ["user", "assistant"]
    assert history[1]["content"] == "You sized up after two losses."
    # Bookkeeping failure is logged, never rendered.
    assert len(exc_log.calls) == 1
    assert error_key(7) not in state
    assert "postgresql://" not in repr(state)


def test_a_successful_turn_reports_usage_logged():
    result = send_turn({}, user_id=7, text="hi", **_wire())
    assert result.ok is True and result.usage_logged is True


# ---------------------------------------------------------------------------
# Each answer keeps its own context
# ---------------------------------------------------------------------------
def _context_with(*labels):
    return FakeContext(
        evidence_sources=tuple(
            FakeSource("journal", i, 7, label) for i, label in enumerate(labels, 1)
        )
    )


def test_each_assistant_turn_keeps_the_context_it_was_answered_from():
    state = {}
    send_turn(
        state,
        user_id=7,
        text="first",
        **_wire(build_context=lambda *, user_id: _context_with("EURUSD 2026-08-01")),
    )
    send_turn(
        state,
        user_id=7,
        text="second",
        **_wire(
            build_context=lambda *, user_id: _context_with(
                "GBPUSD 2026-08-02", "GBPUSD 2026-08-03"
            )
        ),
    )

    history = state[history_key(7)]
    assert [t["role"] for t in history] == ["user", "assistant", "user", "assistant"]
    assert context_used_for(history[1]) == ("EURUSD 2026-08-01",)
    assert context_used_for(history[3]) == ("GBPUSD 2026-08-02", "GBPUSD 2026-08-03")


def test_the_labels_survive_a_rerun():
    """A rerun re-reads session state and re-renders from it. Each answer must
    still carry its own list rather than the newest one."""
    state = {}
    send_turn(
        state,
        user_id=7,
        text="first",
        **_wire(build_context=lambda *, user_id: _context_with("EURUSD 2026-08-01")),
    )
    send_turn(
        state,
        user_id=7,
        text="second",
        **_wire(build_context=lambda *, user_id: _context_with("GBPUSD 2026-08-02")),
    )

    # Whatever a rerun does, it starts again from this dict.
    reread = dict(state)
    rendered = [
        (t["content"], context_used_for(t))
        for t in reread[history_key(7)]
        if t["role"] == "assistant"
    ]
    assert rendered == [
        ("You sized up after two losses.", ("EURUSD 2026-08-01",)),
        ("You sized up after two losses.", ("GBPUSD 2026-08-02",)),
    ]


def test_an_empty_context_stores_no_labels_so_no_heading_renders():
    state = {}
    result = send_turn(state, user_id=7, text="hi", **_wire())
    assert result.context_used == ()
    assistant = state[history_key(7)][1]
    assert context_used_for(assistant) == ()
    assert not context_used_for(assistant), "an empty list must render no heading"


def test_a_user_turn_carries_no_context_of_its_own():
    state = {}
    send_turn(
        state,
        user_id=7,
        text="hi",
        **_wire(build_context=lambda *, user_id: _context_with("x")),
    )
    assert context_used_for(state[history_key(7)][0]) == ()


# ---------------------------------------------------------------------------
# Presentation metadata never reaches the model API
# ---------------------------------------------------------------------------
def test_stored_turns_are_projected_to_role_and_content_only():
    stored = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a", CONTEXT_FIELD: ["EURUSD 2026-08-01"]},
    ]
    assert to_api_messages(stored) == [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
    ]


def test_the_service_never_receives_the_context_field():
    seen = {}

    def spy(messages, **kwargs):
        seen["messages"] = messages
        return _reply_ok()

    state = {}
    send_turn(
        state,
        user_id=7,
        text="first",
        **_wire(build_context=lambda *, user_id: _context_with("EURUSD 2026-08-01")),
    )
    send_turn(
        state,
        user_id=7,
        text="second",
        **_wire(partner_reply=spy, build_context=lambda *, user_id: _context_with("X")),
    )

    assert all(set(m) == {"role", "content"} for m in seen["messages"])
    assert CONTEXT_FIELD not in repr(seen["messages"])
```
- [ ] **Step 6: Wire the rendered conversation**

`render_partner_body` is shared with Task 15's page. Alternating turns clearly attributed; model turns through `st.markdown` with HTML off. Three to four retrospective suggested questions derived from the existing `_PROMPT_CHIPS` pattern in `ai_trade_chat.py` — "What did I do well?", "What rule did I break?", "Summarize this trade in journal format." Never "what should I trade?". A composer with send disabled while a reply is in flight. The `Context used` list beneath **each** reply, populated from `context_used_for(turn)` — not from the newest context — and **omitted entirely when it is empty** rather than rendered as an empty heading. Rendering from the turn is what makes the list survive a rerun and stay attached to the answer it belongs to. A subordinate Clear conversation control, immediate, with the session-only consequence already stated.

The page wires the real collaborators into `send_turn`:

```python
result = send_turn(
    st.session_state,
    user_id=uid,
    text=question,
    build_context=build_global_partner_context,
    partner_reply=partner_reply,
    log_ai_usage=log_ai_usage,
    partner_error=PartnerError,
    log_exception=logging.getLogger(__name__).exception,
)
```

- [ ] **Step 7: Implement the interaction states**

Closed → launcher only. Open and empty → what the Partner can do, its three context sources, the session-only notice, and the suggested questions. No Strategy Profile → says so and links to it. No trades → says it has nothing to review yet and links to New Trade. Sending → send disabled, inline pending state, `aria-live="polite"`, prior turns stay visible. Reply ready → appended, focus not stolen. Domain error → trader-safe specific reason, prior turns stay. Unexpected error → `"AI is temporarily unavailable. Please try again."`, exception logged and never rendered. AI disabled → the launcher states the Partner is unavailable rather than opening to a dead end. Out-of-scope question → the existing scope guard's refusal, phrased as redirection to what the Partner can review.

History lives in `st.session_state` scoped per user and is never persisted. **No history list, no thread switcher, no search, and no stub of any of them** — Phase 1 authorises none of it.

- [ ] **Step 8: Run the send-path tests to verify they pass**

Run: `"$PY" -m pytest tests/test_partner_turn.py tests/test_partner_panel.py -v`
Expected: PASS — 31 send-path tests plus the surface tests from Step 1.

- [ ] **Step 9: The fixed-positioning verification — Claude-owned, required before this ships**

`position: fixed` resolves against the nearest ancestor establishing a containing block. Any ancestor carrying `transform`, `filter`, `perspective`, `contain: paint`, or `will-change` silently converts fixed into ancestor-relative. Inspect Streamlit's `stMainBlockContainer` and app-view wrappers in a live browser at **1440, 1024, and coarse 768** and confirm:

1. the launcher stays viewport-anchored while the page scrolls;
2. it survives a rerun;
3. it never overlaps the collapsed-sidebar control or the safe-area inset;
4. it does not cover the wizard's primary action or the Danger Zone's confirmation controls.

Separately, verify **stacking-context isolation**: a correct scale value still loses if an ancestor isolates it. Confirm in the browser — not by reasoning about the scale — that the Partner renders above page content and *below* the rail and bottom nav.

Record both results in the handoff with the measured values.

- [ ] **Step 10: If fixed positioning proves unstable, escalate as a recorded decision**

Degrade to a **docked Partner**: a persistent right-hand column toggled from a rail entry. This preserves every capability and every safety boundary while removing the dependency on fixed positioning. It changes placement, not scope. **Never a silent substitution** — write the decision and its evidence into the handoff and get Codex's acknowledgement before continuing.

- [ ] **Step 11: Run the full suite, lint, commit**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/ && "$PY" -m black --check src/ scripts/
git add src/tradelens/ui/components/partner_panel.py \
        src/tradelens/ui/components/partner_turn.py \
        src/tradelens/ui/design_system.py \
        tests/test_partner_panel.py tests/test_partner_turn.py
git commit -m "feat(partner): fixed bottom-right drawer at sidebar-navigation widths"
```

- [ ] **Step 12: Update the handoff with the positioning evidence and release the lock**

---

## Task 15: AI Partner — the mobile destination

**Files:**
- Create: `src/tradelens/ui/pages/7_Partner.py`
- Modify: `src/tradelens/ui/components/sidebar.py:69-78`, `src/tradelens/ui/design_system.py` (launcher media query), `tests/test_pages_boot.py` (`ALL_PAGES` gains `7_Partner.py`)
- Test: `tests/test_partner_panel.py`, `tests/test_premium_shell.py`, `tests/test_pages_boot.py`

Adding the page to `ALL_PAGES` is not bookkeeping: that list drives the parametrised boot test, so a page absent from it is a page nothing proves boots.

**Interfaces:**
- Consumes: `render_partner_body` (Task 14); `MOBILE_MORE`, `MOBILE_MORE_SLUGS`, `route_href`, `_active_slug` (`sidebar.py`).
- Produces: the `/Partner` route.

The split keys to the **navigation pattern**, not to a raw pixel value, so the Partner can never appear as a floating overlay on a width that also has a bottom bar to collide with. Mutual exclusivity is structural: at bottom-nav widths there is no Partner overlay to conflict with the `More` sheet.

- [ ] **Step 1: Write the failing navigation tests**

```python
def test_the_more_sheet_lists_the_partner():
    from src.tradelens.ui.components.sidebar import MOBILE_MORE, MOBILE_MORE_SLUGS

    assert "/Partner" in MOBILE_MORE_SLUGS
    entry = [e for e in MOBILE_MORE if e[0] == "/Partner"][0]
    assert entry[1] and entry[2], "the entry needs a label and a Material icon"


def test_the_partner_is_absent_from_the_desktop_rail():
    """One conversation must not have two entry points at one width."""
    from src.tradelens.ui.components.sidebar import PRIMARY_NAV, UTILITY_NAV

    slugs = [s for _p, s, _l, _i in PRIMARY_NAV + UTILITY_NAV]
    assert "/Partner" not in slugs


def test_streamlit_automatic_navigation_is_suppressed_for_the_new_page():
    """Verified, not assumed: sidebar.py builds a curated nav, but Streamlit
    also auto-lists page files."""
    css = ds.build_css()
    assert '[data-testid="stSidebarNav"]' in css
    assert "display: none" in near(css, '[data-testid="stSidebarNav"]')


def test_the_partner_route_is_deep_linkable_like_every_other_destination():
    from src.tradelens.ui.components.sidebar import route_href

    assert route_href("/Partner", "tok").startswith("/Partner?")


def test_no_fixed_launcher_renders_at_bottom_navigation_widths():
    css = ds.build_css()
    launcher = [b for b in css.split("}") if "tl_partner_launcher" in b]
    hidden = [b for b in launcher if "display: none" in b]
    assert hidden, "the launcher is not hidden at bottom-nav widths"
    assert "max-width: 767px" in " ".join(media_context(css, b) for b in hidden)


def test_the_conversation_survives_navigating_away_and_back():
    """Navigating away is not closing the conversation and must not clear it."""
    at = AppTest.from_file("src/tradelens/ui/pages/7_Partner.py")
    at.session_state[partner_turn.history_key(1)] = [
        {"role": "user", "content": "What did I do well?"}
    ]
    at.run()
    assert at.session_state[partner_turn.history_key(1)]
```

- [ ] **Step 2: Run to verify failure**

Run: `"$PY" -m pytest tests/test_partner_panel.py tests/test_premium_shell.py -k partner -v`
Expected: FAIL — `/Partner` is not in `MOBILE_MORE` and the page does not exist.

- [ ] **Step 3: Add the `More` entry**

In `sidebar.py`, add `("/Partner", "AI Partner", "forum")` to `MOBILE_MORE`. Order is deliberate — Analytics and Strategy Profile are work, the Partner is reflective work, and Settings stays last as the quiet utility. `MOBILE_MORE_SLUGS` derives automatically, so the sheet marks itself active on the Partner page exactly as the existing entries do.

- [ ] **Step 4: Create the Partner page**

`src/tradelens/ui/pages/7_Partner.py` renders the masthead and `render_partner_body(st, surface="page")`. It is a reflective surface, not a place for a second bright CTA competing with `Log completed trade` — one primary action still applies.

- [ ] **Step 5: Hide the launcher at bottom-nav widths**

```css
@media (max-width: 767px) {
  .st-key-tl_partner_launcher { display: none; }
}
```

Selecting the Partner from `More` navigates, and the rerun re-emits `More` closed — which the shell already requires ("closed on arrival and after navigation"). No `:has()` selector, no CSS exclusivity machinery, no support floor.

- [ ] **Step 6: Run to verify the tests pass**

Run: `"$PY" -m pytest tests/test_partner_panel.py tests/test_premium_shell.py tests/test_pages_boot.py -v`
Expected: PASS.

- [ ] **Step 7: Browser verification at coarse 375**

Confirm: no fixed launcher renders; the `More` sheet lists the Partner and marks it active while on it; navigating there closes the sheet; every nav target stays ≥44 px and clear of the safe-area inset; returning from the Partner restores the previous destination's state; and the conversation is still there.

At coarse 768, confirm the opposite: the drawer is present and the `More` sheet is not, because bottom navigation does not render at that width.

- [ ] **Step 8: Run the full suite, lint, commit**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/ && "$PY" -m black --check src/ scripts/
git add src/tradelens/ui/pages/7_Partner.py src/tradelens/ui/components/sidebar.py \
        src/tradelens/ui/design_system.py tests/test_partner_panel.py \
        tests/test_premium_shell.py tests/test_pages_boot.py
git commit -m "feat(partner): full-page destination at bottom-navigation widths"
```

- [ ] **Step 9: Update the handoff and release the lock**

---

## Task 16: Cross-page accessibility, security, and consistency audit

**Files:**
- Create: `tests/test_dark_accessibility.py`
- Modify: whatever the audit reproduces as a real defect — nothing else

**Interfaces:**
- Consumes: every surface from Tasks 1–15.
- Produces: no new interface. This task builds the audit before fixing anything.

- [ ] **Step 1: Build the audit first**

Create `tests/test_dark_accessibility.py`. Every helper is defined in the file or imported from an existing module — nothing is assumed to exist.

**Verified 2026-08-04 against the current codebase: `16 passed, 5 skipped`, Ruff clean, Black clean.** The five skips are the composited-contrast cases, gated on Task 1 introducing the role tokens; running with those tokens present was confirmed to activate and pass them.

```python
"""Cross-page accessibility and containment checks for the dark workspace.

Containment is asserted against **rendered output** — the elements AppTest
actually emits — not against a subprocess's stdout. Stdout proves a page exited
zero; it does not prove what a trader would have read on the screen, and a leaked
DSN is precisely a thing that renders without failing.

The pages themselves are not booted in-process here. In a pytest process the
database engine is already bound from import time, so booting a real page would
read whatever DATABASE_URL pointed at when the suite started — a developer's own
journal. Instead the two halves are separated:

  * the containment *renderer* is driven with real leaky exceptions through the
    real error_box builder, and its emitted elements are inspected;
  * every page's own except-blocks are checked structurally, so a page that
    starts rendering an exception object is caught without booting it.

The remaining page-level checks — heading order, tab order, target sizes — are
browser work and live in this task's browser step.
"""

import ast
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.tradelens.ui import design_system as ds
from src.tradelens.ui.components.ui import error_box
from tests.test_design_system import contrast_ratio

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "src" / "tradelens" / "ui"
PAGES_DIR = UI_DIR / "pages"

# Strings that must never reach a rendered element, whatever went wrong.
SECRETS = (
    "Traceback",
    "postgresql://",
    "sqlite:///",
    "sk-ant-",
    "psycopg",
    "ANTHROPIC_API_KEY",
    "OperationalError",
    "SMTP_PASSWORD",
)

# A representative leaky exception per failure class the product actually has.
LEAKY_EXCEPTIONS = {
    "database": (
        "OperationalError",
        'psycopg2.OperationalError: could not connect: dsn="postgresql://tl:hunter2@db:5432/tradelens"',
    ),
    "ai": (
        "AuthenticationError",
        "anthropic.AuthenticationError: invalid x-api-key sk-ant-api03-AAAABBBB",
    ),
    "mail": (
        "SMTPAuthenticationError",
        "smtplib.SMTPAuthenticationError: (535) SMTP_PASSWORD rejected for tl@example.com",
    ),
}


def rendered_text(at) -> str:
    """Every string this app run actually put on the screen."""
    parts = []
    for element in at.main:
        value = getattr(element, "value", None)
        if isinstance(value, str):
            parts.append(value)
    for element in at.sidebar:
        value = getattr(element, "value", None)
        if isinstance(value, str):
            parts.append(value)
    for exc in at.exception:
        parts.append(str(getattr(exc, "value", exc)))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Containment, asserted on what renders
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("kind", sorted(LEAKY_EXCEPTIONS))
def test_an_unexpected_failure_renders_fixed_copy_and_leaks_nothing(kind):
    """The real containment shape: log the exception, render fixed copy.

    Driven through the real error_box builder so the assertion covers the
    string a trader would actually see.
    """
    exc_name, message = LEAKY_EXCEPTIONS[kind]
    script = f"""
import logging
import streamlit as st
from src.tradelens.ui.components.ui import error_box

log = logging.getLogger("tradelens.test")
try:
    raise RuntimeError({message!r})
except Exception:
    log.exception("{exc_name} during a {kind} operation")
    st.markdown(
        error_box("Something went wrong. Please try again."),
        unsafe_allow_html=True,
    )
"""
    at = AppTest.from_string(script, default_timeout=30)
    at.run()

    assert not at.exception, "the failure escaped containment and rendered"
    screen = rendered_text(at)
    assert "Something went wrong" in screen
    for secret in SECRETS:
        assert secret not in screen, f"{kind}: rendered output leaked {secret!r}"


def test_the_containment_probe_can_actually_detect_a_leak():
    """A negative test that never fails proves nothing. Render the exception
    the way a careless handler would, and confirm the probe catches it."""
    script = """
import streamlit as st
try:
    raise RuntimeError('psycopg2 dsn="postgresql://tl:hunter2@db:5432/tradelens"')
except Exception as exc:
    st.markdown(f"Could not load: {exc}")
"""
    at = AppTest.from_string(script, default_timeout=30)
    at.run()
    screen = rendered_text(at)
    assert any(secret in screen for secret in SECRETS)


def test_the_error_builder_escapes_what_it_is_handed():
    """The containment copy is fixed, but the builder must still escape: a
    domain error's own message can carry characters that would otherwise close
    the surrounding tag."""
    html = error_box("<script>alert(1)</script> & more")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html


def test_a_raised_exception_surfaces_as_an_apptest_exception():
    """Pins the other half of the probe: an uncontained failure is visible."""
    at = AppTest.from_string("raise RuntimeError('boom')", default_timeout=30)
    at.run()
    assert at.exception


# ---------------------------------------------------------------------------
# Every page's own handlers, checked without booting them
# ---------------------------------------------------------------------------
def _page_sources():
    """Live pages only. pages/_archive holds superseded files that are not
    imported by anything, and auditing them reports defects nobody can reach."""
    for path in sorted(PAGES_DIR.glob("*.py")):
        yield path
    yield UI_DIR / "app.py"


def _live_ui_sources():
    for path in sorted(UI_DIR.rglob("*.py")):
        if "_archive" in path.parts:
            continue
        yield path


def _is_broad(handler) -> bool:
    """Whether this handler catches everything rather than a named domain type."""
    node = handler.type
    if node is None:
        return True
    names = node.elts if isinstance(node, ast.Tuple) else [node]
    return any(
        isinstance(n, ast.Name) and n.id in {"Exception", "BaseException"}
        for n in names
    )


@pytest.mark.parametrize("path", list(_page_sources()), ids=lambda p: p.name)
def test_no_handler_renders_the_exception_it_caught(path):
    """`except Exception as e: st.error(e)` is the shape that leaks a DSN.

    Only *broad* handlers are flagged. A domain exception is designed to be
    read by a trader — 2_Trades.py deliberately renders OutcomeMismatch next to
    the two fields that disagree — so rendering one is correct, not a leak.
    The rule is about catching everything and showing whatever came back.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    renders = {
        "markdown",
        "write",
        "error",
        "warning",
        "info",
        "caption",
        "text",
        "toast",
    }
    offenders = []

    for handler in (n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)):
        if not handler.name or not _is_broad(handler):
            continue
        for call in (n for n in ast.walk(handler) if isinstance(n, ast.Call)):
            func = call.func
            if not (isinstance(func, ast.Attribute) and func.attr in renders):
                continue
            for node in ast.walk(call):
                if isinstance(node, ast.Name) and node.id == handler.name:
                    offenders.append(
                        f"{path.name}:{call.lineno} renders {handler.name}"
                    )

    assert not offenders, offenders


# ---------------------------------------------------------------------------
# Composited contrast
# ---------------------------------------------------------------------------
RGBA_OVER = {
    "TL_PRIMARY_DIM": "TL_SURFACE_PANEL",
    "TL_SUCCESS_DIM": "TL_SURFACE_PANEL",
    "TL_DANGER_DIM": "TL_SURFACE_PANEL",
    "TL_WARNING_DIM": "TL_SURFACE_PANEL",
    "TL_NEUTRAL_DIM": "TL_SURFACE_PANEL",
}


def composite(rgba: str, backdrop_hex: str) -> str:
    """Flatten an rgba() layer onto an opaque backdrop, returning #RRGGBB.

    Treating the first rgba() layer as opaque is how contrast bugs survive
    tests: the ratio that matters is the one against the composite.
    """
    match = re.fullmatch(
        r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", rgba.strip()
    )
    assert match, f"not an rgba() literal: {rgba!r}"
    fr, fg, fb = (int(match.group(i)) for i in (1, 2, 3))
    alpha = float(match.group(4))
    back = backdrop_hex.lstrip("#")
    br, bg, bb = (int(back[i : i + 2], 16) for i in (0, 2, 4))
    out = [
        round(f * alpha + b * (1 - alpha)) for f, b in ((fr, br), (fg, bg), (fb, bb))
    ]
    return "#%02X%02X%02X" % tuple(out)


def test_composite_flattens_a_known_layer_correctly():
    assert composite("rgba(255,255,255,1.0)", "#000000") == "#FFFFFF"
    assert composite("rgba(255,255,255,0.0)", "#101B20") == "#101B20"
    assert composite("rgba(255,255,255,0.5)", "#000000") == "#808080"


needs_task_one = pytest.mark.skipif(
    not hasattr(ds, "TL_SURFACE_PANEL"),
    reason="Task 1 introduces the role tokens; this activates once it lands",
)


@needs_task_one
@pytest.mark.parametrize("token", sorted(RGBA_OVER))
def test_primary_text_clears_aa_on_every_composited_tint(token):
    flat = composite(getattr(ds, token), getattr(ds, RGBA_OVER[token]))
    ratio = contrast_ratio(ds.TL_CONTENT_PRIMARY, flat)
    assert ratio >= 4.5, f"{token} composites to {flat} = {ratio:.2f}"


# ---------------------------------------------------------------------------
# Tenant scoping at the call site
# ---------------------------------------------------------------------------
SCOPED_CALLS = {
    "get_trades",
    "get_trade",
    "create_trade",
    "update_trade",
    "delete_trade",
    "get_active_strategy",
    "upsert_strategy_profile",
    "count_sample_trades",
    "get_weekly_review",
    "build_global_partner_context",
}

# Call sites that pass the owner inside a payload dict rather than as a keyword.
# Each is listed explicitly with the line that carries the owner, so the
# exemption is auditable instead of a silent hole in the regex.
PAYLOAD_SCOPED = {
    # 1_NewTrade.py builds `data` with "user_id": uid before handing it to
    # _persist(); create_trade(data) is scoped through that dict.
    ("1_NewTrade.py", "create_trade"),
}


def test_every_scoped_service_call_site_names_an_owner():
    """Tenant scoping resolved at the call site, not only inside the service.

    AST-based: a regex window mistook `create_trade(data)` for an unscoped call
    because the owner is set twenty lines earlier, and swept pages/_archive,
    which nothing imports.
    """
    offenders = []
    for path in _live_ui_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in (n for n in ast.walk(tree) if isinstance(n, ast.Call)):
            func = call.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute) else None
            )
            if name not in SCOPED_CALLS:
                continue
            if (path.name, name) in PAYLOAD_SCOPED:
                continue
            scoped = any(kw.arg in {"user_id", "uid"} for kw in call.keywords)
            scoped = scoped or any(
                isinstance(a, ast.Name) and a.id in {"user_id", "uid"}
                for a in call.args
            )
            if not scoped:
                offenders.append(f"{path.name}:{call.lineno} {name}")
    assert not offenders, f"unscoped service calls: {offenders}"


def test_the_payload_scoped_allowlist_has_no_dead_entries():
    """An exemption for a call site that no longer exists hides a real one."""
    for filename, call_name in PAYLOAD_SCOPED:
        matches = [p for p in _live_ui_sources() if p.name == filename]
        assert matches, f"allowlisted file is gone: {filename}"
        assert f"{call_name}(" in matches[0].read_text(encoding="utf-8")
```

**Containment is asserted on rendered elements, not on a subprocess's exit status.** Stdout proves a page exited zero; it does not prove what a trader would have read, and a leaked DSN renders perfectly happily without failing anything. `rendered_text(at)` walks what AppTest actually emitted.

**The pages are not booted in-process.** In a pytest process the database engine is already bound from import time, so booting a real page would read whatever `DATABASE_URL` pointed at when the suite started — a developer's own journal. The two halves are separated instead: the containment *renderer* is driven with real leaky exceptions through the real `error_box`, and each page's own handlers are checked structurally.

**Three findings from running this against the current codebase, already folded in:**

- `pages/_archive/` must be excluded. Sweeping it reported four "unscoped" calls in superseded files nothing imports.
- Only **broad** handlers may be flagged for rendering their exception. `2_Trades.py:855` deliberately renders `OutcomeMismatch` — a domain error with trader-safe copy — next to the two fields that disagree. That is correct behaviour, and a rule that flagged it would have been rejected or, worse, obeyed.
- The scoping check has to be AST-based. A regex window read `create_trade(data)` in `1_NewTrade.py` as unscoped because the owner is set into `data` twenty lines earlier. That call site is now an explicit, tested allowlist entry rather than a silent hole in a pattern.

**A rule that was written and then withdrawn.** An earlier draft asserted every broad handler must log or surface what it swallowed. It failed on five existing files. It encoded a preference this codebase has not adopted, was not requested, and would have blocked Task 16 on pre-existing code — so it is not in the plan. If it is wanted, it is its own change with its own review.

**Heading sequence and tab order are browser checks.** Streamlit composes final heading levels at render time, so asserting on them from AppTest measures the wrong artifact. Both live in step 4.
- [ ] **Step 2: Run the audit and record every finding**

Run: `"$PY" -m pytest tests/test_dark_accessibility.py -v`
Record each failure with its page, width, and reproduction. Do not fix anything yet.

- [ ] **Step 3: Fix only reproduced defects**

Fix what the audit actually reproduces. Do not refactor adjacent code, do not "improve" a surface the audit did not flag, and do not widen scope because a file was already open.

- [ ] **Step 4: Full browser sweep**

All seven authenticated destinations plus the Partner, at 1440, 1024, real coarse-pointer 768, real coarse-pointer 375, and with `prefers-reduced-motion: reduce`. Coarse-pointer verification uses real media emulation (`pointer: coarse`, `hover: none`), not desktop viewport resizing. Assert per destination: expected heading, zero `stException` elements, no document-level horizontal overflow, every visible interactive target ≥44×44 with ≥8 px separation, focus visible on every control, and tab order matching visual order.

Two checks moved here from step 1 because only a browser can answer them:

- **Heading sequence.** Collect `document.querySelectorAll('h1,h2,h3,h4,h5,h6')` and assert no level is skipped. Streamlit composes final heading levels at render time, so source inspection measures the wrong artifact.
- **Tab order.** Walk focus with repeated `Tab`, record `document.activeElement`'s bounding box each time, and assert the sequence is non-decreasing in (top, left) within each landmark. This is also where the Partner drawer's "Close is the first tab stop" claim is confirmed rather than asserted from DOM order.

Recheck the nested-route `_stcore` console 404s recorded in the preflight and state plainly whether they persist. They are baseline infrastructure noise, not a target of this phase.

- [ ] **Step 5: Preserve every workflow**

Confirm still green: the New Trade five-step wizard including the screenshot round trip, all three Journal routes, all four Analytics lenses, the AI caches, Strategy persistence, Settings tenant isolation, and authentication and recovery.

- [ ] **Step 6: Full verification**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/
"$PY" -m black --check src/ scripts/
git diff --check
```

- [ ] **Step 7: Commit**

Stage the audit file plus **only** the files a reproduced defect required. Read `git status --short` and name each path explicitly; a file that appears in the diff without a matching audit finding is scope creep and must be reverted, not committed.

```bash
git status --short
git add tests/test_dark_accessibility.py   # then each fixed file, by name
git commit -m "fix(a11y): close the defects the cross-page dark audit reproduced"
```

- [ ] **Step 8: Hand to Codex for the security and tenancy gate**

Codex runs the final security, tenant-isolation, AI-safety, full-test, and CI gates. Set `Active writer: NONE` and provide the audit output verbatim.

---

## Task 17: Refresh product evidence and re-score the 10K checklist

**Files:**
- Modify: `docs/audits/2026-07-21-10k-checklist-business-audit.md` (add a Phase 2 re-score section), marketing screenshot assets
- Create: `docs/superpowers/audits/<today>-phase2-dark-rescore.md`, where `<today>` is the ISO date the task runs — the repo's audit files are all dated by run date, not by plan date

**Interfaces:**
- Consumes: the finished product from Tasks 1–16.
- Produces: the phase's acceptance evidence.

- [ ] **Step 1: Preserve capture safety**

Capture from an isolated seeded database in the scratchpad — never `data/tradelens.db`, never a user database. No owner chrome, no personal data, no capture artifact committed unless it is a deliberate marketing asset.

- [ ] **Step 2: Re-capture the product**

Coherent seeded data, no owner chrome, fewer and larger crops. All seven destinations plus the Partner drawer and the mobile Partner page, at 1440 and real coarse 375.

- [ ] **Step 3: Re-score against the eight checklist items**

Score the product experience **separately from business proof**, and do not inflate the result because the theme is more attractive.

| # | Item | Baseline | Phase 2 target | Evidence required |
|---|---|---:|---:|---|
| 01 | Point of view, not a template | 7.5 | 8.5 | Product and marketing read as one company; the app no longer looks hosted inside Streamlit; five distinct band forms on Overview, not a card wall |
| 02 | Typography that does work | 8.0 | 8.5 | Generated prose at 68–72 ch; mono limited to metrics, dates, metadata, labels; one editorial lead sentence per note |
| 03 | A restrained colour system | 8.5 | 9.0 | Teal reduced to primary actions and one active state per viewport; neutral hairlines on passive containers; no large red/green chart below a meaningful sample |
| 04 | **Hierarchy that breathes** | **6.5** | **8.5** | One progress system in New Trade; five bands in five forms; no empty chart canvases; no "Not entered yet" wall |
| 05 | Imagery with intent | 6.5 | 7.5 | Re-captured screenshots from coherent seeded data |
| 06 | **Motion that whispers** | **6.0** | **7.5** | Full motion inventory; loading and state feedback improved rather than decoration added; reduced motion verified |
| 07 | **Mobile that is designed, not shrunk** | **5.5** | **7.5** | Real coarse-pointer captures at 375 and 768 for all seven destinations plus the Partner. Not CSS assertions alone |
| 08 | **The invisible expensive stuff** | **4.5** | **7.0** | No rendered exception in any audited state; tenant scoping resolved at every call site; no secret, DSN, or stack text reachable; full suite, Ruff, Black green |

Items 04, 06, 07, and 08 are the phase's real work. A target missed is reported as missed, with what remains.

- [ ] **Step 4: Final verification**

```bash
"$PY" -m pytest tests/ -q
"$PY" -m ruff check src/ scripts/
"$PY" -m black --check src/ scripts/
git diff --check
git log --oneline
```

- [ ] **Step 5: Commit**

```bash
# Stage the audit files and each re-captured asset by explicit path.
# Do not run `git add -A` — the worktree carries untracked directories
# (src/tradelens/ui/.impeccable/) that are not this phase's artifacts.
git status --short
git add docs/audits/2026-07-21-10k-checklist-business-audit.md \
        docs/superpowers/audits/*-phase2-dark-rescore.md
git commit -m "docs(audit): re-score the 10K checklist against the dark workspace"
```

- [ ] **Step 6: Final handoff**

Update the handoff with the complete commit list, final test counts, browser evidence, the re-score, unresolved concerns, and the fixed-positioning outcome. Set `Active writer: NONE`. **Stop.** No push, merge, PR, or deploy without explicit owner approval.

---

## Spec coverage

Checked section by section against the spec. Every requirement maps to a task.

| Spec section | Task |
|---|---|
| §0.1 resolved conflicts | Global Constraints; Task 4 (one Codex service addition), Tasks 5–7 (expanded Overview), Tasks 14–15 (global Partner) |
| §0.2 inherited constraints | Global Constraints |
| §1.2 D1, D2, D3, D4, D13 | Task 1 |
| §1.2 D5, D6, D7, D8 | Task 12 |
| §1.2 D9 emoji icons | Task 2 step 4 |
| §1.2 D10 false zeros | Task 4 (`EdgeLeakSummary`), Tasks 5–6 (`No wins yet` / `No losses yet`) |
| §1.2 D11 rule adherence | Task 4 |
| §1.2 D12 trade-scoped Partner | Tasks 14–15 |
| §2 remove / retain / combine / demote | Task 1 (remove tokens), Task 2 (emoji), Task 7 (combine bands, demote filter), Task 10 (demote lens radio), Task 12 (combine note paths, one stats strip) |
| §3 IA and the hierarchy contract | Task 2 (shell), Tasks 5–13 (per page) |
| §4.1–4.6 token roles, contrast, separation, z-scale, focus | Task 1, Task 3 (focus) |
| §5.1–5.7 five Overview bands and states | Tasks 5, 6, 7 |
| §5.4a date-series policy | Task 5 steps 1–4 |
| §6.1 auth | Task 13 step 5 |
| §6.2 New Trade | Task 8 |
| §6.3 Journal | Task 9 |
| §6.4 Analytics | Task 10 |
| §6.6 Strategy · §6.7 Settings | Task 13 |
| §7.1–7.6 AI Reviews | Tasks 11, 12 |
| §8.1 authorised scope | Task 14 step 1 |
| §8.2 drawer · §8.2a placement | Tasks 14, 15 |
| §8.3 session-only history | Task 14 step 5 |
| §8.4 component inventory · §8.5 states · §8.6 safety copy | Task 14 |
| §9 component inventory | Tasks 5, 6, 11, 12, 14 |
| §10 eight interaction states | Task 3 |
| §11 responsive behaviour | Tasks 2, 15, 16 |
| §12 accessibility | Task 3, Task 16 |
| §13 10K acceptance criteria | Task 17 |
| §14 out of scope | Global Constraints |
| §16.1 rule adherence · §16.2 edge leak · §16.3 Partner context | Task 4 |
| §16.4 fixed-positioning verification | Task 14 step 7 |
| §16.5 rebuild gate | Cleared — `8b35a6e` and `3bb4a5f` are approved |
| Preflight: Partner breakpoints | Tasks 14, 15 |
| Preflight: dataframe toolbar targets | Task 9 |
| Preflight: nested-route 404s | Task 16 step 4 |

**Known gaps carried forward from the spec, unchanged:**

1. **TradeZella reference images were never received.** Direction derives from the spec's written direction plus the layout-reference-only constraint. If the images are supplied, reconcile spec §5 and §7 before Task 5.
2. **The Partner's `position: fixed` behaviour is unverified.** Task 14 step 7 verifies it; step 8 is the reviewed fallback. Nothing downstream assumes it works.
