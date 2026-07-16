# SP1 Landing-Site $10K-Checklist Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining $10K-checklist gaps on the marketing site per the approved spec (`docs/superpowers/specs/2026-07-16-sp1-landing-checklist-design.md`): motion subtraction + one scroll-linked set-piece, mobile-specific design, compliance-callout restyle, OG/social meta.

**Architecture:** All changes live in `site/` (vanilla HTML/CSS/JS, no build step). Motion is CSS-custom-property-driven with one rAF-throttled scroll handler; the og-image is produced by screenshotting a purpose-built 1200×630 HTML card with the existing headless-Chrome CDP driver.

**Tech Stack:** HTML/CSS/vanilla JS; Python + headless Chrome CDP (scratchpad `cdp_shot.py`) for asset generation and verification.

## Global Constraints

- Only `site/` (and scratchpad build scripts) may change. **Never touch `src/`, `tests/`, `prompts/`, or Alembic files.**
- Compliance copy is byte-identical before/after: "Post-trade only", "Reflection, not signals. TradeLens reviews trades you've already taken — it never tells you what to trade.", and the footer disclaimer.
- Design tokens unchanged: bg `#0d1117`, accent `#00e5cc`, easing `cubic-bezier(0.16,1,0.3,1)` (`--ease`).
- All motion gated by `@media (prefers-reduced-motion: no-preference)`; reduced-motion users get final/static states.
- Absolute URLs in meta use the placeholder origin `https://www.tradelens-ai.example` with a `TODO: swap at deploy` comment (same pattern as `APP_URL`).
- Serve locally with `cd /Users/ayoub/tradelens-ai/site && python3 -m http.server 8777`. CDP captures use the scratchpad driver (`cdp_shot.py`, from the marketing-site session; recreate per `.claude/` memory `visual-qa-cdp-screenshots` if missing). Verify pages via Browser-pane JS probes where stated.
- Commit after every task; stage `site/` paths explicitly (the branch may carry unrelated dirty files — never `git add -A`).

---

### Task 1: Motion subtraction

**Files:**
- Modify: `site/styles.css` (the `/* ---- scroll reveals ---- */` block, ~line 130; the `.cta-backdrop` rule, ~line 860)
- Modify: `site/main.js` (delete the CTA-parallax block)

**Interfaces:**
- Consumes: existing `[data-reveal]` attributes and `.reveals-armed` armed-state class set by `main.js`.
- Produces: reveal CSS that Task 2/4 elements inherit automatically (any `[data-reveal]` fades opacity-only; `.section-head[data-reveal]` line-wipes).

- [ ] **Step 1: Replace the reveal styles in `site/styles.css`.** Find the block that begins `/* ---- scroll reveals (elements start hidden only when JS arms them) ---- */` and replace its `@media` contents with:

```css
@media (prefers-reduced-motion: no-preference) {
  .reveals-armed [data-reveal] {
    opacity: 0;
    transition: opacity 450ms var(--ease);
    transition-delay: calc(var(--i, 0) * 40ms);
  }

  .reveals-armed [data-reveal].revealed {
    opacity: 1;
  }

  /* Section headers: masked line-wipe, no vertical movement. */
  .reveals-armed .section-head[data-reveal] {
    opacity: 1;
    clip-path: inset(-2% 100% -2% 0);
    transition: clip-path 600ms var(--ease);
  }

  .reveals-armed .section-head[data-reveal].revealed {
    clip-path: inset(-2% -2% -2% 0);
  }
}
```

- [ ] **Step 2: Remove the parallax.** In `site/main.js`, delete the entire block from `/* ---- CTA band: gentle backdrop parallax (desktop only) ---- */` through the end of its `window.addEventListener("scroll", …)` call (the `const ctaBackdrop` block). In `site/styles.css`, restore the backdrop to a static layer:

```css
.cta-backdrop {
  position: absolute;
  inset: 0;
  z-index: 0;
  background: url("assets/backdrop-journal.webp") center 30% / cover no-repeat;
  opacity: 0.35;
}
```

(removes `inset: -32px 0` and `will-change: transform`.)

- [ ] **Step 3: Verify.** Deterministic checks from the shell:

```bash
grep -c "ctaBackdrop" site/main.js          # expect 0
grep -c "translateY(24px)" site/styles.css  # expect 0
grep -c "clip-path: inset" site/styles.css  # expect 2
```

Scroll the page visually once (Browser pane): headers wipe in left→right, cards fade with stagger, nothing moves vertically, CTA band is static.

- [ ] **Step 4: Commit.**

