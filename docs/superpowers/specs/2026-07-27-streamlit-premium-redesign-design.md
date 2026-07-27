# TradeLens AI — Premium Streamlit App Redesign

**Date:** 2026-07-27

**Status:** Approved direction; written design specification awaiting final review

**Scope:** Signed-in Streamlit product only

**Approach:** Structured Streamlit redesign with custom styling only where it adds clear value

**Delivery constraint:** Preserve current functionality, services, data models, and product claims. Do not push or deploy.

## 1. Executive decision

TradeLens keeps its current marketing site for now. The signed-in Streamlit app is
redesigned as a **Dual-Mode Intelligence Lab**:

- a cool, light workspace for reading, forms, tables, and decisions;
- a dark navigation rail and dark chart instruments for focus and continuity with the
  TradeLens brand;
- a restrained teal system for the single primary action and active state on each view;
- an editorial **Evidence Rail** that connects metrics, observations, sample size, and
  confidence without turning every insight into another card.

The result should feel like a serious post-session research instrument, not a trading
terminal, a generic SaaS dashboard, or a reskinned Streamlit demo.

The redesign does not add broker sync, real-time coaching, predictions, or any other
capability not already present. TradeLens remains a post-trade reflection product.

## 2. Evidence reviewed

This specification is based on:

- `The_10K_Checklist.pdf`;
- marketing screenshots 1–10;
- current Streamlit screenshots 11–35;
- the supplied TradeZella reference screenshots;
- the current Streamlit information architecture and page source;
- `PRODUCT.md`;
- `src/tradelens/ui/design_system.py`;
- the prior `2026-07-21-10k-checklist-business-audit.md`;
- the approved visual decisions from the brainstorming session.

The TradeZella references are used as a quality and organization benchmark, not as a
visual template. TradeLens borrows the clarity of a persistent add-trade action, a calm
calendar, and readable data tables. It does not borrow purple gradients, mascots,
gamified scores, broker-sync claims, or intervention features the product does not have.

## 3. $10K Checklist re-score

This is a screenshot-visible product-design score, not a claim about production speed or
business readiness. Items such as real loading time and keyboard completion remain
implementation acceptance tests.

| Checklist criterion | Marketing now | Streamlit now | Streamlit target | Main gap closed by this spec |
|---|---:|---:|---:|---|
| Point of view, not a template | 8.8/10 | 7.4/10 | 9.2/10 | Evidence-led research lab replaces generic dark dashboard |
| Typography that does work | 9.0/10 | 8.0/10 | 9.2/10 | Clear display, reading, utility, and numeric roles |
| Restrained color | 9.0/10 | 7.5/10 | 9.2/10 | Teal becomes functional; light/dark roles are explicit |
| Hierarchy that breathes | 8.0/10 | 6.3/10 | 9.1/10 | Fewer containers, stronger page composition, calmer density |
| Imagery with intent | 8.5/10 | 6.5/10 | 8.5/10 | Product artifacts become readable; recapture after redesign |
| Motion that whispers | 8.5/10 | 6.0/10 | 8.8/10 | State motion only; no decorative dashboard choreography |
| Mobile designed, not shrunk | 7.5/10 | 5.8/10 | 8.5/10 | Core mobile journeys get their own hierarchy |
| Invisible expensive work | 7.0/10 | 7.0/10 | 9.0/10 | AA contrast, focus, errors, loading, reduced motion, resilience |
| **Total** | **83/100** | **68/100** | **89/100** | Premium product continuity |

The marketing site already clears the visual bar and is frozen. The largest return now
comes from the product: navigation, forms, analytics composition, AI readability, mobile
priority, and failure-state quality.

## 4. Product and user

### Job and audience

The signed-in app serves a serious retail day trader reviewing completed trades after the
session, usually at a desk on a wide monitor. The user wants to understand whether their
process matched their rules, where performance came from, and what evidence deserves
attention next.

### Visitor mode

**Operate**, with a contained **Read** mode inside AI Reviews.

- Operate screens optimize for scanning, predictable controls, and task completion.
- AI Reviews switch to a narrower editorial measure so evidence can be understood without
  becoming a wall of interface chrome.

### Primary outcome

Within one session, a trader can:

1. understand current performance and the next useful review action;
2. log a completed trade without losing context;
3. find a prior trade quickly;
4. analyze one dimension at a time;
5. read an evidence-backed AI review and trace its claims to the journal.

