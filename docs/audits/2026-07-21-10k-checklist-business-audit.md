# TradeLens AI - $10K Checklist and Business Audit

**Date:** 2026-07-21  
**Evidence reviewed:** `The_10K_Checklist.pdf`, marketing screenshots 1-9, Streamlit screenshots 10-28, repository source, targeted tests, and live HTTP checks.  
**Important limitation:** the supplied Vercel preview is access-protected, so its visual grading comes from the screenshots and matching local files in `site/`. The configured production domain is public, but currently serves a different TradeLens page/version. The Streamlit app URL currently redirects anonymous requests through Streamlit platform authentication.

## Executive verdict

TradeLens already looks more expensive than a typical early-stage Streamlit product. The dark palette is disciplined, the marketing hero has a real point of view, the typography is chosen, the screenshots are real, and the motion code is much more intentional than a generic fade-in template.

It does **not yet feel like a finished premium business**. The main gap is not a lack of decoration. It is a lack of trust continuity:

1. The public domain, supplied preview, and app do not form one clean public funnel.
2. The app permits contradictory trade outcomes, and the screenshots expose impossible analytics.
3. Sparse-data charts render as oversized or misleading visualizations instead of calm, explanatory states.
4. Some surfaces still use generic SaaS conventions: repeated rounded cards, icons in tinted circles, glows, and large under-composed blank areas.
5. Multi-user data isolation needs a dedicated audit before inviting more traders; strategy profiles and timezone settings are currently global rather than user-scoped.
6. The business lacks visible trust infrastructure: one canonical positioning statement, public privacy/terms links, support/recovery expectations, and a measurable beta activation funnel.

### Scores

| Area | Score | Meaning |
|---|---:|---|
| Marketing visuals only | **82/100** | Strong art direction; close to premium. |
| Marketing site against all eight checklist items | **76/100** | Mobile/invisible quality is not fully proven, and the live funnel is fragmented. |
| Streamlit product polish | **64/100** | Visually coherent, but sparse states, prototype chrome, and contradictory data reduce trust. |
| Business launch readiness | **44/100** | Public funnel, access, data isolation, policies, and activation measurement need work. |
| Overall premium-business readiness | **66/100** | A credible beta with a strong shell, not yet a premium paid product. |

The fastest path to “more expensive” is therefore: **make the product impossible to distrust, reduce repeated decoration, and make the public journey feel like one company.**

---

## The $10K Checklist scorecard

### 01. Point of view, not a template

**Marketing: 8.5/10**  
**App: 7.5/10**

What works:

- The cinematic dark trading-lab direction is specific to the subject.
- The hero line, candlestick footage, mono data typography, and teal-on-charcoal palette form a coherent identity.
- “Post-trade” positioning is differentiated from the louder trading-tool category.
- The Strategy Profile is a strong product idea: reviews are grounded in the trader's own rules.

What lowers the score:

- The feature section returns to a familiar SaaS bento-card pattern.
- Tinted icon containers, rounded cards, ambient glows, and repeated teal outlines make the middle of the site feel more generated than authored.
- The public domain currently communicates a different positioning and waitlist experience from the supplied site.
- The app still looks visibly hosted inside Streamlit rather than fully owned by the brand.

How to elevate it:

- Keep the hero and trading-lab identity.
- Recompose six feature cards into three editorial product stories: **Review the trade**, **Measure the process**, **Build discipline**.
- Use hairlines, large screenshots, captions, and alternating alignment instead of more containers.
- Pick one positioning sentence and use it on the public domain, auth screen, app title, metadata, and founder outreach.

### 02. Typography that does work

**Marketing: 9/10**  
**App: 8/10**

What works:

- Schibsted Grotesk, Satoshi, and JetBrains Mono are purposeful and avoid default product typography.
- The mono numerals make the product feel like a performance instrument.
- Heading scale and weight are consistent between marketing and app.

What lowers the score:

- The app uses the same strong sans voice almost everywhere; long weekly-review prose becomes a flat wall.
- Some all-caps micro-labels and repeated teal rules are overused, weakening hierarchy.
- Long AI review sections need narrower reading measures, calmer paragraph spacing, and summary-first disclosure.

How to elevate it:

