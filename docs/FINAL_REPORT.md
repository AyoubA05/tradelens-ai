# TradeLens AI — Final Report

## What it is, and the problem it solves

TradeLens AI is a post-trade reflection journal and analytics dashboard for
SMC/ICT day traders. I trade off support/resistance, liquidity sweeps, fair
value gaps, order blocks, break of structure and change of character, with
multi-timeframe analysis to set bias — and like most discretionary traders, my
real leak was never the entries. It was inconsistent *process*: taking trades
outside my plan, mismanaging risk-to-reward, and skipping the emotional review
that would have caught the pattern. Generic journals (TradeZella, Edgewonk,
TraderSync) track P&L and let you free-type notes. None of them understand the
structural vocabulary I actually trade in, and none of them grade whether I
followed *my own* rules. TradeLens does both: it reviews every chart, grades the
process against my strategy profile, and remembers the corrections I make so it
stops repeating them.

## Architecture decisions

**Streamlit** because the product is a data-dense internal tool, not a marketing
site — I wanted to spend my time on analytics and AI, not React plumbing.
Multipage structure keeps each surface (New Trade, Analytics, Weekly Review, AI
Partner…) isolated, and a strict rule — *pages render, services compute* — keeps
business logic testable and Streamlit-free.

**SQLite via SQLAlchemy 2.x** for dev speed with a clean Postgres upgrade path.
Every schema change ships as a reversible **Alembic** migration with a tested
`downgrade()` — I treated the database like production from day one, which is why
adding the SMC/ICT fields later was a migration, not a rewrite.

**Anthropic `claude-opus-5`** for every AI feature — screenshot analysis,
autofill, grading, journaling, weekly review, daily debrief, pattern detection
and the AI Partner. Every AI call routes through a single `ai_client.py` — no
page ever touches the API directly — which is what made cost control, caching,
DEMO_MODE, and the correction loop possible to add in one place instead of six.

> **Historical note.** An earlier revision of this project routed three models:
> `claude-fable-5` as the primary, `claude-haiku-4-5` for a cheaper grading
> pre-pass, and `claude-opus-4-8` as an automatic refusal fallback. That routing
> has been retired. The single-client design is exactly what made collapsing it
> to one model a config change plus one deleted branch, rather than a rewrite
> across six services — the strongest evidence for the architecture decision
> above.

**The correction loop** is the decision I'm most happy with. Every time I edit an
AI label, the change is stored and re-injected as token-budgeted few-shot context
into *every* subsequent call. The model converges on how I actually label
structure, so the journal and grades get more "me" over time instead of staying
generically correct.

## AI prompt architecture & cost decisions

Six prompts back six features (vision, journal, grading, weekly, patterns,
partner), each a locked, versioned contract with a strict output the service
validates. The recurring design move is **deterministic pre-processing in pandas,
then one well-shaped model call**: pattern detection computes killzone win rates
and rule-violation cost in code, so the model only interprets real statistics and
can't hallucinate edges. Cost is managed deliberately — every prompt is shaped to
stay small, the AI Partner sends the strategy profile with `cache_control` so
multi-turn chats bill it at cache rates (writes at 1.25x input, reads at 0.1x,
both tracked in `Usage`), weekly review runs at high thinking effort but
short-circuits to zero spend on an empty week, and DEMO_MODE serves cached
fixtures so the public deployment costs nothing. Cost control is a prompt- and
caching-level concern here, not a model-selection one: routing a single feature
to a cheaper model was traded away for one auditable model everywhere.

## Test suite

481+ tests, with ≥80% coverage enforced **per service module** and a CI gate.
Coverage isn't the point — confidence to refactor is. The tests I value most are
the behavioral ones: DST-aware killzone assignment, the edge-leak math, the
zero-network guarantee for all six AI features in DEMO_MODE, every page booting on
an empty database in a subprocess (which caught a real `StreamlitDuplicateElementId`
crash that only appeared with multiple charts), and the cold-start test that
mirrors a fresh cloud deploy. AI failure paths — malformed JSON, refusal,
timeout, missing screenshot — all assert a typed, friendly error, never a stack
trace in the UI.

## What I'd do differently

- **PostgreSQL sooner.** SQLite was right for velocity, but the cloud
  filesystem is ephemeral, so real persistence needs Postgres now, not "later."
- **A dedicated `ai_usage` ledger.** Cost is tracked per persisted analysis;
  per-session features (patterns, partner) aren't in the spend dashboard. One
  usage table would give true per-feature, per-model cost.
- **Unify the error contract.** Some failures return `AIUnavailable`, others
  raise typed exceptions. Both are handled, but one convention would be cleaner.
- **Real-time chart annotation.** Today the AI reads a screenshot; drawing the
  detected order blocks and FVGs back onto the chart would close the loop
  visually.

## What this project demonstrates

I took a vague personal frustration and shipped a tested, deployed product: a
domain-specific schema, a six-pipeline AI layer behind one auditable client with
real cost engineering, reversible migrations, a per-module-enforced test suite, a
green CI pipeline, and a public demo that spends nothing. It shows I can make
pragmatic architecture calls, keep AI features cheap and safe, and hold a quality
bar — discipline a journal is supposed to teach, applied to building the journal
itself.
