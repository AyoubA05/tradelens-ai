import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PartnerConversation } from "@/components/app/partner/conversation";

/**
 * The conversation island. What matters is what it SENDS: the transcript
 * exactly as the server signed it, a fresh client turn id for every attempt, and
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

/**
 * A fetch that behaves like the real API's ticket, not like a mock that says
 * yes: an id whose attempt failed is answered `duplicate_turn` from then on
 * (`enqueue_with_limit` returns the existing ticket whatever its status).
 * The earlier retry tests mocked a 200 for a reused id — a response the real
 * server never gives — and so pinned the very bug that jammed conversations.
 */
function serverLikeTicket(outcomes: Array<"unavailable" | "drop" | "ok">) {
  const burned = new Set<string>();
  let okAt = 0;
  fetchMock.mockImplementation(async (_url: string, init: { body: string }) => {
    const { client_turn_id: id } = JSON.parse(init.body);
    if (burned.has(id)) return fail(409, "duplicate_turn");
    burned.add(id);
    const outcome = outcomes.shift() ?? "ok";
    if (outcome === "drop") throw new TypeError("Failed to fetch");
    if (outcome === "unavailable") return fail(503, "partner_unavailable");
    const r = reply("c-1", okAt);
    okAt += 2;
    return ok(r);
  });
}

async function retry() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /ask that again/i }));
  });
}

describe("retrying", () => {
  it("retries with a FRESH client turn id, so a failed attempt's ticket cannot jam it", async () => {
    serverLikeTicket(["unavailable", "ok"]);
    renderIt();
    await ask("Why?");
    expect(screen.getByText(/could not answer just now/i)).toBeInTheDocument();
    await retry();
    expect(sent(1).client_turn_id).not.toBe(sent(0).client_turn_id);
    expect(sent(1).question).toBe("Why?");
    // Against a server that refuses a reused id, only a fresh id gets here.
    expect(screen.getAllByTestId("partner-turn-assistant")).toHaveLength(1);
    expect(screen.queryByText(/another tab/i)).toBeNull();
  });

  it("recovers from a dropped connection the same way", async () => {
    serverLikeTicket(["drop", "ok"]);
    renderIt();
    await ask("Why?");
    await retry();
    expect(sent(1).client_turn_id).not.toBe(sent(0).client_turn_id);
    expect(screen.getAllByTestId("partner-turn-assistant")).toHaveLength(1);
  });

  it("does not jam the NEXT question after a failure either", async () => {
    serverLikeTicket(["unavailable", "ok"]);
    renderIt();
    await ask("Why?");
    await ask("A different question");
    expect(sent(1).client_turn_id).not.toBe(sent(0).client_turn_id);
    expect(sent(1).question).toBe("A different question");
    expect(screen.getAllByTestId("partner-turn-assistant")).toHaveLength(1);
  });

  it("retries the question that failed, not whatever is in the box now", async () => {
    serverLikeTicket(["unavailable", "ok"]);
    renderIt();
    await ask("Why?");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "half-typed next" } });
    await retry();
    expect(sent(1).question).toBe("Why?");
    // The trader's unsent typing survives a retry of the earlier question.
    expect(screen.getByRole("textbox")).toHaveValue("half-typed next");
  });

  it("sends an edited question as its own attempt, and retries THAT one", async () => {
    serverLikeTicket(["unavailable", "unavailable", "ok"]);
    renderIt();
    await ask("Question A");
    await ask("Question B");
    expect(sent(1).question).toBe("Question B");
    expect(sent(1).client_turn_id).not.toBe(sent(0).client_turn_id);
    await retry();
    expect(sent(2).question).toBe("Question B");
    expect(new Set([0, 1, 2].map((n) => sent(n).client_turn_id)).size).toBe(3);
  });

  it("never retries on its own — each attempt is a paid call", async () => {
    fetchMock.mockResolvedValue(fail(503, "partner_unavailable"));
    renderIt();
    await ask("Why?");
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sends ONE request for a double-click, even inside one frame", async () => {
    let release: (v: unknown) => void = () => {};
    fetchMock.mockImplementation(() => new Promise((r) => (release = r)));
    renderIt();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Why?" } });
    const button = screen.getByRole("button", { name: /^ask$/i });
    await act(async () => {
      fireEvent.click(button);
      fireEvent.click(button);
      fireEvent.submit(button.closest("form")!);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await act(async () => release(ok(reply("c-1", 0))));
    expect(screen.getAllByTestId("partner-turn-assistant")).toHaveLength(1);
  });

  it("clears an earlier failure message once an answer arrives", async () => {
    serverLikeTicket(["unavailable", "ok"]);
    renderIt();
    await ask("Why?");
    expect(screen.getByText(/could not answer just now/i)).toBeInTheDocument();
    await retry();
    expect(screen.queryByText(/could not answer just now/i)).toBeNull();
    expect(screen.queryByRole("button", { name: /ask that again/i })).toBeNull();
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
      // The conversation clears only when the trader presses the button (plan
      // Group D) — until then the earlier answer stays on screen. Without this,
      // clearing it on the refusal itself went unnoticed (battery R2-U9).
      expect(screen.getAllByTestId("partner-turn-assistant")).toHaveLength(1);
      expect(screen.getByText("Because.")).toBeInTheDocument();
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: /start a new conversation/i }));
      });
      expect(screen.queryAllByTestId("partner-turn-assistant")).toHaveLength(0);
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
    expect(screen.getByText(/can no longer continue/i)).toBeInTheDocument();
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

