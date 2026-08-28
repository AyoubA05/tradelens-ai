/**
 * The New Trade field contract — every field the form collects, its type,
 * its options (where it has a closed set) and a one-line note on its client
 * validation rule.
 *
 * This is the single source Task C1 asks for. It is pinned by
 * `__tests__/new-trade-fields.test.ts` against the field set the Streamlit
 * New Trade form (`src/tradelens/ui/pages/1_NewTrade.py`) actually collects
 * — enumerated from that file's widget keys, not from the plan's prose. A
 * field present in Streamlit and missing here fails that test.
 *
 * Reconciliation with Group A's server-side allowlist (`TradeCreate` in
 * `src/tradelens/api/schemas/trades.py`): the two do NOT name the same
 * fields, and that is expected, not a drift to fix. `TradeCreate` is the
 * wire shape `POST /v1/trades` accepts; several fields below never appear
 * on the wire under their own name because the client folds them into a
 * `TradeCreate` field the same way Streamlit's `_build_trade_data` does:
 *
 *   - `confluences` (multiselect) -> the five `TradeCreate` boolean flags
 *     (`liquidity_sweep`, `fvg_used`, `order_block_used`, `bos`, `choch`).
 *   - `ltf_bias` -> `TradeCreate.bias` (the column is named `bias`; the form
 *     label is "LTF bias" to sit next to "HTF bias").
 *   - `r_multiple` -> `TradeCreate.rr_realized` when no exact price triple
 *     lets the server recompute it (mirrors `_build_trade_data`'s
 *     `"rr_realized": manual_r`).
 *   - `rule_broken`, `did_well`, `do_better` -> folded into `TradeCreate.notes`
 *     as labelled lines, exactly as `_build_trade_data`'s `note_lines` does.
 *     They are not separate `Trade` columns.
 *   - `mindset` -> a fallback for `TradeCreate.emotions_during` only when the
 *     "During" emotion selector was left at "-" (mirrors `final_during`).
 *   - `screenshot` -> never part of `TradeCreate` at all. Design decision #1:
 *     it is uploaded through the presign/finalize flow against the trade id
 *     the create call returns, after the trade exists.
 *
 * Every other field here maps onto a `TradeCreate` field of the same or an
 * obviously corresponding name (`setup` -> `setup_type`, `confirmation text`
 * -> `confirmation_model`, `process notes` -> `trade_process_notes`, etc).
 * `web/lib/app/new-trade.ts` performs this exact mapping in
 * `buildTradeCreatePayload`, so the fold is one reviewable function rather
 * than logic scattered across the form component.
 *
 * Group A derived `TradeCreate` from `1_NewTrade.py` independently, before
 * this task landed, and its own contract test pins `TradeCreate` against
 * `Trade`'s columns (a column omitted from the model fails that test, not a
 * field this form fails to send). Cross-checked field-by-field against
 * `TradeCreate` in `src/tradelens/api/schemas/trades.py`: every fold target
 * named above exists there, and nothing this form needs to send is missing
 * from it. The two contracts agree.
 */

export type NewTradeFieldType =
  | "select"
  | "select-with-custom"
  | "date"
  | "time-text"
  | "text"
  | "textarea"
  | "multiselect"
  | "price-text"
  | "number"
  | "radio"
  | "file-or-url";

export interface NewTradeFieldDef {
  /** The form's own vocabulary — matches `NewTradeFormValues` keys. */
  readonly name: string;
  readonly label: string;
  readonly type: NewTradeFieldType;
  /** Present only for select/multiselect/radio fields with a closed set. */
  readonly options?: readonly string[];
  /** One line: what the client-side check does. Never the only gate — see design-decisions.md #7 / global-constraints.md. */
  readonly clientValidation: string;
}

// Futures + forex only (Item 5 in the Streamlit form's own history — crypto
// stays recognisable to the classifier for legacy rows but is no longer
// offered on New Trade). Mirrors `src/tradelens/services/assets.py`'s
// `FUTURES`/`FOREX`/`OTHER`; that file has no HTTP endpoint of its own, so
// this list is a deliberate, reviewable copy rather than a live fetch.
export const OTHER_ASSET = "Other / Custom";
export const ASSET_OPTIONS = [
  "NQ",
  "MNQ",
  "ES",
  "MES",
  "YM",
  "MYM",
  "RTY",
  "M2K",
  "CL",
  "MCL",
  "GC",
  "MGC",
  "SI",
  "HG",
  "NG",
  "ZB",
  "ZN",
  "6E",
  "6B",
  "6J",
  "6A",
  "6C",
  "6S",
  "EURUSD",
  "GBPUSD",
  "USDJPY",
  "USDCHF",
  "USDCAD",
  "AUDUSD",
  "NZDUSD",
  "EURJPY",
  "GBPJPY",
  "EURGBP",
  "EURAUD",
  "EURCAD",
  "AUDJPY",
  "CADJPY",
  "XAUUSD",
  "XAGUSD",
  OTHER_ASSET,
] as const;

