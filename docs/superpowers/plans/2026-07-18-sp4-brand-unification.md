# SP4 Brand Unification + Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the app's two internal color/font systems onto the marketing site's design system so site → auth → app is visually seamless, then apply a bounded finishing pass for loading states and mobile layout.

**Architecture:** Token *values* change in `design_system.py` (names stay, so all charts/cards/badges cascade automatically); `theme.py`'s legacy brand constants are re-pointed at those tokens so one source of truth remains. Phase A (unification + contrast verification) completes and is verified before Phase B (loading states + mobile) begins, keeping the design-system change reviewable on its own.

**Tech Stack:** Streamlit 1.50, `design_system.py` tokens, Fontshare (Satoshi) + Google Fonts (Schibsted Grotesk, JetBrains Mono), pytest + `AppTest`, headless-Chrome CDP for visual verification.

## Global Constraints

- **Token names never change** — only values. Downstream code reads names; renaming would ripple needlessly.
- **WCAG AA is a hard gate:** ≥4.5:1 for small text, ≥3:1 for large text and UI. The codebase already documents this guarantee in `design_system.py`; the lighter site surfaces force two tokens to be re-tuned (Task 1) to preserve it.
- No marketing-site changes, no auth-logic changes, no page restructuring, no copy changes, no new features.
- `TERRA` / `TERRA_SOFT` stay in `theme.py` — a distinct legacy semantic (used by `ui.py`'s callout border), not a competing brand teal. Removing them is out of scope.
- **NO streamlit imports at module scope in `services/` or `db/`** (CLAUDE.md).
- Scoped CSS only; never style bare tags (breaks Streamlit widgets and contrast).
- No emoji as icons (SVG only). No side-tab accent borders. No gradient text.
- Full suite must stay green. **Baseline is whatever `pytest` reports when SP4 starts, not a fixed number** — uncommitted auth-hardening work (opt-in demo credential, `AuthUnavailableError`) was in flight when this plan was written and moved the count from 871 to 888. Record the baseline in Task 1 Step 5 and require `baseline + N` thereafter (N = tests this plan adds: +1 in Task 4, +2 in Task 6). `ruff check src/ scripts/` and `black --check src/ scripts/` clean.
- Commit after every task; stage paths explicitly (never `git add -A` — the tree carries unrelated dirty files: `.claude/*`, `skills-lock.json`).
- Branch off `main` (SP3 merged at `d02edca`).
- Phase B does not start until Phase A's verification task passes.

---

# PHASE A — Brand unification

### Task 1: Palette tokens (+ AA re-tune)

**Files:**
- Modify: `src/tradelens/ui/design_system.py:49-66`
- Modify: `tests/test_design_system.py:75-77`

**Interfaces:**
- Produces: `TL_BG`, `TL_SURFACE`, `TL_SURFACE_2`, `TL_PRIMARY`, `TL_PRIMARY_HOVER`, `TL_PRIMARY_DIM`, `TL_TEXT_FAINT`, `TL_DANGER`, `TL_DANGER_DIM` at their new values. Every consumer (charts, KPI cards, badges, tables, gauges, auth screen) reads these names and needs no edit.

- [ ] **Step 1: Update the failing contract test first** — `tests/test_design_system.py` lines 75-77 currently pin the old values. Replace them with the site palette:

```python
    assert ds.TL_BG == "#0d1117"
    assert ds.TL_SURFACE == "#161b22"
    assert ds.TL_PRIMARY == "#00e5cc"
```

- [ ] **Step 2: Run it to confirm it fails against the current tokens**

Run: `source .venv/bin/activate && pytest tests/test_design_system.py -q -k "token or palette"`
Expected: FAIL — `assert '#0d0f11' == '#0d1117'`.

- [ ] **Step 3: Change the token values** in `src/tradelens/ui/design_system.py`. Replace the block at lines 49-66 with:

```python
TL_BG = "#0d1117"
TL_SURFACE = "#161b22"
TL_SURFACE_2 = "#1c232b"
TL_BORDER = "#252a32"
TL_BORDER_SUBTLE = "#1e2228"
TL_TEXT = "#e8eaed"
# Muted/faint tuned for WCAG AA (>=4.5:1 small text) against the SP4 site
# surfaces, which are lighter than the pre-SP4 ones:
#   muted  5.65 on BG / 5.17 on SURFACE / 4.73 on SURFACE_2
#   faint  5.50 on BG / 5.03 on SURFACE / 4.61 on SURFACE_2
# faint was #79828f, which fell to 4.08 on the lighter SURFACE_2 (below AA).
TL_TEXT_MUTED = "#848d9c"
TL_TEXT_FAINT = "#828b99"
TL_PRIMARY = "#00e5cc"
TL_PRIMARY_HOVER = "#33ecd8"
TL_PRIMARY_DIM = "rgba(0,229,204,0.12)"
TL_SUCCESS = "#22c55e"
TL_SUCCESS_DIM = "rgba(34,197,94,0.12)"
# Danger brightened from #ef4444: table .pnl-neg text sits on SURFACE_2 on row
# hover, where the old red measured 4.21 (below AA). #f56565 measures 5.23.
TL_DANGER = "#f56565"
TL_DANGER_DIM = "rgba(245,101,101,0.12)"
TL_WARNING = "#f59e0b"
TL_WARNING_DIM = "rgba(245,158,11,0.12)"
TL_NEUTRAL = "#374151"
TL_NEUTRAL_DIM = "rgba(55,65,81,0.3)"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_design_system.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full suite to catch cascade breakage**

Run: `DEMO_MODE=true pytest tests/ -q`
Expected: green except tests pinning legacy literals, which Task 3 updates. Note any failures; if a failure is NOT in `tests/test_theme.py` or `tests/test_components.py`, investigate before proceeding — it means something reads a literal instead of a token.

- [ ] **Step 6: Commit**

```bash
git add src/tradelens/ui/design_system.py tests/test_design_system.py
git commit -m "design-system: adopt site palette (bg/surfaces/teal) + AA re-tune of faint and danger"
```

### Task 2: Typography — Satoshi + Schibsted Grotesk

**Files:**
- Modify: `src/tradelens/ui/components/theme.py:53-62`
- Modify: `tests/test_theme.py:97-100`

**Interfaces:**
- Consumes: nothing from Task 1 (independent).
- Produces: `HEADING_FONT = "Schibsted Grotesk"`, `BODY_FONT = "Satoshi"`, `MONO_FONT = "JetBrains Mono"` (unchanged), and two module constants consumed by `_build_css()`: `_FONT_IMPORT` (Google, existing name retained) and `_FONT_IMPORT_FONTSHARE` (new).

- [ ] **Step 1: Update the font test** — in `tests/test_theme.py`, replace the body of `test_font_stacks_defined` (around line 97) with:

```python
def test_font_stacks_defined():
    # SP4: the app adopts the marketing site's faces so the brand reads as one
    # system. Inter/Space Grotesk were the pre-SP4 pair.
    assert theme.BODY_FONT == "Satoshi"
    assert theme.HEADING_FONT == "Schibsted Grotesk"
    assert theme.MONO_FONT == "JetBrains Mono"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/test_theme.py::test_font_stacks_defined -q`
Expected: FAIL — `assert 'Inter' == 'Satoshi'`.

- [ ] **Step 3: Change the fonts** in `src/tradelens/ui/components/theme.py`, replacing lines 53-62:

```python
# ── Fonts ─────────────────────────────────────────────────────────
# SP4: matches the marketing site (site/index.html) so site -> app is one brand.
HEADING_FONT = "Schibsted Grotesk"
MONO_FONT = "JetBrains Mono"
BODY_FONT = "Satoshi"

# Satoshi is Fontshare-hosted; the rest are Google. Two stylesheet links.
_FONT_IMPORT = (
    "https://fonts.googleapis.com/css2?"
    "family=Schibsted+Grotesk:wght@500;600;700&"
    "family=JetBrains+Mono:wght@400;500;600&display=swap"
)
_FONT_IMPORT_FONTSHARE = (
    "https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700&display=swap"
)
```

- [ ] **Step 4: Load the Fontshare stylesheet.** `_build_css()` (line ~105) opens its f-string with a single `@import` at line 108. Replace that one line:

```
@import url('{_FONT_IMPORT}');
```

with both imports, Fontshare first:

```
@import url('{_FONT_IMPORT_FONTSHARE}');
@import url('{_FONT_IMPORT}');
```

Both must stay at the very top of the stylesheet — CSS requires `@import` rules to precede all other rules, and a misplaced one is silently dropped (fonts would fall back with no error).

- [ ] **Step 5: Audit weight 600 on body text.** Satoshi ships 400/500/700 only; a `font-weight: 600` on Satoshi silently resolves to 700 (the same issue SP1 fixed on the site). Find body-font weights:

```bash
grep -rn "font-weight: 600\|font-weight:600" src/tradelens/ui/components/theme.py src/tradelens/ui/design_system.py
```

For each hit, decide deliberately: keep 700 if it is a heading/button (Schibsted has 600, so heading rules are unaffected), or change to `500` if it is body/label text that should not shout. Headings using `HEADING_FONT` may keep 600.

- [ ] **Step 6: Verify the CSS still builds and injects**

Run: `pytest tests/test_theme.py -q`
Expected: PASS (including `test_build_css_returns_nonempty_str`, `test_css_uses_only_scoped_selectors`, `test_inject_css_runs_in_apptest`).

- [ ] **Step 7: Commit**

```bash
git add src/tradelens/ui/components/theme.py tests/test_theme.py
git commit -m "theme: adopt Satoshi + Schibsted Grotesk to match the marketing site"
```

### Task 3: Collapse the legacy color layer

**Files:**
- Modify: `src/tradelens/ui/components/theme.py:28-45`
- Modify: `tests/test_theme.py:91-95`

**Interfaces:**
- Consumes: `TL_PRIMARY`, `TL_PRIMARY_HOVER`, `TL_PRIMARY_DIM`, `TL_BG`, `TL_TEXT` from Task 1.
- Produces: `theme.TEAL is design_system.TL_PRIMARY` (identity), same for `TEAL_HOVER`, `TEAL_SOFT`, `BG`, `TEXT_PRIMARY`. Consumers `ui.py` and `demo_banner.py` inherit the new palette with no edit.

- [ ] **Step 1: Rewrite the brand-color test** — in `tests/test_theme.py`, replace `test_brand_colors_match_spec` (around line 91) with a collapse assertion:

```python
def test_brand_colors_collapse_to_design_system():
    """SP4: theme.py no longer defines a competing teal — it re-exports the
    design-system token, so the app has exactly one brand color."""
    from src.tradelens.ui import design_system as ds

    assert theme.TEAL == ds.TL_PRIMARY
    assert theme.TEAL_HOVER == ds.TL_PRIMARY_HOVER
    assert theme.TEAL_SOFT == ds.TL_PRIMARY_DIM
    assert theme.BG == ds.TL_BG
    assert theme.TEXT_PRIMARY == ds.TL_TEXT
    # The legacy teal must be gone entirely.
    assert theme.TEAL != "#20808D"
    # TERRA is a separate semantic (ui.py callout border) and intentionally stays.
    assert theme.TERRA == "#A84B2F"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/test_theme.py::test_brand_colors_collapse_to_design_system -q`
Expected: FAIL — `assert '#20808D' == '#00e5cc'`.

- [ ] **Step 3: Re-point the constants.** In `src/tradelens/ui/components/theme.py`, add the import near the top (after `from __future__ import annotations`):

```python
from src.tradelens.ui.design_system import (
    TL_BG as _DS_BG,
    TL_PRIMARY as _DS_PRIMARY,
    TL_PRIMARY_DIM as _DS_PRIMARY_DIM,
    TL_PRIMARY_HOVER as _DS_PRIMARY_HOVER,
    TL_TEXT as _DS_TEXT,
)
```

Then replace lines 28-45 with:

```python
# ── Surfaces ──────────────────────────────────────────────────────
# SP4: BG/TEXT_PRIMARY/TEAL* now re-export design-system tokens so the app has
# a single source of truth. These names stay for the existing call sites
# (ui.py, demo_banner.py) which import them directly.
BG = _DS_BG
SURFACE = "rgba(255,255,255,0.06)"
SURFACE_HOVER = "rgba(255,255,255,0.09)"
BORDER = "rgba(255,255,255,0.10)"

# ── Brand ─────────────────────────────────────────────────────────
TEAL = _DS_PRIMARY
TEAL_HOVER = _DS_PRIMARY_HOVER
TEAL_SOFT = _DS_PRIMARY_DIM
# TERRA is a distinct legacy semantic (ui.py callout border), not a competing
# brand color — intentionally retained.
TERRA = "#A84B2F"
TERRA_SOFT = "rgba(168,75,47,0.15)"

# ── Text hierarchy ────────────────────────────────────────────────
TEXT_PRIMARY = _DS_TEXT
TEXT_SECONDARY = "#B4B8BD"
TEXT_MUTED = "#8E9196"
```

- [ ] **Step 4: Check for a circular import.** `design_system.py` must not import `theme.py`. Verify:

```bash
grep -n "import theme\|from src.tradelens.ui.components.theme" src/tradelens/ui/design_system.py || echo "no cycle — safe"
```
Expected: `no cycle — safe`. (If it prints a match, stop and report — the import direction would need inverting.)

- [ ] **Step 5: Confirm the legacy teal is gone from the codebase**

```bash
grep -rn "20808D\|20808d" src/ || echo "legacy teal eliminated"
```
Expected: `legacy teal eliminated`.

- [ ] **Step 6: Run the full suite**

Run: `DEMO_MODE=true pytest tests/ -q`
Expected: the recorded baseline, unchanged (this task only re-points constants).

- [ ] **Step 7: Commit**

```bash
git add src/tradelens/ui/components/theme.py tests/test_theme.py
git commit -m "theme: collapse legacy brand colors onto design-system tokens (one teal)"
```

### Task 4: Seam-guard test — app palette equals site palette

**Files:**
- Modify: `tests/test_design_system.py`

**Interfaces:**
- Consumes: `TL_BG`, `TL_SURFACE`, `TL_SURFACE_2`, `TL_PRIMARY` (Task 1); `site/styles.css` `:root` block.
- Produces: a regression guard so the seam cannot silently reopen if either surface is re-themed later.

- [ ] **Step 1: Write the test.** Append to `tests/test_design_system.py`:

```python
def test_app_palette_matches_marketing_site():
    """SP4 seam guard: the app and site must share one palette.

    Reads the CSS custom properties out of site/styles.css and compares them to
    the app tokens, so re-theming either surface without the other fails here
    instead of shipping a visible seam at the site -> app handoff.
    """
    import re
    from pathlib import Path

    from src.tradelens.ui import design_system as ds

    css = (
        Path(__file__).resolve().parents[1] / "site" / "styles.css"
    ).read_text(encoding="utf-8")

    def site_var(name: str) -> str:
        m = re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", css)
        assert m, f"--{name} not found in site/styles.css"
        return m.group(1).lower()

    assert ds.TL_BG.lower() == site_var("bg")
    assert ds.TL_SURFACE.lower() == site_var("surface")
    assert ds.TL_SURFACE_2.lower() == site_var("surface-2")
    assert ds.TL_PRIMARY.lower() == site_var("accent")
```

- [ ] **Step 2: Run it**

Run: `pytest tests/test_design_system.py::test_app_palette_matches_marketing_site -q`
Expected: PASS (Task 1 already aligned the values). If it FAILS, the message names the mismatching token — fix the token, not the test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_design_system.py
git commit -m "test: guard the site<->app palette seam against silent re-divergence"
```

### Task 5: Phase A verification sweep

**Files:**
- Modify: fixes only as found.

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: a verified Phase A. **Phase B does not begin until this task passes.**

- [ ] **Step 1: Re-verify every contrast pairing programmatically**

```bash
source .venv/bin/activate
python3 - <<'PY'
from src.tradelens.ui import design_system as ds
def lum(h):
    h=h.lstrip('#'); c=[int(h[i:i+2],16)/255 for i in (0,2,4)]
    c=[x/12.92 if x<=0.03928 else ((x+0.055)/1.055)**2.4 for x in c]
    return 0.2126*c[0]+0.7152*c[1]+0.0722*c[2]
def ratio(f,b):
    a,c=lum(f),lum(b); return (max(a,c)+0.05)/(min(a,c)+0.05)
bgs={'BG':ds.TL_BG,'SURFACE':ds.TL_SURFACE,'SURFACE_2':ds.TL_SURFACE_2}
fgs={'TEXT':ds.TL_TEXT,'MUTED':ds.TL_TEXT_MUTED,'FAINT':ds.TL_TEXT_FAINT,
     'PRIMARY':ds.TL_PRIMARY,'SUCCESS':ds.TL_SUCCESS,'DANGER':ds.TL_DANGER,
     'WARNING':ds.TL_WARNING,'GRADE_B':ds.TL_GRADE_B,'GRADE_D':ds.TL_GRADE_D}
bad=[(f,b,round(ratio(fv,bv),2)) for f,fv in fgs.items() for b,bv in bgs.items()
     if ratio(fv,bv) < 4.5]
print("below AA:", bad if bad else "none")
PY
```
Expected: `below AA: none`. Any entry must be fixed by brightening that token before continuing.

- [ ] **Step 2: Launch the app for visual capture**

```bash
TRADELENS_SESSION_SECRET=qa DEMO_MODE=true streamlit run src/tradelens/ui/app.py \
  --server.headless true --server.port 8501 &
for i in $(seq 1 30); do curl -s -o /dev/null http://localhost:8501 && break || sleep 1; done
TRADELENS_SESSION_SECRET=qa python -c "from src.tradelens.ui.components.auth import _issue_token; print(_issue_token('demo', 1))"
```
Copy the printed token for the `?auth=` parameter below.

- [ ] **Step 3: Capture all pages.** Using the CDP driver (`<scratchpad>/cdp_shot.py`; recreate per the `visual-qa-cdp-screenshots` memory if absent), capture each page at 1440x900 with the auth token appended:

```bash
for page in "" Trades Analytics NewTrade Insights Strategy Settings; do
  CDP_FULL=0 python <scratchpad>/cdp_shot.py \
    "http://localhost:8501/$page?auth=<TOKEN>" \
    "<scratchpad>/shots/sp4-${page:-dashboard}.png" 1440 900 12
done
```
Review each: teal is the brighter `#00e5cc`, backgrounds match the site, Satoshi body text renders (not a serif fallback), charts legible, no unreadable low-contrast text.

- [ ] **Step 4: Capture the auth screen** (logged out — no token) and confirm the seam closes:

```bash
CDP_FULL=0 python <scratchpad>/cdp_shot.py "http://localhost:8501/?v=auth" \
  "<scratchpad>/shots/sp4-auth.png" 1440 900 12
```
Compare against `site/` open in a browser: the teal and background should now read as the same brand.

- [ ] **Step 5: Confirm fonts actually loaded** (not a silent fallback)

```bash
curl -s -o /dev/null -w "fontshare:%{http_code}\n" \
  "https://api.fontshare.com/v2/css?f[]=satoshi@400,500,700&display=swap"
```
Expected: `fontshare:200`. Then in the Browser pane, run `document.fonts.check('16px Satoshi')` — expected `true`.

- [ ] **Step 6: Final Phase A gates**

```bash
DEMO_MODE=true pytest tests/ -q        # expect baseline + 1 (Task 4 seam guard)
ruff check src/ scripts/                # expect All checks passed!
black --check src/ scripts/             # expect unchanged
```

- [ ] **Step 7: Commit any fixes**

```bash
git add src/tradelens/ui/design_system.py src/tradelens/ui/components/theme.py
git commit -m "design-system: Phase A verification fixes (contrast + font loading)"
```

---

# PHASE B — Finishing pass

**Do not start until Task 5 passes.**

### Task 6: Loading states

**Files:**
- Modify: `src/tradelens/ui/pages/1_NewTrade.py`, `src/tradelens/ui/pages/6_Insights.py`
- Modify: `tests/test_page_polish.py`

**Interfaces:**
- Consumes: nothing from Phase A (independent, but sequenced after it).
- Produces: every AI-call path wrapped in `st.spinner`, asserted by a static-source test.

- [ ] **Step 1: Find AI-call paths lacking a spinner**

```bash
grep -n "generate_weekly_review\|run_debrief\|analyze_screenshot\|autofill" \
  src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/pages/6_Insights.py | head -20
grep -c "st.spinner" src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/pages/6_Insights.py
```
Note which call sites have no enclosing `st.spinner`.

- [ ] **Step 2: Write the guard test.** Append to `tests/test_page_polish.py`:

```python
@pytest.mark.parametrize("page", ["1_NewTrade.py", "6_Insights.py"])
def test_ai_pages_show_loading_feedback(page):
    """SP4 Phase B: AI calls take seconds — every AI page must show a spinner
    rather than freezing the pane with no feedback."""
    src = _src(page)
    assert "st.spinner" in src, f"{page}: AI call path needs st.spinner feedback"
```

- [ ] **Step 3: Run it**

Run: `pytest tests/test_page_polish.py -q -k loading`
Expected: PASS if spinners already exist; FAIL naming the page that needs one.

- [ ] **Step 4: Wrap any uncovered AI call.** For each call site found in Step 1 without a spinner, wrap it using the pattern SP3 established on the auth submit:

```python
with st.spinner("Analyzing your chart…"):
    result = <the existing AI call, unchanged>
```

Use copy that names the actual operation: "Analyzing your chart…" (New Trade autofill), "Writing your weekly recap…" (Insights weekly), "Reviewing your day…" (daily debrief). Do not change the call itself — only wrap it.

- [ ] **Step 5: Verify**

Run: `DEMO_MODE=true pytest tests/ -q`
Expected: green — **baseline + 3** (seam guard from Task 4, plus the 2 parametrized cases here).

- [ ] **Step 6: Commit**

```bash
git add src/tradelens/ui/pages/1_NewTrade.py src/tradelens/ui/pages/6_Insights.py tests/test_page_polish.py
git commit -m "ui: loading feedback on every AI call path"
```

### Task 7: Mobile layout at 375px

**Files:**
- Modify: `src/tradelens/ui/design_system.py` (mobile CSS block)

**Interfaces:**
- Consumes: tokens from Task 1.
- Produces: a `@media (max-width: 640px)` block in the design-system CSS covering KPI rows, tables, and touch targets.

- [ ] **Step 1: Capture the current mobile state** (app still running from Task 5, or relaunch):

```bash
for page in "" Trades Analytics; do
  CDP_FULL=0 python <scratchpad>/cdp_shot.py \
    "http://localhost:8501/$page?auth=<TOKEN>" \
    "<scratchpad>/shots/sp4-m-${page:-dashboard}.png" 375 812 12
done
```
Review: note which KPI rows squash, which tables overflow, and any control under 44px.

- [ ] **Step 2: Add the mobile block.** In `src/tradelens/ui/design_system.py`, inside the CSS returned by `build_css()`, append before the closing `</style>`:

```css
/* SP4 Phase B — mobile (<=640px). Streamlit's columns do not wrap on their
   own; these rules let KPI rows stack and keep tables scrollable instead of
   overflowing the viewport. */
@media (max-width: 640px) {{
  /* KPI rows: stack instead of squashing to unreadable widths. */
  .tl-kpi-row {{ flex-direction: column; gap: var(--tl-space-2); }}
  .tl-kpi-card {{ width: 100%; }}
  /* Tables scroll inside their own container, never the page. */
  .tl-table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; }}
  .tl-table {{ min-width: 560px; }}
  /* Touch targets: Streamlit buttons/inputs to >=44px. */
  .stButton > button,
  .stFormSubmitButton > button {{ min-height: 44px; }}
  [data-testid="stTextInput"] input {{ min-height: 44px; }}
}}
```

Note the doubled braces — this string is f-string-interpolated, so literal CSS braces must be escaped.

- [ ] **Step 3: Verify the CSS still builds**

Run: `pytest tests/test_design_system.py tests/test_theme.py -q`
Expected: PASS (including the scoped-selector guard — every new selector is either `.tl-*` or a Streamlit `data-testid`, never a bare tag).

- [ ] **Step 4: Re-capture mobile and compare**

```bash
for page in "" Trades Analytics; do
  CDP_FULL=0 python <scratchpad>/cdp_shot.py \
    "http://localhost:8501/$page?auth=<TOKEN>&m=2" \
    "<scratchpad>/shots/sp4-m2-${page:-dashboard}.png" 375 812 12
done
```
Expected: KPI cards stacked full-width and readable; tables scroll horizontally within their card rather than pushing the page wide; no horizontal page scroll.

- [ ] **Step 5: Commit**

```bash
git add src/tradelens/ui/design_system.py
git commit -m "ui: mobile layout pass — stacked KPIs, scrollable tables, 44px targets"
```

### Task 8: Final verification

**Files:**
- Modify: fixes only as found.

- [ ] **Step 1: Full breakpoint sweep.** Capture all 7 pages plus auth at 1440x900 and 375x812 (commands as in Task 5 Step 3 and Task 7 Step 1). Review every shot for overflow, clipping, unreadable text, or broken chart legibility.

- [ ] **Step 2: Reduced-motion check** — the auth screen animates; confirm it is static under reduced motion:

```bash
CDP_RM=1 CDP_FULL=0 python <scratchpad>/cdp_shot.py \
  "http://localhost:8501/?rm=1" "<scratchpad>/shots/sp4-auth-rm.png" 1280 800 12
```
Expected: card fully visible, no entrance animation caught mid-flight.

- [ ] **Step 3: Confirm no legacy palette survives anywhere**

```bash
grep -rn "20808D\|20808d\|#0d0f11\|#00c2b2" src/ || echo "legacy palette fully eliminated"
```
Expected: `legacy palette fully eliminated`.

- [ ] **Step 4: Final gates**

```bash
DEMO_MODE=true pytest tests/ -q        # expect baseline + 3
ruff check src/ scripts/                # expect All checks passed!
black --check src/ scripts/             # expect unchanged
```

- [ ] **Step 5: Close the plan**

```bash
git add docs/superpowers/plans/2026-07-18-sp4-brand-unification.md
git commit -m "SP4: brand unification + polish complete"
```
