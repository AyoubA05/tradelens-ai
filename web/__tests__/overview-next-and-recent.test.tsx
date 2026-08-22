import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NextReviewAction, STEP_COPY } from "@/components/app/overview/next-review-action";
import { RecentTrades } from "@/components/app/overview/recent-trades";
import type { OverviewResponse } from "@/lib/app/overview";

describe("next review action", () => {
  // The keys below are the ones services/activation.py actually emits. The
  // fixture used to invent "strategy_profile" / "first_review", so two of the
  // three states fell through to "the activation path is complete" and the
  // test agreed with the bug.
  it("tells the trader what to re-read, not what to trade", () => {
    render(
      <NextReviewAction
        action={{ completed: 2, total: 3, next_key: "weekly_review", is_activated: false, trades_until_review: 2 }}
      />,
    );
    expect(screen.getByText(/2 of 3/)).toBeInTheDocument();
    expect(screen.getByText(/2 more completed trades/i)).toBeInTheDocument();
  });

  it("has copy for every step the contract can send", () => {
    // STEP_COPY is typed Record<StepKey, …> off the generated union, so tsc
    // already rejects a missing or misspelled key; this pins that each one
    // actually reaches the screen rather than the "nothing waiting" fallback.
    const keys = Object.keys(STEP_COPY) as Array<keyof typeof STEP_COPY>;
    expect(keys.length).toBe(3);
    for (const key of keys) {
      const { unmount } = render(
        <NextReviewAction
          action={{ completed: 1, total: 3, next_key: key, is_activated: false, trades_until_review: 0 }}
        />,
      );
      expect(screen.getByText(STEP_COPY[key].title)).toBeInTheDocument();
      expect(screen.queryByText(/nothing waiting/i)).not.toBeInTheDocument();
      unmount();
    }
  });

  it("counts down the trades that still stand between the trader and a review", () => {
    render(
      <NextReviewAction
        action={{ completed: 2, total: 3, next_key: "weekly_review", is_activated: false, trades_until_review: 3 }}
      />,
    );
    expect(screen.getByText(/3 more completed trades to unlock it/i)).toBeInTheDocument();
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
  const trades: OverviewResponse["recent_trades"] = [
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