- Keep the existing families.
- Limit mono to metrics, dates, compact metadata, and labels.
- Set AI narratives to a 68-72 character reading measure with stronger section spacing.
- Use one editorial “lead sentence” at the top of weekly and daily reviews, then reveal evidence below.

### 03. A restrained color system

**Marketing: 9/10**  
**App: 8.5/10**

What works:

- Deep charcoal, elevated charcoal, teal, green, and red are a disciplined five-color system.
- Teal is recognizably the brand accent.
- Red and green are mostly semantic in the app.

What lowers the score:

- The marketing site uses teal glow, teal borders, teal icons, teal buttons, and teal labels simultaneously in several sections.
- A giant red bar for a one-trade sample overwhelms the analytics page.
- The production domain currently uses a different experience, weakening color and brand continuity.

How to elevate it:

- Reduce teal coverage by roughly one third: primary actions and one active state per viewport.
- Prefer neutral hairlines over teal outlines on passive containers.
- Do not render large red/green charts until the sample is meaningful.

### 04. Hierarchy that breathes

**Marketing: 7.5/10**  
**App: 6.5/10**

What works:

- The hero has a clear reading order: category, thesis, explanation, action.
- Main app pages use consistent title, subtitle, filters, metrics, and detail sections.
- The sidebar gives the product a stable frame.

What lowers the score:

- The How It Works, pricing, and FAQ screenshots show very large areas of blank space without enough compositional tension.
- The pricing card appears stranded on the left, which reads as unfinished rather than luxurious.
- New Trade has two progress systems at once: text tabs and a numbered rail.
- Sparse analytics occupy full-size chart canvases with almost no information.
- Review & Save contains many “Not entered yet” rows, announcing incompleteness instead of helping the user resolve it.

How to elevate it:

- Use one progress component in New Trade.
- Replace empty chart canvases with a compact explanation and a next action.
- Hide empty review groups and show one “Complete 3 fields” action.
- Give pricing and FAQ an intentional split composition or a narrower centered measure.

### 05. Imagery with intent

**Marketing: 8.5/10**  
**App: 6.5/10**

What works:

- Real product screenshots are used throughout.
- Hero and AI-loop media match the trading-lab direction.
- The strategy banner and app backgrounds feel commissioned for this product.

What lowers the score:

- Several screenshots are too small inside cards to prove product quality.
- The current screenshots include contradictory analytics and platform-owner chrome.
- The same visual grammar repeats: screenshot inside rounded browser frame inside rounded card.

How to elevate it:

- Re-capture the app after data corrections and anonymous-user cleanup.
- Use fewer, larger crops that show one compelling interaction at readable size.
- Add short editorial captions that state what the trader learns, not only what the page contains.

### 06. Motion that whispers

**Marketing: 8.5/10**  
**App: 6/10**

What works:

- The marketing implementation includes custom word entrance, scroll-straightening showcase, candle-line drawing, and reduced-motion handling.
- Motion is mostly tied to meaning rather than random entrance effects.
- Small-screen and data-saving modes suppress video playback.

What lowers the score:

- Too many elements are marked for reveal, which makes motion less special.
- Ambient glow drift adds activity without adding meaning.
- The app's waiting and transition states remain mostly framework-default.

How to elevate it:

- Keep three authored moments only: hero entrance, product-frame settle, workflow line draw.
- Remove ambient drift and most card-by-card reveals.
- In the app, improve loading feedback and button/state transitions rather than adding decorative animation.

### 07. Mobile that is designed, not shrunk

**Marketing: 7.5/10 provisional**  
**App: 5.5/10 provisional**

What works in source:

- Marketing has a full-screen mobile menu, sticky mobile action, portrait art direction, stacked steps, video suppression, and full-bleed screenshots.
- App CSS provides 44px targets and horizontal table scrolling.

What is not proven:

- No phone screenshots were supplied.
- The Streamlit wizard, analytics tables, calendar, and sidebar remain desktop-first.
- Dense tables and wide step indicators need real 375px testing, not only CSS assertions.

How to elevate it:

- Treat 375px as a separate layout review, with screenshots of every marketing section and the five most important app states.
- On phone, prioritize: Dashboard summary, New Trade, Journal row/detail, weekly review summary, and settings. Collapse secondary analytics.

### 08. The invisible expensive stuff

**Marketing: 5.5/10 in the current public funnel**  
**App: 4.5/10 in the current public funnel**

