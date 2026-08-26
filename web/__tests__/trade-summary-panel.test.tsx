import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TradeSummaryPanel } from "@/components/app/trades/summary-panel";

const period = { from: "2026-08-01", to: "2026-08-31", presetId: "custom" };

beforeEach(() => vi.stubGlobal("fetch", vi.fn()));
afterEach(() => vi.unstubAllGlobals());

describe("TradeSummaryPanel", () => {
  it("enqueues the current filters, polls, and renders provider text as inert React text", async () => {
    const content = [
      "### Session Summary",
      "<img src=x onerror=alert(1)>",
      "### Discipline & Rule Adherence",
      "**Two** records were reviewed.",
      "### Emotional Review",
      "Emotion logging was limited.",
      "### Recurring Patterns",
      "The sample is small.",
      "### Improvement Actions",
      "- Keep recording the same fields.",
    ].join("\n");
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job_id: 12, status: "queued", created: true }), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            job_id: 12,
            status: "succeeded",
            result: { content_md: content, reviewed_trades: 2 },
            error: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );

    const { container } = render(
      <TradeSummaryPanel period={period} filters={{ asset: "NQ" }} tradeCount={2} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /summarize these 2 trades/i }));

    await screen.findByRole("heading", { name: "Session Summary", level: 3 });
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("Two", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByRole("listitem")).toHaveTextContent("Keep recording the same fields.");
    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "/api/trades/summary",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ from: period.from, to: period.to, asset: "NQ" }),
      }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/trades/summary/12",
      expect.objectContaining({ cache: "no-store", credentials: "same-origin" }),
    );
    expect(screen.getByText(/reviewed 2 trades/i)).toBeInTheDocument();
  });

  it("degrades to a plain message without automatically retrying paid work", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job_id: 12, status: "queued", created: true }), {
          status: 202,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ job_id: 12, status: "failed", result: null, error: "safe" }),
          { status: 200 },
        ),
      );
    const { rerender } = render(
      <TradeSummaryPanel period={period} filters={{}} tradeCount={2} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /summarize/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "This review didn't finish. To avoid duplicate processing, this exact selection will not run again automatically.",
      ),
    );
    // A failure must not remove the only control on the panel: the trader keeps
    // a deliberate, manual retry. Nothing re-runs on its own.
    expect(screen.getByRole("button", { name: /try again/i })).toBeEnabled();
    expect(fetch).toHaveBeenCalledTimes(2);

    rerender(<TradeSummaryPanel period={period} filters={{ asset: "ES" }} tradeCount={2} />);
    expect(screen.getByRole("button", { name: /summarize/i })).toBeEnabled();
  });

  it("shows the backend's rate-limit message instead of the generic error, with no retry", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ok: false,
          error: "rate_limited",
          detail:
            "You've reached 20 AI summaries for today. New summaries are available again 24 hours after your earliest one. Summaries you've already generated are still available.",
        }),
        { status: 429, headers: { "Content-Type": "application/json" } },
      ),
    );

    render(<TradeSummaryPanel period={period} filters={{}} tradeCount={2} />);
    fireEvent.click(screen.getByRole("button", { name: /summarize/i }));

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "You've reached 20 AI summaries for today. New summaries are available again 24 hours after your earliest one. Summaries you've already generated are still available.",
      ),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /summarize/i })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("does not offer a paid summary below the two-trade floor", () => {
    render(<TradeSummaryPanel period={period} filters={{}} tradeCount={1} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/select at least two trades/i)).toBeInTheDocument();
  });

  it("keeps polling beyond the old 39-second window used by normal AI calls", async () => {
    vi.spyOn(window, "setTimeout").mockImplementation((callback) => {
      queueMicrotask(() => (callback as () => void)());
      return 1 as unknown as ReturnType<typeof setTimeout>;
    });
    const markdown = [
      "### Session Summary\n\nEvidence.",
      "### Discipline & Rule Adherence\n\nEvidence.",
      "### Emotional Review\n\nEvidence.",
      "### Recurring Patterns\n\nEvidence.",
      "### Improvement Actions\n\nEvidence.",
    ].join("\n\n");
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ job_id: 20, status: "queued", created: true }), {
        status: 202,
      }),
    );
    for (let index = 0; index < 8; index += 1) {
      vi.mocked(fetch).mockResolvedValueOnce(
        new Response(
          JSON.stringify({ job_id: 20, status: "running", result: null, error: null }),
          { status: 200 },
        ),
      );
    }
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          job_id: 20,
          status: "succeeded",
          result: { content_md: markdown, reviewed_trades: 2 },
          error: null,
        }),
        { status: 200 },
      ),
    );
    render(<TradeSummaryPanel period={period} filters={{}} tradeCount={2} />);

    fireEvent.click(screen.getByRole("button", { name: /summarize/i }));
    await act(async () => {
      for (let index = 0; index < 50; index += 1) await Promise.resolve();
    });

    expect(screen.getByRole("heading", { name: "Session Summary", level: 3 })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(10);
  });

  it("does not render a summary resolved for a selection the trader has left", async () => {
    const markdown = [
      "### Session Summary\n\nSelection A evidence.",
      "### Discipline & Rule Adherence\n\nEvidence.",
      "### Emotional Review\n\nEvidence.",
      "### Recurring Patterns\n\nEvidence.",
      "### Improvement Actions\n\nEvidence.",
    ].join("\n\n");
    let resolvePoll: (value: Response) => void = () => {};
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job_id: 31, status: "queued", created: true }), {
          status: 202,
        }),
      )
      .mockReturnValueOnce(
        new Promise<Response>((resolve) => {
          resolvePoll = resolve;
        }),
      );

    const { rerender } = render(
      <TradeSummaryPanel period={period} filters={{ asset: "NQ" }} tradeCount={2} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /summarize/i }));
    await act(async () => {
      for (let index = 0; index < 5; index += 1) await Promise.resolve();
    });

    rerender(<TradeSummaryPanel period={period} filters={{ asset: "ES" }} tradeCount={2} />);
    await act(async () => {
      resolvePoll(
        new Response(
          JSON.stringify({
            job_id: 31,
            status: "succeeded",
            result: { content_md: markdown, reviewed_trades: 2 },
            error: null,
          }),
          { status: 200 },
        ),
      );
      for (let index = 0; index < 5; index += 1) await Promise.resolve();
    });

    expect(screen.queryByText("Selection A evidence.")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Session Summary", level: 3 }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/reviewed 2 trades/i)).not.toBeInTheDocument();
  });

  it("leaves no permanently disabled button after filters move away and back", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ job_id: 44, status: "queued", created: true }), {
          status: 202,
        }),
      )
      .mockImplementationOnce(
        (_url, init) =>
          new Promise<Response>((_resolve, reject) => {
            (init as RequestInit).signal?.addEventListener("abort", () =>
              reject(new DOMException("Aborted", "AbortError")),
            );
          }),
      );

    const { rerender } = render(
      <TradeSummaryPanel period={period} filters={{ asset: "NQ" }} tradeCount={2} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /summarize/i }));
    await act(async () => {
      for (let index = 0; index < 5; index += 1) await Promise.resolve();
    });
    expect(screen.getByRole("button", { name: /reviewing trades/i })).toBeDisabled();

    rerender(<TradeSummaryPanel period={period} filters={{ asset: "ES" }} tradeCount={2} />);
    await act(async () => {
      for (let index = 0; index < 5; index += 1) await Promise.resolve();
    });
    rerender(<TradeSummaryPanel period={period} filters={{ asset: "NQ" }} tradeCount={2} />);

    expect(screen.getByRole("button", { name: /summarize these 2 trades/i })).toBeEnabled();
  });
});
