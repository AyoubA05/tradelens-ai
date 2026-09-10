import { beforeEach, describe, expect, it, vi } from "vitest";

const authenticate = vi.fn();
const appRedirect = vi.fn();
const fetchOverview = vi.fn();
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
vi.mock("@/lib/app/overview", () => ({
  fetchOverview: (...args: unknown[]) => fetchOverview(...args),
}));
vi.mock("@/components/app/overview/sections", () => ({ OverviewSections: () => null }));

import OverviewPage from "@/app/app/page";

const params = Promise.resolve<Record<string, string>>({
  from: "2026-08-01",
  to: "2026-08-31",
});

beforeEach(() => {
  authenticate.mockReset();
  appRedirect.mockReset();
  fetchOverview.mockReset();
  redirect.mockClear();
});

describe("Overview page authorization", () => {
  it("does not call FastAPI when the website session is invalid", async () => {
    authenticate.mockResolvedValue(null);

    await expect(OverviewPage({ searchParams: params })).rejects.toThrow("redirect:/login");
    expect(fetchOverview).not.toHaveBeenCalled();
  });

  it("does not call FastAPI before the account clears the app-surface gate", async () => {
    const user = { userId: 7, appSurface: "streamlit" };
    authenticate.mockResolvedValue(user);
    appRedirect.mockReturnValue("/continue");

    await expect(OverviewPage({ searchParams: params })).rejects.toThrow("redirect:/continue");
    expect(fetchOverview).not.toHaveBeenCalled();
  });

  it("forwards the browser token only after the page-local gate passes", async () => {
    const user = { userId: 7, appSurface: "nextjs", strategyProfileCompleted: true };
    authenticate.mockResolvedValue(user);
    appRedirect.mockReturnValue(null);
    fetchOverview.mockResolvedValue({});

    await OverviewPage({ searchParams: params });

    expect(authenticate).toHaveBeenCalledWith("browser-token");
    expect(appRedirect).toHaveBeenCalledWith(user);
    expect(fetchOverview).toHaveBeenCalledOnce();
    expect(fetchOverview.mock.calls[0]?.[0]).toBe("browser-token");
  });
});

describe("Overview first-run routing", () => {
  it("sends an account with no playbook step to /app/strategy before any fetch", async () => {
    authenticate.mockResolvedValue({
      userId: 7,
      appSurface: "nextjs",
      strategyProfileCompleted: false,
    });
    appRedirect.mockReturnValue(null);

    await expect(OverviewPage({ searchParams: params })).rejects.toThrow(
      "redirect:/app/strategy",
    );
    expect(fetchOverview).not.toHaveBeenCalled();
  });

  it("lets a completed account through to its Overview", async () => {
    authenticate.mockResolvedValue({
      userId: 7,
      appSurface: "nextjs",
      strategyProfileCompleted: true,
    });
    appRedirect.mockReturnValue(null);
    fetchOverview.mockResolvedValue({});

    await OverviewPage({ searchParams: params });
    expect(redirect).not.toHaveBeenCalled();
    expect(fetchOverview).toHaveBeenCalledOnce();
  });

  it("never reads first-run state from the URL", async () => {
    authenticate.mockResolvedValue({
      userId: 7,
      appSurface: "nextjs",
      strategyProfileCompleted: false,
    });
    appRedirect.mockReturnValue(null);
    const tampered = Promise.resolve<Record<string, string>>({
      from: "2026-08-01",
      to: "2026-08-31",
      first_run: "0",
      completed: "1",
      strategyProfileCompleted: "true",
    });

    await expect(OverviewPage({ searchParams: tampered })).rejects.toThrow(
      "redirect:/app/strategy",
    );
    expect(fetchOverview).not.toHaveBeenCalled();
  });

  it("sends an ineligible account to its own gate first, not to the playbook", async () => {
    authenticate.mockResolvedValue({
      userId: 7,
      appSurface: "streamlit",
      strategyProfileCompleted: false,
    });
    appRedirect.mockReturnValue("/continue");

    await expect(OverviewPage({ searchParams: params })).rejects.toThrow("redirect:/continue");
    expect(redirect).toHaveBeenCalledTimes(1);
  });
});