export const TIMEFRAME_OPTIONS = ["1m", "5m", "15m", "1H", "4H", "D"] as const;
export const BIAS_OPTIONS = ["Bullish", "Bearish", "Consolidation"] as const;
export const RESULT_OPTIONS = ["Win", "Loss", "Breakeven"] as const;
export const FOLLOWED_RULES_OPTIONS = ["Yes", "No", "Partial"] as const;
export const CONFLUENCE_OPTIONS = [
  "Liquidity Sweep",
  "BOS",
  "MSS/CHOCH",
  "FVG",
  "IFVG",
  "OB Retest",
  "S/R Rejection",
  "Candle Close",
  "VWAP",
  "No Confirmation",
] as const;
export const EMOTION_OPTIONS = [
  "Calm",
  "Confident",
  "Focused",
  "Anxious",
  "FOMO",
  "Revenge",
  "Neutral",
] as const;
// Setup and mistake option lists include Strategy Profile defaults in
// Streamlit; this form offers the fixed default set only (Strategy Profile
// autofill is out of this task's scope — see the report's open items).
export const SETUP_OPTIONS = [
  "Liquidity Sweep + FVG/IFVG",
  "BOS + FVG",
  "FVG + OB",
  "CHoCH Entry",
  "OB Retest",
  "Other",
] as const;
export const MISTAKE_OPTIONS = [
  "Early Entry",
  "Late Entry",
  "FOMO",
  "Revenge Trading",
  "Moved Stop",
  "Closed Early",
  "Against Bias",
  "News Trade",
  "Overtrading",
  "Bad Stop Placement",
] as const;

/**
 * Field contract, one entry per field Streamlit's New Trade form collects.
 * Order matches the brief's enumeration, which itself follows the wizard's
 * step order (Screenshot, Context, Execution, Reflection).
 */
export const NEW_TRADE_FIELDS: readonly NewTradeFieldDef[] = [
  { name: "screenshot", label: "Screenshot", type: "file-or-url", clientValidation: "none — optional; type/size checked by the browser file picker only" },
  { name: "asset", label: "Asset", type: "select-with-custom", clientValidation: "required, non-blank after trim" },
  { name: "trade_date", label: "Trade date", type: "date", clientValidation: "required; not after the browser's local today (courtesy mirror of the server's owner-timezone check)" },
  { name: "entry_time", label: "Entry time", type: "time-text", clientValidation: "required; must parse as HH:MM, H:MM AM/PM, HHMM, or H AM/PM" },
  { name: "timeframe", label: "Timeframe", type: "select", options: TIMEFRAME_OPTIONS, clientValidation: "none — closed set, always has a value" },
  { name: "htf_bias", label: "HTF bias", type: "select", options: BIAS_OPTIONS, clientValidation: "none — closed set, always has a value" },
  { name: "ltf_bias", label: "LTF bias", type: "select", options: BIAS_OPTIONS, clientValidation: "none — closed set, always has a value" },
  { name: "setup_type", label: "Setup model", type: "select", options: SETUP_OPTIONS, clientValidation: "none — closed set, always has a value" },
  { name: "confluences", label: "Evidence", type: "multiselect", options: CONFLUENCE_OPTIONS, clientValidation: "none — optional" },
  { name: "confirmation_model", label: "What confirmed the trade?", type: "textarea", clientValidation: "none — optional free text" },
  { name: "entry_price", label: "Entry price", type: "price-text", clientValidation: "must parse as a decimal number when non-blank; entry and stop cannot be equal" },
  { name: "stop_price", label: "Stop price", type: "price-text", clientValidation: "must parse as a decimal number when non-blank; entry and stop cannot be equal" },
  { name: "tp_price", label: "Take profit", type: "price-text", clientValidation: "must parse as a decimal number when non-blank" },
  { name: "exit_price", label: "Exit price", type: "price-text", clientValidation: "must parse as a decimal number when non-blank" },
  { name: "position_size", label: "Position size", type: "number", clientValidation: "whole number, >= 0, when entered" },
  { name: "risk_amount", label: "Risk ($)", type: "number", clientValidation: "must parse as a number when entered" },
  { name: "r_multiple", label: "R multiple", type: "number", clientValidation: "must parse as a number when entered" },
  { name: "result", label: "Result", type: "select", options: RESULT_OPTIONS, clientValidation: "mirrors the server's canonical_outcome: a result that contradicts a non-zero P&L's sign is flagged inline before submit" },
  { name: "pnl", label: "P&L ($)", type: "number", clientValidation: "must parse as a number when entered; drives the outcome mismatch check above" },
  { name: "followed_rules", label: "Followed your rules?", type: "radio", options: FOLLOWED_RULES_OPTIONS, clientValidation: "none — optional, blank means not answered" },
  { name: "rule_broken", label: "Which rule, or what went wrong?", type: "text", clientValidation: "none — optional free text" },
  { name: "mistake_tags", label: "Tag any mistakes", type: "multiselect", options: MISTAKE_OPTIONS, clientValidation: "none — optional, empty means a clean trade" },
  { name: "emotions_before", label: "Before", type: "select", options: EMOTION_OPTIONS, clientValidation: "none — optional" },
  { name: "emotions_during", label: "During", type: "select", options: EMOTION_OPTIONS, clientValidation: "none — optional" },
  { name: "emotions_after", label: "After", type: "select", options: EMOTION_OPTIONS, clientValidation: "none — optional" },
  { name: "mindset", label: "How were you feeling?", type: "textarea", clientValidation: "none — optional free text" },
  { name: "did_well", label: "What did you do well?", type: "textarea", clientValidation: "none — optional free text" },
  { name: "do_better", label: "What should you do better next time?", type: "textarea", clientValidation: "none — optional free text" },
  { name: "process_notes", label: "What happened during this trade?", type: "textarea", clientValidation: "none — optional free text" },
];

export const NEW_TRADE_FIELD_NAMES: readonly string[] = NEW_TRADE_FIELDS.map((f) => f.name);
