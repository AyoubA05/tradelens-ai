# Paid Beta Gate

TradeLens AI may test a paid beta only when **all** of the following are
true. These are binary conditions, checked with evidence, not a judgement
call about whether the product feels ready.

## Non-negotiable conditions

- [ ] The intended premium site is live at the canonical public domain.
- [ ] The public CTA reaches the intended app sign-in without provider-auth
      confusion (`scripts/verify_public_funnel.py` exits 0).
- [ ] User-owned trades, strategies, settings, AI outputs, and reviews are
      isolated per account.
- [ ] Contradictory outcome records are blocked, and the stored
      contradiction count is zero.
- [ ] Privacy, terms, support, export, and deletion paths are published and
      tested.
- [ ] At least 20 accounts have entered the beta.
- [ ] At least 8 users have reached a first useful weekly review.
- [ ] At least 5 activated users return and journal in week four.
- [ ] At least 5 users describe a concrete workflow benefit in their own
      words.
- [ ] At least 3 retained users state a credible willingness to pay **after**
      using the product.

Do not use a visual redesign, waitlist size, page views, or AI generation
volume as proof of product value. None of them measure whether a trader
came back.

## Known blockers as of 2026-07-24

| Condition | Status |
|---|---|
| Canonical domain serves this site | **Failing** — `tradelens-ai.com` serves an older, differently-positioned build |
| Public CTA reaches TradeLens sign-in | **Failing** — the app 303-redirects anonymous visitors to `share.streamlit.io/-/auth` |
| Contradictions blocked | Passing — enforced at every write boundary |
| Deletion path published | **Failing** — no account-deletion function exists |

The first two are dashboard settings. The fourth is unbuilt functionality.

## First pricing experiment

Once the gate is met:

- Choose one simple monthly plan.
- Include all core journaling and review features.
- State any AI usage limit in plain language.
- Show cancellation and data handling **before** checkout.
- Test the same offer with the next 10 qualified users.
- Measure accepted paid conversions, not stated enthusiasm.
- Revise the price only after the 10-user test is complete.

Do not publish invented annual savings, trading ROI, or fake urgency. A
journal that reviews completed trades cannot honestly quote a return.
