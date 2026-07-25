# TradeLens AI Beta Activation and Business Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Turn the current free beta into a measurable, trustworthy learning loop that gets the right traders from account creation to a useful weekly review, while creating verified evidence for later pricing and marketing decisions.

**Architecture:** Keep the existing Streamlit application and SQLite/SQLAlchemy stack. Add one small, user-scoped activation-status service for product guidance and one aggregate-only reporting script for the operator. Store no new behavioral tracking events during beta; derive milestones from records the product already needs. Keep acquisition measurement on the public site privacy-safe and aggregate. This plan begins only after the multi-user isolation plan has shipped.

**Tech Stack:** Python 3.11+, Streamlit, SQLAlchemy, pandas, pytest, Markdown documentation, Vercel Web Analytics

## Global Constraints

- TradeLens is a post-trade journal. Product and marketing copy describes completed-trade reflection only.
- Complete the multi-user isolation plan before implementing activation or reporting.
- Derive milestones from existing user-owned records; do not create a behavioral-event table.
- Never include usernames, journal prose, psychology text, strategy rules, screenshots, or P&L in the operator report.
- Do not publish profit claims, invented testimonials, or claims of trading-performance improvement.
- Privacy and terms content requires owner and qualified legal review before public launch.
- Use `src/tradelens/ui/design_system.py` for app styling tokens; introduce no new UI dependency.
- Use Vercel Web Analytics only for aggregate public-site acquisition events.
- Preserve unrelated dirty work and stage exact paths only.

---

## Dependency order

Complete these plans first:

1. `docs/superpowers/plans/2026-07-21-multi-user-data-isolation.md`
2. Tasks 1–3 of `docs/superpowers/plans/2026-07-21-product-trust-and-premium-ux.md`
3. Tasks 1–2 of `docs/superpowers/plans/2026-07-21-public-funnel-and-premium-site.md`

Do not recruit a broader cohort until the public domain reaches the intended site, the app has one intentional sign-in experience, records are user-isolated, and contradictory outcomes are blocked.

## File structure

- `docs/business/positioning.md` - canonical audience, promise, boundary, differentiation, proof, and voice.
- `src/tradelens/services/activation.py` - pure activation milestone calculation.
- `scripts/beta_health.py` - aggregate-only operator report and CLI.
- `docs/business/beta-scorecard.md` - metric definitions and internal decision rules.
- `docs/business/data-handling-inventory.md` - factual input for reviewed public policies.
- `docs/business/beta-support-playbook.md` - beta support severity and response process.
- `docs/business/founding-cohort-playbook.md` - cohort cadence and evidence rules.
- `docs/business/interview-notes-template.md` - repeatable discovery interview format.
- `docs/business/paid-beta-gate.md` - evidence required before charging.
- `tests/test_activation.py` - activation state behavior.
- `tests/test_beta_health.py` - aggregation and privacy boundaries.
- `tests/test_site_copy.py` - public positioning contract.
- `tests/test_site_trust_links.py` - public trust-destination contract.

### Task 1: Freeze one positioning hierarchy and one public promise

**Files:**
- Create: `docs/business/positioning.md`
- Modify: `site/index.html`
- Test: `tests/test_site_copy.py`

**Interfaces:**
- Consumes: existing semantic homepage structure in `site/index.html`.
- Produces: canonical copy source and exact homepage copy contracts used by later recruitment and trust tasks.

- [x] **Step 1: Write the failing copy contract tests**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "site" / "index.html").read_text(encoding="utf-8")


def test_homepage_leads_with_post_trade_category_and_outcome():
    assert "post-trade journal" in HTML.lower()
    assert "process, psychology, and performance" in HTML.lower()


def test_homepage_states_the_boundary_once_near_the_primary_story():
    assert "never tells you what to trade" in HTML.lower()


def test_homepage_does_not_promise_profit_or_prediction():
    forbidden = ("guaranteed returns", "predict the market", "winning trades")
    assert not any(term in HTML.lower() for term in forbidden)
```

- [x] **Step 2: Run the test and confirm the missing supporting line fails**

Run: `.venv/bin/python -m pytest -q tests/test_site_copy.py`

Expected: FAIL until the exact supporting promise is present.

- [x] **Step 3: Create the positioning source of truth**

Write `docs/business/positioning.md` with this hierarchy:

```markdown
# TradeLens AI Positioning

