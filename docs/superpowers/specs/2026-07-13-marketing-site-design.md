# TradeLens AI — Marketing Site Design

**Date:** 2026-07-13
**Status:** Approved by Ayoub (brainstorming session)
**Scope:** Standalone static marketing website in `site/`, separate from the Streamlit app.

---

## 1. Purpose & positioning

A single-page marketing site for TradeLens AI — a **post-trade reflection journal and
analytics dashboard** for SMC/ICT day traders. This is a real-business site, not a
portfolio mockup. It must optimize for:

- Trust and premium positioning
- Clear product credibility (real app screenshots throughout)
- Future monetization (pricing section structured for later tiers)
- Strong CTA behavior (app handoff)
- Recruiter / investor / user confidence

**Messaging pillars:** post-trade journaling · AI-assisted review · performance
analytics · discipline improvement · strategy-based reflection.

**Hard exclusions (repo compliance + user direction):** nothing that reads as a
signal app, trading bot, prediction engine, live-trading tool, or financial advice.
No profit promises. Copy must pass the CLAUDE.md project-identity rules.

## 2. Architecture

```
site/
  index.html    — single page, semantic sections
  styles.css    — design tokens + all styling (no framework)
  main.js       — scroll choreography, nav behavior, FAQ accordion (vanilla, no deps)
  assets/       — optimized media (videos, posters, logo, screenshots, backdrops)
```

- Vanilla HTML/CSS/JS only. No build step, no framework, no external JS.
- Self-contained: works from `file://`, deploys to Vercel / Netlify / GitHub Pages as-is.
- The Streamlit app (`src/tradelens/ui/`) is untouched.
- Clean handoff: all app links go through one placeholder constant
  (`APP_URL`, default `https://app.tradelens.example` marked `TODO: replace`).

## 3. Design language

**Art direction:** the marketing layer of the same product — matches the app UI.
Dark cinematic, premium SaaS / trading-terminal. Not crypto, not bright fintech,
no purple/blue AI gradients, no cartoon illustrations, no white backgrounds.

- **Tokens:** bg `#0d1117`; surfaces `#161b22` / `#1c232b`; borders `#252a32`-ish 1px;
  accent teal `#00e5cc` (glows, CTAs, data accents — used sparingly); headings white;
  body `#9aa4b2`. Never pure `#000`.
- **Typography:** Inter (300–700) for headings/body; JetBrains Mono for terminal-style
  micro-labels (e.g. `// 02 — ANALYTICS`), numbers, and stats. "Bloomberg meets Notion."
- **Texture:** faint film-grain overlay; 1–2 slow-drifting teal ambient glow blobs;
  glassy dark cards (blur + translucency) over video; thin borders, generous whitespace.

## 4. Assets

| Asset | Source | Use |
|---|---|---|
| Logo | `hf_20260707_025019_….png` (white line-art on black) | Black knocked out to transparency; nav + footer + favicon |
| Video A | `hf_20260707_044726_….mp4` (~4s, 1.5 MB) | Hero looping background |
| Video B | `hf_20260707_045152_….mp4` (~4s, 2.3 MB) | AI deep-dive section ambient background |
| Cockpit still | `hf_20260707_043848_….png` | Gradient-masked backdrop (AI deep dive fallback/poster) |
| Glowing journal still | `hf_20260707_044407_….png` | Final CTA band backdrop |
| Empty-tray still | `hf_20260707_043200_….png` | Available as poster/spot art if needed |
| App screenshots ×6+ | Captured live via headless-Chrome CDP recipe | Feature cards, how-it-works, wizard rail |

Screenshot targets: Trade Journal, Performance Analytics, New Trade step 1
(Screenshot & AI), Psychology step, Trading Calendar, Strategy Profile, plus the
5-step wizard steps for the deep-dive rail. Compressed to WebP, framed in a minimal
browser-chrome mockup. Videos get poster images; posters show instead of video on
narrow screens, `prefers-reduced-motion`, and `Save-Data`.

