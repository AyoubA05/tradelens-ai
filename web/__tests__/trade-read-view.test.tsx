import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TradeReadView } from "@/components/app/trade-detail/trade-read-view";
import type { TradeDetail } from "@/lib/app/trades";

const BASE: TradeDetail = {
  id: 42,
  ai_grade: "B+",
  asset: "NQ",
  asset_class: "Futures",
  bias: "Bullish",
  bos: 1,
  choch: 0,
  confirmation_model: "3-candle",
  created_at: "2026-08-01T13:00:00Z",
  day_of_week: "Tuesday",
  direction: "Long",
  emotions_after: "Calm",
  emotions_before: "Focused",
  emotions_during: "Steady",
  entry_price: 19500.25,
  entry_type: "Limit",
  exit_price: 19540.5,
  followed_rules: 1,
  fvg_used: 1,
  htf_bias: "Bullish",
  killzone: "London",
  liquidity_sweep: 0,
  mistake_tags: "none",
  notes: "Clean entry off the sweep.",
  order_block_used: 1,
  pnl: 575,
  position_size: 2,
  result: "Win",
  reward_amount: 800,
  risk_amount: 225,
  rr_planned: 3,
  rr_realized: 2.55,
  screenshots: [],
  session: "London",
  setup_type: "FVG retest",
  stop_price: 19475,
  strategy_used: "SMC continuation",
  timeframe: "5m",
  tp_price: 19560,
  trade_date: "2026-08-01",
  trade_process_notes: "Waited for confirmation candle.",
  updated_at: "2026-08-01T14:00:00Z",
  user_grade: "A-",
};

describe("TradeReadView", () => {
  it("shows the asset and date as the header", () => {
    render(<TradeReadView trade={BASE} />);
    expect(screen.getByRole("heading", { name: "NQ" })).toBeInTheDocument();
    expect(screen.getByText("2026-08-01")).toBeInTheDocument();
  });

  it("carries the outcome as a word, not only as colour", () => {
    render(<TradeReadView trade={BASE} />);
    expect(screen.getByText("Win")).toBeInTheDocument();
  });

  it("shows a recorded P&L formatted as money, with a sign in the text", () => {
    render(<TradeReadView trade={{ ...BASE, pnl: -220 }} />);
    expect(screen.getByText("-$220.00")).toBeInTheDocument();
  });

  it("reads an unrecorded P&L as 'not recorded', never $0.00", () => {
    render(<TradeReadView trade={{ ...BASE, pnl: null }} />);
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
  });

  it("distinguishes a recorded zero from an unrecorded field for a 0/1 flag", () => {
    // followed_rules: 0 is a recorded "No"; null is "not recorded". Both must
    // be readable, and they must not collapse into the same text.
    const { rerender } = render(<TradeReadView trade={{ ...BASE, followed_rules: 0 }} />);
    expect(screen.getByText("Rules Followed").nextElementSibling).toHaveTextContent("No");

    rerender(<TradeReadView trade={{ ...BASE, followed_rules: null }} />);
    expect(screen.getByText("Rules Followed").nextElementSibling).toHaveTextContent("—");
  });

  it("renders every null field as the not-recorded token, never blank", () => {
    const empty: TradeDetail = {
      id: 1,
      ai_grade: null,
      asset: null,
      asset_class: null,
      bias: null,
      bos: null,
      choch: null,
      confirmation_model: null,
      created_at: null,
      day_of_week: null,
      direction: null,
      emotions_after: null,
      emotions_before: null,
      emotions_during: null,
      entry_price: null,
      entry_type: null,
      exit_price: null,
      followed_rules: null,
      fvg_used: null,
      htf_bias: null,
      killzone: null,
      liquidity_sweep: null,
      mistake_tags: null,
      notes: null,
      order_block_used: null,
      pnl: null,
      position_size: null,
      result: null,
      reward_amount: null,
      risk_amount: null,
      rr_planned: null,
      rr_realized: null,
      screenshots: [],
      session: null,
      setup_type: null,
      stop_price: null,
      strategy_used: null,
      timeframe: null,
      tp_price: null,
      trade_date: null,
      trade_process_notes: null,
      updated_at: null,
      user_grade: null,
    };
    render(<TradeReadView trade={empty} />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(10);
  });
});