## 5. What stays true

- Python, Streamlit, SQLAlchemy, SQLite/Postgres compatibility, Pandas, and Plotly remain.
- Existing services, AI behavior, database schema, calculations, and saved data remain.
- All AI output stays read-only and user-confirmed.
- The product reviews completed trades only and never predicts what to take next.
- The current fonts remain: Satoshi, Schibsted Grotesk, and JetBrains Mono.
- `src/tradelens/ui/design_system.py` remains the single source of truth for UI tokens.
- Native Streamlit controls are preferred when they are accessible and sufficient.
- Settings and account behavior remain available but visually quiet.

## 6. Non-goals

- No marketing-site redesign in this phase.
- No React, Next.js, FastAPI, custom component framework, or new UI dependency.
- No theme switcher. The hybrid theme is fixed.
- No broker sync, live monitoring, social feed, mascot, gamified score, or invented claim.
- No service-layer or database-schema rewrite for presentation work.
- No purple/violet brand direction, glassmorphism, glowing edges, gradient buttons, or
  decorative ambient motion.
- No full dashboard made from equal rounded cards.
- No deployment or push as part of this specification phase.

## 7. Frontend Design direction contract

### THESIS

TradeLens is a post-trade evidence ledger: the interface should make the relationship
between decision, rule, outcome, and evidence unmistakable. It refuses the category
default of a black terminal filled with glowing KPI cards.

### OWN-WORLD

A cool mineral workspace, ink-dark navigation rail, dark chart instruments, sharp teal
actions, hairline rules, compact metadata, and mono numerals. White panels are rare and
functional; color is reserved for state and data.

### STORY

The trader first sees where the week stands, then what deserves review, then the evidence
behind it. Every deeper view narrows the question instead of adding more dashboard tiles.

### FIRST VIEWPORT

Desktop opens with a dark 248px navigation rail, a light page canvas, a compact page
masthead, a ruled KPI strip, one dominant performance instrument, and a narrow Evidence
Rail containing one observation and one next action. `Log completed trade` is persistent
and unmistakable.

### FORM

Structured Streamlit redesign. The native framework remains the behavioral base; custom
CSS is used for the app shell, typography, tables, evidence treatments, responsive
reflow, and deliberate state transitions.

## 8. Compact visual system

### Palette

The exact values must be contrast-tested in implementation, but these are the approved
starting roles:

| Token role | Value | Use |
|---|---|---|
| Mineral canvas | `#F3F6F6` | Main workspace background |
| Paper panel | `#FFFFFF` | Forms, tables, readable content |
| Mist layer | `#E9EFEF` | Selected rows, filter wells, secondary grouping |
| Ink | `#132125` | Primary light-surface text |
| Graphite rail | `#0F171B` | Sidebar and chart frames |
| Bright teal | `#00E5CC` | Active marks on dark surfaces |
| Deep teal | `#087F74` | Primary action on light surfaces |
| Muted ink | `#5B6A70` | Secondary light-surface text |

Semantic colors on light surfaces use darker AA-safe forms, while the existing brighter
semantic tokens remain available inside dark charts:

- success `#167A47`;
- danger `#B53A43`;
- warning `#A76500`.

Verified initial contrast pairs:

- Ink on Mineral Canvas: 15.19:1
- Muted Ink on Mineral Canvas: 5.17:1
- white on Deep Teal: 4.89:1
- light rail text on Graphite Rail: 16.23:1
- Bright Teal on Graphite Rail: 11.29:1

### Typography

- **Schibsted Grotesk:** page titles and major section headings only.
- **Satoshi:** body, labels, navigation, form text, table text, and AI prose.
- **JetBrains Mono:** currency, dates, R-multiples, sample sizes, compact evidence labels,
  and chart tooltips.

Product typography uses a fixed scale rather than fluid display type:

- page title 30/36, 700;
- section title 22/28, 700;
- subheading 17/24, 700;
- body 16/25, 400;
- compact UI 14/20, 500;
- metadata 12/18, 500;
- metric 26–34, mono 500/600.

AI prose uses a 65–72 character line measure. Data tables can run wider.

### Shape, depth, and spacing

