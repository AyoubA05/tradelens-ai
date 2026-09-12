import type { PartnerEvidence, PartnerTranscriptTurn } from "@/lib/app/partner";

/**
 * The browser's half of a stateless partner conversation.
 *
 * The server keeps no transcript. This module holds the only copy, and its
 * whole job is to hand that copy back *exactly* as it was received: the
 * `mac` on each turn is the server's signature over the owner, the
 * conversation, the turn's position, its role, its text and the turn before
 * it. Editing a turn here, reordering two, or dropping one does not produce
 * a shorter conversation — it produces a conversation the server refuses.
 *
 * So there is deliberately no "edit your last question", no local trimming
 * of old turns, and no merging of two tabs' transcripts. Every one of those
 * would be a 409 the trader could not act on.
 */

export type PartnerConversation = {
  conversationId: string | null;
  turns: PartnerTranscriptTurn[];
  evidence: PartnerEvidence[];
  screenshotAttached: boolean;
};

export type PartnerReply = {
  conversation_id: string;
  turns: PartnerTranscriptTurn[];
  evidence: PartnerEvidence[];
  screenshot_attached: boolean;
};

export const EMPTY_CONVERSATION: PartnerConversation = {
  conversationId: null,
  turns: [],
  evidence: [],
  screenshotAttached: false,
};

/**
 * A fresh id for one *attempt* — every send, retries included (plan D5).
 *
 * The server keeps a failed attempt's ticket and answers its id with
 * `duplicate_turn` from then on, so an id reused for a retry is refused
 * forever. The id's job is narrower: two tabs racing the SAME send are
 * recognised as one and paid for once. Double-clicks within one tab are
 * stopped before they are sent.
 */
export function newClientTurnId(): string {
  const uuid =
    typeof globalThis.crypto?.randomUUID === "function"
      ? globalThis.crypto.randomUUID()
      : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`.padEnd(32, "0");
  return uuid.replace(/-/g, "").slice(0, 32);
}

/**
 * Fold one reply into the conversation.
 *
 * The reply's two turns must continue the local chain exactly — same
 * conversation, and positions picking up where the local copy ends. When
 * they do not, the local copy and the server's idea of this conversation
 * have diverged, and every later turn built on it would be refused. Saying
 * so once, now, is the only honest option; `null` means "start over".
 */
export function applyReply(
  current: PartnerConversation,
  reply: PartnerReply,
): PartnerConversation | null {
  if (current.conversationId !== null && reply.conversation_id !== current.conversationId) {
    return null;
  }
  const expected = current.turns.length;
  const continues =
    reply.turns.length === 2 &&
    reply.turns[0].idx === expected &&
    reply.turns[1].idx === expected + 1 &&
    reply.turns[0].role === "user" &&
    reply.turns[1].role === "assistant";
  if (!continues) return null;
  return {
    conversationId: reply.conversation_id,
    turns: [...current.turns, ...reply.turns],
    evidence: reply.evidence,
    screenshotAttached: reply.screenshot_attached,
  };
}

/**
 * What a trader is told when a turn is refused.
 *
 * Every message names something the trader can do. None of them repeats a
 * code, a status, or anything the backend said: the relay already reduced
 * the failure to one of these, and a trader cannot act on "503".
 */
const CONFLICT_MESSAGES: Record<string, string> = {
  transcript_invalid:
    "This conversation can no longer be continued — it was changed or is from another session. Start a new one.",
  conversation_full: "This conversation is full. Start a new one to keep going.",
  no_trades: "Log a trade first. The partner only reflects on trades you have already logged.",
  duplicate_turn: "This question is already being answered in another tab.",
};

/** Refusals after which continuing the same transcript is pointless. */
const ENDS_CONVERSATION = new Set(["transcript_invalid", "conversation_full"]);

export type PartnerFailure = { text: string; endsConversation: boolean };

export function failureMessage(status: number, detail: unknown): PartnerFailure {
  const code = typeof detail === "string" ? detail : "";
  if (status === 409 && CONFLICT_MESSAGES[code]) {
    return {
      text: CONFLICT_MESSAGES[code],
      endsConversation: ENDS_CONVERSATION.has(code),
    };
  }
  if (status === 422) {
    return {
      text: "That question cannot be sent as written. Shorten it and try again.",
      endsConversation: false,
    };
  }
  if (status === 429) {
    return {
      text: "You have reached the limit for partner questions. Try again later.",
      endsConversation: false,
    };
  }
  if (status === 404) {
    return {
      text: "That trade is no longer available.",
      endsConversation: true,
    };
  }
  // 503, 502, and anything unforeseen: the turn did not happen, and trying
  // the same question again is the right next move.
  return {
    text: "The partner is unavailable right now. Try that question again in a moment.",
    endsConversation: false,
  };
}
