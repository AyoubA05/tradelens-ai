import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AILabelReview } from "@/components/app/trade-detail/ai-label-review";
import type { AIAnalysisDetail } from "@/lib/app/trade-analysis";

const ANALYSIS: AIAnalysisDetail = {
  ai_grade: "B",
  bias: "Bullish",
  confirmed_fields: [],
  detected_setup: "London sweep and reversal",
  grading: null,
  journal_entry_md: null,
  key_zones: [],
  matched_strategy: "OB retest",
  missed_opportunities: [],
  possible_mistakes: [],
  trade_quality: 3,
  updated_at: "2026-09-01T10:00:00Z",
  user_grade: null,
};

function withConfirmed(fields: string[]): AIAnalysisDetail {
  return { ...ANALYSIS, confirmed_fields: fields };
}

/** A PATCH response echoing the labels the server now holds. */
function okResponse(confirmed: string[]) {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      bias: ANALYSIS.bias,
      detected_setup: ANALYSIS.detected_setup,
      trade_quality: ANALYSIS.trade_quality,
      matched_strategy: ANALYSIS.matched_strategy,
      user_grade: null,
      confirmed_fields: confirmed,
    }),
  };
}

function bodyOf(fetchMock: ReturnType<typeof vi.fn>, call = 0): Record<string, unknown> {
  const init = fetchMock.mock.calls[call][1] as RequestInit;
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AILabelReview", () => {
  it("marks an unconfirmed label as the AI's reading", () => {
    render(<AILabelReview analysis={ANALYSIS} tradeId={7} onSaved={() => {}} />);

    const row = screen.getByTestId("label-field-bias");
    expect(row).toHaveAttribute("data-confirmed", "false");
    expect(row).toHaveTextContent(/the AI's reading/i);
    expect(row).not.toHaveTextContent(/you confirmed this/i);
  });

  it("marks a confirmed label as the trader's own, distinctly from the AI's", () => {
    render(<AILabelReview analysis={withConfirmed(["bias"])} tradeId={7} onSaved={() => {}} />);

    const confirmedRow = screen.getByTestId("label-field-bias");
    const aiRow = screen.getByTestId("label-field-detected_setup");
    expect(confirmedRow).toHaveAttribute("data-confirmed", "true");
    expect(confirmedRow).toHaveTextContent(/you confirmed this/i);
    expect(confirmedRow).not.toHaveTextContent(/the AI's reading/i);
    // Textually distinct, and carried by more than colour.
    expect(aiRow).toHaveAttribute("data-confirmed", "false");
    expect(confirmedRow.className).not.toEqual(aiRow.className);
  });

  it("sends only the fields the trader actually changed", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse(["bias"]));
    vi.stubGlobal("fetch", fetchMock);

    render(<AILabelReview analysis={ANALYSIS} tradeId={7} onSaved={() => {}} />);
    fireEvent.change(screen.getByLabelText(/bias at entry/i), {
      target: { value: "Bearish" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save these labels/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = bodyOf(fetchMock);
    expect(body).toEqual({ bias: "Bearish" });
    // Untouched fields are ABSENT, not merely carrying their old value.
    expect(body).not.toHaveProperty("trade_quality");
    expect(body).not.toHaveProperty("detected_setup");
    expect(body).not.toHaveProperty("matched_strategy");
    expect(body).not.toHaveProperty("user_grade");
    expect(Object.keys(body)).toEqual(["bias"]);
  });

  it("releases a confirmed field as its own action, saying the AI may update it again", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    render(<AILabelReview analysis={withConfirmed(["bias"])} tradeId={7} onSaved={() => {}} />);
    const row = screen.getByTestId("label-field-bias");
    expect(row).toHaveTextContent(/a newer analysis may update it again/i);

    fireEvent.click(screen.getByRole("button", { name: /let a newer analysis update bias/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(bodyOf(fetchMock)).toEqual({ release: ["bias"] });
  });

  it("keeps the value in place after releasing it", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    render(<AILabelReview analysis={withConfirmed(["bias"])} tradeId={7} onSaved={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /let a newer analysis update bias/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.getByTestId("label-field-bias")).toHaveAttribute("data-confirmed", "false"),
    );
    expect(screen.getByLabelText(/bias at entry/i)).toHaveValue("Bullish");
  });

  it("says a failed save did not go through and keeps every edit", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: false, status: 502, json: async () => ({ ok: false }) });
    vi.stubGlobal("fetch", fetchMock);

    render(<AILabelReview analysis={ANALYSIS} tradeId={7} onSaved={() => {}} />);
    fireEvent.change(screen.getByLabelText(/bias at entry/i), {
      target: { value: "Bearish" },
    });
    fireEvent.change(screen.getByLabelText(/matched strategy/i), {
      target: { value: "FVG fill" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save these labels/i }));

    await waitFor(() =>
      expect(screen.getByText(/these labels weren't saved/i)).toBeInTheDocument(),
    );
    expect(screen.getByLabelText(/bias at entry/i)).toHaveValue("Bearish");
    expect(screen.getByLabelText(/matched strategy/i)).toHaveValue("FVG fill");
    // Nothing here suggests the trade or its data is at risk.
    expect(screen.queryByText(/lost|deleted|at risk|corrupt/i)).not.toBeInTheDocument();
  });

  it("fires no request when nothing has been changed", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    render(<AILabelReview analysis={ANALYSIS} tradeId={7} onSaved={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /save these labels/i }));

    await waitFor(() =>
      expect(screen.getByText(/nothing has been changed/i)).toBeInTheDocument(),
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("never sends a non-numeric or out-of-range trade quality", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse(["bias"]));
    vi.stubGlobal("fetch", fetchMock);

    render(<AILabelReview analysis={ANALYSIS} tradeId={7} onSaved={() => {}} />);
    const quality = screen.getByLabelText(/trade quality/i);

    fireEvent.change(quality, { target: { value: "great" } });
    fireEvent.click(screen.getByRole("button", { name: /save these labels/i }));
    await waitFor(() =>
      expect(screen.getByText(/whole number from 1 to 5/i)).toBeInTheDocument(),
    );
    expect(fetchMock).not.toHaveBeenCalled();

    fireEvent.change(quality, { target: { value: "9" } });
    fireEvent.click(screen.getByRole("button", { name: /save these labels/i }));
    await waitFor(() =>
      expect(screen.getByText(/whole number from 1 to 5/i)).toBeInTheDocument(),
    );
    expect(fetchMock).not.toHaveBeenCalled();

    // And a good value goes through as a number, never as NaN.
    fireEvent.change(quality, { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: /save these labels/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(bodyOf(fetchMock)).toEqual({ trade_quality: 4 });
  });
});
