import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The Daily Debrief lens. Opening it never starts a paid review; a debrief is
 * generated only from the explicit button, and a saved one links back to that
 * day's trades in the Journal.
 */

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn(), replace: vi.fn() }),
}));

import { DailyLens } from "@/components/app/reviews/daily-lens";

const DEBRIEF = {
  period: "2026-09-08",
  content_md:
    "### Session Summary\nTwo trades in London.\n\n### Discipline & Rule Adherence\n- Rules kept",
  stats: { trades: 2, win_rate: 0.5, total_pnl: 15, profit_factor: 1.5, total_edge_leak: 0 },
  reviewed_trades: 2,
  created_at: "2026-09-08T20:00:00Z",
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

describe("DailyLens", () => {
  it("never calls fetch on render", async () => {
    render(<DailyLens days={["2026-09-08"]} selectedDay="2026-09-08" saved={null} aiAvailable />);
    await flush(10_000);
    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Generate debrief for 2026-09-08" })).toBeInTheDocument();
  });

  it("generates, polls and shows the Day in review note", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(json(202, { job_id: 77, status: "queued", created: true }))
      .mockResolvedValueOnce(
        json(200, { job_id: 77, kind: "daily_debrief", status: "queued", note: null, error: null }),
      )
      .mockResolvedValueOnce(
        json(200, { job_id: 77, kind: "daily_debrief", status: "succeeded", note: DEBRIEF, error: null }),
      );
    render(<DailyLens days={["2026-09-08"]} selectedDay="2026-09-08" saved={null} aiAvailable />);

    fireEvent.click(screen.getByRole("button", { name: "Generate debrief for 2026-09-08" }));
    await flush();
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Day in review" })).toBeNull();

    await flush(1_000);

    expect(screen.getByRole("heading", { name: "Day in review" })).toBeInTheDocument();
    expect(screen.getByText("Two trades in London.")).toBeInTheDocument();
    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "/api/reviews/daily",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ day: "2026-09-08" }) }),
    );
    expect(fetch).toHaveBeenNthCalledWith(2, "/api/reviews/jobs/77", expect.anything());
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it("links a saved debrief to that day in the Journal", () => {
    render(<DailyLens days={["2026-09-08"]} selectedDay="2026-09-08" saved={DEBRIEF} aiAvailable />);
    const link = screen.getByRole("link", { name: "Open these trades in the Journal" });
    expect(link.getAttribute("href")).toContain("from=2026-09-08&to=2026-09-08");
    expect(link).toHaveAttribute("href", "/app/journal?from=2026-09-08&to=2026-09-08");
    expect(
      screen.getByRole("button", { name: "Regenerate debrief for 2026-09-08" }),
    ).toBeInTheDocument();
  });

  it("keeps the saved debrief and shows the refusal copy for an empty day", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json(409, { ok: false, detail: "empty_period" }));
    render(<DailyLens days={["2026-09-08"]} selectedDay="2026-09-08" saved={DEBRIEF} aiAvailable />);

    fireEvent.click(screen.getByRole("button", { name: "Regenerate debrief for 2026-09-08" }));
    await flush();

    expect(screen.getByRole("alert")).toHaveTextContent("Nothing is logged for this period.");
    expect(screen.getByText("Two trades in London.")).toBeInTheDocument();
  });

  it("keeps the saved debrief on screen after a failed regeneration", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(json(202, { job_id: 6, status: "queued", created: true }))
      .mockResolvedValueOnce(
        json(200, { job_id: 6, kind: "daily_debrief", status: "failed", note: null, error: "x" }),
      );
    render(<DailyLens days={["2026-09-08"]} selectedDay="2026-09-08" saved={DEBRIEF} aiAvailable />);
    expect(screen.getByText("Two trades in London.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Regenerate debrief for 2026-09-08" }));
    await flush();
    await flush(1_000);

    expect(screen.getByRole("alert")).toHaveTextContent("The review could not be generated. Try again.");
    expect(screen.getByText("Two trades in London.")).toBeInTheDocument();
    expect(screen.queryByText("x")).toBeNull();
  });

  it("shows the server's rate-limit sentence and hides the button", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      json(429, { ok: false, error: "rate_limited", detail: "You've reached today's limit for daily debriefs." }),
    );
    render(<DailyLens days={["2026-09-08"]} selectedDay="2026-09-08" saved={null} aiAvailable />);

    fireEvent.click(screen.getByRole("button", { name: "Generate debrief for 2026-09-08" }));
    await flush();

    expect(screen.getByRole("status")).toHaveTextContent("You've reached today's limit for daily debriefs.");
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows a saved debrief and no button when AI is unavailable", () => {
    render(
      <DailyLens days={["2026-09-08"]} selectedDay="2026-09-08" saved={DEBRIEF} aiAvailable={false} />,
    );
    expect(screen.getByText("Two trades in London.")).toBeInTheDocument();
    expect(
      screen.getByText("AI reviews are unavailable right now. Saved debriefs are still shown."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("says so when there is no trading day", () => {
    render(<DailyLens days={[]} selectedDay={null} saved={null} aiAvailable />);
    expect(screen.getByText("No trading day to review")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("navigates on day change without enqueueing", async () => {
    render(
      <DailyLens days={["2026-09-08", "2026-09-05"]} selectedDay="2026-09-08" saved={null} aiAvailable />,
    );
    fireEvent.change(screen.getByLabelText("Trading day"), { target: { value: "2026-09-05" } });
    expect(push).toHaveBeenCalledWith("/app/reviews?lens=daily&day=2026-09-05");
    await flush(10_000);
    expect(fetch).not.toHaveBeenCalled();
  });
});
