# Landing Page Design Audit — TradeLens AI

Target: the pre-login screen rendered by `_render_login()` in
`src/tradelens/ui/components/auth.py`. Method: `/impeccable audit` (technical
5-dimension scan, P0–P3 severities). This is a Streamlit dark-dashboard product.

---

## BEFORE (baseline) — audited at start of Part 5

### What the page is

A single centered card (`st.columns([1, 1.4, 1])`, `text-align:center`) holding a
wordmark ("TradeLens AI"), a muted subtitle ("Post-Trade Journal"), one line
("Sign in to review your trades."), then the login form. No hero, no value
proposition, no feature story, no product framing. It is a login box, not a
landing page.

### Audit Health Score

| # | Dimension | Score | Key Finding |
|---|-----------|-------|-------------|
| 1 | Accessibility | 3 | Wordmark is a styled `<div>`, not an `<h1>` — no semantic heading/landmark. Contrast passes AA. |
| 2 | Performance | 4 | Static HTML, no images/animations. Lean. |
| 3 | Theming | 4 | Uses design tokens (SURFACE/BORDER/TEXT_*) from `theme.py`. Dark-only by design. |
| 4 | Responsive Design | 3 | Columns stack on mobile (OK), but `margin-top:8vh` + fixed paddings; the 1.4-wide center column is cramped on desktop. |
| 5 | Anti-Patterns | 2 | **Centered-everything** + **single card holds everything** + no hierarchy/value. Reads as a templated login card. |
| **Total** | | **16/20** | **Good technically, but fails the product brief.** |

### Anti-Patterns Verdict

Does it look AI-generated? **Partially — by omission, not by loudness.** It avoids
the loud slop (no gradient text, no glassmorphism, no neon, no hero-metric, no
icon-in-colored-circle grid). But it commits the quiet tells:

- **Centered-everything** (`text-align:center` on the whole card + centered column).
- **Single card as the lazy container** — everything stuffed in one bordered box.
- **No value proposition** — a serious trader lands and learns nothing about what
  the product does or why it's not a signal app.

### Executive Summary

- Health Score: **16/20** (Good band) — but the score flatters it: the page is
  clean *because* it's nearly empty. It does not do the job of a landing page.
- Issues: P0 0 · P1 2 · P2 3 · P3 1
- Top issues: (1) no hero value proposition; (2) centered-everything layout;
  (3) single-card container; (4) non-semantic heading; (5) no feature framing.

### Detailed Findings

- **[P1] No value proposition / not a landing page** — Location: `_render_login`.
  Category: Anti-Pattern / IA. Impact: a first-time visitor cannot tell what
  TradeLens is or that it is a *post-trade journal, not a signal app*. Fix: add a
  left-aligned hero headline + subcopy + an honest "not signals" scope line, with
  the login as one clear CTA path. Command: `/impeccable shape`.
- **[P1] Centered-everything layout** — Category: Anti-Pattern. Impact: reads
  templated; no visual hierarchy or reading rhythm. Fix: left-align body text;
  reserve centering for the hero headline only; use an asymmetric two-column
  hero + features split. Command: `/impeccable layout`.
- **[P2] Single card holds everything** — Category: Anti-Pattern. Impact: lazy
  affordance; no separation between brand, pitch, and auth. Fix: break into a
  hero band, a feature band, and a compact auth panel. Command: `/impeccable layout`.
- **[P2] Wordmark is a `<div>`, not a heading** — Category: A11y. Impact: screen
  readers get no document title/landmark. WCAG 1.3.1. Fix: render the hero as an
  `<h1>`. Command: `/impeccable harden`.
- **[P2] No feature highlights** — Category: IA. Impact: nothing communicates the
  three things the app actually does (journal, AI review, analytics). Fix: 3–4
  left-aligned feature blurbs in a non-symmetric layout (not an icon-circle grid).
  Command: `/impeccable shape`.
- **[P3] Fixed `margin-top:8vh` + paddings** — Category: Responsive. Impact: minor
  vertical rhythm issues on short viewports. Fix: fluid spacing via `clamp()`.
  Command: `/impeccable adapt`.

### Positive Findings (preserve these)

- Disciplined token usage — colors come from `theme.py`, not hard-coded hexes.
- Honest, restrained copy — no predictive/signal language (project rule R5).
- Dark theme is intentional and matches the app shell.
- Zero DB/data access on the pre-login surface (fast, never errors cold).

### Recommended Actions

1. **[P1] `/impeccable shape`** — define the hero + feature IA for a real landing.
2. **[P1] `/impeccable layout`** — replace centered-everything with an asymmetric,
   left-aligned hero + features split.
3. **[P2] `/impeccable harden`** — semantic `<h1>`, focus states, edge cases.
4. **[P2] `/impeccable polish`** — final pass after the rebuild.

---

## DESIGN PLAN (Step 5) — synthesized from Context7 + impeccable + frontend-design + ui-ux-pro-max

**Register:** product surface with one brand moment (the pre-login screen).
**Identity preservation:** reuse `theme.py` tokens; no new palette.

### Token system (all from `theme.py`)
- Color: bg `#0E1117`, surface `rgba(255,255,255,0.06)`, border `rgba(255,255,255,0.10)`,
  ink `#E8EAED`, secondary `#B4B8BD`, muted `#8E9196`, accent teal `#20808D`,
  loss terra `#A84B2F`. Color strategy: **Restrained** (tinted-dark neutrals + one teal accent ≤10%).
- Type: **Space Grotesk** display, **Inter** body, **JetBrains Mono** for the
  data chip — a real contrast-axis trio (geometric display / humanist body / mono data),
  already committed. No new fonts.

