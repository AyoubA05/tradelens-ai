import { beforeEach, describe, expect, it, vi } from "vitest";

const authenticate = vi.fn();
const appRedirect = vi.fn();
const redirect = vi.fn((path: string) => {
  throw new Error(`redirect:${path}`);
});

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ cookie: "tl_session=browser-token" }),
}));
vi.mock("next/navigation", () => ({
  redirect: (path: string) => redirect(path),
}));
vi.mock("@/lib/auth/session", () => ({
  sessionTokenFromCookieHeader: () => "browser-token",
  authenticateSessionToken: (...args: unknown[]) => authenticate(...args),
  appLayoutRedirect: (...args: unknown[]) => appRedirect(...args),
}));
vi.mock("@/components/app/new-trade/new-trade-form", () => ({
  NewTradeForm: () => null,
}));

import NewTradePage from "@/app/app/trades/new/page";

/**
 * New Trade page authorization (Task C3, global rule "every protected page
 * authenticates before any backend side effect").
 *
 * This page makes no fetch of its own — the form's submit reaches the
 * backend through `/api/trades/create`, which re-checks the same gate. What
 * this test covers is narrower and just as load-bearing: an ineligible or
 * unauthenticated request never renders the form at all, matching the same
 * page-local-gate pattern `trade-detail-page-auth.test.tsx` pins for Trade
 * Detail — a parent layout's redirect is defence, never a precondition.
 */
describe("New Trade page authorization", () => {
  beforeEach(() => {
    authenticate.mockReset();
    appRedirect.mockReset();
    redirect.mockClear();
  });

  it("redirects to login when the website session is invalid", async () => {
    authenticate.mockResolvedValue(null);
    await expect(NewTradePage()).rejects.toThrow("redirect:/login");
  });

  it("redirects when the account has not cleared the app-surface/onboarding gate", async () => {
    authenticate.mockResolvedValue({ userId: 7, appSurface: "streamlit" });
    appRedirect.mockReturnValue("/continue");
    await expect(NewTradePage()).rejects.toThrow("redirect:/continue");
  });

  it("renders for an eligible, authenticated account", async () => {
    const user = { userId: 7, appSurface: "nextjs" };
    authenticate.mockResolvedValue(user);
    appRedirect.mockReturnValue(null);

    const result = await NewTradePage();

    expect(authenticate).toHaveBeenCalledWith("browser-token");
    expect(appRedirect).toHaveBeenCalledWith(user);
    expect(result).toBeTruthy();
  });
});
