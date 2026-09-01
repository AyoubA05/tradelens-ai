import { describe, expect, it } from "vitest";

import { NEW_TRADE_FIELDS, NEW_TRADE_FIELD_NAMES } from "@/lib/app/new-trade-fields";

/**
 * Field parity, pinned (Task C1).
 *
 * The list below is enumerated directly from the Streamlit New Trade form's
 * own widget keys in `src/tradelens/ui/pages/1_NewTrade.py` — asset,
 * trade date, entry time, timeframe, HTF bias, LTF bias, setup, confluences,
 * confirmation text, entry/stop/take-profit/exit prices, position size,
 * risk, R multiple, result, P&L, followed-rules, rule broken, mistake tags,
 * emotions before/during/after, mindset, what went well, what to do better,
 * process notes, screenshot — exactly the enumeration in the Group C brief.
 *
 * A field present in Streamlit and missing from `NEW_TRADE_FIELDS` fails
 * this test, rather than being noticed later by a trader who lost a note.
 */
const STREAMLIT_FIELD_NAMES = [
  "screenshot",
  "asset",
  "trade_date",
  "entry_time",
  "timeframe",
  "htf_bias",
  "ltf_bias",
  "setup_type",
  "confluences",
  "confirmation_model",
  "entry_price",
  "stop_price",
  "tp_price",
  "exit_price",
  "position_size",
  "risk_amount",
  "r_multiple",
  "result",
  "pnl",
  "followed_rules",
  "rule_broken",
  "mistake_tags",
  "emotions_before",
  "emotions_during",
  "emotions_after",
  "mindset",
  "did_well",
  "do_better",
  "process_notes",
];

describe("New Trade field parity", () => {
  it("names every field the Streamlit form collects, and nothing else", () => {
    expect([...NEW_TRADE_FIELD_NAMES].sort()).toEqual([...STREAMLIT_FIELD_NAMES].sort());
  });

  it("has no duplicate field names", () => {
    expect(new Set(NEW_TRADE_FIELD_NAMES).size).toBe(NEW_TRADE_FIELD_NAMES.length);
  });
});

describe("field contract honesty", () => {
  // Task D4: image-URL ingest now ships in the New Trade form (Task D1), so
  // the contract flips to say so — the same test that pinned the deferral
  // now pins that it no longer overstates what ships.
  it("declares the screenshot field as file-or-URL, now that ingest ships", () => {
    const screenshot = NEW_TRADE_FIELDS.find((f) => f.name === "screenshot");
    expect(screenshot?.type).toBe("file-or-url");
  });

  it("has exactly one field claiming URL ingest: screenshot", () => {
    const claiming = NEW_TRADE_FIELDS.filter((f) => String(f.type).includes("url"));
    expect(claiming.map((f) => f.name)).toEqual(["screenshot"]);
  });
});
