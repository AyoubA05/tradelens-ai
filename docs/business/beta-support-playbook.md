# Beta Support Playbook

## Response target

Reply within one business day during the private beta. If a fix will take
longer, say so in that first reply rather than waiting until it's done.

## Intake fields

- What were you trying to do?
- What happened instead?
- Which page were you on?
- Approximate time and timezone
- Screenshot only if the user is comfortable sharing it

## Severity

- **P0 — privacy or cross-account exposure.** Stop recruitment and
  investigate immediately. One user seeing another's trades ends the beta
  until it is fixed and the cause is understood.
- **P1 — cannot sign in, save, or view owned records.** Respond same
  business day. Note that a forgotten password is currently unrecoverable
  (see the data-handling inventory), so treat it as data loss, not a
  support inconvenience.
- **P2 — incorrect metric or AI review.** Acknowledge, and do not use that
  result as proof of anything until it is understood. A wrong number that
  gets quoted back to a trader is worse than a missing one.
- **P3 — visual or copy issue.** Batch into the weekly product review.

## Never request

Broker passwords, API secrets, full account statements, or unrelated
personal documents. TradeLens has no legitimate use for any of them, and
asking teaches users that it is normal to hand them over.

## When a user reports a wrong number

1. Ask for the trade date and asset, not a screenshot of their whole
   journal.
2. Reproduce against seeded data first.
3. Check whether the row is a legacy record saved before write-time
   outcome validation.
4. If a stored row is contradictory, fix the validation gap that allowed
   it — do not hand-edit the user's data without telling them.