```bash
git add site/styles.css site/main.js
git commit -m "Site: motion subtraction — opacity/clip reveals, parallax removed"
```

### Task 2: How-it-works scroll-drawn candle set-piece

**Files:**
- Modify: `site/index.html` (the three `.step-mark` SVGs inside `#how`)
- Modify: `site/styles.css` (`.step-mark`, `.step::before` rules)
- Modify: `site/main.js` (new scroll driver)

**Interfaces:**
- Consumes: `#how` section and `.step` list from the existing markup; `reducedMotion` boolean already defined at the top of `main.js`.
- Produces: CSS custom property `--how-p` (0→1) on `#how`, consumed only by this task's CSS.

- [ ] **Step 1: Add `pathLength="1"` to every stroke in the three step-mark SVGs** in `site/index.html`. Each `<line …>` and `<rect …>` inside `.step-mark svg` gains the attribute `pathLength="1"` (e.g. `<line x1="3.5" y1="6" x2="3.5" y2="15.5" pathLength="1"></line>`). Content/coordinates unchanged. There are 2 shapes in step 1, 4 in step 2, 6 in step 3.

- [ ] **Step 2: Add the draw CSS** to `site/styles.css`, after the existing `.step::before` rules:

```css
/* Scroll-drawn pattern (set-piece): --how-p is 1 by default so no-JS and
   reduced-motion render the fully drawn state. main.js drives 0→1. */
@media (prefers-reduced-motion: no-preference) {
  .step-mark svg :is(line, rect) {
    stroke-dasharray: 1;
    stroke-dashoffset: 0;
  }

  /* glyph segments: step1 0–.18, step2 .40–.58, step3 .80–1 */
  .step:nth-child(1) .step-mark svg :is(line, rect) {
    stroke-dashoffset: clamp(0, calc(1 - (var(--how-p, 1) - 0) / 0.18), 1);
  }
  .step:nth-child(2) .step-mark svg :is(line, rect) {
    stroke-dashoffset: clamp(0, calc(1 - (var(--how-p, 1) - 0.40) / 0.18), 1);
  }
  .step:nth-child(3) .step-mark svg :is(line, rect) {
    stroke-dashoffset: clamp(0, calc(1 - (var(--how-p, 1) - 0.80) / 0.20), 1);
  }

  /* connecting lines extend between glyph draws: seg1 .18–.40, seg2 .58–.80 */
  .step::before { transform-origin: left center; }
  .step:nth-child(1)::before {
    transform: scaleX(clamp(0, calc((var(--how-p, 1) - 0.18) / 0.22), 1));
  }
  .step:nth-child(2)::before {
    transform: scaleX(clamp(0, calc((var(--how-p, 1) - 0.58) / 0.22), 1));
  }

  @media (max-width: 768px) {
    .step::before { transform-origin: center top; }
    .step:nth-child(1)::before {
      transform: scaleY(clamp(0, calc((var(--how-p, 1) - 0.18) / 0.22), 1));
    }
    .step:nth-child(2)::before {
      transform: scaleY(clamp(0, calc((var(--how-p, 1) - 0.58) / 0.22), 1));
    }
  }
}
```

- [ ] **Step 3: Add the scroll driver** to `site/main.js`, after the tilt-showcase block:

```js
/* ---- how-it-works: candles + lines draw with scroll (set-piece) ---- */

const howSection = document.getElementById("how");

if (howSection && !reducedMotion) {
  howSection.style.setProperty("--how-p", "0");
  let howTicking = false;
  const updateHow = () => {
    const r = howSection.getBoundingClientRect();
    const vh = window.innerHeight;
    const p = Math.min(1, Math.max(0, (vh * 0.9 - r.top) / (r.height + vh * 0.3)));
    howSection.style.setProperty("--how-p", p.toFixed(4));
  };
  updateHow();
  window.addEventListener(
    "scroll",
    () => {
      if (howTicking) return;
      howTicking = true;
      requestAnimationFrame(() => {
        updateHow();
        howTicking = false;
      });
    },
    { passive: true }
  );
}
```

- [ ] **Step 4: Verify.** Browser pane (motion allowed):

```js
window.scrollTo({top: 0, behavior: 'instant'});
new Promise(r => setTimeout(() => {
  const how = document.getElementById('how');
  const before = how.style.getPropertyValue('--how-p');
  how.scrollIntoView({block: 'center', behavior: 'instant'});
  setTimeout(() => r(JSON.stringify({before, after: how.style.getPropertyValue('--how-p')})), 300);
}, 200))
```