describe("the plan's Group D contract", () => {
  it("sends exactly question, conversation_id, transcript and client_turn_id", async () => {
    fetchMock.mockResolvedValue(ok(reply("c-1", 0)));
    renderIt();
    await ask("Why?");
    expect(Object.keys(sent(0)).sort()).toEqual([
      "client_turn_id",
      "conversation_id",
      "question",
      "transcript",
    ]);
  });

  it("adds only include_screenshot on the trade panel", async () => {
    fetchMock.mockResolvedValue(ok(reply("c-1", 0)));
    renderIt({ endpoint: "/api/trades/42/partner/turns", includeScreenshot: false });
    await ask("Why?");
    expect(Object.keys(sent(0)).sort()).toEqual([
      "client_turn_id",
      "conversation_id",
      "include_screenshot",
      "question",
      "transcript",
    ]);
  });

  it("writes nothing to localStorage or sessionStorage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    try {
      fetchMock
        .mockResolvedValueOnce(ok(reply("c-1", 0)))
        .mockResolvedValueOnce(ok(reply("c-1", 2)));
      renderIt();
      await ask("Why?");
      await ask("And then?");
      expect(setItem).not.toHaveBeenCalled();
      expect(window.localStorage.length).toBe(0);
      expect(window.sessionStorage.length).toBe(0);
    } finally {
      setItem.mockRestore();
    }
  });

  it("keeps the typed question when a request fails", async () => {
    fetchMock.mockResolvedValue(fail(503, "partner_unavailable"));
    renderIt();
    await ask("Why did I size up?");
    expect(screen.getByRole("textbox")).toHaveValue("Why did I size up?");
    expect(screen.getByText(/your question is still here/i)).toBeInTheDocument();
  });

  it("labels evidence 'Context used', never as citations", async () => {
    fetchMock.mockResolvedValue(
      ok({
        ...reply("c-1", 0),
        evidence: [{ kind: "trade", label: "NQ long", occurred_on: "2026-09-01", trade_id: 42 }],
      }),
    );
    renderIt();
    await ask("Why?");
    const evidence = screen.getByTestId("partner-evidence");
    expect(evidence).toHaveTextContent("Context used");
    expect(evidence.textContent).not.toMatch(/source|cite/i);
  });

  it("offers suggestions only on an empty conversation, and a suggestion never sends by itself", async () => {
    fetchMock.mockResolvedValue(ok(reply("c-1", 0)));
    renderIt({ suggestions: ["Where did I break my own rules?"] });
    fireEvent.click(screen.getByRole("button", { name: "Where did I break my own rules?" }));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox")).toHaveValue("Where did I break my own rules?");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^ask$/i }));
    });
    expect(sent(0).question).toBe("Where did I break my own rules?");
    expect(screen.queryByRole("button", { name: "Where did I break my own rules?" })).toBeNull();
  });

  it("offers no suggestions unless the caller supplies them", () => {
    renderIt();
    expect(screen.queryByRole("list", { name: /suggested questions/i })).toBeNull();
  });

  it("disables the composer while a question is pending", async () => {
    let release: (v: unknown) => void = () => {};
    fetchMock.mockImplementation(() => new Promise((r) => (release = r)));
    renderIt();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Why?" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /^ask$/i }));
    });
    expect(screen.getByRole("textbox")).toBeDisabled();
    await act(async () => release(ok(reply("c-1", 0))));
    expect(screen.getByRole("textbox")).toBeEnabled();
  });

  it("says the conversation is not saved", () => {
    renderIt();
    expect(
      screen.getByText("This conversation is not saved — it clears when you reload or sign out."),
    ).toBeInTheDocument();
  });

  it("links a trader with no trades to logging one, and offers no pointless retry", async () => {
    fetchMock.mockResolvedValue(fail(409, "no_trades"));
    renderIt();
    await ask("Why?");
    expect(screen.getByRole("link", { name: /log a trade/i })).toHaveAttribute(
      "href",
      "/app/trades/new",
    );
    expect(screen.queryByRole("button", { name: /ask that again/i })).toBeNull();
  });

  it("never offers a retry for a send already in flight in another tab — that would pay twice", async () => {
    fetchMock.mockResolvedValue(fail(409, "duplicate_turn"));
    renderIt();
    await ask("Why?");
    expect(screen.getByText(/another tab/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /ask that again/i })).toBeNull();
  });

  it("contains no advice or signal language", async () => {
    fetchMock.mockResolvedValue(fail(503, "partner_unavailable"));
    const { container } = renderIt({
      suggestions: [
        "What did I repeat most last week?",
        "Where did I break my own rules?",
        "Which of my logged mistakes cost the most?",
      ],
    });
    await ask("q");
    expect(container.textContent).not.toMatch(
      /\b(you should|buy|sell|signal|guaranteed|recommend)/i,
    );
  });
});

describe("a signed-out session", () => {
  it("links to sign in and offers no retry that would fail the same way", async () => {
    fetchMock.mockResolvedValue(fail(401));
    renderIt();
    await ask("Why?");
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("button", { name: /ask that again/i })).toBeNull();
  });
});
