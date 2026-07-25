# Founding Cohort Playbook

Twelve traders, run deliberately, will tell you more than two hundred
signups. The point is evidence you can act on, not a number to report.

## Who to recruit

Twelve self-directed day traders who **already review completed trades** in
some form — a spreadsheet, a Notion page, screenshots in a folder. They
have the habit; TradeLens is competing with their current method, not
creating the need.

Require a mix of futures and FX traders.

Do not recruit people looking for calls, predictions, signals, or managed
trading. They will churn, and their feedback will pull the product toward
something it has explicitly decided not to be.

## Cadence

| When | What |
|---|---|
| Week 0 | 20-minute setup interview and observed onboarding |
| Week 1 | First completed-trade journal observation |
| Week 2 | Review of their first five completed trades |
| Week 4 | Retention and willingness-to-pay interview |

## Decision rules

- Change onboarding when at least **3 of 12** users independently fail at
  the same step. One person struggling is a person; three is a design flaw.
- Change a core workflow when at least 3 users show the same high-severity
  problem **and** the change preserves the post-trade boundary.
- Do not add a feature from one enthusiastic request. Look for repeated
  behaviour, not repeated enthusiasm.
- Do not use a quote publicly without written permission and a verifiable
  source.
- Do not claim performance improvement from self-reported satisfaction.
  "I feel more disciplined" is not evidence of discipline.
- Pause recruitment immediately for privacy exposure, record loss, or
  cross-account access.

## Weekly owner ritual (Fridays)

1. Run `scripts/beta_health.py --format markdown`.
2. Review P0/P1 support issues.
3. Cluster interview evidence by user problem, not by feature request.
4. Choose **at most one** onboarding improvement and **one** trust or
   correctness fix for the next week.
5. Record the decision and the evidence that caused it.

Step 5 is the one that compounds. A decision log makes it possible to
notice later that a change was made on thin evidence.

## What would falsify the product thesis

Worth writing down in advance, so it can't be rationalised away later:

- Users journal trades but never open a weekly review.
- Users read one review and never return.
- Users say the reviews are accurate but change nothing about their
  process.

Any of these means the reflection loop is not closing, and more features
will not fix it.