- 4/8px spacing rhythm with page tiers of 16, 24, 32, and 48px.
- 6px controls, 8px panels, 10px overlays; no universal 16px card radius.
- Borders and spacing establish hierarchy before shadows.
- One low elevation token is permitted for overlays and the fixed mobile action bar.
- Passive containers use neutral borders, never teal outlines.
- One primary action per page.

### Iconography

- Use one consistent, restrained line-icon family already viable in Streamlit.
- No emoji as structural icons.
- Icons support labels; top-level navigation never relies on icons alone.
- Icon controls retain an accessible name and a minimum 44×44px target.

## 9. Signature: the Evidence Rail

The Evidence Rail is the memorable TradeLens element. It is a narrow, structured
annotation system that appears beside or below the primary data view.

It contains only information that helps the trader judge an observation:

- observation or thesis;
- evidence count and period;
- confidence;
- the relevant rule, setup, or behavior;
- one next review action;
- a path to the contributing trades.

It is not a generic card, a chatbot bubble, or a decorative sidebar. On Overview it is a
compact right column. In Analytics it becomes a ruled annotation under the dominant
chart. In AI Reviews it becomes the margin evidence for the research note. On mobile it
follows the primary result in normal document order.

## 10. Information architecture

### Desktop navigation

1. **Overview**
2. **Journal**
3. **Analytics**
4. **AI Reviews**
5. **Strategy Profile**

Persistent primary action:

- **Log completed trade**

Quiet utility area:

- Settings
- account identity
- sign out

Current pages are regrouped, not removed:

| New destination | Included views |
|---|---|
| Overview | Dashboard summary, calendar preview, next action, recent trades |
| Journal | Trades, Calendar, Trade Detail |
| Analytics | Performance, Risk, Timing, Setups |
| AI Reviews | Patterns, Weekly Recap, Daily Debrief |
| Strategy Profile | Identity, rules, setups, filters, self-awareness |
| Settings | Timezone, sample data, account, privacy controls |

### Mobile navigation

The core five-item bottom navigation is:

1. Home
2. Log
3. Journal
4. Review
5. More

Analytics, Strategy Profile, and Settings live under More. Mobile navigation does not
duplicate the desktop hierarchy at the same level.

## 11. Page composition

### 11.1 Overview — balanced command center

**Job:** Show where the trader stands and what deserves attention without forcing a tour
of every report.

```text
┌──────── dark rail ────────┬──────────────── light workspace ───────────────┐
│ Brand                     │ Overview                         Date / account │
│ + Log completed trade     ├────────────────────────────────────────────────┤
│ Overview                  │ P&L │ Win rate │ Profit factor │ Expectancy     │
│ Journal                   ├───────────────────────┬────────────────────────┤
│ Analytics                 │ dominant equity /    │ EVIDENCE RAIL          │
│ AI Reviews                │ process instrument   │ observation + action   │
│ Strategy Profile          ├───────────────────────┴────────────────────────┤
│                           │ Calendar preview │ Recent trades              │
│ Settings                  │
└───────────────────────────┴────────────────────────────────────────────────┘
```

Hierarchy:

1. page masthead with active strategy and date range;
2. one ruled KPI strip, not six separate cards;
3. one dominant dark performance instrument;
4. Evidence Rail with one observation and one next action;
5. compact calendar and recent-trades split;
6. secondary links to full Journal and Analytics views.

Current functionality preserved:

- asset filter;
- KPI metrics;
- trading calendar;
- equity curve;
- recent trades;
- activation/next-step logic;
- demo state.

Low-data behavior:

- fewer than four usable time points: replace the oversized chart with a compact trend
  summary and explain what will unlock the chart;
- empty account: one clear start action, a brief workflow preview, and sample-data option;
- demo data is labeled once in the masthead, not repeated as a large banner.

### 11.2 Log completed trade — calm five-step workflow

**Job:** Capture a completed trade accurately with the least avoidable friction.

Steps:

1. Screenshot
2. Context
3. Execution
4. Reflection
5. Review

Rules:

- one progress component only;
- progress labels remain visible on desktop and collapse to current step + count on mobile;
- draft state persists across steps and accidental reruns;
- Back is always available after step one;
- Continue is the single primary action;
- Save completed trade is the final explicit action;
- sticky action row never obscures content;
- required fields are visible and grouped before optional detail;
- validation occurs on blur or attempted navigation, not every keystroke;
- errors sit next to the field and a top summary links to each issue;
- AI suggestions are visually distinct, optional, and user-confirmed;
- an AI failure never blocks manual completion;
- Review shows one completeness summary, not repeated “left blank” rows.

