# SP1 — Landing Site $10K-Checklist Pass (Design)

**Date:** 2026-07-16
**Status:** Approved by Ayoub (brainstorming session; typography item already shipped)
**Scope:** `site/` only. No app (`src/`) changes. SP2 (Postgres), SP3 (auth service), SP4 (dashboard) are separate specs.

## Context

The marketing site was evaluated against the Metics Media "$10K Checklist" (8 criteria).
Scores: POV 8, Typography 5, Color 9, Hierarchy 8, Imagery 9, Motion 7, Mobile 6, Invisible 7.
This pass closes the gaps. Baseline design language (dark cinematic, `#0d1117` + `#00e5cc`,
candle-motif signature) is unchanged.

## 1. Typography — SHIPPED (`8ae2e31`)

Satoshi (Fontshare, 400/500/700) replaces Inter as `--font-body`; General Sans is the
recorded backup. Schibsted Grotesk display and JetBrains Mono labels unchanged. Buttons
moved from body-face 600 → intentional 500 (Satoshi has no 600; 600 would silently
resolve to 700). Optional later: self-host the three woff2 files.

## 2. Motion — subtraction + one set-piece

**Subtraction (site-wide):**
- Generic translateY+fade reveals retired. Section headers reveal via a left-to-right
  masked line-wipe (`clip-path: inset()`, no vertical movement). All other revealed
  elements fade opacity-only.
- Durations tighten 650ms → 450ms; stagger stays 40ms; single shared easing
  (`--ease`, unchanged).
- The CTA-band backdrop parallax is removed entirely (motion without meaning).
- Hero word-stagger and the tilt showcase are kept as-is (existing earners).

**Set-piece (the one new scroll-linked moment):** In `#how`, the three candle glyphs and
their connecting lines draw themselves in sequence as the user scrolls through the
section — glyph 1 strokes in, line extends to glyph 2, and so on to glyph 3. Driven by
scroll progress (not time) via CSS custom properties set from one rAF-throttled scroll
handler. SVG strokes use `pathLength="1"` + dashoffset; connecting lines use `scaleX`.
`prefers-reduced-motion`: all variables default to the drawn/final state and the JS
driver never attaches.

## 3. Mobile — designed, not shrunk (≤768px)

- **Sticky thumb-zone CTA:** slim fixed bottom bar with one "Open TradeLens" button
  (reads `APP_URL` via `data-app-link`), appearing after the hero leaves the viewport,
  hiding while the footer CTA band is visible. Safe-area padding respected.
- **Full-screen menu:** the nav dropdown becomes a full-viewport overlay — large type
  targets, candle glyph accent, body scroll locked while open, closes on link tap.
- **Full-bleed screenshots:** feature-card images extend edge-to-edge (negative
  margins matching card padding) so the product is legible at 375px.
- **Hero composition tune:** mobile-specific `object-position` for video/poster so the
  candle artwork composes intentionally at portrait ratios.

## 4. Compliance callout restyle

The teal side-tab (`border-left: 2px solid var(--accent)`) — a recognized AI-UI tell —
is replaced with terminal-style corner brackets: thin accent strokes on the top-left and
bottom-right corners of a normally-bordered card. The mono `POST-TRADE ONLY` label and
copy are unchanged (compliance language is load-bearing and untouched).

## 5. Invisible expensive stuff

- Open Graph + Twitter-card meta with a generated 1200×630 `site/assets/og-image.png`,
  produced by screenshotting a purpose-built 1200×630 HTML card (real brand fonts/assets)
  via the existing headless-Chrome CDP driver.
- `<meta name="theme-color" content="#0d1117">`, canonical URL, and minimal JSON-LD
  (`WebSite`). Absolute URLs use the placeholder origin `https://www.tradelens-ai.example`
  with a `TODO` comment — same swap-at-deploy pattern as `APP_URL`.

## 6. Verification

CDP captures at 375/768/1024/1440; forced reduced-motion capture (static final states);
Browser-pane JS probes for the set-piece progress variables and sticky-CTA toggling;
console clean; contrast re-check for any new styles; `grep` proves compliance copy is
byte-identical before/after.

## Out of scope

Font self-hosting; any `src/`, `tests/`, or prompt changes; SP2–SP4.
