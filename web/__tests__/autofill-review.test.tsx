import "@testing-library/jest-dom/vitest";
import { configure, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  APPLIABLE_FIELDS,
  AutofillReview,
} from "@/components/app/new-trade/autofill-review";

// The component's own poll interval is 1.5s real time (never faked here —
// see the comment on `startAndResolve`), so `waitFor`'s default 1s timeout
// is too tight for these tests specifically.
configure({ asyncUtilTimeout: 5000 });

/**
 * Task D2 — per-field AI suggestion review.
 *
 * The load-bearing property: every suggested value is visibly *suggested*
 * until the trader accepts it, and stays distinguishable from a
 * human-entered value throughout. This suite tests that distinction
 * directly (per the group brief), rather than trusting the component's own
 * doc comment.
 */

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: async () => body });
}

vi.setConfig({ testTimeout: 10000 });

afterEach(() => {
  vi.unstubAllGlobals();
});

async function startAndResolve(fetchMock: ReturnType<typeof vi.fn>) {
  fireEvent.click(screen.getByRole("button", { name: /get ai suggestions/i }));
  // Real time: the component's own poll interval is short (1.5s) and these
  // tests resolve on the very first poll tick, so a real wait is simpler
  // and faster than juggling fake timers against `waitFor`'s own polling.
  await waitFor(() => expect(fetchMock).toHaveBeenCalled(), { timeout: 5000 });
}