Desktop form width stays readable rather than expanding to the entire canvas. Related
fields use a two-column grid only when they can be compared naturally. Reflection uses a
single-column reading measure.

### 11.3 Journal — quiet ledger

**Job:** Find, compare, and open a completed trade quickly.

Tabs:

- Trades
- Calendar
- Trade Detail

Trades view:

- compact page masthead with count and date range;
- filters in one restrained well, collapsible after use;
- only the active filter summary remains visible when collapsed;
- dense table with sticky header where practical;
- sortable columns use an explicit sort indicator;
- P&L and R use tabular figures;
- win/loss/breakeven use text and a small semantic mark, never full-row color;
- row hover changes background only; it does not lift or scale;
- selected row opens a focused detail view with a predictable back path;
- export/view tools are labeled and keyboard-reachable.

Calendar view:

- month summary and navigation sit on one line;
- day cells show P&L, trade count, and semantic label;
- color is not the only meaning;
- selecting a day updates the detail region below rather than opening a modal.

Trade Detail:

- screenshot and trade facts lead;
- rule adherence, reflection, AI review, and corrections follow in a clear sequence;
- edit and delete are separated; deletion requires confirmation and recovery where
  feasible;
- AI provenance and confidence use the existing exact language contract.

### 11.4 Analytics — one composed instrument panel

**Job:** Answer one performance question at a time.

Tabs:

- Performance
- Risk
- Timing
- Setups

Each tab uses the same composition:

```text
Question / scope / filters
────────────────────────────────────────────────────────────
ruled KPI strip with 3–5 relevant values
┌──────────────── dominant dark instrument ────────────────┐
│ chart with units, direct labels, tooltip, sample context │
└───────────────────────────────────────────────────────────┘
ranked evidence / comparison table
────────────────────────────────────────────────────────────
editorial readout: what changed, evidence, limitation
```

The page is not a collection of reusable cards. Metrics share a ruled strip. The chart is
one deliberate instrument. Supporting comparisons become a ranked table or compact
bar/list. The readout uses a short editorial paragraph with evidence and caveat.

Chart rules:

- trend uses line/area only with enough points;
- category comparison uses sorted bars or a ranked table;
- heatmap requires enough cells and always includes a numeric legend;
- small samples use visible values and a low-data explanation instead of a giant chart;
- no pie or gauge without a real proportional or target question;
- axes include units and readable dates;
- tooltips expose exact values;
- every chart has an adjacent text summary and downloadable/table equivalent;
- red and green are never the only differentiators;
- charts are dark instruments within the light workspace, not a reason to darken the
  entire page.

Tab emphasis:

- **Performance:** equity curve, headline results, recent inflection, drawdown context.
- **Risk:** R distribution, drawdown, risk consistency, largest exposure exceptions.
- **Timing:** ranked session/day evidence and session × day heatmap when sample permits.
- **Setups:** ranked setup performance, sample size, confidence, and contributing trades.

### 11.5 AI Reviews — evidence-backed research note

**Job:** Turn journal evidence into a concise review whose reasoning can be inspected.

Tabs:

- Patterns
- Weekly Recap
- Daily Debrief

The page reads like a research note, not a chatbot and not a grid of insight cards:

```text
AI Review · period · sample · confidence
────────────────────────────────────────────────────────────
Thesis
One clear sentence describing the strongest supported finding.

01  Finding
    concise explanation and implication
    evidence rail: 6 trades · Jul 1–24 · medium confidence

02  Finding
    concise explanation and implication
    evidence rail: contributing trades / rule / limitation

Next review action
one specific journaling or review action

[Evidence used] [Long-form analysis]  collapsed by default
```

Rules:

- the first viewport contains the thesis, sample, confidence, and first finding;
- findings are numbered only because they form a real reading sequence;
- each finding exposes the evidence count and confidence;
- contributing trades can be opened without losing the review;
- limitations and contradictory records are stated plainly;
- long generated prose is secondary and collapsible;
- internal model reasoning, generation cost, and developer/debug detail stay out of the
  normal user path;
