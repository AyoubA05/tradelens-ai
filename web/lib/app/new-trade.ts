import "server-only";

import { callApi } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { FOLLOWED_RULES_OPTIONS, RESULT_OPTIONS } from "@/lib/app/new-trade-fields";

/**
 * New Trade: the form's own values, the fold into `TradeCreate`, client-side
 * validation (courtesy only — see design-decisions.md #7 and
 * global-constraints.md), and the server call.
 *
 * `TradeCreate` is Group A's positive allowlist for `POST /v1/trades`
 * (`src/tradelens/api/schemas/trades.py`); it is read from the generated
 * schema, never re-typed by hand, so this file cannot silently drift from
 * what the backend actually accepts.
 */
export type TradeCreate = components["schemas"]["TradeCreate"];
export type TradeCreateResponse = components["schemas"]["TradeCreateResponse"];

/** Every value the form manages, in the form's own vocabulary (see new-trade-fields.ts). */
export interface NewTradeFormValues {
  asset: string;
  assetCustom: string;
  tradeDate: string; // yyyy-mm-dd
  entryTime: string; // free text, parsed client-side for feedback only
  timeframe: string;
  htfBias: string;
  ltfBias: string;
  setupType: string;
  confluences: string[];
  confirmationModel: string;
  entryPrice: string;
  stopPrice: string;
  tpPrice: string;
  exitPrice: string;
  positionSize: string;
  riskAmount: string;
  rMultiple: string;
  result: string;
  pnl: string;
  followedRules: "" | "Yes" | "No" | "Partial";
  ruleBroken: string;
  mistakeTags: string[];
  emotionsBefore: string;
  emotionsDuring: string;
  emotionsAfter: string;
  mindset: string;
  didWell: string;
  doBetter: string;
  processNotes: string;
}

export function emptyNewTradeFormValues(): NewTradeFormValues {
  return {
    asset: "",
    assetCustom: "",
    tradeDate: "",
    entryTime: "",
    timeframe: "5m",
    htfBias: "Bullish",
    ltfBias: "Bullish",
    setupType: "Liquidity Sweep + FVG/IFVG",
    confluences: [],
    confirmationModel: "",
    entryPrice: "",
    stopPrice: "",
    tpPrice: "",
    exitPrice: "",
    positionSize: "",
    riskAmount: "",
    rMultiple: "",
    result: "Win",
    pnl: "",
    followedRules: "",
    ruleBroken: "",
    mistakeTags: [],
    emotionsBefore: "",
    emotionsDuring: "",
    emotionsAfter: "",
    mindset: "",
    didWell: "",
    doBetter: "",
    processNotes: "",
  };
}

/**
 * Exact-precision price parse (Item 7 in the Streamlit form's own history):
 * `<input type="number">` in some browsers rounds or coerces long decimals,
 * so prices are parsed from plain text here the same way
 * `src/tradelens/utils/format.py:parse_price` does — tolerate commas and
 * whitespace, empty or junk becomes `null`, never `0`.
 */
