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


---

## Deploy gotchas — Streamlit Cloud + SQLite

### Schema drift on persisted DB (discovered 2026-07-15)

**Root cause:** Streamlit Cloud persists the SQLite DB across deploys. SQLAlchemy's `create_all()` creates missing *tables* but does NOT add missing *columns* to existing tables. So when a new nullable column is added to a model, a fresh deploy against the live DB would skip it — causing `OperationalError` on first query that touches that column.

**How it surfaced:** The `trades` table existed from a prior deploy. A new column was added to the model. `create_all()` ran on boot, saw the table existed, and did nothing. The dashboard hit the missing column and crashed with `sqlalchemy.exc.OperationalError`.

**Fix applied:** `init_db()` now runs a reconcile pass after `create_all()`: it inspects the live table's columns and issues `ALTER TABLE ... ADD COLUMN` for any column present in the model but missing from the DB. This runs on every boot and is idempotent — safe on fresh DBs and existing DBs alike.

**Result:** Any future column additions to models self-heal on next deploy/reboot. This class of bug will not recur.

### Reboot-and-verify checklist (post-merge)

Run this after any hotfix or schema-change PR is merged to `main`:

1. **Confirm merge** — check GitHub `main` branch shows your fix commit as HEAD
2. **Reboot app** — Streamlit Cloud dashboard → three-dot menu → Reboot (or wait for auto-redeploy)
3. **Watch boot logs** — Manage app → Logs; confirm `init_db()` runs without errors
4. **Load dashboard** — open https://tradelenai.streamlit.app and confirm no `OperationalError`
5. **Spot-check data** — verify existing trades still display correctly (no data loss from ALTER)
6. **Log trade** — submit one test trade through New Trade wizard; confirm it saves and appears in Journal
7. **Check AI features** — run one AI recap/grading call; confirm no 500 errors

### Key lesson

`create_all()` is safe for greenfield. For any app with a persisted DB (Streamlit Cloud, Railway, Fly.io, etc.), always pair it with a column-reconcile step. Never assume a redeploy reinitializes the DB.
