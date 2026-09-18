import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The Overview asset filter.
 *
 * The financial property under test is that a filter narrows what it claims to
 * narrow and nothing else. A scope with no trades in it is a real view of a
 * real account — it must say so in words, not render a strip of zeros that
 * reads as a flat month.
 */

const push = vi.fn();
const authenticate = vi.fn();
const appRedirect = vi.fn();
const fetchOverview = vi.fn();
const redirect = vi.fn((path: string) => {
  throw new Error(`redirect:${path}`);
});

let searchParams = new URLSearchParams("from=2026-09-01&to=2026-09-30");

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ cookie: "tl_session=browser-token" }),
}));
vi.mock("next/navigation", () => ({
  redirect: (path: string) => redirect(path),
  usePathname: () => "/app",
  useSearchParams: () => searchParams,
  useRouter: () => ({ push, replace: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/lib/auth/session", () => ({
  sessionTokenFromCookieHeader: () => "browser-token",
  authenticateSessionToken: (...args: unknown[]) => authenticate(...args),
  appLayoutRedirect: (...args: unknown[]) => appRedirect(...args),
}));
vi.mock("@/lib/app/overview", () => ({
  fetchOverview: (...args: unknown[]) => fetchOverview(...args),
}));
vi.mock("@/components/app/overview/sections", () => ({
  OverviewSections: () => <div data-testid="overview-sections">KPI strip</div>,
}));

import { AssetFilter } from "@/components/app/overview/asset-filter";
import OverviewPage from "@/app/app/page";

function payload(
  filters: { asset: string | null; available_assets: string[] },
  trades = 3,
) {
  return { filters, kpi: { trades } };
}

beforeEach(() => {
  push.mockReset();
  authenticate.mockReset().mockResolvedValue({
    userId: 7,
    appSurface: "nextjs",
    strategyProfileCompleted: true,
  });
  appRedirect.mockReset().mockReturnValue(null);
  fetchOverview.mockReset().mockResolvedValue(payload({ asset: null, available_assets: [] }));
  redirect.mockClear();
  searchParams = new URLSearchParams("from=2026-09-01&to=2026-09-30");
});

describe("AssetFilter control", () => {
  it("offers every instrument the owner traded, plus an unscoped option", () => {
    render(<AssetFilter asset={null} availableAssets={["ES", "NQ"]} />);
    const select = screen.getByLabelText("Filter by asset");
    expect(
      [...select.querySelectorAll("option")].map((o) => o.textContent),
    ).toEqual(["All assets", "ES", "NQ"]);
    expect(screen.queryByText(/showing/i)).not.toBeInTheDocument();
  });

  it("navigates to the scoped URL when an instrument is chosen", () => {
    render(<AssetFilter asset={null} availableAssets={["ES", "NQ"]} />);
    fireEvent.change(screen.getByLabelText("Filter by asset"), { target: { value: "NQ" } });
    expect(push).toHaveBeenCalledTimes(1);
    const [url] = push.mock.calls[0];
    const [path, query] = (url as string).split("?");
    expect(path).toBe("/app");
    const next = new URLSearchParams(query);
    expect(next.get("asset")).toBe("NQ");
    // The period is a separate lens and must survive the change of scope.
    expect(next.get("from")).toBe("2026-09-01");
    expect(next.get("to")).toBe("2026-09-30");
  });

  it("drops the parameter entirely when the scope is cleared", () => {
    searchParams = new URLSearchParams("from=2026-09-01&to=2026-09-30&asset=NQ");
    render(<AssetFilter asset="NQ" availableAssets={["ES", "NQ"]} />);
    fireEvent.change(screen.getByLabelText("Filter by asset"), { target: { value: "" } });
    const [url] = push.mock.calls[0];
    expect(new URLSearchParams((url as string).split("?")[1]).has("asset")).toBe(false);
  });

  it("renders nothing when the owner has traded nothing in the period", () => {
    const { container } = render(<AssetFilter asset={null} availableAssets={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("Overview page under an asset scope", () => {
  it("says the scope is empty instead of showing a strip of zeros", async () => {
    fetchOverview.mockResolvedValue(payload({ asset: "NQ", available_assets: ["ES", "NQ"] }, 0));
    render(await OverviewPage({ searchParams: Promise.resolve({ asset: "NQ" }) }));

    expect(screen.getByText("No trades for NQ")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Show all assets" })).toBeInTheDocument();
    // The cardinal assertion: zeros are never rendered for an empty scope.
    expect(screen.queryByTestId("overview-sections")).not.toBeInTheDocument();
  });

  it("renders the figures when the scope has trades in it", async () => {
    fetchOverview.mockResolvedValue(payload({ asset: "NQ", available_assets: ["NQ"] }, 3));
    render(await OverviewPage({ searchParams: Promise.resolve({ asset: "NQ" }) }));
    expect(screen.getByTestId("overview-sections")).toBeInTheDocument();
    expect(screen.queryByText(/no trades for/i)).not.toBeInTheDocument();
  });

  it("forwards a real instrument symbol to the fetch", async () => {
    await OverviewPage({ searchParams: Promise.resolve({ asset: "NQ" }) });
    expect(fetchOverview.mock.calls[0][2]).toBe("NQ");
  });

  it.each([
    ["absent", {}],
    ["empty", { asset: "" }],
    ["whitespace", { asset: "   " }],
    ["a markup payload", { asset: "<script>" }],
    ["an array", { asset: ["NQ", "ES"] }],
  ])("does not forward an asset that is %s", async (_label, params) => {
    await OverviewPage({
      searchParams: Promise.resolve(params as Record<string, string | string[] | undefined>),
    });
    expect(fetchOverview.mock.calls[0][2]).toBeUndefined();
  });
});