Expect: `before` near 0, `after` between 0.4 and 1. Then a forced reduced-motion CDP capture of `#how` (env `CDP_RM=1`, anchor `%23how`): all three glyphs and both lines fully drawn/static. Visually scroll through `#how` once: glyphs stroke in left to right as the connecting line reaches them.

- [ ] **Step 5: Commit.**

```bash
git add site/index.html site/styles.css site/main.js
git commit -m "Site: scroll-drawn candle set-piece in how-it-works"
```

### Task 3: Compliance callout corner brackets

**Files:**
- Modify: `site/styles.css` (`.compliance-note` rules, ~line 700)

**Interfaces:**
- Consumes/produces: nothing shared; pure CSS restyle. HTML and copy untouched.

- [ ] **Step 1: Replace the `.compliance-note` block:**

```css
.compliance-note {
  position: relative;
  margin-top: clamp(36px, 5vw, 56px);
  border: 1px solid var(--border);
  border-radius: 12px;
  background: rgba(22, 27, 34, 0.72);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  padding: 20px 26px;
  max-width: 620px;
}

/* Terminal-style corner brackets replace the side-tab accent border. */
.compliance-note::before,
.compliance-note::after {
  content: "";
  position: absolute;
  width: 18px;
  height: 18px;
  border: 2px solid var(--accent);
  pointer-events: none;
}

.compliance-note::before {
  top: -1px;
  left: -1px;
  border-right: none;
  border-bottom: none;
  border-top-left-radius: 12px;
}

.compliance-note::after {
  bottom: -1px;
  right: -1px;
  border-left: none;
  border-top: none;
  border-bottom-right-radius: 12px;
}
```

(The old `border-left: 2px solid var(--accent);` and `border-radius: 0 12px 12px 0;` are gone.)

- [ ] **Step 2: Verify.**

```bash
grep -c "border-left: 2px solid var(--accent)" site/styles.css   # expect 0
grep -c "compliance-note::before" site/styles.css                # expect 1
# compliance copy byte-identical:
grep -c "Reflection, not signals. TradeLens reviews trades" site/index.html  # expect 1
```

CDP capture anchored at `%23ai`: callout shows thin teal brackets top-left/bottom-right, mono label intact, copy unchanged.

- [ ] **Step 3: Commit.**

```bash
git add site/styles.css
git commit -m "Site: compliance callout — corner brackets replace side-tab border"
```

### Task 4: Mobile designed-not-shrunk

**Files:**
- Modify: `site/index.html` (sticky CTA markup before `</main>`)
- Modify: `site/styles.css` (menu overlay, sticky bar, full-bleed shots, hero tune)
- Modify: `site/main.js` (scroll-lock on menu, sticky-bar observer)

**Interfaces:**
- Consumes: `data-app-link` population from the existing `APP_URL` block (runs on all `[data-app-link]`, including new markup); `.nav-links`/`.nav-toggle` handlers.
- Produces: `.mobile-cta` element + `.show` class; `body.menu-open` class.

- [ ] **Step 1: Sticky CTA markup.** In `site/index.html`, immediately before `</main>`:

```html
    <div class="mobile-cta" role="complementary" aria-label="Quick action">
      <a class="btn btn-primary" data-app-link href="https://tradelens-app.streamlit.app">Open TradeLens</a>
    </div>
```

- [ ] **Step 2: Mobile CSS.** In `site/styles.css`:

Replace the existing `@media (max-width: 768px)` nav block's `.nav-links` rules with a full-screen overlay:

```css
@media (max-width: 768px) {
  .nav-toggle { display: inline-flex; }

  .nav-links {
    display: flex;
    position: fixed;
    inset: 0;
    z-index: 9;
    flex-direction: column;
    justify-content: center;
    align-items: flex-start;
    gap: 8px;
    padding: 88px 32px 40px;
    background: var(--bg);
    opacity: 0;
    pointer-events: none;
    transition: opacity 250ms var(--ease);
  }

  .nav-links.open { opacity: 1; pointer-events: auto; }

  .nav-links > a:not(.btn) {
    font-family: var(--font-display);
    font-size: 1.6rem;
    font-weight: 600;
    color: var(--text);
    padding: 10px 0;
  }

  .nav-links > .btn { margin-top: 22px; width: 100%; }

  body.menu-open { overflow: hidden; }
}
```

Sticky bar + full-bleed + hero tune (append near the end of the stylesheet):

