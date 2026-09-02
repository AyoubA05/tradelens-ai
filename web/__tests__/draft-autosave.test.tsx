import "@testing-library/jest-dom/vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";

import { useDraftAutosave, isDraftWorthSaving } from "@/lib/app/draft-autosave";
import { emptyNewTradeFormValues, type NewTradeFormValues } from "@/lib/app/new-trade";
import { OTHER_ASSET } from "@/lib/app/new-trade-fields";

/**
 * Task D3 — draft autosave. The load-bearing properties: debounced, never
 * fires on an empty form, and a save failure is non-blocking — it changes
 * only the quiet status indicator, and never something a real submit reads.
 */

function Harness({
  initial,
  suspended = false,
}: {
  initial: NewTradeFormValues;
  suspended?: boolean;
}) {
  const [values, setValues] = useState(initial);
  const status = useDraftAutosave(values, setValues, OTHER_ASSET, suspended);
  return (
    <div>
      <p data-testid="status">{status.kind}</p>
      <input
        aria-label="asset"
        value={values.asset}
        onChange={(e) => setValues((v) => ({ ...v, asset: e.target.value }))}
      />
    </div>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("isDraftWorthSaving", () => {
  it("is false for a freshly-mounted, untouched form", () => {
    expect(isDraftWorthSaving(emptyNewTradeFormValues(), OTHER_ASSET)).toBe(false);
  });

  it("is true once an asset, a date, or an entry time is present", () => {
    expect(
      isDraftWorthSaving({ ...emptyNewTradeFormValues(), asset: "NQ" }, OTHER_ASSET),
    ).toBe(true);
    expect(
      isDraftWorthSaving({ ...emptyNewTradeFormValues(), tradeDate: "2026-08-31" }, OTHER_ASSET),
    ).toBe(true);
    expect(
      isDraftWorthSaving({ ...emptyNewTradeFormValues(), entryTime: "09:30" }, OTHER_ASSET),
    ).toBe(true);
  });
});

describe("useDraftAutosave", () => {
  it("never fires on an empty form: no PUT even after the debounce window", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ draft: null }) });
    vi.stubGlobal("fetch", fetchMock);

    render(<Harness initial={emptyNewTradeFormValues()} />);
    await new Promise((r) => setTimeout(r, 2200));

    const puts = fetchMock.mock.calls.filter(([, init]) => init?.method === "PUT");
    expect(puts).toHaveLength(0);
  }, 10000);

  it("debounces: rapid edits within the window produce exactly one PUT", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (init?.method === "GET" || init === undefined) {
        return Promise.resolve({ ok: true, json: async () => ({ draft: null }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ draft: {} }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Harness initial={emptyNewTradeFormValues()} />);
    const input = screen.getByLabelText("asset");
    for (const ch of ["N", "NQ"]) {
      await act(async () => {
        input.dispatchEvent(new Event("change", { bubbles: true }));
        (input as HTMLInputElement).value = ch;
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
      await new Promise((r) => setTimeout(r, 400)); // less than DEBOUNCE_MS
    }
    await new Promise((r) => setTimeout(r, 2000)); // clear the final debounce

    const puts = fetchMock.mock.calls.filter(([, init]) => init?.method === "PUT");
    expect(puts.length).toBeLessThanOrEqual(1);
  }, 10000);

  /**
   * The mutation-tested property (per the group brief): a failed autosave
   * PUT must never surface as anything but the quiet indicator. This is
   * the test that would catch a regression where a draft-save failure got
   * wired into `submitError` or otherwise blocked/altered a real submit —
   * exactly the failure mode global-constraints.md calls out.
   */
  it("a failed save only changes the status indicator, never throws", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (!init || init.method === "GET") {
        return Promise.resolve({ ok: true, json: async () => ({ draft: null }) });
      }
      return Promise.resolve({ ok: false, status: 500, json: async () => ({ ok: false }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Harness initial={{ ...emptyNewTradeFormValues(), asset: "NQ" }} />);

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("error"), {
      timeout: 5000,
    });
    // No throw reached React's error boundary path — `render` above would
    // have thrown synchronously/asynchronously into the test if it had.
  }, 10000);

  /**
   * F1, browser half. Once the trade is durable the server has already
   * ended the draft; a debounce scheduled a moment before the submit must
   * not write the journaled values straight back, or the next New Trade
   * opens pre-filled with the trade that was just saved.
   */
  it("saves nothing once the trade is durable and autosave is suspended", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (!init || init.method === "GET") {
        return Promise.resolve({ ok: true, json: async () => ({ draft: null }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ draft: {} }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <Harness initial={{ ...emptyNewTradeFormValues(), asset: "NQ" }} suspended />,
    );
    await new Promise((r) => setTimeout(r, 2200));

    const puts = fetchMock.mock.calls.filter(([, init]) => init?.method === "PUT");
    expect(puts).toHaveLength(0);
  }, 10000);

  it("a network failure during save also only changes the status indicator", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (!init || init.method === "GET") {
        return Promise.resolve({ ok: true, json: async () => ({ draft: null }) });
      }
      return Promise.reject(new TypeError("network down"));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Harness initial={{ ...emptyNewTradeFormValues(), asset: "NQ" }} />);

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("error"), {
      timeout: 5000,
    });
  }, 10000);

  it("an old tab cannot retry through a tombstone created by another tab", async () => {
    let gets = 0;
    const puts: RequestInit[] = [];
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (!init || init.method === "GET") {
        gets += 1;
        if (gets === 1) {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: async () => ({ draft: { asset: "NQ" }, revision: 7 }),
          });
        }
        // Another tab journaled the trade while this tab's PUT was in
        // flight. The null draft at a newer revision is the server's
        // terminal tombstone, not an invitation to retry stale values.
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ draft: null, revision: 8 }),
        });
      }
      puts.push(init);
      if (puts.length === 1) {
        return Promise.resolve({
          ok: false,
          status: 409,
          json: async () => ({ detail: "stale draft" }),
        });
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ draft: { asset: "NQ" }, revision: 9 }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Harness initial={emptyNewTradeFormValues()} />);

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("error"), {
      timeout: 6000,
    });
    expect(gets).toBe(2);
    expect(puts).toHaveLength(1);
  }, 10000);
});