## Category
AI-assisted post-trade journal

## Primary audience
Self-directed day traders who already take screenshots and journal trades, but struggle to turn those records into consistent process improvement.

## Primary promise
TradeLens AI turns completed trades into evidence-backed reviews of your process, psychology, and performance.

## Boundary
It reviews what already happened and never tells you what to trade.

## Differentiator
Your review is compared with your own Strategy Profile, so the feedback is grounded in your rules instead of generic trading commentary.

## Proof order
1. Completed-trade workflow
2. Strategy-aware review
3. Evidence and confidence labels
4. Performance and psychology patterns over time

## Voice
Calm, direct, specific, candid, and never promotional about trading outcomes.
```

- [x] **Step 4: Align the hero and the first explanatory section**

Keep the existing headline `Your Trades Have Patterns. Find Them.` Use this supporting paragraph directly below it:

```html
<p class="hero__description">
  TradeLens AI turns completed trades into evidence-backed reviews of your
  process, psychology, and performance. It reviews what already happened and
  never tells you what to trade.
</p>
```

Move detailed disclaimers to the footer and FAQ. Keep the one-line boundary in the hero so it works as trust, not legal clutter.

- [x] **Step 5: Run the copy test**

Run: `.venv/bin/python -m pytest -q tests/test_site_copy.py tests/test_site_metadata.py`

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add docs/business/positioning.md site/index.html tests/test_site_copy.py
git commit -m "docs: define TradeLens beta positioning"
```

### Task 2: Add a derived activation status without behavioral surveillance

**Files:**
- Create: `src/tradelens/services/activation.py`
- Create: `tests/test_activation.py`
- Modify: `src/tradelens/ui/app.py`
- Modify: `src/tradelens/ui/pages/6_Insights.py`

**Interfaces:**
- Consumes: `get_active_strategy(user_id: int) -> Optional[dict]`, `get_trades(user_id: int) -> list[Trade]`, and `get_weekly_review(monday: str, user_id: int) -> Optional[dict]` from the isolation plan.
- Produces: `ActivationStatus` and `activation_status(*, strategy: Optional[Mapping[str, Any]], trades: Iterable[Any], weekly_review: Optional[Mapping[str, Any]]) -> ActivationStatus`.

- [x] **Step 1: Write failing service tests**

```python
from types import SimpleNamespace

from src.tradelens.services.activation import activation_status


def _trade(day: str, complete: bool = True):
    return SimpleNamespace(
        trade_date=day,
        result="Win" if complete else None,
        pnl=100.0 if complete else None,
        setup_type="FVG" if complete else None,
        followed_rules=1 if complete else None,
    )


def test_new_user_is_directed_to_strategy_profile():
    status = activation_status(strategy=None, trades=[], weekly_review=None)
    assert status.next_key == "strategy"
    assert status.completed == 0


def test_strategy_owner_is_directed_to_first_complete_trade():
    status = activation_status(
        strategy={"name": "My Process"}, trades=[], weekly_review=None
    )
    assert status.next_key == "first_trade"
    assert status.completed == 1


def test_five_complete_trades_unlock_weekly_review_step():
    trades = [_trade(f"2026-07-{day:02d}") for day in range(1, 6)]
    status = activation_status(
        strategy={"name": "My Process"}, trades=trades, weekly_review=None
    )
    assert status.next_key == "weekly_review"
    assert status.completed == 2


def test_reviewed_user_is_activated():
    trades = [_trade(f"2026-07-{day:02d}") for day in range(1, 6)]
    status = activation_status(
        strategy={"name": "My Process"},
        trades=trades,
        weekly_review={"week_start": "2026-06-29"},
    )
    assert status.next_key is None
    assert status.is_activated is True
```

- [x] **Step 2: Run the tests and confirm the missing module fails**

Run: `.venv/bin/python -m pytest -q tests/test_activation.py`

Expected: FAIL with `ModuleNotFoundError`.

- [x] **Step 3: Implement the pure activation state**