```css
/* ---- mobile-designed decisions (≤768px) ---- */

.mobile-cta { display: none; }

@media (max-width: 768px) {
  .mobile-cta {
    display: block;
    position: fixed;
    left: 12px;
    right: 12px;
    bottom: calc(12px + env(safe-area-inset-bottom, 0px));
    z-index: 8;
    opacity: 0;
    transform: translateY(12px);
    pointer-events: none;
    transition: opacity 300ms var(--ease), transform 300ms var(--ease);
  }

  .mobile-cta.show { opacity: 1; transform: none; pointer-events: auto; }

  .mobile-cta .btn { width: 100%; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5); }

  /* Full-bleed product screenshots inside cards (26px padding + 1px border). */
  .card .shot-frame { margin-inline: -27px; border-radius: 0; border-inline: none; }

  /* Hero art composes for portrait: keep the bright candle cluster in frame. */
  .hero-video { object-position: 62% center; }
}

@media (prefers-reduced-motion: reduce) {
  .mobile-cta { transition: none; transform: none; }
}
```

- [ ] **Step 3: JS.** In `site/main.js`: inside the existing `navToggle` click handler, after the `aria-label` update, add `document.body.classList.toggle("menu-open", open);` and in the link-click close handler add `document.body.classList.remove("menu-open");`. Then append after the how-it-works driver:

```js
/* ---- mobile sticky CTA: visible between hero and footer CTA band ---- */

const mobileCta = document.querySelector(".mobile-cta");

if (mobileCta && "IntersectionObserver" in window) {
  const heroEl = document.getElementById("hero");
  const ctaBand = document.getElementById("cta");
  const state = { heroVisible: true, bandVisible: false };
  const apply = () =>
    mobileCta.classList.toggle("show", !state.heroVisible && !state.bandVisible);
  const vis = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.target === heroEl) state.heroVisible = e.isIntersecting;
        if (e.target === ctaBand) state.bandVisible = e.isIntersecting;
      });
      apply();
    },
    { threshold: 0.05 }
  );
  vis.observe(heroEl);
  vis.observe(ctaBand);
}
```

- [ ] **Step 4: Verify.** Browser pane at 375×812:

```js
window.scrollTo({top: document.getElementById('features').offsetTop, behavior: 'instant'});
new Promise(r => setTimeout(() => r(JSON.stringify({
  stickyShown: document.querySelector('.mobile-cta').classList.contains('show'),
  stickyHref: document.querySelector('.mobile-cta a').href,
})), 400))
```

Expect `stickyShown: true`, href = the deployed app URL. Scroll to `#cta`: `show` drops off. Open the menu: full-screen overlay, body doesn't scroll behind it, link tap closes it. CDP captures at 375 for `#features` (full-bleed screenshots) and hero (art composition).

- [ ] **Step 5: Commit.**

```bash
git add site/index.html site/styles.css site/main.js
git commit -m "Site: mobile pass — full-screen menu, sticky thumb CTA, full-bleed shots, hero tune"
```

### Task 5: OG/social meta + generated og-image

**Files:**
- Create: `site/assets/og-image.png` (generated)
- Modify: `site/index.html` (head block)
- Scratchpad: `og-card.html` (throwaway)

**Interfaces:**
- Consumes: `cdp_shot.py` driver (`CDP_FULL=0`, dpr 1); existing brand assets (`logo.png`, `poster-hero.webp`).
- Produces: `site/assets/og-image.png`, 1200×630.

- [ ] **Step 1: Build the og card page** in the scratchpad as `og-card.html`:

```html
<!doctype html><html><head><meta charset="utf-8">
<link href="https://api.fontshare.com/v2/css?f[]=satoshi@500&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@650&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
  body{margin:0;width:1200px;height:630px;background:#0d1117;overflow:hidden;position:relative;
       font-family:'Schibsted Grotesk',sans-serif;color:#e8eaed}
  .bg{position:absolute;inset:0;background:url('file:///Users/ayoub/tradelens-ai/site/assets/poster-hero.webp') center/cover;opacity:.45}
  .scrim{position:absolute;inset:0;background:linear-gradient(180deg,rgba(13,17,23,.55),rgba(13,17,23,.92))}
  .in{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;padding:0 90px}
  .brand{display:flex;align-items:center;gap:18px}
  .brand img{width:64px;height:64px}
  .brand span{font-size:40px;font-weight:650}.brand em{font-style:normal;color:#00e5cc}
  h1{font-size:78px;font-weight:650;letter-spacing:-0.02em;line-height:1.08;margin:34px 0 0;max-width:900px}
  h1 .find{color:#00e5cc}
  .tag{font-family:'JetBrains Mono',monospace;font-size:22px;color:#9aa4b2;margin-top:28px;letter-spacing:.08em}
</style></head><body>
<div class="bg"></div><div class="scrim"></div>
<div class="in">
  <div class="brand"><img src="file:///Users/ayoub/tradelens-ai/site/assets/logo.png"><span>TradeLens&nbsp;<em>AI</em></span></div>
  <h1>Your Trades Have Patterns. <span class="find">Find Them.</span></h1>
  <div class="tag">POST-TRADE JOURNAL · AI-POWERED GROWTH</div>
</div>
</body></html>
```

