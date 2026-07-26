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

## Gate status as of 2026-07-26 (production)

| Condition | Status |
|---|---|
| Intended premium site at the canonical public domain | **Passing** — `www.tradelensai.io` serves the current build; the apex 308-redirects to it |
| Public CTA reaches TradeLens sign-in | Passing — the app requires sign-in by design, and the redirect routes back to it |
| Contradictions blocked | Passing — enforced at every write boundary |
| Deletion path published | Passing — hard deletion in Settings, incl. screenshot files, with a published policy describing it |
| Recovery path published | Passing for accounts with a recovery email; impossible without one, and stated as such |
| User data isolated per account | Passing — verified by the isolation suite and by the deletion test's cross-account check |

Requiring an account before the app opens is a product decision, not a
funnel defect. What the verifier still guards is that the sign-in wall
returns the visitor to TradeLens rather than stranding them.

Every infrastructure condition now passes. What remains is not code:

1. **Qualified legal review** of `/privacy` and `/terms`, including whether
   a governing-law clause is needed. None is asserted at present rather
   than inventing a jurisdiction.
2. **SMTP configured**, or 12 password resets handled by hand. Unconfigured,
   a reset request says it could not send rather than pretending — it never
   claims to have sent mail it did not send.
3. **The evidence conditions above** — 20 accounts, 8 first reviews, 5
   week-four returns, 5 stated benefits, 3 credible willingness-to-pay.
   These need a cohort, not a commit.

The last one is the real gate. The first two are a morning's work; the
third is a month of talking to traders, and no amount of polish
substitutes for it.

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