describe("AutofillReview", () => {
  it("renders every suggestion inside a visibly-labelled 'Suggested' badge, distinct from an entered value", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/trades/autofill") return jsonResponse(202, { job_id: 5 });
      return jsonResponse(200, {
        job_id: 5,
        status: "succeeded",
        error: null,
        suggestions: {
          asset: { value: "NQ", confidence: 0.95, autocheck: true },
          notes: { value: "Clean break of structure", confidence: 0.4, autocheck: false },
        },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AutofillReview tradeId={1} screenshotId={2} expectedUpdatedAt="2026-08-31T00:00:00Z" onDone={vi.fn()} />,
    );
    await startAndResolve(fetchMock);

    await waitFor(() =>
      expect(screen.getByTestId("autofill-suggestion-list")).toBeInTheDocument(),
    );

    // Every rendered suggestion carries the "Suggested" label — this is
    // what makes it structurally different from a value the trader typed:
    // nothing in `NewTradeForm`'s own inputs ever carries this label,
    // because a suggestion never becomes an input's value (see the
    // component's own doc comment).
    const badges = screen.getAllByText("Suggested");
    expect(badges.length).toBe(2);
    expect(screen.getByTestId("autofill-suggestion-asset-value")).toHaveTextContent("NQ");
    expect(screen.getByTestId("autofill-suggestion-notes-value")).toHaveTextContent(
      "Clean break of structure",
    );
  });

  it("pre-checks a suggestion only when the server's own autocheck said so — never a second, client-side threshold", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/trades/autofill") return jsonResponse(202, { job_id: 5 });
      return jsonResponse(200, {
        job_id: 5,
        status: "succeeded",
        error: null,
        suggestions: {
          asset: { value: "NQ", confidence: 0.95, autocheck: true },
          setup_type: { value: "OB Retest", confidence: 0.3, autocheck: false },
        },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AutofillReview tradeId={1} screenshotId={2} expectedUpdatedAt="2026-08-31T00:00:00Z" onDone={vi.fn()} />,
    );
    await startAndResolve(fetchMock);
    await waitFor(() =>
      expect(screen.getByTestId("autofill-suggestion-list")).toBeInTheDocument(),
    );

    const assetCheckbox = screen.getByLabelText(/accept suggested asset/i) as HTMLInputElement;
    const setupCheckbox = screen.getByLabelText(/accept suggested setup type/i) as HTMLInputElement;
    expect(assetCheckbox.checked).toBe(true);
    expect(setupCheckbox.checked).toBe(false);
  });

  it("applies nothing and calls onDone unchanged when the trader skips", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();

    render(
      <AutofillReview tradeId={1} screenshotId={2} expectedUpdatedAt="2026-08-31T00:00:00Z" onDone={onDone} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^skip$/i }));

    expect(onDone).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  /**
   * F4. With `expectedUpdatedAt` null the PATCH's conflict guard has no stamp
   * to send, so nothing can be applied. The component used to call `onDone()`
   * here — the trader ticked boxes, pressed "Apply accepted", was navigated
   * away, and nothing had happened or said so.
   */
  it("says so plainly when accepted suggestions cannot be applied, instead of leaving silently", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/trades/autofill") return jsonResponse(202, { job_id: 5 });
      return jsonResponse(200, {
        job_id: 5,
        status: "succeeded",
        error: null,
        suggestions: { asset: { value: "NQ", confidence: 0.95, autocheck: true } },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();

    render(
      <AutofillReview tradeId={1} screenshotId={2} expectedUpdatedAt={null} onDone={onDone} />,
    );
    await startAndResolve(fetchMock);
    await waitFor(() =>
      expect(screen.getByTestId("autofill-suggestion-list")).toBeInTheDocument(),
    );
    expect(
      (screen.getByLabelText(/accept suggested asset/i) as HTMLInputElement).checked,
    ).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /apply accepted/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("alert").textContent).toMatch(/did not save/i);
    // The trader is told, not silently moved on.
    expect(onDone).not.toHaveBeenCalled();
    // And nothing was PATCHed.
    expect(
      fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH"),
    ).toHaveLength(0);
  });

  it("still leaves quietly when nothing was ticked at all", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/trades/autofill") return jsonResponse(202, { job_id: 5 });
      return jsonResponse(200, {
        job_id: 5,
        status: "succeeded",
        error: null,
        suggestions: { asset: { value: "NQ", confidence: 0.2, autocheck: false } },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();

    render(
      <AutofillReview tradeId={1} screenshotId={2} expectedUpdatedAt={null} onDone={onDone} />,
    );
    await startAndResolve(fetchMock);
    await waitFor(() =>
      expect(screen.getByTestId("autofill-suggestion-list")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: /apply accepted/i }));
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("PATCHes only the accepted, patchable fields when applying", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/trades/autofill") return jsonResponse(202, { job_id: 5 });
      if (url === "/api/trades/autofill/5")
        return jsonResponse(200, {
          job_id: 5,
          status: "succeeded",
          error: null,
          suggestions: {
            asset: { value: "NQ", confidence: 0.95, autocheck: true },
            entry_price: { value: 19850.25, confidence: 0.9, autocheck: true },
          },
        });
      if (url === "/api/trades/1" && init?.method === "PATCH") return jsonResponse(200, { id: 1 });
      return jsonResponse(404, {});
    });
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();

    render(
      <AutofillReview tradeId={1} screenshotId={2} expectedUpdatedAt="2026-08-31T00:00:00Z" onDone={onDone} />,
    );
    await startAndResolve(fetchMock);
    await waitFor(() =>
      expect(screen.getByTestId("autofill-suggestion-list")).toBeInTheDocument(),
    );

    // `entry_price` has no checkbox at all — it isn't a `TradeUpdate` field.
    expect(screen.queryByLabelText(/accept suggested entry price/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /apply accepted/i }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/trades/1",
        expect.objectContaining({ method: "PATCH" }),
      ),
    );
    const patchCall = fetchMock.mock.calls.find(
      ([url, init]) => url === "/api/trades/1" && init?.method === "PATCH",
    );
    const body = JSON.parse((patchCall![1] as RequestInit).body as string);
    expect(body.asset).toBe("NQ");
    expect(body).not.toHaveProperty("entry_price");
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("a failed apply leaves the trade panel saying the trade is unchanged, not lost", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/trades/autofill") return jsonResponse(202, { job_id: 5 });
      if (url === "/api/trades/autofill/5")
        return jsonResponse(200, {
          job_id: 5,
          status: "succeeded",
          error: null,
          suggestions: { asset: { value: "NQ", confidence: 0.95, autocheck: true } },
        });
      if (url === "/api/trades/1" && init?.method === "PATCH") return jsonResponse(500, {});
      return jsonResponse(404, {});
    });
    vi.stubGlobal("fetch", fetchMock);
    const onDone = vi.fn();

    render(
      <AutofillReview tradeId={1} screenshotId={2} expectedUpdatedAt="2026-08-31T00:00:00Z" onDone={onDone} />,
    );
    await startAndResolve(fetchMock);
    await waitFor(() =>
      expect(screen.getByTestId("autofill-suggestion-list")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /apply accepted/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/unchanged/i));
    expect(onDone).not.toHaveBeenCalled();
  });
});

