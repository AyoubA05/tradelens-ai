import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The Weekly Recap lens.
 *
 * Opening it never starts a paid review (R2). A saved recap stays on screen
 * while a regeneration runs and after one fails or is superseded; only a
 * successful regeneration replaces it.
 */

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn(), replace: vi.fn() }),
}));

import { WeeklyLens } from "@/components/app/reviews/weekly-lens";

const SAVED = {
  period: "2026-09-07",
  content_md: "### What Worked\nSaved recap body.\n\n### What Didn't\n- nothing",
  stats: { trades: 6, win_rate: 0.5, total_pnl: 40, profit_factor: 1.2, total_edge_leak: 0 },
  reviewed_trades: 6,
  created_at: "2026-09-10T10:00:00Z",
};

const FRESH = {
  ...SAVED,
  content_md: "### What Worked\nFresh recap body.",
  created_at: "2026-09-14T10:00:00Z",
};

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

async function flush(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn());
  push.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("WeeklyLens", () => {
  it("never calls fetch on render", async () => {
    render(
      <WeeklyLens
        weeks={["2026-09-07", "2026-08-31"]}
        selectedWeek="2026-09-07"
        saved={null}
        completeTrades={12}
        tradesForReview={5}
        aiAvailable
      />,
    );
    await flush(10_000);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Generate weekly recap" })).toBeInTheDocument();
  });

  it("shows the gate copy and no button when undersized with no saved recap", () => {
    render(
      <WeeklyLens
        weeks={["2026-09-07"]}
        selectedWeek="2026-09-07"
        saved={null}
        completeTrades={2}
        tradesForReview={5}
        aiAvailable
      />,
    );
    expect(screen.getByText(/Journal 3 more completed trades/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("keeps the saved recap on screen while regenerating and after a failure", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(json(202, { job_id: 5, status: "queued", created: true }))
      .mockResolvedValueOnce(
        json(200, { job_id: 5, kind: "weekly_recap", status: "running", note: null, error: null }),
      )
      .mockResolvedValueOnce(
        json(200, { job_id: 5, kind: "weekly_recap", status: "failed", note: null, error: "x" }),
      );
    render(
      <WeeklyLens
        weeks={["2026-09-07"]}
        selectedWeek="2026-09-07"
        saved={SAVED}
        completeTrades={2}
        tradesForReview={5}
        aiAvailable
      />,
    );
    expect(screen.getByRole("heading", { name: "Week in review" })).toBeInTheDocument();
    expect(screen.getByText("Saved recap body.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Regenerate this week" }));
    await flush();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("Saved recap body.")).toBeInTheDocument();

    await flush(1_000);
    expect(screen.getByRole("alert")).toHaveTextContent("The review could not be generated. Try again.");
    expect(screen.getByText("Saved recap body.")).toBeInTheDocument();
    expect(screen.queryByText("x")).toBeNull();
  });

  it("keeps the saved recap after a superseded regeneration", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(json(202, { job_id: 5, status: "queued", created: false }))
      .mockResolvedValueOnce(
        json(200, {
          job_id: 5,
          kind: "weekly_recap",
          status: "superseded",
          note: null,
          error: "This review is out of date. Generate it again.",
        }),
      );
    render(
      <WeeklyLens
        weeks={["2026-09-07"]}
        selectedWeek="2026-09-07"
        saved={SAVED}
        completeTrades={12}
        tradesForReview={5}
        aiAvailable
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Regenerate this week" }));
    await flush();

    expect(screen.getByRole("alert")).toHaveTextContent("This review is out of date. Generate it again.");
    expect(screen.getByText("Saved recap body.")).toBeInTheDocument();
  });

  it("replaces the saved recap on success", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(json(202, { job_id: 5, status: "queued", created: true }))
      .mockResolvedValueOnce(
        json(200, { job_id: 5, kind: "weekly_recap", status: "succeeded", note: FRESH, error: null }),
      );
    render(
      <WeeklyLens
        weeks={["2026-09-07"]}
        selectedWeek="2026-09-07"
        saved={SAVED}
        completeTrades={12}
        tradesForReview={5}
        aiAvailable
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Regenerate this week" }));
    await flush();

    expect(screen.getByText("Fresh recap body.")).toBeInTheDocument();
    expect(screen.queryByText("Saved recap body.")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "/api/reviews/weekly",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ week: "2026-09-07" }) }),
    );
  });

  it("shows the saved recap and no button when AI is unavailable", () => {
    render(
      <WeeklyLens
        weeks={["2026-09-07"]}
        selectedWeek="2026-09-07"
        saved={SAVED}
        completeTrades={12}
        tradesForReview={5}
        aiAvailable={false}
      />,
    );
    expect(screen.getByText("Saved recap body.")).toBeInTheDocument();
    expect(
      screen.getByText("AI reviews are unavailable right now. Saved recaps are still shown."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("says so when there is no completed week", () => {
    render(
      <WeeklyLens
        weeks={[]}
        selectedWeek={null}
        saved={null}
        completeTrades={0}
        tradesForReview={5}
        aiAvailable
      />,
    );
    expect(screen.getByText("No completed week to review")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByRole("link", { name: /journal/i })).toHaveAttribute("href", "/app/journal");
  });

  it("navigates on week change without enqueueing", async () => {
    render(
      <WeeklyLens
        weeks={["2026-09-07", "2026-08-31"]}
        selectedWeek="2026-09-07"
        saved={null}
        completeTrades={12}
        tradesForReview={5}
        aiAvailable
      />,
    );
    fireEvent.change(screen.getByLabelText("Week starting"), { target: { value: "2026-08-31" } });
    expect(push).toHaveBeenCalledWith("/app/reviews?lens=weekly&week=2026-08-31");
    await flush(10_000);
    expect(fetch).not.toHaveBeenCalled();
  });
});