What works:

- Marketing HTML is semantic and includes real title, description, canonical, Open Graph, Twitter, JSON-LD, alt text, native details/summary, focus-visible styles, and reduced-motion support.
- Assets are optimized WebP files; the total static site is about 4.6 MB, with most weight in two videos.
- Targeted design, metadata, metrics, trade-service, and page tests pass: **231 passed**.

Critical gaps:

- The supplied Vercel preview redirects through project SSO.
- `tradelens-ai.com` serves a different marketing site/version than the supplied design.
- The app CTA URL redirects anonymous requests through Streamlit platform authentication.
- The New Trade flow deliberately permits outcome/P&L contradictions; metrics then classify by the text outcome while money metrics use P&L.
- Strategy Profile and timezone services are global rather than user-scoped.
- Public privacy and terms links are absent even though the site makes privacy claims.
- App screenshots expose owner/developer chrome and implementation cost details.

How to elevate it:

- Make one production domain serve the chosen site and one public app URL reach the custom auth screen.
- Add automated public-funnel checks to deployment verification.
- Fix outcome validation, existing-data audit, low-sample states, and per-user isolation before paid acquisition.
- Publish reviewed privacy/terms pages before accepting public beta accounts.

---

## Screenshot-by-screenshot findings

### Marketing screenshots 1-9

1. **Hero:** strongest screen. Clear thesis, good contrast, good asymmetry, useful product preview. Reduce background brightness behind body copy and change the primary action from “Open” to a clearer starting action.
2. **Dashboard showcase:** credible product proof. Increase screenshot sharpness/contrast and ensure visible data is internally coherent.
3. **Journal + analytics:** good bento composition, but the familiar card pattern is the first place the site feels templated.
4. **Feature grid + strategy:** useful breadth, but too many rounded frames and icon containers. Group features into fewer stories.
5. **Three-step workflow:** the information is simple and good; the vertical composition is under-filled. Shorten the section or add one thin product artifact, not more cards.
6. **AI workflow:** strong background and clear five-step idea. The stacked step boxes are visually heavy; use a single vertical rail with labels.
7. **Pricing:** the $0 beta offer is clear. The isolated left card makes the section look incomplete. Center it or pair it with a short “who beta is for” note and beta expectations.
8. **FAQ:** accessible native interaction and sensible questions. The composition is too default; use a two-column heading/list layout on desktop.
9. **Final action/footer:** calm and credible. Add privacy, terms, support, and product-status links after those destinations are real.

### Streamlit screenshots 10-28

10. **Auth:** clean, focused, and consistent. Platform chrome weakens ownership; password recovery/support expectations are missing.
11-12. **Dashboard:** navigation and KPI row are good. An almost-empty equity chart consumes too much space; the quick actions are useful but visually generic.
13-17. **New Trade:** the five-step flow is well considered. The duplicate progress UI is busy, optional inputs lead to an empty review, and the outcome mismatch is allowed to pass.
18. **Journal:** filters and table are readable. “Clear Filters” is visually too primary for a reset action.
19-24. **Analytics:** broad feature coverage, but this is the largest trust failure. One contradictory record produces negative “average win,” 100% win rate with negative P&L, a meaningless drawdown axis, giant single-bar charts, the same best/worst category, and `$-500` formatting.
25-27. **Insights:** confidence labeling is responsible. Long prose needs summary-first hierarchy; internal cost and model-reasoning details feel like debug UI. The generated review correctly notices the contradiction, but the product should prevent it earlier.
28. **Strategy Profile:** differentiated and useful. The strategy service must be user-scoped before multi-user beta growth.

---

## What to preserve

- Dark, calm, post-session trading-lab identity.
- Satoshi + Schibsted Grotesk + JetBrains Mono.
- Charcoal + teal palette with semantic green/red.
- Real product screenshots and custom trading imagery.
- The Strategy Profile concept.
- Evidence and confidence language for AI-assisted review.
- Native, accessible controls where possible.
- Reflection-first, non-promissory positioning.

## What to remove or reduce

- Repeated rounded cards as the answer to every layout problem.
- Tinted icon circles/containers in marketing feature grids.
- Ambient glow drift and excessive reveal choreography.
- Duplicate progress navigation in New Trade.
- Full-size charts with fewer than two meaningful points/categories.
- Developer/owner chrome, internal generation cost, and model-reasoning disclosure in the normal user path.
- Any privacy or security claim that is not backed by a public policy and tested architecture.

