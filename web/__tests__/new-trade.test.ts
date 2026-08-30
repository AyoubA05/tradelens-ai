import "@testing-library/jest-dom/vitest";
import { describe, expect, it } from "vitest";

import {
  buildTradeCreatePayload,
  emptyNewTradeFormValues,
  parseEntryTime,
  parsePrice,
  resolvedAsset,
  validateNewTrade,
  type NewTradeFormValues,
} from "@/lib/app/new-trade";

const OTHER = "Other / Custom";


describe("parsePrice", () => {
  it("keeps exact decimals a number_input would round", () => {
    // The Streamlit form moved prices to text inputs for exactly this
    // reason (Item 7): NG 3.3765 must not become 3.38.
    expect(parsePrice("3.3765")).toBe(3.3765);
  });
  it("tolerates commas and whitespace", () => {
    expect(parsePrice(" 19,850.25 ")).toBe(19850.25);
  });
  it("is null, never zero, for blank or junk input", () => {
    expect(parsePrice("")).toBeNull();
    expect(parsePrice("   ")).toBeNull();
    expect(parsePrice("abc")).toBeNull();
  });
});

describe("parseEntryTime", () => {
  it.each(["09:30", "9:30 AM", "0930", "9 AM", "14:05"])("accepts %s", (v) => {
    expect(parseEntryTime(v)).toBe(true);
  });
  it.each(["", "not a time", "25:00", "9:30 XM"])("rejects %s", (v) => {
    expect(parseEntryTime(v)).toBe(false);
  });
});

function values(overrides: Partial<NewTradeFormValues> = {}): NewTradeFormValues {
  return {
    ...emptyNewTradeFormValues(),
    asset: "NQ",
    tradeDate: "2026-08-20",
    entryTime: "09:30",
    ...overrides,
  };
}

describe("resolvedAsset", () => {
  it("uses the picked asset normally", () => {
    expect(resolvedAsset(values({ asset: "NQ" }), OTHER)).toBe("NQ");
  });
  it("uses the custom text when Other is picked", () => {
    expect(resolvedAsset(values({ asset: OTHER, assetCustom: " MNQ " }), OTHER)).toBe("MNQ");
  });
});

describe("validateNewTrade — courtesy mirror of the server's hard rules", () => {
  it("requires an asset", () => {
    const { errors } = validateNewTrade(values({ asset: "" }), OTHER);
    expect(errors).toContain("Asset is required.");
  });

  it("requires a readable entry time", () => {
    const { errors } = validateNewTrade(values({ entryTime: "whenever" }), OTHER);
    expect(errors.some((e) => e.includes("readable time") || e.includes("09:30"))).toBe(true);
  });

  it("rejects entry price equal to stop price", () => {
    const { errors } = validateNewTrade(
      values({ entryPrice: "100", stopPrice: "100" }),
      OTHER,
    );
    expect(errors).toContain("Entry and stop price can't be equal.");
  });

  it("rejects unparseable price text", () => {
    const { errors } = validateNewTrade(values({ entryPrice: "not a number" }), OTHER);
    expect(errors.some((e) => e.startsWith("Entry price"))).toBe(true);
  });

  it("flags a result that contradicts a non-zero P&L — mirrors canonical_outcome", () => {
    const { errors } = validateNewTrade(values({ pnl: "250", result: "Loss" }), OTHER);
    expect(errors.some((e) => e.includes("Loss") && e.includes("Win"))).toBe(true);
  });

  it("allows a result that matches P&L's sign", () => {
    const { errors } = validateNewTrade(values({ pnl: "250", result: "Win" }), OTHER);
    expect(errors.some((e) => e.includes("doesn't match"))).toBe(false);
  });

  it("never blocks on a thin record — warnings are separate from errors", () => {
    const { errors, warnings } = validateNewTrade(values(), OTHER);
    expect(errors).toEqual([]);
    expect(warnings.length).toBeGreaterThan(0);
  });
});

describe("buildTradeCreatePayload — folds form fields into TradeCreate", () => {
  it("folds confluences into the five TradeCreate boolean flags", () => {
    const payload = buildTradeCreatePayload(
      values({ confluences: ["BOS", "FVG"] }),
      OTHER,
    );
    expect(payload.bos).toBe(1);
    expect(payload.fvg_used).toBe(1);
    expect(payload.liquidity_sweep).toBe(0);
    expect(payload.order_block_used).toBe(0);
    expect(payload.choch).toBe(0);
  });

  it("folds rule_broken/did_well/do_better into notes as labelled lines", () => {
    const payload = buildTradeCreatePayload(
      values({ ruleBroken: "moved my stop", didWell: "waited", doBetter: "be patient" }),
      OTHER,
    );
    expect(payload.notes).toBe(
      "Rule broken: moved my stop\nDid well: waited\nDo better next time: be patient",
    );
  });

  it("sends ltf_bias as TradeCreate.bias, lowercased", () => {
    const payload = buildTradeCreatePayload(values({ ltfBias: "Bearish" }), OTHER);
    expect(payload.bias).toBe("bearish");
  });

  it("falls back mindset into emotions_during only when During was left unset", () => {
    const withDuring = buildTradeCreatePayload(
      values({ emotionsDuring: "Calm", mindset: "felt anxious" }),
      OTHER,
    );
    expect(withDuring.emotions_during).toBe("Calm");

    const withoutDuring = buildTradeCreatePayload(
      values({ emotionsDuring: "", mindset: "felt anxious" }),
      OTHER,
    );
    expect(withoutDuring.emotions_during).toBe("felt anxious");
  });

  it("keeps exact price precision through the fold", () => {
    const payload = buildTradeCreatePayload(values({ stopPrice: "3.3765" }), OTHER);
    expect(payload.stop_price).toBe(3.3765);
  });

  it("infers direction from prices only, never asks for it directly", () => {
    const long = buildTradeCreatePayload(
      values({ entryPrice: "100", stopPrice: "95" }),
      OTHER,
    );
    expect(long.direction).toBe("Long");
    const none = buildTradeCreatePayload(values(), OTHER);
    expect(none.direction).toBeNull();
  });

  it("never includes screenshot, session, killzone or asset_class as a fabricated value", () => {
    const payload = buildTradeCreatePayload(values(), OTHER) as Record<string, unknown>;
    expect(payload).not.toHaveProperty("screenshot");
    expect(payload).not.toHaveProperty("session");
    expect(payload).not.toHaveProperty("killzone");
    expect(payload).not.toHaveProperty("asset_class");
  });
});