export function parsePrice(text: string): number | null {
  const s = text.trim().replace(/,/g, "");
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function parseNumber(text: string): number | null {
  const s = text.trim();
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

/**
 * A loose entry-time parse for inline feedback only ("not a readable time").
 * Mirrors `src/tradelens/services/sessions.py:parse_time_input`'s accepted
 * shapes (`09:30`, `9:30 AM`, `0930`, `9 AM`) closely enough to give a
 * trader the same "try 09:30 or 9:30 AM" nudge Streamlit gives — it is not
 * asked to reproduce the server's timezone-aware session/killzone detection,
 * which is out of this task's scope (see the report's open items).
 */
export function parseEntryTime(raw: string): boolean {
  const text = raw.trim().toUpperCase().replace(/\./g, "");
  if (!text) return false;
  return (
    /^([01]\d|2[0-3]):[0-5]\d$/.test(text) ||
    /^(0?\d|1[0-2]):[0-5]\d\s?(AM|PM)$/.test(text) ||
    /^([01]\d|2[0-3])[0-5]\d$/.test(text) ||
    /^(0?\d|1[0-2])\s?(AM|PM)$/.test(text)
  );
}

/** The asset actually being submitted: the custom text when "Other" is picked. */
export function resolvedAsset(values: NewTradeFormValues, otherLabel: string): string {
  return values.asset === otherLabel ? values.assetCustom.trim() : values.asset.trim();
}

export interface NewTradeValidationResult {
  errors: string[];
  warnings: string[];
}

/**
 * Client-side validation. Courtesy only (design-decisions.md #7,
 * global-constraints.md): it mirrors the server's hard rules — asset
 * required, entry time readable, entry != stop, every price field parses,
 * and `result` cannot contradict a non-zero `pnl` (mirrors
 * `canonical_outcome` / `OutcomeMismatch`) — but the server re-checks all of
 * it and is the only thing a bad write is actually gated on. Warnings never
 * block a save (design decision "Completeness warnings are non-blocking").
 */
export function validateNewTrade(
  values: NewTradeFormValues,
  otherLabel: string,
): NewTradeValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  const asset = resolvedAsset(values, otherLabel);
  if (!asset) errors.push("Asset is required.");

  if (!values.entryTime.trim() || !parseEntryTime(values.entryTime)) {
    errors.push("Enter a trade time, such as 09:30 or 9:30 AM.");
  }

  const entry = parsePrice(values.entryPrice);
  const stop = parsePrice(values.stopPrice);
  const tp = parsePrice(values.tpPrice);
  const exit_ = parsePrice(values.exitPrice);
  for (const [label, raw, parsed] of [
    ["Entry price", values.entryPrice, entry],
    ["Stop price", values.stopPrice, stop],
    ["Take profit", values.tpPrice, tp],
    ["Exit price", values.exitPrice, exit_],
  ] as const) {
    if (raw.trim() && parsed === null) errors.push(`${label} isn't a number.`);
  }
  if (entry !== null && stop !== null && entry === stop) {
    errors.push("Entry and stop price can't be equal.");
  }

  for (const [label, raw] of [
    ["Position size", values.positionSize],
    ["Risk", values.riskAmount],
    ["R multiple", values.rMultiple],
    ["P&L", values.pnl],
  ] as const) {
    if (raw.trim() && parseNumber(raw) === null) errors.push(`${label} isn't a number.`);
  }

  // Mirrors canonical_outcome/OutcomeMismatch: P&L's sign decides the label
  // when a result is also chosen, and the two must agree.
  const pnl = parseNumber(values.pnl);
  if (pnl !== null && pnl !== 0 && values.result) {
    const expected = pnl > 0 ? "Win" : "Loss";
    if (
      values.result !== expected &&
      (RESULT_OPTIONS as readonly string[]).includes(values.result)
    ) {
      errors.push(
        `Result "${values.result}" doesn't match a P&L of ${pnl}; expected "${expected}".`,
      );
    }
  }

  if (!values.mindset.trim()) warnings.push("Add how you felt (recommended).");
  if (!(FOLLOWED_RULES_OPTIONS as readonly string[]).includes(values.followedRules)) {
    warnings.push("Answer 'Followed your rules?' (recommended).");
  }

  return { errors, warnings };
}

function confluenceFlag(values: NewTradeFormValues, name: string): 0 | 1 {
  return values.confluences.includes(name) ? 1 : 0;
}

/**
 * Infer direction from the exact prices only, exactly like
 * `_infer_direction` in the Streamlit form — direction is never asked
 * directly.
 */
function inferDirection(entry: number | null, stop: number | null): string | null {
  if (entry === null || stop === null) return null;
  if (stop < entry) return "Long";
  if (stop > entry) return "Short";
  return null;
}

/**
 * Fold the form's values into the `TradeCreate` wire shape, the same way
 * `_build_trade_data` in `1_NewTrade.py` does — see the mapping table at the
 * top of `new-trade-fields.ts` for which form field lands where.
 */
export function buildTradeCreatePayload(
  values: NewTradeFormValues,
  otherLabel: string,
): TradeCreate {
  const entry = parsePrice(values.entryPrice);
  const stop = parsePrice(values.stopPrice);
  const tp = parsePrice(values.tpPrice);
  const exit_ = parsePrice(values.exitPrice);
  const position = parseNumber(values.positionSize);
  const risk = parseNumber(values.riskAmount);
  const manualR = parseNumber(values.rMultiple);
  const pnl = parseNumber(values.pnl);

  const noteLines: string[] = [];
  if (values.ruleBroken.trim()) noteLines.push(`Rule broken: ${values.ruleBroken.trim()}`);
  if (values.didWell.trim()) noteLines.push(`Did well: ${values.didWell.trim()}`);
  if (values.doBetter.trim()) noteLines.push(`Do better next time: ${values.doBetter.trim()}`);

  const finalDuring =
    values.emotionsDuring && values.emotionsDuring !== "—"
      ? values.emotionsDuring
      : values.mindset.trim() || null;

  const followedRulesFlag =
    values.followedRules === "Yes" ? 1 : values.followedRules === "No" ? 0 : null;

  return {
    trade_date: values.tradeDate,
    entry_time: values.entryTime.trim() || null,
    asset: resolvedAsset(values, otherLabel),
    asset_class: null,
    session: null,
    killzone: null,
    timeframe: values.timeframe,
    direction: inferDirection(entry, stop),
    htf_bias: values.htfBias.toLowerCase(),
    bias: values.ltfBias.toLowerCase(),
    setup_type: values.setupType,
    confirmation_model: values.confirmationModel.trim() || null,
    liquidity_sweep: confluenceFlag(values, "Liquidity Sweep"),
    fvg_used: confluenceFlag(values, "FVG"),
    order_block_used: confluenceFlag(values, "OB Retest"),
    bos: confluenceFlag(values, "BOS"),
    choch: confluenceFlag(values, "MSS/CHOCH"),
    followed_rules: followedRulesFlag,
    mistake_tags: JSON.stringify(values.mistakeTags),
    entry_price: entry,
    stop_price: stop,
    tp_price: tp,
    exit_price: exit_,
    position_size: position,
    risk_amount: risk,
    rr_realized: manualR,
    result: (values.result as TradeCreate["result"]) ?? null,
    pnl,
    emotions_before: values.emotionsBefore && values.emotionsBefore !== "—" ? values.emotionsBefore : null,
    emotions_during: finalDuring,
    emotions_after: values.emotionsAfter && values.emotionsAfter !== "—" ? values.emotionsAfter : null,
    notes: noteLines.join("\n") || null,
    trade_process_notes: values.processNotes.trim() || null,
  };
}

/**
 * Create a trade for the authenticated owner.
 *
 * Same boundary as `createTrade`'s siblings in `trades.ts`: the session
 * token is forwarded, ownership is resolved API-side. A submit whose
 * fingerprint matches an existing trade returns 200 with `duplicate_of` set
 * rather than a second row (design decision #5) — that is not an error, and
 * this function does not treat it as one; the caller reads `duplicate_of`.
 * A P&L/result contradiction the client-side check missed still comes back
 * as `ApiError(422)`, which this function does not catch — the server's
 * `canonical_outcome` is the actual gate (design decision, global rule 4).
 */
export async function createTrade(
  sessionToken: string,
  payload: TradeCreate,
): Promise<TradeCreateResponse> {
  return callApi<TradeCreateResponse>("/v1/trades", sessionToken, {
    method: "POST",
    body: payload,
  });
}
