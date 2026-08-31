import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

import { ScreenshotUpload } from "@/components/app/new-trade/screenshot-upload";
import { NewTradeForm } from "@/components/app/new-trade/new-trade-form";

/**
 * Tasks D1 and D2 — the upload island, and the partial-failure interaction.
 *
 * The load-bearing assertions here are the ones about what a trader is
 * told. A trade that was created is durable; nothing after that point may
 * say it was not, and nothing may offer a path back through create.
 */

function pngFile(name = "chart.png", size = 1234): File {
  return { name, type: "image/png", size } as unknown as File;
}

beforeEach(() => {
  push.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ScreenshotUpload", () => {
  it("treats no screenshot as an ordinary state, with no frame and no image", () => {
    const { container } = render(
      <ScreenshotUpload file={null} onSelect={() => {}} status={{ kind: "idle" }} />,
    );
    expect(screen.getByText(/complete record/i)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the picked file's name and offers Remove", () => {
    const onSelect = vi.fn();
    render(
      <ScreenshotUpload file={pngFile()} onSelect={onSelect} status={{ kind: "idle" }} />,
    );
    expect(screen.getByText("chart.png")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /remove/i }));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("wraps a long unbroken filename rather than letting it overflow", () => {
    const name = `${"a".repeat(120)}.png`;
    render(
      <ScreenshotUpload file={pngFile(name)} onSelect={() => {}} status={{ kind: "idle" }} />,
    );
    const line = screen.getByText(name).closest("p");
    expect(line?.className).toContain("break-all");
    expect(line?.className).toContain("min-w-0");
  });

  it("reports upload progress and hides Remove while busy", () => {
    render(
      <ScreenshotUpload
        file={pngFile()}
        onSelect={() => {}}
        status={{ kind: "busy", phase: "uploading", progress: 0.42 }}
      />,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "42");
    expect(screen.queryByRole("button", { name: /remove/i })).not.toBeInTheDocument();
  });

  it("keeps the file control a full-size tap target, usable one-handed", () => {
    render(<ScreenshotUpload file={null} onSelect={() => {}} status={{ kind: "idle" }} />);
    const label = screen.getByText(/choose a screenshot/i);
    expect(label.className).toContain("min-h-[44px]");
  });

  it("shows a problem as an alert without implying anything about the trade", () => {
    render(
      <ScreenshotUpload
        file={pngFile()}
        onSelect={() => {}}
        status={{ kind: "problem", message: "The trade is unchanged — try again." }}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/trade is unchanged/i);
  });
});

/** Fills the minimum the form needs; the server is the real gate anyway. */
function fillMinimum() {
  fireEvent.change(screen.getByLabelText("Asset"), { target: { value: "NQ" } });
}

function stubFetch(handler: (url: string, init?: RequestInit) => unknown) {
  const fetchMock = vi.fn(async (url: unknown, init?: unknown) =>
    handler(String(url), init as RequestInit),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function json(status: number, body: unknown = {}) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

async function submitWithScreenshot() {
  render(<NewTradeForm />);
  fillMinimum();
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  Object.defineProperty(input, "files", { value: [pngFile()], configurable: true });
  fireEvent.change(input);
  fireEvent.click(screen.getByRole("button", { name: /save trade/i }));
}

describe("NewTradeForm — partial failure (Task D2)", () => {
  it("says the trade is saved when the screenshot fails, and never that nothing was saved", async () => {
    stubFetch((url) => {
      if (url.endsWith("/api/trades/create")) return json(200, { id: 77, duplicate_of: null });
      if (url.endsWith("/api/trades/77/screenshot")) return json(502);
      throw new Error(`unexpected ${url}`);
    });
    await submitWithScreenshot();

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByText(/your trade is saved/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing was lost/i)).toBeInTheDocument();
    expect(screen.queryByText(/nothing was recorded/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/did not save/i)).not.toBeInTheDocument();
    // No route back through create — that is the only action here that
    // could look like producing a second trade.
    expect(screen.queryByRole("button", { name: /save trade/i })).not.toBeInTheDocument();
  });

  it("retries against the existing trade and never calls create a second time", async () => {
    let finalizeAttempts = 0;
    const fetchMock = stubFetch((url, init) => {
      if (url.endsWith("/api/trades/create")) return json(200, { id: 77, duplicate_of: null });
      const body = JSON.parse((init?.body as string) ?? "{}");
      if (body.action === "presign")
        return json(200, { url: "https://r2.test/put", key: "k", max_bytes: 99999, expires_in: 1 });
      if (body.action === "finalize")
        return ++finalizeAttempts === 1 ? json(502) : json(201, { id: 3 });
      return json(204);
    });
    // The real PUT would use XMLHttpRequest; jsdom has none that reaches R2.
    vi.stubGlobal(
      "XMLHttpRequest",
      class {
        status = 200;
        upload = {} as { onprogress?: () => void };
        onload: (() => void) | null = null;
        open() {}
        setRequestHeader() {}
        send() {
          this.onload?.();
        }
      },
    );

    await submitWithScreenshot();
    await waitFor(() => expect(screen.getByText(/your trade is saved/i)).toBeInTheDocument());

    const createCallsBefore = fetchMock.mock.calls.filter((c) =>
      String(c[0]).endsWith("/api/trades/create"),
    ).length;
    fireEvent.click(screen.getByRole("button", { name: /try the upload again/i }));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/app/trades/77"));
    const createCallsAfter = fetchMock.mock.calls.filter((c) =>
      String(c[0]).endsWith("/api/trades/create"),
    ).length;
    expect(createCallsAfter).toBe(createCallsBefore);
    // Every retry request named the trade that already exists. The one
    // exception is Task D3's draft-load `GET /api/trades/draft` on mount,
    // which runs independently of and before this create/retry sequence.
    for (const call of fetchMock.mock.calls) {
      const url = String(call[0]);
      if (url === "/api/trades/draft" || url === "/api/trades/create") continue;
      expect(url).toBe("/api/trades/77/screenshot");
    }
  });

  it("lets the trader continue to the saved trade without the screenshot", async () => {
    stubFetch((url) => {
      if (url.endsWith("/api/trades/create")) return json(200, { id: 77, duplicate_of: null });
      return json(502);
    });
    await submitWithScreenshot();
    await waitFor(() => expect(screen.getByText(/your trade is saved/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /without a screenshot/i }));
    expect(push).toHaveBeenCalledWith("/app/trades/77");
  });

  it("still says nothing was saved when creation itself failed", async () => {
    stubFetch(() => json(422, {}));
    render(<NewTradeForm />);
    fillMinimum();
    fireEvent.click(screen.getByRole("button", { name: /save trade/i }));
    await waitFor(() => expect(screen.getByText(/nothing was recorded/i)).toBeInTheDocument());
    expect(screen.queryByText(/your trade is saved/i)).not.toBeInTheDocument();
  });
});
