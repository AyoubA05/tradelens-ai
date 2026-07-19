# SP4 — Brand Unification + Polish Pass (Design)

**Date:** 2026-07-18
**Status:** Approved by Ayoub (brainstorming session)
**Scope:** The Streamlit app's design system and pages. No marketing-site changes, no
auth-logic changes, no new features.

## Context

SP1 shipped the marketing site, SP2 moved to Neon Postgres, SP3 rebuilt the auth screen.
Crossing from site → app today is a visible seam because the app carries **two internal
color/font systems**, neither matching the site:

| Source | Background | Teal | Fonts |
|---|---|---|---|
| `design_system.py` (`TL_*`, newer) | `#0d0f11` | `#00c2b2` | — |
| `theme.py` (`BG`/`TEAL`, legacy) | `#0E1117` | `#20808D` | Inter + Space Grotesk |
| **Marketing site (target)** | `#0d1117` | `#00e5cc` | Satoshi + Schibsted Grotesk |

Investigation found **zero hardcoded app-palette hex outside `design_system.py`**, and the
legacy `#20808D` teal is consumed in only two files (`ui.py`, `demo_banner.py`) plus
`theme.py`'s own base CSS. Every page injects `inject_css()` (theme) then
`inject_design_system()` ("wins ties, injected after theme"). So this is a
**design-system-layer change plus a verification sweep**, not a page-by-page rewrite.

## Sequencing (explicit, per Ayoub)

SP4 is one branch with **two ordered phases**, so the design-system change stays reviewable
on its own and the polish work does not blur it:

1. **Phase A — brand unification.** Collapse the app onto the site's design system and
   verify contrast. Complete and verified before Phase B begins.
2. **Phase B — finishing pass.** A small, explicit scope: loading states and mobile layout.

## Phase A — Brand unification

### A1. Palette

In `design_system.py`, change token *values* (not names — everything downstream reads the
names):

| Token | From | To |
|---|---|---|
| `TL_BG` | `#0d0f11` | `#0d1117` |
| `TL_SURFACE` | `#13161a` | `#161b22` |
| `TL_SURFACE_2` | `#1a1e24` | `#1c232b` |
| `TL_PRIMARY` | `#00c2b2` | `#00e5cc` |
| `TL_PRIMARY_HOVER` | `#00a89a` | `#33ecd8` |
| `TL_PRIMARY_DIM` | `rgba(0,194,178,0.12)` | `rgba(0,229,204,0.12)` |

`TL_BORDER` (`#252a32`), `TL_TEXT` (`#e8eaed`), and the semantic success/danger/warning
tokens already match the site and stay unchanged. The grade ramp (A→F) derives from
success/warning/danger and therefore also stays.

### A2. Typography

Adopt the site's faces: **Satoshi** (body, Fontshare 400/500/700) and **Schibsted Grotesk**
(headings, Google 500/600/700), keeping **JetBrains Mono**. `theme.py`'s `BODY_FONT`
(Inter) and `HEADING_FONT` (Space Grotesk) change, and `_FONT_IMPORT` gains the Fontshare
stylesheet alongside the Google one.

Satoshi ships no 600 weight — any `font-weight: 600` on body text silently resolves to 700.
Audit and set those to 500 or 700 deliberately, the same fix SP1 applied to the site.

### A3. Collapse the legacy layer

Point `theme.py`'s brand constants at the design-system tokens so one source of truth
remains and the third teal disappears:

- `TEAL` → `TL_PRIMARY`, `TEAL_HOVER` → `TL_PRIMARY_HOVER`, `TEAL_SOFT` → `TL_PRIMARY_DIM`
- `BG` → `TL_BG`, `TEXT_PRIMARY` → `TL_TEXT`

`TERRA`/`TERRA_SOFT` stay: they are a distinct semantic (legacy accent used by
`ui.py`'s callout border), not a competing brand teal, and removing them is out of scope.

### A4. Verification

The brighter teal and new surfaces change every contrast pairing, so re-verify WCAG AA
(≥4.5:1 small text, ≥3:1 large/UI) for: KPI cards, muted/faint text on both surfaces, the
A→F grade chips, success/danger table text, gauge bands, heatmap scales, badges, and the
auth screen (SP3 used the app tokens, so it moves too — this is where the seam visibly
closes). CDP screenshots of all 7 pages plus auth, before/after.

## Phase B — Finishing pass

Deliberately small and explicit:

- **Loading states.** Audit the AI-call paths (New Trade autofill, Insights weekly recap
  and daily debrief, AI chart review) and any data load exceeding ~300ms; ensure each shows
  a spinner or skeleton rather than a frozen pane. Use Streamlit's `st.spinner` /
  `st.status`, matching the pattern SP3 introduced on the auth submit.
- **Mobile layout.** Target 375px: KPI rows that currently sit in fixed `st.columns` wrap
  instead of squashing; tables scroll horizontally inside their container rather than
  overflowing the page; touch targets ≥44px; the sidebar nav is reachable.

Phase B does **not** restructure pages, change copy, or add features.

## Testing

Five tests hardcode literals that this change moves, and each is updated to assert the new
value (they are contract tests — the contract is changing deliberately):

- `tests/test_design_system.py:75-77` — `TL_BG`, `TL_SURFACE`, `TL_PRIMARY` literals.
- `tests/test_theme.py:93` — `theme.TEAL == "#20808D"` becomes an identity assertion against
  `TL_PRIMARY` (proving the collapse, not a literal).
- `tests/test_theme.py:97` — font-stack assertions for the new faces.
- `tests/test_auth_screen.py:153` — already asserts `#20808D` is absent; still passes and
  now also guards the collapse.
- `tests/test_components.py:172` — `#A84B2F` terra border; unchanged (terra stays).

A new test asserts the app palette equals the site palette, so the seam cannot silently
reopen: it reads the hex values out of `site/styles.css` and compares them to the tokens.

Full suite (871 passing) must stay green; ruff + black clean.

## Out of scope

Marketing-site changes; auth logic; page restructuring; copy changes; new features; removing
`TERRA`; the placeholder-domain swaps (`APP_URL`, OG origin, `auth_screen.SITE_URL`) which
remain a separate cleanup when a real domain exists.
