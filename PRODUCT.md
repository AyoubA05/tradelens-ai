# PRODUCT.md — TradeLens AI

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

## Brand personality

Three words: **disciplined, precise, calm.** A trading-performance lab, not a
hype machine. Confident and data-honest. Numerals are monospaced; copy is direct
and never promissory.

## Anti-references

- **TradeZella / hype SaaS landing pages**: gradient hero washes, glassmorphism
  cards, "Meet Your AI Trading Partner", icon-in-colored-circle feature grids,
  centered-everything, "100K+ traders" social-proof theater. We borrow the
  *polish*, not the slop.
- Anything that implies signals, predictions, or guaranteed returns.
- Neon "crypto bro" aesthetics; bouncy/elastic motion; emoji as icons.

## Strategic design principles

- **Honest, not promissory.** No predictive language anywhere in UI copy (enforced
  by tests). The product reviews the past; it never forecasts.
- **Dark, data-dense, legible.** Background #0E1117, teal #20808D accent, terra
  #A84B2F for losses. Space Grotesk headings, JetBrains Mono numerals, Inter body.
- **Identity preservation.** A committed design system already exists in
  `components/theme.py`; reuse its tokens, never reinvent colors locally.

## Accessibility

- Dark theme must hold WCAG AA: body text ≥ 4.5:1, large text ≥ 3:1.
- Respect `prefers-reduced-motion` for any added motion.
- Form inputs always labeled; focus states visible (Streamlit defaults retained).