```python
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional


@dataclass(frozen=True)
class ActivationStatus:
    completed: int
    total: int
    next_key: Optional[str]
    is_activated: bool


def _is_complete_trade(trade: Any) -> bool:
    required = ("trade_date", "result", "pnl", "setup_type", "followed_rules")
    return all(getattr(trade, field, None) is not None for field in required)


def activation_status(
    *,
    strategy: Optional[Mapping[str, Any]],
    trades: Iterable[Any],
    weekly_review: Optional[Mapping[str, Any]],
) -> ActivationStatus:
    complete_trades = sum(1 for trade in trades if _is_complete_trade(trade))
    checks = (
        ("strategy", bool(strategy and strategy.get("name"))),
        ("first_trade", complete_trades >= 1),
        ("weekly_review", complete_trades >= 5 and weekly_review is not None),
    )
    completed = sum(1 for _, done in checks if done)
    next_key = next((key for key, done in checks if not done), None)
    return ActivationStatus(
        completed=completed,
        total=len(checks),
        next_key=next_key,
        is_activated=next_key is None,
    )
```

- [x] **Step 4: Render one compact next-step card**

On the Dashboard, show the card only while `is_activated` is false. Use one next action rather than a multi-card checklist:

- `strategy` → `Define your trading process` → `/Strategy`
- `first_trade` → `Journal your first completed trade` → `/NewTrade`
- `weekly_review` → `Review your first useful sample` → `/Insights`

On Insights, when fewer than five complete trades exist, show `Journal X more completed trades to unlock a useful weekly review.` Do not auto-run an AI review on an insufficient sample.

- [x] **Step 5: Test user scoping explicitly**

Add a page-source or integration test proving every call feeding activation status passes `current_user_id()` to strategy, trade, and weekly-review services.

Run: `.venv/bin/python -m pytest -q tests/test_activation.py tests/test_dashboard_metrics.py tests/test_insights_page.py`

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/tradelens/services/activation.py src/tradelens/ui/app.py src/tradelens/ui/pages/6_Insights.py tests/test_activation.py
git commit -m "feat: guide beta users to first useful review"
```

### Task 3: Create an aggregate-only beta health report

**Files:**
- Create: `scripts/beta_health.py`
- Create: `tests/test_beta_health.py`
- Create: `docs/business/beta-scorecard.md`

**Interfaces:**
- Consumes: user-owned Strategy, Trade, and WeeklyReview records after the isolation plan.
- Produces: `compute_beta_health(users: pd.DataFrame, milestones: pd.DataFrame, *, as_of: date) -> dict[str, Any]` and CLI formats `json` and `markdown`.

- [x] **Step 1: Write failing metric tests**

```python
from datetime import date

import pandas as pd

from scripts.beta_health import compute_beta_health


def test_beta_health_counts_users_and_activation_without_identity_fields():
    users = pd.DataFrame(
        [
            {"user_id": 1, "created_at": "2026-07-01"},
            {"user_id": 2, "created_at": "2026-07-02"},
        ]
    )
    milestones = pd.DataFrame(
        [
            {"user_id": 1, "has_strategy": True, "complete_trades": 5, "has_review": True},
            {"user_id": 2, "has_strategy": True, "complete_trades": 1, "has_review": False},
        ]
    )
    report = compute_beta_health(users, milestones, as_of=date(2026, 7, 21))
    assert report == {
        "accounts": 2,
        "strategy_rate": 1.0,
        "first_trade_rate": 1.0,
        "five_trade_rate": 0.5,
        "first_review_rate": 0.5,
        "activation_rate": 0.5,
    }
    assert "username" not in report
```

- [x] **Step 2: Run the test and confirm the missing module fails**

Run: `.venv/bin/python -m pytest -q tests/test_beta_health.py`

Expected: FAIL with `ModuleNotFoundError`.

- [x] **Step 3: Implement pure aggregate calculations**

```python
from datetime import date
from typing import Any

import pandas as pd