### Layout concept (asymmetric, left-aligned — kills the centered-card tell)
```
┌──────────────────────────────────────────────────────────┐
│  ◹ TradeLens AI            Post-trade journal · SMC/ICT    │  header (left wordmark)
├───────────────────────────────┬──────────────────────────┤
│  HERO (left-aligned)          │   AUTH PANEL              │
│  h1 thesis headline           │   "Sign in to your journal"│
│  subcopy (≤70ch)              │   [ username ]            │
│  scope line (not signals)     │   [ password ]           │
│  ▁▂▃ equity-curve signature   │   ( Sign in )  ← one CTA  │
│                               │   Create account (if inv.)│
├───────────────────────────────┴──────────────────────────┤
│  FEATURES (3 left-aligned blocks, hairline top-rule,      │
│  inline line-SVG icons — NOT boxed cards, NOT icon-circles)│
├──────────────────────────────────────────────────────────┤
│  · Private beta · Reflection only, never signals ·  footer │
└──────────────────────────────────────────────────────────┘
```
- Streamlit: `st.columns([1.3, 1], gap="large")` for hero|auth; the auth column
  holds the real `st.form` widgets (the CTA). Features + header + footer are
  scoped-HTML `st.markdown` blocks. Columns stack on mobile (hero → auth → features).

### Signature element
A subtle **equity curve** SVG in the hero — the trader's own artifact (rising line
with a pullback, teal stroke + faint solid-alpha fill, mirroring the app's real
`equity_curve_chart`). One bold thing; everything else quiet. No gradient, no blob.

### Copy (honest, day-trader-specific, no predictive language — R5)
- h1: "The post-trade journal that reads your charts back to you."
- sub: structured journal from a screenshot + the patterns behind wins and leaks.
- scope: "Reflection only — TradeLens reviews the trade you already took. It never
  generates signals, predictions, or advice."
- features: Screenshot-first journaling · SMC/ICT analytics · Weekly AI review.

### Anti-pattern guardrails (verified at build)
No gradient text, no glassmorphism, no neon, no decorative blobs, no
icon-in-colored-circle grid, no identical boxed-card grid, no side-stripe borders,
no centered-everything (only the auth panel intro is centered; hero is left-aligned).
Hover transitions 150–300ms; `prefers-reduced-motion` honored; AA contrast on dark.

### Verification plan (Step 7)
Re-audit with the same 5 dimensions; confirm P1/P2 from baseline resolved and no
new anti-patterns; boot the page under AppTest; `ruff` + `black`; code-review pass.

---

## AFTER (rebuilt) — Re-audit

Target: the redesigned `_render_login()` (header + asymmetric hero with an
equity-curve signature + left-aligned feature band + one CTA + footer).

### Audit Health Score

| # | Dimension | Before | After | Key change |
|---|-----------|:-----:|:-----:|-----------|
| 1 | Accessibility | 3 | 4 | Hero is a semantic `<h1>`; decorative SVGs `aria-hidden`; equity curve `aria-label`'d; badge text bumped to AA (was teal-on-dark ~4.1:1, now secondary ~9:1). |
| 2 | Performance | 4 | 4 | Still static HTML + one small inline SVG; transitions only on cheap `border-color`. |
| 3 | Theming | 4 | 4 | All colors interpolated from `theme.py` tokens; dark-only; scoped `.tl-land-*` selectors only (R1). |
| 4 | Responsive Design | 3 | 4 | Fluid `clamp()` headline, `repeat(auto-fit,minmax(220px,1fr))` feature grid, `st.columns` stack on mobile, `flex-wrap` header/footer, `ch`/`max-width` caps. No fixed px widths. |
| 5 | Anti-Patterns | 2 | 4 | Centered-everything and single-card removed. No gradient text, glassmorphism, neon, blobs, icon-in-circle, hero-metric, eyebrow, numbered markers, side-stripe borders. |
| **Total** | | **16/20** | **20/20** | **Critical & major anti-patterns cleared.** |

### Anti-Patterns Verdict — PASS

Would someone say "AI made that"? No. The page now reads as an intentional,
subject-specific trading product: a left-aligned thesis headline, an honest
"reflection only — not signals" scope chip, three left-aligned feature blocks with
line-style SVG icons (no colored circles, no boxed-card grid — a full top-rule
divides them), and one signature element drawn from the trader's own world (a
rising **equity curve**). Boldness is spent in exactly one place; everything else
is quiet.

### P0/P1 from baseline — resolution

- **[P1] No value proposition** → RESOLVED: hero headline + subcopy + scope line.
- **[P1] Centered-everything** → RESOLVED: asymmetric 1.35:1 hero/auth split, all
  body copy left-aligned; nothing uses `text-align:center`.
- **[P2] Single-card container** → RESOLVED: header / hero / auth card / feature
  band / footer are distinct regions.
- **[P2] Non-semantic heading** → RESOLVED: hero is an `<h1>`.
- **[P2] No feature highlights** → RESOLVED: three honest, app-real features.
- **[P3] Fixed spacing** → RESOLVED: `clamp()` + fluid grid.

### New anti-patterns introduced? None.

Verified by `tests/test_landing_login.py` (gradient-text, glassmorphism, neon,
side-stripe-border, centered-everything, emoji-icon, and R5 predictive-language
gates) and `tests/test_pages_boot.py` (renders without exception).

### Residual P3 (acceptable polish, non-blocking)

- Feature icons hardcode the teal hex inside the SVG strings (mirrors the existing
  `sidebar.py` wordmark convention) rather than interpolating the token.
- The three feature blocks share one accent rule; distinct content/icons keep them
  from reading as an identical card grid, but a future pass could vary their weight.

### Tooling note

Impeccable skill reported a non-blocking update (installed v3.7.1 → v3.8.0); per
its own directive the current task proceeded without updating.

