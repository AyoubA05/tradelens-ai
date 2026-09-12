import { describe, expect, it } from "vitest";

import {
  applyReply,
  EMPTY_CONVERSATION,
  failureMessage,
  newClientTurnId,
  type PartnerConversation,
  type PartnerReply,
} from "@/lib/app/partner-conversation";

/**
 * The browser holds the only copy of the conversation, and every turn in it
 * is signed by the server. These tests pin the two things that follow: the
 * copy is never edited, and a copy that has diverged is abandoned rather
 * than sent.
 */

function turn(idx: number, role: "user" | "assistant", text: string) {
  return {
    idx,
    role,
    text,
    iat: 1_700_000_000 + idx,
    mac: String(idx).repeat(64).slice(0, 64),
  };
}

function reply(id: string, at: number, over: Partial<PartnerReply> = {}): PartnerReply {
  return {
    conversation_id: id,
    turns: [turn(at, "user", "Why?"), turn(at + 1, "assistant", "Because.")],
    evidence: [],
    screenshot_attached: false,
    ...over,
  };
}

describe("client turn ids", () => {
  it("are long enough for the API's 16-character floor and are not reused", () => {
    const ids = new Set(Array.from({ length: 50 }, () => newClientTurnId()));
    expect(ids.size).toBe(50);
    for (const id of ids) {
      expect(id.length).toBeGreaterThanOrEqual(16);
      expect(id.length).toBeLessThanOrEqual(64);
      expect(id).not.toContain("-");
    }
  });
});

describe("folding a reply into the conversation", () => {
  it("adopts the server's conversation id on the first turn", () => {
    const next = applyReply(EMPTY_CONVERSATION, reply("c-1", 0));
    expect(next?.conversationId).toBe("c-1");
    expect(next?.turns).toHaveLength(2);
  });

  it("appends without touching a single stored turn", () => {
    const first = applyReply(EMPTY_CONVERSATION, reply("c-1", 0)) as PartnerConversation;
    const second = applyReply(first, reply("c-1", 2)) as PartnerConversation;
    expect(second.turns).toHaveLength(4);
    // The turns the first reply signed are byte-identical in the second state.
    expect(second.turns.slice(0, 2)).toEqual(first.turns);
    expect(second.turns.map((t) => t.idx)).toEqual([0, 1, 2, 3]);
  });

  it("replaces evidence with the current turn's, and does not accumulate it", () => {
    const cited = {
      kind: "trade" as const,
      label: "NQ 2026-09-01",
      occurred_on: "2026-09-01",
      trade_id: 42,
    };
    const first = applyReply(
      EMPTY_CONVERSATION,
      reply("c-1", 0, { evidence: [cited] }),
    ) as PartnerConversation;
    const second = applyReply(first, reply("c-1", 2)) as PartnerConversation;
    expect(first.evidence).toEqual([cited]);
    expect(second.evidence).toEqual([]);
  });

  it("abandons the conversation when the reply is for a different one", () => {
    const first = applyReply(EMPTY_CONVERSATION, reply("c-1", 0)) as PartnerConversation;
    expect(applyReply(first, reply("c-2", 2))).toBeNull();
  });

  it.each([
    ["a gap", 3],
    ["a repeat of the last position", 1],
    ["a position already used", 0],
  ])("abandons the conversation when the reply starts at %s", (_label, at) => {
    const first = applyReply(EMPTY_CONVERSATION, reply("c-1", 0)) as PartnerConversation;
    expect(applyReply(first, reply("c-1", at))).toBeNull();
  });

  it("checks EACH turn's position, not just the last one", () => {
    // The assistant turn lands exactly where it should; only the user turn
    // is out of place. A check that looked at one end of the pair would
    // accept a user turn from anywhere in the chain.
    const first = applyReply(EMPTY_CONVERSATION, reply("c-1", 0)) as PartnerConversation;
    const misplaced = {
      ...reply("c-1", 2),
      turns: [turn(9, "user", "Why?"), turn(3, "assistant", "Because.")],
    };
    expect(applyReply(first, misplaced)).toBeNull();
  });

  it.each([
    ["the user turn's role", 0, "assistant"],
    ["the assistant turn's role", 1, "user"],
  ] as const)("abandons the conversation when only %s is wrong", (_label, which, role) => {
    // One role at a time: a swapped pair breaks BOTH checks, so a test that
    // only swaps them cannot tell whether either check is still there.
    const r = reply("c-1", 0);
    const turns = r.turns.map((t, i) => (i === which ? { ...t, role } : t));
    expect(applyReply(EMPTY_CONVERSATION, { ...r, turns })).toBeNull();
  });

  it("abandons the conversation when the pair is not user-then-assistant", () => {
    const swapped = {
      ...reply("c-1", 0),
      turns: [turn(0, "assistant", "Because."), turn(1, "user", "Why?")],
    };
    expect(applyReply(EMPTY_CONVERSATION, swapped)).toBeNull();
  });

  it.each([0, 1, 3])("abandons the conversation when the reply carries %i turns", (count) => {
    const wrong = {
      ...reply("c-1", 0),
      turns: Array.from({ length: count }, (_, i) => turn(i, "user", "x")),
    };
    expect(applyReply(EMPTY_CONVERSATION, wrong)).toBeNull();
  });
});

