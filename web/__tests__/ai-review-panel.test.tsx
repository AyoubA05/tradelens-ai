import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AIReviewPanel } from "@/components/app/trade-detail/ai-review-panel";
import type { AIAnalysisDetail } from "@/lib/app/trade-analysis";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const TRADE = { id: 7, screenshots: [{ id: 12 }] } as never;
const NO_SHOT_TRADE = { id: 7, screenshots: [] } as never;

const ANALYSIS: AIAnalysisDetail = {
  ai_grade: "B",
  bias: "Bullish",
  confirmed_fields: [],
  detected_setup: "London sweep and reversal",
  grading: null,
  journal_entry_md: null,
  key_zones: [],
  matched_strategy: null,
  missed_opportunities: [],
  possible_mistakes: [],
  trade_quality: 3,
  updated_at: "2026-09-01T10:00:00Z",
  user_grade: null,
};

/** A poll response for the analysis job route. */
function job(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      job_id: 1,
      kind: "trade_analysis",
      status: "running",
      error: null,
      superseded: false,
      ...overrides,
    }),
  };
}

const ACCEPTED = {
  ok: true,
  status: 202,
  json: async () => ({ job_id: 1, status: "queued", created: true }),
};

/** Route POSTs to `accepted` and job GETs to whatever `poll` returns. */
function stubFetch(poll: () => unknown, accepted: unknown = ACCEPTED) {
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    if ((init?.method ?? "GET") === "POST") return Promise.resolve(accepted);
    void url;
    return Promise.resolve(poll());
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  refresh.mockClear();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("AIReviewPanel", () => {
  it("says the analysis has not been run rather than showing an empty result", () => {
    render(<AIReviewPanel trade={TRADE} analysis={null} />);
    expect(screen.getByText(/not analysed yet/i)).toBeInTheDocument();
    // Not a zero or blank grade standing in for an absent one.
    expect(screen.queryByText(/^Grade$/)).not.toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("renders the stored analysis instead of the not-analysed line", () => {
    render(<AIReviewPanel trade={TRADE} analysis={ANALYSIS} />);
    expect(screen.getByText("London sweep and reversal")).toBeInTheDocument();
    expect(screen.queryByText(/not analysed yet/i)).not.toBeInTheDocument();
  });

  it("offers a retry after a failed job, and the retry is the same one button", async () => {
    stubFetch(() =>
      job({
        status: "failed",
        error: "This could not be generated. Please try again.",
      }),
    );

    render(<AIReviewPanel trade={TRADE} analysis={null} />);
    fireEvent.click(screen.getByRole("button", { name: /analyse the chart/i }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument(),
    );
    expect(screen.getByText(/didn't finish/i)).toBeInTheDocument();
    // The failure is stated without blaming the trader and without a raw trace.
    expect(screen.queryByText(/traceback|exception/i)).not.toBeInTheDocument();
    // One control, not a second "analyse" button beside the retry.
    expect(
      screen.queryByRole("button", { name: /analyse the chart/i }),
    ).not.toBeInTheDocument();
  });

  it("tells the trader when their result was superseded rather than showing it as saved", async () => {
    stubFetch(() => job({ status: "succeeded", superseded: true }));

    render(<AIReviewPanel trade={TRADE} analysis={null} />);
    fireEvent.click(screen.getByRole("button", { name: /analyse the chart/i }));

    await waitFor(() =>
      expect(screen.getByText(/newer analysis replaced this one/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/saved/i)).not.toBeInTheDocument();
  });

  it("cannot start a second job while one is running", async () => {
    const fetchMock = stubFetch(() => job({ status: "running" }));

    render(<AIReviewPanel trade={TRADE} analysis={null} />);
    fireEvent.click(screen.getByRole("button", { name: /analyse the chart/i }));

    const running = await screen.findByRole("button", { name: /analysing/i });
    expect(running).toBeDisabled();
    // Clicking the disabled control enqueues nothing further: exactly the
    // one POST from the first click.
    fireEvent.click(running);
    const posts = fetchMock.mock.calls.filter(
      (call) => (call[1] as RequestInit | undefined)?.method === "POST",
    );
    expect(posts).toHaveLength(1);
  });

  it("says a rate limit is a limit, in the backend's own words, not an error", async () => {
    stubFetch(() => job(), {
      ok: false,
      status: 429,
      json: async () => ({
        ok: false,
        error: "rate_limited",
        detail: "You've reached 20 AI analyses for today.",
      }),
    });

    render(<AIReviewPanel trade={TRADE} analysis={null} />);
    fireEvent.click(screen.getByRole("button", { name: /analyse the chart/i }));

    await waitFor(() =>
      expect(screen.getByText(/reached 20 AI analyses for today/i)).toBeInTheDocument(),
    );
    // Presented as a limit, not as a failure with a retry.
    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/didn't finish/i)).not.toBeInTheDocument();
  });

  it("offers no analysis button at all when the trade has no screenshot", () => {
    render(<AIReviewPanel trade={NO_SHOT_TRADE} analysis={null} />);
    expect(
      screen.queryByRole("button", { name: /analyse the chart/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/add a chart screenshot/i)).toBeInTheDocument();
  });

  it("disables journal and grade until an analysis exists, and says why", () => {
    render(<AIReviewPanel trade={TRADE} analysis={null} />);
    expect(screen.getByRole("button", { name: /write the journal entry/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /grade this trade/i })).toBeDisabled();
    expect(screen.getAllByText(/available once the chart has been analysed/i).length).toBe(2);
  });

  it("enables journal and grade once an analysis exists", () => {
    render(<AIReviewPanel trade={TRADE} analysis={ANALYSIS} />);
    expect(screen.getByRole("button", { name: /write the journal entry/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /grade this trade/i })).toBeEnabled();
    expect(
      screen.queryByText(/available once the chart has been analysed/i),
    ).not.toBeInTheDocument();
  });

  it("surfaces the backend's 409 sentence if the analysis vanished under a journal run", async () => {
    stubFetch(() => job({ kind: "trade_journal" }), {
      ok: false,
      status: 409,
      json: async () => ({
        ok: false,
        error: "conflict",
        detail: "This trade has no analysis to journal from.",
      }),
    });

    render(<AIReviewPanel trade={TRADE} analysis={ANALYSIS} />);
    fireEvent.click(screen.getByRole("button", { name: /write the journal entry/i }));

    await waitFor(() =>
      expect(screen.getByText(/no analysis to journal from/i)).toBeInTheDocument(),
    );
  });

  it("ignores a poll answering about a different job", async () => {
    vi.useFakeTimers();
    let polls = 0;
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if ((init?.method ?? "GET") === "POST") return Promise.resolve(ACCEPTED);
      void url;
      polls += 1;
      // The first poll answers about job 99 — a stale response that must not
      // be allowed to report this job as finished.
      if (polls === 1) {
        return Promise.resolve(
          job({ job_id: 99, status: "succeeded", superseded: true }),
        );
      }
      return Promise.resolve(job({ status: "running" }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<AIReviewPanel trade={TRADE} analysis={null} />);
    fireEvent.click(screen.getByRole("button", { name: /analyse the chart/i }));

    await vi.advanceTimersByTimeAsync(5_000);
    expect(polls).toBeGreaterThan(1);
    expect(screen.queryByText(/newer analysis replaced this one/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /analysing/i })).toBeDisabled();
  });

  it("refreshes the page when a job lands, rather than inventing the result client-side", async () => {
    stubFetch(() => job({ status: "succeeded", superseded: false }));

    render(<AIReviewPanel trade={TRADE} analysis={null} />);
    fireEvent.click(screen.getByRole("button", { name: /analyse the chart/i }));

    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(screen.queryByText(/newer analysis replaced this one/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /analyse the chart/i })).toBeEnabled();
  });

  it("stops polling once unmounted", async () => {
    vi.useFakeTimers();
    const fetchMock = stubFetch(() => job({ status: "running" }));

    const view = render(<AIReviewPanel trade={TRADE} analysis={null} />);
    fireEvent.click(screen.getByRole("button", { name: /analyse the chart/i }));
    await vi.advanceTimersByTimeAsync(5_000);
    const before = fetchMock.mock.calls.length;
    expect(before).toBeGreaterThan(1);

    view.unmount();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(fetchMock.mock.calls.length).toBe(before);
  });
});
