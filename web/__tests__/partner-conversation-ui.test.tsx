import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PartnerConversation } from "@/components/app/partner/conversation";

/**
 * The conversation island. What matters is what it SENDS: the transcript
 * exactly as the server signed it, the same client turn id on a retry, and
 * the screenshot flag only where one was asked for.
 */

const fetchMock = vi.fn();

function turn(idx: number, role: "user" | "assistant", text: string) {
  return { idx, role, text, iat: 1_700_000_000 + idx, mac: `${idx}`.repeat(64).slice(0, 64) };
}

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

function fail(status: number, detail?: unknown) {
  return {
    ok: false,
    status,
    json: async () => (detail === undefined ? { ok: false } : { ok: false, detail }),
  };
}

function reply(conv: string, at: number, text = "Because.") {
  return {
    conversation_id: conv,
    turns: [turn(at, "user", "Why?"), turn(at + 1, "assistant", text)],
    evidence: [],
    screenshot_attached: false,
  };
}

function sent(n: number) {
  return JSON.parse(fetchMock.mock.calls[n][1].body as string);
}

function renderIt(props: Partial<Parameters<typeof PartnerConversation>[0]> = {}) {
  return render(
    <PartnerConversation
      endpoint="/api/partner/turns"
      intro="Intro copy."
      placeholder="Ask"
      {...props}
    />,
  );
}

async function ask(text: string) {
  fireEvent.change(screen.getByRole("textbox"), { target: { value: text } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /^ask$/i }));
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("what a turn sends", () => {
  it("starts with no conversation id and an empty transcript", async () => {
    fetchMock.mockResolvedValue(ok(reply("c-1", 0)));
    renderIt();
    await ask("Why?");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/partner/turns");
    const body = sent(0);
    expect(body.conversation_id).toBeNull();
    expect(body.transcript).toEqual([]);
    expect(body.client_turn_id.length).toBeGreaterThanOrEqual(16);
    expect(body).not.toHaveProperty("include_screenshot");
  });

  it("returns the signed turns byte for byte on the next question", async () => {
    const first = reply("c-1", 0);
    fetchMock.mockResolvedValueOnce(ok(first)).mockResolvedValueOnce(ok(reply("c-1", 2)));
    renderIt();
    await ask("Why?");
    await ask("And then?");
    const body = sent(1);
    expect(body.conversation_id).toBe("c-1");
    expect(body.transcript).toEqual(first.turns);
    expect(body.client_turn_id).not.toBe(sent(0).client_turn_id);
  });

  it("sends the screenshot flag only when the caller set one", async () => {
    fetchMock.mockResolvedValue(ok(reply("c-1", 0)));
    renderIt({ endpoint: "/api/trades/42/partner/turns", includeScreenshot: true });
    await ask("Why?");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/trades/42/partner/turns");
    expect(sent(0).include_screenshot).toBe(true);
  });
});

describe("retrying", () => {
  it("reuses the SAME client turn id, so a question that went through is not bought twice", async () => {
    fetchMock
      .mockResolvedValueOnce(fail(503, "partner_unavailable"))
      .mockResolvedValueOnce(ok(reply("c-1", 0)));
    renderIt();
    await ask("Why?");
    expect(screen.getByText(/unavailable right now/i)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /ask that again/i }));
    });
    expect(sent(1).client_turn_id).toBe(sent(0).client_turn_id);
    expect(sent(1).question).toBe("Why?");
  });

  it("never retries on its own — each attempt is a paid call", async () => {
    fetchMock.mockResolvedValue(fail(503, "partner_unavailable"));
    renderIt();
    await ask("Why?");
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("treats a dropped connection as retryable with the same id", async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(ok(reply("c-1", 0)));
    renderIt();
    await ask("Why?");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /ask that again/i }));
    });
    expect(sent(1).client_turn_id).toBe(sent(0).client_turn_id);
  });
});

describe("refusals", () => {
  it("names the other tab on a duplicate and keeps the conversation", async () => {
    fetchMock.mockResolvedValue(fail(409, "duplicate_turn"));
    renderIt();
    await ask("Why?");
    expect(screen.getByText(/already being answered in another tab/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start a new conversation/i })).toBeNull();
  });

  it.each(["transcript_invalid", "conversation_full"])(
    "ends the conversation on %s and offers a fresh one",
    async (code) => {
      fetchMock.mockResolvedValueOnce(ok(reply("c-1", 0))).mockResolvedValueOnce(fail(409, code));
      renderIt();
      await ask("Why?");
      await ask("And then?");
      expect(screen.getByRole("textbox")).toBeDisabled();
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: /start a new conversation/i }));
      });
      expect(screen.getByRole("textbox")).toBeEnabled();
      expect(screen.getByText("Intro copy.")).toBeInTheDocument();

      fetchMock.mockResolvedValueOnce(ok(reply("c-2", 0)));
      await ask("Fresh start");
      const body = sent(2);
      expect(body.conversation_id).toBeNull();
      expect(body.transcript).toEqual([]);
    },
  );

  it("retires a reply that does not continue this tab's chain instead of repairing it", async () => {
    fetchMock.mockResolvedValueOnce(ok(reply("c-1", 0))).mockResolvedValueOnce(ok(reply("c-OTHER", 2)));
    renderIt();
    await ask("Why?");
    await ask("And then?");
    expect(screen.getByText(/can no longer be continued/i)).toBeInTheDocument();
    expect(screen.getAllByTestId("partner-turn-assistant")).toHaveLength(1);
  });

  it("shows no backend text, only the fixed copy", async () => {
    fetchMock.mockResolvedValue(fail(503, "anthropic overloaded req_SENSITIVE"));
    renderIt();
    await ask("Why?");
    expect(document.body.textContent).not.toContain("SENSITIVE");
  });
});

describe("rendering", () => {
  it("renders the answer as text, never as markup", async () => {
    fetchMock.mockResolvedValue(ok(reply("c-1", 0, "<img src=x onerror=alert(1)>")));
    renderIt();
    await ask("Why?");
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  });

  it("links only evidence the server linked, and only to a trade page", async () => {
    fetchMock.mockResolvedValue(
      ok({
        ...reply("c-1", 0),
        evidence: [
          { kind: "trade", label: "NQ long", occurred_on: "2026-09-01", trade_id: 42 },
          { kind: "strategy", label: "Your playbook", occurred_on: null, trade_id: null },
        ],
      }),
    );
    renderIt();
    await ask("Why?");
    await waitFor(() => expect(screen.getByTestId("partner-evidence")).toBeInTheDocument());
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/app/trades/42");
    expect(screen.getByText("Your playbook").closest("a")).toBeNull();
  });
});