- generation provides visible progress and keeps the previous review until replacement
  succeeds;
- failure provides Retry and preserves the rest of the page;
- empty state says what data is missing and links to the one action that unlocks it.

Patterns prioritizes recurring evidence. Weekly Recap reads as a completed-week research
note. Daily Debrief is shorter and action-oriented.

### 11.6 Strategy Profile — playbook, not settings dump

**Job:** Define the rules AI reviews should use as context.

Sequence:

1. strategy identity and active status;
2. instruments and timeframes;
3. entry, stop, profit, and risk rules;
4. setups traded and avoided;
5. session/news filters;
6. common mistakes and self-awareness;
7. save confirmation.

The page uses progressive disclosure. Identity remains open; rule groups are accordions.
The active strategy banner is compact and functional. The save action is sticky only when
there are unsaved changes. Read-only and editable states are visibly distinct.

### 11.7 Settings and account

**Job:** Maintain preferences and account controls without competing with daily work.

Sections:

- review timezone and display preferences;
- demo/sample data;
- account identity and password recovery path;
- data/privacy controls;
- sign out;
- destructive account action, visually separated.

Settings uses standard controls and minimal custom styling. No decorative chart, banner,
or feature promotion belongs here.

## 12. States and feedback

### Loading

- under 300ms: no blocking indicator;
- over 300ms: local skeleton or progress state that reserves final layout space;
- AI generation: named stage/progress in the current region;
- charts: skeleton of the chart frame, never an empty axis;
- buttons disable during submission to prevent duplicates.

### Empty

Every empty state answers:

1. what is unavailable;
2. why;
3. what one action unlocks it.

No empty state uses a decorative illustration as a substitute for direction.

### Error

- errors state cause and recovery path;
- field errors appear adjacent to the field;
- multi-error forms include an anchored summary;
- data and AI failures preserve the last usable content;
- raw exceptions never appear in the user interface;
- red remains reserved for error or negative financial data.

### Success

- save confirmations use concise, consistent language;
- a non-blocking status message confirms completion;
- focus moves to the meaningful next region;
- success is not celebrated with confetti or a page animation.

### Overflow

- long setup names wrap before truncating;
- tables scroll inside their own frame on narrow screens;
- full text remains available on focus/selection;
- AI prose never runs edge to edge.

## 13. Responsive behavior

Breakpoints are verified at 1440, 1024, 768, and 375px.

### Desktop, 1024px and above

- persistent dark rail;
- 1200–1320px content max depending on view;
- composed two-column Overview;
- form comparison pairs may use two columns;
- analytics uses one dominant chart plus supporting evidence.

### Tablet, 768–1023px

- navigation rail collapses to a compact labeled drawer;
- Evidence Rail moves below the primary chart;
- KPI strip wraps to two rows without becoming individual cards;
- filter wells use two columns;
- wide tables retain contained horizontal scroll.

### Mobile, 375–767px

- five-item bottom navigation;
- page masthead and primary action remain visible without overlap;
- KPI strip becomes a two-column compact definition list;
- chart summaries lead and dense plots simplify;
- Log flow shows current step and `n of 5`;
- sticky form actions include safe-area padding;
- Journal defaults to the most important columns and opens details as a normal page;
- AI Reviews preserve thesis → findings → evidence order;
- Strategy and deep Analytics sit under More.

Desktop feature parity is not forced into the first mobile release. The required mobile
journeys are Overview summary, Log completed trade, Journal list/detail, and AI Review.

## 14. Motion specification — Emil design engineering pass

Motion is crisp, state-driven, and optional. No page-load choreography is used in the
signed-in product.

Global tokens:

```css
--ease-out: cubic-bezier(0.23, 1, 0.32, 1);
--ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
--ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);
```

