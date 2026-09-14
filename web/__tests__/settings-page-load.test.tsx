import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The Settings page as a whole, around its one fetch.
 *
 * A failed load must render the error state and NO controls: the Danger Zone
 * and the data tools are never offered over a picture of the account that did
 * not load. The successful load is the contrast, so the test cannot pass by
 * rendering nothing at all.
 */

const authenticate = vi.fn();
const appRedirect = vi.fn();
const fetchSettings = vi.fn();
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
vi.mock("@/lib/app/settings", () => ({
  fetchSettings: (...args: unknown[]) => fetchSettings(...args),
}));

import SettingsPage from "@/app/app/settings/page";

function settings(overrides: { trade_count?: number; sample_count?: number } = {}) {
  return {
    account: { username: "trader", email: "trader@example.test", email_verified: true },
    reset_email_configured: true,
    timezone: { current: "UTC", options: ["America/New_York", "UTC"] },
    ai: { state: "enabled" as const },
    demo_mode: false,
    data: {
      trade_count: overrides.trade_count ?? 12,
      sample_count: overrides.sample_count ?? 0,
      csv_columns: ["trade_date"],
      max_import_rows: 5000,
    },
    cost: { month: "2026-09", total_usd: 0, rows: [] },
  };
}

beforeEach(() => {
  authenticate.mockReset().mockResolvedValue({ userId: 7, appSurface: "nextjs" });
  appRedirect.mockReset().mockReturnValue(null);
  fetchSettings.mockReset().mockResolvedValue(settings());
  redirect.mockClear();
});

describe("Settings page when the initial load fails", () => {
  it.each([
    ["an upstream error", () => Promise.reject(new Error("upstream 502: internal detail"))],
    ["a thrown fetch", () => {
      throw new TypeError("fetch failed");
    }],
  ])("renders the error state and no controls on %s", async (_label, failure) => {
    fetchSettings.mockImplementation(failure);
    render(await SettingsPage());

    expect(fetchSettings).toHaveBeenCalledWith("browser-token");
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Settings did not load");
    expect(alert).toHaveTextContent("Nothing about your account or your data has changed.");
    // The upstream message is never surfaced.
    expect(document.body).not.toHaveTextContent("internal detail");
    expect(document.body).not.toHaveTextContent("fetch failed");

    // No destructive or data control is offered over a failed load.
    expect(screen.queryByRole("heading", { name: "Danger Zone" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Data" })).toBeNull();
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /export/i })).toBeNull();
    expect(screen.queryByLabelText(/import trades from csv/i)).toBeNull();
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});

describe("Settings page when the initial load succeeds (contrast)", () => {
  it("renders every section and no error state", async () => {
    render(await SettingsPage());
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("heading", { name: "Danger Zone" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export 12 trades as CSV" })).toBeInTheDocument();
  });

  it("shows the server's new counts after a refresh, not the section's stale state", async () => {
    // The page keys DataSection by its counts, so a router refresh that brings
    // new counts replaces the section's local state instead of being ignored.
    const view = render(await SettingsPage());
    expect(screen.getByRole("button", { name: "Export 12 trades as CSV" })).toBeInTheDocument();
    fetchSettings.mockResolvedValue(settings({ trade_count: 0 }));
    view.rerender(await SettingsPage());
    expect(screen.getByRole("button", { name: "Export 0 trades as CSV" })).toBeInTheDocument();
  });
});

describe("Settings page authorization", () => {
  it("does not load settings when the session is invalid", async () => {
    authenticate.mockResolvedValue(null);
    await expect(SettingsPage()).rejects.toThrow("redirect:/login");
    expect(fetchSettings).not.toHaveBeenCalled();
  });
});
