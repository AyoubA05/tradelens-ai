# Data Handling Inventory

**Status: factual product documentation. Not a privacy policy.**

This describes what TradeLens AI actually stores, sends, and retains, read
from the code and deployment configuration on 2026-07-24. It exists so the
owner and qualified counsel can write `/privacy` and `/terms` from facts
rather than from assumptions. Nothing here is a promise to a user, and
nothing here should be copied onto the site as policy language.

Where a capability does not exist, this document says so plainly. Those
gaps are the useful part.

---

## 1. Account data

Table `users`:

| Field | Notes |
|---|---|
| `username` | Chosen by the user. No uniqueness beyond the account system. |
| `password_hash` | bcrypt with a per-password salt (`services/users.py`). The plaintext password is never stored. |
| `created_at`, `is_active` | Timestamps and soft-disable flag. |

No email address, real name, phone number, address, payment detail, or
broker credential is collected anywhere in the schema.

**Consequence for policy:** there is currently no way to contact a user
about their own account, because no contact field exists. Password reset
and account recovery therefore cannot work today (see §7).

## 2. Trade and psychology data

Table `trades` — the substantive record. Includes:

- **Market facts:** date, day of week, session, asset, asset class,
  timeframe, direction, killzone.
- **Prices and money:** entry, stop, take-profit, exit, position size, risk
  amount, reward amount, planned and realised R, P&L, result.
- **Method:** setup type, strategy used, bias, HTF bias, entry type,
  confirmation model, and the SMC flags (liquidity sweep, FVG, order block,
  BOS, CHoCH).
- **Psychology and free text:** `emotions_before`, `emotions_during`,
  `emotions_after`, `notes`, `trade_process_notes`, `mistake_tags`,
  `followed_rules`.
- **Grades:** `ai_grade`, `user_grade`.

`emotions_*`, `notes`, and `trade_process_notes` are free text and may
contain anything the trader types, including personal circumstances. Treat
them as the most sensitive content in the product.

Table `strategies` holds the user's own trading rules (entry, stop, take
profit, risk, setups traded and avoided, common mistakes). This is
proprietary method information and should be treated as confidential to
the account.

## 3. Screenshots

- Uploaded chart images are written to `data/screenshots/` on the
  application filesystem (`services/screenshot_service.py`).
- Table `screenshots` stores the file path and pixel dimensions, linked to
  a trade.
- **On Streamlit Community Cloud the filesystem is ephemeral.** Uploaded
  screenshots do not survive a redeploy or container restart. This is a
  data-loss characteristic users are not currently told about.

## 4. What is sent to the AI provider

The only external processor is **Anthropic** (`services/ai_client.py`;
every AI call routes through that module).

| Feature | What leaves the app |
|---|---|
| Chart analysis / autofill | The uploaded chart image, plus the active Strategy Profile when one exists |
| Trade review / journal generation | The trade's structured fields and free-text notes, plus the Strategy Profile |
| Weekly recap | The week's trades, computed statistics, deterministic pattern statistics, and the Strategy Profile |
| Grading pre-pass | A reduced set of trade fields |

Usernames and password hashes are never included in a prompt. Free-text
psychology notes **are** included when they are part of the trade being
reviewed.

`DEMO_MODE=true` returns cached or synthetic output and makes no API call.

## 5. Logging and cost records

- Table `ai_usage_log`: feature, model, token counts, estimated cost,
  `user_id`, timestamp. No prompt content.
- Table `aianalysis`: model outputs, including `raw_response_json` and
  token/cost fields, linked to a trade.
- Table `weekly_reviews`: generated markdown, `thinking_summary`, statistics
  JSON, cost.

`thinking_summary` and cost fields are stored but, since 2026-07-24, are no
longer displayed in the normal user path.

## 6. Public site behaviour

- `site/` is static and sets no cookies of its own.
- Vercel Web Analytics is loaded (`/_vercel/insights/script.js`).
- Two custom events are sent: `marketing_cta_click` with a location string
  (`nav`, `hero`, `pricing`, `final`, `mobile`) and `faq_open` with the
  question text. Both are fixed strings from the page.
- Fonts are loaded from Google Fonts and Fontshare, so those hosts receive
  visitor IP addresses as a consequence of the request.

## 7. Export, correction, deletion, retention — current reality

| Capability | Status |
|---|---|
| Export own trades | Yes, CSV (`services/csvio.py`) |
| Correct a trade | Yes, edit in the Journal |
| Delete a single trade | Yes (`delete_trade`) |
| Delete an entire account and all its data | **No such function exists** |
| Password reset / account recovery | **Not possible — no contact field is collected** |
| Documented retention period | **None. Data is kept until manually deleted** |
| Backups | **None configured for the application database** |
| Screenshot durability | **Ephemeral on Streamlit Community Cloud** |

## 8. Known beta limitations to disclose

1. No account deletion path.
2. No password recovery; a forgotten password means a lost account.
3. Screenshots and, on an ephemeral host, the database itself can be lost
   on redeploy.
4. No backup or restore procedure.
5. Free-text psychology notes are sent to Anthropic as part of review
   generation.
6. No stated retention period.

## 9. Before publishing any policy

Items 1, 2, and 4 above are functionality gaps, not wording gaps. A privacy
policy that promises deletion or recovery would be inaccurate until they
are built. The honest options are to build them first, or to state the
limitation plainly as a beta condition.

Counsel should also confirm the correct legal posture for a product that
transmits user-authored psychological reflections to a third-party model
provider.
