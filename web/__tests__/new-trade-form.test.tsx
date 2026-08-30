import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { NewTradeForm } from "@/components/app/new-trade/new-trade-form";

function fetchOkOnce(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
}

beforeEach(() => {
  push.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/**
 * Task C2 — the dense New Trade form.
 *
 * These tests cover: it renders every group visible at once (no wizard),
 * client validation surfaces the P&L/outcome contradiction inline without
 * blocking submit, completeness warnings are non-blocking, a successful
 * create navigates to the new trade, and a duplicate (`duplicate_of`) is
 * shown as "already logged," never as an error.
 */
describe("NewTradeForm", () => {
  it("renders every section at once — no wizard, no step indicator", () => {
    render(<NewTradeForm />);
    expect(screen.getByText("Chart")).toBeInTheDocument();
    expect(screen.getByText("When and what")).toBeInTheDocument();
    expect(screen.getByText("Setup and evidence")).toBeInTheDocument();
    expect(screen.getByText("Risk and outcome")).toBeInTheDocument();
    expect(screen.getByText("Reflection")).toBeInTheDocument();
    expect(screen.queryByText(/step \d of \d/i)).not.toBeInTheDocument();
  });

  it("shows a P&L/result contradiction inline, mirroring canonical_outcome, without disabling submit", () => {
    render(<NewTradeForm />);
    fireEvent.change(screen.getByPlaceholderText("e.g., 250.00"), { target: { value: "250" } });
    fireEvent.change(screen.getByLabelText("Result"), { target: { value: "Loss" } });

    expect(screen.getByRole("alert", { name: "" })).toBeInTheDocument();
    expect(screen.getByText(/doesn't match/i)).toBeInTheDocument();
    // Courtesy only — never the only gate (global rule 4).
    expect(screen.getByRole("button", { name: /save trade/i })).not.toBeDisabled();
  });

  it("shows completeness warnings without blocking submit (global rule 5)", () => {
    render(<NewTradeForm />);
    expect(screen.getByText(/thin record is allowed/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save trade/i })).not.toBeDisabled();
  });

  it("submits the built payload and navigates to the created trade", async () => {
    const fetchMock = fetchOkOnce({ id: 99, duplicate_of: null });
    vi.stubGlobal("fetch", fetchMock);

    render(<NewTradeForm />);
    fireEvent.change(screen.getByLabelText("Asset"), { target: { value: "NQ" } });
    fireEvent.change(screen.getByPlaceholderText(/09:30/), { target: { value: "09:30" } });
    fireEvent.click(screen.getByRole("button", { name: /save trade/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/app/trades/99"));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/trades/create");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.asset).toBe("NQ");
  });

  it("shows a duplicate as 'already logged', not as an error, and creates nothing new", async () => {
    vi.stubGlobal("fetch", fetchOkOnce({ id: 7, duplicate_of: 7 }));

    render(<NewTradeForm />);
    fireEvent.change(screen.getByLabelText("Asset"), { target: { value: "NQ" } });
    fireEvent.change(screen.getByPlaceholderText(/09:30/), { target: { value: "09:30" } });
    fireEvent.click(screen.getByRole("button", { name: /save trade/i }));

    await waitFor(() => expect(screen.getByText(/already logged/i)).toBeInTheDocument());
    expect(push).not.toHaveBeenCalled();
    expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
  });

  it("renders the 422 detail the relay forwards, not generic copy", async () => {
    // `{ ok: false, detail }` is exactly what app/api/trades/create answers
    // on a 422 (see new-trade-create-route.test.ts). The trader must see the
    // backend's own message — here the contradiction named by
    // OutcomeMismatch — rather than "nothing was recorded", which tells them
    // nothing to fix.
    vi.stubGlobal(
      "fetch",
      fetchOkOnce(
        { ok: false, detail: "result says Win but pnl is negative" },
        422,
      ),
    );

    render(<NewTradeForm />);
    fireEvent.click(screen.getByRole("button", { name: /save trade/i }));

    await waitFor(() =>
      expect(screen.getByText(/result says Win but pnl is negative/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/nothing was recorded/i)).not.toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("falls back to plain copy when the failure carries no detail", async () => {
    vi.stubGlobal("fetch", fetchOkOnce({ ok: false }, 502));

    render(<NewTradeForm />);
    fireEvent.click(screen.getByRole("button", { name: /save trade/i }));

    await waitFor(() =>
      expect(screen.getByText(/nothing was recorded/i)).toBeInTheDocument(),
    );
    expect(push).not.toHaveBeenCalled();
  });

  it("never says 'nothing was saved' when the trade was created but something after that throws", async () => {
    // The trade-creation POST succeeds; the failure happens after (here,
    // router.push) — a case the outer catch used to conflate with "the
    // server was unreachable, nothing was saved" (design decision #6).
    vi.stubGlobal("fetch", fetchOkOnce({ id: 42, duplicate_of: null }));
    push.mockImplementationOnce(() => {
      throw new Error("navigation failed");
    });

    render(<NewTradeForm />);
    fireEvent.change(screen.getByLabelText("Asset"), { target: { value: "NQ" } });
    fireEvent.change(screen.getByPlaceholderText(/09:30/), { target: { value: "09:30" } });
    fireEvent.click(screen.getByRole("button", { name: /save trade/i }));

    await waitFor(() =>
      expect(screen.getAllByText(/your trade is saved/i).length).toBeGreaterThan(0),
    );
    expect(screen.queryByText(/nothing was saved/i)).not.toBeInTheDocument();
  });

  it("does not claim nothing was saved when the create response is lost", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection reset")));

    render(<NewTradeForm />);
    fireEvent.change(screen.getByLabelText("Asset"), { target: { value: "NQ" } });
    fireEvent.change(screen.getByPlaceholderText(/09:30/), { target: { value: "09:30" } });
    fireEvent.click(screen.getByRole("button", { name: /save trade/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/could not confirm/i),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/safe to retry/i);
    expect(screen.queryByText(/nothing was saved/i)).not.toBeInTheDocument();
  });

  it("reveals the custom asset field only when 'Other / Custom' is picked", () => {
    render(<NewTradeForm />);
    expect(screen.queryByLabelText("Custom asset")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Asset"), { target: { value: "Other / Custom" } });
    expect(screen.getByLabelText("Custom asset")).toBeInTheDocument();
  });
});
