import "@testing-library/jest-dom/vitest";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PERIOD_PRESETS } from "@/lib/app/period";
import { analyticsFixture, emptyAnalyticsFixture } from "./fixtures/analytics";

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