def compute_beta_health(
    users: pd.DataFrame,
    milestones: pd.DataFrame,
    *,
    as_of: date,
) -> dict[str, Any]:
    del as_of
    accounts = len(users)
    if accounts == 0:
        return {
            "accounts": 0,
            "strategy_rate": 0.0,
            "first_trade_rate": 0.0,
            "five_trade_rate": 0.0,
            "first_review_rate": 0.0,
            "activation_rate": 0.0,
        }
    scoped = milestones[milestones["user_id"].isin(users["user_id"])]
    ratio = lambda series: round(float(series.sum()) / accounts, 4)
    five_trades = scoped["complete_trades"].fillna(0) >= 5
    reviewed = scoped["has_review"].fillna(False)
    return {
        "accounts": accounts,
        "strategy_rate": ratio(scoped["has_strategy"].fillna(False)),
        "first_trade_rate": ratio(scoped["complete_trades"].fillna(0) >= 1),
        "five_trade_rate": ratio(five_trades),
        "first_review_rate": ratio(reviewed),
        "activation_rate": ratio(five_trades & reviewed),
    }
```

Add a CLI that reads the production database in read-only mode, builds only `user_id` milestone rows in memory, and prints JSON or Markdown. Never print usernames, journal text, screenshots, P&L, psychology text, or strategy rules.

CLI examples:

```bash
.venv/bin/python scripts/beta_health.py --format markdown
.venv/bin/python scripts/beta_health.py --format json
```

- [x] **Step 4: Define the operator scorecard**

Write `docs/business/beta-scorecard.md` with these definitions and decision rules:

| Metric | Definition | Beta decision rule |
|---|---|---|
| Landing → app | Unique public CTA visitors who reach the app host | Investigate routing before copy if the app host is unreachable |
| Account → strategy | Accounts with an active user-owned Strategy Profile | Fix onboarding if under 60% after 20 accounts |
| Account → first trade | Accounts with one complete journal entry | Interview drop-offs if under 50% after 20 accounts |
| Account → five trades | Accounts with five complete entries | Treat as habit formation, not vanity engagement |
| Account → first review | Accounts with one saved weekly review and five complete entries | Primary activation metric |
| Four-week retention | Activated users who journal again in week four | Do not set paid pricing until this can be measured |
| Contradictory records | Stored records where result and P&L disagree | Must remain zero |

The thresholds are internal diagnostic gates, not market benchmarks or investor claims.

- [x] **Step 5: Verify privacy and calculations**

Run: `.venv/bin/python -m pytest -q tests/test_beta_health.py tests/test_trade_service.py tests/test_weekly_review.py`

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add scripts/beta_health.py tests/test_beta_health.py docs/business/beta-scorecard.md
git commit -m "feat: add privacy-safe beta health scorecard"
```

### Task 4: Publish the minimum trust package before broader recruitment

> **Partially deferred (2026-07-24).** The owner chose the factual
> inventory only. Steps 1, 2, 4, 6, and 7 stay open until reviewed
> `/privacy` and `/terms` pages actually exist: wiring footer links to
> destinations that 404, or claiming a deletion path that is not built,
> would be worse than the current silence. See
> `docs/business/data-handling-inventory.md` §7-9.

**Files:**
- Create: `docs/business/data-handling-inventory.md`
- Create: `docs/business/beta-support-playbook.md`
- Modify: `site/index.html`
- Test: `tests/test_site_trust_links.py`

**Interfaces:**
- Consumes: verified production data flows and reviewed policy destinations `/privacy` and `/terms`.
- Produces: factual data inventory, support process, and footer links for privacy, terms, and support.

- [ ] **Step 1: Write failing trust-link tests**

```python
from pathlib import Path


HTML = (Path(__file__).resolve().parents[1] / "site" / "index.html").read_text(
    encoding="utf-8"
)


def test_footer_links_to_privacy_terms_and_support():
    assert 'href="/privacy"' in HTML
    assert 'href="/terms"' in HTML
    assert 'href="mailto:support@tradelens-ai.com"' in HTML
```

- [ ] **Step 2: Run the test and confirm all three links fail**

Run: `.venv/bin/python -m pytest -q tests/test_site_trust_links.py`

Expected: FAIL.

- [x] **Step 3: Create the factual data inventory**

Document, from the code and deployment configuration:

