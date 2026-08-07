# Phase 2 re-score — the dark workspace against the $10K checklist

**Date:** 2026-08-06
**Scope:** Phase 2, Tasks 1–16, on `codex/full-dark-streamlit-redesign`.
**Baseline:** the 2026-07-21 audit (`docs/audits/2026-07-21-10k-checklist-business-audit.md`).
**Status:** pre-Codex. Nothing here is merged, pushed, or deployed.

## What this scores, and what it does not

The 2026-07-21 audit's own rule applies: **product experience is scored
separately from business proof, and the result may not be inflated because the
theme is more attractive.** This document scores the app only. The marketing
site, the public funnel, policies, and activation measurement are unchanged by
this phase and keep their baseline scores.

A target missed is reported as missed, with what remains.

## Evidence this re-score rests on

- `1997 passed, 7 skipped`. Ruff clean, Black clean, `git diff --check` clean.
- A cross-page browser sweep of **8 destinations × 4 widths = 32 runs**, with
  the pointer state read back from the rendered page on every coarse row
  rather than inferred from the viewport width.
- Reduced-motion runs on Analytics, AI Reviews, Strategy, Settings and the
  Partner, with `prefers-reduced-motion` read back from the page.
- Nine commits, `eaeca32`…`ac8f20e`.

## Scorecard

| # | Item | Baseline | Target | Now | Met? |
|---|---|---:|---:|---:|---|
| 01 | Point of view, not a template | 7.5 | 8.5 | **8.5** | yes |
| 02 | Typography that does work | 8.0 | 8.5 | **8.5** | yes |
| 03 | A restrained colour system | 8.5 | 9.0 | **9.0** | yes |
| 04 | **Hierarchy that breathes** | 6.5 | 8.5 | **8.5** | yes |
| 05 | Imagery with intent | 6.5 | 7.5 | **6.5** | **no — not attempted** |
| 06 | **Motion that whispers** | 6.0 | 7.5 | **7.5** | yes |
| 07 | **Mobile that is designed, not shrunk** | 5.5 | 7.5 | **8.0** | yes |
| 08 | **The invisible expensive stuff** | 4.5 | 7.0 | **7.0** | yes |

**Seven of eight targets met. Item 05 was not attempted** — see below.

---

### 01 — Point of view, not a template · 7.5 → **8.5**

The app no longer looks hosted inside Streamlit. Every destination is built
from the same authored vocabulary: a masthead, ruled KPI strips, section
headers with a teal top-rule, the Evidence Rail, and the dark note sheet.

Phase 2 removed the last two places where a second vocabulary survived. The
Analytics calendar was a **separate component** that predated the dark retarget
and never got it — a money-positive day tinted with the brand teal, literal
pre-redesign hexes, and five raw `st.metric` cards. It now mounts the same
calendar the Journal does. AI Reviews had two different renderings of a review
depending on which lens produced it; all three now read through one shell.

Held back from 9: the ledger is still `st.dataframe`, which is the one surface
a trader can tell is Streamlit.

### 02 — Typography that does work · 8.0 → **8.5**

Generated prose measures **573 px ≈ 71 characters** at 1440 — inside the 68–72
ch band — and 560 / 480 / 295 px at the narrower widths, never stretching into
the unused right side. Mono is confined to metrics, dates, metadata and labels.
Every note opens with one editorial lead sentence, lifted out of the document
so it is never repeated in a section below it.

### 03 — A restrained colour system · 8.5 → **9.0**

Two real over-uses of colour were removed this phase, both found by measuring
rather than by reading:

- The Analytics calendar tinted a **money-positive day with the brand teal**,
  the colour reserved for actions and focus, while the KPI strip and ledger use
  green for exactly that meaning.
- The Settings Danger Zone drew its **perimeter in the danger hue**, so a
  trader opening Settings to change a timezone met a red-framed slab. The
  perimeter is now the neutral strong line; red stays on the heading and the
  two destructive buttons, which is what the comment above the rule had always
  claimed.

Chart heights collapsed to the two the spec names, and no builder sets its own.

### 04 — Hierarchy that breathes · 6.5 → **8.5**

The Analytics lenses follow one shape. AI Reviews shows one section at a time
with a section index, and the Evidence Rail appears **once per note** — it was
appearing under every finding, so a four-finding Patterns note stacked four
rails. Patterns gained the period strip the other two lenses already had, so
one page no longer answers "how big is this sample" two different ways. Two
skipped heading levels (Overview `h2→h4`, Strategy `h1→h5`) were found in the
browser and closed.

