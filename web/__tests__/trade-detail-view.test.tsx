import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

import { TradeDetailView } from "@/components/app/trade-detail/trade-detail-view";
import type { TradeDetail } from "@/lib/app/trades";

const TRADE = {
  id: 42,
  ai_grade: null,
  asset: "NQ",
  asset_class: null,
  bias: null,
  bos: null,
  choch: null,
  confirmation_model: null,
  created_at: null,
  day_of_week: null,
  direction: "Long",
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
  pnl: 100,
  position_size: null,
  result: "Win",
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
  trade_date: "2026-08-01",
  trade_process_notes: null,
  updated_at: "2026-08-01T12:00:00Z",
  user_grade: null,
} satisfies TradeDetail;

beforeEach(() => {
  push.mockReset();
  refresh.mockReset();
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => vi.unstubAllGlobals());

describe("TradeDetailView", () => {
  it("shows the read view and screenshots by default, not the edit form", () => {
    render(<TradeDetailView trade={TRADE} />);
    expect(screen.getByRole("heading", { name: "NQ" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save changes/i })).not.toBeInTheDocument();
  });

  it("switches to the edit form and back via Cancel", () => {
    render(<TradeDetailView trade={TRADE} />);
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    expect(screen.getByRole("button", { name: /save changes/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(screen.queryByRole("button", { name: /save changes/i })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "NQ" })).toBeInTheDocument();
  });

  it("hides Edit/Delete while editing, so they cannot be triggered mid-edit", () => {
    render(<TradeDetailView trade={TRADE} />);
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    expect(screen.queryByRole("button", { name: /^delete$/i })).not.toBeInTheDocument();
  });

  it("refreshes the server data after a successful save, rather than patching local state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => TRADE }),
    );
    render(<TradeDetailView trade={TRADE} />);
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /save changes/i })).not.toBeInTheDocument();
  });

  it("refreshes after an explicit conflict reload, and exits edit mode", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 409, json: async () => ({ error: "stale_trade" }) }),
    );
    render(<TradeDetailView trade={TRADE} />);
    fireEvent.click(screen.getByRole("button", { name: /^edit$/i }));
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    fireEvent.click(await screen.findByRole("button", { name: /reload latest version/i }));
    expect(refresh).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /save changes/i })).not.toBeInTheDocument();
  });

  it("opens the delete dialog from the Delete button", () => {
    render(<TradeDetailView trade={TRADE} />);
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("navigates to the journal after a confirmed delete", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 204 }));
    render(<TradeDetailView trade={TRADE} />);
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/app/journal"));
  });

  it("deletes against this trade's own id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ status: 204 });
    vi.stubGlobal("fetch", fetchMock);
    render(<TradeDetailView trade={TRADE} />);
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^delete trade$/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/trades/42", { method: "DELETE" }));
  });

  it("links back to the journal", () => {
    render(<TradeDetailView trade={TRADE} />);
    expect(screen.getByRole("link", { name: /back to journal/i })).toHaveAttribute(
      "href",
      "/app/journal",
    );
  });
});
