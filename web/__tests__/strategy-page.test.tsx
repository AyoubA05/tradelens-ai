import "@testing-library/jest-dom/vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { emptyStrategyFixture, strategyFixture } from "./fixtures/strategy";

const authenticate = vi.fn();
const appRedirect = vi.fn();
const fetchStrategy = vi.fn();
const redirect = vi.fn((path: string) => {
  throw new Error(`redirect:${path}`);
});

vi.mock("next/headers", () => ({
  headers: async () => new Headers({ cookie: "tl_session=browser-token" }),
}));
vi.mock("next/navigation", () => ({
  redirect: (path: string) => redirect(path),
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn() }),
}));
vi.mock("@/lib/auth/session", () => ({
  sessionTokenFromCookieHeader: () => "browser-token",
  authenticateSessionToken: (...args: unknown[]) => authenticate(...args),
  appLayoutRedirect: (...args: unknown[]) => appRedirect(...args),
}));
vi.mock("@/lib/app/strategy", () => ({
  fetchStrategy: (...args: unknown[]) => fetchStrategy(...args),
}));

import StrategyPage from "@/app/app/strategy/page";

async function renderPage() {
  return render(await StrategyPage());
}

beforeEach(() => {
  authenticate
    .mockReset()
    .mockResolvedValue({ userId: 7, appSurface: "nextjs", strategyProfileCompleted: true });
  appRedirect.mockReset().mockReturnValue(null);
  fetchStrategy.mockReset().mockResolvedValue(strategyFixture());
  redirect.mockClear();
});

describe("Strategy page authorization", () => {
  it("does not call FastAPI when the website session is invalid", async () => {
    authenticate.mockResolvedValue(null);
    await expect(StrategyPage()).rejects.toThrow("redirect:/login");
    expect(fetchStrategy).not.toHaveBeenCalled();
  });

  it("does not call FastAPI before the account clears the app-surface gate", async () => {
    appRedirect.mockReturnValue("/continue");
    await expect(StrategyPage()).rejects.toThrow("redirect:/continue");
    expect(fetchStrategy).not.toHaveBeenCalled();
  });

  it("renders for a first-run account instead of redirecting it in a loop", async () => {
    authenticate.mockResolvedValue({
      userId: 7,
      appSurface: "nextjs",
      strategyProfileCompleted: false,
    });
    fetchStrategy.mockResolvedValue(emptyStrategyFixture({ first_run: true }));
    await renderPage();
    expect(redirect).not.toHaveBeenCalled();
    expect(screen.getByTestId("first-run-banner")).toBeInTheDocument();
    expect(fetchStrategy).toHaveBeenCalledWith("browser-token");
  });
});

describe("A failed load", () => {
  beforeEach(() => {
    fetchStrategy.mockRejectedValue(new Error("connect ECONNREFUSED 10.0.0.4"));
  });

  it("renders an error, not an empty playbook", async () => {
    await renderPage();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The playbook did not load");
    expect(alert).toHaveTextContent("Nothing about your saved rules has changed.");
  });

  it("renders no editor and no Save button that could overwrite the real playbook", async () => {
    await renderPage();
    expect(screen.queryByTestId("playbook-editor")).toBeNull();
    expect(screen.queryByRole("button", { name: /save playbook/i })).toBeNull();
    expect(document.body.textContent).not.toContain("10.0.0.4");
  });
});

describe("The summary prints the server's figures", () => {
  it("shows the server's section count", async () => {
    await renderPage();
    expect(screen.getByTestId("playbook-count")).toHaveTextContent("3 of 6 sections written");
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "3");
  });

  it("prints the server's number even when the section flags would suggest another", async () => {
    // A page that recomputed completion from the flags (or the text) would
    // print 3 here. The server said 5, and the server is what the AI reads.
    fetchStrategy.mockResolvedValue(strategyFixture({ written: 5 }));
    await renderPage();
    expect(screen.getByTestId("playbook-count")).toHaveTextContent("5 of 6 sections written");
  });

  it("shows the saved facets and the active badge", async () => {
    await renderPage();
    const summary = screen.getByTestId("playbook-summary");
    expect(summary).toHaveTextContent("London Killzone Playbook");
    expect(summary).toHaveTextContent("Active");
    expect(summary).toHaveTextContent("Entry 1m");
    expect(summary).toHaveTextContent("HTF 15m");
    expect(within(summary).getByText("NQ")).toBeInTheDocument();
  });

  it("says there is no playbook yet, without a badge, when none is saved", async () => {
    fetchStrategy.mockResolvedValue(emptyStrategyFixture());
    await renderPage();
    const summary = screen.getByTestId("playbook-summary");
    expect(summary).toHaveTextContent("No playbook yet");
    expect(summary).not.toHaveTextContent("Active");
    expect(summary).toHaveTextContent(
      "Reviews and grading fall back to generic reflection until you describe how you trade.",
    );
  });
});

describe("First run and suggestions follow the server", () => {
  it("shows no first-run banner for a completed account", async () => {
    await renderPage();
    expect(screen.queryByTestId("first-run-banner")).toBeNull();
  });

  it("renders the server's rule verbatim and says it goes to Risk Rules", async () => {
    fetchStrategy.mockResolvedValue(
      strategyFixture({
        suggestions: [
          {
            field: "bias",
            user_value: "bearish",
            count: 6,
            rule: "• bias: prefer bearish (from repeated corrections in review)",
          },
        ],
      }),
    );
    await renderPage();
    const region = screen.getByTestId("insight-suggestions");
    expect(region).toHaveTextContent(
      "• bias: prefer bearish (from repeated corrections in review)",
    );
    expect(region).toHaveTextContent("Corrected 6 times in review");
    expect(region).toHaveTextContent("Risk Rules");
    expect(within(region).getByRole("button", { name: "Add to Risk Rules" })).toBeInTheDocument();
  });

  it("renders no suggestions region when there are none", async () => {
    await renderPage();
    expect(screen.queryByTestId("insight-suggestions")).toBeNull();
  });
});

describe("Strategy source hygiene", () => {
  it("does not hide literal NUL bytes in the suggestion identity separator", () => {
    const source = readFileSync(
      path.resolve(process.cwd(), "components/app/strategy/insight-suggestions.tsx"),
    );
    expect(source.includes(0)).toBe(false);
  });
});