describe("AutofillReview — apply path", () => {
  it("does not offer a suggestion it has no way to apply", async () => {
    // `entry_price` is suggestible but not patchable (it feeds `rr_planned`
    // and `rr_realized`). A card a trader cannot act on spends their
    // attention for nothing, so it is not rendered at all — while the
    // evidence flags, which ARE patchable, are.
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/trades/autofill") return jsonResponse(202, { job_id: 9 });
      return jsonResponse(200, {
        job_id: 9,
        status: "succeeded",
        error: null,
        superseded: false,
        suggestions: {
          entry_price: { value: 20100.25, confidence: 0.9, autocheck: true },
          bos: { value: 1, confidence: null, autocheck: false },
        },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AutofillReview tradeId={1} screenshotId={2} expectedUpdatedAt="2026-08-31T00:00:00Z" onDone={vi.fn()} />,
    );
    await startAndResolve(fetchMock);
    await waitFor(() =>
      expect(screen.getByTestId("autofill-suggestion-list")).toBeInTheDocument(),
    );

    expect(screen.getByTestId("autofill-suggestion-bos")).toBeInTheDocument();
    expect(screen.queryByTestId("autofill-suggestion-entry_price")).toBeNull();
    expect(screen.queryByText(/20100.25/)).toBeNull();
    // Every card that IS rendered has a checkbox to act on.
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(1);
  });

  it("says nothing to suggest when every suggestion is unappliable", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/trades/autofill") return jsonResponse(202, { job_id: 10 });
      return jsonResponse(200, {
        job_id: 10,
        status: "succeeded",
        error: null,
        superseded: false,
        suggestions: { stop_price: { value: 20000, confidence: 0.9, autocheck: true } },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AutofillReview tradeId={1} screenshotId={2} expectedUpdatedAt="2026-08-31T00:00:00Z" onDone={vi.fn()} />,
    );
    await startAndResolve(fetchMock);
    await waitFor(() =>
      expect(screen.getByText(/nothing to suggest/i)).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("autofill-suggestion-list")).toBeNull();
  });

  it("shows nothing when the server says this job's suggestions were superseded", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url === "/api/trades/autofill") return jsonResponse(202, { job_id: 11 });
      return jsonResponse(200, {
        job_id: 11,
        status: "succeeded",
        error: null,
        superseded: true,
        suggestions: null,
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AutofillReview tradeId={1} screenshotId={2} expectedUpdatedAt="2026-08-31T00:00:00Z" onDone={vi.fn()} />,
    );
    await startAndResolve(fetchMock);
    await waitFor(() =>
      expect(screen.getByText(/replaced by a newer screenshot/i)).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("autofill-suggestion-list")).toBeNull();
  });

  it("pins APPLIABLE_FIELDS against the PATCH allowlist the API actually publishes", async () => {
    // The Python side pins autofill-vs-PATCH; this pins the browser's own
    // copy against the generated contract, so a field can never be offered
    // with a checkbox that `PATCH /v1/trades/{id}` would reject.
    const spec = (await import("@/lib/api/openapi.json")).default as {
      components: { schemas: { TradeUpdate: { properties: Record<string, unknown> } } };
    };
    const patchable = new Set(Object.keys(spec.components.schemas.TradeUpdate.properties));
    patchable.delete("expected_updated_at");
    for (const field of APPLIABLE_FIELDS) {
      expect(patchable.has(field)).toBe(true);
    }
  });
});
