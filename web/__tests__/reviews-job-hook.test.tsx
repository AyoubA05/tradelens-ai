import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Every state setter the hook calls is recorded, so a set after unmount is
 * visible even though React no longer re-renders an unmounted hook.
 */
const setterCalls: unknown[] = [];
vi.mock("react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react")>();
  return {
    ...actual,
    useState: <S,>(initial: S | (() => S)) => {
      const [value, set] = actual.useState(initial);
      const recorded = actual.useCallback(
        (next: React.SetStateAction<S>) => {
          setterCalls.push(next);
          set(next);
        },
        [set],
      );
      return [value, recorded] as const;
    },
  };
});

import { useReviewJob } from "@/components/app/reviews/use-review-job";

/**
 * The enqueue-and-poll hook behind both generate buttons.
 *
 * A generate is paid work: a double click must POST once, a failure must never
 * retry on its own, and leaving the lens must abort without touching state.
 */

const NOTE = {
  period: "2026-09-07",
  content_md: "### What Worked\nKept rules.",
  stats: { trades: 6, win_rate: 0.5, total_pnl: 40, profit_factor: 1.2, total_edge_leak: 0 },
  reviewed_trades: 6,
  created_at: "2026-09-14T10:00:00Z",
};

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function accepted() {
  return json(202, { job_id: 41, status: "queued", created: true });
}

function job(status: string, extra: Record<string, unknown> = {}) {
  return json(200, { job_id: 41, kind: "weekly_recap", status, note: null, error: null, ...extra });
}

