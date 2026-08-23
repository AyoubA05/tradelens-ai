import { beforeEach, describe, expect, it, vi } from "vitest";

const authenticate = vi.fn();
const appRedirect = vi.fn();
const fetchTradeDetail = vi.fn();
const redirect = vi.fn((path: string) => {
  throw new Error(`redirect:${path}`);
});
const notFound = vi.fn(() => {
  throw new Error("notFound");
});

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ cookie: "tl_session=browser-token" }),
}));
vi.mock("next/navigation", () => ({
  redirect: (path: string) => redirect(path),
  notFound: () => notFound(),
}));
vi.mock("@/lib/auth/session", () => ({
  sessionTokenFromCookieHeader: () => "browser-token",
  authenticateSessionToken: (...args: unknown[]) => authenticate(...args),
  appLayoutRedirect: (...args: unknown[]) => appRedirect(...args),
}));
vi.mock("@/lib/app/trades", () => ({
  fetchTradeDetail: (...args: unknown[]) => fetchTradeDetail(...args),
}));
vi.mock("@/components/app/trade-detail/trade-detail-view", () => ({
  TradeDetailView: () => null,
}));

import TradeDetailPage from "@/app/app/trades/[id]/page";
import { ApiError } from "@/lib/api/client";

const params = Promise.resolve({ id: "42" });

beforeEach(() => {
  authenticate.mockReset();
  appRedirect.mockReset();
  fetchTradeDetail.mockReset();
  redirect.mockClear();
  notFound.mockClear();
});

describe("Trade Detail page authorization", () => {
  it("does not call FastAPI when the website session is invalid", async () => {
    authenticate.mockResolvedValue(null);
    await expect(TradeDetailPage({ params })).rejects.toThrow("redirect:/login");
    expect(fetchTradeDetail).not.toHaveBeenCalled();
  });

  it("does not call FastAPI before the account clears the app-surface gate", async () => {
    authenticate.mockResolvedValue({ userId: 7, appSurface: "streamlit" });
    appRedirect.mockReturnValue("/continue");
    await expect(TradeDetailPage({ params })).rejects.toThrow("redirect:/continue");
    expect(fetchTradeDetail).not.toHaveBeenCalled();
  });

  it("forwards the browser token and the numeric id only after the page-local gate passes", async () => {
    const user = { userId: 7, appSurface: "nextjs" };
    authenticate.mockResolvedValue(user);
    appRedirect.mockReturnValue(null);
    fetchTradeDetail.mockResolvedValue({ id: 42, screenshots: [] });

    await TradeDetailPage({ params });

    expect(authenticate).toHaveBeenCalledWith("browser-token");
    expect(appRedirect).toHaveBeenCalledWith(user);
    expect(fetchTradeDetail).toHaveBeenCalledWith("browser-token", 42);
  });

  it("renders not-found for a non-numeric id without calling FastAPI", async () => {
    authenticate.mockResolvedValue({ userId: 7, appSurface: "nextjs" });
    appRedirect.mockReturnValue(null);

    await expect(TradeDetailPage({ params: Promise.resolve({ id: "abc" }) })).rejects.toThrow(
      "notFound",
    );
    expect(fetchTradeDetail).not.toHaveBeenCalled();
  });

  it("renders not-found for a trade that is another owner's or does not exist (404, byte-identical)", async () => {
    authenticate.mockResolvedValue({ userId: 7, appSurface: "nextjs" });
    appRedirect.mockReturnValue(null);
    fetchTradeDetail.mockRejectedValue(new ApiError(404));

    await expect(TradeDetailPage({ params })).rejects.toThrow("notFound");
  });

  it("lets a non-404 failure reach the route's error boundary rather than becoming not-found", async () => {
    authenticate.mockResolvedValue({ userId: 7, appSurface: "nextjs" });
    appRedirect.mockReturnValue(null);
    fetchTradeDetail.mockRejectedValue(new ApiError(500));

    await expect(TradeDetailPage({ params })).rejects.toBeInstanceOf(ApiError);
    expect(notFound).not.toHaveBeenCalled();
  });
});

describe("Trade Detail page id parsing", () => {
  beforeEach(() => {
    authenticate.mockResolvedValue({ userId: 7, appSurface: "nextjs" });
    appRedirect.mockReturnValue(null);
  });

  /**
   * The page uses the same strict digit test as the relay's `parseTradeId`.
   * Bare `Number()` accepts JavaScript's other numeric literal forms, so
   * "1e3", "0x10", "0b11" and " 1" would each render a different trade under
   * a URL that does not name it, and "999999999999999999999" would survive
   * `Number.isInteger` only to be sent upstream as the literal "1e+21".
   * Ownership is enforced backend-side, so none of this is exploitable — it
   * is simply several URLs aliasing one row, and one malformed request.
   */
  it.each([
    "1e3",
    "0x10",
    "0b11",
    "0o17",
    " 1",
    "1 ",
    "+1",
    "1.0",
    "01",
    "999999999999999999999",
    "0",
    "-1",
    "",
    "Infinity",
  ])("renders not-found for %j without calling FastAPI", async (id) => {
    await expect(TradeDetailPage({ params: Promise.resolve({ id }) })).rejects.toThrow("notFound");
    expect(fetchTradeDetail).not.toHaveBeenCalled();
  });

  it("accepts a plain positive integer and forwards it as a number", async () => {
    fetchTradeDetail.mockResolvedValue({ id: 1234567890123456, screenshots: [] });
    await TradeDetailPage({ params: Promise.resolve({ id: "1234567890123456" }) });
    expect(fetchTradeDetail).toHaveBeenCalledWith("browser-token", 1234567890123456);
  });
});