- account fields collected;
- trade and psychology fields stored;
- screenshot locations and lifecycle;
- AI providers and exactly what is sent for each AI feature;
- logging and cost records;
- cookie/analytics behavior on the public site;
- backup, export, correction, and deletion capabilities;
- retention behavior;
- known beta limitations.

This inventory is factual product documentation for counsel and the owner. Do not invent retention promises or legal language.

- [ ] **Step 4: Obtain owner and qualified legal review**

The owner uses the inventory to publish `/privacy` and `/terms`. Treat legal publication as an external approval gate: the implementation is not launch-complete until the actual reviewed pages exist at the production origin.

- [x] **Step 5: Add a plain support operating procedure**

Write `docs/business/beta-support-playbook.md`:

```markdown
# Beta Support Playbook

## Response target
Reply within one business day during the private beta.

## Intake fields
- What were you trying to do?
- What happened instead?
- Which page were you on?
- Approximate time and timezone
- Screenshot only if the user is comfortable sharing it

## Severity
- P0: privacy or cross-account exposure — stop recruitment and investigate immediately
- P1: cannot sign in, save, or view owned records — respond same business day
- P2: incorrect metric or AI review — acknowledge and investigate before using the result as proof
- P3: visual or copy issue — batch into the weekly product review

## Never request
Broker passwords, API secrets, full account statements, or unrelated personal documents.
```

- [ ] **Step 6: Add the reviewed links to the footer**

Use the existing footer style. Do not add a new trust-card section.

- [ ] **Step 7: Verify production routes after deployment**

Run:

```bash
curl -fsS https://tradelens-ai.com/privacy >/dev/null
curl -fsS https://tradelens-ai.com/terms >/dev/null
```

Expected: both commands exit 0 and return the reviewed public pages.

- [x] **Step 8: Commit**

```bash
git add docs/business/data-handling-inventory.md docs/business/beta-support-playbook.md site/index.html tests/test_site_trust_links.py
git commit -m "docs: add beta trust and support package"
```

### Task 5: Run a disciplined 12-person founding cohort

**Files:**
- Create: `docs/business/founding-cohort-playbook.md`
- Create: `docs/business/interview-notes-template.md`

**Interfaces:**
- Consumes: aggregate beta scorecard from Task 3 and support severity model from Task 4.
- Produces: a 12-person cohort protocol, interview evidence format, and weekly owner decision ritual.

- [x] **Step 1: Define the cohort**

Recruit 12 self-directed day traders who already review completed trades. Require a mix of futures and FX traders, but do not recruit people seeking calls, predictions, or managed trading.

Use this cadence:

- Week 0: 20-minute setup interview and observed onboarding;
- Week 1: first completed-trade journal observation;
- Week 2: review the first five completed trades;
- Week 4: retention and willingness-to-pay interview.

- [x] **Step 2: Define interview questions that avoid leading users**

Create `docs/business/interview-notes-template.md` with:

```markdown
# Founding Cohort Interview

## Context
- How do you review completed trades today?
- Show me the last review you completed without TradeLens.
- What is hardest to notice across several trades?

## Product observation
- Please journal one completed trade while thinking aloud.
- Where did you hesitate?
- Which field felt unnecessary or unclear?
- What did the review tell you that your old process did not?
- What did you distrust or need to verify?

## Retention
- When did you choose not to journal a trade, and why?
- Which part would you miss if the beta disappeared tomorrow?
- What result would make this worth paying for?

## Pricing discovery
- What do you pay for your current journaling or review workflow?
- At what monthly price would TradeLens feel too expensive to consider?
- At what monthly price would you question its quality?

## Evidence
- Exact user language:
- Observed behavior:
- Severity:
- Proposed change:
- Evidence needed before changing the product:
```

- [x] **Step 3: Define decision rules**

Write these rules in `docs/business/founding-cohort-playbook.md`:

- Change onboarding when at least 3 of 12 users independently fail at the same step.
- Change a core workflow when at least 3 users show the same high-severity problem and the change preserves the post-trade boundary.
- Do not add a feature from one enthusiastic request; look for repeated behavior.
- Do not use a quote publicly without written permission and a verifiable source.
- Do not claim performance improvement from self-reported satisfaction.
- Pause recruitment immediately for privacy exposure, record loss, or cross-account access.