async function flush(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useReviewJob", () => {
  it("POSTs once for a double start while running", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(accepted()).mockResolvedValue(job("running"));
    const { result } = renderHook(() => useReviewJob("/api/reviews/weekly"));

    act(() => {
      void result.current.start({ week: "2026-09-07" });
      void result.current.start({ week: "2026-09-07" });
    });
    await flush();

    const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0]![0]).toBe("/api/reviews/weekly");
    expect(posts[0]![1]).toEqual(
      expect.objectContaining({
        body: JSON.stringify({ week: "2026-09-07" }),
        cache: "no-store",
        credentials: "same-origin",
      }),
    );
    expect(result.current.state).toBe("running");
  });

  it("succeeds after queued → running → succeeded and exposes the note", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(accepted())
      .mockResolvedValueOnce(job("queued"))
      .mockResolvedValueOnce(job("running"))
      .mockResolvedValueOnce(job("succeeded", { note: NOTE }));
    const { result } = renderHook(() => useReviewJob("/api/reviews/weekly"));

    act(() => {
      void result.current.start({ week: "2026-09-07" });
    });
    await flush();
    expect(result.current.state).toBe("running");
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/reviews/jobs/41",
      expect.objectContaining({ cache: "no-store", credentials: "same-origin" }),
    );

    await flush(1_000);
    expect(result.current.state).toBe("running");
    await flush(2_000);

    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(result.current.state).toBe("succeeded");
    expect(result.current.note).toEqual(NOTE);
    expect(result.current.message).toBeNull();
  });

  it("maps a failed job to the fixed failure copy, not the job's text", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(accepted())
      .mockResolvedValueOnce(job("failed", { error: "provider said something internal" }));
    const { result } = renderHook(() => useReviewJob("/api/reviews/weekly"));

    act(() => {
      void result.current.start({ week: "2026-09-07" });
    });
    await flush();

    expect(result.current.state).toBe("failed");
    expect(result.current.message).toBe("The review could not be generated. Try again.");
    expect(result.current.note).toBeNull();
    await flush(60_000);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("maps a superseded job to the out-of-date copy", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(accepted())
      .mockResolvedValueOnce(
        job("superseded", { error: "This review is out of date. Generate it again." }),
      );
    const { result } = renderHook(() => useReviewJob("/api/reviews/weekly"));

    act(() => {
      void result.current.start({ week: "2026-09-07" });
    });
    await flush();

    expect(result.current.state).toBe("superseded");
    expect(result.current.message).toBe("This review is out of date. Generate it again.");
    expect(result.current.note).toBeNull();
  });

  it("surfaces the server's 429 sentence without polling", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      json(429, { ok: false, error: "rate_limited", detail: "You've reached today's limit for weekly recaps." }),
    );
    const { result } = renderHook(() => useReviewJob("/api/reviews/weekly"));

    act(() => {
      void result.current.start({ week: "2026-09-07" });
    });
    await flush();

    expect(result.current.state).toBe("rate_limited");
    expect(result.current.message).toBe("You've reached today's limit for weekly recaps.");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("maps a 409 not_enough_trades to its copy", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json(409, { ok: false, detail: "not_enough_trades" }));
    const { result } = renderHook(() => useReviewJob("/api/reviews/weekly"));

    act(() => {
      void result.current.start({ week: "2026-09-07" });
    });
    await flush();

    expect(result.current.state).toBe("refused");
    expect(result.current.message).toBe("Journal more completed trades before a weekly recap.");
  });

  it("maps a 409 empty_period to its copy", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json(409, { ok: false, detail: "empty_period" }));
    const { result } = renderHook(() => useReviewJob("/api/reviews/daily"));

    act(() => {
      void result.current.start({ day: "2026-09-08" });
    });
    await flush();

    expect(result.current.state).toBe("refused");
    expect(result.current.message).toBe("Nothing is logged for this period.");
  });

  it("treats a failed poll response as a failure", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(accepted()).mockResolvedValueOnce(json(502, { ok: false }));
    const { result } = renderHook(() => useReviewJob("/api/reviews/weekly"));

    act(() => {
      void result.current.start({ week: "2026-09-07" });
    });
    await flush();

    expect(result.current.state).toBe("failed");
    expect(result.current.message).toBe("The review could not be generated. Try again.");
  });

  it("fails with the fixed copy when the job never finishes, and stops polling", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(accepted()).mockImplementation(async () => job("running"));
    const { result } = renderHook(() => useReviewJob("/api/reviews/weekly"));

    act(() => {
      void result.current.start({ week: "2026-09-07" });
    });
    await flush();
    // 1 + 2 + 4 + 23 × 8 = 191 seconds of back-off across 27 polls.
    await flush(190_000);
    expect(result.current.state).toBe("running");

    await flush(1_000);
    expect(result.current.state).toBe("failed");
    expect(result.current.message).toBe("The review could not be generated. Try again.");
    expect(fetchMock).toHaveBeenCalledTimes(1 + 27);

    await flush(120_000);
    expect(fetchMock).toHaveBeenCalledTimes(1 + 27);
  });

  it("sets no state from a response that lands after unmount", async () => {
    const fetchMock = vi.mocked(fetch);
    let deliver!: (response: Response) => void;
    // The poll ignores the abort signal and resolves late, like a slow network
    // that finished just after the lens was left.
    fetchMock
      .mockResolvedValueOnce(accepted())
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (deliver = resolve)));
    const { result, unmount } = renderHook(() => useReviewJob("/api/reviews/weekly"));

    act(() => {
      void result.current.start({ week: "2026-09-07" });
    });
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const last = result.current;

    unmount();
    setterCalls.length = 0;
    await act(async () => {
      deliver(job("succeeded", { note: NOTE }));
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(setterCalls).toEqual([]);
    expect(result.current).toBe(last);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("aborts on unmount without polling again or setting state", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(accepted()).mockResolvedValue(job("running"));
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    const { result, unmount } = renderHook(() => useReviewJob("/api/reviews/weekly"));

    act(() => {
      void result.current.start({ week: "2026-09-07" });
    });
    await flush();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const last = result.current;

    unmount();
    await flush(60_000);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current).toBe(last);
    expect(errors).not.toHaveBeenCalled();
    errors.mockRestore();
  });
});
