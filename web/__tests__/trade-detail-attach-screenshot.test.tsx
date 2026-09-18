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

function relayBodies(fetchMock: ReturnType<typeof vi.fn>): Array<Record<string, unknown>> {
  return fetchMock.mock.calls.map(
    (call) => JSON.parse(String((call[1] as RequestInit).body)) as Record<string, unknown>,
  );
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
  /**
   * The local preflight is the island's own gate, not the helper's.
   *
   * `attachScreenshot` re-runs the same type check internally, so asserting
   * only "message shown, fetch not called" cannot tell the two apart — the
   * helper would produce exactly that too. What the island's own call buys
   * is that the refusal is IMMEDIATE: the trader never sees a "Preparing the
   * upload…" state for a file that was never going to leave the browser.
   * Asserting synchronously, before any microtask can run, is what pins it.
   */
  it("refuses a wrong-type file synchronously, with no busy state and no request", async () => {
    render(<AttachScreenshot tradeId={7} />);
    const pdf = new File(["x"], "notes.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/choose a screenshot/i), { target: { files: [pdf] } });

    // No `waitFor`: the message must already be on screen.
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Only PNG, JPEG and WebP screenshots can be uploaded.",
    );
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.queryByText("Preparing the upload…")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    // And nothing starts afterwards either.
    await Promise.resolve();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(refresh).not.toHaveBeenCalled();
  });

  /**
   * Size is the server's rule, not ours.
   *
   * `screenshotPreflight` only enforces a byte cap when it is given one, and
   * the island passes `null` because `max_bytes` is not known until presign
   * answers. So an oversized PNG legitimately reaches presign — and is then
   * refused against the server's own number, with the key abandoned so the
   * quarantine object is not orphaned. The bytes themselves never go out.
   */
  it("refuses an oversized file against the server's own limit and abandons the key", async () => {
    render(<AttachScreenshot tradeId={7} />);
    fireEvent.change(screen.getByLabelText(/choose a screenshot/i), {
      target: { files: [pngFile("huge.png", 6_000_000)] },
    });

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "That file is larger than the 5 MB limit, so uploading it would not succeed.",
      ),
    );
    expect(relayCalls(fetchMock)).toEqual(["presign", "abandon"]);
    expect(relayBodies(fetchMock)[1]).toEqual({ action: "abandon", key: "quarantine/7/abc" });
    expect(refresh).not.toHaveBeenCalled();
    expect(document.querySelector("img")).not.toBeInTheDocument();
  });

  /**
   * A presigned key that finalize could not resolve must not be orphaned.
   *
   * `attachScreenshot` hands back `pendingKey` rather than abandoning it
   * itself (the object may still be finalizable), so cleanup is the island's
   * job. Without it the R2 object has no download path, no `screenshots` row
   * and no name anyone else can ever produce — it would simply sit there.
   */
  it("abandons the presigned key when finalize fails after presign succeeded", async () => {
    fetchMock.mockImplementation(async (_url: string, init: RequestInit) => {
      const action = JSON.parse(String(init.body)).action as string;
      if (action === "presign") {
        return jsonResponse({ key: "quarantine/7/abc", url: "https://r2.example/put", max_bytes: 5_242_880 });
      }
      if (action === "finalize") return jsonResponse({ detail: "boom" }, 500);
      return jsonResponse({});
    });
    render(<AttachScreenshot tradeId={7} />);
    fireEvent.change(screen.getByLabelText(/choose a screenshot/i), {
      target: { files: [pngFile()] },
    });

    await waitFor(() => expect(relayCalls(fetchMock)).toContain("abandon"));
    const abandon = relayBodies(fetchMock).find((body) => body.action === "abandon");
    expect(abandon).toEqual({ action: "abandon", key: "quarantine/7/abc" });
    expect(relayCalls(fetchMock)).toEqual(["presign", "finalize", "abandon"]);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "That screenshot was not attached. Try again.",
    );
    expect(refresh).not.toHaveBeenCalled();
  });
});
