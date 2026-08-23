import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EditTradeForm } from "@/components/app/trade-detail/edit-trade-form";
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
  followed_rules: 1,
  fvg_used: null,
  htf_bias: null,
  killzone: "London",
  liquidity_sweep: null,
  mistake_tags: null,
  notes: "Original note",
  order_block_used: null,
  pnl: 100,
  position_size: null,
  result: "Win",
  reward_amount: null,
  risk_amount: null,
  rr_planned: null,
  rr_realized: null,
  screenshots: [],
  session: "London",
  setup_type: "FVG",
  stop_price: null,
  strategy_used: null,
  timeframe: null,
  tp_price: null,
  trade_date: "2026-08-01",
  trade_process_notes: null,
  updated_at: "2026-08-01T12:00:00Z",
  user_grade: null,
} satisfies TradeDetail;

function fetchOkOnce(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EditTradeForm", () => {
  it("pre-fills fields from the current trade", () => {
    render(<EditTradeForm trade={TRADE} onCancel={vi.fn()} onSaved={vi.fn()} onConflictReload={vi.fn()} />);
    expect(screen.getByDisplayValue("NQ")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Original note")).toBeInTheDocument();
  });

  it("sends expected_updated_at from the trade it was opened with", async () => {
    const fetchMock = fetchOkOnce({ ...TRADE, asset: "ES" });
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();

    render(<EditTradeForm trade={TRADE} onCancel={vi.fn()} onSaved={onSaved} onConflictReload={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/trades/42");
    expect(init.method).toBe("PATCH");
    const body = JSON.parse(init.body);
    expect(body.expected_updated_at).toBe("2026-08-01T12:00:00Z");
  });

  it("sends an edited field's new value", async () => {
    const fetchMock = fetchOkOnce({ ...TRADE, asset: "ES" });
    vi.stubGlobal("fetch", fetchMock);

    render(<EditTradeForm trade={TRADE} onCancel={vi.fn()} onSaved={vi.fn()} onConflictReload={vi.fn()} />);
    fireEvent.change(screen.getByDisplayValue("NQ"), { target: { value: "ES" } });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.asset).toBe("ES");
  });

  it("clears a field to null when the input is emptied", async () => {
    const fetchMock = fetchOkOnce(TRADE);
    vi.stubGlobal("fetch", fetchMock);

    render(<EditTradeForm trade={TRADE} onCancel={vi.fn()} onSaved={vi.fn()} onConflictReload={vi.fn()} />);
    fireEvent.change(screen.getByDisplayValue("Original note"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.notes).toBeNull();
  });

  it("blocks submission with a non-numeric P&L rather than sending it", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<EditTradeForm trade={TRADE} onCancel={vi.fn()} onSaved={vi.fn()} onConflictReload={vi.fn()} />);
    fireEvent.change(screen.getByDisplayValue("100"), { target: { value: "not a number" } });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/must be numbers/i);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("calls onCancel without saving", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const onCancel = vi.fn();

    render(<EditTradeForm trade={TRADE} onCancel={onCancel} onSaved={vi.fn()} onConflictReload={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

    expect(onCancel).toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  describe("409 conflict", () => {
    it("shows the conflict plainly instead of the form, and does not call onSaved", async () => {
      const fetchMock = fetchOkOnce({ error: "stale_trade" }, 409);
      vi.stubGlobal("fetch", fetchMock);
      const onSaved = vi.fn();

      render(<EditTradeForm trade={TRADE} onCancel={vi.fn()} onSaved={onSaved} onConflictReload={vi.fn()} />);
      fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

      expect(await screen.findByRole("alert")).toHaveTextContent(/changed elsewhere/i);
      expect(onSaved).not.toHaveBeenCalled();
    });

    it("does not silently discard the draft — the form is still there under Cancel", async () => {
      const fetchMock = fetchOkOnce({ error: "stale_trade" }, 409);
      vi.stubGlobal("fetch", fetchMock);

      render(<EditTradeForm trade={TRADE} onCancel={vi.fn()} onSaved={vi.fn()} onConflictReload={vi.fn()} />);
      fireEvent.change(screen.getByDisplayValue("NQ"), { target: { value: "ES" } });
      fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

      await screen.findByRole("alert");
      // The conflict view offers an explicit choice — reload or cancel — never
      // an automatic retry and never a silent pick between the two versions.
      expect(screen.getByRole("button", { name: /reload latest version/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
      expect(fetchMock).toHaveBeenCalledOnce();
    });

    it("only reloads when the trader explicitly chooses to", async () => {
      const fetchMock = fetchOkOnce({ error: "stale_trade" }, 409);
      vi.stubGlobal("fetch", fetchMock);
      const onConflictReload = vi.fn();

      render(
        <EditTradeForm trade={TRADE} onCancel={vi.fn()} onSaved={vi.fn()} onConflictReload={onConflictReload} />,
      );
      fireEvent.click(screen.getByRole("button", { name: /save changes/i }));
      await screen.findByRole("alert");
      expect(onConflictReload).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole("button", { name: /reload latest version/i }));
      expect(onConflictReload).toHaveBeenCalledOnce();
    });
  });

  describe("other failures", () => {
    it("reports a generic save failure without claiming anything changed", async () => {
      const fetchMock = fetchOkOnce({ ok: false }, 500);
      vi.stubGlobal("fetch", fetchMock);

      render(<EditTradeForm trade={TRADE} onCancel={vi.fn()} onSaved={vi.fn()} onConflictReload={vi.fn()} />);
      fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

      expect(await screen.findByRole("alert")).toHaveTextContent(/nothing was changed/i);
    });

    it("reports a network failure the same way", async () => {
      vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

      render(<EditTradeForm trade={TRADE} onCancel={vi.fn()} onSaved={vi.fn()} onConflictReload={vi.fn()} />);
      fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

      expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach the server/i);
    });
  });
});

describe("EditTradeForm — a missing conflict stamp", () => {
  /**
   * `expected_updated_at` is the entire conflict guard. Substituting `""`
   * for a missing `updated_at` failed safe — the backend would 409 — but it
   * did so silently, which is the exact shape that hid the un-editable
   * sample-trade bug. Post-backfill this is unreachable; the point is that
   * if it ever becomes reachable again, the trader is told, not left staring
   * at an unexplained failure.
   */
  const stampless = { ...TRADE, updated_at: null } satisfies TradeDetail;

  it("does not attempt the save at all", async () => {
    const fetchMock = fetchOkOnce({});
    vi.stubGlobal("fetch", fetchMock);

    render(
      <EditTradeForm
        trade={stampless}
        onCancel={vi.fn()}
        onSaved={vi.fn()}
        onConflictReload={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await screen.findByRole("alert");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says the trade cannot be edited until it is reloaded", async () => {
    vi.stubGlobal("fetch", fetchOkOnce({}));

    render(
      <EditTradeForm
        trade={stampless}
        onCancel={vi.fn()}
        onSaved={vi.fn()}
        onConflictReload={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/cannot be edited until it is reloaded/i);
    expect(alert).toHaveTextContent(/reload/i);
  });

  it("never sends an empty string in place of the stamp", async () => {
    const fetchMock = fetchOkOnce({});
    vi.stubGlobal("fetch", fetchMock);

    render(
      <EditTradeForm
        trade={stampless}
        onCancel={vi.fn()}
        onSaved={vi.fn()}
        onConflictReload={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await screen.findByRole("alert");

    for (const call of fetchMock.mock.calls) {
      expect(JSON.parse((call[1] as RequestInit).body as string)).not.toMatchObject({
        expected_updated_at: "",
      });
    }
  });

  it("still saves normally when the stamp is present", async () => {
    // The guard must not have made every save conditional on something else.
    const fetchMock = fetchOkOnce({ ...TRADE, updated_at: "2026-08-02T00:00:00Z" });
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();

    render(
      <EditTradeForm
        trade={TRADE}
        onCancel={vi.fn()}
        onSaved={onSaved}
        onConflictReload={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.expected_updated_at).toBe("2026-08-01T12:00:00Z");
  });
});