---

## Priority roadmap

### P0 - Trust and access (before inviting more users)

1. Select the canonical marketing experience and deploy it to `tradelens-ai.com`.
2. Make the app URL public to anonymous visitors so they reach TradeLens's own auth screen.
3. Block outcome/P&L contradictions at create and edit time; audit existing rows.
4. Make metrics prefer signed P&L when present so old contradictory rows cannot corrupt dashboards.
5. Scope Strategy Profile and timezone settings by user; audit every ID-based read/update/delete service.
6. Publish reviewed privacy and terms pages, then link them from marketing and auth.

### P1 - Premium product polish

1. Replace sparse charts with compact low-data states.
2. Simplify New Trade to one progress system and clearer required/optional hierarchy.
3. Collapse marketing features into three editorial stories and reduce teal decoration.
4. Re-capture trustworthy product screenshots without owner chrome.
5. Replace debug-facing AI details with evidence, sample size, and confidence.

### P2 - Beta activation and proof

1. Measure the activation path: account created -> strategy completed -> first trade -> five trades -> first weekly review.
2. Add a calm onboarding checklist driven by existing records; do not add a new database table.
3. Recruit a small founding cohort and interview them after their first and fifth logged trade.
4. Publish only verified proof: workflow time saved, journal completion, and review consistency. Do not use profit claims.
5. Decide paid packaging only after retention and willingness-to-pay interviews.

### P3 - Scale polish

1. Move from framework-hosted presentation to a branded app domain only if beta usage justifies the infrastructure cost.
2. Add account recovery, account deletion, and a documented support path.
3. Add performance budgets and automated anonymous-funnel monitoring.

---

## Business operating targets for the beta

Use these as decision metrics rather than vanity traffic:

| Funnel stage | Definition | First target |
|---|---|---:|
| Landing-to-app | Marketing visitors who click the primary action | 15%+ |
| Account completion | App visitors who create an account successfully | 60%+ |
| Strategy activation | New accounts with an active Strategy Profile | 60%+ |
| First-value moment | New accounts that save one coherent trade | 45%+ |
| Habit formation | Activated users who log five trades within 14 days | 30%+ |
| Insight activation | Five-trade users who open a weekly review | 60%+ |
| Four-week retention | Activated users who return in week four | 25%+ |

These are internal beta targets, not market benchmarks or public claims. Revisit them after the first 20-30 activated traders.

## Positioning recommendation

Use one sentence everywhere:

> **TradeLens AI is a post-trade journal that turns completed trades into evidence-backed reviews of your process, psychology, and performance.**

Supporting line:

> **It reviews what already happened and never tells you what to trade.**

This is specific, credible, and defensible. It also leaves room for analytics, AI assistance, and strategy-aware review without sounding like a generic coaching product.


---

# Completion record — 2026-07-26

Written after executing the four plans. Each line states what changed and
what proves it. Items that could not be closed from the codebase are named
as such rather than quietly marked done.

## P0 — Trust and access

| # | Finding | Status |
|---|---|---|
| 1 | Canonical marketing on the public domain | **Done 2026-07-26** — `www.tradelensai.io` is live and serves the current build; the apex 308-redirects to it and `SITE_ORIGIN` matches |
| 2 | App URL public to anonymous visitors | **Resolved by decision** — the sign-in gate is intentional. The verifier now passes it when the redirect routes back to the app, and still fails if it strands the visitor |
| 3 | Block outcome/P&L contradictions; audit existing rows | Done. Blocked at create and edit (`trade_validation.py`); `scripts/audit_contradictions.py` reports stored contradictions, exits non-zero, and repairs only on request |
| 4 | Metrics prefer signed P&L | Done — `outcome_masks` decides per row, so a legacy "Win" carrying -$500 counts as the loss it was |
| 5 | Scope Strategy Profile and timezone by user | Done before this session; verified (51 tests) |
| 6 | Publish reviewed privacy and terms | Live at `/privacy` and `/terms` (200 in production) with a real contact address, linked from every page. **Qualified legal review remains owner-gated** |

## P1 — Premium product polish