### 05 — Imagery with intent · 6.5 → **6.5 (target missed)**

**Not attempted.** Re-capturing the marketing screenshots from coherent seeded
data was in Task 17's scope and was not done. The scoring rule forbids
inflating a score because the underlying product improved, so this keeps its
baseline.

What remains: capture all seven destinations plus the Partner drawer and the
mobile Partner page at 1440 and real coarse 375, from the isolated seeded
scratchpad database, with no owner chrome, and replace the marketing assets.
The capture harness needed for it already exists and is proven.

### 06 — Motion that whispers · 6.0 → **7.5**

Six keyframe animations in total, each tied to a state change rather than
decoration, and all inside `prefers-reduced-motion: no-preference` blocks. The
motion added this phase is the AI Reviews section transition — 170 ms, opacity
and a 4 px lift, keyed on the section id so it **cannot** replay on first load,
on regeneration, or on an error, because none of those change the key.

Loading and state feedback improved rather than being decorated: the Partner
shows a spinner over a conversation that stays put, and a regenerating review
keeps the prior note on screen under an inline status line instead of replacing
it with a skeleton.

Verified under reduced motion on five destinations, with the state read back
from the page.

### 07 — Mobile that is designed, not shrunk · 5.5 → **8.0 (target exceeded)**

Real coarse-pointer captures at 768 and 375 for all eight destinations, with
`pointer: coarse` **and** `pointer: fine` both asserted from the page — a
width-only viewport was never accepted as coarse.

The phone is designed, not hidden: the calendar stays seven columns across with
47×44 day cells at 375; the `More` sheet carries four 190×44 links and is closed
on arrival; the bottom bar reserves its own safe-area inset. The AI Partner has
a **different shape per width** rather than a shrunken one — a drawer at rail
widths, a full destination at bottom-nav widths — and the launcher is
`display: none` below 768 so a keyboard user cannot reach a control they cannot
see.

Above target because the exclusivity is structural: there is no width at which
a floating overlay and the bottom bar both exist.

### 08 — The invisible expensive stuff · 4.5 → **7.0**

- **No rendered exception in any audited state**: 0 across 31 completed sweep
  runs and every lens, drawer and error path driven this phase.
- **Tenant scoping resolved at every call site**, asserted through the AST so
  `create_trade(data)` is judged by where the owner is set rather than by a
  regex window.
- **No secret, DSN, or stack text reachable**: driven with real leaky
  exceptions — a Postgres DSN, an `sk-ant-` key, an SMTP password — through the
  real error builder, and the probe is itself proved able to detect a leak.
- **A data-loss defect closed**: regenerating a Daily Debrief destroyed the
  review a trader already had if the call failed.
- Full suite, Ruff and Black green.

Held at 7.0 rather than higher by the four items in "What is still open".

---

## What is still open

1. **Item 05 not attempted** (above).
2. **`aria-sort` is `null`** on Streamlit's dataframe column headers, and its
   **four toolbar controls have no accessible names**. Both need JavaScript
   injection — which this phase forbids — or replacing the ledger with an
   authored table. Recorded across four handoff entries and deliberately not
   expanded into a ledger replacement.
3. **Focus visibility is not verified.** The sweep uses programmatic
   `element.focus()`, and `:focus-visible` does not match it, so the counts it
   produced measure the probe. Needs real `Tab` dispatch.
4. **Tab order is not verified** by key dispatch. The Partner drawer's "Close is
   the first tab stop" rests on DOM order, which is weaker than walking focus.
5. **Target separation**: one adjacent pair under 8 px on Journal at 768 and on
   Strategy at all widths, both halves of a single field group. Recorded rather
   than silently changed.
6. Tabular numerals cannot reach the canvas-rendered ledger.

## Business scores — unchanged

| Area | Score | Note |
|---|---:|---|
| Marketing visuals only | 82/100 | untouched by this phase |
| Marketing site vs all eight items | 76/100 | untouched |
| Business launch readiness | 44/100 | untouched — public funnel, policies and activation are not this phase |

**Streamlit product polish: 64/100 → 80/100.** Overall premium-business
readiness is not re-scored here, because it is dominated by the business items
this phase did not touch.
