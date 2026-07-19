# SP3 — Premium Auth Experience (Design)

**Date:** 2026-07-17
**Status:** Approved by Ayoub (brainstorming session; all three gate decisions confirmed)
**Scope:** The pre-login auth screen inside the Streamlit app. No auth service, no changes to
token/bcrypt logic, no marketing-site changes.

## Context

SP1 shipped the real marketing landing page (`site/`). SP2 moved the database to Neon Postgres.
The auth *logic* already exists and is solid: HMAC-signed `?auth=` tokens with TTL, bcrypt DB
users (which take precedence over the secrets fallback), invite-gated signup, a `User` model.

SP3 is purely a **presentation** project: the login/signup screens render inside Streamlit and
hit a quality ceiling, and `auth.py` has grown to 620 lines with roughly half of it presentation —
including a full duplicate landing page (header, hero, features band, footer, inline SVGs, ~100
lines of CSS) that now competes with the real marketing site and will inevitably drift from it.

**Approach (decided):** restyle in Streamlit with a focused auth card. Explicitly NOT a separate
auth service — the added deploy target, token-minting endpoint, and CORS surface aren't worth the
marginal design ceiling.

## 1. Structure

`auth.py` splits by responsibility:

- **`auth.py` → logic only.** Tokens (`_issue_token`, `_verify_token`), session persistence
  (`_try_restore`, `_persist_token`), `authenticate_login`, `validate_signup`, `process_signup`,
  `signup_enabled`, `invite_code`, `expected_credentials`, `verify_credentials`,
  `is_authenticated`, `current_user`, `current_user_id`, `require_auth`, `render_logout_button`.
  No HTML, no CSS.
- **`src/tradelens/ui/components/auth_screen.py` (new) → presentation only.** The focused card,
  its scoped CSS, backdrop, form rendering, toggle, error/success states, motion.

`require_auth()` remains the public entry point (every page calls it) and lazily imports
`auth_screen.render_auth_screen()` inside the function body — the same lazy-import pattern
`sidebar.py` already uses, which avoids the circular import (auth_screen needs auth.py's logic).

## 2. Deletions and survivals

**Deleted (~200 lines from `auth.py`):** `_landing_header_html`, `_landing_hero_html`,
`_landing_features_html`, `_landing_footer_html`, `_render_hero_visual`, `_render_login`,
`_IC_SHOT`, `_IC_CHART`, `_IC_REVIEW`, `_EQUITY_SVG`, and `_landing_css`.

**Must survive, relocated into the card:**

- The compliance line, verbatim: **"Reflection only."** followed by *"TradeLens reviews the trade
  you already took. It does not generate signals, predictions, or trade advice."* (load-bearing per
  CLAUDE.md; guarded by an existing test).
- A compact brand lockup (logo mark + wordmark) and a "← Back to tradelens-ai.com" link, so a cold
  visitor who lands directly on the app URL still gets orientation without a duplicate landing page.

## 3. The auth card

Centered, `max-width: 420px`, over `poster-hero.webp` (17 KB, reused from the marketing site for
visual continuity — replaces this screen's use of the 4.8 MB `hero_bg.png`, a large perf win) with a
dark scrim plus the site's grain + teal glow ambience.

Card contents, top to bottom: brand lockup → title ("Welcome back" / "Create your account") →
one-line sub → segmented toggle → fields → full-width primary submit → message region →
compliance note + back-link.

All tokens, type (Satoshi / Schibsted Grotesk / JetBrains Mono), and corner-bracket detailing
inherit from the existing design system. No new visual vocabulary. No side-tab accent borders, no
gradient text, SVG icons only.

## 4. Flow UX

- **Toggle:** native `st.segmented_control` (verified present in Streamlit 1.50) for
  "Sign in" / "Create account" — accessible and keyboard-navigable for free, replacing today's
  primary "Sign In" button with a competing "Create Account" button beneath it.
- **Labels:** visible labels on every field, never placeholder-only.
- **Errors:** rendered adjacent to the form in an `aria-live="polite"` region; copy states cause
  *and* fix ("Incorrect username or password. Check your details and try again."), never a bare
  "Invalid input." Signup surfaces specific recovery text for password mismatch, missing/incorrect
  invite code, and taken username.
- **Submit feedback:** the button disables and shows a spinner during the check, then resolves to
  an in-place error or a success transition into the app.
- **Autofill:** `autocomplete` hints (`username`, `current-password`, `new-password`) so password
  managers work.

**Accepted constraint:** the UX guidance recommends validating on blur, but Streamlit reruns on
every interaction and exposes no true blur hook for `st.text_input`. This design validates on
submit, with `on_change` feedback only where it is cheap and genuinely useful. Blur validation is
explicitly out of scope rather than promised and faked.

## 5. Motion

Deliberately minimal, all gated behind `prefers-reduced-motion`:

- Card entrance: fade + scale from 0.98, ~250ms, expo-out (`cubic-bezier(0.16,1,0.3,1)`), once on load.
- Toggle indicator: slides between segments, ~200ms.
- Error messages: fade in rather than snapping.
- Button press: scale 0.97.
- Crisp focus rings (2px accent, matching the site).

Nothing decorative, nothing looping.

## 6. Mobile

Card goes full-width with 16px gutters; inputs ≥44px tall; backdrop simplified (no heavy blur
stacking) to reduce paint cost on phones.

## 7. Testing

`tests/test_landing_login.py` is rewritten to target `auth_screen`. Assertions that still matter
carry over: compliance line present, SVG icons not emoji, design tokens rather than hardcoded hex,
reduced-motion respected, no gradient text, no side-stripe accent borders. Assertions about the
deleted landing sections are removed. `test_no_centered_everything` was written for the old landing
page and now conflicts by design — a focused auth card *should* be centered — so it is replaced by
an assertion that the card is the intentional, scoped exception.

Verification: full suite green, ruff + black clean, and visual checks at 375 / 768 / 1440 plus
forced reduced-motion.

## 8. Out of scope

Separate auth service; new Higgsfield backdrop (a dedicated auth backdrop remains an optional
polish upgrade *after* this lands, only if the reused poster reads too busy behind the card);
forgot-password and email flows; any change to token or bcrypt logic; marketing-site changes.
