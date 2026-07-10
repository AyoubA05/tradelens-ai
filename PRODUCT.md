# PRODUCT.md — TradeLens AI

Design/product contract for all UI work. Every UI change must comply.
(Maintained manually — Impeccable is not installed in this environment;
audits are performed manually against this file plus tests/.)

## Register

**Product** (design SERVES the product). TradeLens AI is an app — a post-trade
reflection journal and analytics dashboard. The pre-login screen is the one
brand-shaped surface, but it lives inside a product and must match the app shell.

## Product purpose

A post-trade reflection journal and analytics dashboard for SMC/ICT day traders.
It helps a trader review completed trades, surface behavioral patterns, and get an
AI second opinion on their own journal. It is explicitly **not** a signal app, not
a bot, and not financial advice — nothing in it generates trade ideas, predictions,
or live signals.

## Target users

Serious retail day traders (futures, forex, crypto, equities) who already trade a
defined SMC/ICT methodology and want disciplined post-session review. Context of
use: at a desk, after the session, on a wide monitor, in focus mode — reviewing,
not trading. Often dark rooms / low ambient light (the dark theme is deliberate,
not decorative).

## Identity

- **Product:** TradeLens AI
- **Category:** Financial analytics dashboard / trading journal
- **Tone:** Professional, dark, data-dense, premium fintech
- **Brand personality:** disciplined, precise, calm. A trading-performance lab,
  not a hype machine. Numerals monospaced; copy direct and never promissory.

## Palette (2026-07 UI polish pass — supersedes previous palette)

Teal `#00c2b2` accent on deep charcoal blacks (`#0d0f11` bg, `#13161a` surface).
Success `#22c55e`, danger `#ef4444`, warning `#f59e0b`.
Full token set lives in `src/tradelens/ui/design_system.py` — **the source of
truth**. Never override tokens inline; never re-type hex values in pages.
(Previous source of truth `components/theme.py` is being migrated.)

## Anti-patterns to block

- Colored side borders on cards¹
- Gradient buttons
- Icon circles / icon-in-colored-circle feature grids
- Centered everything
- Purple/violet gradients
- Emoji as design elements
- Hype SaaS patterns: glassmorphism cards, social-proof theater, bouncy motion

¹ Known conflict: the Phase 1C spec defines `.tl-insight-card.strength/.leak/.neutral`
with 3px colored left borders. Owner decision pending — flag at Phase 1.

## Language rules

Blocked everywhere (code, UI copy, prompts): "entry signal", "live trade",
"buy now", "go long", "go short", "trade this", "signal", "alert".
AI output is read-only, reflection-only, never auto-applied. The product
reviews the past; it never forecasts.

## Provenance & confidence (screenshot AI)

- Badges: "Read from label" / "Estimated from markup" / "Not visible"
- Confidence ≥ 0.70 → auto-checked; < 0.70 → unchecked
- Red is for errors only — never for checkbox states

## Accessibility

- Dark theme must hold WCAG AA: body text ≥ 4.5:1, large text ≥ 3:1.
- Respect `prefers-reduced-motion` for any added motion.
- Form inputs always labeled; focus states visible (Streamlit defaults retained).