describe("what a refused turn tells the trader", () => {
  it("names the other tab when the same question is already in flight", () => {
    const failure = failureMessage(409, "duplicate_turn");
    expect(failure.text).toContain("another tab");
    expect(failure.endsConversation).toBe(false);
  });

  it.each(["transcript_invalid", "conversation_full"])("ends the conversation on %s", (code) => {
    const failure = failureMessage(409, code);
    expect(failure.endsConversation).toBe(true);
    expect(failure.text).toContain("new one");
  });

  it("tells a trader with no trades what to do first", () => {
    const failure = failureMessage(409, "no_trades");
    expect(failure.action).toEqual({ href: "/app/trades/new", label: "Log a trade" });
    expect(failure.retryable).toBe(false);
  });

  it("does not end the conversation when the partner is merely unavailable", () => {
    const failure = failureMessage(503, "partner_unavailable");
    expect(failure.endsConversation).toBe(false);
    expect(failure.text).toContain("still here");
    expect(failure.retryable).toBe(true);
  });

  it.each([
    [409, "some_unknown_code"],
    [502, null],
    [500, { nested: "object" }],
  ])("falls back to the retry message for %i / %j", (status, detail) => {
    expect(failureMessage(status, detail).text).toContain("could not answer");
    expect(failureMessage(status, detail).retryable).toBe(true);
  });

  it("never repeats a status code or a backend code back to the trader", () => {
    for (const [status, detail] of [
      [409, "transcript_invalid"],
      [409, "conversation_full"],
      [409, "no_trades"],
      [409, "duplicate_turn"],
      [422, null],
      [429, "rate_limited"],
      [404, null],
      [503, "partner_unavailable"],
    ] as const) {
      const { text } = failureMessage(status, detail);
      expect(text).not.toContain(String(status));
      expect(text).not.toContain("_");
    }
  });
});

describe("which refusals offer a retry", () => {
  it.each([
    [409, "duplicate_turn"],
    [409, "transcript_invalid"],
    [409, "conversation_full"],
    [409, "no_trades"],
    [422, null],
    [429, "rate_limited"],
    [404, null],
  ] as const)("offers none for %i / %s", (status, detail) => {
    // duplicate_turn above all: that send is already in flight, and a retry is
    // a fresh attempt — a second paid call for an answer on its way.
    expect(failureMessage(status, detail).retryable).toBe(false);
  });

  it.each([503, 502, 500, 0])("offers one for %i", (status) => {
    expect(failureMessage(status, null).retryable).toBe(true);
  });
});
