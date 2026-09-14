import "@testing-library/jest-dom/vitest";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The AI Reviews page around its one fetch.
 *
 * A failed load renders an error and zero buttons: no generate control is ever
 * offered over a picture of the journal that did not load.
 */

const authenticate = vi.fn();
const appRedirect = vi.fn();
const fetchReviews = vi.fn();
const redirect = vi.fn((path: string) => {
  throw new Error(`redirect:${path}`);
});

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ cookie: "tl_session=browser-token" }),
}));
vi.mock("next/navigation", () => ({
  redirect: (path: string) => redirect(path),
  useRouter: () => ({ refresh: vi.fn(), replace: vi.fn(), push: vi.fn() }),
}));
vi.mock("@/lib/auth/session", () => ({
  sessionTokenFromCookieHeader: () => "browser-token",
  authenticateSessionToken: (...args: unknown[]) => authenticate(...args),
  appLayoutRedirect: (...args: unknown[]) => appRedirect(...args),
}));
vi.mock("@/lib/app/reviews", () => ({
  fetchReviews: (...args: unknown[]) => fetchReviews(...args),
}));

import ReviewsPage from "@/app/app/reviews/page";

function reviews(overrides = {}) {
  return {
    patterns: {
      trades: 12,
      stats: { trades: 12, win_rate: 0.5, total_pnl: 120, profit_factor: 1.4, total_edge_leak: -20 },
      insights: [
        { title: "After a loss", body: "Re-entries lose.", confidence: "low", type: "negative", min_trades: 3 },
        { title: "London Open", body: "Best window.", confidence: "medium", type: "positive", min_trades: 3 },
      ],
      strategy_included: true,
    },
    weeks: ["2026-09-07"],
    days: ["2026-09-08"],
    complete_trades: 12,
    trades_for_review: 5,
    ai_available: true,
    weekly: null,
    daily: null,
    ...overrides,
  };
}

function params(values: Record<string, string> = {}) {
  return Promise.resolve(values);
}

beforeEach(() => {
  authenticate.mockReset().mockResolvedValue({ userId: 7, appSurface: "nextjs" });
  appRedirect.mockReset().mockReturnValue(null);
  fetchReviews.mockReset().mockResolvedValue(reviews());
  redirect.mockClear();
});

describe("AI Reviews page — Patterns (default lens)", () => {
  it("opens on Patterns with the lead thesis, findings and the period strip", async () => {
    render(await ReviewsPage({ searchParams: params() }));

    expect(screen.getByRole("heading", { level: 1, name: "AI Reviews" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Patterns" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Weekly Recap" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByText("What keeps repeating in the journal?")).toBeInTheDocument();

    // Sorted by confidence: the medium insight leads even though it came second.
    const lead = screen.getByTestId("patterns-lead");
    expect(within(lead).getByText("Best window.")).toBeInTheDocument();
    const findings = screen.getAllByTestId("patterns-finding");
    expect(findings[0]).toHaveTextContent("After a loss");

    expect(screen.getByText("Trades").nextSibling).toHaveTextContent("12");
    expect(screen.getByText("Profit factor").nextSibling).toHaveTextContent("1.4x");
    expect(screen.getByText("Computed from your journal — no AI call")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Re-read the trades behind/ })).toHaveAttribute(
      "href",
      "/app/journal",
    );
    expect(fetchReviews).toHaveBeenCalledWith("browser-token", {});
  });

  it("states the reflection-only sentence", async () => {
    render(await ReviewsPage({ searchParams: params() }));
    expect(document.body).toHaveTextContent("Reflection only — never signals or advice.");
  });

  it("renders the empty and small-sample copy", async () => {
    fetchReviews.mockResolvedValue(
      reviews({
        patterns: {
          trades: 2,
          stats: { trades: 2, win_rate: 0.5, total_pnl: 10, profit_factor: 2, total_edge_leak: 0 },
          insights: [],
          strategy_included: false,
        },
        complete_trades: 2,
      }),
    );
    render(await ReviewsPage({ searchParams: params() }));
    expect(screen.getByText("No repeating patterns yet")).toBeInTheDocument();
    expect(screen.getByText(/Journal 3 more completed trades/)).toBeInTheDocument();
  });

  it("falls back to Patterns for an unknown lens", async () => {
    render(await ReviewsPage({ searchParams: params({ lens: "signals" }) }));
    expect(screen.getByRole("tab", { name: "Patterns" })).toHaveAttribute("aria-selected", "true");
  });
});

describe("AI Reviews page — period parameters", () => {
  it("forwards an ISO week", async () => {
    await ReviewsPage({ searchParams: params({ lens: "weekly", week: "2026-09-07" }) });
    expect(fetchReviews).toHaveBeenCalledWith("browser-token", { week: "2026-09-07" });
  });

  it("drops a week that is not ISO-shaped", async () => {
    await ReviewsPage({ searchParams: params({ lens: "weekly", week: "../x" }) });
    expect(fetchReviews).toHaveBeenCalledWith("browser-token", {});
  });

  it("forwards an ISO day", async () => {
    await ReviewsPage({ searchParams: params({ lens: "daily", day: "2026-09-08" }) });
    expect(fetchReviews).toHaveBeenCalledTimes(1);
    expect(fetchReviews).toHaveBeenCalledWith("browser-token", { day: "2026-09-08" });
  });

  it("drops a malformed day and never forwards it", async () => {
    await ReviewsPage({ searchParams: params({ lens: "daily", day: "2026-9-8" }) });
    expect(fetchReviews).toHaveBeenNthCalledWith(1, "browser-token", {});
    for (const [, query] of fetchReviews.mock.calls) {
      expect(query).not.toEqual(expect.objectContaining({ day: "2026-9-8" }));
    }
  });

  it("reads the newest week's saved recap when no week is chosen, and never generates", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    render(await ReviewsPage({ searchParams: params({ lens: "weekly" }) }));
    expect(fetchReviews).toHaveBeenNthCalledWith(1, "browser-token", {});
    expect(fetchReviews).toHaveBeenNthCalledWith(2, "browser-token", { week: "2026-09-07" });
    expect(screen.getByRole("tab", { name: "Weekly Recap" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: "Generate weekly recap" })).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});

describe("AI Reviews page when the load fails", () => {
  it.each([
    ["an upstream error", () => Promise.reject(new Error("upstream 502: internal detail"))],
    ["a thrown fetch", () => {
      throw new TypeError("fetch failed");
    }],
  ])("renders the error and zero buttons on %s", async (_label, failure) => {
    fetchReviews.mockImplementation(failure);
    render(await ReviewsPage({ searchParams: params({ lens: "weekly", week: "2026-09-07" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent("AI Reviews did not load");
    expect(document.body).not.toHaveTextContent("internal detail");
    expect(document.body).not.toHaveTextContent("fetch failed");
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});

describe("AI Reviews page authorization", () => {
  it("does not load reviews when the session is invalid", async () => {
    authenticate.mockResolvedValue(null);
    await expect(ReviewsPage({ searchParams: params() })).rejects.toThrow("redirect:/login");
    expect(fetchReviews).not.toHaveBeenCalled();
  });

  it("redirects an ineligible account before loading", async () => {
    appRedirect.mockReturnValue("/onboarding");
    await expect(ReviewsPage({ searchParams: params() })).rejects.toThrow("redirect:/onboarding");
    expect(fetchReviews).not.toHaveBeenCalled();
  });
});