- [x] **Step 4: Define the weekly owner ritual**

Every Friday:

1. Run the aggregate beta health report.
2. Review P0/P1 support issues.
3. Cluster interview evidence by user problem.
4. Choose at most one onboarding improvement and one trust/correctness fix for the next week.
5. Record the decision and the evidence that caused it.

- [x] **Step 5: Commit**

```bash
git add docs/business/founding-cohort-playbook.md docs/business/interview-notes-template.md
git commit -m "docs: define founding beta cohort"
```

### Task 6: Set a paid-beta gate from evidence, not aesthetics

**Files:**
- Create: `docs/business/paid-beta-gate.md`

**Interfaces:**
- Consumes: beta scorecard definitions, cohort evidence, trust destinations, and the three prerequisite implementation plans.
- Produces: binary paid-beta readiness conditions and a 10-user pricing experiment protocol.

- [x] **Step 1: Define non-negotiable launch gates**

```markdown
# Paid Beta Gate

TradeLens AI may test a paid beta only when all conditions are true:

- The intended premium site is live at the canonical public domain.
- The public CTA reaches the intended app sign-in without provider auth confusion.
- User-owned trades, strategies, settings, AI outputs, and reviews are isolated.
- Contradictory outcome records are blocked and the stored contradiction count is zero.
- Privacy, terms, support, export, and deletion paths are published and tested.
- At least 20 accounts have entered the beta.
- At least 8 users have reached the first useful weekly review.
- At least 5 activated users return and journal in week four.
- At least 5 users describe a concrete workflow benefit in their own words.
- At least 3 retained users state a credible willingness to pay after using the product.

Do not use a visual redesign, waitlist size, page views, or AI generation volume as proof of product value.
```

- [x] **Step 2: Define the first pricing experiment**

Once the gate is met:

- choose one simple monthly plan;
- include all core journaling and review features;
- state any AI usage limit in plain language;
- show cancellation and data handling before checkout;
- test the same offer with the next 10 qualified users;
- measure accepted paid conversions, not stated enthusiasm;
- revise the price only after the 10-user test is complete.

Do not publish invented annual savings, trading ROI, or fake urgency.

- [x] **Step 3: Commit**

```bash
git add docs/business/paid-beta-gate.md
git commit -m "docs: define evidence gate for paid beta"
```

### Task 7: Final verification and owner review

**Files:**
- Modify only if a verification failure requires a correction to files in this plan.

**Interfaces:**
- Consumes: every file and command produced by Tasks 1–6 plus `scripts/verify_public_funnel.py` from the public-funnel plan.
- Produces: passing focused tests, a passing public-funnel report, an aggregate beta-health report, and a dated owner gate review.

- [x] **Step 1: Run the focused suite**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_activation.py \
  tests/test_beta_health.py \
  tests/test_site_copy.py \
  tests/test_site_metadata.py \
  tests/test_site_trust_links.py \
  tests/test_trade_service.py \
  tests/test_weekly_review.py
```

Expected: PASS.

- [x] **Step 2: Run the public funnel verification**

Run:

```bash
.venv/bin/python scripts/verify_public_funnel.py \
  --site https://tradelens-ai.com \
  --app https://tradelens-app.streamlit.app
```

Expected: public site 200, canonical and metadata use the same origin, primary CTA uses the configured app origin, and the app reaches the intended TradeLens auth screen without provider-auth loops.

- [x] **Step 3: Produce the first operator report**

Run: `.venv/bin/python scripts/beta_health.py --format markdown`

Expected: aggregate counts and rates only; no usernames, journal text, screenshots, psychology text, strategy rules, or P&L.

- [x] **Step 4: Review against the paid-beta gate**

The owner marks every item in `docs/business/paid-beta-gate.md` as pass or fail with a dated evidence link. A failed gate remains a failed gate; do not replace it with a subjective judgment that the product “looks ready.”

- [x] **Step 5: Commit verification corrections if any**

```bash
git add src/tradelens/services/activation.py src/tradelens/ui/app.py src/tradelens/ui/pages/6_Insights.py scripts/beta_health.py site/index.html tests docs/business
git commit -m "chore: verify beta business readiness"
```
