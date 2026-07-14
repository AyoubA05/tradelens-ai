# TradeLens AI Marketing Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the standalone dark-cinematic marketing site in `site/` per the approved spec (`docs/superpowers/specs/2026-07-13-marketing-site-design.md`).

**Architecture:** Single-page vanilla HTML/CSS/JS static site in `site/`, fully separate from the Streamlit app. Assets prepared by throwaway Python scripts (PIL for images, headless-Chrome CDP for live app screenshots and video posters). Motion via CSS transitions + one IntersectionObserver.

**Tech Stack:** HTML5, CSS custom properties, vanilla ES2020 JS, PIL (already installed), headless system Chrome + tornado CDP driver, `python -m http.server` for local preview.

## Global Constraints

- **Do not modify anything under `src/`, `tests/`, `scripts/`, or Alembic files.** The Streamlit app stays untouched.
- All app links use one constant: `const APP_URL = "https://app.tradelens.example"; // TODO: replace with deployed app URL` in `main.js`; HTML anchors get `data-app-link` and are populated by JS (with `href` fallback set to the same placeholder).
- Design tokens (exact): bg `#0d1117`; surface `#161b22`; surface-2 `#1c232b`; border `#252a32`; text `#e8eaed`; muted `#9aa4b2`; accent `#00e5cc`; accent-dim `rgba(0,229,204,0.12)`. Never pure `#000`.
- Fonts: Inter (300,400,500,600,700) + JetBrains Mono (400,500) via Google Fonts, `display=swap`.
- Compliance copy (verbatim requirements): site must state "Post-trade only. Reflection, not signals." in the AI section and the footer disclaimer "TradeLens AI is a post-trade reflection journal. It does not provide trade signals, predictions, or financial advice." Never use: signal(s) app, predictions, win more, guaranteed, profit promise language.
- No emoji as icons — inline SVG line icons only (1.5px stroke, round caps, matching logo line-art).
- Motion: easing `cubic-bezier(0.16,1,0.3,1)`, 150–400ms; transform/opacity only; everything gated by `@media (prefers-reduced-motion: reduce)` → static page, posters instead of videos.
- Every image gets explicit `width`/`height` or `aspect-ratio` (CLS ≈ 0); below-fold images `loading="lazy"`.
- Commit after every task (site files + this plan's checkboxes only; never `git add -A` — the branch has unrelated dirty files).
- Throwaway build scripts live in the session scratchpad, not the repo.

---

### Task 1: Scaffold, tokens, ambience shell

**Files:**
- Create: `site/index.html`
- Create: `site/styles.css`
- Create: `site/main.js`

**Interfaces:**
- Produces: section shells with ids `features`, `how`, `ai`, `pricing`, `faq` (later tasks fill them); CSS custom properties listed in Global Constraints as `--bg`, `--surface`, `--surface-2`, `--border`, `--text`, `--muted`, `--accent`, `--accent-dim`; utility classes `.container` (max-width 1140px, 24px side padding), `.section` (block padding clamp(72px,10vw,140px)), `.kicker` (JetBrains Mono micro-label), `[data-reveal]` (motion hook attribute, animated in Task 8; default styles no-op until then); `.grain` and `.glow` ambience layers.

- [ ] **Step 1: Write `site/index.html`** — `<!doctype html>`, `lang="en"`, viewport meta, title `TradeLens AI — Post-Trade Journal. AI-Powered Growth.`, meta description, `<link rel="icon" href="assets/favicon.png">` (asset lands in Task 2), Google Fonts preconnect + stylesheet link, `styles.css`, deferred `main.js`. Body: fixed `.grain` div, two `.glow` divs, `<header class="nav">` placeholder, `<main>` with empty `<section>` shells (`hero`, `features`, `how`, `ai`, `pricing`, `faq`, `cta`), `<footer>`.
- [ ] **Step 2: Write `site/styles.css` base** — `:root` tokens; reset (`box-sizing`, margin 0); `body { background:var(--bg); color:var(--text); font-family:'Inter',system-ui,sans-serif; line-height:1.6; -webkit-font-smoothing:antialiased; }`; heading scale (`h1: clamp(2.5rem,6vw,4.5rem)` weight 650 letter-spacing -0.02em); `.kicker { font-family:'JetBrains Mono',monospace; font-size:0.75rem; letter-spacing:0.12em; text-transform:uppercase; color:var(--accent); }`; `.grain` = fixed inset-0, pointer-events none, base64 SVG turbulence noise at ~4% opacity, z-index 2; `.glow` = large blurred radial teal gradients (`filter:blur(120px)`, opacity ~0.14) positioned off-canvas edges with slow CSS keyframe drift (gated by reduced-motion); visible `:focus-visible` outlines `2px solid var(--accent)`.
- [ ] **Step 3: Write `site/main.js` stub** — `const APP_URL = "https://app.tradelens.example"; // TODO: replace with deployed app URL` and `document.querySelectorAll('[data-app-link]').forEach(a => a.href = APP_URL);`
- [ ] **Step 4: Verify** — `cd /Users/ayoub/tradelens-ai/site && python3 -m http.server 8777 &`; open `http://localhost:8777` in the Browser pane; confirm dark bg, grain, glows, zero console errors, no horizontal scroll at 375px.
- [ ] **Step 5: Commit** — `git add site/ && git commit -m "Site: scaffold, design tokens, ambience shell"`

### Task 2: Asset preparation (logo, favicon, videos, stills)

**Files:**
- Create: `site/assets/logo.png` (transparent), `site/assets/favicon.png`, `site/assets/hero-loop.mp4`, `site/assets/ai-loop.mp4`, `site/assets/backdrop-cockpit.webp`, `site/assets/backdrop-journal.webp`, `site/assets/spot-empty.webp`
- Scratchpad: `prep_assets.py`

**Interfaces:**
- Produces: the exact asset filenames above, referenced by Tasks 4–7.

- [ ] **Step 1: Write `prep_assets.py` in scratchpad** — PIL script: (a) open `hf_20260707_025019_….png`, convert to RGBA, map luminance→alpha (white lines stay, black→transparent), autocrop to content + 8% margin, save `site/assets/logo.png` at 512px and `favicon.png` at 64px; (b) open the cockpit (`…043848`), journal (`…044407`), empty-tray (`…043200`) PNGs, resize to max 1600px wide, save as WebP quality 78 with the target names; (c) copy `hf_…044726….mp4` → `hero-loop.mp4` and `hf_…045152….mp4` → `ai-loop.mp4`.
- [ ] **Step 2: Run it and verify** — `python3 <scratchpad>/prep_assets.py`; then `ls -la site/assets/` (each WebP < 300 KB) and view `logo.png` on a non-black background to confirm transparency.
- [ ] **Step 3: Commit** — `git add site/assets && git commit -m "Site: prepared brand and backdrop assets"`

### Task 3: Live app screenshots + video posters (CDP)

**Files:**
- Create: `site/assets/shot-journal.webp`, `shot-analytics.webp`, `shot-newtrade.webp`, `shot-insights.webp`, `shot-calendar.webp`, `shot-strategy.webp`, `poster-hero.webp`, `poster-ai.webp`
- Scratchpad: `cdp_shot.py`, `postprocess_shots.py`

**Interfaces:**
- Consumes: memory recipe `visual-qa-cdp-screenshots` (auth token mint, DEMO_MODE launch, tornado CDP driver).
- Produces: the eight WebP files above (screenshots cropped to content, ~1400px wide; posters are first-frames of each video).

- [ ] **Step 1: Launch app** — `TRADELENS_SESSION_SECRET=qa DEMO_MODE=true streamlit run src/tradelens/ui/app.py --server.headless true --server.port 8599 &` (from repo root, venv active); poll `curl -s localhost:8599` until up. Mint token: `TRADELENS_SESSION_SECRET=qa python -c "from src.tradelens.ui.components.auth import _issue_token; print(_issue_token('demo', 1))"`.
- [ ] **Step 2: Recreate `cdp_shot.py`** per memory: launch system Chrome `--headless=new --remote-debugging-port=9333 --user-data-dir=<tmp>`, PUT `/json/new?<url>`, connect via tornado websocket, `Emulation.setDeviceMetricsOverride` (1600×3600, dpr 2), sleep ~12s, `Page.captureScreenshot` → PNG.
- [ ] **Step 3: Capture pages** — Dashboard/calendar (`/?auth=…`), Trades (`/Trades`), Analytics (`/Analytics`), NewTrade (`/NewTrade`), Insights (`/Insights`), Strategy (`/Strategy`) — all with `?auth=<token>`. Also capture posters: `file://` page embedding each video (`muted autoplay`, viewport = video aspect), sleep 1s, screenshot.
- [ ] **Step 4: Post-process** — PIL: crop each page PNG to the meaningful top region (trim Streamlit chrome/sidebar edges consistently; target ~3:2 landscape crops), resize to 1400px wide, save WebP q80 with the target filenames. Posters → WebP at video native size.
- [ ] **Step 5: Verify & clean up** — view each WebP (Read tool) to confirm content shows real data and no auth token/URL bar artifacts; kill streamlit + Chrome.
- [ ] **Step 6: Commit** — `git add site/assets && git commit -m "Site: real app screenshots and video posters"`

### Task 4: Nav + hero

**Files:**
- Modify: `site/index.html` (nav + hero sections), `site/styles.css`, `site/main.js`

**Interfaces:**
- Consumes: `logo.png`, `hero-loop.mp4`, `poster-hero.webp`, `.kicker`, `.container`, `APP_URL` wiring.
- Produces: `.btn` and `.btn-primary`/`.btn-ghost` button styles reused by Tasks 6–7; `data-reveal` attributes consumed by Task 8.

- [ ] **Step 1: Nav HTML/CSS** — fixed header, glass (`background:rgba(13,17,23,0.72); backdrop-filter:blur(14px); border-bottom:1px solid var(--border)`); logo img (28px) + wordmark "TradeLens **AI**"; links Features/How it works/AI/Pricing/FAQ (anchor scroll, `scroll-behavior:smooth` on `html`, gated by reduced-motion); right-aligned `.btn-primary` "Open TradeLens" `data-app-link`. Mobile ≤768px: links hidden, hamburger button toggles a full-width dropdown panel (aria-expanded wired in main.js).
- [ ] **Step 2: Hero HTML** — full-viewport (`min-height:100dvh`) section: `<video class="hero-video" autoplay muted loop playsinline preload="metadata" poster="assets/poster-hero.webp"><source src="assets/hero-loop.mp4" type="video/mp4"></video>` + gradient overlay (`linear-gradient(180deg, rgba(13,17,23,0.55), var(--bg) 92%)`); content: kicker chip *Post-Trade Journal. AI-Powered Growth.*; `<h1>` "Your Trades Have Patterns. Find Them." with each word wrapped in `<span class="w">` by JS for the stagger; sub-headline (spec verbatim); buttons "Open TradeLens" (`data-app-link`) + "See How It Works" (`href="#features"`); support line "Built by a trader, for traders."
- [ ] **Step 3: Hero motion JS/CSS** — on `DOMContentLoaded`, if `matchMedia('(prefers-reduced-motion: no-preference)')`: add `.loaded` to hero; `.w` spans transition from `opacity:0; transform:translateY(0.6em)` staggered 45ms via `transition-delay`. Buttons: `transform:scale(0.97)` on `:active`; 200ms transitions. Video suppression: in JS, if `matchMedia('(max-width:768px)')` or reduced-motion or `navigator.connection?.saveData`, remove the `<source>` and call `video.load()` so the poster shows.
- [ ] **Step 4: Verify** — Browser pane at 1280 and 375: video plays muted on desktop, poster-only at 375; word stagger runs once; nav glass on scroll; anchors scroll; no console errors.
- [ ] **Step 5: Commit** — `git add site/ && git commit -m "Site: nav and cinematic video hero"`

### Task 5: Feature showcase (bento grid)

**Files:**
- Modify: `site/index.html` (`#features`), `site/styles.css`

**Interfaces:**
- Consumes: six `shot-*.webp`; `.kicker`; `.section`.
- Produces: `.card` glass-card style (surface bg, 1px border, 16px radius, hover border→accent-dim + translateY(-2px)) reused by Tasks 6–7; `.shot-frame` browser-chrome mockup (top bar with three 8px dots, `aspect-ratio:3/2`, `overflow:hidden`).

- [ ] **Step 1: Section HTML** — kicker `// 01 — FEATURES`, h2 "Everything your trading journal should have been.", muted intro line. Grid: 6 `.card`s — Trade Journal (`shot-journal`), Performance Analytics (`shot-analytics`), AI Chart Review (`shot-newtrade`), Honest Trade Review (`shot-insights`), Trading Calendar (`shot-calendar`), Strategy Profile (`shot-strategy`). Each: inline SVG icon (24px, 1.5 stroke: book, line-chart, scan/camera, brain, calendar, target), h3, one-liner from the user's brief (compliance-checked), `.shot-frame > img` (`loading="lazy" width=1400 height=933`, alt describing the real page).
- [ ] **Step 2: Grid CSS** — CSS grid: 1 col ≤700px, 2 cols ≤1024px, 3 cols above; first two cards `grid-column: span …` for bento variation on desktop (Journal and Analytics wider); consistent 20px gaps.
- [ ] **Step 3: Verify** — all six screenshots render inside frames at 375/768/1280; hover states smooth; alt text present.
- [ ] **Step 4: Commit** — `git add site/ && git commit -m "Site: feature bento grid with real app screenshots"`

### Task 6: How it works + AI deep dive

**Files:**
- Modify: `site/index.html` (`#how`, `#ai`), `site/styles.css`

**Interfaces:**
- Consumes: `ai-loop.mp4`, `poster-ai.webp`, `backdrop-cockpit.webp`, `shot-newtrade.webp`, `.card`, `.btn` styles.

- [ ] **Step 1: How it works HTML/CSS** — kicker `// 02 — HOW IT WORKS`, h2 "Three steps. Every trade."; 3 columns (stack ≤768px) with JetBrains Mono step numbers `01/02/03`, connected by a 1px teal gradient line (horizontal ::before on desktop, vertical on mobile); steps verbatim from spec §5.4.
- [ ] **Step 2: AI deep dive HTML/CSS** — full-bleed band: background = `ai-loop.mp4` (same suppression rules as hero, poster `poster-ai.webp`; fallback image `backdrop-cockpit.webp`) under `rgba(13,17,23,0.82)` overlay. Content: kicker `// 03 — THE AI LAYER`, h2 "A second set of eyes on every trade — after you take it."; horizontal wizard rail (5 glass chips: Screenshot & AI → Market Context → Trade Details → Psychology → Review & Save; scrollable row on mobile with `overflow-x:auto` + scroll-snap) beside one `.shot-frame` of `shot-newtrade.webp`; framed compliance callout (accent left border, mono label `POST-TRADE ONLY`): "Post-trade only. Reflection, not signals. TradeLens reviews trades you've already taken — it never tells you what to trade."
- [ ] **Step 3: Verify** — band video/poster behavior at both widths; wizard rail scroll-snaps on mobile; compliance callout prominent.
- [ ] **Step 4: Commit** — `git add site/ && git commit -m "Site: how-it-works and AI deep-dive sections"`

### Task 7: Pricing, FAQ, CTA band, footer

**Files:**
- Modify: `site/index.html` (`#pricing`, `#faq`, `#cta`, footer), `site/styles.css`, `site/main.js`

**Interfaces:**
- Consumes: `backdrop-journal.webp`, `logo.png`, `.card`, `.btn` styles, `APP_URL` wiring.

- [ ] **Step 1: Pricing** — kicker `// 04 — PRICING`, h2 "Free while in beta."; a `.tier-grid` (single centered `.card`, max-width 420px, markup as a grid so tiers slot in later): mono price `$0`, "during beta"; checklist (accent check SVGs): Unlimited trade journaling · AI chart review & autofill · Performance analytics · Trading calendar · Strategy profile & honest review; CTA "Open TradeLens" `data-app-link`; fine print "No card required."
- [ ] **Step 2: FAQ accordion** — native `<details>/<summary>` styled as `.card`s (keyboard-accessible for free; custom chevron rotates via `details[open]`); six Q&As from spec §5.7 — the signal-service answer explicitly: "No. TradeLens is a post-trade reflection journal. It analyzes trades you've already taken and never generates trade ideas, predictions, or signals." Others: markets/instruments (any — built around SMC/ICT day-trading concepts), broker account access (no — you log trades and screenshots yourself), what you need (a browser and your trade history), data privacy (your journal is yours; entries are used only to generate your own reviews), SMC/ICT support (killzones, setups, session tagging built in).
- [ ] **Step 3: CTA band + footer** — band: `backdrop-journal.webp` gradient-masked into bg, h2 "Trade better tomorrow.", one-liner, "Open TradeLens" button. Footer: logo + wordmark, tagline, nav links repeated, disclaimer paragraph (Global Constraints verbatim), `© 2026 TradeLens AI`.
- [ ] **Step 4: Verify** — accordion keyboard-operable (tab + enter), only styled-checkmark SVGs (no emoji), disclaimer present, all `data-app-link`s populated.
- [ ] **Step 5: Commit** — `git add site/ && git commit -m "Site: pricing, FAQ, CTA band, footer"`

### Task 8: Motion system + performance polish

**Files:**
- Modify: `site/main.js`, `site/styles.css`, `site/index.html` (add `data-reveal` attributes)

**Interfaces:**
- Consumes: all sections; `.reveal` base class from Task 1.

- [ ] **Step 1: Scroll reveals** — one `IntersectionObserver` (`threshold:0.15, rootMargin:'0px 0px -8% 0px'`): elements with `[data-reveal]` start `opacity:0; transform:translateY(24px)` and transition to visible on first intersection (then unobserve). Stagger within grids via `transition-delay: calc(var(--i) * 40ms)` (set `--i` per card in HTML). Entire block skipped (elements immediately visible) under reduced-motion or when `!('IntersectionObserver' in window)`.
- [ ] **Step 2: Parallax + polish** — subtle backdrop parallax on `#cta` band via `background-attachment` alternative: a `transform:translateY` driven by one passive scroll listener with rAF throttle, ±24px max, desktop + no-preference only. Nav gains `.scrolled` (stronger bg) past 40px.
- [ ] **Step 3: Performance pass** — `<link rel="preload" as="image" href="assets/poster-hero.webp">`; confirm every `<img>` has dimensions/aspect-ratio; lazy-load all below-fold imgs; `fetchpriority="high"` on hero poster; run Browser network panel: initial payload (without videos) < 1.5 MB.
- [ ] **Step 4: Verify** — reduced-motion emulation: page fully static and readable; normal: reveals fire once, 60fps scroll (no layout-shifting animations); console clean.
- [ ] **Step 5: Commit** — `git add site/ && git commit -m "Site: scroll choreography and performance polish"`

### Task 9: Full verification + compliance audit

**Files:**
- Modify: fixes only as found.

- [ ] **Step 1: Breakpoint sweep** — Browser pane screenshots of every section at 375, 768, 1024, 1440; fix any overflow, cramped spacing, or contrast issue found.
- [ ] **Step 2: Copy compliance audit** — `grep -inE "signal|predict|win rate guarantee|guarantee|advice|profit" site/index.html` and review each hit: allowed only inside the explicit "not signals / not advice" disclaimers and factual feature names (e.g. "win rate" as an analytics metric is fine; promises are not).
- [ ] **Step 3: Accessibility spot-check** — tab through nav → CTAs → FAQ; heading order h1→h2→h3; every img alt; contrast of `--muted` on `--bg` ≥ 4.5:1 (9aa4b2 on 0d1117 ≈ 7:1 ✓).
- [ ] **Step 4: Lint guard** — `ruff check src/ scripts/ && pytest tests/ -x -q` to prove the app is untouched (no site files are collected).
- [ ] **Step 5: Final commit** — `git add site/ docs/superpowers/plans/2026-07-13-marketing-site.md && git commit -m "Site: verification fixes; marketing site complete"`
