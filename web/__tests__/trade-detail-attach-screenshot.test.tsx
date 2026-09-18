import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const refresh = vi.fn();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh }) }));

import { AttachScreenshot } from "@/components/app/trade-detail/attach-screenshot";

/**
 * Attaching a screenshot to a trade that already exists.
 *
 * These tests drive the REAL `attachScreenshot` helper against a mocked
 * `fetch`, so the assertion that the island reuses the existing relay
 * (`/api/trades/{id}/screenshot`) rather than inventing an endpoint is a
 * property of the run, not of a mock's shape.
 */

/** A stand-in for the PUT to R2 — jsdom has no network. */
class FakeXHR {
  static succeed = true;
  status = 200;
  upload = { onprogress: null as ((e: unknown) => void) | null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  open() {}
  setRequestHeader() {}
  send() {
    this.status = FakeXHR.succeed ? 200 : 500;
    queueMicrotask(() => this.onload?.());
  }
}

function pngFile(name = "chart.png", size = 1024): File {
  const file = new File(["x"], name, { type: "image/png" });
  Object.defineProperty(file, "size", { value: size });
  return file;
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

function relayCalls(fetchMock: ReturnType<typeof vi.fn>): string[] {
  return fetchMock.mock.calls.map((call) => JSON.parse(String((call[1] as RequestInit).body)).action);
}

describe("AttachScreenshot", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    refresh.mockClear();
    FakeXHR.succeed = true;
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const action = JSON.parse(String(init.body)).action as string;
      if (action === "presign") {
        return jsonResponse({ key: "quarantine/7/abc", url: "https://r2.example/put", max_bytes: 5_242_880 });
      }
      if (action === "finalize") {
        return jsonResponse({ id: 11, url: "https://r2.example/a.png", width: 800, height: 450, uploaded_at: null });
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("idle: invites attaching a chart to this trade, with a labelled file input", () => {
    render(<AttachScreenshot tradeId={7} />);
    expect(screen.getByText("Attach a chart screenshot to this trade.")).toBeInTheDocument();
    const input = screen.getByLabelText(/choose a screenshot/i);
    expect(input).toHaveAttribute("type", "file");
    expect(document.querySelector("img")).not.toBeInTheDocument();
  });

  it("runs presign → PUT → finalize through the existing relay, then refreshes", async () => {
    render(<AttachScreenshot tradeId={7} />);
    fireEvent.change(screen.getByLabelText(/choose a screenshot/i), {
      target: { files: [pngFile()] },
    });

    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    expect(relayCalls(fetchMock)).toEqual(["presign", "finalize"]);
    for (const call of fetchMock.mock.calls) {
      expect(call[0]).toBe("/api/trades/7/screenshot");
    }
    expect(document.querySelector("img")).not.toBeInTheDocument();
  });

  it("refuses a file the preflight rejects without sending a byte", async () => {
    render(<AttachScreenshot tradeId={7} />);
    const pdf = new File(["x"], "notes.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/choose a screenshot/i), { target: { files: [pdf] } });

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Only PNG, JPEG and WebP screenshots can be uploaded.",
      ),
    );
    expect(fetchMock).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
    expect(document.querySelector("img")).not.toBeInTheDocument();
  });

  it("states plainly that a relay failure left the gallery untouched, and does not refresh", async () => {
    fetchMock.mockImplementation(async () => jsonResponse({ detail: "boom" }, 500));
    render(<AttachScreenshot tradeId={7} />);
    fireEvent.change(screen.getByLabelText(/choose a screenshot/i), {
      target: { files: [pngFile()] },
    });

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "That screenshot was not attached. Try again.",
      ),
    );
    expect(refresh).not.toHaveBeenCalled();
    expect(document.querySelector("img")).not.toBeInTheDocument();
  });

  it("abandons the quarantine object when the upload itself fails", async () => {
    FakeXHR.succeed = false;
    render(<AttachScreenshot tradeId={7} />);
    fireEvent.change(screen.getByLabelText(/choose a screenshot/i), {
      target: { files: [pngFile()] },
    });

    await waitFor(() => expect(relayCalls(fetchMock)).toContain("abandon"));
    expect(relayCalls(fetchMock)).not.toContain("finalize");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("sends one sequence when the file is picked twice in a row", async () => {
    render(<AttachScreenshot tradeId={7} />);
    const input = screen.getByLabelText(/choose a screenshot/i);
    fireEvent.change(input, { target: { files: [pngFile()] } });
    fireEvent.change(input, { target: { files: [pngFile("chart2.png")] } });

    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    expect(relayCalls(fetchMock).filter((action) => action === "presign")).toHaveLength(1);
  });
});