| Surface | Should animate? | Purpose | Production decision |
|---|---|---|---|
| Overview | Only direct interactions | Feedback and non-jarring disclosure | Button press 120ms; Evidence Rail disclosure 160ms; no KPI/chart entrance |
| Log flow | Yes, occasionally | Preserve step continuity | Step body crossfade + 4px translate, 180ms ease-out; keyboard step changes are instant |
| Journal | Drastically reduced | Keep frequent navigation fast | Row hover is color only; filter disclosure 160ms; no row stagger or lift |
| Analytics | Only tab/disclosure state | Explain focus change | Active underline/clip 180ms; chart data readable immediately; tooltip becomes instant after first |
| AI Reviews | Yes for generation/disclosure | System status and reading continuity | Progress motion only while waiting; evidence expansion 180ms; no finding-by-finding entrance |
| Strategy Profile | Yes for accordions/save state | Explain disclosure and confirmation | Accordion 180ms; save-state content crossfade; no decorative banner motion |
| Settings | Minimal | Standard control feedback | Button active 120ms; no section animation |
| Mobile drawer | Yes | Spatial consistency | Transform/opacity, 240ms `--ease-drawer`; exit 160ms |

Implementation rules:

- animate transform and opacity only where possible;
- never use `transition: all`;
- never enter from `scale(0)`;
- buttons use a subtle `scale(0.97)` active state without shifting layout;
- hover motion is gated behind `(hover: hover) and (pointer: fine)`;
- frequent and keyboard-initiated actions do not wait for animation;
- `prefers-reduced-motion` removes translation and keeps only brief opacity/color feedback;
- no UI transition exceeds 300ms.

## 15. Accessibility and invisible quality

- WCAG AA contrast for all text, icons, focus rings, semantic states, and chart marks.
- Visible focus is retained and standardized.
- A skip link reaches main content.
- Heading hierarchy follows document order.
- Navigation labels accompany icons.
- Touch targets are at least 44×44px with 8px separation.
- Labels remain visible; placeholders only demonstrate format.
- Route/page change moves focus to the main heading.
- Accordion state, active tab, disabled state, errors, and loading are announced correctly.
- Charts provide a text summary and table/download alternative.
- Dates, currencies, and numbers are locale-aware and use tabular figures.
- No important meaning depends on red/green alone.
- Zoom is never disabled.
- Async regions reserve space to prevent layout shift.
- Font loading uses swap/compatible fallback and avoids unnecessary preloads.
- Below-fold media and expensive views load only when needed.

## 16. Reviewer responsibilities by major page

The named skills are applied as explicit gates, not as a general final pass.

| Page / section | UI/UX Pro Max — main reviewer | Frontend Design — production decisions | Impeccable — polish and cleanup | Emil — premium motion |
|---|---|---|---|---|
| App shell + nav | Validate hierarchy, keyboard order, 44px targets, adaptive nav | Own rail/canvas composition, type roles, Evidence Rail signature | Remove duplicate controls, normalize states, harden overflow | Drawer, active, and press feedback only |
| Overview | Validate scan order, low-data states, chart/table alternative | Compose KPI strip, dominant instrument, evidence balance | Distill repeated cards and decorative banners | No load choreography; disclosure and press only |
| Log flow | Validate progress, labels, validation, recovery, draft safety | Own form measure, grouping, sticky action hierarchy | Clarify helper text, errors, optional fields, success state | Step continuity, upload/generation status |
| Journal | Validate sorting, filter state, selection, accessible table | Own ledger density and calendar/detail relationship | Quiet semantic color, repair overflow and empty states | Frequent row interactions stay instant |
| Analytics | Validate chart choice, units, sample thresholds, fallback | Own one-instrument editorial composition | Remove chart/card wall, normalize legends and caveats | Tab and tooltip transitions only |
| AI Reviews | Validate evidence trace, confidence, reading order | Own research-note composition and numbered findings | Distill prose, remove debug detail, harden generation failure | Progress and evidence disclosure only |
| Strategy Profile | Validate form grouping, read/edit distinction, unsaved state | Own playbook hierarchy and progressive disclosure | Normalize accordions, copy, save/error states | Accordion and save-state feedback |
| Settings | Validate destructive separation and labels | Keep standard, quiet production controls | Harden account, empty, error, and privacy states | Minimal control feedback |
| Responsive pass | Review 375/768/1024/1440 and landscape | Own structural reflow, not scaled desktop | Adapt, clarify, harden every core journey | Verify reduced motion and touch behavior |

UI/UX Pro Max recommendations adopted:

- contrast, keyboard order, focus, labels, responsive breakpoints, loading feedback;
- bottom navigation limited to five items;
- one primary action per screen;
- chart type follows the question;
- charts include exact values and a text/table alternative.

UI/UX Pro Max recommendations intentionally rejected:

