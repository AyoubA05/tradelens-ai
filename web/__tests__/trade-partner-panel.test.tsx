import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TradePartnerPanel } from "@/components/app/trade-detail/trade-partner-panel";

/**
 * The per-trade partner. The trade is in the PATH; the body carries a
 * boolean for the screenshot and never an id or a key.
 */

const fetchMock = vi.fn();

function reply() {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      conversation_id: "c-1",
      turns: [
        { idx: 0, role: "user", text: "Why?", iat: 1, mac: "a".repeat(64) },
        { idx: 1, role: "assistant", text: "Because.", iat: 2, mac: "b".repeat(64) },
      ],
      evidence: [],
      screenshot_attached: false,
    }),
  };
}

async function ask() {
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "Why?" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /^ask$/i }));
  });
  return JSON.parse(fetchMock.mock.calls.at(-1)![1].body as string);
}

beforeEach(() => {
  fetchMock.mockReset().mockResolvedValue(reply());
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => vi.unstubAllGlobals());

describe("the trade partner panel", () => {
  it("sends to this trade's relay and names no screenshot by default", async () => {
    render(<TradePartnerPanel tradeId={42} hasScreenshot />);
    const body = await ask();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/trades/42/partner/turns");
    expect(body.include_screenshot).toBe(false);
    expect(JSON.stringify(body)).not.toMatch(/screenshot_id|object_key|trade_id/);
  });

  it("asks for the trade's own screenshot only when ticked", async () => {
    render(<TradePartnerPanel tradeId={42} hasScreenshot />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect((await ask()).include_screenshot).toBe(true);
  });

  it("offers no screenshot option on a trade without one, and never sends true", async () => {
    render(<TradePartnerPanel tradeId={42} hasScreenshot={false} />);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect((await ask()).include_screenshot).toBe(false);
  });

  it("starts a fresh conversation when the screenshot choice changes", async () => {
    render(<TradePartnerPanel tradeId={42} hasScreenshot />);
    await ask();
    expect(screen.getAllByTestId("partner-turn-assistant")).toHaveLength(1);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.queryAllByTestId("partner-turn-assistant")).toHaveLength(0);
    const body = await ask();
    expect(body.transcript).toEqual([]);
    expect(body.conversation_id).toBeNull();
  });

  it("says it looks back at a closed trade, never forward", () => {
    render(<TradePartnerPanel tradeId={42} hasScreenshot={false} />);
    expect(screen.getByText(/never comments on future market direction/i)).toBeInTheDocument();
  });
});
