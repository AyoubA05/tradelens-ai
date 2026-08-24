import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const authenticate = vi.fn();
const appRedirect = vi.fn();
const fetchTrades = vi.fn();
const fetchOverview = vi.fn();
const summaryPanel = vi.fn((props: unknown) => {
  void props;
  return null;
});
const redirect = vi.fn((path: string) => {
  throw new Error(`redirect:${path}`);
});

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ cookie: "tl_session=browser-token" }),
}));
vi.mock("next/navigation", () => ({ redirect: (path: string) => redirect(path) }));
vi.mock("@/lib/auth/session", () => ({
  sessionTokenFromCookieHeader: () => "browser-token",
  authenticateSessionToken: (...args: unknown[]) => authenticate(...args),
  appLayoutRedirect: (...args: unknown[]) => appRedirect(...args),
}));
vi.mock("@/lib/app/trades", () => ({
  fetchTrades: (...args: unknown[]) => fetchTrades(...args),
  DEFAULT_TRADES_LIMIT: 25,
}));
vi.mock("@/lib/app/overview", () => ({
  fetchOverview: (...args: unknown[]) => fetchOverview(...args),
}));
vi.mock("@/components/app/trades/filter-bar", () => ({ FilterBar: () => null }));
vi.mock("@/components/app/trades/journal-calendar", () => ({ JournalCalendar: () => null }));
vi.mock("@/components/app/trades/trades-table", () => ({ TradesTable: () => null }));
vi.mock("@/components/app/trades/pagination", () => ({ Pagination: () => null }));
vi.mock("@/components/app/trades/summary-panel", () => ({
  TradeSummaryPanel: (props: unknown) => summaryPanel(props),
}));

import JournalPage from "@/app/app/journal/page";

const params = Promise.resolve<Record<string, string>>({
  from: "2026-08-01",
  to: "2026-08-31",
});

beforeEach(() => {
  authenticate.mockReset();
  appRedirect.mockReset();
  fetchTrades.mockReset();
  fetchOverview.mockReset();
  summaryPanel.mockClear();
  redirect.mockClear();
});

describe("Journal page authorization", () => {
  it("does not call FastAPI when the website session is invalid", async () => {
    authenticate.mockResolvedValue(null);

    await expect(JournalPage({ searchParams: params })).rejects.toThrow("redirect:/login");
    expect(fetchTrades).not.toHaveBeenCalled();
    expect(fetchOverview).not.toHaveBeenCalled();
  });

  it("does not call FastAPI before the account clears the app-surface gate", async () => {
    const user = { userId: 7, appSurface: "streamlit" };
    authenticate.mockResolvedValue(user);
    appRedirect.mockReturnValue("/continue");

    await expect(JournalPage({ searchParams: params })).rejects.toThrow("redirect:/continue");
    expect(fetchTrades).not.toHaveBeenCalled();
    expect(fetchOverview).not.toHaveBeenCalled();
  });

  it("forwards the browser token only after the page-local gate passes", async () => {
    const user = { userId: 7, appSurface: "nextjs" };
    authenticate.mockResolvedValue(user);
    appRedirect.mockReturnValue(null);
    fetchTrades.mockResolvedValue({ trades: [], total: 0, limit: 25, offset: 0 });
    fetchOverview.mockResolvedValue({ calendar: {}, period: {}, sample: { show_summary: false } });

    await JournalPage({ searchParams: params });

    expect(authenticate).toHaveBeenCalledWith("browser-token");
    expect(appRedirect).toHaveBeenCalledWith(user);
    expect(fetchTrades.mock.calls[0]?.[0]).toBe("browser-token");
    expect(fetchOverview.mock.calls[0]?.[0]).toBe("browser-token");
  });

  it("reads filters and offset from the URL and forwards them to fetchTrades", async () => {
    const user = { userId: 7, appSurface: "nextjs" };
    authenticate.mockResolvedValue(user);
    appRedirect.mockReturnValue(null);
    fetchTrades.mockResolvedValue({ trades: [], total: 0, limit: 25, offset: 25 });
    fetchOverview.mockResolvedValue({ calendar: {}, period: {}, sample: { show_summary: false } });

    await JournalPage({
      searchParams: Promise.resolve({
        from: "2026-08-01",
        to: "2026-08-31",
        asset: "NQ",
        offset: "25",
        debug: "1",
      }),
    });

    const [, args] = fetchTrades.mock.calls[0];
    expect(args.filters).toEqual({ asset: "NQ" });
    expect(args.offset).toBe(25);
  });

  it("gives the AI panel the same period, filters, and filtered total as the table", async () => {
    const user = { userId: 7, appSurface: "nextjs" };
    authenticate.mockResolvedValue(user);
    appRedirect.mockReturnValue(null);
    fetchTrades.mockResolvedValue({ trades: [{ id: 1 }], total: 7, limit: 25, offset: 0 });
    fetchOverview.mockResolvedValue({ calendar: {}, period: {}, sample: { show_summary: true } });

    render(
      await JournalPage({
        searchParams: Promise.resolve({
          from: "2026-08-01",
          to: "2026-08-31",
          asset: "NQ",
          result: "Win",
        }),
      }),
    );

    expect(summaryPanel).toHaveBeenCalledWith({
      period: expect.objectContaining({ from: "2026-08-01", to: "2026-08-31" }),
      filters: { asset: "NQ", result: "Win" },
      tradeCount: 7,
    });
  });
});