- dark mode as the entire product surface;
- glassmorphism, ambient blobs, glows, gradients, and haptic/mobile-library patterns;
- generic Inter typography;
- blue/amber palette;
- route transition choreography.

Those outputs conflict with the approved hybrid direction, existing brand, Streamlit
stack, and the product's calm Operate mode.

## 17. Production architecture

### Styling boundary

- Extend semantic tokens and component rules in `src/tradelens/ui/design_system.py`.
- Keep page files free of raw hex values and ad hoc font declarations.
- Continue removing duplicate theme rules during the existing migration.
- Use custom CSS only for shell, tokens, typography, layout, tables, evidence treatments,
  responsive behavior, and the approved state motion.
- Keep native Streamlit widgets for forms and controls unless a documented UX problem
  requires a small rendering helper.

### Presentation boundary

Page reorganization may create shared presentation helpers, but it must not:

- alter calculation semantics;
- rewrite services;
- change data ownership;
- change AI prompts or model routing unless separately approved;
- modify the database schema;
- silently rename saved fields.

### Likely shared presentation primitives

- app masthead;
- primary action;
- ruled KPI strip;
- filter well;
- empty/loading/error region;
- data ledger/table;
- chart instrument frame;
- Evidence Rail;
- research note;
- sticky form actions;
- responsive navigation.

These are visual/interaction primitives, not a new frontend framework.

## 18. Verification matrix

Each page is checked with realistic states:

| State | Overview | Log | Journal | Analytics | AI Reviews | Strategy | Settings |
|---|---:|---:|---:|---:|---:|---:|---:|
| Typical data | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Empty / first run | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Low sample | ✓ | — | ✓ | ✓ | ✓ | — | — |
| Loading | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Recoverable error | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Long/overflow content | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Keyboard-only | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Reduced motion | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 375px mobile | ✓ | ✓ | ✓ | summary | ✓ | via More | via More |

Quality gates:

1. unit and integration tests stay green;
2. ruff and black stay clean;
3. design-system contract tests cover new tokens and banned raw values;
4. WCAG contrast pairs are measured, not guessed;
5. browser screenshots at all four breakpoints;
6. real keyboard walkthrough of every core journey;
7. one Impeccable mechanical detector run after UI work is finished;
8. Emil slow-motion inspection for the small set of approved transitions;
9. UI/UX Pro Max final checklist review on every destination;
10. no marketing screenshot refresh until the app redesign is stable.

## 19. Delivery sequence

This is the implementation order to expand into the separate execution plan after this
design specification is approved:

1. lock semantic tokens and shell contract;
2. build navigation and shared page structure;
3. redesign Overview;
4. redesign Log completed trade;
5. redesign Journal and Trade Detail;
6. redesign Analytics as composed instruments;
7. redesign AI Reviews as research notes;
8. redesign Strategy Profile and Settings;
9. complete responsive and state matrix;
10. complete accessibility, performance, and motion review;
11. recapture the app screenshots used by the frozen marketing site;
12. prepare deployment separately, only when explicitly authorized.

Each vertical slice uses the four reviewer gates from Section 16 before the next slice
begins. Static hierarchy is approved before Emil motion is added.

## 20. Acceptance criteria

The redesign is complete when:

- all existing functions remain reachable and behave as before;
- the signed-in app uses the fixed light-workspace/dark-instrument hybrid everywhere;
- navigation has five clear destinations plus the persistent log action;
- no major page is composed as an undifferentiated wall of cards;
- Overview communicates status and next review action in its first viewport;
- Log uses one five-step progress system and preserves a draft;
- Journal reads as a quiet ledger and opens a focused detail;
- Analytics presents one question and one dominant instrument at a time;
- AI Reviews begin with a thesis, evidence, sample, and confidence;
- Strategy Profile reads as a playbook;
- every async, empty, low-data, error, success, and overflow state is intentional;
- core mobile journeys work at 375px without horizontal page overflow;
- keyboard navigation, focus, contrast, and reduced motion pass;
- no invented product claim or prohibited post-trade wording is introduced;
- the refreshed app screenshots can replace the current dark/cluttered marketing captures
  without changing the marketing site's art direction.

## 21. Explicit open item after approval

After this design specification is approved, the next artifact is a phased implementation
plan with exact files, tests, verification commands, and reviewer checkpoints. That plan
will also be exported as the single PDF requested for execution.
