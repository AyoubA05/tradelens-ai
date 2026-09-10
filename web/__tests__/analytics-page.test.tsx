import "@testing-library/jest-dom/vitest";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERIOD_PRESETS } from "@/lib/app/period";
import {
  analyticsFixture,
  emptyAnalyticsFixture,
  undefinedValue,
  value,
} from "./fixtures/analytics";

const authenticate = vi.fn();
const appRedirect = vi.fn();
const fetchAnalytics = vi.fn();
const redirect = vi.fn((path: string) => {
  throw new Error(`redirect:${path}`);
});

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ cookie: "tl_session=browser-token" }),
}));
vi.mock("next/navigation", () => ({
  redirect: (path: string) => redirect(path),
  usePathname: () => "/app/analytics",
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));
vi.mock("@/lib/auth/session", () => ({
  sessionTokenFromCookieHeader: () => "browser-token",
  authenticateSessionToken: (...args: unknown[]) => authenticate(...args),
  appLayoutRedirect: (...args: unknown[]) => appRedirect(...args),
}));
vi.mock("@/lib/app/analytics", () => ({
  fetchAnalytics: (...args: unknown[]) => fetchAnalytics(...args),
}));

import AnalyticsPage from "@/app/app/analytics/page";

const PERIOD = { from: "2026-08-01", to: "2026-08-31" };

function searchParams(extra: Record<string, string> = {}) {
  return Promise.resolve<Record<string, string>>({ ...PERIOD, ...extra });
}

async function renderPage(extra: Record<string, string> = {}) {
  return render(await AnalyticsPage({ searchParams: searchParams(extra) }));
}

beforeEach(() => {
  authenticate.mockReset().mockResolvedValue({ userId: 7, appSurface: "nextjs" });
  appRedirect.mockReset().mockReturnValue(null);
  fetchAnalytics.mockReset().mockResolvedValue(analyticsFixture());
  redirect.mockClear();
});

describe("Analytics page authorization", () => {
  it("does not call FastAPI when the website session is invalid", async () => {
    authenticate.mockResolvedValue(null);
    await expect(AnalyticsPage({ searchParams: searchParams() })).rejects.toThrow("redirect:/login");
    expect(fetchAnalytics).not.toHaveBeenCalled();
  });

  it("does not call FastAPI before the account clears the app-surface gate", async () => {
    appRedirect.mockReturnValue("/continue");
    await expect(AnalyticsPage({ searchParams: searchParams() })).rejects.toThrow(
      "redirect:/continue",
    );
    expect(fetchAnalytics).not.toHaveBeenCalled();
  });
});

describe("Analytics page carries no date control of its own", () => {
  it("renders no date input anywhere on the page", async () => {
    const { container } = await renderPage();
    expect(container.querySelectorAll('input[type="date"]')).toHaveLength(0);
    expect(container.querySelectorAll('input[type="month"], input[type="week"]')).toHaveLength(0);
  });

  it("renders none of the global period presets, so there is no second preset row", async () => {
    await renderPage();
    for (const preset of PERIOD_PRESETS) {
      expect(screen.queryByText(preset.label)).toBeNull();
    }
  });

  it("offers no control that changes the compared-to window", async () => {
    await renderPage();
    const comparison = screen.getByTestId("analytics-comparison");
    expect(within(comparison).queryAllByRole("button")).toHaveLength(0);
    expect(within(comparison).queryAllByRole("combobox")).toHaveLength(0);
    expect(within(comparison).queryAllByRole("link")).toHaveLength(0);
    expect(comparison.querySelectorAll("input, select")).toHaveLength(0);
  });

  it("labels the comparison with the actual dates the API derived", async () => {
    await renderPage();
    expect(screen.getByTestId("analytics-comparison")).toHaveTextContent(
      "2026-07-02 → 2026-08-01",
    );
  });
});

describe("Analytics lens selection", () => {
  it("renders the performance lens region when no lens is in the URL", async () => {
    await renderPage();
    expect(screen.getByTestId("lens-performance")).toBeInTheDocument();
    expect(screen.queryByTestId("lens-timing")).toBeNull();
  });

  it("renders the lens named in the URL", async () => {
    await renderPage({ lens: "timing" });
    expect(screen.getByTestId("lens-timing")).toBeInTheDocument();
    expect(screen.queryByTestId("lens-performance")).toBeNull();
  });

  it("falls back to performance for an unknown lens rather than rendering nothing", async () => {
    await renderPage({ lens: "hour-of-day" });
    expect(screen.getByTestId("lens-performance")).toBeInTheDocument();
  });

  it("keeps the lens links in the URL so a lens is linkable", async () => {
    await renderPage({ lens: "risk", asset: "NQ" });
    const href = screen.getByRole("link", { name: "Setups" }).getAttribute("href") ?? "";
    expect(href).toContain("lens=setups");
    expect(href).toContain("asset=NQ");
    expect(href).toContain("from=2026-08-01");
  });
});

describe("Analytics filters", () => {
  it("forwards the period and the three filters to fetchAnalytics", async () => {
    await renderPage({ asset: "NQ", session: "London", strategy: "Silver bullet", debug: "1" });
    expect(fetchAnalytics).toHaveBeenCalledWith("browser-token", {
      from: "2026-08-01",
      to: "2026-08-31",
      asset: "NQ",
      session: "London",
      strategy: "Silver bullet",
    });
  });

  it("sends no filter keys at all when none are in the URL", async () => {
    await renderPage();
    expect(fetchAnalytics.mock.calls[0]?.[1]).toEqual({ from: "2026-08-01", to: "2026-08-31" });
  });

  it("round-trips an active filter back into the filter control", async () => {
    await renderPage({ asset: "NQ", strategy: "Silver bullet" });
    expect(screen.getByLabelText("Asset")).toHaveValue("NQ");
    expect(screen.getByLabelText("Strategy")).toHaveValue("Silver bullet");
  });

  it("replaces local filter text when navigation changes the measured slice", async () => {
    const view = render(await AnalyticsPage({ searchParams: searchParams({ asset: "NQ" }) }));
    expect(screen.getByLabelText("Asset")).toHaveValue("NQ");

    view.rerender(await AnalyticsPage({ searchParams: searchParams({ asset: "ES" }) }));

    // The newly fetched numbers are for ES. Leaving NQ in the field would put
    // a false label directly above them after Back/Forward navigation.
    expect(screen.getByLabelText("Asset")).toHaveValue("ES");
  });
});

describe("Analytics empty period", () => {
  it("says the period holds no trades, once, naming the period", async () => {
    fetchAnalytics.mockResolvedValue(emptyAnalyticsFixture());
    await renderPage();

    const empty = screen.getByTestId("analytics-empty");
    expect(empty).toHaveTextContent("No trades in this period");
    expect(empty).toHaveTextContent(
      "Nothing is logged between 2026-08-01 and 2026-08-31, so there is nothing to measure.",
    );
    expect(screen.getAllByTestId("analytics-empty")).toHaveLength(1);
  });

  it("renders no lens panel behind the empty state, so there is no wall of dashes", async () => {
    fetchAnalytics.mockResolvedValue(emptyAnalyticsFixture());
    await renderPage();
    for (const lens of ["performance", "risk", "timing", "setups"]) {
      expect(screen.queryByTestId(`lens-${lens}`)).toBeNull();
    }
    expect(screen.queryByTestId("analytics-comparison")).toBeNull();
  });
});

describe("Analytics fetch failure", () => {
  beforeEach(() => {
    fetchAnalytics.mockRejectedValue(new Error("connection refused at 10.0.0.4"));
  });

  it("renders an error state, not a reading of the record", async () => {
    await renderPage();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Analytics did not load");
    expect(alert).toHaveTextContent(
      "This is a loading failure, not a reading of your trades for 2026-08-01 to 2026-08-31.",
    );
  });

  it("never claims the period is empty when the fetch failed", async () => {
    await renderPage();
    expect(screen.queryByTestId("analytics-empty")).toBeNull();
    expect(screen.queryByText(/no trades in this period/i)).toBeNull();
  });

  it("renders no lens panel and does not leak the underlying failure", async () => {
    await renderPage();
    expect(screen.queryByTestId("lens-performance")).toBeNull();
    expect(document.body.textContent).not.toContain("10.0.0.4");
  });
});

describe("Each lens renders its own panel", () => {
  it("renders the performance figures inside the performance region", async () => {
    await renderPage();
    const region = screen.getByTestId("lens-performance");
    expect(within(region).getByTestId("figure-total-pnl")).toHaveTextContent("$500.00");
    expect(within(region).getByTestId("figure-win-rate")).toHaveTextContent("50.0%");
    expect(within(region).getByTestId("figure-rule-adherence")).toHaveTextContent("80.0%");
  });

  it("renders the risk figures when the risk lens is selected", async () => {
    await renderPage({ lens: "risk" });
    const region = screen.getByTestId("lens-risk");
    expect(within(region).getByTestId("figure-max-drawdown")).toHaveTextContent("-$80.00");
    expect(screen.queryByTestId("lens-performance")).toBeNull();
  });

  it("renders the timing breakdowns when the timing lens is selected", async () => {
    await renderPage({ lens: "timing" });
    const region = screen.getByTestId("lens-timing");
    expect(within(region).getByTestId("breakdown-by_day_of_week")).toBeInTheDocument();
    expect(within(region).getByTestId("breakdown-by_session")).toBeInTheDocument();
    expect(within(region).getByTestId("breakdown-by_killzone")).toBeInTheDocument();
  });

  it("renders the setups breakdowns when the setups lens is selected", async () => {
    await renderPage({ lens: "setups" });
    const region = screen.getByTestId("lens-setups");
    expect(within(region).getByTestId("breakdown-by_setup")).toBeInTheDocument();
    expect(within(region).getByTestId("setups-mistakes")).toHaveTextContent("Moved stop");
  });

  it("renders no date control of its own inside any lens", async () => {
    const { container } = await renderPage({ lens: "timing" });
    expect(container.querySelectorAll('input[type="date"]').length).toBe(0);
    for (const preset of PERIOD_PRESETS) {
      expect(screen.queryByRole("button", { name: preset.label })).toBeNull();
    }
  });
});

describe("Analytics comparison figures", () => {
  it("shows the deltas it says it compared, not just the dates", async () => {
    // The line promises "compared with the equally long period before it".
    // Printing only the dates leaves that promise unkept: the four figures
    // are fetched, typed and never rendered.
    const base = analyticsFixture();
    fetchAnalytics.mockResolvedValue({
      ...base,
      comparison: {
        period: { from: "2026-08-02", to: "2026-08-31" },
        net_pnl: value(250),
        win_rate: value(0.1),
        profit_factor: value(0.4),
        consistency: undefinedValue("undefined_no_sample"),
      },
    });
    await renderPage();

    const region = screen.getByTestId("analytics-comparison");
    expect(region).toHaveTextContent("2026-08-02");
    // `toBeVisible`, not just `toHaveTextContent`: a `hidden` element still
    // carries its text, so a content-only assertion cannot tell "rendered"
    // from "rendered but invisible" — and an invisible delta keeps the
    // promise no better than an absent one.
    const netPnl = within(region).getByTestId("comparison-net_pnl");
    expect(netPnl).toBeVisible();
    expect(netPnl).toHaveTextContent("$250.00");
    const winRate = within(region).getByTestId("comparison-win_rate");
    expect(winRate).toBeVisible();
    expect(winRate).toHaveTextContent("10.0%");
  });

  it("renders an undefined delta as a missing figure, never as no change", async () => {
    // "Nothing to compare against" is not "held steady". A 0.0 delta would
    // tell a trader their performance was unchanged against a period that
    // does not exist.
    const base = analyticsFixture();
    fetchAnalytics.mockResolvedValue({
      ...base,
      comparison: {
        period: { from: "2026-08-02", to: "2026-08-31" },
        net_pnl: undefinedValue("undefined_no_sample"),
        win_rate: undefinedValue("undefined_no_sample"),
        profit_factor: undefinedValue("undefined_no_sample"),
        consistency: undefinedValue("undefined_no_sample"),
      },
    });
    await renderPage();

    const region = screen.getByTestId("analytics-comparison");
    const missing = within(region).getByTestId("comparison-net_pnl");
    expect(missing).toBeVisible();
    expect(missing).toHaveTextContent("—");
    expect(region.textContent ?? "").not.toMatch(/\$0\.00|\b0\.0%|no change|unchanged/i);
  });
});