## 5. Page sections (top → bottom)

1. **Nav** — sticky, glass blur. Logo + wordmark; links: Features · How it works ·
   AI · Pricing · FAQ; CTA button **"Open TradeLens"** → `APP_URL`.
2. **Hero** — Video A loop under dark gradient. Tagline chip *"Post-Trade Journal.
   AI-Powered Growth."* Word-split reveal headline **"Your Trades Have Patterns.
   Find Them."** Sub-headline: *"TradeLens AI is an AI-powered post-trade journal
   that analyzes your setups, psychology, and performance — so you can trade better
   tomorrow."* CTAs: primary **"Open TradeLens"**, secondary **"See How It Works"**
   (smooth-scrolls to features). Support line: *"Built by a trader, for traders."*
3. **Feature showcase** — bento grid, six features with real screenshots + inline SVG
   line icons (stroke style matching logo; no emoji):
   Trade Journal · Performance Analytics · AI Chart Review · Honest Trade Review ·
   Trading Calendar · Strategy Profile. Staggered scroll-in (~40 ms/card).
4. **How it works** — three numbered steps joined by a teal connecting line:
   ① Log your trade (upload chart screenshot, AI reads context) →
   ② AI reviews your setup (compares to your Strategy Profile, flags rule breaks) →
   ③ Track your patterns (which setups win, when rules break, and why).
5. **AI deep dive** — dark band, Video B (or cockpit still) ambient backdrop.
   Horizontal step rail of the 5-step New Trade wizard (Screenshot & AI → Market
   Context → Trade Details → Psychology → Review & Save). Framed compliance note:
   **"Post-trade only. Reflection, not signals."**
6. **Pricing** — single **"Free during beta"** card (feature checklist + CTA), markup
   structured as a tier grid so paid tiers can slot in later. No invented prices.
7. **FAQ** — accessible accordion (~6): Is this a signal service? (No — post-trade
   only) · Which markets/instruments? · Does the AI see my broker account? · What do
   I need to start? · Is my data private? · Does it support SMC/ICT concepts?
8. **Final CTA band** — glowing-journal backdrop, headline *"Trade better tomorrow."*,
   CTA "Open TradeLens".
9. **Footer** — logo, tagline, disclaimer: *TradeLens AI is a post-trade reflection
   journal. It does not provide trade signals, predictions, or financial advice.*

## 6. Motion system

- One rhythm: expo-out `cubic-bezier(0.16,1,0.3,1)`; 150–400 ms micro-interactions.
- Scroll reveals via IntersectionObserver: fade + small translate, transform/opacity
  only, first-reveal only, staggered lists.
- Hero headline word-split stagger once on load; CTA subtle scale-press (0.97);
  gentle parallax on section backdrops; ambient blobs drift slowly (CSS keyframes).
- All motion gated by `prefers-reduced-motion`; reduced-motion = fully static page,
  videos replaced by posters, content immediately visible.

## 7. Performance & responsiveness

- Mobile-first; verified at 375 / 768 / 1024 / 1440. No horizontal scroll.
- Lazy-load below-fold images; explicit dimensions / `aspect-ratio` everywhere (CLS ≈ 0).
- WebP screenshots; preload hero poster + fonts only; `font-display: swap`.
- Videos: `muted playsinline loop autoplay preload="metadata"` + poster.
- Contrast ≥ 4.5:1 body text; visible focus states; semantic headings; alt text;
  keyboard-operable accordion and nav.

## 8. Out of scope

- No backend, no email capture, no analytics scripts, no CMS.
- No changes to the Streamlit app or Python code.
- No multi-page routing (single page + anchors).

## 9. Verification

- Open the built page in the browser; screenshot-verify every section at all four
  breakpoints, with reduced-motion on and off.
- Check console for errors; confirm videos autoplay muted and posters show when
  video is suppressed.
- Copy audit against CLAUDE.md project-identity rules (no signal/prediction language).