| # | Finding | Status |
|---|---|---|
| 1 | Sparse charts → compact low-data states | Done — one shared policy; a one-trade dashboard draws zero charts (proved by an AppTest that fails if a chart appears) |
| 2 | One New Trade progress system | Done — the duplicated rail removed; tabs remain as the single system |
| 3 | Three editorial stories; reduce teal | Done — six bento cards replaced; glow drift, the reveal layer, and five glass wizard boxes removed |
| 4 | Re-capture trustworthy screenshots | Done — all seven re-captured from coherent seeded data, no owner chrome |
| 5 | Debug AI details → evidence and confidence | Done — reasoning trace and generation cost removed from the user path |

## P2 — Beta activation and proof

All five done: derived activation status (no event table), one next-step
card, aggregate-only `beta_health.py`, cohort and interview playbooks, and
a paid-beta gate whose conditions are binary.

## P3 — Scale polish

| # | Finding | Status |
|---|---|---|
| 1 | Branded app domain | Marketing is on `tradelensai.io`; the Streamlit app keeps its platform host, which the audit lists as optional and cost-dependent |
| 2 | Account recovery, deletion, documented support | Done — optional recovery email, emailed reset token, hard account deletion including screenshot files, and a support playbook |
| 3 | Automated anonymous-funnel monitoring | Done — `verify_public_funnel.py`. Performance budgets not implemented |

## Checklist items that needed work beyond the plans

- **02 Typography.** Weekly-review prose had no reading measure. Now 68ch
  with paragraph spacing.
- **07 Mobile.** Was "provisional" because no phone screenshots existed.
  Capturing them found the sidebar opening expanded at 390px and covering
  the whole dashboard; fixed to `auto`.

## Known open — 2026-07-26

Everything in the codebase and the deployment is done. What remains needs
a person, not a commit:

1. **Qualified legal review** of `/privacy` and `/terms`. No governing-law
   clause is asserted rather than inventing a jurisdiction.
2. **SMTP credentials**, or password resets handled by hand. Unconfigured,
   a reset says it could not send rather than pretending.
3. **Performance budgets** — the audit's P3.3 half that was not built.
   Funnel monitoring exists; budget thresholds do not.
4. **Cohort evidence** — 20 accounts, 8 first reviews, 5 week-four
   returns. This is the real gate on charging, and it takes a month of
   talking to traders.

## Verified in production — 2026-07-26

- `verify_public_funnel.py` exits 0 against `www.tradelensai.io` and the app.
- `/privacy` and `/terms` return 200 with the real support address.
- Canonical, OG, and JSON-LD URLs resolve to the live origin; no deploy
  token survives in the served HTML.
- All five CTAs point at the configured app origin.
- 1173 tests pass; ruff and black clean.

---

## Phase 2 re-score — 2026-08-06

The dark-workspace redesign (Phase 2, Tasks 1–16, branch
`codex/full-dark-streamlit-redesign`) re-scores the **app** against the eight
items. The marketing site, public funnel, policies and activation measurement
are untouched by that phase and keep the scores above.

Full working: `docs/superpowers/audits/2026-08-06-phase2-dark-rescore.md`.

| # | Item | This audit (app) | Phase 2 target | Phase 2 result |
|---|---|---:|---:|---:|
| 01 | Point of view, not a template | 7.5 | 8.5 | **8.5** |
| 02 | Typography that does work | 8.0 | 8.5 | **8.5** |
| 03 | A restrained colour system | 8.5 | 9.0 | **9.0** |
| 04 | Hierarchy that breathes | 6.5 | 8.5 | **8.5** |
| 05 | Imagery with intent | 6.5 | 7.5 | **6.5 — not attempted** |
| 06 | Motion that whispers | 6.0 | 7.5 | **7.5** |
| 07 | Mobile that is designed, not shrunk | 5.5 | 7.5 | **8.0** |
| 08 | The invisible expensive stuff | 4.5 | 7.0 | **7.0** |

**Streamlit product polish: 64/100 → 80/100.** Seven of eight targets met.
Item 05 was in scope and was not done, so it keeps its baseline rather than
inheriting credit from the product improvements around it.

Item 05's remaining work — and the four accessibility items still open,
including the Streamlit dataframe's null `aria-sort` — are listed in the
re-score document. This phase is pre-Codex: nothing is merged, pushed or
deployed.
