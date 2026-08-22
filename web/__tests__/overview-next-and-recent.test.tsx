import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NextReviewAction } from "@/components/app/overview/next-review-action";
import { RecentTrades } from "@/components/app/overview/recent-trades";

describe("next review action", () => {
  it("tells the trader what to re-read, not what to trade", () => {
    render(
      <NextReviewAction
        action={{ completed: 2, total: 3, next_key: "first_review", is_activated: false, trades_until_review: 2 }}
      />,
    );
    expect(screen.getByText(/2 of 3/)).toBeInTheDocument();
    expect(screen.getByText(/2 more completed trades/i)).toBeInTheDocument();
  });

  it("says the path is complete once it is", () => {
    render(
      <NextReviewAction
        action={{ completed: 3, total: 3, next_key: null, is_activated: true, trades_until_review: 0 }}
      />,
    );
    expect(screen.getByText(/nothing waiting/i)).toBeInTheDocument();
  });
});

describe("recent trades", () => {
  const trades = [
    { id: 3, trade_date: "2026-08-15", asset: "NQ", session: "New York Open", setup_type: "Liquidity Sweep + FVG", result: "Win", pnl: 410, rr_realized: 2.7 },
    { id: 2, trade_date: "2026-08-13", asset: "ES", session: "New York Open", setup_type: "Liquidity Sweep + FVG", result: "Loss", pnl: -220, rr_realized: null },
  ];

  it("lists the most recent trades with their outcome in text", () => {
    render(<RecentTrades trades={trades} />);
    expect(screen.getByText("NQ")).toBeInTheDocument();
    expect(screen.getByText("Win")).toBeInTheDocument();
    expect(screen.getByText("Loss")).toBeInTheDocument();
  });

  it("shows a dash where an R multiple was never recorded", () => {
    render(<RecentTrades trades={trades} />);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("invites the first trade when there are none", () => {
    render(<RecentTrades trades={[]} />);
    expect(screen.getByRole("link", { name: /log completed trade/i })).toBeInTheDocument();
  });
});