- [ ] **Step 2: Capture it** (dpr 1, exact OG size; wait for fonts):

```bash
source .venv/bin/activate
SCRATCH=<scratchpad>
CDP_FULL=0 python $SCRATCH/cdp_shot.py "file://$SCRATCH/og-card.html" "$SCRATCH/og-raw.png" 1200 630 5
python3 - <<'EOF'
from PIL import Image
im = Image.open('<scratchpad>/og-raw.png')
if im.size != (1200, 630):           # dpr-2 capture safety
    im = im.resize((1200, 630), Image.LANCZOS)
im.convert('RGB').save('/Users/ayoub/tradelens-ai/site/assets/og-image.png', optimize=True)
print(im.size)
EOF
```

Note: `cdp_shot.py` hardcodes `dpr=2`; either pass through and downscale (above handles it) or view the output to confirm crispness. Inspect the PNG (Read tool) before committing — logo visible, headline legible, no font fallback serif.

- [ ] **Step 3: Head tags.** In `site/index.html`, after the `<meta name="description" …>` line insert:

```html
  <meta name="theme-color" content="#0d1117">
  <!-- TODO: swap www.tradelens-ai.example for the real domain at deploy (same drill as APP_URL) -->
  <link rel="canonical" href="https://www.tradelens-ai.example/">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="TradeLens AI">
  <meta property="og:title" content="TradeLens AI — Post-Trade Journal. AI-Powered Growth.">
  <meta property="og:description" content="An AI-powered post-trade journal that analyzes your setups, psychology, and performance — so you can trade better tomorrow.">
  <meta property="og:url" content="https://www.tradelens-ai.example/">
  <meta property="og:image" content="https://www.tradelens-ai.example/assets/og-image.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="TradeLens AI — Post-Trade Journal. AI-Powered Growth.">
  <meta name="twitter:description" content="An AI-powered post-trade journal that analyzes your setups, psychology, and performance.">
  <meta name="twitter:image" content="https://www.tradelens-ai.example/assets/og-image.png">
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"WebSite","name":"TradeLens AI","url":"https://www.tradelens-ai.example/"}</script>
```

- [ ] **Step 4: Verify.**

```bash
python3 -c "from PIL import Image; im=Image.open('site/assets/og-image.png'); assert im.size==(1200,630), im.size; print('og-image ok', im.size)"
grep -c "og:image" site/index.html      # expect 3 (og:image, og:image:width, og:image:height)
grep -c "summary_large_image" site/index.html  # expect 1
curl -s http://localhost:8777/ | grep -c "theme-color"  # expect 1
```

- [ ] **Step 5: Commit.**

```bash
git add site/index.html site/assets/og-image.png
git commit -m "Site: OG/Twitter meta, canonical, theme-color, generated og-image"
```

### Task 6: Full verification sweep

**Files:**
- Modify: fixes only as found.

- [ ] **Step 1: Breakpoint sweep.** CDP viewport captures (`CDP_FULL=0`) at 375×812, 768×1024, 1024×800, 1440×900 for anchors: top, `%23features`, `%23how`, `%23ai`, `%23pricing`, `%23faq`, `%23cta`. Review contact sheets; fix any overflow/clipping.
- [ ] **Step 2: Reduced-motion capture.** `CDP_RM=1` at 1280×800 and 375×812: page fully static, candles drawn, sticky CTA visible without animation, no hidden content.
- [ ] **Step 3: Console + copy audit.** Browser pane: zero console errors after a full scroll. `grep -inE "signal|predict|guarantee|advice" site/index.html` — every hit still inside disclaimers/FAQ; compliance strings byte-identical (Task 3 grep).
- [ ] **Step 4: Contrast spot-check** on new styles: sticky-CTA button (accent bg/dark text = 10.65:1, unchanged), overlay menu text `--text` on `--bg` (15.7:1). No new muted-on-muted pairs introduced.
- [ ] **Step 5: Lint guard for the repo** (proves no app leakage): `source .venv/bin/activate && ruff check src/ scripts/ | tail -1` → "All checks passed!".
- [ ] **Step 6: Final commit.**

```bash
git add site/ docs/superpowers/plans/2026-07-16-sp1-landing-checklist.md
git commit -m "Site: SP1 verification fixes — landing checklist pass complete"
```
